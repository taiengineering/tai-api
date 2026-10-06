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

from typing import Any, Dict, Optional


def _safe_int(v) -> Optional[int]:
    try:
        return int(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


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


def extract_h01_fields(title_items: list) -> Dict[str, Any]:
    """표제부 리스트에서 H01 필드(building_height, floor_count)만 추출."""
    if not title_items:
        return {}
    title = next((i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"), None)
    if not title:
        title = title_items[0]
    out: Dict[str, Any] = {}
    bh = _safe_float(title.get("heit"))
    if bh is not None:
        out["building_height"] = bh
    fc = _safe_int(title.get("grndFlrCnt"))
    if fc is not None:
        out["floor_count"] = fc
    return out


def fetch_h01_title_for_bdmgtsn(bdmgtsn: str) -> Optional[list]:
    """건물관리번호로 표제부(title) API 호출. 실패/빈값 → None."""
    from services.kr_public_api import kr_get
    import os, json as _json

    p = parse_bdmgtsn(bdmgtsn)
    if not p:
        return None

    BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
    BUILDING_KEY = os.environ.get("BUILDING_API_KEY", "")
    params = {
        "serviceKey": BUILDING_KEY,
        "sigunguCd":  p["sigunguCd"],
        "bjdongCd":   p["bjdongCd"],
        "platGbCd":   p["mountain"],
        "bun":        p["bun"],
        "ji":         p["ji"],
        "numOfRows":  10,
        "pageNo":     1,
        "_type":      "json",
    }

    def _call(ji_val: str) -> Optional[list]:
        params["ji"] = ji_val
        try:
            status, text = kr_get(
                f"{BUILDING_BASE}/getBrTitleInfo",
                params=params,
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
        items = body.get("items") or {}
        raw = items.get("item") if isinstance(items, dict) else None
        if raw is None:
            return None
        return raw if isinstance(raw, list) else [raw]

    result = _call(p["ji"])
    if not result:
        result = _call("0000")
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
            .select("bdmgtsn")
            .eq("id", factory_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(row_res, "data", None) or [])
        if not rows:
            return {"updated": False, "reason": "factory_not_found"}
        bdmgtsn = (rows[0] or {}).get("bdmgtsn") or ""
        if not bdmgtsn or len(str(bdmgtsn)) != 19:
            return {"updated": False, "reason": "bdmgtsn_missing_or_invalid"}
    except Exception:
        return {"updated": False, "reason": "db_read_error"}

    title_items = fetch_h01_title_for_bdmgtsn(str(bdmgtsn))
    if not title_items:
        return {"updated": False, "reason": "api_no_result"}

    fields = extract_h01_fields(title_items)
    if not fields:
        return {"updated": False, "reason": "h01_fields_absent_in_response"}

    from services.time import now_kst, serialize_business_datetime
    patch = {**fields, "building_register_updated_at": serialize_business_datetime(now_kst())}

    try:
        supabase.table("factories").update(patch).eq("id", factory_id).execute()
    except Exception:
        return {"updated": False, "reason": "db_write_error"}

    return {
        "updated": True,
        "building_height": fields.get("building_height"),
        "floor_count": fields.get("floor_count"),
    }
