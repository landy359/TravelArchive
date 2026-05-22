"""
port3.py
P3 포트 — 양방향 (Port3 ↔ Core)

흐름: PC3 → QUST → sDB.run → dDB.run → (PPL 미구현) → LLM → PC3
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List

from .protocol import PC3, QUST, _mk_from_list, _pn_from_list

if TYPE_CHECKING:
    from .core import Core


class Port3:

    def __init__(self, core: "Core") -> None:
        self.core = core
        from ..kernel.db_connector import DBConnector
        from ..kernel.sdb import SDB
        from ..kernel.ddb import DDB
        _connector = DBConnector()
        self.sdb = SDB(_connector)
        self.ddb = DDB(_connector)

    # ────────────────────────────────────────────────
    # Core ↔ Port3 인터페이스
    # ────────────────────────────────────────────────

    async def execute(self, pc3: PC3) -> None:
        pc3_result: PC3 = await self._process(pc3)
        await self.core.receive_from_p3(pc3_result)

    async def _process(self, pc3: PC3) -> PC3:
        qust = QUST(
            USR_ANAL=pc3.USR_ANAL,
            SSN_TPC=pc3.SSN_TPC,
            SSN_PCL=pc3.SSN_PCL,
            CC=pc3.CC,
            T_SL=pc3.T_SL,
            T_CD=pc3.T_CD or [],
            T_MP=pc3.T_MP or [],
            T_MK=pc3.T_MK or [],
            T_PN=pc3.T_PN or [],
        )
        qust = await self.sdb.run(qust)
        qust = await self.ddb.run(qust)
        # PPL — 미구현
        return await self._call_llm(qust)

    # ────────────────────────────────────────────────
    # LLM 어댑터 (임시 구현)
    # ────────────────────────────────────────────────

    async def _call_llm(self, qust: QUST) -> PC3:
        from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY, ROUTER_PROMPT
        from ..kernel.llm import LLM

        past = json.loads(qust.SSN_PCL) if qust.SSN_PCL else []
        history = "\n".join(
            f"{'사용자' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')}"
            for m in past
        ) or "없음"

        prompt = ROUTER_PROMPT.format(
            usr_anal=qust.USR_ANAL or "없음",
            ssn_tpc=qust.SSN_TPC or "없음",
            ssn_pcl=history,
            cc=qust.CC,
        )

        raw = await LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY).ask(prompt)

        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]
            stripped = stripped.rsplit("```", 1)[0].strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = {"CC": raw}

        # None = LLM이 해당 필드를 JSON에서 생략함 → core의 _diff_or_keep이 이전 값 유지.
        # [] = LLM이 명시적으로 빈 배열을 반환함 → 위젯 초기화.
        return PC3(
            USR_ANAL=qust.USR_ANAL,
            SSN_TPC=qust.SSN_TPC,
            SSN_PCL=qust.SSN_PCL,
            CC=data.get("CC", raw),
            T_SL=data.get("T_SL", qust.T_SL),
            T_CD=data["T_CD"] if "T_CD" in data else None,
            T_MP=data["T_MP"] if "T_MP" in data else None,
            T_MK=_mk_from_list(data["T_MK"]) if "T_MK" in data else None,
            T_PN=_pn_from_list(data["T_PN"]) if "T_PN" in data else None,
        )

    async def _call_ppl(self, query: str) -> str:
        raise NotImplementedError
