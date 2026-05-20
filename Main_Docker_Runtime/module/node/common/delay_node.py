import asyncio
from typing import Any, Optional

from module.node.base.base import BaseProcessor


class DelayProcessor(BaseProcessor):
    """
    입력 데이터를 지정된 시간(ms)만큼 지연한 뒤 그대로 반환하는 Processor.
    """

    def __init__(self, delay_ms: int, verbose: bool = False):
        super().__init__()
        self.delay_ms = delay_ms
        self.verbose = verbose

    async def process(self, data: Any) -> Optional[Any]:

        if self.verbose and self.node is not None:
            print(f"[{self.node.node_id}] received: {data}")

        # ms → seconds
        await asyncio.sleep(self.delay_ms / 1000)

        if self.verbose and self.node is not None:
            print(f"[{self.node.node_id}] echo after {self.delay_ms} ms")

        return data