"""
법령진단 접근 제어 + 단건 결제 라우터 — v1.1.0

법령진단은 SaaS 구독(contract_level)과 완전 분리된 단건 결제 서비스.
  - 1단계: 항상 무료 (has_access=True)
  - 2단계 / 3단계 / 99(종합리포트): diagnosis_purchases 단건 결제 기록 확인

API:
  GET  /diagnosis/access-check?factory_id=&step=   단계별 접근 가능 여부
  POST /diagnosis/purchases                         단건 결제 기록 생성
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

VERSION = "1.1.0"

VALID_STEPS = {1, 2, 3, 99}  # 99 = 종합리포트

SECTOR_PRICES = {
    "BUILDING":         {2: 29000, 3:  59000, 99: 99000},
    "MANUFACTURING":    {2: 49000, 3:  99000, 99: 249000},
    "CONSTRUCTION":     {2: 79000, 3: 149000, 99: 399000},
    "SPECIAL_FACILITY": {2: 49000, 3:  99000, 99: 199000},
}

VALID_PAY_METHODS = {"card", "transfer", "invoice"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


# ============================================================
# POST /diagnosis/purchases — 단건 결제 기록
# ============================================================

class PurchaseCreateBody(BaseModel):
    factory_id:      str
    sector:          str                        # BUILDING | MANUFACTURING | CONSTRUCTION | SPECIAL_FACILITY
    step:            int                        # 2 | 3 | 99
    amount:          int                        # 결제금액 (원)
    payment_method:  Optional[str] = "card"    # card | transfer | invoice
    diagnosis_id:    Optional[str] = None       # factory_diagnosis_results.id
    company_id:      Optional[str] = None
    step_label:      Optional[str] = None       # step2 | step3 | report
    invoice_biz_no:  Optional[str] = None
    invoice_email:   Optional[str] = None


@router.post("/purchases")
def create_purchase(body: PurchaseCreateBody):
    """
    법령진단 단건 결제 기록.

    - payment_method=card   → status=PAID, paid_at=now 즉시 기록
    - payment_method=transfer/invoice → status=PENDING (관리자 확인 후 PAID 전환)
    """
    if body.step not in {2, 3, 99}:
        raise HTTPException(status_code=422, detail="step은 2, 3, 99 중 하나여야 합니다.")

    pm = (body.payment_method or "card").lower()
    if pm not in VALID_PAY_METHODS:
        raise HTTPException(status_code=422, detail=f"payment_method는 {sorted(VALID_PAY_METHODS)} 중 하나여야 합니다.")

    supabase = get_supabase()

    # company_id 자동 조회
    company_id = body.company_id
    if not company_id:
        fac = supabase.table("factories").select("company_id").eq(
            "id", body.factory_id
        ).limit(1).execute()
        if fac.data:
            company_id = fac.data[0].get("company_id")

    # 가격 검증 (프론트 조작 방어)
    expected = SECTOR_PRICES.get(body.sector, {}).get(body.step)
    if expected and body.amount != expected:
        raise HTTPException(
            status_code=422,
            detail=f"금액이 올바르지 않습니다. (기대값: {expected:,}원)"
        )

    now = _now()
    is_card  = pm == "card"
    status   = "PAID" if is_card else "PENDING"
    paid_at  = now if is_card else None

    row = {
        "factory_id":      body.factory_id,
        "company_id":      company_id,
        "sector":          body.sector,
        "step":            body.step,
        "price":           body.amount,
        "status":          status,
        "paid_at":         paid_at,
        "expires_at":      None,          # 영구 (만료 없음)
        "payment_method":  pm,
        "diagnosis_id":    body.diagnosis_id,
        "step_label":      body.step_label or f"step{body.step}",
        "invoice_biz_no":  body.invoice_biz_no,
        "invoice_email":   body.invoice_email,
        "created_at":      now,
    }

    res = supabase.table("diagnosis_purchases").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="결제 기록 생성에 실패했습니다.")

    record = res.data[0]
    return {
        "status":  "success",
        "message": "결제가 기록됐습니다." if is_card else "결제 신청이 접수됐습니다. 확인 후 활성화됩니다.",
        "data": {
            **record,
            "has_access": is_card,   # card=즉시 접근, transfer/invoice=대기
        }
    }
