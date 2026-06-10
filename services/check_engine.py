"""Check Engine — 범용 역검증 엔진 (도메인 중립).

목적
====
어떤 엔진(법령엔진 등)의 '출력'이, 그 엔진이 사용한 '룰'과 일관되는지를
거꾸로 대조(역검증)하는 범용 메커니즘.

범용엔진의 4가지 특성을 지킨다:
  1) 역할만 있다       — 대조(매칭)만 수행한다.
  2) 값을 갖지 않는다   — sector/법령/도메인 상수를 하드코딩하지 않는다.
  3) 판단하지 않는다   — PASS/FAIL 같은 합격 판정을 내리지 않는다(사실만 반환).
  4) 데이터가 없다      — DB/테이블/저장구조를 모른다. 호출부가 계약 형식으로 넣어준다.

입력/출력은 '계약(contract)'으로 표준화된다. 호출하는 쪽(어댑터)이 자신의
도메인 데이터를 이 계약 형식으로 변환해 넣고, 결과(사실)를 받아 자기 식으로
해석(판정/표시)한다. 그래서 법령엔진뿐 아니라 다른 어떤 엔진에도 붙는다.

오염 금지
========
이 파일에는 sector, 법령, 진단, 테이블명 등 특정 도메인 용어가 들어가면 안 된다.
그런 변환·판단은 전부 '어댑터'(예: 법령엔진용 어댑터)에 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

# ── 판정값(verdict): 사실만. 합격/불합격이 아니다. ───────────────────────────
VERDICT_MATCH = "MATCH"        # expected가 item.values 안에 있음 (정합)
VERDICT_MISMATCH = "MISMATCH"  # item.values는 있는데 expected가 그 안에 없음 (모순)
VERDICT_NO_RULE = "NO_RULE"    # item.values가 비어있음 (대조할 룰이 없음 → 판단 보류)


@dataclass(frozen=True)
class CheckItem:
    """검사 대상 1건 (입력 계약).

    id     : 항목 식별자(무엇인지는 엔진이 모른다. 호출부가 의미 부여).
    values : 이 항목이 가진 분류값 목록(룰에서 온 값). 비어있으면 NO_RULE.
    """
    id: str
    values: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class CheckResult:
    """검사 결과 1건 (출력 계약). 사실만 담는다."""
    id: str
    verdict: str
    expected: str
    values: Sequence[str] = field(default_factory=tuple)


def _norm(v: Optional[str]) -> str:
    return (v or "").strip().upper()


def check_one(item: CheckItem, expected: str) -> CheckResult:
    """단건 대조. expected가 item.values 안에 있는지만 본다(사실 판정)."""
    exp = _norm(expected)
    vals = [_norm(x) for x in (item.values or []) if _norm(x)]
    if not vals:
        verdict = VERDICT_NO_RULE
    elif exp in vals:
        verdict = VERDICT_MATCH
    else:
        verdict = VERDICT_MISMATCH
    return CheckResult(id=item.id, verdict=verdict, expected=exp, values=tuple(vals))


def check(items: Iterable[CheckItem], expected: str) -> List[CheckResult]:
    """다건 대조. 같은 expected 기준으로 각 item을 대조한다.

    역검증 의미:
      - expected = '결과가 나온 기준값'(예: 진단에 쓰인 분류값)
      - item.values = '그 항목(법 등)이 룰상 허용하는 분류값들'
      - MATCH    : 이 항목은 그 기준에서 나올 수 있다(정합)
      - MISMATCH : 이 항목은 그 기준에서 나오면 안 되는데 나왔다(역방향 모순)
      - NO_RULE  : 룰이 없어 판단 불가(누락/오매핑 단정 안 함)
    """
    return [check_one(it, expected) for it in items]


def tally(results: Sequence[CheckResult]) -> Dict[str, int]:
    """verdict별 개수 집계(사실 요약). 합격 판정이 아니다."""
    out = {VERDICT_MATCH: 0, VERDICT_MISMATCH: 0, VERDICT_NO_RULE: 0}
    for r in results:
        out[r.verdict] = out.get(r.verdict, 0) + 1
    return out
