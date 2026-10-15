"""WO-LFR-OBJ-H01-FAST-01 — 건물대장 H01 온디맨드 수화 서비스.

단일 factory_id 에 대해 building_height / floor_count 를 건물대장 API에서 가져와
factories 테이블에 PATCH 한다. services 레이어에서 routers/building_register.py 의
fetch_all_building_data / build_factory_update 를 임포트하지 않고, 같은 API 경로를
직접 호출한다.

반환:
  {"updated": True,  "building_height": float|None, "floor_count": int|None}
  {"updated": False, "reason": str}
"""
from __future__ import annotations

import json as _json
import math
import os
from typing import Any, Dict, List, Optional

from services.kr_public_api import kr_get

_BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
_TITLE_ENDPOINT = "getBrTitleInfo"
_TITLE_PAGE_SIZE = 100
_MAX_TITLE_PAGES = 20  # 무한 반복 방지 상한


def _safe_int(v) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, float) and not v.is_integer():
        return None  # 소수 층수 절삭 금지
    try:
        result = int(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None
    if result is not None and result < 0:
        return None
    return result


def _safe_float(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    try:
        result = float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None
    if result is not None and (not math.isfinite(result) or result < 0):
        return None
    return result


def parse_bdmgtsn(bdmgtsn: str) -> Optional[Dict[str, str]]:
    """19자리 건물관리번호 파싱. 형식 불일치 시 None."""
    if not bdmgtsn or len(bdmgtsn) != 19:
        return None
    return {
        "sigunguCd": bdmgtsn[0:5],
        "bjdongCd":  bdmgtsn[5:10],
        "mountain":  bdmgtsn[10],
        "bun":       bdmgtsn[11:15],
        "ji":        bdmgtsn[15:19],
    }


def extract_h01_fields(
    title_items: list,
    existing_pk: Optional[str] = None,
) -> Dict[str, Any]:
    """표제부 리스트에서 H01 필드를 추출. 정확한 본동 선택 필수.

    existing_pk: factory의 기존 mgm_bldrgst_pk.
      - 있으면: PK가 정확히 일치하는 주건축물 1개만 허용.
      - 없으면: 주건축물 후보가 정확히 1개일 때만 채택.
    복수 본동·PK 불일치·후보 없음 → {} (SOURCE_IDENTITY_UNRESOLVED).
    """
    if not title_items:
        return {}

    main_candidates = [i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"]
    if not main_candidates:
        return {}  # 주건축물 없음 → SOURCE_IDENTITY_UNRESOLVED

    if existing_pk:
        exact = [c for c in main_candidates
                 if str(c.get("mgmBldrgstPk") or "").strip() == existing_pk]
        if len(exact) != 1:
            return {}  # PK 불일치 또는 복수 일치 → SOURCE_IDENTITY_UNRESOLVED
        title = exact[0]
    else:
        if len(main_candidates) != 1:
            return {}  # 복수 본동 + 기존 PK 없음 → SOURCE_IDENTITY_UNRESOLVED
        title = main_candidates[0]

    out: Dict[str, Any] = {}
    bh = _safe_float(title.get("heit"))
    if bh is not None:
        out["building_height"] = bh
    fc = _safe_int(title.get("grndFlrCnt"))
    if fc is not None:
        out["floor_count"] = fc
    pk = title.get("mgmBldrgstPk")
    if pk is not None and str(pk).strip():
        out["mgm_bldrgst_pk"] = str(pk).strip()
    return out


def fetch_h01_title_for_bdmgtsn(bdmgtsn: str) -> Optional[list]:
    """건물관리번호로 표제부(title) API 전체 페이지 수집. 실패/빈값 → None."""
    p = parse_bdmgtsn(bdmgtsn)
    if not p:
        return None

    building_key = os.environ.get("BUILDING_API_KEY", "")
    base_params = {
        "serviceKey": building_key,
        "sigunguCd":  p["sigunguCd"],
        "bjdongCd":   p["bjdongCd"],
        "platGbCd":   p["mountain"],
        "bun":        p["bun"],
        "numOfRows":  _TITLE_PAGE_SIZE,
        "_type":      "json",
    }

    def _fetch_all_pages(ji_val: str) -> Optional[list]:
        """페이지 전체 수집.

        반환:
          []         → totalCount=0 (진짜 빈값, ji fallback 허용)
          [rows...]  → 데이터 수집 완료
          None       → API 오류·정합성 실패 (ji fallback 금지)
        """
        params = {**base_params, "ji": ji_val}
        all_rows: List[dict] = []
        expected_total: Optional[int] = None
        page = 1

        while page <= _MAX_TITLE_PAGES:
            call_params = {**params, "pageNo": page}
            try:
                status, text = kr_get(
                    f"{_BUILDING_BASE}/{_TITLE_ENDPOINT}",
                    params=call_params,
                    timeout=25,
                )
            except Exception:
                return None
            if status != 200 or not text:
                return None
            try:
                data = _json.loads(text)
            except Exception:
                return None
            body = (data.get("response") or {}).get("body") or {}

            # totalCount 누락·음수·불일치 → 즉시 실패
            raw_total = body.get("totalCount")
            if raw_total is None:
                return None
            try:
                total = int(raw_total)
            except (TypeError, ValueError):
                return None
            if total < 0:
                return None

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                return None  # 페이지 간 totalCount 변동 → 정합성 실패

            if total == 0:
                return []  # 진짜 빈값 → [] 반환 (ji fallback 허용)

            items_obj = body.get("items") or {}
            raw = items_obj.get("item") if isinstance(items_obj, dict) else None
            if raw is None:
                return None  # 기대 데이터 있으나 빈 페이지 → 부분 결과 거부
            page_rows = raw if isinstance(raw, list) else [raw]
            all_rows.extend(page_rows)
            if len(all_rows) >= expected_total:
                break
            page += 1
        else:
            return None  # _MAX_TITLE_PAGES 초과 → 무한 반복 차단

        if len(all_rows) < (expected_total or 0):
            return None
        return all_rows

    result = _fetch_all_pages(p["ji"])
    if result is None:
        return None  # API 오류 → ji fallback 금지
    if not result:
        # totalCount=0 (진짜 빈 ji) → 대체 지번 시도
        result = _fetch_all_pages("0000")
        if result is None:
            return None
    return result or None


def hydrate_factory_h01(supabase, factory_id: str) -> Dict[str, Any]:
    """factory_id 의 bdmgtsn 을 읽어 H01 필드를 건물대장에서 가져와 PATCH.

    반환:
      {"updated": True, "building_height": float|None, "floor_count": int|None}
      {"updated": False, "reason": str}
    """
    try:
        row_res = (
            supabase.table("factories")
            .select("bdmgtsn, mgm_bldrgst_pk")
            .eq("id", factory_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(row_res, "data", None) or [])
        if not rows:
            return {"updated": False, "reason": "factory_not_found"}
        row = rows[0] or {}
        bdmgtsn = row.get("bdmgtsn") or ""
        if not bdmgtsn or len(str(bdmgtsn)) != 19:
            return {"updated": False, "reason": "bdmgtsn_missing_or_invalid"}
        existing_mgm_pk = str(row.get("mgm_bldrgst_pk") or "").strip() or None
    except Exception:
        return {"updated": False, "reason": "db_read_error"}

    title_items = fetch_h01_title_for_bdmgtsn(str(bdmgtsn))
    if not title_items:
        return {"updated": False, "reason": "api_no_result"}

    fields = extract_h01_fields(title_items, existing_pk=existing_mgm_pk)
    if not fields:
        return {"updated": False, "reason": "h01_fields_absent_in_response"}

    # 본동 동일성 확인 필수 — PK 없으면 미인증 수치 저장 금지
    if not fields.get("mgm_bldrgst_pk"):
        return {"updated": False, "reason": "h01_identity_unresolved"}

    # 수치 하나 이상 확보된 경우에만 provenance timestamp 기록
    has_numeric = fields.get("building_height") is not None or fields.get("floor_count") is not None
    if not has_numeric:
        return {"updated": False, "reason": "h01_fields_absent_in_response"}

    from services.time import now_kst, serialize_business_datetime
    # 명시적 PATCH: 미반환 수치 필드를 None으로 설정해 기존 미인증 값의 false-auth 방지
    patch: Dict[str, Any] = {
        "building_height": fields.get("building_height"),
        "floor_count": fields.get("floor_count"),
        "mgm_bldrgst_pk": fields["mgm_bldrgst_pk"],
        "building_register_updated_at": serialize_business_datetime(now_kst()),
    }

    try:
        supabase.table("factories").update(patch).eq("id", factory_id).execute()
    except Exception:
        return {"updated": False, "reason": "db_write_error"}

    return {
        "updated": True,
        "building_height": fields.get("building_height"),
        "floor_count": fields.get("floor_count"),
        "mgm_bldrgst_pk": fields["mgm_bldrgst_pk"],
    }
