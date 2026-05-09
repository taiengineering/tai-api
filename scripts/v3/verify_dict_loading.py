"""scripts/v3/verify_dict_loading.py — Track C v1.1 ENFORCEMENT 확장 자동 로드 검증.

실행: python3 scripts/v3/verify_dict_loading.py

Track C 누적 통보:
  v1.0 (2026-05-09): verified=TRUE 186건 (LAW_NAME 145 + AGENCY_NAME 26 + TECH_TERM 15)
  v1.1 (2026-05-09): verified=TRUE 464건 (LAW_NAME 423 + AGENCY_NAME 26 + TECH_TERM 15)
                     LAW_NAME 423 = LAW 본법 145 + ENFORCEMENT_DECREE 139 + ENFORCEMENT_RULE 139
                     다단어 LAW_NAME 344건 (수직 73%) — add_re_word 라우팅 부담 ↑

검증 항목 (5단계, 단계별 fail-fast):
  1. DB 사실 재확인 (총합 + term_type별 + 다단어 카운트)
  2. MorphemeEngine(supabase=sb) 자동 로드 → user_dict_size == 464
  3. 토큰화 sample 2종 (본법 + 시행령) 회귀 검증
     - "고압가스 안전관리법 제10조에 따라 등록한다." → "고압가스 안전관리법" / NNP
     - "고압가스 안전관리법 시행령 제5조에 따른다." → "고압가스 안전관리법 시행령" / NNP
  4. 다단어 LAW_NAME 344건 일괄 토큰화 → 모두 단일 NNP
  5. 성능 측정 (Track C v1.1 권장 — 정규식 컴파일 비용)
     - 인스턴스 생성 + 자동 로드 시간
     - 첫 토큰화 (warmup) vs warm 토큰화
     - 100회 평균 토큰화 시간

종료 코드:
  0: 모든 검증 통과 (성능 측정은 측정만 수행, fail X)
  1: DB 사실 불일치
  2: 자동 로드 카운트 불일치
  3: 다단어 토큰화 sample 실패 (둘 중 하나라도)
  4: 다단어 일괄 검증 실패
"""

from __future__ import annotations

import sys
from time import perf_counter

from db.supabase_client import get_supabase
from engine.morpheme import MorphemeEngine

# v1.1 기대값
EXPECTED_TOTAL = 464
EXPECTED_BY_TYPE = {
    "LAW_NAME": 423,
    "AGENCY_NAME": 26,
    "TECH_TERM": 15,
}
EXPECTED_MULTIWORD_LAWS = 344

# 토큰화 sample 2종 (회귀 + 신규)
TOKENIZE_SAMPLES: list[tuple[str, str]] = [
    # (입력, 기대 첫 토큰 form)
    ("고압가스 안전관리법 제10조에 따라 등록한다.", "고압가스 안전관리법"),
    ("고압가스 안전관리법 시행령 제5조에 따른다.", "고압가스 안전관리법 시행령"),
]
EXPECTED_FIRST_TAG = "NNP"


def step_1_db_facts(sb) -> bool:
    print("\n[1] DB 사실 재확인 (v1.1 기대값)")
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

    # 다단어 LAW_NAME (전체 — 본법 + 시행령 + 시행규칙)
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


def step_2_auto_load(sb) -> tuple[bool, MorphemeEngine | None, float]:
    print("\n[2] MorphemeEngine 자동 로드 (시간 측정)")
    t0 = perf_counter()
    engine = MorphemeEngine(supabase=sb)
    elapsed = perf_counter() - t0
    actual = engine.user_dict_size
    ok = actual == EXPECTED_TOTAL
    print(f"  {'✅' if ok else '❌'} user_dict_size = {actual} (기대 {EXPECTED_TOTAL})")
    print(f"  ⏱  인스턴스 생성 + 자동 로드: {elapsed:.3f}s")
    return ok, (engine if ok else None), elapsed


def step_3_tokenize_samples(engine: MorphemeEngine) -> bool:
    print("\n[3] 토큰화 sample 회귀 검증 (본법 + 시행령)")
    all_ok = True
    for text, expected_first in TOKENIZE_SAMPLES:
        tokens, _ = engine.analyze(text)
        if not tokens:
            print(f"  ❌ 빈 토큰화: {text!r}")
            all_ok = False
            continue
        first = tokens[0]
        print(f"  입력: {text!r}")
        print(f"    첫 토큰: {first.form!r} / {first.tag}")
        print(f"    기대:    {expected_first!r} / {EXPECTED_FIRST_TAG}")
        if first.form == expected_first and first.tag == EXPECTED_FIRST_TAG:
            print("    ✅ 통과")
        else:
            print("    ❌ 실패")
            print(f"    전체 토큰 (앞 8개): {[f'{t.form}/{t.tag}' for t in tokens[:8]]}")
            all_ok = False
    return all_ok


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
    t0 = perf_counter()
    for term in terms:
        tokens, _ = engine.analyze(term)
        if not tokens:
            failures.append((term, "빈 토큰화"))
            continue
        if len(tokens) != 1:
            tokens_str = "/".join(f"{t.form}_{t.tag}" for t in tokens)
            failures.append((term, f"{len(tokens)}개 토큰: {tokens_str}"))
            continue
        if tokens[0].form != term or tokens[0].tag != "NNP":
            failures.append((term, f"{tokens[0].form!r} / {tokens[0].tag}"))
    bulk_elapsed = perf_counter() - t0

    if not failures:
        avg_ms = (bulk_elapsed / len(terms)) * 1000
        print(f"  ✅ {len(terms)}건 모두 단일 NNP 토큰화 성공")
        print(f"  ⏱  일괄 토큰화: {bulk_elapsed:.2f}s (평균 {avg_ms:.2f}ms/건)")
        return True

    print(f"  ❌ {len(failures)} / {len(terms)}건 실패")
    for term, reason in failures[:10]:
        print(f"    - {term!r}: {reason}")
    if len(failures) > 10:
        print(f"    ... + {len(failures) - 10}건")
    return False


def step_5_performance(engine: MorphemeEngine, init_elapsed: float) -> bool:
    """Track C v1.1 권장: 정규식 컴파일 비용 측정.

    측정만 수행. 임계값 위반은 fail로 처리하지 않음 (회신 양식 제공용).
    """
    print("\n[5] 성능 측정 (Track C v1.1 권장)")

    # warmup (정규식 컴파일 첫 트리거 가능)
    t0 = perf_counter()
    engine.tokenize("고압가스 안전관리법 시행령 제5조에 따라 처리한다.")
    warmup_ms = (perf_counter() - t0) * 1000

    # warm (반복)
    t0 = perf_counter()
    engine.tokenize("산업안전보건법 시행규칙 제38조의2 별표 1.")
    warm_ms = (perf_counter() - t0) * 1000

    # 100회 평균 (안정 평균)
    samples = [
        "고압가스 안전관리법 시행령 제5조에 따른다.",
        "산업안전보건법 제38조 제1항에 따른다.",
        "건축물의 분양에 관한 법률 시행규칙 제3조의2.",
    ]
    t0 = perf_counter()
    for i in range(100):
        engine.tokenize(samples[i % len(samples)])
    avg_100_ms = ((perf_counter() - t0) / 100) * 1000

    print(f"  인스턴스 생성 + 자동 로드: {init_elapsed:.3f}s ({EXPECTED_TOTAL}건)")
    print(f"  첫 토큰화 (warmup):       {warmup_ms:.2f}ms")
    print(f"  두 번째 토큰화 (warm):    {warm_ms:.2f}ms")
    print(f"  100회 평균 토큰화:        {avg_100_ms:.2f}ms")
    print()
    print("  분석:")
    print(f"  - 정규식 컴파일 비용은 인스턴스 생성 시점에 응집되는지(eager)")
    print(f"    또는 첫 토큰화 시점에 응집되는지(lazy) 확인:")
    if warmup_ms > avg_100_ms * 3:
        print(f"    → LAZY 추정 (warmup {warmup_ms:.1f}ms >> warm 평균 {avg_100_ms:.2f}ms)")
    else:
        print(f"    → EAGER 추정 (warmup ≈ warm 평균)")
    print(f"  - 인스턴스 생성 비용 {init_elapsed:.2f}s가 Worker 부팅 시 1회 발생")
    print(f"  - warm 평균 {avg_100_ms:.2f}ms/건은 Stage 1/2 batch 작업 시 직접 영향")
    return True


def main() -> int:
    print("=" * 72)
    print("Track C v1.1 ENFORCEMENT 확장 자동 로드 검증 (2026-05-09)")
    print("=" * 72)

    sb = get_supabase()

    if not step_1_db_facts(sb):
        return 1

    ok, engine, init_elapsed = step_2_auto_load(sb)
    if not ok or engine is None:
        return 2

    if not step_3_tokenize_samples(engine):
        return 3

    if not step_4_multiword_bulk(sb, engine):
        return 4

    # 성능 측정은 fail 처리 X — 측정만
    step_5_performance(engine, init_elapsed)

    print("\n" + "=" * 72)
    print("✅ Track C v1.1 자동 로드 검증 통과 (4/4 단계 + 성능 측정)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
