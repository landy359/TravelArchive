import asyncio
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

from module.node.base.message import Message, StreamChunk, create_message


MAX_PAYLOAD_SIZE = 1024


@dataclass
class StreamBuffer:
    source: str
    stream_id: str
    total_chunks: Optional[int] = None
    chunks: Dict[int, Union[str, bytes]] = field(default_factory=dict)
    started: bool = False
    ended: bool = False
    start_time: float = field(default_factory=time.time)
    data_type: Optional[type] = None


class RealNodeInterface:
    """
    4-Queue + Tick 기반의 노드 인터페이스.
    - 메시지 생성/해제
    - 스트림 분할/재조립
    - 라우터와 베이스 간 데이터 경계 처리
    """

    def __init__(
        self,
        node_id: str,
        context: Optional[dict] = None,
        max_payload_size: int = MAX_PAYLOAD_SIZE,
        stream_timeout: float = 5.0,
        max_inbound_per_tick: int = 16,
        max_outbound_per_tick: int = 16,
    ):
        self.node_id = node_id
        self.context = context or {}

        self.node_out_q: asyncio.Queue[Any] = asyncio.Queue()
        self.node_in_q: asyncio.Queue[Any] = asyncio.Queue()
        self.to_router_q: asyncio.Queue[Message] = asyncio.Queue()
        self.from_router_q: asyncio.Queue[Message] = asyncio.Queue()

        self.max_payload_size = max_payload_size
        self.stream_timeout = stream_timeout
        self.max_inbound_per_tick = max_inbound_per_tick
        self.max_outbound_per_tick = max_outbound_per_tick

        self._stream_buffers: Dict[Tuple[str, str], StreamBuffer] = {}

    # =========================
    # Base(Node) API
    # =========================

    async def dequeue(self) -> Any:
        if self.node_in_q.empty():
            return None
        return await self.node_in_q.get()

    async def emit(self, result: Any, kind: str = "data", target: Optional[str] = None):
        """
        베이스가 순수 데이터를 인터페이스에 전달한다.
        인터페이스는 이후 tick()에서 메시지화 또는 스트리밍 분할을 수행한다.
        """
        await self.node_out_q.put({
            "kind": kind,
            "target": target,
            "data": result,
        })

    async def emit_error(self, reason: str, target: Optional[str] = None):
        await self.node_out_q.put({
            "kind": "error",
            "target": target,
            "data": {"error": reason},
        })

    # =========================
    # Tick
    # =========================

    async def tick(self):
        await self._process_outbound()
        await self._process_inbound()
        await self._check_stream_timeouts()

    # =========================
    # Outbound
    # =========================

    async def _process_outbound(self):
        processed = 0

        while processed < self.max_outbound_per_tick and not self.node_out_q.empty():
            item = await self.node_out_q.get()
            processed += 1

            kind = item.get("kind", "data")
            target = item.get("target")
            data = item.get("data")

            if self._should_stream(data):
                async for msg in self._fragment_stream(
                    data=data,
                    kind="stream",
                    target=target,
                ):
                    await self.to_router_q.put(msg)
            else:
                msg = create_message(
                    source=self.node_id,
                    kind=kind,
                    data=data,
                    target=target,
                )
                await self.to_router_q.put(msg)

    def _should_stream(self, data: Any) -> bool:
        if isinstance(data, str):
            return len(data) > self.max_payload_size
        if isinstance(data, bytes):
            return len(data) > self.max_payload_size
        return False

    async def _fragment_stream(
        self,
        data: Union[str, bytes],
        kind: str = "stream",
        target: Optional[str] = None,
    ):
        stream_id = str(uuid.uuid4())
        total_len = len(data)
        total_chunks = max(1, math.ceil(total_len / self.max_payload_size))

        for index in range(total_chunks):
            start = index * self.max_payload_size
            end = start + self.max_payload_size
            chunk_data = data[start:end]

            chunk = StreamChunk(
                stream_id=stream_id,
                index=index,
                data=chunk_data,
                total=total_chunks,
                is_start=(index == 0),
                is_end=(index == total_chunks - 1),
            )

            yield create_message(
                source=self.node_id,
                kind=kind,
                data=chunk,
                target=target,
            )

    # =========================
    # Inbound
    # =========================

    async def _process_inbound(self):
        processed = 0

        while processed < self.max_inbound_per_tick and not self.from_router_q.empty():
            msg = await self.from_router_q.get()
            processed += 1

            if isinstance(msg.data, StreamChunk):
                assembled = await self._handle_stream_message(msg)
                if assembled is not None:
                    await self.node_in_q.put(assembled)
                continue

            await self.node_in_q.put(msg.data)

    async def _handle_stream_message(self, msg: Message) -> Optional[Union[str, bytes]]:
        chunk = msg.data
        key = (msg.source, chunk.stream_id)

        buf = self._stream_buffers.get(key)
        if buf is None:
            buf = StreamBuffer(
                source=msg.source,
                stream_id=chunk.stream_id,
                total_chunks=chunk.total,
            )
            self._stream_buffers[key] = buf

        if chunk.is_start:
            buf.started = True
            buf.start_time = time.time()

        if buf.total_chunks is None and chunk.total is not None:
            buf.total_chunks = chunk.total

        if chunk.data is not None:
            if buf.data_type is None:
                buf.data_type = type(chunk.data)
            elif buf.data_type is not type(chunk.data):
                # 혼합 타입 스트림은 폐기
                del self._stream_buffers[key]
                return None

            if chunk.index not in buf.chunks:
                buf.chunks[chunk.index] = chunk.data

        if chunk.is_end:
            buf.ended = True

        if self._is_stream_complete(buf):
            merged = self._assemble(buf)
            del self._stream_buffers[key]
            return merged

        return None

    def _is_stream_complete(self, buf: StreamBuffer) -> bool:
        if buf.total_chunks is None:
            return False
        if not buf.ended:
            return False

        expected = set(range(buf.total_chunks))
        actual = set(buf.chunks.keys())
        return actual == expected

    def _assemble(self, buf: StreamBuffer) -> Union[str, bytes]:
        ordered = [buf.chunks[i] for i in range(buf.total_chunks or 0)]

        if buf.data_type is bytes:
            return b"".join(ordered)

        return "".join(ordered)

    # =========================
    # Stream timeout
    # =========================

    async def _check_stream_timeouts(self):
        now = time.time()
        expired = [
            key
            for key, buf in self._stream_buffers.items()
            if now - buf.start_time > self.stream_timeout
        ]

        for key in expired:
            del self._stream_buffers[key]

            await self.to_router_q.put(
                create_message(
                    source=self.node_id,
                    kind="error",
                    data={
                        "error": "stream_timeout",
                        "stream_source": key[0],
                        "stream_id": key[1],
                    },
                )
            )