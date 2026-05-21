"""
PPL 커널 노드 테스트.
실행: python -m pytest backend/tests/test_ppl.py -v
실제 API 호출 포함 테스트: python -m pytest backend/tests/test_ppl.py -v -m live
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.kernel.ppl import PPL
from backend.router.protocol import QUST, T_MK_Item, T_PN_Item, PlaceInfo, sDB_Item, dDB_Item


# ──────────────────────────────────────────────────────────
# _clean 단위 테스트 (API 호출 없음)
# ──────────────────────────────────────────────────────────

class CleanTests(unittest.TestCase):

    def test_removes_citation_numbers(self):
        result = PPL._clean("서울은 수도입니다[1]. 인구는 약 1000만[2,3].")
        self.assertNotIn("[1]", result)
        self.assertNotIn("[2,3]", result)
        self.assertIn("서울은 수도입니다", result)

    def test_removes_markdown_bold_and_italic(self):
        result = PPL._clean("**굵은** 텍스트와 *기울임* 텍스트.")
        self.assertEqual(result, "굵은 텍스트와 기울임 텍스트.")

    def test_removes_inline_code(self):
        result = PPL._clean("`코드블록` 제거.")
        self.assertEqual(result, "코드블록 제거.")

    def test_removes_urls(self):
        result = PPL._clean("참고: https://example.com/page?q=1 여기를 보세요.")
        self.assertNotIn("https://", result)

    def test_removes_meta_sentences(self):
        result = PPL._clean("According to recent data: 서울은 크다.")
        self.assertNotIn("According to", result)
        self.assertIn("서울은 크다", result)

    def test_collapses_excess_newlines(self):
        result = PPL._clean("A\n\n\n\nB")
        self.assertEqual(result, "A\n\nB")

    def test_empty_string_passthrough(self):
        self.assertEqual(PPL._clean(""), "")


# ──────────────────────────────────────────────────────────
# _build_prompt 단위 테스트 (API 호출 없음)
# ──────────────────────────────────────────────────────────

class BuildPromptTests(unittest.TestCase):

    def _ppl(self) -> PPL:
        return PPL(api_key="dummy")

    def test_includes_ssn_tpc(self):
        q = QUST(SSN_TPC="제주도 3박4일")
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("제주도 3박4일", prompt)

    def test_includes_t_cd(self):
        q = QUST(T_CD=["260601", "260602"])
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("260601", prompt)
        self.assertIn("260602", prompt)

    def test_includes_cc(self):
        q = QUST(CC="카페 위주로 보여줘")
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("카페 위주로 보여줘", prompt)

    def test_includes_t_mk_names(self):
        mk = T_MK_Item(marker_id="m1", place_info=PlaceInfo(name="성산일출봉"))
        q = QUST(T_MK=[mk])
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("성산일출봉", prompt)

    def test_includes_t_pn_places(self):
        pn = [[T_PN_Item(date="260601", order=1, place="협재해수욕장")]]
        q = QUST(T_PN=pn)
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("협재해수욕장", prompt)

    def test_includes_sdb_when_populated(self):
        q = QUST(sDB=[sDB_Item(name="흑돼지식당", main_category="식당", region="북부")])
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("흑돼지식당", prompt)
        self.assertIn("식당", prompt)

    def test_includes_ddb_when_populated(self):
        q = QUST(dDB=[dDB_Item(location="제주시", forecast_time="09", summary="맑음",
                               rain_prob=10, temperature=22.0)])
        prompt = self._ppl()._build_prompt(q)
        self.assertIn("제주시", prompt)
        self.assertIn("맑음", prompt)

    def test_empty_qust_has_only_prefix(self):
        prompt = self._ppl()._build_prompt(QUST())
        # prefix만 있어야 하고 섹션 구분자(\n\n)는 없어야 함
        self.assertNotIn("\n\n", prompt)


# ──────────────────────────────────────────────────────────
# run() 모킹 테스트 (API 호출 없음)
# ──────────────────────────────────────────────────────────

class RunMockTests(unittest.IsolatedAsyncioTestCase):

    async def test_run_fills_ppl_field(self):
        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message.content = "1. 경로 A\n2. 경로 B"

        with patch("backend.kernel.ppl._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
            mock_get_client.return_value = mock_client

            ppl = PPL(api_key="dummy")
            q = QUST(SSN_TPC="제주도 3박4일", CC="맛집 위주로")
            result = await ppl.run(q)

        self.assertIn("경로 A", result.PPL)
        self.assertIn("경로 B", result.PPL)

    async def test_run_returns_empty_on_api_error(self):
        with patch("backend.kernel.ppl._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
            mock_get_client.return_value = mock_client

            ppl = PPL(api_key="dummy")
            result = await ppl.run(QUST(SSN_TPC="제주도"))

        self.assertEqual(result.PPL, "")

    async def test_run_raises_without_api_key(self):
        ppl = PPL(api_key="")
        with self.assertRaises(RuntimeError):
            await ppl.run(QUST())


# ──────────────────────────────────────────────────────────
# 실제 API 호출 테스트 (PERPLEXITY_API_KEY 필요)
# pytest -m live 로만 실행
# ──────────────────────────────────────────────────────────

import pytest

@pytest.mark.live
class LiveTests(unittest.IsolatedAsyncioTestCase):

    async def test_real_api_call(self):
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            self.skipTest("PERPLEXITY_API_KEY not set")

        ppl = PPL(api_key=api_key)
        q = QUST(
            SSN_TPC="제주도 2박3일",
            T_CD=["260601", "260602", "260603"],
            CC="가족 여행, 아이 있음",
        )
        result = await ppl.run(q)

        print(f"\n[PPL 실제 응답]\n{result.PPL}")
        self.assertIsInstance(result.PPL, str)
        self.assertGreater(len(result.PPL), 50)


if __name__ == "__main__":
    unittest.main()
