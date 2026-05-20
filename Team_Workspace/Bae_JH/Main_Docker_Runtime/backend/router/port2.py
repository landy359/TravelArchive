"""
port2.py
P2 포트 — 양방향 (Port2 ↔ Core)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .protocol import PC2

if TYPE_CHECKING:
    from .core import Core


class Port2:

    def __init__(self, core: "Core", current: str, widget_state: dict) -> None:
        self.core          = core
        self._current      = current
        self._widget_state = widget_state
        self.last_response: str  = ""
        self.updated_widget_state: dict = {}

    async def on_user_message(self) -> None:
        await self.core.receive_from_p2(self._build_pc2())

    def _build_pc2(self) -> PC2:
        w = self._widget_state
        return PC2(
            CC=self._current,
            T_SL=w.get("t_sl", ""),
            T_CD=w.get("t_cd", []),
            T_MP=w.get("t_mp", []),
            T_MK=w.get("t_mk", []),
            T_PN=w.get("t_pn", []),
        )

    async def receive_from_core(self, pc2: PC2) -> None:
        self.last_response = pc2.CC
        self.updated_widget_state = {
            "t_sl": pc2.T_SL,
            "t_cd": pc2.T_CD,
            "t_mp": pc2.T_MP,
            "t_mk": pc2.T_MK,
            "t_pn": pc2.T_PN,
        }

    async def on_error(self, msg: str) -> None:
        self.last_response = f"[라우터 오류] {msg}"
        self.updated_widget_state = self._widget_state
