"""
work_schedules.py — v1.2.7

v1.2.7 (2026-08-22, Phase E-1):
  [ADD] FACTORY 스코프 — scoped_filter(company_id+factory_id). FACTORY role 은
        자기 factory 행만. TEAM/ASSIGNED 는 team_id 컬럼 없으므로 FACTORY→COMPANY
        폴백. 단건·factory 경로·_owned_ids 동시 적용.

v1.2.6 (2026-08-21, LEDGER §34 keyword):
  [ADD] GET /work-schedules 에 keyword 자유검색 추가. 화면(작업일정)이 보내던 keyword 가
        서버에 선언되지 않아 버려졌다. description·law_name·rule_code 를 ilike or 로 검색한다
        (or_ 파싱 보호로 쉼표는 공백 치환). ※ §34 잔여(알럿 미사용/비활성 카드 동일값·
        상태 선택지 '예정-구' 하드코딩)는 화면 = vue3.

v1.2.5 (2026-08-21, LEDGER ㉑-마감일):
  [ADD] SchedulePatchBody · _apply_one_update 에 planned_date(마감일) 지원.
        대시보드 [담당자 배정]에서 담당자(assigned_user_id)는 저장됐으나, 마감일이
        스키마·화이트리스트에 없어 조용히 버려지던 것 해소. planned_date 는 실제
        컬럼(v1.2.4 GET 범위필터가 이미 사용 중).

v1.2.4 (2026-08-17, LEDGER ㉙):
  [ADD] GET /work-schedules 에 obligation_type · planned_date_from · planned_date_to 필터.
        점검 캘린더/작업일정 화면이 보내던 계획일 범위·의무구분 필터가 서버에 선언되지
        않아 무시되던 것 해소. planned_date · obligation_type 은 실제 컬럼(실측 확인).

v1.2.3 (2026-08-17, LEDGER ㉑·㉘·㉝):
  [ADD] PATCH /work-schedules/{schedule_id} — 단건 갱신(담당자 배정·상태 등).
  [ADD] POST  /work-schedules/bulk-assign   — 선택 일정 일괄 담당자 배정.
        대시보드 [담당자 배정]·점검 캘린더 [완료처리]·작업일정 [담당자 배정] 공통 경로.
        화면 별칭 assignee_id → assigned_user_id 흡수. work_assignments 동기화 재사용.

v1.2.2 (2026-08-17):
  [FIX] GET /work-schedules/{schedule_id} — 비-uuid 경로(/summary 등) 404 처리(22P02 500 방지).
v1.2.1 (2026-05-26): GET size 상한 100→500.
v1.2.0 (2026-04-13): GET 필터(is_assigned 등).
v1.1.0 (2026-04-07): PATCH /batch-update, POST /confirm/{factory_id}.

API:
  GET   /work-schedules                              전체 목록 (필터 지원)
  GET   /work-schedules/factory/{factory_id}         공장별 목록
  GET   /work-schedules/inspection-set/{id}          점검세트별 목록
  PATCH /work-schedules/batch-update                 일괄 업데이트
  POST  /work-schedules/bulk-assign                  일괄 담당자 배정  ← v1.2.3
  POST  /work-schedules/confirm/{factory_id}         검토 확정
  GET   /work-schedules/{schedule_id}                단건 조회
  PATCH /work-schedules/{schedule_id}                단건 갱신        ← v1.2.3
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import (
    DENY,
    apply_scoped_filter,
    scoped_filter,
    _ensure_own_company,
    _ensure_factory_own,
    _scope,
    _is_admin,
    _tier,
)
from services.status_vocab import wa_active_query_values, wa_write_ready
from services.time import now_kst, serialize_external_utc

router = APIRouter(prefix="/work-schedules", tags=["work_schedules"])

VERSION = "1.2.7"


def _now() -> str:
    return serialize_external_utc(now_kst())


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _apply_one_update(supabase, schedule_id: str, fields: dict, now: str) -> bool:
    """단일 work_schedules 행 갱신 + assigned_user_id 변경 시 work_assignments 동기화.

    fields 에 'assigned_user_id' 키가 있으면(None 포함) 배정 변경으로 본다(batch-update 와 동일).
    지원 필드: is_excluded · excluded_reason · custom_cycle · status_code · resolved_at · planned_date · assigned_user_id.

    WP-04C: 신규 work_assignments 생성 시 factory_id = parent work_schedules.factory_id(companion).
            parent factory_id 확인 불가 시 어떤 side-effect(work_schedules UPDATE 포함)보다 먼저 409.
    """
    payload: dict = {"updated_at": now}
    for k in ("is_excluded", "excluded_reason", "custom_cycle", "status_code", "resolved_at", "planned_date"):
        if fields.get(k) is not None:
            payload[k] = fields[k]
    assign_changed = "assigned_user_id" in fields
    if assign_changed:
        payload["assigned_user_id"] = fields["assigned_user_id"]

    # WP-04C parent factory PRE-READ (side-effect 전 fail-closed).
    # 신규 assignment INSERT가 발생하는 경우(assigned_user_id 실제 값)만 검사한다.
    _parent_factory_id = None
    if assign_changed and fields["assigned_user_id"]:
        _parent = supabase.table("work_schedules").select("factory_id") \
            .eq("id", schedule_id).limit(1).execute()
        _parent_factory_id = _parent.data[0].get("factory_id") if _parent.data else None
        if not _parent_factory_id:
            raise HTTPException(
                status_code=409,
                detail="일정의 factory_id를 확인할 수 없습니다.",
            )

    # fail-closed 통과 후에만 기존 work_schedules UPDATE 수행
    res = supabase.table("work_schedules").update(payload).eq("id", schedule_id).execute()
    updated = bool(res.data)

    if assign_changed:
        auid = fields["assigned_user_id"]
        if auid:
            existing = supabase.table("work_assignments").select("id") \
                .eq("schedule_id", schedule_id).in_("status_code", wa_active_query_values()).limit(1).execute()
            if existing.data:
                supabase.table("work_assignments").update({
                    "assigned_user_id": auid, "updated_at": now,
                }).eq("id", existing.data[0]["id"]).execute()
            else:
                supabase.table("work_assignments").insert({
                    "schedule_id": schedule_id, "assigned_user_id": auid,
                    "scheduled_date": now_kst().date().isoformat(),
                    "status_code": wa_write_ready(), "created_at": now,
                    "factory_id": _parent_factory_id,   # WP-04C parent companion (PRE-READ 값)
                }).execute()
        else:
            supabase.table("work_assignments").update({
                "status_code": "CANCELLED", "updated_at": now,
            }).eq("schedule_id", schedule_id).in_("status_code", wa_active_query_values()).execute()
    return updated


def _owned_ids(supabase, ids, current):
    """비-ALL: 자기 스코프 소유 schedule id 집합만. ALL: 전체 그대로.

    E-1: FACTORY/TEAM(team_id 없는 테이블)은 factory_id 까지 좁힘.
    """
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return set(ids)
    if not ids:
        return set()
    filt = scoped_filter(current, supabase, {"company_id", "factory_id"})
    if filt is DENY:
        return set()
    q = supabase.table("work_schedules").select("id").in_("id", list(ids))
    q = apply_scoped_filter(q, filt)
    if q is None:
        return set()
    res = q.execute()
    return {r["id"] for r in (res.data or [])}


def _ensure_ws_factory_access(supabase, factory_id, current) -> None:
    """시설 경로: 회사 소유 + E-1 FACTORY/TEAM 은 자기 factory 만."""
    _ensure_factory_own(supabase, factory_id, current)
    tier = _tier(supabase, current.get("role_code"))
    if tier in ("FACTORY", "TEAM"):
        token_fid = current.get("factory_id")
        if not token_fid or factory_id != token_fid:
            raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")


def _ensure_ws_row(row, current, supabase) -> None:
    """단건: 회사 + (FACTORY/TEAM 이면) factory 일치."""
    _ensure_own_company(
        row.get("company_id"),
        current,
        supabase,
        "일정을 찾을 수 없습니다",
        resource_factory_id=row.get("factory_id"),
    )


# ── Pydantic 모델 ─────────────────────────────────────────────

class ScheduleUpdateItem(BaseModel):
    id:               str
    is_excluded:      Optional[bool]  = None
    excluded_reason:  Optional[str]   = None
    custom_cycle:     Optional[str]   = None   # ex) 'MONTHLY', '3MONTH'
    assigned_user_id: Optional[str]   = None   # null 허용 → 배정 해제


class BatchUpdateBody(BaseModel):
    updates: List[ScheduleUpdateItem]


class ConfirmBody(BaseModel):
    reviewed_by: str   # user uuid


class SchedulePatchBody(BaseModel):
    assigned_user_id: Optional[str]  = None
    assignee_id:      Optional[str]  = None   # 화면 별칭 → assigned_user_id
    status_code:      Optional[str]  = None
    status:           Optional[str]  = None   # 화면 별칭 → status_code
    is_excluded:      Optional[bool] = None
    excluded_reason:  Optional[str]  = None
    custom_cycle:     Optional[str]  = None
    resolved_at:      Optional[str]  = None
    planned_date:     Optional[str]  = None   # 마감일(㉑) — YYYY-MM-DD


class BulkAssignBody(BaseModel):
    ids:              List[str]
    assigned_user_id: Optional[str] = None
    assignee_id:      Optional[str] = None   # 화면 별칭


# ── 고정경로 먼저 선언 (/{schedule_id} 보다 앞에) ──────────────

@router.patch("/batch-update")
def batch_update_schedules(body: BatchUpdateBody, current: dict = Depends(get_current_user)):
    """
    v1.1.0: 복수 work_schedules 일괄 업데이트.
    - is_excluded / excluded_reason / custom_cycle 업데이트
    - assigned_user_id 있으면 work_assignments에도 반영(PENDING UPDATE/INSERT, null→CANCELLED)
    """
    supabase = get_supabase()
    now      = _now()
    updated  = 0
    owned = _owned_ids(supabase, [it.id for it in body.updates], current)

    for item in body.updates:
        if item.id not in owned:
            continue
        fields: dict = {}
        if item.is_excluded is not None:
            fields["is_excluded"] = item.is_excluded
        if item.excluded_reason is not None:
            fields["excluded_reason"] = item.excluded_reason
        if item.custom_cycle is not None:
            fields["custom_cycle"] = item.custom_cycle
        if "assigned_user_id" in item.__fields_set__:
            fields["assigned_user_id"] = item.assigned_user_id
        if _apply_one_update(supabase, item.id, fields, now):
            updated += 1

    return {"status": "success", "data": {"updated": updated}}


@router.post("/bulk-assign")
def bulk_assign_schedules(body: BulkAssignBody, current: dict = Depends(get_current_user)):
    """v1.2.3: 선택 일정 일괄 담당자 배정(작업일정 §33). ids[] + assignee_id/assigned_user_id."""
    supabase = get_supabase()
    now = _now()
    auid = body.assigned_user_id if body.assigned_user_id is not None else body.assignee_id
    updated = 0
    owned = _owned_ids(supabase, body.ids, current)
    for sid in body.ids:
        if not _is_uuid(sid):
            continue
        if sid not in owned:
            continue
        if _apply_one_update(supabase, sid, {"assigned_user_id": auid}, now):
            updated += 1
    return {"status": "success", "data": {"updated": updated}}


@router.post("/confirm/{factory_id}")
def confirm_schedules(factory_id: str, body: ConfirmBody, current: dict = Depends(get_current_user)):
    """
    v1.1.0: 검토 완료 후 스케줄 확정.
    1. is_excluded=FALSE → reviewed_at/reviewed_by, custom_cycle→cycle_code
    2. is_excluded=TRUE → status_code='EXCLUDED', is_active=FALSE
    """
    supabase = get_supabase()
    _ensure_ws_factory_access(supabase, factory_id, current)   # 타사·타시설 404
    now      = _now()

    active_res = supabase.table("work_schedules") \
        .select("id, custom_cycle") \
        .eq("factory_id", factory_id) \
        .eq("is_excluded", False) \
        .eq("active_yn", True) \
        .execute()
    active_rows = active_res.data or []

    confirmed = 0
    for row in active_rows:
        update_payload: dict = {
            "reviewed_at": now,
            "reviewed_by": body.reviewed_by,
            "updated_at":  now,
        }
        if row.get("custom_cycle"):
            update_payload["cycle_code"] = row["custom_cycle"]
        supabase.table("work_schedules").update(update_payload).eq("id", row["id"]).execute()
        confirmed += 1

    excluded_res = supabase.table("work_schedules") \
        .select("id") \
        .eq("factory_id", factory_id) \
        .eq("is_excluded", True) \
        .execute()
    excluded_rows = excluded_res.data or []

    excluded = 0
    if excluded_rows:
        exc_ids = [r["id"] for r in excluded_rows]
        for i in range(0, len(exc_ids), 50):
            batch = exc_ids[i:i+50]
            supabase.table("work_schedules").update({
                "status_code": "EXCLUDED",
                "is_active":   False,
                "updated_at":  now,
            }).in_("id", batch).execute()
        excluded = len(excluded_rows)

    return {
        "status": "success",
        "data": {"confirmed": confirmed, "excluded": excluded, "created": 0},
    }


# ── 기존 CRUD ─────────────────────────────────────────────────

@router.get("")
def get_work_schedules(
    company_id:        Optional[str]  = Query(None, description="회사 ID 필터"),
    factory_id:        Optional[str]  = Query(None, description="시설 ID 필터"),
    status_code:       Optional[str]  = Query(None, description="상태코드 필터"),
    source_type:       Optional[str]  = Query(None, description="소스 타입 필터 (MANUAL/LAW_ENGINE)"),
    obligation_type:   Optional[str]  = Query(None, description="의무 구분 필터 (v1.2.4)"),
    is_assigned:       Optional[bool] = Query(None, description="배정 여부 필터. false=미배정, true=배정완료"),
    planned_date_from: Optional[str]  = Query(None, description="계획일 시작 YYYY-MM-DD (v1.2.4)"),
    planned_date_to:   Optional[str]  = Query(None, description="계획일 종료 YYYY-MM-DD (v1.2.4)"),
    keyword:           Optional[str]  = Query(None, description="자유 검색어(설명·법령명·규칙코드) (v1.2.6 §34)"),
    page:              int            = Query(1, ge=1, description="페이지 번호"),
    size:              int            = Query(20, ge=1, le=500, description="페이지 크기"),
    current:           dict           = Depends(get_current_user),
):
    """v1.2.4: 업무 일정 목록 조회. is_assigned·obligation_type·planned_date 범위 필터, size 상한 500.

    E-1: FACTORY role 은 자기 factory_id 행만(scoped_filter). TEAM/ASSIGNED 는
    team_id 컬럼 없으므로 FACTORY→COMPANY 폴백.
    """
    supabase = get_supabase()
    filt = scoped_filter(current, supabase, {"company_id", "factory_id"})
    if filt is DENY:
        return {"status": "success", "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}}

    # ALL: 클라 company_id 유지. 그 외: scoped_filter 가 강제.
    if _is_admin(_tier(supabase, current.get("role_code"))):
        if not company_id and not factory_id:
            # ALL + 필터 없음 = 전체(기존과 동일하게 company 필수였던 분기와 맞춤:
            # 기존은 scoped_list_company 후 not scoped_cid 이면 빈결과 — ALL 에
            # company_id=None 이면 (None, False) 반환 후 `if deny_all or not scoped_cid`
            # 에서 빈결과. 즉 ALL 도 company_id 없으면 빈결과였음. 유지.)
            return {"status": "success", "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}}
        filt = {}
        if company_id:
            filt["company_id"] = company_id
        if factory_id:
            filt["factory_id"] = factory_id
    else:
        # 클라 factory_id 가 스코프 밖이면 빈결과(존재 숨김)
        if factory_id and filt.get("factory_id") and factory_id != filt["factory_id"]:
            return {"status": "success", "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}}
        if factory_id and "factory_id" not in filt:
            filt = {**filt, "factory_id": factory_id}

    q = supabase.table("work_schedules").select("*", count="exact")
    q = apply_scoped_filter(q, filt)
    if q is None:
        return {"status": "success", "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}}

    if status_code:     q = q.eq("status_code",     status_code)
    if source_type:     q = q.eq("source_type",     source_type)
    if obligation_type: q = q.eq("obligation_type", obligation_type)

    if is_assigned is False:
        q = q.is_("assigned_user_id", "null")
    elif is_assigned is True:
        q = q.not_.is_("assigned_user_id", "null")

    # v1.2.4 (LEDGER ㉙): 화면이 보내던 계획일 범위 필터를 실제 적용
    if planned_date_from: q = q.gte("planned_date", planned_date_from)
    if planned_date_to:   q = q.lte("planned_date", planned_date_to)

    # v1.2.6 (LEDGER §34): 화면이 보내던 keyword 자유검색을 실제 적용(설명·법령명·규칙코드).
    #   or_ 파싱이 쉼표로 깨지지 않도록 쉼표는 공백으로 치환.
    if keyword:
        kw = keyword.replace(",", " ").strip()
        if kw:
            q = q.or_(f"description.ilike.%{kw}%,law_name.ilike.%{kw}%,rule_code.ilike.%{kw}%")

    offset = (page - 1) * size
    result = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()

    total = result.count or 0
    return {
        "status": "success",
        "data": {
            "items":       result.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/factory/{factory_id}")
def get_factory_work_schedules(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_ws_factory_access(supabase, factory_id, current)   # 타사·타시설 404
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/inspection-set/{inspection_set_id}")
def get_inspection_set_work_schedules(inspection_set_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("inspection_set_id", inspection_set_id)
        .order("created_at", desc=True)
        .execute()
    )
    data = result.data or []
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return data
    # E-1: FACTORY/TEAM 은 factory 까지 in-memory 필터
    filt = scoped_filter(current, supabase, {"company_id", "factory_id"})
    if filt is DENY:
        return []
    out = []
    for d in data:
        if filt.get("company_id") and d.get("company_id") != filt["company_id"]:
            continue
        if filt.get("factory_id") and d.get("factory_id") != filt["factory_id"]:
            continue
        out.append(d)
    return out


# /{schedule_id}는 반드시 모든 고정경로 뒤에 선언
@router.get("/{schedule_id}")
def get_work_schedule(schedule_id: str, current: dict = Depends(get_current_user)):
    # v1.2.2: 비-uuid 경로(/summary 등)가 catch-all 에 잡혀 500(22P02) 나던 것 방지.
    if not _is_uuid(schedule_id):
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    supabase = get_supabase()
    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _ensure_ws_row(result.data[0], current, supabase)
    return result.data


@router.patch("/{schedule_id}")
def patch_work_schedule(schedule_id: str, body: SchedulePatchBody, current: dict = Depends(get_current_user)):
    """v1.2.3: 단건 갱신 — 담당자 배정(assignee_id/assigned_user_id)·상태(status_code) 등.

    대시보드 [담당자 배정](㉑)·점검 캘린더 [완료처리](㉘)·작업일정 [담당자 배정](㉝) 공통 경로.
    [주의] 완료처리의 "다음 회차 자동 생성"은 별도 기능이며 여기서 하지 않는다(상태만 저장).
    """
    if not _is_uuid(schedule_id):
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    supabase = get_supabase()
    _own = (
        supabase.table("work_schedules")
        .select("company_id,factory_id")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    if not _own.data:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _ensure_ws_row(_own.data[0], current, supabase)
    now = _now()

    fields: dict = {}
    if "assigned_user_id" in body.__fields_set__:
        fields["assigned_user_id"] = body.assigned_user_id
    elif "assignee_id" in body.__fields_set__:
        fields["assigned_user_id"] = body.assignee_id
    if body.status_code is not None:
        fields["status_code"] = body.status_code
    elif body.status is not None:
        fields["status_code"] = body.status
    for k in ("is_excluded", "excluded_reason", "custom_cycle", "resolved_at", "planned_date"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다")

    updated = _apply_one_update(supabase, schedule_id, fields, now)
    if not updated:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")

    row = supabase.table("work_schedules").select("*").eq("id", schedule_id).limit(1).execute()
    return {"status": "success", "data": (row.data[0] if row.data else None)}
