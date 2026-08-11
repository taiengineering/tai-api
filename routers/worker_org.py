"""
작업자 조직배정 조회 — worker_org.py v1.0.0

GET /worker-registry/{id}/org-assignment
  작업자의 현재 그룹 배정(대표 1건)을 group→team→department 로 해석해 반환.
  작업자 수정 패널의 부서·팀·그룹 프리필용. (배정 없으면 data=null)

DB: worker_group, groups, teams, departments
경로가 3세그먼트라 worker_registry.py의 /template · PATCH·DELETE /{id} 와 충돌 없음.
"""
from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(tags=["worker_registry"])


@router.get("/worker-registry/{worker_id}/org-assignment")
def get_worker_org_assignment(worker_id: str):
    sb = get_supabase()
    wg = sb.table("worker_group").select(
        "id, group_id, is_lead, "
        "groups(id, group_name, team_id, "
        "teams(id, team_name, department_id, "
        "departments(id, department_name)))"
    ).eq("worker_id", worker_id).limit(1).execute()

    if not wg.data:
        return {"status": "success", "data": None}

    row = wg.data[0]
    g = row.get("groups") or {}
    if not isinstance(g, dict):
        g = {}
    t = g.get("teams") or {}
    if not isinstance(t, dict):
        t = {}
    d = t.get("departments") or {}
    if not isinstance(d, dict):
        d = {}

    return {
        "status": "success",
        "data": {
            "assign_id":       row.get("id"),
            "group_id":        g.get("id"),
            "group_name":      g.get("group_name"),
            "team_id":         t.get("id"),
            "team_name":       t.get("team_name"),
            "department_id":   d.get("id"),
            "department_name": d.get("department_name"),
        },
    }
