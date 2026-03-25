# routers/quotes.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime
import os
import resend as resend_client

from db.supabase_client import get_supabase

router = APIRouter(prefix="/quotes", tags=["quotes"])


class SurveySubmit(BaseModel):
    """필수 연락처·회사만 고정, 나머지 필드는 설문 JSON 전부 허용(extra)."""

    model_config = ConfigDict(extra="allow")

    contact_name:  str
    contact_phone: str
    company_name:  str
    contact_email: Optional[str] = None
    source:        Optional[str] = "survey_web"
    survey_type:   Optional[str] = "legal_diagnosis"


def _payload_dict(m: SurveySubmit) -> Dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


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
        "quote_no":       quote_no,
        "service_type":   "CONSULTING",
        "status_code":    "REQUESTED",
        "contact_name":   payload.contact_name,
        "contact_phone":  payload.contact_phone,
        "contact_email":  payload.contact_email or None,
        "company_name":   payload.company_name,
        "source":         payload.source or "survey_web",
        "survey_data":    full,
        "company_id":     None,
        "items":          [],
        "supply_amount":  0,
        "vat_amount":     0,
        "total_amount":   0,
        "is_active":      True,
        "created_at":     datetime.utcnow().isoformat(),
        "updated_at":     datetime.utcnow().isoformat(),
    }

    try:
        supabase.table("quotes").insert(insert_data).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")

    background_tasks.add_task(send_notification_email, quote_no, full)

    return {
        "status": "success",
        "data": {
            "quote_no": quote_no,
            "message": "접수가 완료됐습니다. 3일 이내 담당자가 연락드립니다."
        }
    }


@router.get("/survey/test")
def survey_test():
    return {"status": "ok", "message": "POST /quotes/survey ready"}
