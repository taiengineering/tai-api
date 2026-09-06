"""결제 조회·수동처리·VBANK 상태 — /payments 보조 라우트 (payment.py 용량 분리).

[2026-07-30 #5 감사 완결성] 결제취소(PAYMENT_CANCEL)·수동활성화(PAYMENT_MANUAL_CONFIRM)를
  admin_ops_audit_logs 에 before/after·actor 로 기록한다(best-effort — 감사 실패가 본 처리를 막지 않음).

[2026-08-15 P0-보정1] 인증 경계 추가: 전 엔드포인트 SUPER_ADMIN(role_code==001).
  공용 자산 재사용: routers.matching_deps._require_admin (get_current_user + role 001).
  감사 주체(actor)는 body의 by/cancelled_by를 신뢰하지 않고 인증 사용자(current_user["id"])로 서버 확정.
  결제 business logic·PG flow 무변경 — 인증/감사주체만 보정.

[2026-08-20 §35] 고객 자사 조회 분리: GET /payments/my 신설.
  기존 관리자 엔드포인트(전체 조회)는 불변. /my 는 로그인 사용자의 소속 회사(current_user["company_id"])
  결제만 반환한다 — client 가 보난 company_id 를 신뢰하지 않는다(P13). 관리자 여부와 무관하게 자사만 조회.

[2026-09-05 FE-0] GET /payments/my 투영 보정: v_payments_list 에 proof_type 가 없어
  payments 테이블을 명시 컴럼(proof_type 포함)으로 직접 조회. company ownership·envelope 불변.
  관리자 list_payments 는 v_payments_list 그대로 유지.

[2026-09-06 FE-0-2] GET /payments/my 각 행에 tax_status(세금계산서 원장 상태, 사실값) 추가.
  tax_invoices.payment_id / tax_invoice_requests.payment_id 를 배치 2쿼리로 조회(N+1 금지).
  fail-soft: tax 조회 실패해도 결제목록은 정상(tax_status=NONE). envelope 불변(행에 필드 추가만).
  정책 판정 아니라 원장 상태 조회—프론트는 라벨만 매핑.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.payment import CancelBody, ManualConfirmBody
from services import audit_svc
from services.payment_helpers import SAAS_PRODUCT_TYPES, calc_expired_at, now_iso
from services.time import now_kst

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])


def _attach_tax_status(supabase, rows: list) -> None:
    """각 결제행에 tax_status(세금계산서 원장 상태, 사실값) 부여. N+1 금지 — 배치 2쿼리.

    값: MODIFIED(수정발급) / ISSUED(발행완료) / PROCESSING / REQUESTED / FAILED /
         REVIEW_REQUIRED / CANCELLED / NONE(미발급)
    파생 우선순위: 발행된 수정세금계산서 > 발행완료 > 최신 요청 상태 > NONE.
    정책 판정이 아닌 원장(tax_invoices/tax_invoice_requests) 사실 조회. fail-soft.
    """
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        for r in rows:
            r["tax_status"] = "NONE"
        return

    issued_original: set = set()
    issued_modified: set = set()
    try:
        inv = (
            supabase.table("tax_invoices")
            .select("payment_id, invoice_kind, status")
            .in_("payment_id", ids)
            .execute()
        )
        for iv in (inv.data or []):
            if str(iv.get("status")) == "ISSUED":
                pid = iv.get("payment_id")
                if iv.get("invoice_kind") == "MODIFIED":
                    issued_modified.add(pid)
                else:
                    issued_original.add(pid)
    except Exception as e:  # noqa: BLE001 — fail-soft
        log.warning("[tax_status] tax_invoices lookup failed: %s", e)

    latest_req: dict = {}
    try:
        reqs = (
            supabase.table("tax_invoice_requests")
            .select("payment_id, status, created_at")
            .in_("payment_id", ids)
            .order("created_at", desc=True)
            .execute()
        )
        for rq in (reqs.data or []):
            pid = rq.get("payment_id")
            if pid and pid not in latest_req:  # desc 정렬 → 첫 등장이 최신
                latest_req[pid] = rq.get("status")
    except Exception as e:  # noqa: BLE001 — fail-soft
        log.warning("[tax_status] tax_invoice_requests lookup failed: %s", e)

    for r in rows:
        pid = r.get("id")
        if pid in issued_modified:
            r["tax_status"] = "MODIFIED"
        elif pid in issued_original or latest_req.get(pid) == "ISSUED":
            r["tax_status"] = "ISSUED"
        elif pid in latest_req:
            r["tax_status"] = latest_req[pid]
        else:
            r["tax_status"] = "NONE"


@router.get("")
def list_payments(
    user_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    service_status: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    plan_code: Optional[str] = Query(None),
    pg_method: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="회원명 또는 회사명 검색"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    q = supabase.table("v_payments_list").select("*", count="exact")

    if user_id:
        q = q.eq("user_id", user_id)
    if company_id:
        q = q.eq("company_id", company_id)
    if status_code:
        q = q.eq("status_code", status_code)
    if service_status:
        q = q.eq("service_status", service_status)
    if product_type:
        q = q.eq("product_type", product_type)
    if plan_code:
        q = q.eq("plan_code", plan_code)
    if pg_method:
        q = q.eq("pg_method", pg_method)

    if keyword:
        q = q.or_(f"user_name.ilike.%{keyword}%,company_name.ilike.%{keyword}%")

    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/my")
def list_my_payments(
    status_code: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """
    고객 자사 결제 조회 (§35).

    로그인 사용자의 소속 회사 결제만 반환한다. 관리자 여부와 무관.
    company_id 는 토큰(current_user)에서만 도출한다 — client 가 보난 값을 신뢰하지 않는다(P13).

    FE-0: v_payments_list 에 proof_type 가 없으므로 payments 테이블을 명시 컴럼으로
    직접 조회한다(proof_type 포함). 응답 envelope 와 company ownership 은 그대로 유지.

    FE-0-2: 각 행에 tax_status(세금계산서 원장 상태, 사실값) 추가(배치 조회). envelope 불변.
    """
    company_id = current_user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="소속 회사가 없어 조회할 수 없습니다.")

    supabase = get_supabase()
    q = (
        supabase.table("payments")
        .select(
            "id, product_type, plan_code, "
            "total_amount, supply_amount, vat_amount, "
            "status_code, service_status, "
            "pg_method, proof_type, "
            "period_months, paid_at, created_at, expired_at",
            count="exact",
        )
        .eq("company_id", company_id)
    )

    if status_code:
        q = q.eq("status_code", status_code)
    if product_type:
        q = q.eq("product_type", product_type)

    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    rows = res.data or []
    _attach_tax_status(supabase, rows)
    return {
        "status": "success",
        "data": {
            "items": rows,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/expiring")
def list_expiring_payments(
    days: int = Query(30, ge=1, le=90),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    now = now_kst()
    deadline = (now + timedelta(days=days)).isoformat()
    q = supabase.table("v_payments_list").select(
        "id, user_id, user_name, company_name, product_type, plan_code, "
        "period_months, total_amount, status_code, service_status, paid_at, expired_at",
        count="exact",
    ).eq("status_code", "SUCCESS").lte("expired_at", deadline).gte("expired_at", now.isoformat())
    offset = (page - 1) * size
    res = q.order("expired_at", desc=False).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "days_threshold": days,
        },
    }


@router.post("/manual/confirm")
def manual_confirm(body: ManualConfirmBody, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    now = now_iso()
    pay_res = (
        supabase.table("payments")
        .select("id, status_code, product_type, period_months")
        .eq("id", body.payment_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "SUCCESS":
        raise HTTPException(status_code=409, detail="이미 성공 처리된 결제입니다.")

    update_row: dict = {
        "status_code": "SUCCESS",
        "service_status": "ACTIVE",
        "paid_at": now,
        "memo": "수동 활성화 처리",
        "updated_at": now,
    }
    product_type = payment.get("product_type", "")
    period_months = payment.get("period_months")
    if product_type in SAAS_PRODUCT_TYPES and period_months:
        update_row["expired_at"] = calc_expired_at(now, period_months)

    supabase.table("payments").update(update_row).eq("id", body.payment_id).execute()
    supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", body.contract_id).execute()

    audit_svc.record(
        "PAYMENT_MANUAL_CONFIRM", "payment", entity_id=str(body.payment_id),
        actor_id=current_user["id"],
        before={"status_code": payment["status_code"]},
        after={"status_code": "SUCCESS", "service_status": "ACTIVE",
               "contract_id": str(body.contract_id)},
    )

    try:
        from services.payment_post_process import on_payment_success_sync
        on_payment_success_sync(str(body.payment_id))
    except Exception as e:
        log.error("Payment post-process failed: %s", e)

    return {
        "status": "success",
        "message": "수동 활성화 완료",
        "data": {"payment_id": body.payment_id, "contract_id": body.contract_id},
    }


@router.post("/{payment_id}/cancel")
def cancel_payment(payment_id: str, body: CancelBody, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    now = now_iso()
    pay_res = (
        supabase.table("payments")
        .select("id, status_code, contract_id")
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 결제입니다.")

    supabase.table("payments").update(
        {
            "status_code": "CANCELLED",
            "service_status": "ENDED",
            "cancel_reason": body.reason,
            "cancelled_at": now,
            "expired_at": None,
            "updated_at": now,
        }
    ).eq("id", payment_id).execute()

    contract_id = payment.get("contract_id")
    if contract_id:
        supabase.table("contracts").update({"is_active": False, "updated_at": now}).eq("id", contract_id).execute()

    audit_svc.record(
        "PAYMENT_CANCEL", "payment", entity_id=str(payment_id),
        actor_id=current_user["id"],
        before={"status_code": payment["status_code"], "contract_id": contract_id},
        after={"status_code": "CANCELLED", "service_status": "ENDED", "reason": body.reason},
    )

    return {
        "status": "success",
        "message": "취소 처리되었습니다.",
        "data": {"payment_id": payment_id, "status_code": "CANCELLED"},
    }


@router.get("/{payment_id}/vbank-status")
def get_vbank_status(payment_id: str, current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    res = (
        supabase.table("payments")
        .select(
            "id, status_code, total_amount, "
            "vbank_number, vbank_bank, vbank_expires_at, "
            "vbank_depositor, vbank_confirmed_at, paid_at"
        )
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="결제 정보를 찾을 수 없습니다.")

    p = res.data[0]
    return {
        "status": "success",
        "data": {
            "payment_id": payment_id,
            "status_code": p["status_code"],
            "is_paid": p["status_code"] == "SUCCESS",
            "total_amount": p["total_amount"],
            "vbank_number": p.get("vbank_number"),
            "vbank_bank": p.get("vbank_bank"),
            "vbank_expires_at": p.get("vbank_expires_at"),
            "vbank_depositor": p.get("vbank_depositor"),
            "confirmed_at": p.get("vbank_confirmed_at"),
        },
    }
