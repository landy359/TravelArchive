"""
PPL → LLM 전체 파이프라인 입출력 디버그 스크립트.
실행: python run_ppl_debug.py
"""
import asyncio
import json
import os

from backend.kernel.ppl import PPL
from backend.kernel.llm import LLM
from backend.router.protocol import QUST, T_MK_Item, T_PN_Item, PlaceInfo
from setting.config import LLM_MODEL_GENERATION, GENERATION_API_KEY, ROUTER_PROMPT


DIVIDER = "=" * 60


def _build_llm_prompt(qust: QUST) -> str:
    """port3._call_llm 로직 그대로 + PPL 섹션 추가."""
    past = json.loads(qust.SSN_PCL) if qust.SSN_PCL else []
    history = "\n".join(
        f"{'사용자' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')}"
        for m in past
    ) or "없음"

    base = ROUTER_PROMPT.format(
        usr_anal=qust.USR_ANAL or "없음",
        ssn_tpc=qust.SSN_TPC or "없음",
        ssn_pcl=history,
        cc=qust.CC,
    )

    if qust.PPL:
        base += f"\n\n[경로 후보 (Perplexity 검색 결과)]:\n{qust.PPL}"

    return base


async def main():
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise SystemExit("PERPLEXITY_API_KEY not set")

    # ── 입력 QUST 구성 ──────────────────────────────
    qust = QUST(
        SSN_TPC="제주도 2박3일",
        T_CD=["260601", "260602", "260603"],
        CC="가족 여행, 아이 있음",
        T_MK=[
            T_MK_Item(marker_id="m1", place_info=PlaceInfo(name="성산일출봉", category="관광지")),
            T_MK_Item(marker_id="m2", place_info=PlaceInfo(name="협재해수욕장", category="해변")),
        ],
        T_PN=[[
            T_PN_Item(date="260601", order=1, place="제주공항"),
            T_PN_Item(date="260601", order=2, place="애월 카페"),
        ]],
    )

    print(DIVIDER)
    print("[1] INPUT — QUST JSON")
    print(DIVIDER)
    print(json.dumps(qust.to_dict(), ensure_ascii=False, indent=2))

    # ── PPL 실행 ─────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("[2] PPL — Perplexity에 보내는 프롬프트")
    print(DIVIDER)
    ppl = PPL(api_key=api_key)
    print(ppl._build_prompt(qust))

    print(f"\n{DIVIDER}")
    print("[3] PPL — Perplexity 응답 (qust.PPL)")
    print(DIVIDER)
    qust = await ppl.run(qust)
    print(qust.PPL)

    # ── LLM 실행 ─────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("[4] LLM — GPT에 보내는 프롬프트")
    print(DIVIDER)
    llm_prompt = _build_llm_prompt(qust)
    print(llm_prompt)

    print(f"\n{DIVIDER}")
    print("[5] LLM — GPT 응답 (raw)")
    print(DIVIDER)
    llm = LLM(model_name=LLM_MODEL_GENERATION, api_key=GENERATION_API_KEY)
    raw = await llm.ask(llm_prompt)
    print(raw)

    print(f"\n{DIVIDER}")
    print("[6] OUTPUT — 파싱된 PC3 필드")
    print(DIVIDER)
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(stripped)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(f"JSON 파싱 실패 — raw 반환:\n{raw}")


if __name__ == "__main__":
    asyncio.run(main())
