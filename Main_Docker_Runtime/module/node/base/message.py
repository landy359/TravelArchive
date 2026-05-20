import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class StreamChunk:
    stream_id: str
    index: int
    data: Any
    total: Optional[int] = None   # 총 chunk 수
    is_start: bool = False
    is_end: bool = False


@dataclass(frozen=True)
class Message:
    id: str
    trace_id: str
    source: str
    kind: str
    data: Any = None
    target: Optional[str] = None
    in_reply_to: Optional[str] = None
    created_at: float = 0.0


def create_message(
    source: str,
    kind: str,
    data: Any = None,
    target: Optional[str] = None,
    trace_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> Message:
    return Message(
        id=str(uuid.uuid4()),
        trace_id=trace_id or str(uuid.uuid4()),
        source=source,
        kind=kind,
        data=data,
        target=target,
        in_reply_to=in_reply_to,
        created_at=time.time(),
    )