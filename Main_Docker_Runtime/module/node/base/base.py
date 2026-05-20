from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseProcessor(ABC):
    """
    사용자 정의 노드 로직의 최소 베이스 클래스.

    역할:
    - 순수 입력 데이터를 받아 처리한다.
    - 필요하면 순수 출력 데이터를 반환한다.

    이 클래스는 처리 로직만 담당하며, 다음은 직접 다루지 않는다.
    - 메시지 생성/해제
    - 스트림 분할/재조립
    - 라우팅 및 전송
    - 인터페이스 내부 큐 제어

    구현 규칙:
    - 반드시 `process(data)`를 구현해야 한다.
    - 입력은 Interface가 해제한 순수 데이터다.
    - 반환값은 출력 데이터 또는 `None`이다.
    - 메시지/스트림/라우터 구조에 직접 의존하지 않는 것을 원칙으로 한다.

    선택 기능:
    - `signal(name, data=None)` : Node에 상태 신호 전달 (선택 사용)
    - `on_start()` : 시작 시 1회 호출
    - `on_stop()`  : 종료 시 1회 호출
    - `on_idle()`  : 입력이 없을 때 호출
    """

    def __init__(self):
        """
        처리기 내부 상태를 초기화한다.

        Attributes:
            node:
                이 처리기가 연결된 상위 Node.
                프레임워크가 `bind_node()`로 설정하며, 초기값은 None이다.

            _signal:
                Base 내부에서 기록된 상태 신호.
                Node가 tick 처리 후 consume한다.

            _signal_data:
                signal과 함께 전달되는 추가 데이터.
        """
        self.node = None

        # Optional signal state
        self._signal: Optional[str] = None
        self._signal_data: Any = None

    def bind_node(self, node):
        """
        현재 처리기를 상위 Node에 연결한다.

        일반적으로 프레임워크 내부에서만 호출된다.
        구현체는 필요하면 `self.node`를 통해 노드 문맥에 접근할 수 있다.
        """
        self.node = node

    # =========================================================
    # Signal API (Optional)
    # =========================================================

    def signal(self, name: str, data: Any = None):
        """
        Base 내부에서 상태 신호를 기록한다.

        Node는 process 실행 이후 이 신호를 확인하여
        메시지 전송 방식을 결정한다.

        예:
            self.signal("error")          → 오류 처리
            self.signal("skip")           → 빈 메시지
            self.signal("branch", "A")    → control 메시지

        Args:
            name:
                signal 이름

            data:
                signal과 함께 전달할 추가 데이터
        """
        self._signal = name
        self._signal_data = data

    def consume_signal(self):
        """
        Node가 signal을 읽고 초기화한다.

        Returns:
            (signal_name, signal_data)
        """
        name = self._signal
        data = self._signal_data

        self._signal = None
        self._signal_data = None

        return name, data

    # =========================================================
    # Optional Hooks
    # =========================================================

    async def on_start(self) -> None:
        """
        선택적 시작 훅.

        용도:
        - 캐시 초기화
        - 상태 준비
        - 모델 로딩
        """
        pass

    async def on_stop(self) -> None:
        """
        선택적 종료 훅.

        용도:
        - 자원 정리
        - 버퍼 정리
        - 종료 시 저장 작업
        """
        pass

    async def on_idle(self) -> None:
        """
        선택적 유휴 훅.

        입력이 없을 때 호출된다.
        무거운 작업보다는 가벼운 점검용으로 사용하는 것을 권장한다.
        """
        pass

    # =========================================================
    # Main Processing
    # =========================================================

    @abstractmethod
    async def process(self, data: Any) -> Optional[Any]:
        """
        입력 데이터를 처리하고 결과를 반환한다.

        Args:
            data:
                Interface가 전달한 순수 입력 데이터.
                str, bytes, dict, list, 객체 등 어떤 타입도 가능하다.

        Returns:
            처리 결과 데이터 또는 None.
            - Any  : 출력 전송
            - None : 출력 없음

        최소 규칙:
        - 반드시 `async def`로 구현할 것
        - 입력을 받아 처리할 것
        - 결과를 반환하거나 `None`을 반환할 것

        선택 규칙:
        - 상태 전달이 필요하면 `signal()` 사용 가능

        비권장:
        - 메시지 헤더 직접 해석
        - 라우터/큐 직접 조작
        - 스트림 직접 처리
        """
        raise NotImplementedError