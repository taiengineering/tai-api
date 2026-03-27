"""
점검리스트 시스템 — v1.0.0
prefix: /inspection

엔드포인트:
  POST /inspection/generate-items/{factory_id}     법령별 점검항목 자동 생성
  POST /inspection/generate-schedules/{factory_id} 점검 스케줄 일괄 생성
  GET  /inspection/status/{factory_id}             점검 현황 조회
  GET  /inspection/schedules/{factory_id}          점검 일정 목록
  POST /inspection/start/{work_schedule_id}        점검 실행 시작
  POST /inspection/result/{inspection_id}/items    점검 항목 결과 기록
  POST /inspection/complete/{work_schedule_id}     점검 완료 처리
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone, date, timedelta
import calendar

from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection", tags=["점검리스트"])

VERSION = "1.0.0"


# ──────────────────────────────────────────────
# 법령 코드별 표준 점검 항목 매핑
# ──────────────────────────────────────────────
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


def _calc_schedule_dates(start_date: date, end_date: date, cycle_unit: str, cycle_value: int) -> list:
    """cycle_unit/cycle_value 기반으로 start~end 사이 점검 날짜 목록 생성"""
    dates = []
    current = start_date

    while current <= end_date:
        dates.append(current)
        if cycle_unit == "day":
            current += timedelta(days=cycle_value)
        elif cycle_unit == "week":
            current += timedelta(weeks=cycle_value)
        elif cycle_unit == "month":
            # 월 단위 계산
            month = current.month - 1 + cycle_value
            year  = current.year + month // 12
            month = month % 12 + 1
            day   = min(current.day, calendar.monthrange(year, month)[1])
            current = date(year, month, day)
        elif cycle_unit == "year":
            try:
                current = date(current.year + cycle_value, current.month, current.day)
            except ValueError:
                current = date(current.year + cycle_value, current.month, 28)
        else:
            break

    return dates


# ──────────────────────────────────────────────────────────
# 1. POST /inspection/generate-items/{factory_id}
#    법령별 점검 항목 자동 생성
# ──────────────────────────────────────────────────────────
@router.post("/generate-items/{factory_id}")
async def generate_inspection_items(factory_id: str):
    """
    factory_id의 inspection_sets(LEGAL_ENGINE) 조회 →
    LEGAL_INSPECTION_ITEMS 매핑 → inspection_set_items 재생성
    """
    supabase = get_supabase()
    try:
        sets_res = supabase.table("inspection_sets").select(
            "id, inspection_set_code, inspection_set_name, law_name"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").execute()
        sets = sets_res.data or []

        if not sets:
            raise HTTPException(status_code=404, detail="점검 세트가 없습니다. 먼저 법령엔진을 실행하세요.")

        set_ids = [s["id"] for s in sets]

        # 기존 항목 삭제 (멱등성)
        for sid in set_ids:
            supabase.table("inspection_set_items").delete().eq("inspection_set_id", sid).execute()

        now = _now_iso()
        insert_rows = []
        matched = 0
        default = 0

        for s in sets:
            code     = s.get("inspection_set_code", "")
            law_name = s.get("law_name", s.get("inspection_set_name", ""))
            items    = LEGAL_INSPECTION_ITEMS.get(code)

            if items:
                matched += 1
                for seq, item_name in enumerate(items, start=1):
                    insert_rows.append({
                        "inspection_set_id": s["id"],
                        "item_seq":          seq,
                        "item_name":         item_name,
                        "is_required":       True,
                        "is_active":         True,
                        "created_at":        now,
                    })
            else:
                # 매핑 없는 경우 기본 항목 1개
                default += 1
                insert_rows.append({
                    "inspection_set_id": s["id"],
                    "item_seq":          1,
                    "item_name":         f"{law_name} 점검 실시",
                    "is_required":       True,
                    "is_active":         True,
                    "created_at":        now,
                })

        # 배치 삽입 (50건씩)
        created = 0
        for i in range(0, len(insert_rows), 50):
            res = supabase.table("inspection_set_items").insert(insert_rows[i:i+50]).execute()
            created += len(res.data or [])

        return {
            "status": "success",
            "message": f"{created}개 점검 항목이 생성됐습니다.",
            "data": {
                "factory_id":    factory_id,
                "sets_total":    len(sets),
                "sets_matched":  matched,
                "sets_default":  default,
                "items_created": created,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 2. POST /inspection/generate-schedules/{factory_id}
#    점검 스케줄 일괄 생성
# ──────────────────────────────────────────────────────────
@router.post("/generate-schedules/{factory_id}")
async def generate_schedules(factory_id: str, body: Optional[dict] = None):
    """
    inspection_sets(LEGAL_ENGINE) → work_schedules 자동 생성
    body: { start_date: 'YYYY-MM-DD', months: 12 }
    """
    supabase = get_supabase()
    try:
        # 파라미터
        body = body or {}
        start_str = body.get("start_date") or date.today().isoformat()
        months    = int(body.get("months", 12))
        start_dt  = date.fromisoformat(start_str)
        # end_date: months개월 후
        end_month = start_dt.month - 1 + months
        end_year  = start_dt.year + end_month // 12
        end_month = end_month % 12 + 1
        end_dt    = date(end_year, end_month, min(start_dt.day, calendar.monthrange(end_year, end_month)[1]))

        # 점검 세트 조회
        sets_res = supabase.table("inspection_sets").select(
            "id, company_id, cycle_unit, cycle_value"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").execute()
        sets = sets_res.data or []

        if not sets:
            raise HTTPException(status_code=404, detail="점검 세트가 없습니다.")

        # 기존 planned 스케줄 삭제 (해당 기간)
        supabase.table("work_schedules").delete().eq(
            "factory_id", factory_id
        ).eq("status_code", "planned").gte("planned_date", start_str).lte(
            "planned_date", end_dt.isoformat()
        ).execute()

        now = _now_iso()
        insert_rows = []

        for s in sets:
            cycle_unit  = s.get("cycle_unit", "year")
            cycle_value = s.get("cycle_value", 1)
            company_id  = s.get("company_id")

            schedule_dates = _calc_schedule_dates(start_dt, end_dt, cycle_unit, cycle_value)

            for d in schedule_dates:
                insert_rows.append({
                    "inspection_set_id": s["id"],
                    "company_id":        company_id,
                    "factory_id":        factory_id,
                    "planned_date":      d.isoformat(),
                    "status_code":       "planned",
                })

        # 배치 삽입
        created = 0
        for i in range(0, len(insert_rows), 100):
            res = supabase.table("work_schedules").insert(insert_rows[i:i+100]).execute()
            created += len(res.data or [])

        return {
            "status": "success",
            "message": f"{created}개 스케줄이 생성됐습니다.",
            "data": {
                "factory_id":     factory_id,
                "sets_processed": len(sets),
                "created":        created,
                "period":         f"{start_str} ~ {end_dt.isoformat()}",
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 3. GET /inspection/status/{factory_id}
#    점검 현황 조회
# ──────────────────────────────────────────────────────────
@router.get("/status/{factory_id}")
async def get_inspection_status(factory_id: str):
    supabase = get_supabase()
    try:
        today = date.today()
        this_month_start = today.replace(day=1).isoformat()
        this_month_end   = today.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        ).isoformat()
        in_30_days = (today + timedelta(days=30)).isoformat()

        # 전체 점검 세트 수
        sets_res = supabase.table("inspection_sets").select(
            "id", count="exact"
        ).eq("factory_id", factory_id).eq("source", "LEGAL_ENGINE").limit(0).execute()
        total_sets = sets_res.count or 0

        # 이번 달 예정
        month_res = supabase.table("work_schedules").select(
            "id, status_code", count="exact"
        ).eq("factory_id", factory_id).gte(
            "planned_date", this_month_start
        ).lte("planned_date", this_month_end).limit(0).execute()
        this_month_count = month_res.count or 0

        # 전체 work_schedules 현황
        all_res = supabase.table("work_schedules").select(
            "id, status_code, planned_date, inspection_set_id"
        ).eq("factory_id", factory_id).execute()
        all_schedules = all_res.data or []

        completed_count = sum(1 for s in all_schedules if s.get("status_code") == "completed")
        overdue_count   = sum(
            1 for s in all_schedules
            if s.get("status_code") in ("planned", "in_progress")
            and s.get("planned_date", "") < today.isoformat()
        )

        # 다가오는 30일 이내 일정 (최대 10건)
        upcoming_res = supabase.table("work_schedules").select(
            "id, planned_date, status_code, inspection_set_id, inspection_sets(inspection_set_name, law_name)"
        ).eq("factory_id", factory_id).gte(
            "planned_date", today.isoformat()
        ).lte(
            "planned_date", in_30_days
        ).in_("status_code", ["planned", "in_progress"]).order(
            "planned_date"
        ).limit(10).execute()

        upcoming = []
        for s in (upcoming_res.data or []):
            iset = s.pop("inspection_sets", {}) or {}
            s["inspection_set_name"] = iset.get("inspection_set_name", "")
            s["law_name"]            = iset.get("law_name", "")
            upcoming.append(s)

        return {
            "status": "success",
            "data": {
                "factory_id":       factory_id,
                "total_sets":       total_sets,
                "this_month_count": this_month_count,
                "completed_count":  completed_count,
                "overdue_count":    overdue_count,
                "upcoming":         upcoming,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 4. GET /inspection/schedules/{factory_id}
#    점검 일정 목록
# ──────────────────────────────────────────────────────────
@router.get("/schedules/{factory_id}")
async def list_schedules(
    factory_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM 형식"),
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("work_schedules").select(
            "*, inspection_sets(inspection_set_name, law_name, law_article, cycle_unit, cycle_value)",
            count="exact"
        ).eq("factory_id", factory_id)

        if month:
            # YYYY-MM → YYYY-MM-01 ~ YYYY-MM-말일
            y, m = int(month[:4]), int(month[5:7])
            last_day = calendar.monthrange(y, m)[1]
            query = query.gte("planned_date", f"{month}-01").lte("planned_date", f"{month}-{last_day:02d}")
        if status_code:
            query = query.eq("status_code", status_code)

        offset = (page - 1) * page_size
        query  = query.order("planned_date").range(offset, offset + page_size - 1)
        res    = query.execute()

        items = []
        for row in (res.data or []):
            iset = row.pop("inspection_sets", {}) or {}
            row["inspection_set_name"] = iset.get("inspection_set_name", "")
            row["law_name"]            = iset.get("law_name", "")
            row["law_article"]         = iset.get("law_article", "")
            row["cycle_unit"]          = iset.get("cycle_unit", "")
            row["cycle_value"]         = iset.get("cycle_value", "")
            items.append(row)

        total = res.count or 0
        return {
            "status": "success",
            "data": {
                "items":       items,
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 5. POST /inspection/start/{work_schedule_id}
#    점검 실행 시작
# ──────────────────────────────────────────────────────────
@router.post("/start/{work_schedule_id}")
async def start_inspection(work_schedule_id: str, body: dict = None):
    supabase = get_supabase()
    try:
        body = body or {}
        inspector_name = body.get("inspector_name", "")
        started_at     = body.get("started_at", date.today().isoformat())

        # work_schedules 상태 변경
        ws_res = supabase.table("work_schedules").update({
            "status_code":   "in_progress",
            "inspector_name": inspector_name,
        }).eq("id", work_schedule_id).execute()

        if not ws_res.data:
            raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")

        ws = ws_res.data[0]

        # safety_inspections 레코드 생성
        insp_res = supabase.table("safety_inspections").insert({
            "assignment_id":  work_schedule_id,
            "inspection_date": started_at,
            "status_code":    "in_progress",
        }).execute()

        if not insp_res.data:
            raise HTTPException(status_code=500, detail="점검 레코드 생성 실패")

        inspection_id = insp_res.data[0]["id"]

        return {
            "status": "success",
            "message": "점검이 시작됐습니다.",
            "data": {
                "work_schedule_id": work_schedule_id,
                "inspection_id":    inspection_id,
                "inspector_name":   inspector_name,
                "started_at":       started_at,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 6. POST /inspection/result/{inspection_id}/items
#    점검 항목 결과 기록
# ──────────────────────────────────────────────────────────
@router.post("/result/{inspection_id}/items")
async def record_inspection_results(inspection_id: str, body: dict):
    supabase = get_supabase()
    try:
        results = body.get("results", [])
        if not results:
            raise HTTPException(status_code=400, detail="results가 비어 있습니다.")

        now = _now_iso()
        insert_rows = []
        for r in results:
            insert_rows.append({
                "inspection_id":        inspection_id,
                "inspection_set_item_id": r.get("inspection_set_item_id"),
                "result_code":          r.get("result", "NA"),
                "note":                 r.get("note", ""),
                "photo_url":            r.get("photo_url"),
                "checked_at":           now,
            })

        res = supabase.table("safety_inspection_results").insert(insert_rows).execute()
        created = len(res.data or [])

        # 전체 항목 완료 여부 확인
        # inspection_id → assignment_id(=work_schedule_id) 역추적
        insp_res = supabase.table("safety_inspections").select(
            "assignment_id"
        ).eq("id", inspection_id).limit(1).execute()

        if insp_res.data:
            ws_id = insp_res.data[0].get("assignment_id")
            if ws_id:
                # FAIL 없고 NA 없으면 자동 완료 처리
                fail_count = sum(1 for r in results if r.get("result") == "FAIL")
                na_count   = sum(1 for r in results if r.get("result") == "NA")
                if fail_count == 0 and na_count == 0:
                    supabase.table("work_schedules").update({
                        "status_code": "completed",
                        "completed_at": date.today().isoformat(),
                    }).eq("id", ws_id).execute()
                    # safety_inspections 도 완료
                    supabase.table("safety_inspections").update({
                        "status_code": "completed"
                    }).eq("id", inspection_id).execute()

        return {
            "status": "success",
            "message": f"{created}개 결과가 기록됐습니다.",
            "data": {"inspection_id": inspection_id, "created": created}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────
# 7. POST /inspection/complete/{work_schedule_id}
#    점검 완료 처리
# ──────────────────────────────────────────────────────────
@router.post("/complete/{work_schedule_id}")
async def complete_inspection(work_schedule_id: str, body: dict = None):
    supabase = get_supabase()
    try:
        body = body or {}
        summary      = body.get("summary", "")
        completed_at = body.get("completed_at", date.today().isoformat())

        # work_schedules 완료 처리
        ws_res = supabase.table("work_schedules").update({
            "status_code":  "completed",
            "completed_at": completed_at,
            "summary":      summary,
        }).eq("id", work_schedule_id).execute()

        if not ws_res.data:
            raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")

        ws = ws_res.data[0]
        factory_id      = ws.get("factory_id")
        inspection_set_id = ws.get("inspection_set_id")

        # inspection_set → cycle_unit/value 조회 → 다음 점검일 계산
        if inspection_set_id:
            iset_res = supabase.table("inspection_sets").select(
                "cycle_unit, cycle_value"
            ).eq("id", inspection_set_id).limit(1).execute()

            if iset_res.data:
                cycle_unit  = iset_res.data[0].get("cycle_unit", "year")
                cycle_value = iset_res.data[0].get("cycle_value", 1)
                base = date.fromisoformat(str(completed_at))

                # 다음 점검일 계산
                if cycle_unit == "day":
                    next_date = base + timedelta(days=cycle_value)
                elif cycle_unit == "week":
                    next_date = base + timedelta(weeks=cycle_value)
                elif cycle_unit == "month":
                    m    = base.month - 1 + cycle_value
                    y    = base.year + m // 12
                    m    = m % 12 + 1
                    next_date = date(y, m, min(base.day, calendar.monthrange(y, m)[1]))
                else:  # year
                    try:
                        next_date = date(base.year + cycle_value, base.month, base.day)
                    except ValueError:
                        next_date = date(base.year + cycle_value, base.month, 28)

                # 다음 점검 스케줄 자동 생성
                if factory_id:
                    company_res = supabase.table("factories").select("company_id").eq(
                        "id", factory_id
                    ).limit(1).execute()
                    company_id = company_res.data[0].get("company_id") if company_res.data else None

                    supabase.table("work_schedules").insert({
                        "inspection_set_id": inspection_set_id,
                        "company_id":        company_id,
                        "factory_id":        factory_id,
                        "planned_date":      next_date.isoformat(),
                        "status_code":       "planned",
                    }).execute()

        # safety_inspections 완료
        supabase.table("safety_inspections").update({
            "status_code": "completed"
        }).eq("assignment_id", work_schedule_id).execute()

        return {
            "status": "success",
            "message": "점검이 완료 처리됐습니다.",
            "data": {
                "work_schedule_id": work_schedule_id,
                "completed_at":     completed_at,
                "summary":          summary,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
