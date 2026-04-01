"""
법령진단 접근 제어 + 견적 요청 라우터 — v2.0.0

변경 이력:
  v2.0.0 (2026-04-01):
    - POST /diagnosis/request-quote  신규: quotes 테이블에 DIAGNOSIS 견적 생성
    - GET  /diagnosis/access-check   변경: contracts 테이블 기반 접근 확인
      (기존 diagnosis_purchases 테이블 조회 → 제거)
    - POST /diagnosis/purchases      DEPRECATED (삭제 금지, 하위호환 유지)

  v1.1.0: diagnosis_purchases 기반 access-check + purchases 생성
  v1.0.0: 초기 구현

결제 흐름 (B2B):
  견적 신청(request-quote) → 관리자 확인·승인
  → 계약 생성(contracts, service_type='DIAGNOSIS')
  → access-check: contracts 테이블에서 ACTIVE 계약 + items 확인

API:
  POST /diagnosis/request-quote        DIAGNOSIS 견적 생성 (신규)
  GET  /diagnosis/access-check         단계별 접근 가능 여부 (contracts 기반)
  POST /diagnosis/purchases            [DEPRECATED] 단건 결제 기록 (삭제 금지)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase
import random

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

VERSION = "2.0.0"

VALID_STEPS = {1, 2, 3, 99}  # 99 = 종합리포트

SECTOR_PRICES = {
    "BUILDING":         {2: 29000, 3:  59000, 99:  99000},
    "MANUFACTURING":    {2: 49000, 3:  99000, 99: 249000},
    "CONSTRUCTION":     {2: 79000, 3: 149000, 99: 399000},
    "SPECIAL_FACILITY": {2: 49000, 3:  99000, 99: 199000},
}

STEP_LABELS = {2: "2단계 공정진단", 3: "3단계 설비진단", 99: "종합리포트"}

VALID_PAY_METHODS = {"card", "transfer", "invoice"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_utc():
    return datetime.now(timezone.utc)


def _gen_quote_no() -> str:
    return f"QUO-DIAG-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


# ============================================================
# POST /diagnosis/request-quote  신규 v2.0.0
# ============================================================

class DiagnosisQuoteRequest(BaseModel):
    factory_id:    str
    sector:        str            # BUILDING / MANUFACTURING / CONSTRUCTION / SPECIAL_FACILITY
    step:          int            # 2 or 3 or 99
    contact_name:  str
    contact_phone: str
    contact_email: Optional[str] = None
    memo:          Optional[str] = None
    company_id:    Optional[str] = None


@router.post("/request-quote")
def request_diagnosis_quote(body: DiagnosisQuoteRequest):
    """
    DIAGNOSIS 견적 생성 (B2B 플로우).

    quotes 테이블에 service_type='DIAGNOSIS' 행 생성.
    금액은 SECTOR_PRICES 기준 자동 계산.
    items JSONB에 factory_id + step 저장 → 이후 contracts.items로 복사됨.
    """
    if body.step not in {2, 3, 99}:
        raise HTTPException(status_code=422, detail="step은 2, 3, 99 중 하나여야 합니다.")

    sector = body.sector.upper()
    if sector not in SECTOR_PRICES:
        raise HTTPException(
            status_code=422,
            detail=f"sector는 {list(SECTOR_PRICES.keys())} 중 하나여야 합니다."
        )

    supabase = get_supabase()

    # company_id 조회 (없으면 factory에서 자동 조회)
    company_id = body.company_id
    factory_name = ""
    fac = supabase.table("factories").select("company_id, name").eq(
        "id", body.factory_id
    ).limit(1).execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    if not company_id:
        company_id = fac.data[0].get("company_id")
    factory_name = fac.data[0].get("name", "")

    unit_price     = SECTOR_PRICES[sector][body.step]
    supply_amount  = unit_price
    vat_amount     = int(supply_amount * 0.1)
    total_amount   = supply_amount + vat_amount

    items = [{
        "sector":       sector,
        "step":         body.step,
        "step_label":   STEP_LABELS.get(body.step, f"{body.step}단계 진단"),
        "factory_id":   body.factory_id,
        "factory_name": factory_name,
        "unit_price":   unit_price,
        "quantity":     1,
        "subtotal":     unit_price,
    }]

    now = _now()
    row = {
        "quote_no":      _gen_quote_no(),
        "company_id":    company_id,
        "service_type":  "DIAGNOSIS",
        "status_code":   "REQUESTED",
        "contact_name":  body.contact_name,
        "contact_phone": body.contact_phone,
        "contact_email": body.contact_email,
        "supply_amount": supply_amount,
        "vat_amount":    vat_amount,
        "total_amount":  total_amount,
        "items":         items,
        "memo":          body.memo,
        "is_active":     True,
        "created_at":    now,
        "updated_at":    now,
    }

    res = supabase.table("quotes").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="견적 생성에 실패했습니다.")

    return {
        "status":  "success",
        "message": "견적 신청이 완료됐습니다. 담당자가 확인 후 연락드립니다.",
        "data":    res.data[0],
    }


# ============================================================
# GET /diagnosis/access-check  v2.0.0 변경
# ============================================================

@router.get("/access-check")
def check_diagnosis_access(
    factory_id: str = Query(..., description="factories.id (UUID)"),
    step:        int = Query(..., description="1=기초진단(무료) | 2=2단계 | 3=3단계 | 99=종합리포트"),
):
    """
    법령진단 단계별 접근 가능 여부 확인.

    v2.0.0 변경사항:
    - 기존: diagnosis_purchases 테이블에서 단건 결제 기록 확인
    - 변경: contracts 테이블에서 DIAGNOSIS ACTIVE 계약 + items 확인
      (B2B 플로우: 견적→계약 승인 후 접근 허용)

    - step=1 → 항상 has_access=True (무료)
    - step=2/3/99 → contracts에서 service_type='DIAGNOSIS', status_code='ACTIVE',
      items 배열에 factory_id + step 일치 항목 존재 여부 확인

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

    # contracts에서 DIAGNOSIS ACTIVE 계약 조회
    q = supabase.table("contracts").select("id, items").eq(
        "service_type", "DIAGNOSIS"
    ).eq("status_code", "ACTIVE").eq("is_active", True)

    if company_id:
        q = q.eq("company_id", company_id)

    contract_res = q.execute()
    contracts = contract_res.data or []

    # items 배열에서 factory_id + step 일치 여부 확인
    has_access  = False
    contract_id = None
    for contract in contracts:
        items = contract.get("items") or []
        for item in items:
            if (
                str(item.get("factory_id", "")) == str(factory_id) and
                int(item.get("step", -1))        == step
            ):
                has_access  = True
                contract_id = contract["id"]
                break
        if has_access:
            break

    if not has_access:
        return {
            "status": "success",
            "data": {
                "factory_id": factory_id,
                "step":       step,
                "has_access": False,
                "reason":     "NO_CONTRACT",
            }
        }

    return {
        "status": "success",
        "data": {
            "factory_id":  factory_id,
            "step":        step,
            "has_access":  True,
            "reason":      "CONTRACT_ACTIVE",
            "contract_id": contract_id,
        }
    }


# ============================================================
# POST /diagnosis/purchases — [DEPRECATED v2.0.0]
# 삭제 금지: 하위 호환 유지 / 내부 관리 로그 용도
# 프론트에서 더 이상 호출하지 않음
# ============================================================

class PurchaseCreateBody(BaseModel):
    factory_id:      str
    sector:          str
    step:            int
    amount:          int
    payment_method:  Optional[str] = "card"
    diagnosis_id:    Optional[str] = None
    company_id:      Optional[str] = None
    step_label:      Optional[str] = None
    invoice_biz_no:  Optional[str] = None
    invoice_email:   Optional[str] = None


@router.post("/purchases")
def create_purchase(body: PurchaseCreateBody):
    """
    [DEPRECATED v2.0.0]
    법령진단 단건 결제 기록.

    이 엔드포인트는 deprecated 처리됐습니다.
    새로운 결제 흐름은 POST /diagnosis/request-quote → 관리자 승인 → contracts 생성입니다.
    하위 호환을 위해 삭제하지 않고 유지합니다.
    """
    if body.step not in {2, 3, 99}:
        raise HTTPException(status_code=422, detail="step은 2, 3, 99 중 하나여야 합니다.")

    pm = (body.payment_method or "card").lower()
    if pm not in VALID_PAY_METHODS:
        raise HTTPException(status_code=422, detail=f"payment_method는 {sorted(VALID_PAY_METHODS)} 중 하나여야 합니다.")

    supabase = get_supabase()

    company_id = body.company_id
    if not company_id:
        fac = supabase.table("factories").select("company_id").eq(
            "id", body.factory_id
        ).limit(1).execute()
        if fac.data:
            company_id = fac.data[0].get("company_id")

    expected = SECTOR_PRICES.get(body.sector, {}).get(body.step)
    if expected and body.amount != expected:
        raise HTTPException(
            status_code=422,
            detail=f"금액이 올바르지 않습니다. (기대값: {expected:,}원)"
        )

    now     = _now()
    is_card = pm == "card"
    status  = "PAID" if is_card else "PENDING"
    paid_at = now if is_card else None

    try:
        row = {
            "factory_id":      body.factory_id,
            "company_id":      company_id,
            "sector":          body.sector,
            "step":            body.step,
            "price":           body.amount,
            "status":          status,
            "paid_at":         paid_at,
            "expires_at":      None,
            "payment_method":  pm,
            "diagnosis_id":    body.diagnosis_id,
            "step_label":      body.step_label or f"step{body.step}",
            "invoice_biz_no":  body.invoice_biz_no,
            "invoice_email":   body.invoice_email,
            "created_at":      now,
        }
        res = supabase.table("diagnosis_purchases").insert(row).execute()
        record = res.data[0] if res.data else {}
    except Exception as e:
        record = {}

    return {
        "status":     "success",
        "deprecated": True,
        "message":    "[DEPRECATED] 새로운 결제 흐름은 POST /diagnosis/request-quote를 사용하세요.",
        "data": {
            **record,
            "has_access": is_card,
        }
    }
"""
