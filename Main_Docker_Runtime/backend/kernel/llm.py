import os
from typing import Final

from openai import AsyncOpenAI


PERSONA: Final[str] = "마크다운, 이모티콘, 이모지를 절대 사용하지 말 것.\n"

# 모델명 + API키 조합별 클라이언트를 캐싱한다.
# AsyncOpenAI는 내부적으로 connection pool을 유지하므로 재생성 비용이 크다.
_client_cache: dict[str, AsyncOpenAI] = {}


def _get_client(api_key: str) -> AsyncOpenAI:
    if api_key not in _client_cache:
        _client_cache[api_key] = AsyncOpenAI(api_key=api_key)
    return _client_cache[api_key]


class LLM:
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model_name: str = model_name
        self._api_key: str = api_key or os.getenv("OPENAI_API_KEY") or ""
        self.client: AsyncOpenAI = _get_client(self._api_key)

    async def ask(self, prompt: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": PERSONA},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            return f"ERROR: {str(e)}"
