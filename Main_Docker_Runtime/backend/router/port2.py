"""
port2.py
P2 포트 — 양방향 (Port2 ↔ Core)
"""

from __future__ import annotations
import json
import re
from typing import TYPE_CHECKING

from .protocol import PC2, _mk_to_list, _mk_from_list, _pn_to_list, _pn_from_list, T_MK_Item, T_PN_Item
from ..execute_unit.widget.widget_trip_select import TripSelectWidget
from ..execute_unit.widget.widget_trip_clander import TripClanderWidget
from ..execute_unit.widget.widget_trip_map import TripMapWidget
from ..execute_unit.widget.widget_trip_marker import TripMarkerWidget
from ..execute_unit.widget.widget_trip_plan import TripPlanWidget

if TYPE_CHECKING:
    from .core import Core

_CD_RE = re.compile(r'^\d{6}$')


def _guard_t_sl(new_val: str, buf: str) -> str:
    """빈 문자열이면 버퍼 값 유지."""
    return new_val if new_val.strip() else buf


def _guard_t_cd(new_val: list, buf: list) -> list:
    """YYMMDD 형식 아닌 항목 제거. 유효 항목이 없고 버퍼가 있으면 버퍼 유지."""
    valid = [v for v in new_val if isinstance(v, str) and _CD_RE.match(v)]
    return valid if (valid or not buf) else buf


def _guard_t_mp(new_val: list, buf: list) -> list:
    """빈 문자열 항목 제거. 유효 항목 없고 버퍼 있으면 버퍼 유지."""
    valid = [v for v in new_val if isinstance(v, str) and v.strip()]
    return valid if (valid or not buf) else buf


def _guard_t_mk(new_val: list, buf: list) -> list:
    """marker_id·name 모두 비어 있는 가비지 항목 제거. 결과 없고 버퍼 있으면 버퍼 유지."""
    valid = [
        item for item in new_val
        if isinstance(item, T_MK_Item)
        and (item.marker_id.strip() or item.place_info.name.strip())
    ]
    return valid if (valid or not buf) else buf


def _guard_t_pn(new_val: list, buf: list) -> list:
    """place 빈 항목 제거 후 빈 행 제거. 유효 행 없고 버퍼 있으면 버퍼 유지."""
    valid_rows = []
    for row in new_val:
        if not isinstance(row, list):
            continue
        valid_items = [
            item for item in row
            if isinstance(item, T_PN_Item) and item.place.strip()
        ]
        if valid_items:
            valid_rows.append(valid_items)
    return valid_rows if (valid_rows or not buf) else buf


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
        self._t_sel_dict: dict = widget_state.get("t_sel", {})
        self._buf_pc2: PC2 | None = None
        self.last_response: str = ""
        self.updated_widget_state: dict = {}

    async def on_user_message(self) -> None:
        self._buf_pc2 = self._build_pc2()
        await self.core.receive_from_p2(self._buf_pc2)

    def _build_pc2(self) -> PC2:
        return PC2(
            CC=self._current,
            T_SL=self._t_sl.get_for_llm(),
            T_CD=self._t_cd.get_for_llm(),
            T_MP=self._t_mp.get_for_llm(),
            T_MK=self._t_mk.get_for_llm(),
            T_PN=self._t_pn.get_for_llm(),
            T_SEL=self._t_sel_dict,
        )

    def _parse_raw_json_cc(self, pc2: PC2) -> PC2:
        """CC가 JSON blob 그대로 내려온 경우(P3 파싱 실패 폴백) 재파싱해 실제 CC + 위젯을 복원."""
        cc = pc2.CC
        if not cc:
            return pc2
        stripped = cc.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if not stripped.startswith("{"):
            return pc2
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return pc2
        if "CC" not in data:
            return pc2
        return PC2(
            CC=data["CC"],
            T_SL=data.get("T_SL", pc2.T_SL),
            T_CD=data["T_CD"] if "T_CD" in data else pc2.T_CD,
            T_MP=data["T_MP"] if "T_MP" in data else pc2.T_MP,
            T_MK=_mk_from_list(data["T_MK"]) if "T_MK" in data else pc2.T_MK,
            T_PN=_pn_from_list(data["T_PN"]) if "T_PN" in data else pc2.T_PN,
        )

    async def receive_from_core(self, pc2: PC2, sl_ctx: dict | None = None) -> None:
        pc2 = self._parse_raw_json_cc(pc2)

        buf = self._buf_pc2
        b_sl = buf.T_SL if buf else ""
        b_cd = buf.T_CD if buf else []
        b_mp = buf.T_MP if buf else []
        b_mk = buf.T_MK if buf else []
        b_pn = buf.T_PN if buf else []

        self.last_response = pc2.CC
        self._t_sl.set_for_llm(_guard_t_sl(pc2.T_SL, b_sl))
        self._t_cd.set_for_llm(_guard_t_cd(pc2.T_CD, b_cd))
        self._t_mp.set_for_llm(_guard_t_mp(pc2.T_MP, b_mp))
        self._t_mk.set_for_llm(_guard_t_mk(pc2.T_MK, b_mk))
        self._t_pn.set_for_llm(_guard_t_pn(pc2.T_PN, b_pn))
        self.updated_widget_state = {
            "t_sl":  self._t_sl.get_for_llm(),
            "t_cd":  self._t_cd.get_for_llm(),
            "t_mp":  self._t_mp.get_for_llm(),
            "t_mk":  _mk_to_list(self._t_mk.get_for_llm()),
            "t_pn":  _pn_to_list(self._t_pn.get_for_llm()),
            "t_sel": {},  # LLM이 처리했으므로 커서 초기화
            "_sl_ctx": sl_ctx or {},
        }

    async def on_error(self, msg: str) -> None:
        self.last_response = f"[라우터 오류] {msg}"
        self.updated_widget_state = {
            "t_sl":  self._t_sl.get_for_llm(),
            "t_cd":  self._t_cd.get_for_llm(),
            "t_mp":  self._t_mp.get_for_llm(),
            "t_mk":  _mk_to_list(self._t_mk.get_for_llm()),
            "t_pn":  _pn_to_list(self._t_pn.get_for_llm()),
            "t_sel": self._t_sel_dict,  # 오류 시 커서 보존
        }
