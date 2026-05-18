import os
from typing import Final

from openai import AsyncOpenAI


PERSONA: Final[str] = "마크다운, 이모티콘, 이모지를 절대 사용하지 말 것.\n"


class GptNode:
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        self.model_name: str = model_name
        self.client: AsyncOpenAI = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

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