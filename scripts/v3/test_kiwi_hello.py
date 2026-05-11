"""
TAI 법령엔진 v3.0 — Track A Phase 1 검증 스크립트
Kiwi 형태소 분석기 동작 확인 (Hello World).

실행 전 설치:
    pip install kiwipiepy>=0.22.0 kiwipiepy-model>=0.22.0

실행:
    python scripts/v3/test_kiwi_hello.py

목적:
  - Kiwi 정상 import + Kiwi() 인스턴스 생성 확인
  - 법령 어말 패턴 (하여야 한다 / 할 수 없다 / 처한다 / 할 수 있다 /
    말한다 / 정한다 / 적용하지 아니한다 / 할 것 / 다만, ...) 토큰화 결과 검토
  - v3.0 Stage 2 sub_type 분류 룰 작성을 위한 어말 형태소 패턴 확인

절대 원칙 (MASTER_HANDOFF §2):
  - LLM 사용 X — Kiwi 형태소 분석만 사용
  - 법령 보전 — 직접 인용 sample만 사용
"""

from __future__ import annotations

from kiwipiepy import Kiwi


# Stage 2 핵심 어말 패턴별 검증 sample (10 sub_type)
# MASTER_HANDOFF.md §5 25 sub_type 중 빈도 상위 10개
SAMPLES: list[tuple[str, str]] = [
    (
        "OBLIGATION_HEADER",
        "사업주는 근로자가 추락할 위험이 있는 장소에 안전대를 설치하여야 한다.",
    ),
    (
        "PROHIBITION_HEADER",
        "누구든지 정당한 사유 없이 안전보건교육을 거부할 수 없다.",
    ),
    (
        "PENALTY_HEADER",
        "제38조를 위반한 자는 7년 이하의 징역 또는 1억원 이하의 벌금에 처한다.",
    ),
    (
        "AUTHORITY_HEADER",
        "고용노동부장관은 필요한 경우 사업장에 출입하여 검사를 할 수 있다.",
    ),
    (
        "DEFINITION_HEADER",
        '이 법에서 "근로자"란 직업의 종류와 관계없이 임금을 목적으로 사업이나 사업장에 근로를 제공하는 자를 말한다.',
    ),
    (
        "DELEGATION_ACTIVE",
        "구체적인 안전조치 기준은 대통령령으로 정한다.",
    ),
    (
        "EXEMPTION_HEADER",
        "다음 각 호의 어느 하나에 해당하는 경우에는 이 법을 적용하지 아니한다.",
    ),
    (
        "OBLIGATION_DETAIL_ITEM",
        "안전난간을 설치할 것",
    ),
    (
        "PENALTY_VIOLATOR_ITEM",
        "제38조제1항을 위반하여 안전조치를 하지 아니한 자",
    ),
    (
        "EXCEPTION_CLAUSE",
        "다만, 작업의 성질상 안전대 사용이 곤란한 경우에는 그러하지 아니하다.",
    ),
]


def print_tokens(label: str, sentence: str, tokens: list) -> None:
    print(f"\n[{label}]")
    print(f"  원문: {sentence}")
    print("  형태소:")
    for tok in tokens:
        print(f"    - {tok.form:<10s}  {tok.tag:<8s}  pos={tok.start:>3d}  len={tok.len}")
    tail = tokens[-3:] if len(tokens) >= 3 else tokens
    tail_str = " + ".join(f"{t.form}/{t.tag}" for t in tail)
    print(f"  ── 어말 후보 (tail-3): {tail_str}")


def main() -> int:
    print("=" * 72)
    print("TAI 법령엔진 v3.0 — Track A Phase 1: Kiwi Hello World")
    print("=" * 72)

    print("\n[STEP 1] Kiwi 인스턴스 생성")
    kiwi = Kiwi()
    print(f"  ✓ Kiwi 객체 생성 성공: {type(kiwi).__name__}")

    print("\n[STEP 2] 어말 패턴별 토큰화 (10 sub_type 대표 sample)")
    for label, sentence in SAMPLES:
        tokens = kiwi.tokenize(sentence)
        print_tokens(label, sentence, tokens)

    print("\n" + "=" * 72)
    print("✓ Phase 1 동작 확인 완료")
    print("  다음: python scripts/v3/tokenize_sample_100.py 실행 → 100건 일괄 토큰화")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
