"""
점검리스트 시스템 — v1.5.0
v1.5.0: 인증·회사 스코프 (Wave3, 직접MCP)
  - 전 엔드포인트 로그인 필수(get_current_user).
  - factory 직결: generate-items/generate-schedules/status/schedules(factory_id) → _ensure_factory_own
  - work_schedule 경유: start/complete → _ensure_ws_own(행 company_id 소유확인)
  - inspection 경유: result/{id}/items → _ensure_inspection_own(assignment→work_schedule.company_id)
  - 무path 목록(GET /schedules): _own_factory_ids 로 자사 factory 제한(P13, 전사노출 차단)
  - 소유가드는 try 앞(404가 500으로 삼켜지는 것 방지). 비즈니스 로직 verbatim.
v1.4.0: Rolling 완료 후 다음 회차 자동 생성
  - complete/{id}: 완료 시점에 다음 planned_date 1건 자동 INSERT
  - schedule_end_date 있으면 다음 회차가 그 날짜 넘으면 생성 안 함
  - schedule_end_date 없으면 무한 반복
  - 다음 회차 assigned_user_id=NULL (배정은 안전관리자 추후 시행)
  - COMPLETED 상태 절대 수정 안 함
v1.3.0: skipped_anchor 응답 필드
v1.2.0: anchor_confirmed=True 필터 + sets_skipped
v1.1.0: /status count 쿼리 4개 분리
prefix: /inspection
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone, date, timedelta
import calendar

from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import (
    _scope,
    _is_admin,
    _ensure_own_company,
    _ensure_factory_own,
)
from services.status_vocab import (
    normalize_inspection_result_write,
    ws_completed_query_values,
)
from services.inspection_record_writer_bridge import (
    complete_inspection_status,
    InspectionStatusWriteError,
)
from services.inspection_record_start import (
    start_safe_inspection,
    SafeStartError,
)
from services.safe_inspection_result_batch import (
    record_safe_result_batch,
    SafeResultBatchError,
)
from services.inspection_rolling import ensure_next_rolling_schedule

router = APIRouter(prefix="/inspection", tags=["점검리스트"])

VERSION = "1.5.0"

LEGAL_INSPECTION_ITEMS = {
    "ELECACT-010":    ["배전반 외관 점검", "접지 상태 확인", "절연저항 측정", "과전류 차단기 동작 확인"],
    "ELECSAFEDC-002": ["월간 전기설비 육안 점검", "단자 조임 상태 확인", "발열 여부 확인"],
    "ELECSAFEDC-003": ["연간 전기설비 정기점검", "절연저항 측정", "보호계전기 시험"],
    "ELECBIZ-001":    ["사용전 검사 서류 확인", "설비 설치 상태 확인"],
    "ELECBIZ-002":    ["정기검사 서류 제출", "설비 이상 여부 확인"],
    "ELECRULE-001":   ["전기설비 안전점검 실시", "점검 결과 기록"],
    "ELECRULE-002":   ["정밀안전진단 실시", "진단 보고서 작성"],
    "FIREACT-010":    ["소화기 압력 확인", "소화기 위치 확인", "소화전 수압 점검", "자동화재탐지설비 작동 테스트"],
    "FIREACT-011":    ["소방시설 작동기능 점검 실시", "점검표 작성", "관할 소방서 통보"],
    "FIREACT-005":    ["소방시설 작동기능 점검 실시", "스프링클러 헤드 확인", "감지기 작동 테스트"],
    "FIREPREDC-002":  ["소방훈련 계획 수립", "훈련 실시", "훈련 결과 기록"],
    "FIREPREACT-001": ["화재예방안전진단 신청", "진단 실시", "결과 보고"],
    "FIRECONST-001":  ["소방시설 완공검사 신청"],
    "FIRECONST-002":  ["소방시설 중간점검 실시"],
    "ELEVACT-010":    ["승강기 연간 안전검사 신청", "검사 결과 확인"],
    "ELEVACT-002":    ["승강기 자체점검 실시", "작동 상태 확인", "비상통화 장치 점검", "문 개폐 동작 확인"],
    "ELEVACT-003":    ["정밀안전검사 신청", "검사 결과 수령"],
    "ELEVRULE-001":   ["승강기 사용검사 신청"],
    "ELEVRULE-002":   ["승강기 안전검사 실시", "검사 합격증 보관"],
    "ELEVSTD-003":    ["승강기 월간 안전점검 실시", "이상 여부 기록"],
    "BLDMGT-001":     ["건축물 정기점검 신청", "점검 실시", "결과 보고"],
    "BLDMGT-003":     ["건축물 안전진단 실시", "진단 보고서 제출"],
    "BLDACT-001":     ["건축물 정기점검 실시"],
    "BLDACT-002":     ["건축물 안전진단 실시"],
    "BLDMGTDC-001":   ["건축물 정기점검 실시", "점검 결과 기록"],
    "BLDDEC-001":     ["건축물 정기점검 실시"],
    "BLDRULE2-003":   ["내진설계 건축물 점검"],
    "OSHACT-010":     ["위험성평가 실시", "평가 결과 기록", "개선 조치 이행"],
    "OSHACT-008":     ["근로자 안전보건교육 실시", "교육 일지 작성", "교육 확인서 보관"],
    "OSHEMPH-001":    ["위험성평가 반기 재검토 실시", "변경 사항 반영"],
    "OSHSTD-003":     ["작업환경 측정 신청", "측정 결과 확인", "결과 보고 및 보관"],
    "OSHSTD-004":     ["특수건강진단 실시", "진단 결과 확인"],
    "OSHSTD-006":     ["크레인 사용 전 점검", "와이어 로프 상태 확인", "제동장치 점검"],
    "OSHSTD-007":     ["국소배기장치 점검 실시", "흡입 성능 확인"],
    "OSHRULE-001":    ["일반건강진단 실시", "진단 결과 확인"],
    "OSHHIGH-004":    ["근골격계 유해요인 조사 실시"],
    "OSHEDU-001":     ["관리감독자 안전보건교육 실시", "16시간 이수 확인"],
    "OSHNOTICE-003":  ["관리감독자 교육 이수 확인"],
    "GASACT-001":     ["가스설비 정기검사 신청", "검사 합격증 수령"],
    "GASACT-002":     ["가스누출 감지기 작동 확인", "배관 누출 점검"],
    "ENERGYACT-003":  ["보일러 설치검사 신청"],
    "ENERGYACT-004":  ["보일러 계속사용검사 신청", "검사 결과 확인"],
    "ENERGYRULE-001": ["열사용기자재 설치 검사 신청"],
    "AIRACT-002":     ["대기환경 자가측정 실시", "측정 결과 기록", "보고"],
    "FACTSAFE-001":   ["1종 시설물 정기안전점검 신청", "점검 실시"],
    "FACTSAFE-002":   ["2종 시설물 정기안전점검 실시"],
    "FACTSAFE-003":   ["정밀안전점검 실시"],
    "FACTSAFE-004":   ["정밀안전진단 실시"],
    "SERIOUSDC-002":  ["안전보건 이행상황 점검 실시", "이행 결과 기록"],
    "CONMACT-001":    ["건설기계 정기검사 신청"],
    "CONMSAFE-002":   ["건설기계 자체검사 실시"],
    "CONMDC-002":     ["건설기계 정기검사 실시"],
    "MECHFAC-002":    ["기계설비 성능점검 신청", "점검 결과 확인"],
    "MECHFACDC-001":  ["기계설비 정기점검 실시"],
    "WATERLAW-001":   ["급수시설 위생검사 실시"],
    "SEWAGEACT-002":  ["개인하수처리시설 정기점검 실시"],
    "SEWAGEDC-001":   ["방류수 수질검사 실시"],
    "PARKING-003":    ["주차장 안전점검 실시"],
    "MCHPARK-001":    ["기계식주차장치 정기검사 신청"],
    "ACCESS-002":     ["편의시설 실태조사 실시"],
    "ICTADD-002":     ["통신설비 성능점검 실시"],
    "ELECBIZ-003":    ["변압기 전기안전점검 실시"],
    "ENVADD-004":     ["하수처리시설 수질검사 실시"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_cycle(base: date, cycle_unit: str, cycle_value: int) -> date:
    """base + cycle → 다음 날짜."""
    unit = cycle_unit.lower()
    if unit == "day":        return base + timedelta(days=cycle_value)
    if unit == "week":       return base + timedelta(weeks=cycle_value)
    if unit in ("month", "quarter", "half_year"):
        months = cycle_value if unit == "month" else (3 if unit == "quarter" else 6)
        return base + relativedelta(months=months)
    # year / 기타
    try:    return base + relativedelta(years=cycle_value)
    except: return base + relativedelta(years=1)


def _calc_schedule_dates(start_date: date, end_date: date, cycle_unit: str, cycle_value: int) -> list:
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        if cycle_unit == "day":
            current += timedelta(days=cycle_value)
        elif cycle_unit == "week":
            current += timedelta(weeks=cycle_value)
        elif cycle_unit == "month":
            month = current.month - 1 + cycle_value
            year  = current.year + month // 12
            month = month % 12 + 1
            current = date(year, month, min(current.day, calendar.monthrange(year, month)[1]))
        elif cycle_unit == "year":
            try:    current = date(current.year + cycle_value, current.month, current.day)
            except: current = date(current.year + cycle_value, current.month, 28)
        else: break
    return dates


# ── 인증·회사 스코프 헬퍼 (P13, 로컬 정의 — company_scope.py 는 ADDITIVE만) ──

def _own_factory_ids(sb, current):
    """ALL→None(전체) / 무회사→[] / else 자사 factory id 목록."""
    if _is_admin(_scope(sb, current.get("role_code"))):
        return None
    cid = current.get("company_id")
    if not cid:
        return []
    r = sb.table("factories").select("id").eq("company_id", cid).execute()
    return [row["id"] for row in (r.data or [])]


def _ensure_ws_own(sb, work_schedule_id, current):
    """work_schedule 소유확인(행 company_id 경유). 없으면/타사면 404."""
    r = sb.table("work_schedules").select("id, company_id").eq("id", work_schedule_id).limit(1).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")
    _ensure_own_company(r.data[0].get("company_id"), current, sb, "점검 일정을 찾을 수 없습니다.")


def _ensure_inspection_own(sb, inspection_id, current):
    """safety_inspection → assignment(work_schedule) → company 경유 소유확인."""
    insp = sb.table("safety_inspections").select("id, assignment_id").eq("id", inspection_id).limit(1).execute()
    if not insp.data:
        raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")
    if _is_admin(_scope(sb, current.get("role_code"))):
        return
    ws_id = insp.data[0].get("assignment_id")
    ws = sb.table("work_schedules").select("company_id").eq("id", ws_id).limit(1).execute()
    if not ws.data or ws.data[0].get("company_id") != current.get("company_id"):
        raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")


@router.post("/generate-items/{factory_id}")
async def generate_inspection_items(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        sets_res = supabase.table("inspection_sets").select(
            "id, inspection_set_code, inspection_set_name, law_name"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").execute()
        sets = sets_res.data or []
        if not sets:
            raise HTTPException(status_code=404, detail="점검 세트가 없습니다. 먼저 법령엔진을 실행하세요.")
        for sid in [s["id"] for s in sets]:
            supabase.table("inspection_set_items").delete().eq("inspection_set_id", sid).execute()
        now = _now_iso()
        insert_rows, matched, default = [], 0, 0
        for s in sets:
            code     = s.get("inspection_set_code", "")
            law_name = s.get("law_name", s.get("inspection_set_name", ""))
            items    = LEGAL_INSPECTION_ITEMS.get(code)
            if items:
                matched += 1
                for seq, item_name in enumerate(items, start=1):
                    insert_rows.append({"inspection_set_id": s["id"], "item_seq": seq,
                                        "item_name": item_name, "is_required": True, "is_active": True, "created_at": now})
            else:
                default += 1
                insert_rows.append({"inspection_set_id": s["id"], "item_seq": 1,
                                    "item_name": f"{law_name} 점검 실시", "is_required": True, "is_active": True, "created_at": now})
        created = 0
        for i in range(0, len(insert_rows), 50):
            res = supabase.table("inspection_set_items").insert(insert_rows[i:i+50]).execute()
            created += len(res.data or [])
        return {"status": "success", "message": f"{created}개 점검 항목이 생성됐습니다.",
                "data": {"factory_id": factory_id, "sets_total": len(sets), "sets_matched": matched,
                         "sets_default": default, "items_created": created}}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-schedules/{factory_id}")
async def generate_schedules(factory_id: str, body: Optional[dict] = None, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        body = body or {}
        start_str = body.get("start_date") or date.today().isoformat()
        months    = int(body.get("months", 12))
        start_dt  = date.fromisoformat(start_str)
        end_month = start_dt.month - 1 + months
        end_year  = start_dt.year + end_month // 12
        end_month = end_month % 12 + 1
        end_dt    = date(end_year, end_month, min(start_dt.day, calendar.monthrange(end_year, end_month)[1]))

        total_sets_res = supabase.table("inspection_sets").select(
            "id", count="exact"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").eq("is_active", True).limit(0).execute()
        total_sets = total_sets_res.count or 0

        sets_res = supabase.table("inspection_sets").select(
            "id, company_id, cycle_unit, cycle_value"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE") \
         .eq("anchor_confirmed", True) \
         .not_.is_("schedule_anchor_date", "null") \
         .execute()
        sets = sets_res.data or []
        skipped_anchor = total_sets - len(sets)

        if not sets:
            return {
                "status":  "success",
                "message": "기준일이 확정된 점검 세트가 없습니다.",
                "data": {
                    "factory_id": factory_id, "sets_total": total_sets, "sets_processed": 0,
                    "sets_skipped": total_sets, "skipped_anchor": skipped_anchor,
                    "created": 0, "period": f"{start_str} ~ {end_dt.isoformat()}",
                }
            }

        supabase.table("work_schedules").delete().eq("factory_id", factory_id).eq(
            "status_code", "planned"
        ).gte("planned_date", start_str).lte("planned_date", end_dt.isoformat()).execute()

        insert_rows = []
        for s in sets:
            for d in _calc_schedule_dates(start_dt, end_dt, s.get("cycle_unit", "year"), s.get("cycle_value", 1)):
                insert_rows.append({
                    "inspection_set_id": s["id"], "company_id": s.get("company_id"),
                    "factory_id": factory_id, "planned_date": d.isoformat(), "status_code": "planned",
                })

        created = 0
        for i in range(0, len(insert_rows), 100):
            res = supabase.table("work_schedules").insert(insert_rows[i:i+100]).execute()
            created += len(res.data or [])

        return {
            "status":  "success",
            "message": f"{created}개 스케줄이 생성됐습니다.",
            "data": {
                "factory_id": factory_id, "sets_total": total_sets, "sets_processed": len(sets),
                "sets_skipped": total_sets - len(sets), "skipped_anchor": skipped_anchor,
                "created": created, "period": f"{start_str} ~ {end_dt.isoformat()}",
            }
        }
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{factory_id}")
async def get_inspection_status(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        today      = date.today()
        today_str  = today.isoformat()
        month_start = today.replace(day=1).isoformat()
        month_end   = today.replace(day=calendar.monthrange(today.year, today.month)[1]).isoformat()
        in_30_days  = (today + timedelta(days=30)).isoformat()

        sets_res = supabase.table("inspection_sets").select("id", count="exact")\
            .eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").limit(0).execute()
        total_sets = sets_res.count or 0

        month_res = supabase.table("work_schedules").select("id", count="exact")\
            .eq("factory_id", factory_id).gte("planned_date", month_start)\
            .lte("planned_date", month_end).limit(0).execute()
        this_month_count = month_res.count or 0

        completed_res = supabase.table("work_schedules").select("id", count="exact")\
            .eq("factory_id", factory_id).in_("status_code", ws_completed_query_values()).limit(0).execute()
        completed_count = completed_res.count or 0

        overdue_res = supabase.table("work_schedules").select("id", count="exact")\
            .eq("factory_id", factory_id).eq("status_code", "planned")\
            .lt("planned_date", today_str).limit(0).execute()
        overdue_count = overdue_res.count or 0

        upcoming_res = supabase.table("work_schedules").select(
            "id, planned_date, status_code, inspection_set_id, "
            "inspection_sets(inspection_set_name, law_name)"
        ).eq("factory_id", factory_id).gte("planned_date", today_str)\
         .lte("planned_date", in_30_days).in_("status_code", ["planned", "in_progress"])\
         .order("planned_date").limit(10).execute()

        upcoming = []
        for s in (upcoming_res.data or []):
            iset = s.pop("inspection_sets", {}) or {}
            s["inspection_set_name"] = iset.get("inspection_set_name", "")
            s["law_name"]            = iset.get("law_name", "")
            upcoming.append(s)

        return {"status": "success", "data": {
            "factory_id": factory_id, "total_sets": total_sets,
            "this_month_count": this_month_count, "completed_count": completed_count,
            "overdue_count": overdue_count, "upcoming": upcoming,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedules/{factory_id}")
async def list_schedules(
    factory_id: str,
    month: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        query = supabase.table("work_schedules").select(
            "*, inspection_sets(inspection_set_name, law_name, law_article, cycle_unit, cycle_value)",
            count="exact"
        ).eq("factory_id", factory_id)
        if month:
            y, m = int(month[:4]), int(month[5:7])
            last_day = calendar.monthrange(y, m)[1]
            query = query.gte("planned_date", f"{month}-01").lte("planned_date", f"{month}-{last_day:02d}")
        if status_code:
            query = query.eq("status_code", status_code)
        offset = (page - 1) * page_size
        res = query.order("planned_date").range(offset, offset + page_size - 1).execute()
        items = []
        for row in (res.data or []):
            iset = row.pop("inspection_sets", {}) or {}
            row["inspection_set_name"] = iset.get("inspection_set_name", "")
            row["law_name"]   = iset.get("law_name", "")
            row["law_article"] = iset.get("law_article", "")
            row["cycle_unit"]  = iset.get("cycle_unit", "")
            row["cycle_value"] = iset.get("cycle_value", "")
            items.append(row)
        total = res.count or 0
        return {"status": "success", "data": {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start/{work_schedule_id}")
async def start_inspection(work_schedule_id: str, body: dict = None, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_ws_own(supabase, work_schedule_id, current)
    try:
        body = body or {}
        inspector_name = body.get("inspector_name", "")
        started_at     = body.get("started_at", date.today().isoformat())

        # WP-04D: parent factory companion PRE-READ (side-effect 전 fail-closed)
        # REV-1B: schema 는 factory 간 동일 id 를 허용하므로 id 단독으로 임의 factory 를
        # 고르지 않는다. 0→404, >1→409(WORK_SCHEDULE_ID_AMBIGUOUS), 1→그 factory 사용.
        _ws = supabase.table("work_schedules").select("factory_id").eq("id", work_schedule_id).execute()
        _ws_rows = _ws.data or []
        if not _ws_rows:
            raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")
        if len(_ws_rows) > 1:
            raise HTTPException(status_code=409,
                                detail={"code": "WORK_SCHEDULE_ID_AMBIGUOUS",
                                        "message": "동일 id 의 일정이 여러 factory 에 존재합니다."})
        _parent_factory_id = _ws_rows[0].get("factory_id")
        if not _parent_factory_id:
            raise HTTPException(status_code=409, detail="일정의 factory_id를 확인할 수 없습니다.")

        # KNOT-3C1: 직접 work_schedules UPDATE + safety_inspections INSERT 제거.
        # 하나의 원자적 RPC(fn_start_safe_inspection_record)로 schedule lock →
        # cardinality 확인 → in_progress → base IN_PROGRESS 를 한 트랜잭션으로 수행.
        # 동일 (schedule, factory) 재호출은 replay(두 번째 생성 0). Worker one-shot 과
        # 같은 parent lock 규율로 동시성 직렬화.
        try:
            _result = start_safe_inspection(
                supabase,
                schedule_id=work_schedule_id,
                factory_id=str(_parent_factory_id),
                started_at=started_at,
                inspector_name=inspector_name,
            )
        except SafeStartError as e:
            if e.is_not_found:
                raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")
            if e.is_cardinality:
                raise HTTPException(status_code=409,
                                    detail={"code": e.code, "message": "점검 레코드가 이미 여러 건입니다."})
            raise HTTPException(status_code=500, detail={"error": e.code})
        snap = _result.get("data") or {}
        return {"status": "success", "message": "점검이 시작됐습니다.",
                "data": {"work_schedule_id": work_schedule_id, "inspection_id": snap.get("inspection_id"),
                         "inspector_name": snap.get("inspector_name", inspector_name),
                         "started_at": snap.get("started_at", started_at)}}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.post("/result/{inspection_id}/items")
async def record_inspection_results(inspection_id: str, body: dict, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_inspection_own(supabase, inspection_id, current)
    try:
        results = body.get("results", [])
        if not results:
            raise HTTPException(status_code=400, detail="results가 비어 있습니다.")
        # WO-DEBT-W3-02: 직접 batch INSERT 제거. inspection_id-scoped 원자 RPC 로
        # initial batch 생성/replay/conflict 를 parent lock 하에 처리.
        try:
            _rb = record_safe_result_batch(supabase, inspection_id=inspection_id, results=results)
        except SafeResultBatchError as e:
            if e.is_not_found:
                raise HTTPException(status_code=404, detail="점검 레코드를 찾을 수 없습니다.")
            if e.is_conflict:
                raise HTTPException(status_code=409,
                                    detail={"code": e.code, "message": "이미 다른 결과가 기록된 점검입니다."})
            if e.is_empty:
                raise HTTPException(status_code=400, detail="results가 비어 있습니다.")
            raise HTTPException(status_code=500, detail={"error": e.code})
        created = _rb.get("count", 0)

        # CREATED/REPLAY 공통으로 기존 auto-complete 로직 실행 (REPLAY early-return 금지).
        insp_res = supabase.table("safety_inspections").select("assignment_id").eq("id", inspection_id).limit(1).execute()
        if insp_res.data:
            ws_id = insp_res.data[0].get("assignment_id")
            _all_normal = all(
                normalize_inspection_result_write(r.get("result", "NA")) == "NORMAL"
                for r in results
            )
            if ws_id and _all_normal:
                # completion anchor freeze — 최초 완료일 고정(REPLAY 마다 today 덮어쓰기 금지)
                _wsrow = supabase.table("work_schedules").select("completed_at").eq("id", ws_id).limit(1).execute()
                _existing = (_wsrow.data[0].get("completed_at") if _wsrow.data else None)
                _anchor_str = _existing or date.today().isoformat()
                supabase.table("work_schedules").update({
                    "status_code": "completed", "completed_at": _anchor_str,
                }).eq("id", ws_id).execute()
                complete_inspection_status(
                    supabase, inspection_id,
                    actor_id=current["id"], reason="SAFE_RESULT_AUTO_COMPLETE",
                )
                ensure_next_rolling_schedule(supabase, ws_id, date.fromisoformat(str(_anchor_str)[:10]))
        return {"status": "success", "message": f"{created}개 결과가 기록됐습니다.",
                "data": {"inspection_id": inspection_id, "created": created}}
    except HTTPException: raise
    except InspectionStatusWriteError as e:
        raise HTTPException(status_code=409, detail={"code": e.code, "message": "점검 상태를 완료 처리할 수 없습니다."})
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete/{work_schedule_id}")
async def complete_inspection(work_schedule_id: str, body: dict = None, current: dict = Depends(get_current_user)):
    """
    v1.4.0: Rolling 완료 후 다음 회차 자동 생성.
    - 완료된 planned_date + delta = 다음 planned_date 1건 INSERT
    - schedule_end_date 있으면 해당 날짜 넘으면 생성 안 함
    - schedule_end_date 없으면 무한 반복
    - assigned_user_id=NULL (배정은 안전관리자가 시행)
    - COMPLETED 자체는 절대 수정 안 함
    """
    supabase = get_supabase()
    _ensure_ws_own(supabase, work_schedule_id, current)
    try:
        body = body or {}
        summary      = body.get("summary", "")
        completed_at = body.get("completed_at", date.today().isoformat())

        # KNOT-3A: schedule mutation 전에 대상 inspection cardinality 확정 (fail-closed).
        # assignment_id 당 inspection 은 0/1 만 허용. 2건 이상이면 각각 별도 전표화 시
        # 중간 실패로 partial journal 이 생길 수 있으므로 schedule 변경 전에 HARD FAIL.
        _linked = supabase.table("safety_inspections").select("id").eq(
            "assignment_id", work_schedule_id
        ).execute()
        _linked_rows = _linked.data or []
        if len(_linked_rows) > 1:
            raise HTTPException(
                status_code=409,
                detail={"code": "INSPECTION_CARDINALITY_VIOLATION",
                        "message": "점검 상태를 완료 처리할 수 없습니다."},
            )
        _target_inspection_id = _linked_rows[0]["id"] if _linked_rows else None

        # 완료 상태로 업데이트 (COMPLETED 리코드는 이후 건드리지 않음)
        ws_res = supabase.table("work_schedules").update({
            "status_code": "completed", "completed_at": completed_at, "summary": summary,
        }).eq("id", work_schedule_id).execute()
        if not ws_res.data:
            raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")

        ws                = ws_res.data[0]
        inspection_set_id = ws.get("inspection_set_id")
        completed_date    = date.fromisoformat(str(completed_at))

        next_schedule_created = False
        next_planned_date     = None

        if inspection_set_id:
            _roll = ensure_next_rolling_schedule(supabase, work_schedule_id, completed_date)
            next_schedule_created = _roll.get("created", False)
            next_planned_date     = _roll.get("next_planned_date")

        # KNOT-3A: 기존 bulk base UPDATE 대신, 연결된 inspection 1건에 한해
        # STATUS_CHANGE 전표를 append 한다. 0건이면 schedule 완료/rolling 만 진행.
        if _target_inspection_id is not None:
            complete_inspection_status(
                supabase, _target_inspection_id,
                actor_id=current["id"], reason="SAFE_COMPLETE",
            )

        return {
            "status":  "success",
            "message": "점검이 완료 처리됐습니다.",
            "data": {
                "work_schedule_id":     work_schedule_id,
                "completed_at":         completed_at,
                "summary":              summary,
                "next_schedule_created": next_schedule_created,
                "next_planned_date":    next_planned_date,
            }
        }
    except HTTPException: raise
    except InspectionStatusWriteError as e:
        raise HTTPException(status_code=409, detail={"code": e.code, "message": "점검 상태를 완료 처리할 수 없습니다."})
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedules")
async def list_inspection_schedules(
    factory_id: str = None,
    status_code: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current: dict = Depends(get_current_user),
):
    """점검 일정 목록 (work_schedules 기반)"""
    supabase = get_supabase()
    q = supabase.table("work_schedules").select("*", count="exact")
    # ── 회사 스코프 (P13): factory 지정 시 소유확인, 아니면 자사 factory 제한 ──
    if factory_id:
        _ensure_factory_own(supabase, factory_id, current)
        q = q.eq("factory_id", factory_id)
    else:
        own = _own_factory_ids(supabase, current)
        if own is not None:            # 비-ALL
            if not own:                # 무회사 → 빈 결과
                return {"status": "success", "data": [], "total": 0}
            q = q.in_("factory_id", own)
    if status_code:
        q = q.eq("status_code", status_code)
    offset = (page - 1) * page_size
    res = q.order("planned_date", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": res.data, "total": res.count or 0}
