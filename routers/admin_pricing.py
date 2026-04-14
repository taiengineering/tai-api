# routers/admin_pricing.py — 관리자 가격 일괄 수정 API v1.0.0
# v1.0.0 (2026-04-14):
#   PATCH /admin/pricing — key 배열로 복수 가격 동시 수정
#   GET   /admin/pricing/keys — 지원 key 목록 조회
#
# key 예시:
#   diag_building       → price_diagnosis_report BUILDING total_report_fee
#   diag_factory        → price_diagnosis_report FACTORY total_report_fee
#   building_starter_fee → price_saas_plan BUILDING_STARTER monthly_base_fee
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.database import get_supabase
from routers.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["관리자 가격"])


# ── 모델 ──────────────────────────────────────────────────────────────

class PricingPatchItem(BaseModel):
    key:   str
    value: Any   # 숫자 or 문자열


class PricingPatchBody(BaseModel):
    updates: list[PricingPatchItem]
    memo:    Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── GET /admin/pricing/keys ───────────────────────────────────────────

@router.get("/pricing/keys")
def list_pricing_keys(
    current_user: dict = Depends(get_current_user),
):
    """지원되는 pricing key 목록 조회."""
    sb = get_supabase()
    res = sb.table("pricing_key_map").select(
        "key, table_name, field_name, label, is_active"
    ).eq("is_active", True).order("key").execute()
    return {"status": "success", "data": res.data or []}


# ── PATCH /admin/pricing ─────────────────────────────────────────────

@router.patch("/pricing")
def patch_pricing(
    body: PricingPatchBody,
    current_user: dict = Depends(get_current_user),
):
    """
    key 기반 가격 일괄 수정.

    요청 예시:
    ```json
    {
      "updates": [
        {"key": "diag_building",     "value": 99000},
        {"key": "building_starter_fee", "value": 79000}
      ],
      "memo": "2026-04 가격 정책 변경"
    }
    ```
    """
    if not body.updates:
        raise HTTPException(status_code=400, detail="updates가 비어있습니다")

    sb = get_supabase()
    results = []
    errors  = []
    changed_by = current_user.get("id")

    for item in body.updates:
        # key 맵 조회
        km = sb.table("pricing_key_map").select("*").eq("key", item.key).eq("is_active", True).limit(1).execute()
        if not km.data:
            errors.append({"key": item.key, "error": "알 수 없는 key"})
            continue

        mapping     = km.data[0]
        table_name  = mapping["table_name"]
        record_id   = mapping["record_id"]
        field_name  = mapping["field_name"]

        # 숫자 검증 (금액 필드)
        try:
            new_value = int(item.value)
            if new_value < 0:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append({"key": item.key, "error": f"value는 0 이상 정수여야 합니다 (받은 값: {item.value})"})
            continue

        # 기존 값 조회
        old_res = sb.table(table_name).select(field_name).eq("id", record_id).limit(1).execute()
        old_value = old_res.data[0].get(field_name) if old_res.data else None

        # 업데이트
        update_payload = {field_name: new_value, "updated_at": _now()}
        upd = sb.table(table_name).update(update_payload).eq("id", record_id).execute()

        # 변경 로그
        try:
            sb.table("price_change_log").insert({
                "table_name":  table_name,
                "record_id":   record_id,
                "field_name":  field_name,
                "old_value":   str(old_value) if old_value is not None else None,
                "new_value":   str(new_value),
                "changed_by":  changed_by,
            }).execute()
        except Exception:
            pass

        results.append({
            "key":       item.key,
            "label":     mapping.get("label"),
            "field":     field_name,
            "old_value": old_value,
            "new_value": new_value,
            "status":    "updated",
        })

    # 가격 캐시 초기화 (public_pricing 캐시)
    try:
        from routers.public_pricing import _cache
        _cache.clear()
    except Exception:
        pass

    return {
        "status":  "success" if not errors else "partial",
        "updated": results,
        "errors":  errors,
        "memo":    body.memo,
    }
