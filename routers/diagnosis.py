"""
법령진단 접근 제어 + 견적 요청 라우터 — v2.1.0

변경 이력:
  v2.1.0 (2026-08-20, §80 무인증 해소):
    - GET  /diagnosis/access-check   인증 필수(_require_login) + 회사 스코프(P13):
      관리자가 아니면 자사 시설만 조회. 타 회사 factory_id → 403 (계약 존재 노출 차단)
    - POST /diagnosis/request-quote  company_id 를 factory 에서만 도출(client 신뢰 제거, P13).
      접수 자체는 공개 유지(비로그인 견적 신청 허용)
    - POST /diagnosis/purchases      [DEPRECATED] 410 Gone 잠금

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
  POST /diagnosis/request-quote        DIAGNOSIS 견적 생성 (공개, company_id 는 factory 도출)
  GET  /diagnosis/access-check         단계별 접근 가능 여부 (인증 필수 + 회사 스코프)
  POST /diagnosis/purchases            [DEPRECATED · LOCKED] 410 Gone
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _is_admin, _scope
import random

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

VERSION = "2.1.0"

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
# POST /diagnosis/request-quote  신규 v2.0.0 · v2.1.0 P13
# ============================================================

class DiagnosisQuoteRequest(BaseModel):
    factory_id:    str
    sector:        str            # BUILDING / MANUFACTURING / CONSTRUCTION / SPECIAL_FACILITY
    step:          int            # 2 or 3 or 99
    contact_name:  str
    contact_phone: str
    contact_email: Optional[str] = None
    memo:          Optional[str] = None
    # company_id 제거(v2.1.0 §80/P13): client 가 보낸 company_id 를 신뢰하지 않는다.
    # company_id 는 서버에서 factory_id 로만 도출한다.


@router.post("/request-quote")
def request_diagnosis_quote(body: DiagnosisQuoteRequest):
    """
    DIAGNOSIS 견적 생성 (B2B 플로우) — 접수는 공개(비로그인 허용).

    quotes 테이블에 service_type='DIAGNOSIS' 행 생성.
    금액은 SECTOR_PRICES 기준 자동 계산.
    company_id 는 factory_id 로만 도출(P13: client 신뢰 금지).
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

    # company_id 는 factory 에서만 도출 (P13: client 가 보낸 company_id 신뢰 금지)
    fac = supabase.table("factories").select("company_id, name").eq(
        "id", body.factory_id
    ).limit(1).execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")
    company_id   = fac.data[0].get("company_id")
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
# GET /diagnosis/access-check  v2.0.0 변경 · v2.1.0 인증+스코프
# ============================================================

@router.get("/access-check")
def check_diagnosis_access(
    factory_id: str = Query(..., description="factories.id (UUID)"),
    step:        int = Query(..., description="1=기초진단(무료) | 2=2단계 | 3=3단계 | 99=종합리포트"),
    current:    dict = Depends(get_current_user),
):
    """
    법령진단 단계별 접근 가능 여부 확인.

    v2.1.0 (§80): 인증 필수 + 회사 스코프(P13).
      관리자가 아니면 자사 시설만 조회 가능. 타 회사 factory_id 는 403.
    - step=1 → 항상 has_access=True (무료), 단 소유 검증은 선행
    - step=2/3/99 → contracts에서 service_type='DIAGNOSIS', status_code='ACTIVE',
      items 배열에 factory_id + step 일치 항목 존재 여부 확인
    """
    if step not in VALID_STEPS:
        raise HTTPException(
            status_code=422,
            detail=f"step은 {sorted(VALID_STEPS)} 중 하나여야 합니다."
        )

    supabase = get_supabase()

    # factory → company_id 확인 (step 무관하게 소유 검증 선행)
    fac_res = supabase.table("factories").select("id, company_id").eq(
        "id", factory_id
    ).limit(1).execute()

    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    company_id = fac_res.data[0].get("company_id")

    # 회사 스코프 (P13): 관리자가 아니면 자사 시설만 접근 가능
    if not _is_admin(_scope(supabase, current.get("role_code"))):
        if str(company_id) != str(current.get("company_id")):
            raise HTTPException(status_code=403, detail="타 회사 시설에 접근할 수 없습니다.")

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
# POST /diagnosis/purchases — [DEPRECATED · LOCKED v2.1.0]
# 410 Gone: 새 흐름은 POST /diagnosis/request-quote
# 모델은 하위호환 참조용으로 유지하되, 엔드포인트는 잠근다.
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
    [DEPRECATED · LOCKED v2.1.0] 법령진단 단건 결제 기록.
    이 엔드포인트는 폐기됐습니다. 새로운 결제 흐름은
    POST /diagnosis/request-quote 를 사용하세요.
    """
    raise HTTPException(
        status_code=410,
        detail="이 엔드포인트는 폐기됐습니다. POST /diagnosis/request-quote 를 사용하세요.",
    )
