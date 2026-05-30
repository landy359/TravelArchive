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

    def __init__(self, core: "Core", user_id: str = "", kw_bag: dict | None = None, use_pipeline: bool = False) -> None:
        self.core      = core
        self._user_id  = user_id
        self._kw_bag   = kw_bag or {}
        from ..kernel.mock_db_connector import MockDBConnector
        from ..kernel.db_connector import DBConnector
        from ..kernel.sdb import SDB
        from ..kernel.ddb import DDB
        from ..kernel.ppl import PPL
        from ..kernel.llm import LLM
        _mock_connector = MockDBConnector()   # SDB: CSV 기반 장소 DB
        _db_connector   = DBConnector()       # DDB: 기상청 캐시용 실제 DB
        _llm = LLM()
        self.sdb = SDB(_mock_connector, _llm)
        self.ddb = DDB(_db_connector)
        self.ppl = PPL()
        # @PLAN일 때만 SDB/DDB/PPL 실행
        self._pipeline = [self.sdb, self.ddb, self.ppl] if use_pipeline else []

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
            T_SEL=pc3.T_SEL or {},
            kw_hint=kw_hint,
        )
        for node in self._pipeline:
            qust = await node.run(qust)

        sl_ctx = compute_sl_ctx(qust.route_keywords, self._kw_bag) if qust.route_keywords else None
        return await self._call_llm(qust, sl_ctx=sl_ctx)

    # ────────────────────────────────────────────────
    # LLM 어댑터
    # ────────────────────────────────────────────────

    _PLACEHOLDER_PLACES = {"장소명", "장소명1", "장소명2", "(채울 것)", ""}

    @staticmethod
    def _fix_t_pn_days(t_pn_raw: list, dates: list) -> list:
        if not t_pn_raw or not dates:
            return t_pn_raw
        n = len(dates)
        # 플레이스홀더 아이템 제거 (비-dict 아이템도 방어적으로 걸러냄)
        t_pn_raw = [
            [item for item in day
             if isinstance(item, dict) and item.get("place", "") not in Port3._PLACEHOLDER_PLACES]
            for day in t_pn_raw
            if isinstance(day, list)
        ]
        all_items = [item for day in t_pn_raw for item in day]
        if not all_items:
            return [[] for _ in dates]
        # 날짜 수 맞고 빈 날 없으면 date만 교정
        if len(t_pn_raw) == n and all(len(day) > 0 for day in t_pn_raw):
            for i, day_items in enumerate(t_pn_raw):
                for item in day_items:
                    item["date"] = dates[i]
            return t_pn_raw
        # 빈 날이 있거나 날짜 수 틀리면 전체 재분배
        per_day = max(1, len(all_items) // n)
        result = []
        idx = 0
        for i, d in enumerate(dates):
            slice_ = all_items[idx:] if i == n - 1 else all_items[idx:idx + per_day]
            idx += per_day
            for order, item in enumerate(slice_):
                item["date"] = d
                item["order"] = order
            result.append(slice_)
        return result

    def _enrich_place_info(self, t_pn_raw: list | None) -> list | None:
        """LLM이 생성한 place_info를 SDB 실제 데이터로 교정."""
        if not t_pn_raw:
            return t_pn_raw
        conn = getattr(self.sdb, "_conn", None)
        if not conn or not hasattr(conn, "lookup_by_name"):
            return t_pn_raw
        for day in t_pn_raw:
            if not isinstance(day, list):
                continue
            for item in day:
                if not isinstance(item, dict):
                    continue
                place = item.get("place", "")
                if not place:
                    continue
                row = conn.lookup_by_name(place)
                if row:
                    item["place_info"] = {
                        "name":         row["name"],
                        "address_road": row.get("address_road", ""),
                        "lat":          row["lat"],
                        "lng":          row["lon"],
                        "description":  row.get("sub_category", ""),
                        "category":     row.get("main_category", ""),
                    }
        return t_pn_raw

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
            n = len(qust.T_CD)
            day_lines = [
                f"{i+1}일차: 20{d[:2]}년 {int(d[2:4])}월 {int(d[4:6])}일 (date코드: {d})"
                for i, d in enumerate(qust.T_CD)
            ]
            cd_codes = list(qust.T_CD)
            skeleton = [[{"date": d, "order": i} for i in range(3)] for d in cd_codes]
            extra.append(
                f"[여행 날짜 ({n}일) — 절대 규칙]\n"
                + "\n".join(day_lines)
                + f"\n\n★ T_CD는 반드시 {json.dumps(cd_codes, ensure_ascii=False)} 그대로 출력. 다른 날짜 코드 사용 금지.\n"
                + f"★ T_PN과 T_PN_B 모든 date 필드는 위 date코드만 사용. 다른 날짜 코드 사용 시 오답.\n"
                + f"★ T_PN, T_PN_B 외부 배열 수 = {n}개 (날짜 수와 반드시 일치). 반드시 [[day1 items], [day2 items], ...] 형식.\n"
                + f"★ 모든 날짜({n}일치)에 장소를 채울 것.\n"
                + f"▶ CC는 T_PN 장소만 2~3문장으로 짧게 요약. 장황한 일정 나열 금지.\n"
                + f"\nT_PN / T_PN_B skeleton (동일한 중첩 구조. date 코드 그대로 유지, place·place_info만 실제 장소로 채울 것):\n"
                + json.dumps(skeleton, ensure_ascii=False)
            )
        if qust.T_PN:
            pn_lines = []
            for i, day_items in enumerate(qust.T_PN):
                if not day_items:
                    continue
                date_code = day_items[0].get("date", "") if isinstance(day_items[0], dict) else ""
                places = ", ".join(
                    item.get("place", "") for item in day_items if isinstance(item, dict) and item.get("place")
                )
                if places:
                    pn_lines.append(f"{i+1}일차 ({date_code}): {places}")
            if pn_lines:
                extra.append("[현재 저장된 여행 일정 — CC 작성 시 반드시 이 일정 기준으로 설명할 것]:\n" + "\n".join(pn_lines))
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
                f"① T_PN에 A안({sl_ctx['A']['name']}) {len(qust.T_CD)}일치 일정을 확정하세요.\n"
                f"② T_PN_B에 B안({sl_ctx['B']['name']}) {len(qust.T_CD)}일치 일정을 확정하세요.\n"
                f"③ CC는 A안({sl_ctx['A']['name']}) 전체 여행을 2~3문장으로 소개하세요. T_PN 장소만 사용. 완결된 독립 문장.\n"
                f"④ T_SL은 B안({sl_ctx['B']['name']}) 전체 여행을 2~3문장으로 소개하세요. T_PN_B 장소만 사용. 완결된 독립 문장.\n"
                f"   CC와 T_SL은 각각 독립된 여행 소개이며, 서로 이어지거나 연속되는 서술 절대 금지."
            )
        elif qust.T_SL:
            extra.append(f"[현재 선택 대기 중]: {qust.T_SL}")
        if qust.T_SEL and qust.T_SEL.get("days"):
            day_labels = [f"{d + 1}일차" for d in qust.T_SEL["days"]]
            extra.append(
                f"[편집 대상 제한]: 사용자가 {', '.join(day_labels)}만 수정하도록 지정했습니다. "
                f"T_PN 응답 시 해당 일차만 변경하고, 나머지 일차는 기존 내용을 그대로 유지하세요."
            )
        if extra:
            prompt += "\n\n" + "\n\n".join(extra)

        print("\n===== [PORT3 LLM PROMPT] =====\n" + prompt + "\n==============================\n", flush=True)
        try:
            raw = await LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY).ask(prompt, json_mode=True)
        except Exception as e:
            print(f"[Port3] LLM 호출 실패: {type(e).__name__}: {e}", flush=True)
            return PC3(
                USR_ANAL=qust.USR_ANAL, SSN_TPC=qust.SSN_TPC, SSN_PCL=qust.SSN_PCL,
                CC=f"일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요. ({type(e).__name__})",
                T_SL=qust.T_SL, T_CD=None, T_MP=None, T_MK=None, T_PN=None, SL_CTX={},
            )
        print("\n===== [PORT3 LLM RAW] =====\n" + raw + "\n===========================\n", flush=True)

        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]
            stripped = stripped.rsplit("```", 1)[0].strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            # LLM이 콜론 대신 쉼표로 key-value 구분하거나 JSON 잘린 경우 CC 추출
            import re as _re
            cc_match = _re.search(r'"CC"\s*[,:]\s*"((?:[^"\\]|\\.)*)"', stripped)
            data = {"CC": cc_match.group(1)} if cc_match else {"CC": "죄송합니다, 응답 생성 중 오류가 발생했습니다."}

        # T_SL이 설정된 경우 A/B 각 일정을 sl_ctx에 내장 → 선택 시 LLM 재호출 불필요
        t_pn_a_raw = data["T_PN"] if "T_PN" in data else None
        t_pn_b_raw = data.get("T_PN_B")

        # 날짜 수 교정 + 플레이스홀더 아이템 제거 (항상 실행)
        if t_pn_a_raw is not None and qust.T_CD:
            t_pn_a_raw = Port3._fix_t_pn_days(t_pn_a_raw, list(qust.T_CD))
        if t_pn_b_raw is not None and qust.T_CD:
            t_pn_b_raw = Port3._fix_t_pn_days(t_pn_b_raw, list(qust.T_CD))

        # SDB 실제 좌표/주소로 place_info 교정 (LLM 할루시네이션 방지)
        t_pn_a_raw = self._enrich_place_info(t_pn_a_raw)
        t_pn_b_raw = self._enrich_place_info(t_pn_b_raw)

        if sl_ctx:
            if t_pn_a_raw is not None:
                sl_ctx["A"]["t_pn"] = t_pn_a_raw
            if t_pn_b_raw is not None:
                sl_ctx["B"]["t_pn"] = t_pn_b_raw

        # T_CD: 캘린더에서 이미 선택된 날짜는 LLM이 덮어쓰지 못하게 보존
        t_cd_result = data["T_CD"] if "T_CD" in data else None
        if qust.T_CD:
            t_cd_result = list(qust.T_CD)

        # None = LLM이 해당 필드를 JSON에서 생략함 → core의 _diff_or_keep이 이전 값 유지.
        # [] = LLM이 명시적으로 빈 배열을 반환함 → 위젯 초기화.
        return PC3(
            USR_ANAL=qust.USR_ANAL,
            SSN_TPC=qust.SSN_TPC,
            SSN_PCL=qust.SSN_PCL,
            CC=data.get("CC") or "죄송합니다, 응답 생성 중 오류가 발생했습니다.",
            T_SL=data.get("T_SL", qust.T_SL),
            T_CD=t_cd_result,
            T_MP=data["T_MP"] if "T_MP" in data else None,
            T_MK=_mk_from_list(data["T_MK"]) if "T_MK" in data else None,
            T_PN=_pn_from_list(t_pn_a_raw) if t_pn_a_raw is not None else None,
            SL_CTX=sl_ctx or {},
        )

    async def _call_ppl(self, query: str) -> str:
        raise NotImplementedError
