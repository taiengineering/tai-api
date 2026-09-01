"""services/factory_canonical_vocab_svc.py

WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP3B-IMPL — factory canonical code vocabulary 검증.

책임(정확히):
  FIELD_TO_CATEGORY               — Factory canonical array field → system_codes category
  load_active_codes(supabase)     — 4 category 의 is_active=true code set 로드(1회 read)
  validate_factory_canonical_codes(cleaned, supabase) — 제공된 array field 만 code 존재 검증

금지: Marketing diagnosis_input_fields 조회 / Marketing option 직접 비교 / assembler / LEG / diagnosis logic.
검증 SoT = system_codes ONLY.

NULL semantics:
  field 미제공/None → 검증 생략(미확인).
  []               → valid(명시적 없음).
  non-empty        → 모든 item 이 해당 category의 is_active code 에 존재해야 함(하나라도 없으면 422).
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from fastapi import HTTPException

# Factory canonical array field → system_codes category (Marketing SoT 아님)
FIELD_TO_CATEGORY: Dict[str, str] = {
    "business_activity_types":      "factory_business_activity",
    "hazardous_work_environments":  "factory_hazardous_environment",
    "building_composition_codes":   "factory_building_composition",
    "regulatory_designation_codes": "factory_regulatory_designation",
}


def load_active_codes(supabase) -> Dict[str, Set[str]]:
    """4 category 의 is_active=true code 집합을 한 번의 read 로 로드."""
    categories = list(FIELD_TO_CATEGORY.values())
    res = (
        supabase.table("system_codes")
        .select("category, code")
        .in_("category", categories)
        .eq("is_active", True)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    out: Dict[str, Set[str]] = {c: set() for c in categories}
    for r in rows:
        cat = r.get("category")
        code = r.get("code")
        if cat in out and code is not None:
            out[cat].add(code)
    return out


def validate_factory_canonical_codes(cleaned: Dict[str, Any], supabase) -> None:
    """cleaned(provided-only dict) 중 canonical array field 만 system_codes 로 검증.

    제공되지 않은 field 는 건너뜀. None → 생략. [] → 통과. non-empty → 전 item code 존재 필수.
    검증이 필요한 field 가 하나도 없으면 DB read 도 하지 않는다.
    """
    targets = {f: cleaned[f] for f in FIELD_TO_CATEGORY if f in cleaned}
    # 실제 검증이 필요한(non-None non-empty) field 만 추림
    need = {f: v for f, v in targets.items() if v is not None}
    if not need:
        return

    codes_by_cat = load_active_codes(supabase)
    for field, value in need.items():
        if value == []:
            continue
        category = FIELD_TO_CATEGORY[field]
        allowed = codes_by_cat.get(category) or set()
        bad = [x for x in value if x not in allowed]
        if bad:
            raise HTTPException(
                status_code=422,
                detail=f"'{field}' 에 허용되지 않은 코드: {bad}",
            )
