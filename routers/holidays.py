"""
휴무·작업일 캘린더 라우터 — v1.2.0

Goal: G-ms6az4y8-b88c4a(휴무) / G-ms6skzj3(공식 동기화) / G-ms6zml74-76dbad(조업요일)
서비스: services/holiday_svc.py (조회·판정 공용 모듈)
        services/holiday_sync_svc.py (특일정보 API 동기화)
데이터: org_holiday(휴무), org_work_policy(조업요일)

v1.2.0 (2026-07-30) — 조업요일 정책 API
  GET/PUT /work-policy 추가. 사업장/시설의 조업요일(work_weekdays, ISO 1~7)을 조회·설정한다.
  '작업일' 판정(상시평가 3호·점검 일정)이 이 정책을 쓴다. 미설정 시 월~금 폴백.

v1.1.0 (2026-07-30) — 공휴일 공식 API 동기화 (POST /holidays/sync)

API:
  GET    /holidays                 스코프 병합 목록 (법정 + 회사 + 시설)
  POST   /holidays                 사업장 휴무 등록 (source=COMPANY)
  DELETE /holidays/{holiday_id}    사업장 휴무 삭제 (법정공휴일은 삭제 불가)
  POST   /holidays/sync            공휴일 공식 API 동기화 (LEGAL 교체)
  GET    /work-policy              조업요일 정책 조회 (미설정 시 기본 월~금)
  PUT    /work-policy              조업요일 정책 설정 (upsert)
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.health_registry import register_probe
from services.holiday_svc import DEFAULT_WORK_WEEKDAYS, get_holidays, get_work_weekdays
from services.holiday_sync_svc import HolidaySyncError, sync_year
from services.time import business_today

router = APIRouter(prefix="", tags=["휴무·작업일 캘린더"])

VERSION = "1.2.0"

_WD_LABEL = {1: "월", 2: "화", 3: "수", 4: "목", 5: "금", 6: "토", 7: "일"}


class HolidayCreateBody(BaseModel):
    company_id: str
    factory_id: Optional[str] = None      # 지정 시 시설 휴무, 없으면 회사 전체
    holiday_date: str                     # YYYY-MM-DD
    name: str
    note: Optional[str] = None
    created_by: Optional[str] = None


class WorkPolicyBody(BaseModel):
    company_id: str
    factory_id: Optional[str] = None
    work_weekdays: List[int]              # ISO 1=월 … 7=일
    note: Optional[str] = None
    created_by: Optional[str] = None


# ── 공휴일 동기화 (고정경로) ──────────────────────────────────────

@router.post("/holidays/sync")
def sync_holidays(
    year: Optional[int] = Query(None, description="동기화 대상 연도(기본: 올해)"),
    created_by: Optional[str] = Query(None),
):
    """공휴일 공식 API(한국천문연구원 특일정보)로 LEGAL 공휴일을 교체 동기화."""
    target = year or business_today().year
    try:
        result = sync_year(target, created_by)
    except HolidaySyncError as e:
        raise HTTPException(status_code=502, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"동기화 실패: {e}")
    return {"status": "success", "message": f"{target}년 공휴일 {result['inserted']}건 동기화", "data": result}


# ── 조업요일 정책 ────────────────────────────────────────────────

@router.get("/work-policy")
def get_work_policy(
    company_id: str = Query(...),
    factory_id: Optional[str] = Query(None),
):
    """조업요일 정책 조회. 미설정/테이블 미적용 시 기본 월~금 폴백."""
    wd = sorted(get_work_weekdays(company_id, factory_id))
    is_default = set(wd) == set(DEFAULT_WORK_WEEKDAYS)
    return {"status": "success", "data": {
        "company_id": company_id, "factory_id": factory_id,
        "work_weekdays": wd,
        "work_weekdays_label": "·".join(_WD_LABEL[n] for n in wd),
        "is_default": is_default,
    }}


@router.put("/work-policy")
def set_work_policy(body: WorkPolicyBody):
    """조업요일 정책 설정(스코프당 1건 upsert)."""
    wd = sorted({int(n) for n in body.work_weekdays if 1 <= int(n) <= 7})
    if not wd:
        raise HTTPException(status_code=422, detail="조업요일을 하나 이상 선택하십시오(ISO 1=월 … 7=일).")

    sb = get_supabase()
    try:
        q = (sb.table("org_work_policy").select("id")
             .eq("company_id", body.company_id))
        q = q.is_("factory_id", "null") if not body.factory_id else q.eq("factory_id", body.factory_id)
        existing = q.limit(1).execute().data or []

        payload = {
            "company_id": body.company_id,
            "factory_id": body.factory_id,
            "work_weekdays": wd,
            "note": body.note,
        }
        if existing:
            payload["updated_at"] = "now()"
            res = (sb.table("org_work_policy").update(
                {"work_weekdays": wd, "note": body.note})
                .eq("id", existing[0]["id"]).execute())
        else:
            payload["created_by"] = body.created_by
            res = sb.table("org_work_policy").insert(payload).execute()
    except Exception as e:
        msg = str(e).lower()
        if any(h in msg for h in ("does not exist", "relation", "42p01", "schema cache")):
            raise HTTPException(status_code=409,
                                detail="org_work_policy 스키마가 아직 적용되지 않았습니다. 마이그레이션 적용 후 다시 시도하세요.")
        raise HTTPException(status_code=500, detail=f"조업요일 설정 실패: {e}")

    row = (res.data or [{}])[0]
    return {"status": "success", "message": "조업요일이 설정되었습니다. 상시평가 작업일 판정에 반영됩니다.",
            "data": {**row, "work_weekdays_label": "·".join(_WD_LABEL[n] for n in wd)}}


# ── 휴무 조회/등록/삭제 ───────────────────────────────────────────

@router.get("/holidays")
def list_holidays(
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    date_from:  Optional[str] = Query(None, description="YYYY-MM-DD (기본: 올해 1/1)"),
    date_to:    Optional[str] = Query(None, description="YYYY-MM-DD (기본: 올해 12/31)"),
):
    """법정공휴일 + 사업장 휴무를 병합해 돌려준다."""
    year = business_today().year
    df = date_from or f"{year}-01-01"
    dt = date_to or f"{year}-12-31"
    rows = get_holidays(company_id, factory_id, df, dt)
    rows.sort(key=lambda r: str(r.get("holiday_date")))
    return {"status": "success",
            "data": {"items": rows, "total": len(rows), "date_from": df, "date_to": dt}}


@router.post("/holidays")
def create_holiday(body: HolidayCreateBody):
    """사업장 휴무 등록. 법정공휴일은 등록 대상이 아니다(동기화/시드로만 관리)."""
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


@router.delete("/holidays/{holiday_id}")
def delete_holiday(holiday_id: str, company_id: str = Query(..., description="요청 사업장 — 소유 검증용")):
    """사업장 휴무 삭제. 자기 회사 소유(source=COMPANY)만 지울 수 있다."""
    sb = get_supabase()
    cur = sb.table("org_holiday").select("id, company_id, source").eq("id", holiday_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="휴무일을 찾을 수 없습니다.")
    row = cur.data[0]
    if row.get("source") == "LEGAL" or not row.get("company_id"):
        raise HTTPException(status_code=403, detail="법정공휴일은 삭제할 수 없습니다. 동기화/시드로만 관리합니다.")
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
    desc_ko="휴무·작업일 캘린더",
    meta={
        "impacts": [
            {"name": "위험성평가 상시평가 판정", "page": "safe > 위험성평가"},
        ],
        "api": "GET /holidays",
        "code": "routers/holidays.py",
    },
)
