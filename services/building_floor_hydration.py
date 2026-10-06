"""WO-LFR-OBJ-H03-FAST-01 — 11층 이상 바닥면적 합계 도출 서비스.

SOURCE: BldRgstHubService/getBrFlrOulnInfo
ENTITY: exact main-building mgmBldrgstPk
DERIVATION:
  지상층(flrGbCd=="20") + flrNo >= 11 + areaExctYn 미제외 rows의 area 합계.
  Decimal 내부 누적, float 반환.

계약 불변식:
  0 != ABSENT (0 valid when qualifying rows all area=0)
  missing != false (absent data → LEAVE_UNRESOLVED)
  pagination must be complete (partial → LEAVE_UNRESOLVED)
  parcel-wide aggregation prohibited (exact mgmBldrgstPk filter)
  direct user input workaround prohibited (question_eligible=false)
"""
from __future__ import annotations

import json as _json
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from services.building_register_hydration import parse_bdmgtsn
from services.kr_public_api import kr_get

_BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
_FLOOR_ENDPOINT = "getBrFlrOulnInfo"
_PAGE_SIZE = 100

_EXCLUDE_FLAGS = {1, "1", "Y"}
_INCLUDE_FLAGS = {0, "0", "N", None, ""}


def _fetch_all_floor_rows(bdmgtsn: str) -> Dict[str, Any]:
    """bdmgtsn에서 getBrFlrOulnInfo 전체 페이지를 수집.

    반환:
      {"ok": True,  "rows": [...], "page_count": int}
      {"ok": False, "reason": str}
    """
    p = parse_bdmgtsn(bdmgtsn)
    if not p:
        return {"ok": False, "reason": "invalid_bdmgtsn"}

    building_key = os.environ.get("BUILDING_API_KEY", "")
    base_params = {
        "serviceKey": building_key,
        "sigunguCd":  p["sigunguCd"],
        "bjdongCd":   p["bjdongCd"],
        "platGbCd":   p["mountain"],
        "bun":        p["bun"],
        "ji":         p["ji"],
        "numOfRows":  _PAGE_SIZE,
        "_type":      "json",
    }

    all_rows: List[dict] = []
    expected_total: Optional[int] = None
    page = 1

    while True:
        params = {**base_params, "pageNo": page}
        try:
            status, text = kr_get(
                f"{_BUILDING_BASE}/{_FLOOR_ENDPOINT}",
                params=params,
                timeout=25,
            )
        except Exception:
            return {"ok": False, "reason": "page_failure"}

        if status != 200 or not text:
            return {"ok": False, "reason": "page_failure"}

        try:
            data = _json.loads(text)
        except Exception:
            return {"ok": False, "reason": "page_failure"}

        body = (data.get("response") or {}).get("body") or {}
        try:
            total = int(body.get("totalCount", 0))
        except (TypeError, ValueError):
            return {"ok": False, "reason": "page_failure"}

        if expected_total is None:
            expected_total = total

        if total == 0:
            return {"ok": True, "rows": [], "page_count": 1}

        items_obj = body.get("items") or {}
        raw = items_obj.get("item") if isinstance(items_obj, dict) else None
        if raw is None:
            # totalCount > 0 but no items → partial result
            return {"ok": False, "reason": "api_partial_result"}

        page_rows = raw if isinstance(raw, list) else [raw]
        all_rows.extend(page_rows)

        if len(all_rows) >= expected_total:
            break
        page += 1

    if len(all_rows) < (expected_total or 0):
        return {"ok": False, "reason": "api_partial_result"}

    return {"ok": True, "rows": all_rows, "page_count": page}


def _classify_floor_type(row: dict) -> str:
    """floor type 분류.
    반환: "ground" | "not_ground" | "conflict"
    """
    cd = str(row.get("flrGbCd") or "").strip()
    nm = str(row.get("flrGbCdNm") or "").strip()

    if cd:
        is_ground_by_cd = (cd == "20")
        if nm:
            is_ground_by_nm = (nm == "지상")
            if is_ground_by_cd != is_ground_by_nm:
                return "conflict"
        return "ground" if is_ground_by_cd else "not_ground"
    if nm:
        if nm == "지상":
            return "ground"
        return "not_ground"
    return "not_ground"


def _parse_floor_no(row: dict) -> Optional[int]:
    """flrNo → int. NULL/blank/non-numeric → None."""
    v = row.get("flrNo")
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _parse_area_exclusion(row: dict) -> Optional[bool]:
    """areaExctYn → True(exclude) / False(include) / None(unexpected).
    None = unexpected value → DERIVATION FAILURE."""
    v = row.get("areaExctYn")
    if v in _EXCLUDE_FLAGS:
        return True
    if v in _INCLUDE_FLAGS:
        return False
    return None


def _parse_area(row: dict) -> Optional[Decimal]:
    """area → Decimal. NULL/blank/non-numeric/negative → None."""
    v = row.get("area")
    if v is None or str(v).strip() == "":
        return None
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        return None
    if d < 0:
        return None
    return d


def resolve_floor_area_sum_11f_plus(
    bdmgtsn: str,
    main_building_pk: Optional[str],
) -> Dict[str, Any]:
    """11층 이상 지상층 바닥면적 합계를 도출한다.

    반환 (성공):
      {"resolved": True, "value": float, "main_building_pk": str,
       "source_row_count": int, "qualifying_row_count": int, "page_count": int}
    반환 (실패):
      {"resolved": False, "reason": str}
    """
    if not main_building_pk:
        return {"resolved": False, "reason": "main_building_not_resolved"}

    fetch_result = _fetch_all_floor_rows(bdmgtsn)
    if not fetch_result.get("ok"):
        reason = fetch_result.get("reason", "api_no_result")
        return {"resolved": False, "reason": reason}

    all_rows: List[dict] = fetch_result["rows"]
    page_count: int = fetch_result.get("page_count", 1)

    if not all_rows:
        return {"resolved": False, "reason": "api_no_result"}

    # Filter to exact main building
    entity_rows = [r for r in all_rows if str(r.get("mgmBldrgstPk") or "").strip() == main_building_pk]
    if not entity_rows:
        return {"resolved": False, "reason": "entity_rows_absent"}

    accumulated = Decimal(0)
    qualifying_count = 0

    for row in entity_rows:
        floor_type = _classify_floor_type(row)

        if floor_type == "conflict":
            return {"resolved": False, "reason": "invalid_floor_type"}
        if floor_type == "not_ground":
            continue

        # ground row: check floor number
        flr_no = _parse_floor_no(row)
        if flr_no is None:
            return {"resolved": False, "reason": "invalid_floor_no"}
        if flr_no < 11:
            continue

        # qualifying row (ground + flrNo >= 11): check exclusion flag
        excl = _parse_area_exclusion(row)
        if excl is None:
            return {"resolved": False, "reason": "invalid_area_exclusion_flag"}
        if excl:
            continue

        # included qualifying row: check area
        area = _parse_area(row)
        if area is None:
            return {"resolved": False, "reason": "invalid_area"}

        accumulated += area
        qualifying_count += 1

    if qualifying_count == 0:
        return {"resolved": False, "reason": "no_qualifying_rows"}

    return {
        "resolved": True,
        "value": float(accumulated),
        "main_building_pk": main_building_pk,
        "source_row_count": len(entity_rows),
        "qualifying_row_count": qualifying_count,
        "page_count": page_count,
    }
