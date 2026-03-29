# routers/quotes.py — v2.0.0
# 변경사항:
#   v2.0.0 S02: 설문 접수 후 법령엔진 자동 실행 (BackgroundTask)
#   v2.0.0 S03: survey 견적 convert 지원 (company_id NULL 허용)
#              + 설문 견적 전용 /quotes/{id}/convert-survey 엔드포인트 추가

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime
import os
import resend as resend_client
import httpx

from db.supabase_client import get_supabase

router = APIRouter(prefix="/quotes", tags=["quotes"])

API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.taieng.co.kr")


# ============================================================
# 스키마
# ============================================================

class SurveySubmit(BaseModel):
    """필수 연락처·회사만 고정, 나머지 필드는 설문 JSON 전부 허용(extra)."""
    model_config = ConfigDict(extra="allow")

    contact_name:  str
    contact_phone: str
    company_name:  str
    contact_email: Optional[str] = None
    source:        Optional[str] = "survey_web"
    survey_type:   Optional[str] = "legal_diagnosis"


class SurveyConvertRequest(BaseModel):
    """설문 견적 → 계약 전환 (company_id 없이 처리)"""
    plan_code:         Optional[str] = None
    contract_amount:   Optional[int] = None   # None이면 total_amount 사용
    start_date:        Optional[str] = None   # None이면 오늘
    end_date:          Optional[str] = None
    max_factory_count: Optional[int] = 1
    max_user_count:    Optional[int] = 5
    memo:              Optional[str] = None
    activate_now:      bool = False


# ============================================================
# 헬퍼
# ============================================================

def _payload_dict(m: SurveySubmit) -> Dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


def _gen_contract_no() -> str:
    import random
    return f"CON-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"


def _calc_vat(amount: int) -> int:
    return int(amount * 0.1)


# ============================================================
# S02: 법령엔진 자동 실행 (BackgroundTask)
# ============================================================

def _run_legal_engine(quote_id: str):
    """
    설문 접수 완료 후 BackgroundTask로 법령엔진 자동 실행.
    POST /legal-engine/apply-quote/{quote_id} 내부 호출.
    """
    try:
        url = f"{API_BASE_URL}/legal-engine/apply-quote/{quote_id}"
        resp = httpx.post(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            count = data.get("data", {}).get("summary", {}).get("total", 0)
            print(f"[LEGAL ENGINE AUTO] 완료: {quote_id} → {count}건 적용")
        else:
            print(f"[LEGAL ENGINE AUTO] 실패: {quote_id} status={resp.status_code}")
    except Exception as e:
        print(f"[LEGAL ENGINE AUTO] 오류: {quote_id} → {e}")


def send_notification_email(quote_no: str, payload: dict):
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            print("[EMAIL] RESEND_API_KEY 미설정 — 스킵")
            return

        resend_client.api_key = api_key
        notify_email = os.environ.get("NOTIFY_EMAIL", "tai@taieng.co.kr")

        snap = payload.get("survey_snapshot") or {}
        addr = payload.get("address") or snap.get("addr") or ""
        floor_area = payload.get("floor_area")
        if floor_area is None and snap.get("area") is not None:
            try:
                floor_area = float(snap["area"])
            except (TypeError, ValueError):
                floor_area = snap.get("area")

        resend_client.Emails.send({
            "from": "TAI Engineering <noreply@taieng.co.kr>",
            "to": [notify_email],
            "subject": f"[TAI] 새 견적 문의 접수 — {quote_no}",
            "text": f"""새 견적 문의가 접수됐습니다.

접수번호: {quote_no}
담당자명: {payload.get('contact_name', '')}
연락처:   {payload.get('contact_phone', '')}
이메일:   {payload.get('contact_email', '')}
회사명:   {payload.get('company_name', '')}
주소:     {addr}
연면적:   {floor_area}㎡
"""
        })
        print(f"[EMAIL] Resend 발송 성공 → {notify_email} ({quote_no})")

    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


# ============================================================
# 설문 접수 (S02: 법령엔진 자동 실행 추가)
# ============================================================

@router.post("/survey")
def submit_survey(payload: SurveySubmit, background_tasks: BackgroundTasks):
    supabase = get_supabase()

    today = datetime.now().strftime("%Y%m%d")
    try:
        count_res = supabase.table("quotes")\
            .select("id", count="exact")\
            .like("quote_no", f"TAI-{today}-%")\
            .execute()
        seq = (count_res.count or 0) + 1
    except Exception:
        seq = 1

    quote_no = f"TAI-{today}-{seq:04d}"

    full = _payload_dict(payload)
    insert_data: Dict[str, Any] = {
        "quote_no":      quote_no,
        "service_type":  "CONSULTING",
        "status_code":   "REQUESTED",
        "contact_name":  payload.contact_name,
        "contact_phone": payload.contact_phone,
        "contact_email": payload.contact_email or None,
        "company_name":  payload.company_name,
        "source":        payload.source or "survey_web",
        "survey_data":   full,
        "survey_type":   payload.survey_type or "legal_diagnosis",
        "company_id":    None,
        "items":         [],
        "supply_amount": 0,
        "vat_amount":    0,
        "total_amount":  0,
        "is_active":     True,
        "created_at":    datetime.utcnow().isoformat(),
        "updated_at":    datetime.utcnow().isoformat(),
    }

    try:
        res = supabase.table("quotes").insert(insert_data).execute()
        quote_id = res.data[0]["id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")

    # ✅ S02: 법령엔진 자동 실행
    background_tasks.add_task(_run_legal_engine, quote_id)
    # 이메일 알림
    background_tasks.add_task(send_notification_email, quote_no, full)

    return {
        "status": "success",
        "data": {
            "quote_id": quote_id,
            "quote_no": quote_no,
            "message": "접수가 완료됐습니다. 3일 이내 담당자가 연락드립니다."
        }
    }


@router.get("/survey/test")
def survey_test():
    return {"status": "ok", "message": "POST /quotes/survey ready"}


# ============================================================
# S02: 법령엔진 수동 재실행 (어드민용)
# ============================================================

@router.post("/survey/{quote_id}/run-legal-engine")
def rerun_legal_engine(quote_id: str, background_tasks: BackgroundTasks):
    """어드민에서 법령엔진 수동 재실행"""
    supabase = get_supabase()
    q = supabase.table("quotes").select("id, survey_data").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    if not q.data.get("survey_data"):
        raise HTTPException(status_code=400, detail="설문 데이터가 없습니다. 법령진단 설문 견적만 실행 가능합니다.")

    background_tasks.add_task(_run_legal_engine, quote_id)
    return {"status": "success", "message": "법령엔진이 백그라운드에서 실행됩니다."}


# ============================================================
# S03: 설문 견적 → 계약 전환 (company_id=NULL 허용)
# ============================================================

@router.post("/survey/{quote_id}/convert")
def convert_survey_to_contract(quote_id: str, req: SurveyConvertRequest):
    """
    설문 견적(company_id=NULL) → 계약 전환.
    일반 /quotes/{id}/convert와 달리 company_id 없이도 전환 가능.
    법령진단 설문 접수건 전용.
    """
    supabase = get_supabase()
    q = supabase.table("quotes").select("*").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")

    if q.data.get("source") not in ("survey_web", "survey_pro", "survey"):
        raise HTTPException(status_code=400, detail="설문 접수 견적만 이 API를 사용하세요")

    if q.data["status_code"] not in ("REQUESTED", "CONFIRMED"):
        raise HTTPException(status_code=400, detail=f"현재 상태({q.data['status_code']})에서는 계약 전환 불가합니다")

    if q.data.get("contract_id"):
        raise HTTPException(status_code=409, detail="이미 계약이 존재합니다")

    import random
    now = datetime.now()
    amount = req.contract_amount or q.data.get("total_amount") or 0
    vat = _calc_vat(amount)
    start = req.start_date or now.strftime("%Y-%m-%d")
    status = "ACTIVE" if req.activate_now else "PENDING_PAYMENT"

    contract_res = supabase.table("contracts").insert({
        "contract_no":      f"CON-{now.strftime('%Y%m%d')}-{random.randint(1000,9999)}",
        "company_id":       q.data.get("company_id"),   # NULL 허용
        "service_type":     q.data.get("service_type") or "SAAS",
        "plan_code":        req.plan_code,
        "contract_amount":  amount,
        "vat_amount":       vat,
        "total_amount":     amount + vat,
        "status_code":      status,
        "quote_id":         quote_id,
        "start_date":       start,
        "end_date":         req.end_date,
        "max_factory_count": req.max_factory_count,
        "max_user_count":   req.max_user_count,
        "paid_amount":      amount if req.activate_now else 0,
        "paid_at":          now.isoformat() if req.activate_now else None,
        "memo":             req.memo or f"설문 견적({q.data.get('quote_no')})에서 전환",
        "is_active":        True,
        "created_at":       now.isoformat(),
        "updated_at":       now.isoformat(),
    }).execute()

    contract_id = contract_res.data[0]["id"]

    # 견적 상태 업데이트
    supabase.table("quotes").update({
        "status_code": "PENDING_PAYMENT",
        "contract_id": contract_id,
        "updated_at":  now.isoformat(),
    }).eq("id", quote_id).execute()

    msg = "계약이 생성됐습니다" + (" (즉시 활성화)" if req.activate_now else " (입금 대기)")
    return {
        "status": "success",
        "message": msg,
        "data": contract_res.data[0]
    }


# ============================================================
# 견적 조회 (어드민용 — contracts.py의 /quotes와 별개로 survey 전용)
# ============================================================

@router.get("/survey/list")
def list_survey_quotes(
    page:        int = Query(1, ge=1),
    page_size:   int = Query(20, ge=1, le=100),
    status_code: Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
    has_legal:   Optional[bool] = Query(None, description="법령판정 결과 보유 여부"),
):
    """설문 접수 견적 목록 (어드민 quote-list.html 전용)"""
    supabase = get_supabase()

    query = supabase.table("quotes").select(
        "id, quote_no, company_name, contact_name, contact_phone, contact_email, "
        "status_code, source, survey_type, legal_applicable_count, legal_evaluated_at, "
        "contract_id, created_at, updated_at",
        count="exact"
    ).eq("source", "survey_web")

    if status_code:
        query = query.eq("status_code", status_code)
    if search:
        pat = f"%{search}%"
        query = query.or_(
            f"company_name.ilike.{pat},contact_name.ilike.{pat},quote_no.ilike.{pat}"
        )
    if has_legal is True:
        query = query.not_.is_("legal_evaluated_at", "null")
    elif has_legal is False:
        query = query.is_("legal_evaluated_at", "null")

    offset = (page - 1) * page_size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "page_size": page_size,
            "total_pages": ((res.count or 0) + page_size - 1) // page_size,
        }
    }
