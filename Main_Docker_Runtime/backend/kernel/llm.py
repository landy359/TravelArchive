import os
from typing import Final, TypeAlias

from openai import AsyncOpenAI


PERSONA: Final[str] = "마크다운, 이모티콘, 이모지를 절대 사용하지 말 것.\n"

ImagePayload: TypeAlias = tuple[str, str]  # (base64_str, mime_type)
UserContent: TypeAlias = "str | list[dict]"

_client_cache: dict[str, AsyncOpenAI] = {}


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

    async def ask(self, prompt: str, images: list[ImagePayload] | None = None) -> str:
        """images: [(base64_str, mime_type), ...] 형태. 있으면 vision 요청."""
        user_content: list[dict] | str = _build_image_content(images, prompt) if images else prompt
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PERSONA},
                    {"role": "user", "content": user_content},
                ],
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            return f"ERROR: {str(e)}"
