"""
port2.py
P2 포트 — 양방향 (Port2 ↔ Core)
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .protocol import PC2, _mk_to_list, _pn_to_list
from ..execute_unit.widget.widget_trip_select import TripSelectWidget
from ..execute_unit.widget.widget_trip_clander import TripClanderWidget
from ..execute_unit.widget.widget_trip_map import TripMapWidget
from ..execute_unit.widget.widget_trip_marker import TripMarkerWidget
from ..execute_unit.widget.widget_trip_plan import TripPlanWidget

if TYPE_CHECKING:
    from .core import Core


class Port2:

    def __init__(self, core: "Core", current: str, widget_state: dict) -> None:
        self.core     = core
        self._current = current
        self._t_sl    = TripSelectWidget()
        self._t_cd    = TripClanderWidget()
        self._t_mp    = TripMapWidget()
        self._t_mk    = TripMarkerWidget()
        self._t_pn    = TripPlanWidget()
        self._t_sl.set_for_llm(widget_state.get("t_sl", ""))
        self._t_cd.set_for_llm(widget_state.get("t_cd", []))
        self._t_mp.set_for_llm(widget_state.get("t_mp", []))
        self._t_mk.set_for_llm(widget_state.get("t_mk", []))
        self._t_pn.set_for_llm(widget_state.get("t_pn", []))
        self.last_response: str = ""
        self.updated_widget_state: dict = {}

    async def on_user_message(self) -> None:
        await self.core.receive_from_p2(self._build_pc2())

    def _build_pc2(self) -> PC2:
        return PC2(
            CC=self._current,
            T_SL=self._t_sl.get_for_llm(),
            T_CD=self._t_cd.get_for_llm(),
            T_MP=self._t_mp.get_for_llm(),
            T_MK=self._t_mk.get_for_llm(),
            T_PN=self._t_pn.get_for_llm(),
        )

    async def receive_from_core(self, pc2: PC2) -> None:
        self.last_response = pc2.CC
        self._t_sl.set_for_llm(pc2.T_SL)
        self._t_cd.set_for_llm(pc2.T_CD)
        self._t_mp.set_for_llm(pc2.T_MP)
        self._t_mk.set_for_llm(pc2.T_MK)
        self._t_pn.set_for_llm(pc2.T_PN)
        self.updated_widget_state = {
            "t_sl": self._t_sl.get_for_llm(),
            "t_cd": self._t_cd.get_for_llm(),
            "t_mp": self._t_mp.get_for_llm(),
            "t_mk": _mk_to_list(self._t_mk.get_for_llm()),
            "t_pn": _pn_to_list(self._t_pn.get_for_llm()),
        }

    async def on_error(self, msg: str) -> None:
        self.last_response = f"[라우터 오류] {msg}"
        self.updated_widget_state = {
            "t_sl": self._t_sl.get_for_llm(),
            "t_cd": self._t_cd.get_for_llm(),
            "t_mp": self._t_mp.get_for_llm(),
            "t_mk": _mk_to_list(self._t_mk.get_for_llm()),
            "t_pn": _pn_to_list(self._t_pn.get_for_llm()),
        }
