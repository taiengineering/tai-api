"""
공개 API 라우터 — 비회원 법령점검 신청
URL: /public/inspection-request
인증: 불필요 (CORS 허용)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import random

from db.supabase_client import get_supabase

router = APIRouter(prefix="/public", tags=["공개 API"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_request_no() -> str:
    return f"TAI-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


class InspectionRequestBody(BaseModel):
    contact_name:  str
    contact_phone: str
    contact_email: Optional[str] = None
    company_name:  str
    sector:        Optional[str] = None
    memo:          Optional[str] = None
    source:        Optional[str] = "direct"   # kmong / direct
    service_type:  Optional[str] = "LEGAL_INSPECTION"


@router.post("/inspection-request")
def create_inspection_request(body: InspectionRequestBody):
    """
    비회원 법령점검 신청 접수
    - 크몽 등 외부 채널 연결용
    - 인증 불필요
    - inspection_requests 테이블에 저장
    """
    if not body.contact_name or not body.contact_name.strip():
        raise HTTPException(status_code=422, detail="담당자명을 입력해 주세요.")
    if not body.contact_phone or not body.contact_phone.strip():
        raise HTTPException(status_code=422, detail="연락처를 입력해 주세요.")
    if not body.company_name or not body.company_name.strip():
        raise HTTPException(status_code=422, detail="회사명을 입력해 주세요.")

    supabase = get_supabase()
    request_no = _gen_request_no()
    now = _now()

    row = {
        "request_no":   request_no,
        "contact_name": body.contact_name.strip(),
        "contact_phone": body.contact_phone.strip(),
        "contact_email": body.contact_email,
        "company_name": body.company_name.strip(),
        "sector":       (body.sector or "").upper() or None,
        "memo":         body.memo,
        "source":       body.source or "direct",
        "service_type": body.service_type or "LEGAL_INSPECTION",
        "status_code":  "NEW",
        "is_active":    True,
        "created_at":   now,
        "updated_at":   now,
    }

    res = supabase.table("inspection_requests").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="신청 접수에 실패했습니다. 잠시 후 다시 시도해 주세요.")

    return {
        "status":  "success",
        "message": "법령점검 신청이 완료되었습니다. 담당자가 1~2 영업일 내 연락드립니다.",
        "data": {
            "request_no":   request_no,
            "contact_name": body.contact_name.strip(),
            "company_name": body.company_name.strip(),
        }
    }


@router.get("/inspection-request/{request_no}")
def get_inspection_request_status(request_no: str):
    """
    신청 접수 번호로 처리 상태 조회 (비회원용)
    """
    supabase = get_supabase()
    res = supabase.table("inspection_requests") \
        .select("request_no, company_name, contact_name, status_code, created_at") \
        .eq("request_no", request_no) \
        .eq("is_active", True) \
        .limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="접수 번호를 찾을 수 없습니다.")

    row = res.data[0]
    STATUS_LABELS = {
        "NEW":         "접수 완료",
        "IN_PROGRESS": "처리 중",
        "DONE":        "완료",
        "CANCELLED":   "취소",
    }

    return {
        "status": "success",
        "data": {
            "request_no":   row["request_no"],
            "company_name": row["company_name"],
            "contact_name": row["contact_name"],
            "status_code":  row["status_code"],
            "status_label": STATUS_LABELS.get(row["status_code"], row["status_code"]),
            "created_at":   row["created_at"],
        }
    }
