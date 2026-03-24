# routers/quotes.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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


SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASS   = os.getenv("SMTP_PASS")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "tai@taieng.co.kr")


def send_notification_email(quote_no: str, payload: SurveySubmit):
    try:
        if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
            print("[EMAIL] SMTP 미설정 — 발송 스킵")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[TAI] 새 견적 문의 접수 — {quote_no}"
        msg["From"]    = SMTP_USER
        msg["To"]      = NOTIFY_EMAIL

        body = (
            f"새 견적 문의가 접수됐습니다.\n\n"
            f"견적번호: {quote_no}\n"
            f"접수시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"업체명:   {payload.company_name}\n"
            f"담당자:   {payload.contact_name}\n"
            f"연락처:   {payload.contact_phone}\n"
            f"이메일:   {payload.contact_email or 'N/A'}\n\n"
            f"건물유형: {payload.building_type or 'N/A'}\n"
            f"주소:     {payload.address or 'N/A'}\n"
            f"연면적:   {payload.floor_area or 'N/A'} m2\n"
            f"근로자수: {payload.employee_count or 'N/A'}명\n"
            f"전기용량: {payload.electrical_kw or 'N/A'} kW\n\n"
            f"출처:     {payload.source}\n\n"
            f"관리자:   https://admin.taieng.co.kr/quote-list.html\n"
        )

        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())

        print(f"[EMAIL] 발송 성공 → {NOTIFY_EMAIL}")

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

    background_tasks.add_task(send_notification_email, quote_no, payload)

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
