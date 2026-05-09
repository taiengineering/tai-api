"""scripts/v3/verify_dict_loading.py — Track C v1 시드 자동 로드 검증.

실행: python3 scripts/v3/verify_dict_loading.py

Track C 통보 (2026-05-09):
  verified=TRUE 186건 (LAW_NAME 145 + AGENCY_NAME 26 + TECH_TERM 15)
  다단어 LAW_NAME 70건 (term LIKE '% %') — add_re_word 자동 분기 대상

검증 항목 (4단계, 단계별 fail-fast):
  1. DB 사실 재확인 (총합 + term_type별 + 다단어 카운트)
  2. MorphemeEngine(supabase=sb) 자동 로드 → user_dict_size == 186
  3. 토큰화 sample: "고압가스 안전관리법 제10조에 따라 등록한다."
     → 첫 토큰 "고압가스 안전관리법" / NNP
  4. 다단어 LAW_NAME 70건 일괄 토큰화 → 모두 단일 토큰

종료 코드:
  0: 모든 검증 통과
  1: DB 사실 불일치
  2: 자동 로드 카운트 불일치
  3: 다단어 토큰화 sample 실패
  4: 다단어 일괄 검증 실패
"""

from __future__ import annotations

import sys

from db.supabase_client import get_supabase
from engine.morpheme import MorphemeEngine

EXPECTED_TOTAL = 186
EXPECTED_BY_TYPE = {
    "LAW_NAME": 145,
    "AGENCY_NAME": 26,
    "TECH_TERM": 15,
}
EXPECTED_MULTIWORD_LAWS = 70

SAMPLE_TEXT = "고압가스 안전관리법 제10조에 따라 등록한다."
EXPECTED_FIRST_TOKEN = "고압가스 안전관리법"
EXPECTED_FIRST_TAG = "NNP"


def step_1_db_facts(sb) -> bool:
    print("\n[1] DB 사실 재확인")
    # 총합
    res = (
        sb.table("dict_legal_terms")
        .select("id", count="exact")
        .eq("verified", True)
        .execute()
    )
    total = res.count or 0
    ok = total == EXPECTED_TOTAL
    print(f"  {'✅' if ok else '❌'} verified=TRUE 총 {total}건 (기대 {EXPECTED_TOTAL})")
    if not ok:
        return False

    # term_type별
    print("  term_type별:")
    for tt, expected in EXPECTED_BY_TYPE.items():
        r = (
            sb.table("dict_legal_terms")
            .select("id", count="exact")
            .eq("verified", True)
            .eq("term_type", tt)
            .execute()
        )
        actual = r.count or 0
        mark = "✅" if actual == expected else "❌"
        print(f"    {mark} {tt}: {actual} / 기대 {expected}")
        if actual != expected:
            return False

    # 다단어 LAW_NAME
    r = (
        sb.table("dict_legal_terms")
        .select("term")
        .eq("verified", True)
        .eq("term_type", "LAW_NAME")
        .like("term", "% %")
        .execute()
    )
    multiword = r.data or []
    ok = len(multiword) == EXPECTED_MULTIWORD_LAWS
    print(f"  {'✅' if ok else '❌'} 다단어 LAW_NAME {len(multiword)}건 (기대 {EXPECTED_MULTIWORD_LAWS})")
    return ok


def step_2_auto_load(sb) -> tuple[bool, MorphemeEngine | None]:
    print("\n[2] MorphemeEngine 자동 로드")
    engine = MorphemeEngine(supabase=sb)
    actual = engine.user_dict_size
    ok = actual == EXPECTED_TOTAL
    print(f"  {'✅' if ok else '❌'} user_dict_size = {actual} (기대 {EXPECTED_TOTAL})")
    return ok, engine if ok else None


def step_3_tokenize_sample(engine: MorphemeEngine) -> bool:
    print("\n[3] 다단어 토큰화 sample")
    print(f"  입력: {SAMPLE_TEXT!r}")
    tokens, _ = engine.analyze(SAMPLE_TEXT)
    if not tokens:
        print("  ❌ 토큰화 실패 (빈 결과)")
        return False

    first = tokens[0]
    print(f"  첫 토큰: {first.form!r} / {first.tag}")
    print(f"  기대:    {EXPECTED_FIRST_TOKEN!r} / {EXPECTED_FIRST_TAG}")

    if first.form == EXPECTED_FIRST_TOKEN and first.tag == EXPECTED_FIRST_TAG:
        print("  ✅ add_re_word 자동 분기 동작 확인")
        return True
    else:
        print("  ❌ 다단어 토큰화 실패")
        print(f"  전체 토큰 (앞 10개): {[f'{t.form}/{t.tag}' for t in tokens[:10]]}")
        return False


def step_4_multiword_bulk(sb, engine: MorphemeEngine) -> bool:
    print(f"\n[4] 다단어 LAW_NAME {EXPECTED_MULTIWORD_LAWS}건 일괄 토큰화 검증")
    r = (
        sb.table("dict_legal_terms")
        .select("term")
        .eq("verified", True)
        .eq("term_type", "LAW_NAME")
        .like("term", "% %")
        .execute()
    )
    terms = [row["term"] for row in (r.data or [])]
    if len(terms) != EXPECTED_MULTIWORD_LAWS:
        print(f"  ❌ DB 카운트 불일치: {len(terms)} != {EXPECTED_MULTIWORD_LAWS}")
        return False

    failures: list[tuple[str, str]] = []
    for term in terms:
        tokens, _ = engine.analyze(term)
        if not tokens:
            failures.append((term, "빈 토큰화"))
            continue
        # term 그 자체를 입력했을 때 단일 토큰으로 묶이는지
        if len(tokens) != 1:
            tokens_str = "/".join(f"{t.form}_{t.tag}" for t in tokens)
            failures.append((term, f"{len(tokens)}개 토큰: {tokens_str}"))
            continue
        if tokens[0].form != term or tokens[0].tag != "NNP":
            failures.append((term, f"{tokens[0].form!r} / {tokens[0].tag}"))

    if not failures:
        print(f"  ✅ {len(terms)}건 모두 단일 NNP 토큰화 성공")
        return True

    print(f"  ❌ {len(failures)} / {len(terms)}건 실패")
    for term, reason in failures[:10]:
        print(f"    - {term!r}: {reason}")
    if len(failures) > 10:
        print(f"    ... + {len(failures) - 10}건")
    return False


def main() -> int:
    print("=" * 70)
    print("Track C v1 시드 자동 로드 검증 (2026-05-09)")
    print("=" * 70)

    sb = get_supabase()

    if not step_1_db_facts(sb):
        return 1

    ok, engine = step_2_auto_load(sb)
    if not ok or engine is None:
        return 2

    if not step_3_tokenize_sample(engine):
        return 3

    if not step_4_multiword_bulk(sb, engine):
        return 4

    print("\n" + "=" * 70)
    print("✅ Track C 자동 로드 검증 통과 (4/4 단계)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
