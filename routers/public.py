"""
공개 API 라우터 — 비회원 법령진단 신청 (3개 모듈)
URL prefix: /public
인증: 불필요 (CORS 허용)

모듈:
  v1 = 법령진단  (시설조건 기반)
  v2 = 공정진단  (KCSC 공정 선택)
  v3 = 설비진단  (설비 선택)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import random

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

router = APIRouter(prefix="/public", tags=["공개 API"])

STATUS_LABELS = {
    "NEW":         "접수 완료",
    "IN_PROGRESS": "분석 중",
    "DONE":        "결과 발송 완료",
    "CANCELLED":   "취소",
}


def _now() -> str:
    return serialize_external_utc(now_kst())


def _gen_request_no(type_code: str) -> str:
    prefix = {"v1": "D1", "v2": "D2", "v3": "D3"}.get(type_code, "DX")
    return f"TAI-{prefix}-{now_kst().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


# ─────────────────────────────────────────────────
# 공통 모델
# ─────────────────────────────────────────────────

class DiagnosisRequestBody(BaseModel):
    request_type:   str                        # v1 / v2 / v3
    # 회사 정보
    company_name:   str
    biz_no:         Optional[str] = None       # 사업자번호
    address:        Optional[str] = None       # 주소
    address_detail: Optional[str] = None
    contact_name:   str
    contact_phone:  str
    contact_email:  Optional[str] = None
    # 시설 조건
    sector:         Optional[str] = None
    facility_data:  Optional[Dict[str, Any]] = None   # 시설 상세
    process_data:   Optional[Dict[str, Any]] = None   # v2: 공정 목록
    equipment_data: Optional[Dict[str, Any]] = None   # v3: 설비 목록
    memo:           Optional[str] = None
    source:         Optional[str] = "direct"


# ─────────────────────────────────────────────────
# POST /public/diagnosis-request  — 신청 접수
# ─────────────────────────────────────────────────

@router.post("/diagnosis-request")
def create_diagnosis_request(body: DiagnosisRequestBody):
    """
    비회원 법령진단 신청 접수 (v1/v2/v3 공통)
    public_diagnosis_requests 테이블에 저장.
    """
    if body.request_type not in ("v1", "v2", "v3"):
        raise HTTPException(status_code=422, detail="request_type은 v1/v2/v3 중 하나여야 합니다.")
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=422, detail="회사명을 입력해 주세요.")
    if not (body.contact_name or "").strip():
        raise HTTPException(status_code=422, detail="담당자명을 입력해 주세요.")
    if not (body.contact_phone or "").strip():
        raise HTTPException(status_code=422, detail="연락처를 입력해 주세요.")

    supabase    = get_supabase()
    request_no  = _gen_request_no(body.request_type)
    now         = _now()

    row = {
        "request_no":     request_no,
        "request_type":   body.request_type,
        "company_name":   body.company_name.strip(),
        "biz_no":         (body.biz_no or "").strip() or None,
        "address":        body.address,
        "address_detail": body.address_detail,
        "contact_name":   body.contact_name.strip(),
        "contact_phone":  body.contact_phone.strip(),
        "contact_email":  body.contact_email,
        "sector":         (body.sector or "").upper() or None,
        "facility_data":  body.facility_data or {},
        "process_data":   body.process_data  or {},
        "equipment_data": body.equipment_data or {},
        "memo":           body.memo,
        "source":         body.source or "direct",
        "status_code":    "NEW",
        "is_active":      True,
        "created_at":     now,
        "updated_at":     now,
    }

    res = supabase.table("public_diagnosis_requests").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="신청 접수에 실패했습니다. 잠시 후 다시 시도해 주세요.")

    type_labels = {"v1": "법령진단", "v2": "공정진단", "v3": "설비진단"}
    return {
        "status":  "success",
        "message": f"{type_labels.get(body.request_type, '')} 신청이 완료되었습니다. 영업일 기준 3일 이내에 결과를 보내드립니다.",
        "data": {
            "request_no":    request_no,
            "request_type":  body.request_type,
            "company_name":  body.company_name.strip(),
            "contact_name":  body.contact_name.strip(),
        },
    }


# ─────────────────────────────────────────────────
# GET /public/diagnosis-request/{request_no}
# ─────────────────────────────────────────────────

@router.get("/diagnosis-request/{request_no}")
def get_diagnosis_request_status(request_no: str):
    """신청 번호로 처리 상태 조회 (비회원용)"""
    supabase = get_supabase()
    res = supabase.table("public_diagnosis_requests") \
        .select("request_no, request_type, company_name, contact_name, status_code, created_at, result_sent_at") \
        .eq("request_no", request_no) \
        .eq("is_active", True) \
        .limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="접수 번호를 찾을 수 없습니다.")

    row = res.data[0]
    type_labels = {"v1": "법령진단", "v2": "공정진단", "v3": "설비진단"}

    return {
        "status": "success",
        "data": {
            "request_no":    row["request_no"],
            "request_type":  row["request_type"],
            "type_label":    type_labels.get(row["request_type"], row["request_type"]),
            "company_name":  row["company_name"],
            "contact_name":  row["contact_name"],
            "status_code":   row["status_code"],
            "status_label":  STATUS_LABELS.get(row["status_code"], row["status_code"]),
            "created_at":    row["created_at"],
            "result_sent_at": row.get("result_sent_at"),
        },
    }


# ─────────────────────────────────────────────────
# 기존 inspection-request (하위 호환 유지)
# ─────────────────────────────────────────────────

class InspectionRequestBody(BaseModel):
    contact_name:  str
    contact_phone: str
    contact_email: Optional[str] = None
    company_name:  str
    sector:        Optional[str] = None
    memo:          Optional[str] = None
    source:        Optional[str] = "direct"
    service_type:  Optional[str] = "LEGAL_INSPECTION"


@router.post("/inspection-request")
def create_inspection_request(body: InspectionRequestBody):
    """[구버전 호환] inspection_requests 테이블 저장"""
    if not (body.contact_name or "").strip():
        raise HTTPException(status_code=422, detail="담당자명을 입력해 주세요.")
    if not (body.contact_phone or "").strip():
        raise HTTPException(status_code=422, detail="연락처를 입력해 주세요.")
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=422, detail="회사명을 입력해 주세요.")

    supabase   = get_supabase()
    request_no = f"TAI-{now_kst().strftime('%Y%m%d')}-{random.randint(1000,9999)}"
    now        = _now()

    try:
        res = supabase.table("inspection_requests").insert({
            "request_no":    request_no,
            "contact_name":  body.contact_name.strip(),
            "contact_phone": body.contact_phone.strip(),
            "contact_email": body.contact_email,
            "company_name":  body.company_name.strip(),
            "sector":        (body.sector or "").upper() or None,
            "memo":          body.memo,
            "source":        body.source or "direct",
            "service_type":  body.service_type or "LEGAL_INSPECTION",
            "status_code":   "NEW",
            "is_active":     True,
            "created_at":    now,
            "updated_at":    now,
        }).execute()
        if not res.data:
            raise Exception("insert failed")
    except Exception:
        raise HTTPException(status_code=500, detail="신청 접수에 실패했습니다.")

    return {
        "status":  "success",
        "message": "법령점검 신청이 완료되었습니다.",
        "data": {"request_no": request_no, "company_name": body.company_name.strip()},
    }


@router.get("/inspection-request/{request_no}")
def get_inspection_request_status(request_no: str):
    """[구버전 호환] 상태 조회"""
    supabase = get_supabase()
    res = supabase.table("inspection_requests") \
        .select("request_no, company_name, contact_name, status_code, created_at") \
        .eq("request_no", request_no).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="접수 번호를 찾을 수 없습니다.")
    row = res.data[0]
    return {
        "status": "success",
        "data": {
            **row,
            "status_label": STATUS_LABELS.get(row["status_code"], row["status_code"]),
        },
    }
