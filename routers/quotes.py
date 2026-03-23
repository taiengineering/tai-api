# routers/quotes.py
from fastapi import APIRouter, HTTPException
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


def send_notification_email(quote_no: str, payload: SurveySubmit):
    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", 587))
    smtp_user  = os.getenv("SMTP_USER")
    smtp_pass  = os.getenv("SMTP_PASS")
    notify_to  = os.getenv("NOTIFY_EMAIL", "tai@taieng.co.kr")

    if not smtp_user or not smtp_pass:
        print("[WARN] SMTP not configured")
        return

    equip_list = []
    if payload.equip_electric:  equip_list.append("Electric")
    if payload.equip_gas:       equip_list.append("Gas")
    if payload.equip_fire:      equip_list.append("Fire")
    if payload.equip_elevator:  equip_list.append("Elevator")
    if payload.equip_boiler:    equip_list.append("Boiler")
    if payload.equip_crane:     equip_list.append("Crane")
    if payload.equip_pressure:  equip_list.append("Pressure")
    if payload.equip_chemical:  equip_list.append("Chemical")
    if payload.equip_cold:      equip_list.append("Cold Storage")

    body = (
        f"[TAI Legal Diagnosis Request]\n\n"
        f"Quote No: {quote_no}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Company: {payload.company_name}\n"
        f"Contact: {payload.contact_name}\n"
        f"Phone: {payload.contact_phone}\n"
        f"Email: {payload.contact_email or 'N/A'}\n\n"
        f"Building Type: {payload.building_type or 'N/A'}\n"
        f"Address: {payload.address or 'N/A'}\n"
        f"Floor Area: {payload.floor_area or 'N/A'} m2\n"
        f"Employees: {payload.employee_count or 'N/A'}\n"
        f"Electrical: {payload.electrical_kw or 'N/A'} kW\n\n"
        f"Equipment: {', '.join(equip_list) if equip_list else 'None'}\n"
        f"Hazmat: {'Yes' if payload.hazmat_yn else 'No'}\n"
        f"Night Work: {'Yes' if payload.night_work_yn else 'No'}\n"
        f"Source: {payload.source}\n\n"
        f"Admin: https://admin.taieng.co.kr/quote-list.html\n"
    )

    try:
        # Railway 서버는 한글 호스트명 문제 없음 — name_resolution 직접 지정
        server = smtplib.SMTP(smtp_host, smtp_port, local_hostname="localhost")
        server.ehlo("localhost")
        server.starttls()
        server.ehlo("localhost")
        server.login(smtp_user, smtp_pass)

        # 전체 이메일을 bytes로 직접 구성 (한글 인코딩 완전 우회)
        import email.utils
        boundary = "===============TAI001=="
        raw = (
            f"MIME-Version: 1.0\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Transfer-Encoding: base64\r\n"
            f"From: {smtp_user}\r\n"
            f"To: {notify_to}\r\n"
            f"Subject: =?utf-8?b?{__import__('base64').b64encode(f'[TAI] {quote_no} - {payload.company_name}'.encode('utf-8')).decode()}?=\r\n"
            f"\r\n"
            f"{__import__('base64').b64encode(body.encode('utf-8')).decode()}\r\n"
        )
        server.sendmail(smtp_user, notify_to, raw.encode("ascii"))
        server.quit()
        print(f"[EMAIL] Sent -> {notify_to} ({quote_no})")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


@router.post("/survey")
def submit_survey(payload: SurveySubmit):
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

    send_notification_email(quote_no, payload)

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
