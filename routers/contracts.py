#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Contracts 라우터 - 견적/계약 관리
전역변수: contract_status / service_type / saas_plan

v2.1.0 (2026-04-07):
  - PATCH /contracts/{id}/status 래퍼 추가
    status 값에 따라 activate/suspend/cancel로 분기
    order-detail.html 프론트엔드 호환용

v2.0.0 (2026-04-01):
  - convert_to_contract: service_type='DIAGNOSIS'이면 quotes.items → contracts.items 복사
  - activate_contract: DIAGNOSIS 계약 활성화 시 status_code='ACTIVE' 처리

[견적]
GET    /quotes                   견적 목록
POST   /quotes                   견적 등록
GET    /quotes/{id}              견적 상세
PATCH  /quotes/{id}              견적 수정
POST   /quotes/{id}/confirm      견적 확정 → CONFIRMED
POST   /quotes/{id}/convert      계약 전환 → PENDING_PAYMENT

[계약]
GET    /contracts                계약 목록
POST   /contracts                계약 직접 등록
GET    /contracts/{id}           계약 상세
PATCH  /contracts/{id}           계약 수정
PATCH  /contracts/{id}/status    상태 변경 래퍼 (ACTIVE/SUSPENDED/CANCELLED) ← v2.1.0
POST   /contracts/{id}/activate  서비스 활성화 → ACTIVE
POST   /contracts/{id}/payment   입금 확인
POST   /contracts/{id}/suspend   일시 정지 → SUSPENDED
POST   /contracts/{id}/cancel    계약 취소 → CANCELLED
GET    /contracts/{id}/history   상태 변경 이력
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from db.supabase_client import get_supabase
import random

router = APIRouter(tags=["contracts"])


# ============================================================
# 헬퍼
# ============================================================

def gen_quote_no() -> str:
    return f"QUO-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

def gen_contract_no() -> str:
    return f"CON-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

def calc_vat(amount: int) -> int:
    return int(amount * 0.1)


# ============================================================
# 스키마
# ============================================================

class QuoteItem(BaseModel):
    name:       str
    qty:        int = 1
    unit_price: int

class QuoteCreate(BaseModel):
    company_id:    str
    service_type:  str
    contact_name:  Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    items:         Optional[List[QuoteItem]] = []
    memo:          Optional[str] = None

class QuoteUpdate(BaseModel):
    service_type:  Optional[str] = None
    contact_name:  Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    items:         Optional[List[dict]] = None
    memo:          Optional[str] = None
    status_code:   Optional[str] = None

class ContractCreate(BaseModel):
    company_id:        str
    service_type:      str
    plan_code:         Optional[str] = None
    contract_amount:   int
    start_date:        str
    end_date:          Optional[str] = None
    max_factory_count: Optional[int] = None
    max_user_count:    Optional[int] = None
    memo:              Optional[str] = None
    activate_now:      bool = False

class ContractUpdate(BaseModel):
    service_type:      Optional[str] = None
    plan_code:         Optional[str] = None
    contract_amount:   Optional[int] = None
    start_date:        Optional[str] = None
    end_date:          Optional[str] = None
    max_factory_count: Optional[int] = None
    max_user_count:    Optional[int] = None
    memo:              Optional[str] = None

class ContractStatusUpdate(BaseModel):
    """v2.1.0: PATCH /contracts/{id}/status 래퍼용"""
    status:  str               # ACTIVE | SUSPENDED | CANCELLED
    reason:  Optional[str] = None   # suspend/cancel 시 사유

class PaymentConfirm(BaseModel):
    paid_amount: int
    memo:        Optional[str] = None

class SuspendRequest(BaseModel):
    reason: str

class CancelRequest(BaseModel):
    reason: Optional[str] = None


# ============================================================
# 견적 API
# ============================================================

@router.get("/quotes")
def get_quotes(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    company_id:   Optional[str] = Query(default=None),
    service_type: Optional[str] = Query(default=None),
    status_code:  Optional[str] = Query(default=None),
    search:       Optional[str] = Query(default=None),
):
    supabase = get_supabase()
    query = supabase.table("quotes").select("*", count="exact")

    if company_id:   query = query.eq("company_id", company_id)
    if service_type: query = query.eq("service_type", service_type)
    if status_code:  query = query.eq("status_code", status_code)
    if search:
        pat = f"%{search}%"
        query = query.or_(f"contact_name.ilike.{pat},company_name.ilike.{pat},quote_no.ilike.{pat}")

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {"status": "success", "data": {
        "items": res.data, "total": res.count,
        "page": page, "size": size,
        "total_pages": -(-res.count // size) if res.count else 0,
    }}


@router.post("/quotes")
def create_quote(req: QuoteCreate):
    supabase = get_supabase()

    company = supabase.table("companies")\
        .select("id").eq("id", req.company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")

    items = []
    supply_amount = 0
    for item in (req.items or []):
        subtotal = item.qty * item.unit_price
        items.append({"name": item.name, "qty": item.qty,
                      "unit_price": item.unit_price, "subtotal": subtotal})
        supply_amount += subtotal

    vat_amount   = calc_vat(supply_amount)
    now          = datetime.now()

    res = supabase.table("quotes").insert({
        "quote_no":      gen_quote_no(),
        "company_id":    req.company_id,
        "service_type":  req.service_type,
        "status_code":   "REQUESTED",
        "contact_name":  req.contact_name,
        "contact_phone": req.contact_phone,
        "contact_email": req.contact_email,
        "items":         items,
        "supply_amount": supply_amount,
        "vat_amount":    vat_amount,
        "total_amount":  supply_amount + vat_amount,
        "memo":          req.memo,
        "is_active":     True,
        "created_at":    now.isoformat(),
        "updated_at":    now.isoformat(),
    }).execute()

    return {"status": "success", "message": "견적이 등록됐습니다", "data": res.data[0]}


@router.get("/quotes/{quote_id}")
def get_quote(quote_id: str):
    supabase = get_supabase()
    res = supabase.table("quotes").select("*").eq("id", quote_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


@router.patch("/quotes/{quote_id}")
def update_quote(quote_id: str, req: QuoteUpdate):
    supabase = get_supabase()

    existing = supabase.table("quotes")\
        .select("id, status_code").eq("id", quote_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    st = existing.data["status_code"]
    if st == "CANCELLED":
        raise HTTPException(status_code=400, detail="취소된 견적은 수정할 수 없습니다")
    if st == "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="계약 전환된 견적은 수정할 수 없습니다")

    update_data = {k: v for k, v in req.dict(exclude_unset=True).items() if v is not None}
    if req.status_code is not None:
        if req.status_code != "CANCELLED":
            raise HTTPException(status_code=400, detail="상태 변경은 취소(CANCELLED)만 가능합니다")
        if st not in ("REQUESTED", "CONFIRMED"):
            raise HTTPException(status_code=400, detail="이 상태에서는 견적을 취소할 수 없습니다")
    if req.items:
        supply = sum(i.get("qty", 1) * i.get("unit_price", 0) for i in req.items)
        update_data["supply_amount"] = supply
        update_data["vat_amount"]    = calc_vat(supply)
        update_data["total_amount"]  = supply + update_data["vat_amount"]

    update_data["updated_at"] = datetime.now().isoformat()
    res = supabase.table("quotes").update(update_data).eq("id", quote_id).execute()
    return {"status": "success", "message": "견적이 수정됐습니다", "data": res.data[0] if res.data else {}}


@router.post("/quotes/{quote_id}/confirm")
def confirm_quote(quote_id: str):
    """견적 확정 → CONFIRMED"""
    supabase = get_supabase()
    q = supabase.table("quotes").select("status_code").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    if q.data["status_code"] != "REQUESTED":
        raise HTTPException(status_code=400, detail="견적요청 상태에서만 확정 가능합니다")

    supabase.table("quotes").update({
        "status_code": "CONFIRMED",
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", quote_id).execute()

    return {"status": "success", "message": "견적이 확정됐습니다. 고객에게 이메일이 발송됩니다"}


@router.post("/quotes/{quote_id}/convert")
def convert_to_contract(quote_id: str):
    """견적 → 계약 전환 → PENDING_PAYMENT
    v2.0.0: service_type='DIAGNOSIS'이면 quotes.items → contracts.items 복사
    """
    supabase = get_supabase()
    q = supabase.table("quotes").select("*").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    if q.data["status_code"] != "CONFIRMED":
        raise HTTPException(status_code=400, detail="견적확정 상태에서만 계약 전환 가능합니다")

    now          = datetime.now()
    service_type = q.data.get("service_type", "")

    contract_row = {
        "contract_no":     gen_contract_no(),
        "company_id":      q.data["company_id"],
        "service_type":    service_type,
        "contract_amount": q.data["supply_amount"],
        "vat_amount":      q.data["vat_amount"],
        "total_amount":    q.data["total_amount"],
        "status_code":     "PENDING_PAYMENT",
        "quote_id":        quote_id,
        "paid_amount":     0,
        "is_active":       True,
        "created_at":      now.isoformat(),
        "updated_at":      now.isoformat(),
    }

    # DIAGNOSIS: quotes.items → contracts.items 복사 (factory_id + step 정보 유지)
    if service_type == "DIAGNOSIS":
        contract_row["items"] = q.data.get("items") or []

    contract_res = supabase.table("contracts").insert(contract_row).execute()
    contract_id  = contract_res.data[0]["id"]

    supabase.table("quotes").update({
        "status_code": "PENDING_PAYMENT",
        "contract_id": contract_id,
        "updated_at":  now.isoformat(),
    }).eq("id", quote_id).execute()

    return {"status": "success", "message": "계약이 생성됐습니다. 입금 대기 상태입니다",
            "data": contract_res.data[0]}


# ============================================================
# 계약 API
# ============================================================

@router.get("/contracts")
def get_contracts(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    company_id:   Optional[str] = Query(default=None),
    service_type: Optional[str] = Query(default=None),
    status_code:  Optional[str] = Query(default=None),
    search:       Optional[str] = Query(default=None),
    expiring:     bool = Query(default=False),
):
    supabase = get_supabase()
    query = supabase.table("contracts").select("*", count="exact")

    if company_id:   query = query.eq("company_id", company_id)
    if service_type: query = query.eq("service_type", service_type)
    if status_code:  query = query.eq("status_code", status_code)
    if search:       query = query.ilike("contract_no", f"%{search}%")
    if expiring:
        expire_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        today       = datetime.now().strftime("%Y-%m-%d")
        query = query.lte("end_date", expire_date)\
                     .gte("end_date", today)\
                     .eq("status_code", "ACTIVE")

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {"status": "success", "data": {
        "items": res.data, "total": res.count,
        "page": page, "size": size,
        "total_pages": -(-res.count // size) if res.count else 0,
    }}


@router.post("/contracts")
def create_contract(req: ContractCreate):
    supabase = get_supabase()
    company = supabase.table("companies")\
        .select("id").eq("id", req.company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")

    vat    = calc_vat(req.contract_amount)
    now    = datetime.now()
    status = "ACTIVE" if req.activate_now else "PENDING_PAYMENT"

    res = supabase.table("contracts").insert({
        "contract_no":      gen_contract_no(),
        "company_id":       req.company_id,
        "service_type":     req.service_type,
        "plan_code":        req.plan_code,
        "contract_amount":  req.contract_amount,
        "vat_amount":       vat,
        "total_amount":     req.contract_amount + vat,
        "status_code":      status,
        "start_date":       req.start_date,
        "end_date":         req.end_date,
        "max_factory_count": req.max_factory_count,
        "max_user_count":   req.max_user_count,
        "paid_amount":      req.contract_amount if req.activate_now else 0,
        "paid_at":          now.isoformat() if req.activate_now else None,
        "memo":             req.memo,
        "is_active":        True,
        "created_at":       now.isoformat(),
        "updated_at":       now.isoformat(),
    }).execute()

    msg = "계약이 등록됐습니다" + (" (즉시 활성화)" if req.activate_now else " (입금 대기)")
    return {"status": "success", "message": msg, "data": res.data[0]}


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: str):
    supabase = get_supabase()
    res = supabase.table("contracts").select("*").eq("id", contract_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


@router.patch("/contracts/{contract_id}")
def update_contract(contract_id: str, req: ContractUpdate):
    supabase = get_supabase()
    existing = supabase.table("contracts")\
        .select("id").eq("id", contract_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    if req.contract_amount:
        vat = calc_vat(req.contract_amount)
        update_data["vat_amount"]   = vat
        update_data["total_amount"] = req.contract_amount + vat
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("contracts").update(update_data).eq("id", contract_id).execute()
    return {"status": "success", "message": "계약이 수정됐습니다", "data": res.data[0] if res.data else {}}


# ──────────────────────────────────────────────────────────────
# v2.1.0: PATCH /contracts/{id}/status — 상태 변경 래퍼
# 주의: 고정경로 (/history, /activate 등)보다 뒤에 선언해야
#       하지만 /status는 별도 세그먼트이므로 충돌 없음.
#       order-detail.html 프론트엔드 호환용.
# ──────────────────────────────────────────────────────────────

@router.patch("/contracts/{contract_id}/status")
def update_contract_status(contract_id: str, req: ContractStatusUpdate):
    """
    계약 상태 변경 래퍼 (프론트엔드 단일 엔드포인트 호환).

    status 값에 따라 내부 처리:
      ACTIVE    → activate_contract() 로직 (PENDING_PAYMENT 또는 SUSPENDED → ACTIVE)
      SUSPENDED → suspend_contract() 로직 (ACTIVE → SUSPENDED)
      CANCELLED → cancel_contract() 로직 (모든 상태 → CANCELLED)
    """
    supabase = get_supabase()
    c = supabase.table("contracts").select("*").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    target = req.status.upper()
    current = c.data["status_code"]
    now = datetime.now()

    # ── ACTIVE 처리 ──────────────────────────────────────────
    if target == "ACTIVE":
        if current not in ("PENDING_PAYMENT", "SUSPENDED"):
            raise HTTPException(
                status_code=400,
                detail=f"입금대기 또는 정지 상태에서만 활성화 가능합니다. (현재: {current})"
            )
        supabase.table("contracts").update({
            "status_code": "ACTIVE",
            "is_active":   True,
            "updated_at":  now.isoformat(),
        }).eq("id", contract_id).execute()

        # SAAS 계약만 회사 상태 변경
        if c.data.get("service_type") != "DIAGNOSIS":
            supabase.table("companies").update({
                "status_code": "ACTIVE",
                "updated_at":  now.isoformat(),
            }).eq("id", c.data["company_id"]).execute()

        return {"status": "success", "message": "서비스가 활성화됐습니다 🎉",
                "data": {"contract_id": contract_id, "status": "ACTIVE"}}

    # ── SUSPENDED 처리 ───────────────────────────────────────
    elif target == "SUSPENDED":
        if current != "ACTIVE":
            raise HTTPException(
                status_code=400,
                detail=f"활성화 상태에서만 정지 가능합니다. (현재: {current})"
            )
        supabase.table("contracts").update({
            "status_code":      "SUSPENDED",
            "suspended_at":     now.isoformat(),
            "suspended_reason": req.reason or "관리자 정지",
            "updated_at":       now.isoformat(),
        }).eq("id", contract_id).execute()

        return {"status": "success", "message": "서비스가 일시정지됐습니다",
                "data": {"contract_id": contract_id, "status": "SUSPENDED"}}

    # ── CANCELLED 처리 ───────────────────────────────────────
    elif target == "CANCELLED":
        if current in ("CANCELLED", "EXPIRED"):
            raise HTTPException(
                status_code=400,
                detail="이미 취소/만료된 계약입니다"
            )
        supabase.table("contracts").update({
            "status_code":  "CANCELLED",
            "cancelled_at": now.isoformat(),
            "is_active":    False,
            "memo":         req.reason or "관리자 취소",
            "updated_at":   now.isoformat(),
        }).eq("id", contract_id).execute()

        return {"status": "success", "message": "계약이 취소됐습니다",
                "data": {"contract_id": contract_id, "status": "CANCELLED"}}

    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 상태값입니다: {req.status} (ACTIVE/SUSPENDED/CANCELLED 중 하나)"
        )


# ============================================================
# 기존 개별 액션 엔드포인트 (유지)
# ============================================================

@router.post("/contracts/{contract_id}/activate")
def activate_contract(contract_id: str):
    """PENDING_PAYMENT → ACTIVE + 회사 상태 ACTIVE
    v2.0.0: DIAGNOSIS 계약도 동일하게 ACTIVE 처리 (end_date=None → 영구)
    """
    supabase = get_supabase()
    c = supabase.table("contracts").select("*").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    if c.data["status_code"] != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="입금대기 상태에서만 활성화 가능합니다")

    now = datetime.now()
    supabase.table("contracts").update({
        "status_code": "ACTIVE",
        "is_active":   True,
        "updated_at":  now.isoformat(),
    }).eq("id", contract_id).execute()

    if c.data.get("service_type") != "DIAGNOSIS":
        supabase.table("companies").update({
            "status_code": "ACTIVE",
            "updated_at":  now.isoformat(),
        }).eq("id", c.data["company_id"]).execute()

    return {"status": "success", "message": "서비스가 활성화됐습니다 🎉"}


@router.post("/contracts/{contract_id}/payment")
def confirm_payment(contract_id: str, req: PaymentConfirm):
    """입금 확인"""
    supabase = get_supabase()
    c = supabase.table("contracts").select("id").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    now = datetime.now()
    supabase.table("contracts").update({
        "paid_amount": req.paid_amount,
        "paid_at":     now.isoformat(),
        "updated_at":  now.isoformat(),
    }).eq("id", contract_id).execute()

    return {"status": "success", "message": f"입금이 확인됐습니다 ({req.paid_amount:,}원)"}


@router.post("/contracts/{contract_id}/suspend")
def suspend_contract(contract_id: str, req: SuspendRequest):
    """ACTIVE → SUSPENDED"""
    supabase = get_supabase()
    c = supabase.table("contracts").select("status_code").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    if c.data["status_code"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="활성화 상태에서만 정지 가능합니다")

    now = datetime.now()
    supabase.table("contracts").update({
        "status_code":      "SUSPENDED",
        "suspended_at":     now.isoformat(),
        "suspended_reason": req.reason,
        "updated_at":       now.isoformat(),
    }).eq("id", contract_id).execute()

    return {"status": "success", "message": "서비스가 일시정지됐습니다"}


@router.post("/contracts/{contract_id}/cancel")
def cancel_contract(contract_id: str, req: CancelRequest):
    """계약 취소 → CANCELLED"""
    supabase = get_supabase()
    c = supabase.table("contracts").select("status_code").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")
    if c.data["status_code"] in ["CANCELLED", "EXPIRED"]:
        raise HTTPException(status_code=400, detail="이미 취소/만료된 계약입니다")

    now = datetime.now()
    supabase.table("contracts").update({
        "status_code":  "CANCELLED",
        "cancelled_at": now.isoformat(),
        "is_active":    False,
        "memo":         req.reason,
        "updated_at":   now.isoformat(),
    }).eq("id", contract_id).execute()

    return {"status": "success", "message": "계약이 취소됐습니다"}


@router.get("/contracts/{contract_id}/history")
def get_contract_history(contract_id: str):
    """계약 상태 변경 이력"""
    supabase = get_supabase()
    c = supabase.table("contracts").select("*").eq("id", contract_id).single().execute()
    if not c.data:
        raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다")

    d = c.data
    history = [{"status": "CREATED", "label": "계약 생성", "at": d.get("created_at")}]
    if d.get("paid_at"):
        history.append({"status": "PAID", "label": f"입금 확인 ({d.get('paid_amount',0):,}원)", "at": d.get("paid_at")})
    if d.get("suspended_at"):
        history.append({"status": "SUSPENDED", "label": f"일시정지 ({d.get('suspended_reason','')})", "at": d.get("suspended_at")})
    if d.get("cancelled_at"):
        history.append({"status": "CANCELLED", "label": "계약 취소", "at": d.get("cancelled_at")})

    history.sort(key=lambda x: x["at"] or "")

    return {"status": "success", "data": {"contract": d, "history": history}}
