from typing import Any, Optional

from module.node.base.base import BaseProcessor


class EchoProcessor(BaseProcessor):
    """
    입력 데이터를 그대로 반환하는 가장 단순한 공용 처리기.
    """

    def __init__(self, verbose: bool = False):
        super().__init__()
        self.verbose = verbose

    async def process(self, data: Any) -> Optional[Any]:
        if self.verbose and self.node is not None:
            print(f"[{self.node.node_id}] received: {data}")
        return data