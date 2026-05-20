from typing import Any, Optional, List

from module.node.base.base import BaseProcessor


class MergeProcessor(BaseProcessor):
    """
    지정된 개수의 입력을 모을 때까지 대기한 후
    하나의 데이터로 합쳐 반환하는 Processor.
    """

    def __init__(
        self,
        count: int,
        separator: str = "",
        numbered: bool = False,
        verbose: bool = False,
    ):
        super().__init__()

        self.count = count
        self.separator = separator
        self.numbered = numbered
        self.verbose = verbose

        self._buffer: List[Any] = []

    async def process(self, data: Any) -> Optional[Any]:

        if self.verbose and self.node is not None:
            print(f"[{self.node.node_id}] received: {data}")

        self._buffer.append(data)

        # 아직 충분히 모이지 않았으면 대기
        if len(self._buffer) < self.count:
            return None

        parts: List[str] = []

        if self.numbered:

            for i, item in enumerate(self._buffer):
                parts.append(f"{self.separator}{i+1}. {item}")

        else:

            for item in self._buffer:
                parts.append(f"{self.separator}{item}")

        merged = "\n".join(parts)

        if self.verbose and self.node is not None:
            print(f"[{self.node.node_id}] merged {len(self._buffer)} items")

        # 버퍼 초기화
        self._buffer.clear()

        return merged