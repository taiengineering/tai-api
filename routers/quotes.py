# routers/quotes.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import resend as resend_client
from supabase import create_client

router = APIRouter(prefix="/quotes", tags=["quotes"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


class SurveySubmit(BaseModel):
    building_type:        Optional[str]   = None
    building_type_custom: Optional[str]   = None
    address:              Optional[str]   = None
    floor_area:           Optional[float] = None
    floors_above:         Optional[int]   = None
    floors_below:         Optional[int]   = None
    built_year:           Optional[int]   = None
    employee_count:       Optional[int]   = None
    electrical_kw:        Optional[float] = None
    equip_electric:       Optional[bool]  = False
    equip_gas:            Optional[bool]  = False
    equip_fire:           Optional[bool]  = False
    equip_elevator:       Optional[bool]  = False
    equip_boiler:         Optional[bool]  = False
    equip_crane:          Optional[bool]  = False
    equip_pressure:       Optional[bool]  = False
    equip_chemical:       Optional[bool]  = False
    equip_cold:           Optional[bool]  = False
    hazmat_yn:            Optional[bool]  = False
    night_work_yn:        Optional[bool]  = False
    outsource_yn:         Optional[bool]  = False
    contact_name:         str
    contact_phone:        str
    contact_email:        Optional[str]   = None
    company_name:         str
    source:               Optional[str]   = "survey_web"
    survey_type:          Optional[str]   = "basic"


def send_notification_email(quote_no: str, payload: dict):
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            print("[EMAIL] RESEND_API_KEY 미설정 — 스킵")
            return

        resend_client.api_key = api_key
        notify_email = os.environ.get("NOTIFY_EMAIL", "tai@taieng.co.kr")

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
주소:     {payload.get('address', '')}
연면적:   {payload.get('floor_area', '')}㎡
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

    insert_data = {
        "quote_no":      quote_no,
        "service_type":  "CONSULTING",
        "status_code":   "REQUESTED",
        "contact_name":  payload.contact_name,
        "contact_phone": payload.contact_phone,
        "contact_email": payload.contact_email,
        "company_name":  payload.company_name,
        "source":        payload.source or "survey_web",
        "survey_data":   payload.dict(),
        "is_active":     True,
        "created_at":    datetime.utcnow().isoformat(),
        "updated_at":    datetime.utcnow().isoformat(),
    }

    try:
        supabase.table("quotes").insert(insert_data).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")

    background_tasks.add_task(send_notification_email, quote_no, payload.dict())

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
