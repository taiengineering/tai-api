"""FREE 결과페이지 '진단에 사용된 정보' 입력 스냅샷 projection.

WO-FREE-RESULT-INPUT-SUMMARY-IMPL-001 (OPTION A, READ-ONLY / additive).

저장 정본 = anonymous_diagnosis_results.input_data.raw_structured_input.form_data
공개 기준 = (active FREE catalog field_code) INTERSECT (stored form_data leaf)   # WO 18 allowlist
- raw passthrough 금지(WO 5): facility/process/equipment container 미노출.
- top-level form_data.<code> 우선, 없으면 form_data.facility.<code> (WO 4/17 dedup).
- catalog 조회 실패/timeout/0행 -> {} (fail closed, WO 8). 예외를 밖으로 던지지 않는다.
- 값 생성 없음. run_diagnosis / floor_area writer / engine 무관(WO 3 NON-SCOPE).
- /diagnosis/fields 와 동일한 sector 정규화/카탈로그 계약 재사용(WO 6/7):
  normalize_sector_db() + sector_codes_for_query().
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# form_data 내부 컨테이너 - allowlist field_code 가 아니며 절대 노출하지 않는다.
_CONTAINER_KEYS = frozenset({"facility", "process", "equipment"})


def _free_field_codes(supabase, sector: str) -> List[str]:
    """현재 active FREE catalog 의 field_code 목록.

    /diagnosis/fields 와 동일 계약(normalize_sector_db + sector_codes_for_query,
    tier=FREE, is_active=true)을 재사용한다. 실패/0행 시 빈 리스트(fail closed).
    """
    try:
        from constants.sectors import sector_codes_for_query
        from services.legal_rules import normalize_sector_db

        norm = normalize_sector_db(sector)
        res = (
            supabase.table("diagnosis_input_fields")
            .select("field_code")
            .in_("sector", list(sector_codes_for_query(norm)))
            .eq("tier", "FREE")
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[result-input-projection] FREE catalog read failed sector=%s: %s", sector, e)
        return []

    codes: List[str] = []
    seen: set = set()
    for row in (getattr(res, "data", None) or []):
        code = (row.get("field_code") or "").strip()
        if code and code not in _CONTAINER_KEYS and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def project_free_input_snapshot(supabase, sector: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """저장 form_data 에서 FREE allowlist INTERSECT leaf 만 {field_code: value} 로 투영.

    - 값이 없거나 None 인 field_code 는 제외한다.
    - false / 0 은 유효 값으로 보존한다(WO 16 표시 규칙은 프론트가 적용; API 는 값만 운반).
    - 항상 dict 를 반환한다. 어떤 실패에서도 raise 하지 않고 {} 를 반환한다(fail closed).
    """
    try:
        idata = input_data if isinstance(input_data, dict) else {}
        rsi = idata.get("raw_structured_input")
        fd = rsi.get("form_data") if isinstance(rsi, dict) else None
        if not isinstance(fd, dict):
            return {}

        facility = fd.get("facility")
        facility = facility if isinstance(facility, dict) else {}

        codes = _free_field_codes(supabase, sector)
        if not codes:
            return {}  # WO 8 fail closed: catalog 실패/0행 -> 확장 미노출

        out: Dict[str, Any] = {}
        for code in codes:
            if code in _CONTAINER_KEYS:
                continue  # 방어적: container 는 절대 싣지 않는다(WO 5)
            if code in fd:
                val = fd.get(code)
            elif code in facility:
                val = facility.get(code)
            else:
                continue
            if val is None:
                continue
            out[code] = val
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("[result-input-projection] projection failed sector=%s: %s", sector, e)
        return {}
