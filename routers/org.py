"""
조직 관리 라우터 — org.py  v1.0.0

회사 > 시설 > 부서 > 팀 > 그룹 > 근로자 계층 (Phase 1).
TBM 하이브리드 설계: taieng/docs/2026-08-11_TBM-team-group-hybrid-design.md

endpoints
  부서  GET/POST /departments        · PATCH/DELETE /departments/{id}
  팀    GET/POST /teams              · PATCH/DELETE /teams/{id}         (lead_worker_id = 팀 리더 1명)
  그룹  GET/POST /groups             · PATCH/DELETE /groups/{id}        (lead_worker_id = 조장)
  배정  GET/POST /worker-group       · PATCH/DELETE /worker-group/{id}  (다중소속, is_lead)

DB: departments, teams, groups, worker_group
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

router = APIRouter(tags=["org"])
VERSION = "1.0.0"


def _now() -> str:
    return serialize_external_utc(now_kst())


# ============================================================
# 스키마
# ============================================================

class DepartmentCreate(BaseModel):
    company_id: str
    factory_id: Optional[str] = None
    construction_site_id: Optional[str] = None
    department_name: str
    department_code: Optional[str] = None


class DepartmentUpdate(BaseModel):
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    is_active: Optional[bool] = None


class TeamCreate(BaseModel):
    department_id: Optional[str] = None
    factory_id: Optional[str] = None
    construction_site_id: Optional[str] = None
    team_name: str
    team_code: Optional[str] = None
    description: Optional[str] = None
    lead_worker_id: Optional[str] = None   # 팀 리더 1명 (단일 컬럼 = 강제 1명)


class TeamUpdate(BaseModel):
    department_id: Optional[str] = None
    team_name: Optional[str] = None
    team_code: Optional[str] = None
    description: Optional[str] = None
    lead_worker_id: Optional[str] = None
    is_active: Optional[bool] = None


class GroupCreate(BaseModel):
    team_id: str
    company_id: Optional[str] = None
    group_name: str
    group_code: Optional[str] = None
    lead_worker_id: Optional[str] = None   # 조장 (옵션 1명)


class GroupUpdate(BaseModel):
    group_name: Optional[str] = None
    group_code: Optional[str] = None
    lead_worker_id: Optional[str] = None
    is_active: Optional[bool] = None


class WorkerGroupAssign(BaseModel):
    worker_id: str
    group_id: str
    is_lead: Optional[bool] = False


class WorkerGroupUpdate(BaseModel):
    is_lead: bool


# ============================================================
# 부서 (departments)
# ============================================================

@router.get("/departments")
def list_departments(
    company_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
):
    sb = get_supabase()
    q = sb.table("departments").select("*")
    if company_id:           q = q.eq("company_id", company_id)
    if factory_id:           q = q.eq("factory_id", factory_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    if is_active is not None: q = q.eq("is_active", is_active)
    res = q.order("department_name").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@router.post("/departments")
def create_department(body: DepartmentCreate):
    if not body.department_name.strip():
        raise HTTPException(status_code=422, detail="부서명은 필수입니다.")
    # 시설 XOR (factory_id 또는 construction_site_id 중 정확히 하나)
    if bool(body.factory_id) == bool(body.construction_site_id):
        raise HTTPException(status_code=422, detail="factory_id 또는 construction_site_id 중 정확히 하나가 필요합니다.")
    sb = get_supabase()
    data = {
        "company_id":           body.company_id,
        "factory_id":           body.factory_id,
        "construction_site_id": body.construction_site_id,
        "department_name":      body.department_name.strip(),
        "department_code":      body.department_code,
        "is_active":            True,
    }
    res = sb.table("departments").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="부서 생성 실패")
    return {"status": "success", "message": "부서가 생성됐습니다.", "data": res.data[0]}


@router.patch("/departments/{dept_id}")
def update_department(dept_id: str, body: DepartmentUpdate):
    sb = get_supabase()
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    upd["updated_at"] = _now()
    res = sb.table("departments").update(upd).eq("id", dept_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")
    return {"status": "success", "message": "부서가 수정됐습니다.", "data": res.data[0]}


@router.delete("/departments/{dept_id}")
def delete_department(dept_id: str):
    sb = get_supabase()
    res = sb.table("departments").update({"is_active": False, "updated_at": _now()}).eq("id", dept_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")
    return {"status": "success", "message": "부서가 비활성화됐습니다."}


# ============================================================
# 팀 (teams)
# ============================================================

@router.get("/teams")
def list_teams(
    department_id: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
):
    sb = get_supabase()
    q = sb.table("teams").select("*")
    if department_id:        q = q.eq("department_id", department_id)
    if factory_id:           q = q.eq("factory_id", factory_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    if is_active is not None: q = q.eq("is_active", is_active)
    res = q.order("team_name").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@router.post("/teams")
def create_team(body: TeamCreate):
    if not body.team_name.strip():
        raise HTTPException(status_code=422, detail="팀명은 필수입니다.")
    sb = get_supabase()
    data = {
        "department_id":        body.department_id,
        "factory_id":           body.factory_id,
        "construction_site_id": body.construction_site_id,
        "team_name":            body.team_name.strip(),
        "team_code":            body.team_code,
        "description":          body.description,
        "lead_worker_id":       body.lead_worker_id,
        "is_active":            True,
    }
    res = sb.table("teams").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="팀 생성 실패")
    return {"status": "success", "message": "팀이 생성됐습니다.", "data": res.data[0]}


@router.patch("/teams/{team_id}")
def update_team(team_id: str, body: TeamUpdate):
    sb = get_supabase()
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    upd["updated_at"] = _now()
    res = sb.table("teams").update(upd).eq("id", team_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")
    return {"status": "success", "message": "팀이 수정됐습니다.", "data": res.data[0]}


@router.delete("/teams/{team_id}")
def delete_team(team_id: str):
    sb = get_supabase()
    res = sb.table("teams").update({"is_active": False, "updated_at": _now()}).eq("id", team_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다.")
    return {"status": "success", "message": "팀이 비활성화됐습니다."}


# ============================================================
# 그룹 (groups) — 팀 하위 소단위 = TBM 실제 단위
# ============================================================

@router.get("/groups")
def list_groups(
    team_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
):
    sb = get_supabase()
    q = sb.table("groups").select("*")
    if team_id:               q = q.eq("team_id", team_id)
    if is_active is not None:  q = q.eq("is_active", is_active)
    res = q.order("group_name").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@router.post("/groups")
def create_group(body: GroupCreate):
    if not body.group_name.strip():
        raise HTTPException(status_code=422, detail="그룹명은 필수입니다.")
    sb = get_supabase()
    data = {
        "team_id":        body.team_id,
        "company_id":     body.company_id,
        "group_name":     body.group_name.strip(),
        "group_code":     body.group_code,
        "lead_worker_id": body.lead_worker_id,
        "is_active":      True,
    }
    res = sb.table("groups").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="그룹 생성 실패")
    return {"status": "success", "message": "그룹이 생성됐습니다.", "data": res.data[0]}


@router.patch("/groups/{group_id}")
def update_group(group_id: str, body: GroupUpdate):
    sb = get_supabase()
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    upd["updated_at"] = _now()
    res = sb.table("groups").update(upd).eq("id", group_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return {"status": "success", "message": "그룹이 수정됐습니다.", "data": res.data[0]}


@router.delete("/groups/{group_id}")
def delete_group(group_id: str):
    sb = get_supabase()
    res = sb.table("groups").update({"is_active": False, "updated_at": _now()}).eq("id", group_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return {"status": "success", "message": "그룹이 비활성화됐습니다."}


# ============================================================
# 근로자-그룹 배정 (worker_group) — 다중소속
# ============================================================

@router.get("/worker-group")
def list_worker_group(
    group_id: Optional[str] = Query(None),
    worker_id: Optional[str] = Query(None),
):
    """그룹 기준(그룹원 목록) 또는 근로자 기준(소속 그룹 목록) 조회. 근로자 정보 임베드."""
    sb = get_supabase()
    q = sb.table("worker_group").select(
        "id, worker_id, group_id, is_lead, assigned_at, "
        "worker_registry(name, phone, job_type_code, job_type_name)"
    )
    if group_id:  q = q.eq("group_id", group_id)
    if worker_id: q = q.eq("worker_id", worker_id)
    res = q.order("assigned_at").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@router.post("/worker-group")
def assign_worker_group(body: WorkerGroupAssign):
    """근로자를 그룹에 배정(다중소속). 이미 배정돼 있으면 그대로 반환."""
    sb = get_supabase()
    dup = sb.table("worker_group").select("id").eq(
        "worker_id", body.worker_id
    ).eq("group_id", body.group_id).limit(1).execute()
    if dup.data:
        return {"status": "success", "message": "이미 배정된 근로자입니다.", "data": {"id": dup.data[0]["id"]}}
    data = {
        "worker_id": body.worker_id,
        "group_id":  body.group_id,
        "is_lead":   bool(body.is_lead),
    }
    res = sb.table("worker_group").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="배정 실패")
    return {"status": "success", "message": "근로자가 그룹에 배정됐습니다.", "data": res.data[0]}


@router.patch("/worker-group/{assign_id}")
def update_worker_group(assign_id: str, body: WorkerGroupUpdate):
    """배정의 조장 여부(is_lead) 변경."""
    sb = get_supabase()
    res = sb.table("worker_group").update({"is_lead": body.is_lead}).eq("id", assign_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="배정을 찾을 수 없습니다.")
    return {"status": "success", "message": "배정이 수정됐습니다.", "data": res.data[0]}


@router.delete("/worker-group/{assign_id}")
def unassign_worker_group(assign_id: str):
    """근로자를 그룹에서 해제(하드 삭제 — 배정 이력이 아니라 현재 소속만 관리)."""
    sb = get_supabase()
    sb.table("worker_group").delete().eq("id", assign_id).execute()
    return {"status": "success", "message": "배정이 해제됐습니다."}
