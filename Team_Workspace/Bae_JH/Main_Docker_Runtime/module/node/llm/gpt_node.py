import os
import asyncio
from typing import Any, Optional

from module.node.base.base import BaseProcessor

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class GPTProcessor(BaseProcessor):
    """
    NodeConnect용 GPT 처리 노드
    input → LLM → output
    """

    def __init__(
        self,
        persona: str = "",
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        verbose: bool = False,
    ):
        super().__init__()

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.persona = persona
        self.temperature = temperature
        self.model = model
        self.verbose = verbose

        self.llm = None

    async def on_start(self):

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        self.llm = ChatOpenAI(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
        )

    def _build_prompt(self, data: Any) -> str:

        if isinstance(data, str):
            return data

        if isinstance(data, dict):

            parts = []

            if "context" in data:
                parts.append("Context:\n" + str(data["context"]))

            if "history" in data:
                parts.append("History:\n" + str(data["history"]))

            if "query" in data:
                parts.append("User Query:\n" + str(data["query"]))

            for k, v in data.items():
                if k not in {"query", "context", "history"}:
                    parts.append(f"{k}:\n{v}")

            return "\n\n".join(parts)

        return str(data)

    async def process(self, data: Any) -> Optional[Any]:

        if data is None:
            return None

        prompt = self._build_prompt(data)

        if self.verbose and self.node:
            print(f"[{self.node.node_id}] prompt:\n{prompt}")

        try:

            messages = [
                SystemMessage(content=self.persona),
                HumanMessage(content=prompt),
            ]

            response = await self.llm.ainvoke(messages)

        except Exception as e:
            print(f"[GPTProcessor] LLM 오류 ({self.model}): {type(e).__name__}: {str(e)[:120]}")
            return None

        result = response.content

        if self.verbose and self.node:
            print(f"[{self.node.node_id}] response:\n{result}")

        return result