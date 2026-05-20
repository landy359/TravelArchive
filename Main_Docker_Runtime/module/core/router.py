import asyncio
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, Union

from src.node.base.node import Node
from src.node.base.base import BaseProcessor
from src.node.base.message import Message, StreamChunk, create_message


EXTERNAL_SOURCE = "__router_external__"


@dataclass
class NodeStats:
    """
    노드별 런타임 메타데이터.
    """
    input_count: int = 0
    output_count: int = 0
    run_count: int = 0
    unique_input_count: int = 0
    unique_output_count: int = 0
    last_active_at: float = field(default_factory=time.time)

    seen_input_ids: Set[str] = field(default_factory=set)
    seen_output_ids: Set[str] = field(default_factory=set)

    overload_score: int = 0


@dataclass
class StreamAssemblyBuffer:
    """
    스트림 조립용 버퍼.
    source + stream_id 조합별로 독립 관리한다.
    """
    source: str
    stream_id: str
    total_chunks: Optional[int] = None
    chunks: Dict[int, Union[str, bytes]] = field(default_factory=dict)
    data_type: Optional[type] = None
    ended: bool = False
    start_time: float = field(default_factory=time.time)
    last_update_time: float = field(default_factory=time.time)


class Router:
    """
    노드 그래프를 관리하고, 각 노드를 비동기 실행하며,
    노드 간 메시지를 연결 규칙에 따라 전달하는 런타임 라우터.

    공개 API는 파일 하단에 정리되어 있다.
    내부 동작:
    - 각 노드 tick 실행
    - 인터페이스 출력 큐 폴링
    - 그래프 기반 메시지 전달
    - 외부 입력 스트림 분할
    - 출력 노드 스트림 최종 재조립
    - 폭주 상태 감시
    """

    def __init__(
        self,
        tick_interval: float = 0.01,
        route_interval: float = 0.005,
        overload_threshold: int = 200,
        overload_margin: int = 50,
    ):
        self.tick_interval = tick_interval
        self.route_interval = route_interval
        self.overload_threshold = overload_threshold
        self.overload_margin = overload_margin

        self.nodes: Dict[str, Node] = {}
        self.alias_to_id: Dict[str, str] = {}
        self.id_to_alias: Dict[str, str] = {}

        self.graph: Dict[str, Set[str]] = {}
        self.reverse_graph: Dict[str, Set[str]] = {}

        self.input_nodes: Set[str] = set()
        self.output_nodes: Set[str] = set()

        self.stats: Dict[str, NodeStats] = {}

        # 사용자에게는 최종 완성 데이터만 반환
        self.output_q: asyncio.Queue[Any] = asyncio.Queue()

        # 출력 노드의 스트림 조립 버퍼
        self._output_stream_buffers: Dict[Tuple[str, str], StreamAssemblyBuffer] = {}

        self._running = False
        self._node_tasks: Dict[str, asyncio.Task] = {}
        self._route_task: Optional[asyncio.Task] = None

    # =========================================================
    # Internal Runtime
    # =========================================================

    async def _run_node_loop(self, node_id: str, node: Node):
        try:
            while self._running:
                await node.tick()
                self.stats[node_id].run_count += 1
                await asyncio.sleep(self.tick_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._running = False
            raise

    async def _run_route_loop(self):
        try:
            while self._running:
                await self._poll_all_outgoing()
                self._check_overload()
                await asyncio.sleep(self.route_interval)
        except asyncio.CancelledError:
            raise

    async def _poll_all_outgoing(self):
        for src_id, node in self.nodes.items():
            await self._drain_node_output(src_id, node)

    async def _drain_node_output(self, src_id: str, node: Node):
        q = node.iface.to_router_q

        while not q.empty():
            msg = await q.get()

            stat = self.stats[src_id]
            stat.output_count += 1
            stat.last_active_at = time.time()

            if msg.id not in stat.seen_output_ids:
                stat.seen_output_ids.add(msg.id)
                stat.unique_output_count += 1

            # 1) 명시 target 우선
            if msg.target is not None:
                await self._route_to_target(src_id, msg)
            # 2) target이 없으면 그래프 연결 기반 전달
            else:
                await self._route_by_graph(src_id, msg)

            # 3) 출력 노드면 외부 출력 수집
            if src_id in self.output_nodes:
                await self._collect_output(src_id, msg)

    # =========================================================
    # Internal Routing
    # =========================================================

    async def _route_to_target(self, src_id: str, msg: Message):
        try:
            dst_id = self.resolve_node_id(msg.target)
        except KeyError:
            return

        if dst_id in self.nodes:
            await self.nodes[dst_id].iface.from_router_q.put(msg)
            self._mark_input(dst_id, msg)

    async def _route_by_graph(self, src_id: str, msg: Message):
        targets = self.graph.get(src_id, set())

        for dst_id in targets:
            await self.nodes[dst_id].iface.from_router_q.put(msg)
            self._mark_input(dst_id, msg)

    def _mark_input(self, node_id: str, msg: Message):
        stat = self.stats[node_id]
        stat.input_count += 1
        stat.last_active_at = time.time()

        if msg.id not in stat.seen_input_ids:
            stat.seen_input_ids.add(msg.id)
            stat.unique_input_count += 1

    def _check_overload(self):
        """
        단순 폭주 감시.
        출력이 입력보다 지속적으로 과도한 노드를 감시하여 전체 실행을 중단한다.
        """
        for node_id, stat in self.stats.items():
            delta = stat.output_count - stat.input_count

            if delta > self.overload_margin:
                stat.overload_score += 1
            else:
                stat.overload_score = max(0, stat.overload_score - 1)

            if stat.overload_score >= self.overload_threshold:
                self._running = False
                raise RuntimeError(f"Router overload detected at node: {node_id}")

    # =========================================================
    # Internal Output Stream Handling
    # =========================================================

    async def _collect_output(self, src_id: str, msg: Message):
        """
        출력 노드에서 나온 메시지를 외부 사용자용 출력 큐로 수집한다.
        긴 데이터 스트림은 여기서 최종 조립한다.
        """
        data = msg.data

        if isinstance(data, StreamChunk):
            assembled = self._handle_output_stream(src_id, data)
            if assembled is not None:
                await self.output_q.put(assembled)
            return

        await self.output_q.put(data)

    def _handle_output_stream(self, src_id: str, chunk: StreamChunk) -> Optional[Union[str, bytes]]:
        key = (src_id, chunk.stream_id)

        buf = self._output_stream_buffers.get(key)
        if buf is None:
            buf = StreamAssemblyBuffer(
                source=src_id,
                stream_id=chunk.stream_id,
                total_chunks=chunk.total,
            )
            self._output_stream_buffers[key] = buf

        buf.last_update_time = time.time()

        if buf.total_chunks is None and chunk.total is not None:
            buf.total_chunks = chunk.total

        if chunk.data is not None:
            if buf.data_type is None:
                buf.data_type = type(chunk.data)
            elif buf.data_type is not type(chunk.data):
                del self._output_stream_buffers[key]
                return None

            if chunk.index not in buf.chunks:
                buf.chunks[chunk.index] = chunk.data

        if chunk.is_end:
            buf.ended = True

        if self._is_stream_complete(buf):
            merged = self._assemble_stream(buf)
            del self._output_stream_buffers[key]
            return merged

        return None

    # =========================================================
    # Internal External-Input Fragmentation
    # =========================================================

    def _should_stream_for_node(self, node_id: str, data: Any) -> bool:
        max_payload_size = self.nodes[node_id].iface.max_payload_size

        if isinstance(data, str):
            return len(data) > max_payload_size
        if isinstance(data, bytes):
            return len(data) > max_payload_size
        return False

    async def _fragment_external_input(self, target_node_id: str, data: Union[str, bytes]):
        """
        외부 입력 데이터를 입력 노드 인터페이스가 이해할 수 있는
        Message + StreamChunk 형태로 분할한다.
        """
        max_payload_size = self.nodes[target_node_id].iface.max_payload_size
        stream_id = str(uuid.uuid4())
        total_len = len(data)
        total_chunks = max(1, math.ceil(total_len / max_payload_size))

        trace_id = str(uuid.uuid4())

        for index in range(total_chunks):
            start = index * max_payload_size
            end = start + max_payload_size
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
                source=EXTERNAL_SOURCE,
                kind="stream",
                data=chunk,
                target=target_node_id,
                trace_id=trace_id,
            )

    # =========================================================
    # Internal Stream Helpers
    # =========================================================

    def _is_stream_complete(self, buf: StreamAssemblyBuffer) -> bool:
        if buf.total_chunks is None:
            return False
        if not buf.ended:
            return False

        expected = set(range(buf.total_chunks))
        actual = set(buf.chunks.keys())
        return actual == expected

    def _assemble_stream(self, buf: StreamAssemblyBuffer) -> Union[str, bytes]:
        ordered = [buf.chunks[i] for i in range(buf.total_chunks or 0)]

        if buf.data_type is bytes:
            return b"".join(ordered)

        return "".join(ordered)

    # =========================================================
    # Public Node / Alias API
    # =========================================================

    def add_node(
        self,
        node_or_base: Union[Node, BaseProcessor],
        node_id: Optional[str] = None,
        alias: Optional[str] = None,
        is_input: bool = False,
        is_output: bool = False,
        context: Optional[dict] = None,
    ) -> Node:
        """
        노드를 라우터에 등록한다.

        지원 방식:
        1. Node 객체 직접 등록
        2. BaseProcessor만 넘기면 내부에서 Node를 자동 생성 후 등록

        BaseProcessor 방식에서는 interface도 자동 생성되므로,
        일반 사용자는 BaseProcessor만 구현해서 넣으면 된다.
        """
        if isinstance(node_or_base, Node):
            node = node_or_base

            if node_id is not None and node_id != node.node_id:
                raise ValueError(
                    f"node_id mismatch: given={node_id}, actual={node.node_id}"
                )

        elif isinstance(node_or_base, BaseProcessor):
            if not node_id:
                raise ValueError("node_id is required when adding a BaseProcessor")

            node = Node(
                node_id=node_id,
                base=node_or_base,
                interface=None,
                context=context,
            )

        else:
            raise TypeError("add_node() expects a Node or BaseProcessor instance")

        actual_node_id = node.node_id

        if actual_node_id in self.nodes:
            raise ValueError(f"Node already exists: {actual_node_id}")

        self.nodes[actual_node_id] = node
        self.graph[actual_node_id] = set()
        self.reverse_graph[actual_node_id] = set()
        self.stats[actual_node_id] = NodeStats()

        if alias:
            if alias in self.alias_to_id:
                raise ValueError(f"Alias already exists: {alias}")
            self.alias_to_id[alias] = actual_node_id
            self.id_to_alias[actual_node_id] = alias

        if is_input:
            self.input_nodes.add(actual_node_id)

        if is_output:
            self.output_nodes.add(actual_node_id)

        return node

    def resolve_node_id(self, node_or_alias: str) -> str:
        """
        노드 ID 또는 별칭을 실제 node_id로 해석한다.
        """
        if node_or_alias in self.nodes:
            return node_or_alias
        if node_or_alias in self.alias_to_id:
            return self.alias_to_id[node_or_alias]
        raise KeyError(f"Unknown node or alias: {node_or_alias}")

    def get_node(self, node_or_alias: str) -> Node:
        """
        노드 ID 또는 별칭으로 등록된 Node 객체를 반환한다.
        """
        node_id = self.resolve_node_id(node_or_alias)
        return self.nodes[node_id]

    def set_alias(self, node_or_alias: str, alias: str):
        """
        노드의 별칭을 설정하거나 변경한다.
        """
        node_id = self.resolve_node_id(node_or_alias)

        if alias in self.alias_to_id:
            raise ValueError(f"Alias already exists: {alias}")

        old_alias = self.id_to_alias.get(node_id)
        if old_alias:
            del self.alias_to_id[old_alias]

        self.alias_to_id[alias] = node_id
        self.id_to_alias[node_id] = alias

    # =========================================================
    # Public Graph API
    # =========================================================

    def add_connect(self, src: str, dst: str):
        """
        src -> dst 유방향 연결을 추가한다.
        """
        src_id = self.resolve_node_id(src)
        dst_id = self.resolve_node_id(dst)

        self.graph[src_id].add(dst_id)
        self.reverse_graph[dst_id].add(src_id)

    def remove_connect(self, src: str, dst: str):
        """
        src -> dst 유방향 연결을 제거한다.
        """
        src_id = self.resolve_node_id(src)
        dst_id = self.resolve_node_id(dst)

        self.graph[src_id].discard(dst_id)
        self.reverse_graph[dst_id].discard(src_id)

    def set_input_node(self, node_or_alias: str, enabled: bool = True):
        """
        입력 노드 여부를 설정한다.
        """
        node_id = self.resolve_node_id(node_or_alias)
        if enabled:
            self.input_nodes.add(node_id)
        else:
            self.input_nodes.discard(node_id)

    def set_output_node(self, node_or_alias: str, enabled: bool = True):
        """
        출력 노드 여부를 설정한다.
        """
        node_id = self.resolve_node_id(node_or_alias)
        if enabled:
            self.output_nodes.add(node_id)
        else:
            self.output_nodes.discard(node_id)

    # =========================================================
    # Public External I/O API
    # =========================================================

    async def inject(self, target: str, data: Any):
        """
        외부에서 입력 노드로 순수 데이터를 주입한다.

        동작:
        - 짧은 데이터는 일반 Message로 감싸서 전달
        - 긴 str/bytes는 StreamChunk 여러 개로 분할하여 전달
        - 입력 노드 인터페이스가 이를 조립한 뒤 BaseProcessor에 넘긴다
        """
        node_id = self.resolve_node_id(target)

        if node_id not in self.input_nodes:
            raise ValueError(f"Node is not registered as input node: {node_id}")

        if self._should_stream_for_node(node_id, data):
            async for msg in self._fragment_external_input(target_node_id=node_id, data=data):
                await self.nodes[node_id].iface.from_router_q.put(msg)
                self._mark_input(node_id, msg)
        else:
            msg = create_message(
                source=EXTERNAL_SOURCE,
                kind="data",
                data=data,
                target=node_id,
            )
            await self.nodes[node_id].iface.from_router_q.put(msg)
            self._mark_input(node_id, msg)

    async def recv_output(self) -> Optional[Any]:
        """
        출력 노드에서 최종적으로 수집된 완성 데이터를 하나 꺼낸다.

        반환값은 항상 사용자 관점의 최종 데이터이며,
        StreamChunk는 반환하지 않는다.
        """
        if self.output_q.empty():
            return None
        return await self.output_q.get()

    # =========================================================
    # Public Runtime API
    # =========================================================

    async def start(self):
        """
        라우터와 모든 노드 실행 루프를 시작한다.
        """
        if self._running:
            return

        self._running = True

        for node_id, node in self.nodes.items():
            self._node_tasks[node_id] = asyncio.create_task(self._run_node_loop(node_id, node))

        self._route_task = asyncio.create_task(self._run_route_loop())

    async def stop(self):
        """
        라우터와 모든 노드 실행 루프를 중지한다.
        """
        if not self._running:
            return

        self._running = False

        for task in self._node_tasks.values():
            task.cancel()

        if self._route_task:
            self._route_task.cancel()

        await asyncio.gather(*self._node_tasks.values(), return_exceptions=True)

        if self._route_task:
            await asyncio.gather(self._route_task, return_exceptions=True)

        for node in self.nodes.values():
            await node.stop()

        self._node_tasks.clear()
        self._route_task = None
        self._output_stream_buffers.clear()

    # =========================================================
    # Public Introspection API
    # =========================================================

    def get_stats(self, node_or_alias: str) -> NodeStats:
        """
        특정 노드의 통계를 반환한다.
        """
        node_id = self.resolve_node_id(node_or_alias)
        return self.stats[node_id]

    def get_alias(self, node_or_alias: str) -> str:
        """
        노드의 별칭을 반환한다. 별칭이 없으면 node_id를 반환한다.
        """
        node_id = self.resolve_node_id(node_or_alias)
        return self.id_to_alias.get(node_id, node_id)

    def list_nodes(self) -> List[Tuple[str, str]]:
        """
        등록된 모든 노드의 (node_id, alias 또는 node_id) 목록을 반환한다.
        """
        result = []
        for node_id in self.nodes:
            result.append((node_id, self.id_to_alias.get(node_id, node_id)))
        return result

    def list_connections(self) -> List[Tuple[str, str]]:
        """
        등록된 모든 연결 (src_id, dst_id) 목록을 반환한다.
        """
        result = []
        for src_id, dsts in self.graph.items():
            for dst_id in dsts:
                result.append((src_id, dst_id))
        return result