"""
port3.py
P3 포트 — 양방향 (Port3 ↔ Core)

흐름: PC3 → QUST → [sDB → dDB → PPL] → LLM → PC3
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List

from .protocol import PC3, QUST, _mk_from_list, _pn_from_list
from ..kernel.keyword_scorer import top_n_keywords, compute_sl_ctx, KW_BAG_HINT_N

if TYPE_CHECKING:
    from .core import Core


class Port3:

    def __init__(self, core: "Core", user_id: str = "", kw_bag: dict | None = None) -> None:
        self.core      = core
        self._user_id  = user_id
        self._kw_bag   = kw_bag or {}
        from ..kernel.db_connector import DBConnector
        from ..kernel.sdb import SDB
        from ..kernel.ddb import DDB
        from ..kernel.ppl import PPL
        _connector = DBConnector()
        self.sdb = SDB(_connector)
        self.ddb = DDB(_connector)
        self.ppl = PPL()
        self._pipeline = [self.sdb, self.ddb, self.ppl]

    # ────────────────────────────────────────────────
    # Core ↔ Port3 인터페이스
    # ────────────────────────────────────────────────

    async def execute(self, pc3: PC3) -> None:
        pc3_result: PC3 = await self._process(pc3)
        await self.core.receive_from_p3(pc3_result)

    async def _process(self, pc3: PC3) -> PC3:
        kw_hint = top_n_keywords(self._kw_bag, KW_BAG_HINT_N)

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
            kw_hint=kw_hint,
        )
        for node in self._pipeline:
            qust = await node.run(qust)

        sl_ctx = compute_sl_ctx(qust.route_keywords, self._kw_bag) if qust.route_keywords else None
        return await self._call_llm(qust, sl_ctx=sl_ctx)

    # ────────────────────────────────────────────────
    # LLM 어댑터 (임시 구현)
    # ────────────────────────────────────────────────

    async def _call_llm(self, qust: QUST, sl_ctx: dict | None = None) -> PC3:
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

        extra: list[str] = []
        if qust.T_CD:
            dates = " ~ ".join(
                f"20{d[:2]}년 {int(d[2:4])}월 {int(d[4:6])}일"
                for d in qust.T_CD
            )
            extra.append(f"[여행 날짜]: {dates}")
        if qust.sDB:
            lines = [
                f"{p.name} ({p.main_category}) / {p.region}"
                for p in qust.sDB
            ]
            extra.append("[방문 가능한 장소 DB]:\n" + "\n".join(lines))
        if qust.dDB:
            lines = [
                f"{w.location} {w.forecast_time}시: {w.summary}"
                + (f", 강수확률 {w.rain_prob}%" if w.rain_prob else "")
                + f", 기온 {w.temperature}°C"
                for w in qust.dDB
            ]
            extra.append("[날씨 예보]:\n" + "\n".join(lines))
        if qust.PPL:
            extra.append(f"[Perplexity 경로 참고]:\n{qust.PPL}")
        if sl_ctx:
            extra.append(
                f"[선택지 제안]: 두 여행 경로의 키워드 점수가 비슷합니다.\n"
                f"A안: {sl_ctx['A']['name']} / B안: {sl_ctx['B']['name']}\n"
                f'T_SL 필드를 "A안: {sl_ctx["A"]["name"]} | B안: {sl_ctx["B"]["name"]}" 로 채워주세요.'
            )
        elif qust.T_SL:
            extra.append(f"[현재 선택 대기 중]: {qust.T_SL}")
        if extra:
            prompt += "\n\n" + "\n\n".join(extra)

        print("\n===== [PORT3 LLM PROMPT] =====\n" + prompt + "\n==============================\n", flush=True)
        raw = await LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY).ask(prompt)
        print("\n===== [PORT3 LLM RAW] =====\n" + raw + "\n===========================\n", flush=True)

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
            SL_CTX=sl_ctx or {},
        )

    async def _call_ppl(self, query: str) -> str:
        raise NotImplementedError
