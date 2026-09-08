"""services/legal_time_normalizer.py

WO-SHARED-LEGAL-TIME-NORMALIZER-V1-001 / STEP 4B-4A.

official obligations_raw 의 법적 시간 원문(obligation_detail.when / enrichment.inspection_cycle)을
tai-api 공용 **deterministic** module 에서 구조화한다.

- DERIVED HELPER (LEG SoT 아님). LEG 원문이 항상 우선. Check Layer/DB/LEG 무변경.
- PURE: DB/network/LLM/filesystem/global mutable state/input mutation = 0.
- 명시 패턴에만 해상. 애매하면 RAW_ONLY (source_text 원문 보존).
- 어느 consumer(SaaS/PAID Excel/FREE)에도 종속되지 않는다. 이 STEP 에서 consumer 연결 0.

출력(v1):
    { "version":"v1", "timing":{...}?, "cycle":{...}? }
  timing ← obligation_detail.when · cycle ← enrichment.inspection_cycle (둘을 합치지 않음).
  각 node: source_text(원문 EXACT, 필수) · status(NORMALIZED|RAW_ONLY) · (해상 시) type/basis_text/value/unit/operator.
  absent ≠ null ≠ 0 — 없는 값은 key 자체를 만들지 않는다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

VERSION = "v1"

# ── canonical domains ──
UNIT_DAY, UNIT_WEEK, UNIT_MONTH = "DAY", "WEEK", "MONTH"
UNIT_QUARTER, UNIT_HALF_YEAR, UNIT_YEAR = "QUARTER", "HALF_YEAR", "YEAR"

# 원문 단위 표기 → canonical (명시 패턴에서만 사용)
_UNIT_WORD = {
    "일": UNIT_DAY, "주": UNIT_WEEK, "개월": UNIT_MONTH, "달": UNIT_MONTH,
    "분기": UNIT_QUARTER, "반기": UNIT_HALF_YEAR, "년": UNIT_YEAR,
}
# "매X" / "X 1회" 형태의 단위어 → (value, unit)
_EVERY_WORD = {
    "매일": (1, UNIT_DAY), "매주": (1, UNIT_WEEK), "매월": (1, UNIT_MONTH),
    "매분기": (1, UNIT_QUARTER), "매반기": (1, UNIT_HALF_YEAR), "매년": (1, UNIT_YEAR),
}
_PERIOD_ONCE_WORD = {  # "일 1회" 류: 단위어 → unit
    "일": UNIT_DAY, "주": UNIT_WEEK, "월": UNIT_MONTH,
    "분기": UNIT_QUARTER, "반기": UNIT_HALF_YEAR, "연": UNIT_YEAR,
}

# ── 명시 패턴 (deterministic; 애매하면 매치 안 됨 → RAW_ONLY) ──
_RE_EVERY_NUM = re.compile(r"^(\d+)\s*(일|주|개월|달|분기|반기|년)\s*마다$")           # "15일마다"
_RE_YEAR_ONCE = re.compile(r"^1\s*년에\s*(?:1|한)\s*(?:회|번)$")                       # "1년에 1회/한번/한 번"
_RE_PERIOD_ONCE = re.compile(r"^(일|주|월|분기|반기|연)\s*1\s*회$")                     # "월 1회"
_RE_WITHIN_NUM = re.compile(r"(?:^|\s)(\d+)\s*(일|주|개월|달|분기|반기|년)\s*이내$")     # "...14일 이내"
_RE_BASIS_WITHIN = re.compile(r"^(?P<basis>.+?)\s*(?:후|부터)\s*\d+\s*(?:일|주|개월|달|분기|반기|년)\s*이내$")
_RE_BEFORE = re.compile(r"^(?P<basis>.+?)\s*전(?:\(.*\))?$")                            # "작업시작 전(...)"

_CONTINUOUS_PREFIX = "상시"
_IMMEDIATE_PREFIX = "즉시"
_RE_ONE_TIME = re.compile(r"^최초\s*(?:1|한)\s*(?:회|번)$")


def _text(value: Any) -> Optional[str]:
    """유효 문자열 원문(공백 trim 후 non-empty)만 반환. 그 외 None (fail-close)."""
    if not isinstance(value, str):
        return None
    t = value.strip()
    return t if t else None


def _raw_only(source_text: str) -> Dict[str, Any]:
    return {"source_text": source_text, "status": "RAW_ONLY"}


def normalize_legal_time_text(text: Any) -> Optional[Dict[str, Any]]:
    """법적 시간 원문 1개 → 구조화 node (PURE, deterministic). 유효 원문 없으면 None.

    명시 패턴에만 NORMALIZED, 애매하면 RAW_ONLY. source_text 는 원문(trim만) 그대로.
    """
    source = _text(text)
    if source is None:
        return None
    s = source  # 비교용(원문 그대로; 내부 whitespace 차이는 각 정규식이 \s* 로 흡수)

    # CONTINUOUS / IMMEDIATE (접두 일치)
    if s.startswith(_CONTINUOUS_PREFIX):
        return {"source_text": source, "status": "NORMALIZED", "type": "CONTINUOUS"}
    if s.startswith(_IMMEDIATE_PREFIX):
        return {"source_text": source, "status": "NORMALIZED", "type": "IMMEDIATE"}

    # ONE_TIME
    if _RE_ONE_TIME.match(s):
        return {"source_text": source, "status": "NORMALIZED", "type": "ONE_TIME"}

    # RECURRING — "N<unit>마다"
    m = _RE_EVERY_NUM.match(s)
    if m:
        return {
            "source_text": source, "status": "NORMALIZED", "type": "RECURRING",
            "value": int(m.group(1)), "unit": _UNIT_WORD[m.group(2)], "operator": "EVERY",
        }
    # RECURRING — "매X"
    if s in _EVERY_WORD:
        v, u = _EVERY_WORD[s]
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": v, "unit": u, "operator": "EVERY"}
    # RECURRING — "1년에 1회"
    if _RE_YEAR_ONCE.match(s):
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": 1, "unit": UNIT_YEAR, "operator": "EVERY"}
    # RECURRING — "<unit> 1회"
    m = _RE_PERIOD_ONCE.match(s)
    if m:
        return {"source_text": source, "status": "NORMALIZED", "type": "RECURRING",
                "value": 1, "unit": _PERIOD_ONCE_WORD[m.group(1)], "operator": "EVERY"}

    # EVENT_DEADLINE — "... 이내" (숫자+단위 명확)
    m = _RE_WITHIN_NUM.search(s)
    if m:
        node = {
            "source_text": source, "status": "NORMALIZED", "type": "EVENT_DEADLINE",
            "value": int(m.group(1)), "unit": _UNIT_WORD[m.group(2)], "operator": "WITHIN",
        }
        bm = _RE_BASIS_WITHIN.match(s)  # "선임사유 후 14일 이내" → basis
        if bm:
            basis = bm.group("basis").strip()
            if basis:
                node["basis_text"] = basis
        return node

    # EVENT_DEADLINE — "... 전" (기준 표현만, 숫자/단위 생성 0)
    m = _RE_BEFORE.match(s)
    if m:
        basis = m.group("basis").strip()
        node = {"source_text": source, "status": "NORMALIZED",
                "type": "EVENT_DEADLINE", "operator": "BEFORE"}
        if basis:
            node["basis_text"] = basis
        return node

    # 그 외(bare duration "1년", "정기적으로", "수시", "분기 3시간", "연 2회" 등) = RAW_ONLY
    return _raw_only(source)


def normalize_obligation_legal_time(raw_obligation: Any) -> Optional[Dict[str, Any]]:
    """official obligation → {version, timing?, cycle?} (PURE). when/cycle 둘 다 없으면 None.

    timing ← obligation_detail.when · cycle ← enrichment.inspection_cycle. 둘을 합치지 않음.
    입력 mutation 없음.
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
