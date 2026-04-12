"""
routers/settlements.py — v1.0.0
정산 시스템 — 최종 리포트 / 신청자 확인 / 정산 생성 / 이체 완료 / 원천세

파이프라인:
  IN_PROGRESS
    → (전문가) POST /final-report      → CONFIRMING
    → (신청자) POST /client-confirm    → SETTLED + settlements 자동 생성
    → (어드민) PATCH /{id}/process     → PROCESSING (계좌 입력)
    → (어드민) PATCH /{id}/complete    → PAID + matching_requests CLOSED

entity_type별 세금 처리:
  CORPORATION / SOLE_PROPRIETOR  → INVOICE     (세금계산서)
  SIMPLIFIED_TAX                 → CASH_RECEIPT (현금영수증)
  INDIVIDUAL                     → WITHHOLDING (원천세 3.3%)

prefix: /settlements  (main.py에서 지정)
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter()   # prefix는 main.py에서 지정


# ── 유틸 ──────────────────────────────────────────────────────────────
def _now_iso() -> str:
    from datetime import timezone
    return datetime.datetime.now(timezone.utc).isoformat()


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


def _get_expert_entity_type(supabase: Any, expert_user_id: str) -> str:
    """전문가 user_id로 entity_type 조회 (3개 테이블 순서대로)"""
    for table in ("safety_personnel", "safety_agencies", "repair_companies"):
        try:
            res = (
                supabase.table(table)
                .select("entity_type")
                .eq("user_id", expert_user_id)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("entity_type"):
                return res.data[0]["entity_type"]
        except Exception:
            continue
    return "INDIVIDUAL"   # 미확인 시 원천세 적용 (보수적 처리)


def _create_settlement(supabase: Any, contract: dict, now: str) -> str:
    """
    settlements 레코드 자동 생성.
    entity_type에 따라 원천세(3.3%) / 세금계산서 / 현금영수증 분기.
    """
    entity_type  = _get_expert_entity_type(supabase, contract.get("expert_user_id", ""))
    gross_amount = contract.get("expert_amount", 0) or 0
    withholding  = 0
    tax_type     = "INVOICE"

    if entity_type == "INDIVIDUAL":
        tax_type    = "WITHHOLDING"
        withholding = round(gross_amount * 0.033)
    elif entity_type == "SIMPLIFIED_TAX":
        tax_type    = "CASH_RECEIPT"

    net_pay = gross_amount - withholding

    # 전문가 이름 조회
    expert_name = ""
    try:
        u_res = (
            supabase.table("users")
            .select("name, identity_name")
            .eq("id", contract.get("expert_user_id", ""))
            .limit(1)
            .execute()
        )
        if u_res.data:
            u = u_res.data[0]
            expert_name = u.get("identity_name") or u.get("name") or ""
    except Exception as e:
        log.warning(f"[SETTLEMENT] expert_name 조회 실패: {e}")

    res = supabase.table("settlements").insert({
        "matching_contract_id": contract["id"],
        "matching_request_id":  contract.get("request_id"),
        "expert_user_id":       contract.get("expert_user_id"),
        "expert_name":          expert_name,
        "expert_entity_type":   entity_type,
        "contract_amount":      contract.get("contract_amount", 0),
        "tai_fee_rate":         contract.get("tai_fee_rate", 10),
        "tai_fee_amount":       contract.get("tai_fee_amount", 0),
        "expert_gross_amount":  gross_amount,
        "withholding_tax":      withholding,
        "net_pay_amount":       net_pay,
        "tax_type":             tax_type,
        "status":               "PENDING",
        "created_at":           now,
        "updated_at":           now,
    }).execute()

    if not res.data:
        log.error("[SETTLEMENT] settlements INSERT 실패")
        return ""

    settlement_id = res.data[0]["id"]
    log.info(f"[SETTLEMENT] 생성 settlement_id={settlement_id} tax_type={tax_type} net={net_pay:,}")
    return settlement_id


# ── Pydantic 모델 ──────────────────────────────────────────────────────
class FinalReportBody(BaseModel):
    contract_id: str
    report_url:  str
    report_memo: Optional[str] = None


class ClientConfirmBody(BaseModel):
    contract_id:  str
    confirm_note: Optional[str] = None


class ProcessBody(BaseModel):
    expert_bank:    str
    expert_account: str
    settle_memo:    Optional[str] = None


class CompleteBody(BaseModel):
    invoice_number:       Optional[str] = None
    invoice_issued_at:    Optional[str] = None
    transfer_receipt_url: Optional[str] = None


class HoldBody(BaseModel):
    reason: str


# ════════════════════════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════════════════════════

@router.post("/final-report")
def upload_final_report(
    body:         FinalReportBody,
    current_user: dict = Depends(get_current_user),
):
    """
    전문가: 최종 업무 리포트 업로드
    POST /settlements/final-report

    처리:
      1. matching_contracts.final_report_url 저장
      2. matching_requests → CONFIRMING
      3. 신청자 최종 확인 요청 알림
    """
    supabase = get_supabase()
    res = (
        supabase.table("matching_contracts")
        .select("id, status, expert_user_id, client_user_id, request_id")
        .eq("id", body.contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    c = res.data[0]

    if c.get("expert_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="담당 전문가만 리포트를 업로드할 수 있습니다.")
    if c.get("status") not in ("ACTIVE", "IN_PROGRESS"):
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태({c['status']})에서는 리포트를 업로드할 수 없습니다.",
        )

    now = _now_iso()

    # 1. matching_contracts 업데이트
    supabase.table("matching_contracts").update({
        "final_report_url": body.report_url,
        "updated_at":       now,
    }).eq("id", body.contract_id).execute()

    # 2. matching_requests → CONFIRMING
    request_id = c.get("request_id")
    if request_id:
        req = (
            supabase.table("matching_requests")
            .select("status, status_history")
            .eq("id", request_id)
            .limit(1)
            .execute()
        )
        if req.data and req.data[0]["status"] == "IN_PROGRESS":
            history = req.data[0].get("status_history") or []
            history.append({
                "status": "CONFIRMING",
                "at":     now,
                "by":     current_user["id"],
                "memo":   "전문가 최종 리포트 업로드 완료",
            })
            supabase.table("matching_requests").update({
                "status":         "CONFIRMING",
                "status_history": history,
                "updated_at":     now,
            }).eq("id", request_id).execute()

    # 3. 신청자 알림
    if c.get("client_user_id"):
        supabase.table("notifications").insert({
            "user_id":    c["client_user_id"],
            "title":      "최종 리포트가 등록되었습니다",
            "body":       "전문가가 최종 결과 리포트를 제출했습니다. 확인 후 서비스를 완료해 주세요.",
            "type":       "SETTLEMENT",
            "ref_id":     body.contract_id,
            "is_read":    False,
            "created_at": now,
        }).execute()

    log.info(f"[SETTLEMENT] 최종 리포트 등록 contract_id={body.contract_id}")
    return {
        "status": "success",
        "data": {
            "contract_id": body.contract_id,
            "report_url":  body.report_url,
            "message":     "리포트가 등록되었습니다. 신청자 최종 확인을 기다립니다.",
        },
    }


@router.post("/client-confirm")
def client_confirm(
    body:         ClientConfirmBody,
    current_user: dict = Depends(get_current_user),
):
    """
    신청자: 서비스 완료 최종 확인
    POST /settlements/client-confirm

    처리:
      1. matching_contracts.client_confirm_at, status=COMPLETED
      2. matching_requests → SETTLED
      3. settlements 레코드 자동 생성 (entity_type별 세금 처리)
      4. 전문가 알림
    """
    supabase = get_supabase()
    res = (
        supabase.table("matching_contracts")
        .select("*")
        .eq("id", body.contract_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다.")

    c = res.data[0]

    if c.get("client_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="신청자만 최종 확인할 수 있습니다.")
    if not c.get("final_report_url"):
        raise HTTPException(status_code=400, detail="전문가의 최종 리포트가 아직 등록되지 않았습니다.")

    now        = _now_iso()
    request_id = c.get("request_id")

    # 1. matching_contracts → COMPLETED
    supabase.table("matching_contracts").update({
        "client_confirm_at": now,
        "status":            "COMPLETED",
        "updated_at":        now,
    }).eq("id", body.contract_id).execute()

    # 2. matching_requests → SETTLED
    if request_id:
        req = (
            supabase.table("matching_requests")
            .select("status_history")
            .eq("id", request_id)
            .limit(1)
            .execute()
        )
        history = (req.data[0].get("status_history") or []) if req.data else []
        history.append({
            "status": "SETTLED",
            "at":     now,
            "by":     current_user["id"],
            "memo":   body.confirm_note or "신청자 최종 확인 완료",
        })
        supabase.table("matching_requests").update({
            "status":         "SETTLED",
            "status_history": history,
            "updated_at":     now,
        }).eq("id", request_id).execute()

    # 3. settlements 레코드 자동 생성
    settlement_id = _create_settlement(supabase, c, now)

    # 4. 전문가 알림
    if c.get("expert_user_id"):
        supabase.table("notifications").insert({
            "user_id":    c["expert_user_id"],
            "title":      "✅ 서비스 완료 확인",
            "body":       "고객이 서비스 완료를 확인했습니다. 영업일 기준 익일 대금이 지급됩니다.",
            "type":       "SETTLEMENT",
            "ref_id":     body.contract_id,
            "is_read":    False,
            "created_at": now,
        }).execute()

    return {
        "status": "success",
        "data": {
            "contract_id":   body.contract_id,
            "settlement_id": settlement_id,
            "message":       "최종 확인 완료. 영업일 기준 익일 대금이 지급될 예정입니다.",
        },
    }


@router.get("/withholding")
def withholding_list(
    year_month:   str           = Query(..., description="귀속연월 YYYY-MM"),
    reported:     Optional[bool] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 원천세 신고 대상 목록
    GET /settlements/withholding?year_month=2026-04

    개인 전문가(INDIVIDUAL) 지급분 조회 — 매월 10일 신고 의무.
    """
    supabase = get_supabase()

    try:
        ym      = datetime.datetime.strptime(year_month, "%Y-%m")
        next_ym = (ym.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="year_month 형식은 YYYY-MM 이어야 합니다.")

    q = (
        supabase.table("settlements")
        .select(
            "id, expert_name, expert_biz_number, "
            "expert_gross_amount, withholding_tax, net_pay_amount, "
            "settled_at, withholding_reported, withholding_report_month"
        )
        .eq("tax_type", "WITHHOLDING")
        .eq("status", "PAID")
        .gte("settled_at", ym.strftime("%Y-%m-01"))
        .lt("settled_at",  next_ym.strftime("%Y-%m-01"))
    )
    if reported is not None:
        q = q.eq("withholding_reported", reported)

    res   = q.order("settled_at").execute()
    items = res.data or []

    total_gross       = sum(r.get("expert_gross_amount", 0) or 0 for r in items)
    total_withholding = sum(r.get("withholding_tax",     0) or 0 for r in items)
    total_net         = sum(r.get("net_pay_amount",      0) or 0 for r in items)

    return {
        "status": "success",
        "data": {
            "year_month":        year_month,
            "items":             items,
            "total_count":       len(items),
            "total_gross":       total_gross,
            "total_withholding": total_withholding,
            "total_net":         total_net,
        },
    }


@router.patch("/withholding/mark-reported")
def mark_withholding_reported(
    settlement_ids: List[str],
    year_month:     str,
    current_user:   dict = Depends(_require_admin),
):
    """
    원천세 신고 완료 일괄 처리
    PATCH /settlements/withholding/mark-reported
    """
    supabase = get_supabase()
    now      = _now_iso()
    for sid in settlement_ids:
        supabase.table("settlements").update({
            "withholding_reported":     True,
            "withholding_report_month": year_month,
            "updated_at":               now,
        }).eq("id", sid).execute()

    return {
        "status": "success",
        "data": {
            "reported_count": len(settlement_ids),
            "year_month":     year_month,
        },
    }


@router.get("")
def list_settlements(
    status:      Optional[str]  = Query(None),
    tax_type:    Optional[str]  = Query(None),
    entity_type: Optional[str]  = Query(None),
    wh_reported: Optional[bool] = Query(None, description="원천세 신고 여부"),
    date_from:   Optional[str]  = Query(None, description="YYYY-MM-DD"),
    date_to:     Optional[str]  = Query(None, description="YYYY-MM-DD"),
    keyword:     Optional[str]  = Query(None, description="전문가명 검색"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 정산 목록
    GET /settlements
    """
    supabase = get_supabase()
    q = supabase.table("settlements").select(
        "id, matching_contract_id, expert_name, expert_entity_type, "
        "expert_biz_number, expert_bank, expert_account, "
        "contract_amount, tai_fee_amount, expert_gross_amount, "
        "withholding_tax, net_pay_amount, tax_type, "
        "invoice_number, invoice_issued_at, "
        "status, settled_at, settle_memo, "
        "withholding_reported, withholding_report_month, "
        "created_at",
        count="exact",
    )
    if status:              q = q.eq("status",               status)
    if tax_type:            q = q.eq("tax_type",             tax_type)
    if entity_type:         q = q.eq("expert_entity_type",   entity_type)
    if wh_reported is not None:
                            q = q.eq("withholding_reported", wh_reported)
    if keyword:             q = q.ilike("expert_name",       f"%{keyword}%")
    if date_from:           q = q.gte("created_at",          date_from)
    if date_to:             q = q.lte("created_at",          f"{date_to}T23:59:59")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0
    items  = res.data or []

    total_net = sum(r.get("net_pay_amount", 0) or 0 for r in items)

    return {
        "status": "success",
        "data": {
            "items":         items,
            "total":         total,
            "page":          page,
            "size":          size,
            "total_pages":   (total + size - 1) // size if total else 0,
            "total_net_pay": total_net,
        },
    }


@router.get("/{settlement_id}")
def get_settlement(
    settlement_id: str,
    current_user:  dict = Depends(_require_admin),
):
    """정산 상세 조회 — GET /settlements/{settlement_id}"""
    supabase = get_supabase()
    res = (
        supabase.table("settlements")
        .select("*")
        .eq("id", settlement_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="정산 건을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/{settlement_id}/process")
def process_settlement(
    settlement_id: str,
    body:          ProcessBody,
    current_user:  dict = Depends(_require_admin),
):
    """
    어드민: 정산 처리 시작 (계좌 입력 → PROCESSING)
    PATCH /settlements/{settlement_id}/process
    """
    supabase = get_supabase()
    res = (
        supabase.table("settlements")
        .select("id, status")
        .eq("id", settlement_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="정산 건을 찾을 수 없습니다.")
    if res.data[0]["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="PENDING 상태인 건만 처리할 수 있습니다.")

    now = _now_iso()
    supabase.table("settlements").update({
        "status":         "PROCESSING",
        "expert_bank":    body.expert_bank,
        "expert_account": body.expert_account,
        "settle_memo":    body.settle_memo,
        "settled_by":     current_user["id"],
        "updated_at":     now,
    }).eq("id", settlement_id).execute()

    return {
        "status": "success",
        "data":   {"settlement_id": settlement_id, "status": "PROCESSING"},
    }


@router.patch("/{settlement_id}/complete")
def complete_settlement(
    settlement_id: str,
    body:          CompleteBody,
    current_user:  dict = Depends(_require_admin),
):
    """
    어드민: 이체 완료 처리 → PAID
    PATCH /settlements/{settlement_id}/complete

    처리:
      1. settlements → PAID
      2. matching_contracts → settled_at, net_pay_amount
      3. matching_requests → CLOSED
      4. 전문가 💰 알림
    """
    supabase = get_supabase()
    settle_res = (
        supabase.table("settlements")
        .select("*")
        .eq("id", settlement_id)
        .limit(1)
        .execute()
    )
    if not settle_res.data:
        raise HTTPException(status_code=404, detail="정산 건을 찾을 수 없습니다.")
    if settle_res.data[0]["status"] != "PROCESSING":
        raise HTTPException(status_code=400, detail="PROCESSING 상태인 건만 완료 처리할 수 있습니다.")

    s   = settle_res.data[0]
    now = _now_iso()

    # 1. settlements → PAID
    supabase.table("settlements").update({
        "status":               "PAID",
        "invoice_number":       body.invoice_number,
        "invoice_issued_at":    body.invoice_issued_at,
        "transfer_receipt_url": body.transfer_receipt_url,
        "settled_at":           now,
        "updated_at":           now,
    }).eq("id", settlement_id).execute()

    # 2. matching_contracts 정산 반영
    supabase.table("matching_contracts").update({
        "settled_at":     now,
        "net_pay_amount": s.get("net_pay_amount"),
        "updated_at":     now,
    }).eq("id", s["matching_contract_id"]).execute()

    # 3. matching_requests → CLOSED
    if s.get("matching_request_id"):
        req = (
            supabase.table("matching_requests")
            .select("status_history")
            .eq("id", s["matching_request_id"])
            .limit(1)
            .execute()
        )
        history = (req.data[0].get("status_history") or []) if req.data else []
        history.append({
            "status": "CLOSED",
            "at":     now,
            "by":     current_user["id"],
            "memo":   "정산 완료",
        })
        supabase.table("matching_requests").update({
            "status":         "CLOSED",
            "status_history": history,
            "updated_at":     now,
        }).eq("id", s["matching_request_id"]).execute()

    # 4. 전문가 알림
    net_pay = s.get("net_pay_amount", 0) or 0
    if s.get("expert_user_id"):
        supabase.table("notifications").insert({
            "user_id":    s["expert_user_id"],
            "title":      "💰 대금이 지급되었습니다",
            "body":       f"{net_pay:,}원이 등록된 계좌로 입금되었습니다.",
            "type":       "SETTLEMENT",
            "ref_id":     settlement_id,
            "is_read":    False,
            "created_at": now,
        }).execute()

    log.info(f"[SETTLEMENT] 이체 완료 settlement_id={settlement_id} net={net_pay:,}")
    return {
        "status":  "success",
        "message": "정산이 완료되었습니다.",
        "data": {
            "settlement_id":  settlement_id,
            "status":         "PAID",
            "net_pay_amount": net_pay,
            "settled_at":     now,
        },
    }


@router.patch("/{settlement_id}/hold")
def hold_settlement(
    settlement_id: str,
    body:          HoldBody,
    current_user:  dict = Depends(_require_admin),
):
    """
    어드민: 정산 보류 (세금계산서 미수취 / 계좌 오류 등)
    PATCH /settlements/{settlement_id}/hold
    """
    supabase = get_supabase()
    res = (
        supabase.table("settlements")
        .select("id, status")
        .eq("id", settlement_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="정산 건을 찾을 수 없습니다.")

    supabase.table("settlements").update({
        "status":      "HOLD",
        "settle_memo": body.reason,
        "updated_at":  _now_iso(),
    }).eq("id", settlement_id).execute()

    return {
        "status": "success",
        "data":   {"settlement_id": settlement_id, "status": "HOLD"},
    }
