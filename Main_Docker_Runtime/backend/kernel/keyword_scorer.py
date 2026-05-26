"""
keyword_scorer.py
역할: 경로 키워드 선호도 점수 계산 — 순수 함수만.
Redis 접근은 Cacher(memory/cacher.py)를 통해 호출자가 처리한다.
"""
from __future__ import annotations

KW_SCORE_MIN     = -10
KW_SCORE_MAX     =  10
KW_SCORE_DELTA   =   1
KW_BAG_HINT_N    =   5
SELECT_THRESHOLD =   3
KW_BAG_TTL       = 86400 * 30   # 30일
SL_CTX_TTL       = 1800         # 30분
PENDING_TTL      = 1800         # 30분


def _clamp(score: int) -> int:
    return max(KW_SCORE_MIN, min(KW_SCORE_MAX, score))


def top_n_keywords(bag: dict, n: int = KW_BAG_HINT_N) -> list[str]:
    return sorted(bag, key=bag.__getitem__, reverse=True)[:n]


def score_route(keywords: list[str], bag: dict) -> int:
    return sum(bag.get(kw, 0) for kw in keywords)


def compute_sl_ctx(
    route_data: dict,
    bag: dict,
    threshold: int = SELECT_THRESHOLD,
) -> dict | None:
    """route_data: {route_num: {name: str, keywords: list[str]}}
    Returns {A: {name, keywords}, B: {name, keywords}} if top-2 scores within threshold.
    Returns None if gap exceeds threshold or fewer than 2 routes.
    """
    if not route_data:
        return None
    scored = sorted(
        route_data.items(),
        key=lambda item: score_route(item[1].get("keywords", []), bag),
        reverse=True,
    )
    if len(scored) < 2:
        return None
    _, rd1 = scored[0]
    _, rd2 = scored[1]
    s1 = score_route(rd1.get("keywords", []), bag)
    s2 = score_route(rd2.get("keywords", []), bag)
    if abs(s1 - s2) > threshold:
        return None
    return {
        "A": {"name": rd1["name"], "keywords": rd1.get("keywords", [])},
        "B": {"name": rd2["name"], "keywords": rd2.get("keywords", [])},
    }


def apply_selection(choice: str, sl_ctx: dict, bag: dict) -> dict:
    """kw_bag을 업데이트한 새 dict를 반환한다. Redis 접근 없음.
    Raises ValueError('invalid_choice') if choice is not 'A' or 'B'.
    """
    if choice not in ("A", "B"):
        raise ValueError("invalid_choice")
    rejected = "B" if choice == "A" else "A"
    new_bag = dict(bag)
    for kw in sl_ctx.get(choice, {}).get("keywords", []):
        new_bag[kw] = _clamp(new_bag.get(kw, 0) + KW_SCORE_DELTA)
    for kw in sl_ctx.get(rejected, {}).get("keywords", []):
        new_bag[kw] = _clamp(new_bag.get(kw, 0) - KW_SCORE_DELTA)
    return new_bag
