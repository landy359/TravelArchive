"""
port3.py
P3 포트 — 양방향 (Port3 ↔ Core)

흐름: PC3 → QUST → [sDB → dDB → PPL] → LLM → PC3
"""

from __future__ import annotations

import dataclasses
import json
import re as _re
from typing import TYPE_CHECKING, List

from .protocol import PC3, QUST, _mk_from_list, _pn_from_list
from ..kernel.keyword_scorer import top_n_keywords, compute_sl_ctx, KW_BAG_HINT_N

if TYPE_CHECKING:
    from .core import Core

# ── 패턴 감지 (모듈 로드 시 컴파일) ───────────────────────────────────────
_WEATHER_RE    = _re.compile(r'날씨|기온|강수|우산|맑음?|흐림?|바람|온도|덥|춥|따뜻')
_DETAIL_RE     = _re.compile(r'상세|자세(히|하게)?|길게|설명해줘?|동선|장소.*정보')
_DAY_RE        = _re.compile(r'(\d+)\s*일\s*차')
_EDIT_RE       = _re.compile(r'추가|제거|삭제|바꿔|교체|수정|넣어|빼|변경|제외')
_RESET_RE      = _re.compile(r'다시\s*(?:세워|짜|만들어|계획|작성)|새로\s*(?:세워|짜|만들어|계획|작성)|처음부터\s*다시|새\s*여행\s*계획')
_RESTAURANT_RE = _re.compile(r'식당|음식점|맛집|레스토랑|밥집')
_DATE_CHANGE_RE = _re.compile(r'날짜.*(?:바꿔|바꿔줘|변경|수정|고쳐)|달력.*(?:수정|바꿔|변경)|\d+월\s*\d+일.*(?:부터|~|까지)')


class Port3:

    def __init__(self, core: "Core", user_id: str = "", kw_bag: dict | None = None, use_pipeline: bool = False) -> None:
        self.core      = core
        self._user_id  = user_id
        self._kw_bag   = kw_bag or {}
        from ..kernel.db_connector import DBConnector
        from ..kernel.sdb import SDB
        from ..kernel.ddb import DDB
        from ..kernel.ppl import PPL
        from ..kernel.llm import LLM
        _db_connector = DBConnector()
        _llm = LLM()
        self.sdb = SDB(_db_connector, _llm)
        self.ddb = DDB(_db_connector)
        self.ppl = PPL()
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
        from ..execute_unit.widget.widget_trip_clander import TripClanderWidget
        # 시나리오1: "다시 세워줘" 패턴 + CC에 날짜가 있으면 T_CD 교체 + T_PN 초기화
        if _RESET_RE.search(qust.CC or "") and qust.T_PN:
            _new_cd = TripClanderWidget._normalize_dates(qust.CC)
            if _new_cd:
                qust = dataclasses.replace(qust, T_CD=_new_cd, T_PN=[])
        # @PLAN 또는 일반 채팅에서 명시적 날짜 변경 요청 시 T_CD 갱신
        elif self._pipeline or _DATE_CHANGE_RE.search(qust.CC or ""):
            _cd_from_cc = TripClanderWidget._normalize_dates(qust.CC)
            if _cd_from_cc and _cd_from_cc != list(qust.T_CD or []):
                qust = dataclasses.replace(qust, T_CD=_cd_from_cc)

        # T_CD(여행 날짜)가 없으면 날씨(DDB) 생략 — 날짜 없이 날씨 조회는 무의미
        for node in self._pipeline:
            if node.__class__.__name__ == 'DDB' and not qust.T_CD:
                continue
            qust = await node.run(qust)

        # 시나리오6: @PLAN 없어도 날씨 질문 + T_CD가 있으면 날씨 데이터 단독 조회
        if not self._pipeline and qust.T_CD and _WEATHER_RE.search(qust.CC or ""):
            qust = await self.ddb.run(qust)

        sl_ctx = compute_sl_ctx(qust.route_keywords, self._kw_bag) if qust.route_keywords else None
        # CC에서 "X A와 Y B" 패턴 감지 → 사용자가 명시한 A/B 순서로 sl_ctx 재정렬
        if sl_ctx and qust.CC:
            _m_ab = _re.search(
                r'([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)\s+[Aa]안?\s*[와과,]?\s*'
                r'([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)\s+[Bb]안?',
                qust.CC
            )
            if _m_ab:
                _a_hint = _m_ab.group(1).strip()
                _score_cur_a = sum(1 for w in _a_hint.split() if len(w) >= 2 and w in sl_ctx['A']['name'])
                _score_cur_b = sum(1 for w in _a_hint.split() if len(w) >= 2 and w in sl_ctx['B']['name'])
                if _score_cur_b > _score_cur_a:
                    sl_ctx['A'], sl_ctx['B'] = sl_ctx['B'], sl_ctx['A']
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

    @staticmethod
    def _auto_t_sel(cc: str, t_pn_len: int) -> dict:
        """CC에서 'N일차 편집' 패턴을 감지해 T_SEL 자동 생성. 편집 동사 없으면 {}."""
        if not cc or not t_pn_len or not _EDIT_RE.search(cc):
            return {}
        days = [int(m) - 1 for m in _DAY_RE.findall(cc)]
        valid = sorted({d for d in days if 0 <= d < t_pn_len})
        return {"days": valid} if valid else {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        """이름 비교용 정규화: 공백·특수문자 제거 후 소문자."""
        import re as _re2
        return _re2.sub(r'[\s\-·.·,()（）\[\]「」『』]', '', name).lower()

    def _enrich_place_info(self, t_pn_raw: list | None, sdb_items) -> list | None:
        """LLM이 생성한 place_info를 qust.sDB 실제 데이터로 교정 (DB 접근 X)."""
        if not t_pn_raw or not sdb_items:
            return t_pn_raw

        # 일차별 dict 구조 또는 flat list 모두 처리
        sdb_dict = {}      # exact name → item
        sdb_norm = {}      # normalized name → item
        if isinstance(sdb_items, dict):
            for day_dict in sdb_items.values():
                for items in day_dict.values():
                    for item in items:
                        sdb_dict[item.name] = item
                        sdb_norm[Port3._normalize_name(item.name)] = item
        elif isinstance(sdb_items, list):
            for item in sdb_items:
                sdb_dict[item.name] = item
                sdb_norm[Port3._normalize_name(item.name)] = item

        for day in t_pn_raw:
            if not isinstance(day, list):
                continue
            for item in day:
                if not isinstance(item, dict):
                    continue
                place = item.get("place", "")
                # exact match → normalized match 순으로 시도
                row = sdb_dict.get(place) or sdb_norm.get(Port3._normalize_name(place)) if place else None
                if row:
                    item["place_info"] = {
                        "place_id":     row.place_id,
                        "name":         row.name,
                        "address_road": row.address_road,
                        "lat":          row.lat,
                        "lng":          row.lon,
                        "description":  row.sub_category,
                        "category":     row.main_category,
                    }
        return t_pn_raw

    async def _call_llm(self, qust: QUST, sl_ctx: dict | None = None) -> PC3:
        from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY, ROUTER_PROMPT
        from ..kernel.llm import LLM

        # 시나리오8: T_SEL 없고 T_PN이 있으면 CC에서 편집 범위 자동 추출
        if not qust.T_SEL and qust.T_PN:
            auto_sel = Port3._auto_t_sel(qust.CC, len(qust.T_PN))
            if auto_sel:
                qust = dataclasses.replace(qust, T_SEL=auto_sel)

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
        # T_CD가 없으면: SDB가 추출한 days 수만큼 오늘부터 날짜 생성, 없으면 오늘 하루만
        from datetime import date as _date, timedelta as _td
        if qust.T_CD:
            _effective_cd = list(qust.T_CD)
        elif self._pipeline:  # 시나리오5: @PLAN 모드에서만 오늘 날짜 자동 생성
            _n = max(1, getattr(qust, 'days', 1) or 1)
            _today = _date.today()
            _effective_cd = [
                f"{(_today + _td(i)).year % 100:02d}{(_today + _td(i)).month:02d}{(_today + _td(i)).day:02d}"
                for i in range(_n)
            ]
        else:
            _effective_cd = []
        if _effective_cd:
            cd_codes = _effective_cd
            n = len(cd_codes)
            day_lines = [
                f"{i+1}일차: 20{d[:2]}년 {int(d[2:4])}월 {int(d[4:6])}일 (date코드: {d})"
                for i, d in enumerate(cd_codes)
            ]
            skeleton = [[{"date": d, "order": i} for i in range(4)] for d in cd_codes]
            extra.append(
                f"[여행 날짜 ({n}일) — 절대 규칙]\n"
                + "\n".join(day_lines)
                + f"\n\n★ T_CD는 반드시 {json.dumps(cd_codes, ensure_ascii=False)} 그대로 출력. 다른 날짜 코드 사용 금지.\n"
                + f"★ T_PN과 T_PN_B 모든 date 필드는 위 date코드만 사용. 다른 날짜 코드 사용 시 오답.\n"
                + f"★ T_PN, T_PN_B 외부 배열 수 = {n}개 (날짜 수와 반드시 일치). 반드시 [[day1 items], [day2 items], ...] 형식.\n"
                + f"★ 모든 날짜({n}일치)에 장소를 채울 것.\n"
                + f"★ 각 일차 T_PN에 최소 3개 이상의 서로 다른 장소를 채울 것. 1~2개만 넣으면 오답.\n"
                + (
                    "▶ 사용자가 상세 설명을 원합니다. CC에 일차별 장소와 이동 동선을 충분히 설명하세요."
                    + (" T_PN에 있는 장소 이름만 사용.\n" if qust.T_PN else " 계획된 장소를 일차별로 상세히 서술하세요.\n")
                    if _DETAIL_RE.search(qust.CC or "")
                    else "▶ CC는 T_PN 장소만 2~3문장으로 짧게 요약. 장황한 일정 나열 금지.\n"
                )
                + (
                    "▶ 사용자가 식당/음식점을 요청했습니다. 매 일차 T_PN에 반드시 식당·음식점 장소를 1개 이상 포함하세요.\n"
                    if _RESTAURANT_RE.search(qust.CC or "")
                    else ""
                )
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
        if qust.sDB and isinstance(qust.sDB, dict):
            lines = []
            for day, cat_dict in qust.sDB.items():
                lines.append(f"\n[{day}일차 앵커 주변 장소 후보]")
                for cat, items in cat_dict.items():
                    if not items:
                        continue
                    place_names = ", ".join([f"{p.name}({p.region})" for p in items])
                    lines.append(f" - {cat}: {place_names}")
            extra.append("[일차별 방문 가능한 장소 DB]:" + "\n".join(lines))
        elif qust.sDB and isinstance(qust.sDB, list):
            lines = [f"{p.name} ({p.main_category}) / {p.region}" for p in qust.sDB]
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
        # 시나리오12/14: 사용자가 지도에 직접 추가한 마커 — 일정 수립 시 반영 요청
        if qust.T_MK:
            mk_lines = []
            for mk in qust.T_MK:
                pi = mk.place_info if hasattr(mk, 'place_info') else {}
                name = (pi.name if hasattr(pi, 'name') else pi.get('name', '')) if pi else ''
                lat  = (pi.lat  if hasattr(pi, 'lat')  else pi.get('lat',  0))  if pi else 0
                lng  = (pi.lng  if hasattr(pi, 'lng')  else pi.get('lng',  0))  if pi else 0
                if name or lat:
                    coord = f" (lat:{lat}, lng:{lng})" if lat and lng else ""
                    mk_lines.append(f"- {name or mk.marker_id}{coord}")
            if mk_lines:
                extra.append(
                    "[사용자 지정 마커 — 반드시 반영]:\n"
                    + "\n".join(mk_lines)
                    + "\n▶ 위 마커 장소들을 T_PN 일정에 포함하거나, 동선 최적화 시 기준점으로 활용하세요."
                )
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
            _edit_hint = ""
            if _RESTAURANT_RE.search(qust.CC or ""):
                _edit_hint = " 사용자가 식당/음식점을 요청했습니다. 반드시 식당·음식점 장소를 포함하세요."
            extra.append(
                f"[편집 대상 제한]: 사용자가 {', '.join(day_labels)}만 수정하도록 지정했습니다. "
                f"T_PN 응답 시 해당 일차만 변경하고, 나머지 일차는 기존 내용을 그대로 유지하세요."
                + _edit_hint
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
        t_pn_a_raw = self._enrich_place_info(t_pn_a_raw, qust.sDB)
        t_pn_b_raw = self._enrich_place_info(t_pn_b_raw, qust.sDB)

        if sl_ctx:
            if t_pn_a_raw is not None:
                sl_ctx["A"]["t_pn"] = t_pn_a_raw
            if t_pn_b_raw is not None:
                sl_ctx["B"]["t_pn"] = t_pn_b_raw

        # T_CD: _effective_cd가 있으면 LLM 출력 무시하고 강제 고정
        # LLM이 "반드시 ... 그대로 출력" 지시를 어겨도 날짜 drift 방지
        if _effective_cd:
            t_cd_result = _effective_cd
        else:
            t_cd_result = data["T_CD"] if "T_CD" in data else None

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
