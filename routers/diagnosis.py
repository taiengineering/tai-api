"""
법령진단 접근 제어 라우터 — v1.0.0

법령진단은 SaaS 구독(contract_level)과 완전 분리된 단건 결제 서비스.
  - 1단계: 항상 무료 (has_access=True)
  - 2단계 / 3단계 / 99(종합리포트): diagnosis_purchases 단건 결제 기록 확인

API:
  GET /diagnosis/access-check?factory_id=&step=  단계별 접근 가능 여부
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

VERSION = "1.0.0"

VALID_STEPS = {1, 2, 3, 99}  # 99 = 종합리포트


def _now_utc():
    return datetime.now(timezone.utc)


# ============================================================
# GET /diagnosis/access-check
# ============================================================

@router.get("/access-check")
def check_diagnosis_access(
    factory_id: str = Query(..., description="factories.id (UUID)"),
    step:        int = Query(..., description="1=기초진단(무료) | 2=2단계 | 3=3단계 | 99=종합리포트"),
):
    """
    법령진단 단계별 접근 가능 여부 확인.

    - step=1  → 항상 has_access=True (무료)
    - step=2/3/99 → diagnosis_purchases 테이블에서
      factory_id + step + status='PAID' 기록 존재 여부 확인.
      expires_at 있으면 만료일 체크 (NULL=영구).

    SaaS contract_level(STARTER/BUSINESS/ENTERPRISE)은 체크하지 않음.
    """
    if step not in VALID_STEPS:
        raise HTTPException(
            status_code=422,
            detail=f"step은 {sorted(VALID_STEPS)} 중 하나여야 합니다."
        )

    # 1단계 — 항상 무료
    if step == 1:
        return {
            "status": "success",
            "data": {
                "factory_id": factory_id,
                "step":       step,
                "has_access": True,
                "reason":     "FREE",
            }
        }

    supabase = get_supabase()

    # factory → company_id 확인
    fac_res = supabase.table("factories").select("id, company_id").eq(
        "id", factory_id
    ).limit(1).execute()

    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    company_id = fac_res.data[0].get("company_id")

    # diagnosis_purchases 조회
    q = supabase.table("diagnosis_purchases").select(
        "id, step, status, paid_at, expires_at"
    ).eq("factory_id", factory_id)

    if company_id:
        q = q.eq("company_id", company_id)

    q = q.eq("step", step).eq("status", "PAID")
    purchase_res = q.order("paid_at", desc=True).limit(1).execute()

    purchases = purchase_res.data or []

    if not purchases:
        return {
            "status": "success",
            "data": {
                "factory_id": factory_id,
                "step":       step,
                "has_access": False,
                "reason":     "NO_PURCHASE",
            }
        }

    purchase = purchases[0]
    expires_at_str = purchase.get("expires_at")

    # expires_at 있으면 만료 체크
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(
                expires_at_str.replace("Z", "+00:00")
            )
            if _now_utc() > expires_at:
                return {
                    "status": "success",
                    "data": {
                        "factory_id": factory_id,
                        "step":       step,
                        "has_access": False,
                        "reason":     "EXPIRED",
                        "expired_at": expires_at_str,
                    }
                }
        except Exception:
            pass  # 파싱 실패 시 영구로 간주

    return {
        "status": "success",
        "data": {
            "factory_id":  factory_id,
            "step":        step,
            "has_access":  True,
            "reason":      "PAID",
            "purchase_id": purchase["id"],
            "paid_at":     purchase.get("paid_at"),
            "expires_at":  expires_at_str,  # NULL = 영구
        }
    }
