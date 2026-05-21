"""
core.py
라우터 코어

역할:
  - P2 수신 → P1 pull → merge → PC3 조립 → P3 전달
  - P3 출력 수신 → split → diff 비교 → PC2 → P2 전달
  - P1/P2/P3와 포트 인터페이스로만 통신 (내부 동작 모름)
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from .protocol import PC1, PC2, PC3

if TYPE_CHECKING:
    from .port1 import Port1
    from .port2 import Port2
    from .port3 import Port3


class Core:

    @classmethod
    async def run(cls,
                  current: str,
                  history: list,
                  session_topic: str,
                  usr_anal: str,
                  widget_state: dict) -> tuple[str, dict]:
        """대화 데이터를 받아 (bot_text, updated_widget_state) 반환."""
        import json
        from .port1 import Port1
        from .port2 import Port2
        from .port3 import Port3
        p1   = Port1(usr_anal, session_topic, json.dumps(history, ensure_ascii=False))
        p2   = Port2(None, current, widget_state)
        p3   = Port3(None)
        core = cls(p1, p2, p3)
        p2.core = core
        p3.core = core
        await p2.on_user_message()
        return p2.last_response, p2.updated_widget_state

    def __init__(self, p1: "Port1", p2: "Port2", p3: "Port3"):
        self.p1 = p1
        self.p2 = p2
        self.p3 = p3
        self._prev_pc2: PC2 = PC2()   # diff 비교용 이전 PC2

    # ────────────────────────────────────────────────
    # P2 → Core 인터페이스
    # ────────────────────────────────────────────────

    async def receive_from_p2(self, pc2: PC2) -> None:
        """CC 수신이 트리거 → merge → P3 전달"""
        await self._merge_and_execute(pc2)

    # ────────────────────────────────────────────────
    # P3 → Core 인터페이스
    # ────────────────────────────────────────────────

    async def receive_from_p3(self, pc3_result: PC3) -> None:
        """P3 출력(LLM 결과) 수신 → split → P2 전달"""
        await self._split_and_send(pc3_result)

    # ────────────────────────────────────────────────
    # MERGE
    # ────────────────────────────────────────────────

    async def _merge_and_execute(self, pc2: PC2) -> None:
        self._prev_pc2 = pc2   # diff 기준: 현재 위젯 상태로 초기화
        pc1: PC1 = self.p1.request_pc1()
        pc3: PC3 = self._merge(pc1, pc2)

        if not self._validate_pc3(pc3):
            await self.p2.on_error("Core: CC 누락 — PC3 구성 실패")
            return

        await self.p3.execute(pc3)

    def _merge(self, pc1: PC1, pc2: PC2) -> PC3:
        """PC1 + PC2 → PC3"""
        return PC3(
            USR_ANAL=pc1.USR_ANAL,
            SSN_TPC=pc1.SSN_TPC,
            SSN_PCL=pc1.SSN_PCL,
            CC=pc2.CC,
            T_SL=pc2.T_SL,
            T_CD=pc2.T_CD,
            T_MP=pc2.T_MP,
            T_MK=pc2.T_MK,
            T_PN=pc2.T_PN,
        )

    def _validate_pc3(self, pc3: PC3) -> bool:
        """CC는 반드시 있어야 함"""
        return bool(pc3.CC)

    # ────────────────────────────────────────────────
    # SPLIT
    # ────────────────────────────────────────────────

    async def _split_and_send(self, pc3_result: PC3) -> None:
        """PC1 필드 제거, diff 비교 후 변경분만 PC2로 → P2 전달"""
        pc2_new = PC2(
            CC=pc3_result.CC,
            T_SL=pc3_result.T_SL,
            T_CD=self._diff_or_keep(pc3_result.T_CD, self._prev_pc2.T_CD),
            T_MP=self._diff_or_keep(pc3_result.T_MP, self._prev_pc2.T_MP),
            T_MK=self._diff_or_keep(pc3_result.T_MK, self._prev_pc2.T_MK),
            T_PN=self._diff_or_keep(pc3_result.T_PN, self._prev_pc2.T_PN),
        )
        self._prev_pc2 = pc2_new
        await self.p2.receive_from_core(pc2_new)

    def _diff_or_keep(self, new_val, old_val: list) -> list:
        """None = LLM이 필드를 생략 (이전 값 유지). [] = 명시적 초기화."""
        if new_val is None:
            return old_val
        return new_val
