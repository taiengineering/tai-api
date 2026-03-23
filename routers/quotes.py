# routers/quotes.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from supabase import create_client

router = APIRouter(prefix="/quotes", tags=["quotes"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# Pydantic 모델
# ============================================================

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


# ============================================================
# 이메일 발송
# ============================================================

def send_notification_email(quote_no: str, payload: SurveySubmit):
    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", 587))
    smtp_user  = os.getenv("SMTP_USER")
    smtp_pass  = os.getenv("SMTP_PASS")
    notify_to  = os.getenv("NOTIFY_EMAIL", "tai@taieng.co.kr")

    if not smtp_user or not smtp_pass:
        print("[WARN] SMTP 환경변수 미설정 — 이메일 발송 건너뜀")
        return

    equip_list = []
    if payload.equip_electric:  equip_list.append("전기설비")
    if payload.equip_gas:       equip_list.append("가스설비")
    if payload.equip_fire:      equip_list.append("소방설비")
    if payload.equip_elevator:  equip_list.append("승강기")
    if payload.equip_boiler:    equip_list.append("보일러")
    if payload.equip_crane:     equip_list.append("크레인/호이스트")
    if payload.equip_pressure:  equip_list.append("압력용기")
    if payload.equip_chemical:  equip_list.append("화학물질")
    if payload.equip_cold:      equip_list.append("냉동냉장설비")

    ops_list = []
    if payload.hazmat_yn:     ops_list.append("위험물 취급")
    if payload.night_work_yn: ops_list.append("야간작업")
    if payload.outsource_yn:  ops_list.append("외주/도급")

    body = (
        f"[법적진단 신청 접수]\n\n"
        f"접수번호: {quote_no}\n"
        f"접수시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"회사명:   {payload.company_name}\n"
        f"담당자:   {payload.contact_name}\n"
        f"연락처:   {payload.contact_phone}\n"
        f"이메일:   {payload.contact_email or '미입력'}\n\n"
        f"건물용도: {payload.building_type or '미입력'}\n"
        f"주소:     {payload.address or '미입력'}\n"
        f"연면적:   {payload.floor_area or '미입력'} m2\n"
        f"층수:     지상 {payload.floors_above or '-'}층 / 지하 {payload.floors_below or '-'}층\n"
        f"근로자수: {payload.employee_count or '미입력'}명\n"
        f"수전용량: {payload.electrical_kw or '미입력'} kW\n\n"
        f"설비현황: {', '.join(equip_list) if equip_list else '없음'}\n"
        f"운영현황: {', '.join(ops_list) if ops_list else '없음'}\n"
        f"출처:     {payload.source}\n\n"
        f"Admin 확인: https://admin.taieng.co.kr/quote-list.html\n"
    )

    # 한글 제목 인코딩 처리
    subject_text = f"[TAI 신규접수] {quote_no} - {payload.company_name}"
    subject = Header(subject_text, "utf-8")

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = notify_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, notify_to, msg.as_bytes())
        print(f"[EMAIL] 발송 완료 -> {notify_to} ({quote_no})")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


# ============================================================
# POST /quotes/survey — 비회원 설문 제출
# ============================================================

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


# ============================================================
# GET /quotes/survey/test
# ============================================================

@router.get("/survey/test")
def survey_test():
    return {"status": "ok", "message": "POST /quotes/survey ready"}
