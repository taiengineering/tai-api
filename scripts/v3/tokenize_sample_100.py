"""
TAI 법령엔진 v3.0 — Track A Day 1
의미절 sample 100건 일괄 토큰화 + 어말 분포 통계.

데이터 소스: Supabase law_article_part (deterministic random 100건)
출력: tail-3 토큰 패턴 분포 → Stage 2 sub_type 룰 baseline

실행:
    python scripts/v3/tokenize_sample_100.py

절대 원칙:
  - 결과 해석은 사람이 함. 본 스크립트는 분포 출력만.
  - LLM 사용 X.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# tai-api 루트 import path 보정
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.supabase_client import get_supabase  # noqa: E402
from kiwipiepy import Kiwi  # noqa: E402


def fetch_samples(n: int = 100) -> list[dict]:
    """law_article_part에서 100건 추출 (id 정렬, 길이 30~400, 삭제 제외).
    
    NOTE: deterministic md5 random은 PostgREST 미지원 → SQL RPC 함수 분리 필요.
          Day 1에선 id 정렬 + client-side 필터로 대체.
    """
    sb = get_supabase()
    # 1차로 500건 가져온 뒤 client-side 필터링
    res = (
        sb.table("law_article_part")
        .select("id,part_code,part_type,depth,part_text")
        .not_.like("part_text", "삭제%")
        .order("id")
        .limit(500)
        .execute()
    )
    rows = [
        r
        for r in (res.data or [])
        if r.get("part_text")
        and 30 <= len(r["part_text"]) <= 400
        and "&lt;" not in r["part_text"]
    ]
    return rows[:n]


def main() -> int:
    print("=" * 72)
    print("TAI 법령엔진 v3.0 — Track A Day 1: Sample 100 Tokenize")
    print("=" * 72)

    print("\n[STEP 1] Sample 100건 로드")
    samples = fetch_samples(100)
    print(f"  ✓ {len(samples)}건 로드 완료")
    if not samples:
        print("  ✗ Sample 0건 — DB 연결/쿼리 확인 필요")
        return 1

    print("\n[STEP 2] Kiwi 초기화")
    kiwi = Kiwi()
    print("  ✓ 완료")

    print("\n[STEP 3] 일괄 토큰화 (auto multi-thread)")
    texts = [row["part_text"] for row in samples]
    results = list(kiwi.tokenize(texts))
    print(f"  ✓ {len(results)}건 처리")

    print("\n[STEP 4] 마지막 토큰 (어말) POS 분포")
    last_tag: Counter[str] = Counter()
    last_form: Counter[str] = Counter()
    for tokens in results:
        if tokens:
            last_tag[tokens[-1].tag] += 1
            last_form[f"{tokens[-1].form}/{tokens[-1].tag}"] += 1
    for tag, cnt in last_tag.most_common():
        print(f"  {tag:<6s}  {cnt}")

    print("\n  마지막 토큰 (form/tag) top 20:")
    for form, cnt in last_form.most_common(20):
        print(f"  {form:<28s}  {cnt}")

    print("\n[STEP 5] 어말 (tail-3) 누적 패턴 — Stage 2 룰 baseline")
    tail3: Counter[str] = Counter()
    for tokens in results:
        if len(tokens) >= 3:
            key = " + ".join(f"{t.form}/{t.tag}" for t in tokens[-3:])
            tail3[key] += 1
    print("  Top 30 tail-3 patterns:")
    for pat, cnt in tail3.most_common(30):
        print(f"  [{cnt:>3d}] {pat}")

    print("\n" + "=" * 72)
    print("✓ Sample 100 분포 출력 완료. 결과를 Track_A_log에 기록.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
