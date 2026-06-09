import asyncio
import os
from typing import Final, TypeAlias

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError


PERSONA: Final[str] = "마크다운, 이모티콘, 이모지를 절대 사용하지 말 것.\n답변은 반드시 1024자 이내로 작성할 것.\n"

ImagePayload: TypeAlias = tuple[str, str]  # (base64_str, mime_type)
UserContent: TypeAlias = "str | list[dict]"

_client_cache: dict[str, AsyncOpenAI] = {}

_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds (doubled each attempt)


def _get_client(api_key: str) -> AsyncOpenAI:
    if api_key not in _client_cache:
        _client_cache[api_key] = AsyncOpenAI(api_key=api_key)
    return _client_cache[api_key]


def _build_image_content(images: list[ImagePayload], prompt: str) -> list[dict]:
    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        for b64, mime in images
    ]
    content.append({"type": "text", "text": prompt})
    return content


class LLM:
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model_name: str = model_name
        self._api_key: str = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.client: AsyncOpenAI = _get_client(self._api_key)

    async def ask(self, prompt: str, images: list[ImagePayload] | None = None, json_mode: bool = False, max_tokens: int | None = None) -> str:
        """images: [(base64_str, mime_type), ...] 형태. 있으면 vision 요청.
        json_mode=True 시 response_format=json_object 강제 (JSON 외 출력 차단).
        재시도 가능한 에러(연결·타임아웃·레이트리밋)는 최대 3회 재시도."""
        user_content: list[dict] | str = _build_image_content(images, prompt) if images else prompt
        last_exc: Exception | None = None
        delay = _RETRY_DELAY
        # json_mode(port3 구조 출력)는 제한 없음. 일반 응답은 기본 1024 토큰.
        effective_max_tokens = max_tokens if max_tokens is not None else (None if json_mode else 1024)
        for attempt in range(_MAX_RETRIES):
            try:
                kwargs: dict = dict(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": PERSONA},
                        {"role": "user", "content": user_content},
                    ],
                )
                if json_mode and not images:
                    kwargs["response_format"] = {"type": "json_object"}
                if effective_max_tokens is not None:
                    kwargs["max_tokens"] = effective_max_tokens
                response = await self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                return content or ""
            except _RETRYABLE as e:
                last_exc = e
                print(f"[LLM] 재시도 {attempt + 1}/{_MAX_RETRIES}: {type(e).__name__}: {e}")
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as e:
                print(f"[LLM] 복구 불가 에러: {type(e).__name__}: {e}")
                raise
        raise last_exc
