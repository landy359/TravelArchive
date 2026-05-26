"""
T_SL 선택지 시스템 — 시나리오 테스트 (외부 API 없이 mock)

시나리오:
  1. 유저 "제주도 3박4일 여행 추천해줘"
  2. PPL이 5개 경로 반환, 각 경로 5개 키워드 포함
  3. kw_bag 없음 → 모든 경로 점수 0 → 차이 0 ≤ SELECT_THRESHOLD → sl_ctx 생성
  4. LLM이 T_SL = "A안: 제주 힐링코스 | B안: 제주 맛집투어" 출력
  5. 게이트 활성화: t_cd/t_mk/t_pn은 pending_widgets 보관, t_sl만 위젯에 적용
  6. 유저가 A안 선택 → select_route("A")
  7. A안 키워드 +1, B안 키워드 -1 → kw_bag 업데이트
  8. pending_widgets 적용, t_sl="" → SSE widget_update
  9. 다음 PPL 호출 시 kw_bag 상위 N개 힌트 주입됨
 10. kw_bag이 채워진 두번째 대화 → 경로 점수 차 threshold 초과 → T_SL 미표시
"""
from __future__ import annotations
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any


# ─────────────────────────────────────────────
# Redis 인메모리 Mock
# ─────────────────────────────────────────────

def make_redis(initial: dict | None = None) -> MagicMock:
    store: dict = dict(initial or {})
    r = MagicMock()
    async def get_json(key):             return store.get(key)
    async def set_json(key, val, ttl):   store[key] = val; return None
    r.get_json  = get_json
    r.set_json  = set_json
    r._store    = store
    return r


# ─────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────

PPL_OUTPUT = """\
1. 제주 힐링코스: 사려니숲길 → 협재해변 → 카페거리
  실제 여행자들이 자연과 휴식을 위해 선택하는 경로.
  키워드: 힐링, 자연, 해수욕장, 숲길, 카페

2. 제주 맛집투어: 동문시장 → 성산일출봉 → 흑돼지거리
  맛집과 관광을 동시에 즐기는 인기 경로.
  키워드: 맛집, 시장, 일출, 야경, 현지음식

3. 제주 드라이브: 해안도로 → 우도 → 마라도
  드라이브와 섬 탐방을 위한 경로.
  키워드: 드라이브, 섬, 낚시, 바다, 자전거

4. 제주 문화투어: 국립박물관 → 제주시청 → 민속촌
  제주 문화 탐방 경로.
  키워드: 문화, 역사, 전통, 박물관, 민속

5. 제주 레저: 한라산 → 성판악 → 오름
  액티비티를 즐기는 경로.
  키워드: 등산, 트레킹, 오름, 한라산, 액티비티
"""


# ─────────────────────────────────────────────
# 1. keyword_scorer 단위 테스트
# ─────────────────────────────────────────────

class TestKeywordScorer(unittest.IsolatedAsyncioTestCase):

    # S1: 빈 bag → 모든 경로 점수 0
    def test_empty_bag_all_zero(self):
        from backend.kernel.keyword_scorer import score_route
        self.assertEqual(score_route(["힐링", "자연", "해수욕장"], {}), 0)
        self.assertEqual(score_route(["맛집", "시장", "야경"], {}), 0)

    # S2: bag에 점수 있으면 매칭된 경로 점수 상승
    def test_bag_scores_matching_route(self):
        from backend.kernel.keyword_scorer import score_route
        bag = {"힐링": 3, "자연": 2, "맛집": 1}
        self.assertEqual(score_route(["힐링", "자연", "해수욕장"], bag), 5)  # 3+2+0
        self.assertEqual(score_route(["맛집", "시장", "야경"], bag), 1)      # 1+0+0

    # S3: 점수 차 ≤ threshold → sl_ctx 반환
    def test_similar_scores_returns_sl_ctx(self):
        from backend.kernel.keyword_scorer import compute_sl_ctx
        route_data = {
            1: {"name": "힐링코스", "keywords": ["힐링", "자연"]},
            2: {"name": "맛집투어", "keywords": ["맛집", "시장"]},
        }
        sl_ctx = compute_sl_ctx(route_data, bag={}, threshold=3)
        self.assertIsNotNone(sl_ctx)
        self.assertIn("A", sl_ctx)
        self.assertIn("B", sl_ctx)

    # S4: 점수 차 > threshold → None
    def test_biased_bag_no_sl_ctx(self):
        from backend.kernel.keyword_scorer import compute_sl_ctx
        bag = {"힐링": 10, "자연": 8, "해수욕장": 6}
        route_data = {
            1: {"name": "힐링코스", "keywords": ["힐링", "자연", "해수욕장"]},
            2: {"name": "맛집투어", "keywords": ["맛집", "시장", "야경"]},
        }
        sl_ctx = compute_sl_ctx(route_data, bag, threshold=3)
        self.assertIsNone(sl_ctx)  # 24 vs 0, 차이 24 > 3

    # S5: top_n_keywords — 점수 내림차순 상위 N개
    def test_top_n_returns_highest_scored(self):
        from backend.kernel.keyword_scorer import top_n_keywords
        bag = {"힐링": 5, "자연": 3, "맛집": 1, "야경": 7}
        top = top_n_keywords(bag, n=2)
        self.assertEqual(top, ["야경", "힐링"])

    # S6: 경로 1개 → sl_ctx 불가
    def test_single_route_no_sl_ctx(self):
        from backend.kernel.keyword_scorer import compute_sl_ctx
        sl_ctx = compute_sl_ctx({1: {"name": "X", "keywords": ["a"]}}, {}, threshold=3)
        self.assertIsNone(sl_ctx)

    # S7: clamp — 점수 상한/하한 (순수 함수)
    def test_score_clamped_at_max(self):
        from backend.kernel.keyword_scorer import apply_selection, KW_SCORE_MAX
        sl_ctx = {
            "A": {"name": "X", "keywords": ["힐링"]},
            "B": {"name": "Y", "keywords": []},
        }
        new_bag = apply_selection("A", sl_ctx, {"힐링": KW_SCORE_MAX})
        self.assertEqual(new_bag["힐링"], KW_SCORE_MAX)  # 초과 안 함

    # S8: invalid choice → ValueError (순수 함수)
    def test_invalid_choice_raises(self):
        from backend.kernel.keyword_scorer import apply_selection
        with self.assertRaises(ValueError) as ctx:
            apply_selection("C", {}, {})
        self.assertEqual(str(ctx.exception), "invalid_choice")

    # S9: 다른 유저의 bag에 영향 없음 — ChatService.select_route 경유
    async def test_kw_bag_user_isolation(self):
        sl_ctx = {"A": {"name":"X","keywords":["a"]}, "B": {"name":"Y","keywords":[]}}
        redis = make_redis({
            "session:s:sl_ctx": sl_ctx,
            "user:u1:kw_bag": {"a": 0},
            "user:u2:kw_bag": {"a": 5},
        })
        container = MagicMock()
        container.widget_state = {"t_sl": "", "t_cd": [], "t_mp": [], "t_mk": [], "t_pn": []}
        container.commit_turn = AsyncMock()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            await ChatService.select_route("s", "u1", "A", redis, manager=None)
        bag1 = await redis.get_json("user:u1:kw_bag")
        bag2 = await redis.get_json("user:u2:kw_bag")
        self.assertEqual(bag1["a"], 1)   # u1만 변경
        self.assertEqual(bag2["a"], 5)   # u2 불변


# ─────────────────────────────────────────────
# 2. PPL 키워드 파싱 단위 테스트
# ─────────────────────────────────────────────

class TestPPLKeywordParsing(unittest.TestCase):

    def setUp(self):
        from backend.kernel.ppl import PPL
        self.ppl = PPL.__new__(PPL)

    # P1: 5개 경로 파싱
    def test_parses_five_routes(self):
        result = self.ppl._parse_route_data(PPL_OUTPUT)
        self.assertEqual(len(result), 5)

    # P2: 각 경로 키워드 파싱
    def test_each_route_has_keywords(self):
        result = self.ppl._parse_route_data(PPL_OUTPUT)
        self.assertEqual(result[1]["keywords"], ["힐링", "자연", "해수욕장", "숲길", "카페"])
        self.assertEqual(result[2]["keywords"], ["맛집", "시장", "일출", "야경", "현지음식"])

    # P3: 경로명 파싱
    def test_route_names_extracted(self):
        result = self.ppl._parse_route_data(PPL_OUTPUT)
        self.assertEqual(result[1]["name"], "제주 힐링코스")
        self.assertEqual(result[2]["name"], "제주 맛집투어")

    # P4: 키워드 라인 없는 경로 → 건너뜀
    def test_missing_keyword_line_skipped(self):
        text = "1. 테스트 경로: A → B\n이런저런 이유.\n\n2. 두번째 경로: C → D\n내용.\n키워드: 문화, 역사\n"
        result = self.ppl._parse_route_data(text)
        self.assertNotIn(1, result)   # 키워드 없어서 건너뜀
        self.assertIn(2, result)
        self.assertEqual(result[2]["keywords"], ["문화", "역사"])


# ─────────────────────────────────────────────
# 3. select_route 처리 시나리오
# ─────────────────────────────────────────────

class TestSelectRoute(unittest.IsolatedAsyncioTestCase):

    def _make_container(self, t_sl="A안:힐링|B안:맛집", t_cd=None):
        container = MagicMock()
        container.widget_state = {
            "t_sl": t_sl,
            "t_cd": t_cd or [],
            "t_mp": [],
            "t_mk": [],
            "t_pn": [],
        }
        container.commit_turn = AsyncMock()
        return container

    # E2E: A 선택 → kw_bag 업데이트 + pending 적용 + t_sl 제거
    async def test_select_a_full_flow(self):
        sl_ctx = {
            "A": {"name": "힐링코스", "keywords": ["힐링", "자연", "해수욕장"]},
            "B": {"name": "맛집투어", "keywords": ["맛집", "시장", "야경"]},
        }
        pending = {"t_cd": ["260601", "260604"], "t_mp": [], "t_mk": [], "t_pn": []}
        redis = make_redis({
            "session:s1:sl_ctx": sl_ctx,
            "session:s1:pending_widgets": pending,
        })
        container = self._make_container()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            result = await ChatService.select_route("s1", "u1", "A", redis, manager=None)

        self.assertTrue(result["success"])
        self.assertEqual(result["choice"], "A")

        # kw_bag: A 키워드 +1, B 키워드 -1
        bag = await redis.get_json("user:u1:kw_bag")
        self.assertEqual(bag["힐링"], 1)
        self.assertEqual(bag["자연"], 1)
        self.assertEqual(bag["맛집"], -1)
        self.assertEqual(bag["야경"], -1)

        # commit_turn 호출: t_sl="" + pending t_cd 적용
        call_kw = container.commit_turn.call_args.kwargs
        self.assertEqual(call_kw["widget_state"]["t_sl"], "")
        self.assertEqual(call_kw["widget_state"]["t_cd"], ["260601", "260604"])

    # B 선택 → B 키워드 +1, A 키워드 -1
    async def test_select_b_opposite_update(self):
        sl_ctx = {
            "A": {"name": "힐링코스", "keywords": ["힐링", "자연"]},
            "B": {"name": "맛집투어", "keywords": ["맛집", "야경"]},
        }
        redis = make_redis({
            "session:s2:sl_ctx": sl_ctx,
            "session:s2:pending_widgets": {"t_cd": [], "t_mp": [], "t_mk": [], "t_pn": []},
        })
        container = self._make_container()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            await ChatService.select_route("s2", "u2", "B", redis, manager=None)
        bag = await redis.get_json("user:u2:kw_bag")
        self.assertEqual(bag["맛집"], 1)   # B 선택
        self.assertEqual(bag["힐링"], -1)  # A 거부

    # sl_ctx 없으면 ValueError
    async def test_select_without_sl_ctx_raises(self):
        redis = make_redis()
        container = self._make_container()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            with self.assertRaises(ValueError) as ctx:
                await ChatService.select_route("s3", "u3", "A", redis, manager=None)
        self.assertEqual(str(ctx.exception), "sl_ctx_not_found")

    # pending 없어도 bag 업데이트는 정상
    async def test_select_without_pending_bag_still_updates(self):
        sl_ctx = {"A": {"name": "X", "keywords": ["a", "b"]}, "B": {"name": "Y", "keywords": ["c"]}}
        redis = make_redis({"session:s4:sl_ctx": sl_ctx})  # pending 없음
        container = self._make_container(t_sl="")
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            await ChatService.select_route("s4", "u4", "A", redis, manager=None)
        bag = await redis.get_json("user:u4:kw_bag")
        self.assertEqual(bag["a"], 1)

    # sl_ctx clear after selection
    async def test_sl_ctx_cleared_after_select(self):
        sl_ctx = {"A": {"name": "X", "keywords": ["a"]}, "B": {"name": "Y", "keywords": []}}
        redis = make_redis({
            "session:s5:sl_ctx": sl_ctx,
            "session:s5:pending_widgets": {"t_cd": [], "t_mp": [], "t_mk": [], "t_pn": []},
        })
        container = self._make_container()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            await ChatService.select_route("s5", "u5", "A", redis, manager=None)
        # sl_ctx가 빈 dict로 교체됨 (apply_selection에서 처리)
        ctx = await redis.get_json("session:s5:sl_ctx")
        self.assertFalse(bool(ctx))  # None 또는 {}

    # session 격리: 다른 세션의 sl_ctx와 섞이지 않음
    async def test_sl_ctx_session_isolation(self):
        sl_ctx_s1 = {"A": {"name": "X", "keywords": ["a"]}, "B": {"name": "Y", "keywords": []}}
        sl_ctx_s2 = {"A": {"name": "P", "keywords": ["b"]}, "B": {"name": "Q", "keywords": []}}
        redis = make_redis({
            "session:s_a:sl_ctx": sl_ctx_s1,
            "session:s_b:sl_ctx": sl_ctx_s2,
            "session:s_a:pending_widgets": {"t_cd":[],"t_mp":[],"t_mk":[],"t_pn":[]},
        })
        container = self._make_container()
        from backend.execute_unit.chat.chat_service import ChatService
        with patch.object(ChatService, '_get_container', new=AsyncMock(return_value=container)):
            await ChatService.select_route("s_a", "u", "A", redis, manager=None)
        # s_b sl_ctx는 그대로
        ctx_b = await redis.get_json("session:s_b:sl_ctx")
        self.assertEqual(ctx_b["A"]["name"], "P")


# ─────────────────────────────────────────────
# 4. compute_sl_ctx 상세 시나리오
# ─────────────────────────────────────────────

class TestComputeSlCtxScenario(unittest.TestCase):

    def test_top_two_selected_as_a_b(self):
        """점수가 가장 높은 2개가 A/B로 선정됨"""
        from backend.kernel.keyword_scorer import compute_sl_ctx
        bag = {"맛집": 5, "야경": 3}
        route_data = {
            1: {"name": "힐링코스", "keywords": ["힐링", "자연"]},
            2: {"name": "맛집투어", "keywords": ["맛집", "야경"]},
            3: {"name": "드라이브", "keywords": ["드라이브", "섬"]},
        }
        sl_ctx = compute_sl_ctx(route_data, bag, threshold=10)
        self.assertIsNotNone(sl_ctx)
        # 2번 경로가 점수 8로 1위 → A
        # 나머지 0점 → threshold 내 → B
        self.assertEqual(sl_ctx["A"]["name"], "맛집투어")

    def test_threshold_boundary(self):
        """threshold 정확히 같으면 표시, 1 초과면 미표시"""
        from backend.kernel.keyword_scorer import compute_sl_ctx
        bag = {"a": 3}
        route_data = {
            1: {"name": "X", "keywords": ["a"]},  # score=3
            2: {"name": "Y", "keywords": []},      # score=0
        }
        self.assertIsNotNone(compute_sl_ctx(route_data, bag, threshold=3))  # 3-0==3 ≤ 3
        self.assertIsNone(compute_sl_ctx(route_data, bag, threshold=2))     # 3-0==3 > 2


if __name__ == "__main__":
    unittest.main(verbosity=2)
