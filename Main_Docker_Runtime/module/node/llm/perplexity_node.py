import os
import re
from typing import Any, Optional

from module.node.base.base import BaseProcessor

from openai import AsyncOpenAI


class PerplexityProcessor(BaseProcessor):
    """
    NodeConnect용 Perplexity 검색 노드

    input → Perplexity search → cleaned text output
    """

    DEFAULT_SYSTEM_PROMPT = """
You are an information retrieval engine.

Return factual information extracted from reliable sources.

Output rules:
- Plain text only
- No markdown
- No citations
- No references
- No links
- No reasoning
- No opinions
- No speculation
- No explanation about sources

Focus on:
- factual data
- definitions
- mechanisms
- technical descriptions

Prefer:
- official documentation
- academic sources
- technical sources

Prefer recent information when applicable.
""".strip()

    def __init__(
        self,
        persona: str = "",
        api_key: Optional[str] = None,
        model: str = "sonar",
        temperature: float = 0.2,
        verbose: bool = False,
    ):
        super().__init__()

        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.persona = persona
        self.model = model
        self.temperature = temperature
        self.verbose = verbose

        self.client = None

    async def on_start(self):

        if not self.api_key:
            raise RuntimeError("PERPLEXITY_API_KEY not set")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.perplexity.ai"
        )

    def _build_prompt(self, data: Any) -> str:

        if isinstance(data, str):
            return data

        if isinstance(data, dict):

            parts = []

            if "query" in data:
                parts.append(str(data["query"]))

            if "context" in data:
                parts.append("Context:\n" + str(data["context"]))

            for k, v in data.items():
                if k not in {"query", "context"}:
                    parts.append(f"{k}:\n{v}")

            return "\n\n".join(parts)

        return str(data)

    def _clean_output(self, text: str) -> str:
        """
        Perplexity 결과에서 노이즈 제거
        """

        if not text:
            return text

        # citation 제거
        text = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", text)

        # markdown 제거
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)

        # URL 제거
        text = re.sub(r"https?://\S+", "", text)

        # meta 문장 제거
        noise_patterns = [
            r"According to.*?:",
            r"Search results.*?:",
            r"Sources indicate.*?:",
            r"Based on the search results.*?:",
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # 과도한 공백 제거
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    async def process(self, data: Any) -> Optional[Any]:

        if data is None:
            return None

        prompt = self._build_prompt(data)

        if self.verbose and self.node:
            print(f"[{self.node.node_id}] query:\n{prompt}")

        system_prompt = self.DEFAULT_SYSTEM_PROMPT

        if self.persona:
            system_prompt += "\n\n" + self.persona

        try:

            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )

        except Exception as e:

            if self.verbose and self.node:
                print(f"[{self.node.node_id}] Perplexity error: {e}")

            # 오류 플래그만 설정
            self.signal("error")

            # 출력은 빈 값
            return ""

        if not response or not response.choices:
            self.signal("error")
            return ""

        result = response.choices[0].message.content

        if not result:
            self.signal("error")
            return ""

        result = self._clean_output(result)

        if self.verbose and self.node:
            print(f"[{self.node.node_id}] response:\n{result}")

        return result