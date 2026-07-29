"""
휴무 캘린더 라우터 — v1.0.0

Goal: G-ms6az4y8-b88c4a
서비스: services/holiday_svc.py (공용 모듈 — 캘린더를 쓰는 모든 기능이 공유)
데이터: org_holiday

API:
  GET    /holidays                 스코프 병합 목록 (법정 + 회사 + 시설)
  POST   /holidays                 사업장 휴무 등록 (source=COMPANY)
  DELETE /holidays/{holiday_id}    사업장 휴무 삭제 (법정공휴일은 삭제 불가)

법정공휴일(source=LEGAL, company_id 없음)은 사업장이 만들지도 지우지도 못한다.
연도별 갱신은 마이그레이션 시드로만 한다(BKP-004 — DDL·시드 git 고정).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.health_registry import register_probe
from services.holiday_svc import get_holidays

router = APIRouter(prefix="/holidays", tags=["휴무 캘린더"])

VERSION = "1.0.0"


class HolidayCreateBody(BaseModel):
    company_id: str
    factory_id: Optional[str] = None      # 지정 시 시설 휴무, 없으면 회사 전체
    holiday_date: str                     # YYYY-MM-DD
    name: str
    note: Optional[str] = None
    created_by: Optional[str] = None


@router.get("")
def list_holidays(
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    date_from:  Optional[str] = Query(None, description="YYYY-MM-DD (기본: 올해 1/1)"),
    date_to:    Optional[str] = Query(None, description="YYYY-MM-DD (기본: 올해 12/31)"),
):
    """법정공휴일 + 사업장 휴무를 병합해 돌려준다."""
    year = date.today().year
    df = date_from or f"{year}-01-01"
    dt = date_to or f"{year}-12-31"
    rows = get_holidays(company_id, factory_id, df, dt)
    rows.sort(key=lambda r: str(r.get("holiday_date")))
    return {"status": "success",
            "data": {"items": rows, "total": len(rows), "date_from": df, "date_to": dt}}


@router.post("")
def create_holiday(body: HolidayCreateBody):
    """사업장 휴무 등록. 법정공휴일은 등록 대상이 아니다(시드로만 관리)."""
    try:
        date.fromisoformat(body.holiday_date)
    except Exception:
        raise HTTPException(status_code=422, detail="holiday_date 는 YYYY-MM-DD 형식이어야 합니다.")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="휴무 이름을 입력하십시오.")

    sb = get_supabase()
    row = {
        "company_id":   body.company_id,
        "factory_id":   body.factory_id,
        "holiday_date": body.holiday_date,
        "name":         body.name.strip(),
        "source":       "COMPANY",
        "note":         body.note,
        "created_by":   body.created_by,
    }
    try:
        res = sb.table("org_holiday").insert(row).execute()
    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise HTTPException(status_code=409, detail="같은 날짜에 같은 이름의 휴무가 이미 있습니다.")
        raise HTTPException(status_code=500, detail="휴무 등록에 실패했습니다. org_holiday 마이그레이션 적용 여부를 확인하십시오.")
    if not res.data:
        raise HTTPException(status_code=500, detail="휴무 등록에 실패했습니다.")
    return {"status": "success", "message": "휴무일이 등록되었습니다.", "data": res.data[0]}


@router.delete("/{holiday_id}")
def delete_holiday(holiday_id: str, company_id: str = Query(..., description="요청 사업장 — 소유 검증용")):
    """사업장 휴무 삭제. 자기 회사 소유(source=COMPANY)만 지울 수 있다."""
    sb = get_supabase()
    cur = sb.table("org_holiday").select("id, company_id, source").eq("id", holiday_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="휴무일을 찾을 수 없습니다.")
    row = cur.data[0]
    if row.get("source") == "LEGAL" or not row.get("company_id"):
        raise HTTPException(status_code=403, detail="법정공휴일은 삭제할 수 없습니다. 연도별 시드로만 관리합니다.")
    if str(row.get("company_id")) != str(company_id):
        raise HTTPException(status_code=403, detail="다른 사업장의 휴무일은 삭제할 수 없습니다.")

    sb.table("org_holiday").delete().eq("id", holiday_id).execute()
    return {"status": "success", "message": "휴무일이 삭제되었습니다.", "data": {"id": holiday_id}}


async def _probe_holidays():
    sb = get_supabase()
    r = sb.table("org_holiday").select("id", count="exact").limit(1).execute()
    return {"holidays_count": r.count or 0}


register_probe(
    "holidays",
    _probe_holidays,
    critical=False,
    desc_ko="휴무 캘린더",
    meta={
        "impacts": [
            {"name": "위험성평가 상시평가 판정", "page": "safe > 위험성평가"},
        ],
        "api": "GET /holidays",
        "code": "routers/holidays.py",
    },
)
