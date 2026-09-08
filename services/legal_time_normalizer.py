"""services/legal_time_normalizer.py

WO-SHARED-LEGAL-TIME-NORMALIZER-V1-001 / STEP 4B-4A (+PATCH-1).

official obligations_raw 의 법적 시간 원문(obligation_detail.when / enrichment.inspection_cycle)을
tai-api 공용 **deterministic** module 에서 구조화한다.

- DERIVED HELPER (LEG SoT 아님). LEG 원문이 항상 우선. Check Layer/DB/LEG 무변경.
- PURE: DB/network/LLM/filesystem/global mutable state/input mutation = 0.
- 명시 패턴에만 해상(full-match). 애매/복합문이면 RAW_ONLY.
- PATCH-1: source_text = **입력 원문 EXACT**(trim 안 함). 판별은 strip 한 별도 변수(m)로만.
  CONTINUOUS/IMMEDIATE 는 "상시"/"즉시" 또는 "상시(...)"/"즉시(...)" 만(startswith 제거).
  WITHIN 은 search 제거·full-match 만.
- 어느 consumer(SaaS/PAID Excel/FREE)에도 종속되지 않는다. 이 STEP 에서 consumer 연결 0.

출력(v1): { "version":"v1", "timing":{...}?, "cycle":{...}? }
  timing ← obligation_detail.when · cycle ← enrichment.inspection_cycle (합치지 않음).
  node: source_text(원문 EXACT, 필수) · status(NORMALIZED|RAW_ONLY) · (해상 시) type/basis_text/value/unit/operator.
  absent ≠ null ≠ 0 — 없는 값은 key 자체를 만들지 않는다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

VERSION = "v1"

# ── canonical domains ──
UNIT_DAY, UNIT_WEEK, UNIT_MONTH = "DAY", "WEEK", "MONTH"
UNIT_QUARTER, UNIT_HALF_YEAR, UNIT_YEAR = "QUARTER", "HALF_YEAR", "YEAR"

_UNIT_WORD = {
    "일": UNIT_DAY, "주": UNIT_WEEK, "개월": UNIT_MONTH, "달": UNIT_MONTH,
    "분기": UNIT_QUARTER, "반기": UNIT_HALF_YEAR, "년": UNIT_YEAR,
}
_EVERY_WORD = {
    "매일": (1, UNIT_DAY), "매주": (1, UNIT_WEEK), "매월": (1, UNIT_MONTH),
    "매분기": (1, UNIT_QUARTER), "매반기": (1, UNIT_HALF_YEAR), "매년": (1, UNIT_YEAR),
}
_PERIOD_ONCE_WORD = {
    "일": UNIT_DAY, "주": UNIT_WEEK, "월": UNIT_MONTH,
    "분기": UNIT_QUARTER, "반기": UNIT_HALF_YEAR, "연": UNIT_YEAR,
}

# ── 명시 패턴 (전부 full-match; 애매/복합문은 매치 안 됨 → RAW_ONLY) ──
_RE_EVERY_NUM = re.compile(r"^(\d+)\s*(일|주|개월|달|분기|반기|년)\s*마다$")
_RE_YEAR_ONCE = re.compile(r"^1\s*년에\s*(?:1|한)\s*(?:회|번)$")
_RE_PERIOD_ONCE = re.compile(r"^(일|주|월|분기|반기|연)\s*1\s*회$")
# WITHIN: full-match 만 (기준 후/부터 + N단위 이내, 또는 기준 없는 N단위 이내)
_RE_WITHIN_BASIS = re.compile(
    r"^(?P<basis>.+?)\s*(?:후|부터)\s*(?P<v>\d+)\s*(?P<u>일|주|개월|달|분기|반기|년)\s*이내$"
)
_RE_WITHIN_BARE = re.compile(r"^(?P<v>\d+)\s*(?P<u>일|주|개월|달|분기|반기|년)\s*이내$")
# BEFORE: 기준 + 전, 뒤에 괄호주석만 허용 (그 외 접속/추가절 있으면 매치 안 됨)
_RE_BEFORE = re.compile(r"^(?P<basis>.+?)\s*전(?:\s*\([^()]*\))?$")
# CONTINUOUS/IMMEDIATE: 정확히 그 단어, 또는 그 단어 + 괄호주석만
_RE_CONTINUOUS = re.compile(r"^상시(?:\s*\([^()]*\))?$")
_RE_IMMEDIATE = re.compile(r"^즉시(?:\s*\([^()]*\))?$")
_RE_ONE_TIME = re.compile(r"^최초\s*(?:1|한)\s*(?:회|번)$")


def _raw_input(value: Any) -> Optional[str]:
    """비어있지 않은(공백 제외 내용 존재) 문자열 원문을 그대로 반환. 그 외 None (fail-close).

    반환값은 **입력 원문 EXACT**(trim 안 함). 판별용 strip 은 호출부에서 별도 수행.
    """
    if not isinstance(value, str):
        return None
    if not value.strip():
        return None
    return value


def _raw_only(source_text: str) -> Dict[str, Any]:
    return {"source_text": source_text, "status": "RAW_ONLY"}


def normalize_legal_time_text(text: Any) -> Optional[Dict[str, Any]]:
    """법적 시간 원문 1개 → 구조화 node (PURE, deterministic). 유효 원문 없으면 None.

    source_text = 입력 원문 EXACT. 판별은 strip 한 m 으로만. full-match 만 NORMALIZED.
    """
    source = _raw_input(text)
    if source is None:
        return None
    m = source.strip()  # 판별 전용 (source_text 에는 반영 안 함)

    # CONTINUOUS / IMMEDIATE (정확 일치 또는 괄호주석만)
    if _RE_CONTINUOUS.match(m):
        return {"source_text": source, "status": "NORMALIZED", "type": "CONTINUOUS"}
    if _RE_IMMEDIATE.match(m):
        return {"source_text": source, "status": "NORMALIZED", "type": "IMMEDIATE"}

    # ONE_TIME
    if _RE_ONE_TIME.match(m):
        return {"source_text": source, "status": "NORMALIZED", "type": "ONE_TIME"}

    # RECURRING
    mm = _RE_EVERY_NUM.match(m)
    if mm:
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": int(mm.group(1)), "unit": _UNIT_WORD[mm.group(2)], "operator": "EVERY"}
    if m in _EVERY_WORD:
        v, u = _EVERY_WORD[m]
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": v, "unit": u, "operator": "EVERY"}
    if _RE_YEAR_ONCE.match(m):
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": 1, "unit": UNIT_YEAR, "operator": "EVERY"}
    mm = _RE_PERIOD_ONCE.match(m)
    if mm:
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": 1, "unit": _PERIOD_ONCE_WORD[mm.group(1)], "operator": "EVERY"}

    # EVENT_DEADLINE — "이내" (full-match; 기준 후/부터 있으면 basis)
    mm = _RE_WITHIN_BASIS.match(m)
    if mm:
        node = {"source_text": source, "status": "NORMALIZED", "type": "EVENT_DEADLINE",
                "value": int(mm.group("v")), "unit": _UNIT_WORD[mm.group("u")], "operator": "WITHIN"}
        basis = mm.group("basis").strip()
        if basis:
            node["basis_text"] = basis
        return node
    mm = _RE_WITHIN_BARE.match(m)
    if mm:
        return {"source_text": source, "status": "NORMALIZED", "type": "EVENT_DEADLINE",
                "value": int(mm.group("v")), "unit": _UNIT_WORD[mm.group("u")], "operator": "WITHIN"}

    # EVENT_DEADLINE — "…전" (기준만, 숫자/단위 0)
    mm = _RE_BEFORE.match(m)
    if mm:
        basis = mm.group("basis").strip()
        node = {"source_text": source, "status": "NORMALIZED",
                "type": "EVENT_DEADLINE", "operator": "BEFORE"}
        if basis:
            node["basis_text"] = basis
        return node

    # 그 외 = RAW_ONLY (bare duration/정기적으로/수시/분기N시간/연2회/복합문…)
    return _raw_only(source)


def normalize_obligation_legal_time(raw_obligation: Any) -> Optional[Dict[str, Any]]:
    """official obligation → {version, timing?, cycle?} (PURE). when/cycle 둘 다 없으면 None.

    timing ← obligation_detail.when · cycle ← enrichment.inspection_cycle. 합치지 않음. 입력 mutation 0.
    """
    ob = raw_obligation if isinstance(raw_obligation, dict) else {}
    detail = ob.get("obligation_detail")
    enr = ob.get("enrichment")
    when_text = detail.get("when") if isinstance(detail, dict) else None
    cycle_text = enr.get("inspection_cycle") if isinstance(enr, dict) else None

    timing = normalize_legal_time_text(when_text)
    cycle = normalize_legal_time_text(cycle_text)
    if timing is None and cycle is None:
        return None

    out: Dict[str, Any] = {"version": VERSION}
    if timing is not None:
        out["timing"] = timing
    if cycle is not None:
        out["cycle"] = cycle
    return out


__all__ = ["VERSION", "normalize_legal_time_text", "normalize_obligation_legal_time"]
