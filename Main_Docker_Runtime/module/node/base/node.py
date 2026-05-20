from typing import Optional

from module.node.base.base import BaseProcessor
from module.node.base.interface import RealNodeInterface


class Node:
    """
    실제 구동 단위.
    Interface와 BaseProcessor를 조합하여 실행한다.
    """

    def __init__(
        self,
        node_id: str,
        base: BaseProcessor,
        interface: Optional[RealNodeInterface] = None,
        context: Optional[dict] = None,
    ):
        self.node_id = node_id
        self.context = context or {}

        self.iface = interface or RealNodeInterface(
            node_id=node_id,
            context=self.context,
        )

        self.base = base
        self.base.bind_node(self)

        self._started = False
        self._running = True

    async def start(self):
        if self._started:
            return
        await self.base.on_start()
        self._started = True

    async def stop(self):
        if not self._running:
            return
        await self.base.on_stop()
        self._running = False

    async def tick(self):

        if not self._running:
            return

        if not self._started:
            await self.start()

        # 1. interface 처리
        await self.iface.tick()

        # 2. 입력 수신
        data = await self.iface.dequeue()

        if data is None:
            await self.base.on_idle()
            return

        # 3. base 실행
        try:
            result = await self.base.process(data)
        except Exception as exc:
            await self.iface.emit_error(
                f"PROCESS_ERROR:{type(exc).__name__}:{exc}"
            )
            return

        # 4. signal 확인 (optional)
        signal_name, signal_data = self.base.consume_signal()

        if signal_name is not None:

            # error signal
            if signal_name == "error":

                # result가 있으면 그대로
                if result is not None:
                    await self.iface.emit(result)
                else:
                    await self.iface.emit("")

                return

            # skip → 빈 메시지
            if signal_name == "skip":
                await self.iface.emit("")
                return

            # branch / control
            if signal_name == "branch":
                await self.iface.emit(signal_data, kind="control")
                return

            # custom signal → control message
            await self.iface.emit(
                {"signal": signal_name, "data": signal_data},
                kind="control",
            )
            return

        # 5. 일반 출력
        if result is not None:
            await self.iface.emit(result)