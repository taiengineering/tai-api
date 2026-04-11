# routers/quotes.py — v3.0.0
# v3.0.0 (2026-04-11):
#   - POST /survey: DiagnosisSurveyRequest 스펙 추가 (sector/grade/user_id/form_data)
#   - POST /survey: Authorization Bearer 토큰 처리 (실패해도 관대하게 통과)
#   - POST /survey: public_diagnosis_requests 테이블에 저장 + request_id 응답
# v2.0.0 S02: 설문 접수 후 법령엔진 자동 실행 (BackgroundTask)
# v2.0.0 S03: survey 견적 convert 지원 (company_id NULL 허용)

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Header
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

class DiagnosisSurveyRequest(BaseModel):
    """v3.0.0: new.taieng.co.kr free-diagnosis.html 전용 스펙."""
    model_config = ConfigDict(extra="allow")

    # 섹터 & 등급
    sector:     str               # building / construction / industry
    grade:      Optional[int] = None  # 1 / 2 / 3 (상시근로자 규모)

    # 로그인 사용자 정보 (Bearer 토큰 보조)
    user_id:    Optional[str] = None
    user_name:  Optional[str] = None
    user_email: Optional[str] = None

    # 연락처 & 회사 (필수)
    contact_name:  str
    contact_phone: str
    company_name:  str
    contact_email: Optional[str] = None

    # 섹터별 입력값 전체 (설문 폼 JSON)
    form_data:  Optional[Dict[str, Any]] = None

    # 기존 호환 필드
    source:      Optional[str] = "survey_web"
    survey_type: Optional[str] = "legal_diagnosis"


class SurveySubmit(BaseModel):
    """하위 호환 유지 — 기존 어드민·Kmong 연동 등에서 사용."""
    model_config = ConfigDict(extra="allow")

    contact_name:  str
    contact_phone: str
    company_name:  str
    contact_email: Optional[str] = None
    source:        Optional[str] = "survey_web"
    survey_type:   Optional[str] = "legal_diagnosis"


class SurveyConvertRequest(BaseModel):
    plan_code:         Optional[str] = None
    contract_amount:   Optional[int] = None
    start_date:        Optional[str] = None
    end_date:          Optional[str] = None
    max_factory_count: Optional[int] = 1
    max_user_count:    Optional[int] = 5
    memo:              Optional[str] = None
    activate_now:      bool = False


# ============================================================
# 헬퍼
# ============================================================

def _payload_dict(m) -> Dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


def _gen_no(prefix: str) -> str:
    import random
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"


def _calc_vat(amount: int) -> int:
    return int(amount * 0.1)


def _resolve_user_from_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Bearer 토큰으로 users 테이블 조회. 실패해도 None 반환 (관대 처리)."""
    if not token:
        return None
    try:
        supabase = get_supabase()
        # Supabase access_token → auth.getUser 방식 대신 users 테이블 직접 조회
        # users 테이블에 access_token 컬럼이 없으므로 Supabase Admin API로 uid 추출
        import base64, json
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            uid = payload.get("sub")
            if uid:
                res = supabase.table("users").select(
                    "id, name, email, company_id"
                ).eq("id", uid).maybe_single().execute()
                return res.data if res.data else None
    except Exception as e:
        print(f"[AUTH] 토큰 조회 실패 (관대 처리): {e}")
    return None


# ============================================================
# 법령엔진 BackgroundTask
# ============================================================

def _run_legal_engine(quote_id: str):
    try:
        url = f"{API_BASE_URL}/legal-engine/apply-quote/{quote_id}"
        resp = httpx.post(url, timeout=30)
        if resp.status_code == 200:
            count = resp.json().get("data", {}).get("summary", {}).get("total", 0)
            print(f"[LEGAL ENGINE AUTO] 완료: {quote_id} → {count}건")
        else:
            print(f"[LEGAL ENGINE AUTO] 실패: {quote_id} status={resp.status_code}")
    except Exception as e:
        print(f"[LEGAL ENGINE AUTO] 오류: {quote_id} → {e}")


def send_notification_email(quote_no: str, payload: dict):
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            return
        resend_client.api_key = api_key
        notify_email = os.environ.get("NOTIFY_EMAIL", "tai@taieng.co.kr")
        snap = payload.get("survey_snapshot") or payload.get("form_data") or {}
        addr = payload.get("address") or snap.get("addr") or ""
        resend_client.Emails.send({
            "from": "TAI Engineering <noreply@taieng.co.kr>",
            "to": [notify_email],
            "subject": f"[TAI] 새 진단 접수 — {quote_no}",
            "text": (
                f"새 무료 법령 진단이 접수됐습니다.\n\n"
                f"접수번호: {quote_no}\n"
                f"담당자명: {payload.get('contact_name', '')}\n"
                f"연락처:   {payload.get('contact_phone', '')}\n"
                f"이메일:   {payload.get('contact_email', '')}\n"
                f"회사명:   {payload.get('company_name', '')}\n"
                f"섹터:     {payload.get('sector', '')}\n"
                f"주소:     {addr}\n"
            )
        })
        print(f"[EMAIL] 발송 성공 → {notify_email} ({quote_no})")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


# ============================================================
# v3.0.0: 무료 법령 진단 접수 (new.taieng.co.kr free-diagnosis.html)
# ============================================================

@router.post("/survey")
def submit_survey(
    payload: DiagnosisSurveyRequest,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """
    무료 법령 진단 접수 (v3.0.0).

    - Authorization: Bearer <access_token> 헤더 선택적 수용
    - public_diagnosis_requests 테이블에 저장
    - 응답: { success, data: { request_id, status } }
    """
    supabase = get_supabase()
    now = datetime.utcnow()

    # ── 1. 토큰에서 유저 조회 (관대 처리) ─────────────────────
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user_info = _resolve_user_from_token(token)

    user_id    = payload.user_id    or (user_info.get("id")    if user_info else None)
    user_name  = payload.user_name  or (user_info.get("name")  if user_info else None)
    user_email = payload.user_email or (user_info.get("email") if user_info else payload.contact_email)
    company_id = user_info.get("company_id") if user_info else None

    # ── 2. request_no 생성 ────────────────────────────────────
    today = now.strftime("%Y%m%d")
    try:
        cnt = supabase.table("public_diagnosis_requests")\
            .select("id", count="exact")\
            .like("request_no", f"DR-{today}-%")\
            .execute()
        seq = (cnt.count or 0) + 1
    except Exception:
        seq = 1
    request_no = f"DR-{today}-{seq:04d}"

    # ── 3. form_data 분해 → facility_data / process_data / equipment_data ──
    form_data = payload.form_data or {}
    sector    = (payload.sector or "").lower()

    facility_data  = form_data.get("facility")  or form_data.get("facility_data")  or {}
    process_data   = form_data.get("process")   or form_data.get("process_data")   or {}
    equipment_data = form_data.get("equipment") or form_data.get("equipment_data") or {}

    # form_data 전체를 facility_data에 fallback 저장
    if not facility_data and form_data:
        facility_data = form_data

    # ── 4. public_diagnosis_requests INSERT ───────────────────
    address = (
        form_data.get("address")
        or form_data.get("addr")
        or (form_data.get("facility") or {}).get("address")
        or None
    )

    insert_data: Dict[str, Any] = {
        "request_no":       request_no,
        "request_type":     "FREE_DIAGNOSIS",
        "company_name":     payload.company_name,
        "contact_name":     payload.contact_name,
        "contact_phone":    payload.contact_phone,
        "contact_email":    user_email,
        "sector":           sector,
        "address":          address,
        "facility_data":    facility_data  or None,
        "process_data":     process_data   or None,
        "equipment_data":   equipment_data or None,
        "memo":             f"grade={payload.grade}" if payload.grade else None,
        "source":           payload.source or "survey_web",
        "status_code":      "PENDING",
        "is_active":        True,
        "created_at":       now.isoformat(),
        "updated_at":       now.isoformat(),
    }

    try:
        res = supabase.table("public_diagnosis_requests").insert(insert_data).execute()
        request_id = res.data[0]["id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"진단 접수 저장 실패: {str(e)}")

    # ── 5. quotes 테이블에도 미러 저장 (어드민 견적 리스트 연동) ──
    try:
        today2 = now.strftime("%Y%m%d")
        cnt2 = supabase.table("quotes").select("id", count="exact")\
            .like("quote_no", f"TAI-{today2}-%").execute()
        seq2 = (cnt2.count or 0) + 1
        quote_no = f"TAI-{today2}-{seq2:04d}"

        full = _payload_dict(payload)
        supabase.table("quotes").insert({
            "quote_no":      quote_no,
            "service_type":  "CONSULTING",
            "status_code":   "REQUESTED",
            "contact_name":  payload.contact_name,
            "contact_phone": payload.contact_phone,
            "contact_email": user_email,
            "company_name":  payload.company_name,
            "source":        payload.source or "survey_web",
            "survey_data":   full,
            "survey_type":   payload.survey_type or "legal_diagnosis",
            "company_id":    company_id,
            "items":         [],
            "supply_amount": 0,
            "vat_amount":    0,
            "total_amount":  0,
            "is_active":     True,
            "created_at":    now.isoformat(),
            "updated_at":    now.isoformat(),
        }).execute()
        # 법령엔진 자동 실행은 quotes 기반으로 유지
        background_tasks.add_task(send_notification_email, quote_no, full)
    except Exception as e:
        print(f"[MIRROR] quotes 미러 저장 실패 (무시): {e}")

    # ── 6. 응답 ──────────────────────────────────────────────
    return {
        "success": True,
        "data": {
            "request_id": request_id,
            "request_no": request_no,
            "status":     "pending",
            "message":    "접수가 완료됐습니다. 3일 이내 담당자가 연락드립니다."
        }
    }


@router.get("/survey/test")
def survey_test():
    return {"status": "ok", "message": "POST /quotes/survey v3.0.0 ready"}


# ============================================================
# 법령엔진 수동 재실행 (어드민용)
# ============================================================

@router.post("/survey/{quote_id}/run-legal-engine")
def rerun_legal_engine(quote_id: str, background_tasks: BackgroundTasks):
    supabase = get_supabase()
    q = supabase.table("quotes").select("id, survey_data").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    if not q.data.get("survey_data"):
        raise HTTPException(status_code=400, detail="설문 데이터 없음")
    background_tasks.add_task(_run_legal_engine, quote_id)
    return {"status": "success", "message": "법령엔진이 백그라운드에서 실행됩니다."}


# ============================================================
# 설문 견적 → 계약 전환
# ============================================================

@router.post("/survey/{quote_id}/convert")
def convert_survey_to_contract(quote_id: str, req: SurveyConvertRequest):
    supabase = get_supabase()
    q = supabase.table("quotes").select("*").eq("id", quote_id).single().execute()
    if not q.data:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")
    if q.data.get("source") not in ("survey_web", "survey_pro", "survey"):
        raise HTTPException(status_code=400, detail="설문 접수 견적만 이 API를 사용하세요")
    if q.data["status_code"] not in ("REQUESTED", "CONFIRMED"):
        raise HTTPException(status_code=400, detail=f"현재 상태({q.data['status_code']})에서 전환 불가")
    if q.data.get("contract_id"):
        raise HTTPException(status_code=409, detail="이미 계약이 존재합니다")

    import random
    now = datetime.now()
    amount = req.contract_amount or q.data.get("total_amount") or 0
    vat    = _calc_vat(amount)
    start  = req.start_date or now.strftime("%Y-%m-%d")
    status = "ACTIVE" if req.activate_now else "PENDING_PAYMENT"

    contract_res = supabase.table("contracts").insert({
        "contract_no":      f"CON-{now.strftime('%Y%m%d')}-{random.randint(1000,9999)}",
        "company_id":       q.data.get("company_id"),
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
    supabase.table("quotes").update({
        "status_code": "PENDING_PAYMENT",
        "contract_id": contract_id,
        "updated_at":  now.isoformat(),
    }).eq("id", quote_id).execute()

    msg = "계약 생성" + (" (즉시 활성화)" if req.activate_now else " (입금 대기)")
    return {"status": "success", "message": msg, "data": contract_res.data[0]}


# ============================================================
# 설문 견적 목록 (어드민용)
# ============================================================

@router.get("/survey/list")
def list_survey_quotes(
    page:        int = Query(1, ge=1),
    page_size:   int = Query(20, ge=1, le=100),
    status_code: Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
    has_legal:   Optional[bool] = Query(None),
):
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
        query = query.or_(f"company_name.ilike.{pat},contact_name.ilike.{pat},quote_no.ilike.{pat}")
    if has_legal is True:
        query = query.not_.is_("legal_evaluated_at", "null")
    elif has_legal is False:
        query = query.is_("legal_evaluated_at", "null")

    offset = (page - 1) * page_size
    res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       res.count or 0,
            "page":        page,
            "page_size":   page_size,
            "total_pages": ((res.count or 0) + page_size - 1) // page_size,
        }
    }
