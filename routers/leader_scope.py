"""
TBM 리더 스코프 API — v1.1.0

DESIGN_phase3-leader-auth_v2 §4 A-3 구현.

리더(관리감독자, role_code=013)가 자기 팀 범위의 데이터만 조회·생성하도록
서버가 스코프를 강제한다.

API:
  GET  /leader/me            내 리더 컨텍스트(팀·스코프 등급)
  GET  /leader/groups        내 팀의 그룹 목록
  GET  /leader/members       내 팀 그룹원 목록 (group_id 로 좁힐 수 있음)
  GET  /leader/templates     내 팀에서 쓸 수 있는 TBM 템플릿
  POST /leader/tbm           TBM 생성 (그룹원 자동 소집)

핵심 원칙 — 클라이언트가 보낸 team_id 를 신뢰하지 않는다.
  요청 바디나 쿼리의 team_id 로 판정하면, 값을 바꾸는 것만으로 남의 팀에
  접근된다. 스코프의 기준값은 오직 토큰에서 도출한 users.team_id 다.
  group_id 처럼 클라이언트가 지정하는 값은 받되, 그것이 내 팀 소속인지
  서버가 반드시 재확인한다.

TBM 생성은 기존 로직을 재사용한다(v1.1.0).
  POST /tbm-templates/{id}/use 가 group_id 지정 시 그룹원을 자동 소집한다.
  그 로직을 다시 만들지 않고, 소유권 검증만 앞에 붙여 위임한다.
  기존 /use 는 웹 관리자(안전관리자) 경로이므로 변경하지 않는다 —
  거기서는 전체 권한을 갖는 것이 정상이다.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/leader", tags=["LeaderScope"])

# 팀 경계를 넘어 볼 수 있는 등급. 이보다 좁은 등급은 자기 팀으로 제한한다.
WIDE_SCOPES = ("ALL", "COMPANY", "FACTORY")


def _scope_of(supabase, role_code: Optional[str]) -> str:
    """role_data_scope 에서 등급을 읽는다. 정의가 없으면 가장 좁게 본다.

    미정의 role 을 넓게 열어주면 권한이 새므로, 모르는 값은 TEAM 으로 좁힌다.
    """
    if not role_code:
        return "TEAM"
    try:
        r = supabase.table("role_data_scope").select("scope_type").eq("role_code", role_code).limit(1).execute()
        if r.data and r.data[0].get("scope_type"):
            return r.data[0]["scope_type"]
    except Exception as e:
        log.error(f"[leader] role_data_scope 조회 실패 role_code={role_code}: {e}")
    return "TEAM"


def leader_context(current_user: dict = Depends(get_current_user)) -> dict:
    """토큰 → users → 스코프 컨텍스트.

    get_current_user 가 토큰을 검증하고 users 행을 돌려주므로,
    여기서 나오는 team_id 는 클라이언트가 조작할 수 없다.
    """
    supabase = get_supabase()
    scope = _scope_of(supabase, current_user.get("role_code"))
    return {
        "user_id":    current_user["id"],
        "name":       current_user.get("name"),
        "role_code":  current_user.get("role_code"),
        "scope_type": scope,
        "team_id":    current_user.get("team_id"),
        "factory_id": current_user.get("factory_id"),
        "company_id": current_user.get("company_id"),
    }


def _require_team(ctx: dict) -> str:
    """팀 스코프 사용자의 team_id 를 확보한다.

    리더인데 team_id 가 비어 있으면 조회 대상을 특정할 수 없다.
    빈 목록을 돌려주면 "우리 팀에 아무도 없다"로 오인되므로 명시적으로 막는다.
    """
    team_id = ctx.get("team_id")
    if not team_id:
        raise HTTPException(
            status_code=409,
            detail="소속 팀이 지정되지 않았습니다. 안전관리자에게 팀 배정을 요청해주세요.",
        )
    return team_id


def _my_group_ids(supabase, team_id: str) -> dict:
    """내 팀의 활성 그룹 id → 이름. 접근 가능한 경계다."""
    try:
        gr = supabase.table("groups").select("id,group_name").eq("team_id", team_id).eq("is_active", True).execute()
        return {g["id"]: g.get("group_name") for g in (gr.data or [])}
    except Exception as e:
        log.error(f"[leader] groups 조회 실패 team_id={team_id}: {e}")
        raise HTTPException(status_code=500, detail="그룹 목록을 불러오지 못했습니다")


@router.get("/me")
def get_leader_me(ctx: dict = Depends(leader_context)):
    """내 리더 컨텍스트. 앱이 화면을 분기할 때 쓴다.

    분기 근거는 서버가 정한 값이며, 앱은 표시만 한다.
    """
    supabase = get_supabase()
    team = None
    if ctx.get("team_id"):
        try:
            t = supabase.table("teams").select("id,team_name,team_code,department_id,factory_id,construction_site_id") \
                .eq("id", ctx["team_id"]).limit(1).execute()
            if t.data:
                team = t.data[0]
        except Exception as e:
            log.error(f"[leader] teams 조회 실패 team_id={ctx['team_id']}: {e}")

    return {
        "status": "success",
        "data": {
            "user_id":    ctx["user_id"],
            "name":       ctx["name"],
            "role_code":  ctx["role_code"],
            "scope_type": ctx["scope_type"],
            "is_leader":  ctx["scope_type"] == "TEAM" and bool(ctx.get("team_id")),
            "team":       team,
        },
    }


@router.get("/groups")
def list_my_groups(ctx: dict = Depends(leader_context)):
    """내 팀의 그룹 목록.

    team_id 를 파라미터로 받지 않는다. 받으면 남의 팀을 넘겨볼 여지가 생긴다.
    """
    supabase = get_supabase()
    team_id = _require_team(ctx)

    try:
        r = supabase.table("groups").select("id,group_name,group_code,lead_worker_id,is_active") \
            .eq("team_id", team_id).eq("is_active", True) \
            .order("group_name").execute()
        items = r.data or []
    except Exception as e:
        log.error(f"[leader] groups 조회 실패 team_id={team_id}: {e}")
        raise HTTPException(status_code=500, detail="그룹 목록을 불러오지 못했습니다")

    # 그룹별 인원수를 함께 준다. 리더가 소집 전에 규모를 확인한다.
    for g in items:
        try:
            c = supabase.table("worker_group").select("id", count="exact").eq("group_id", g["id"]).execute()
            g["member_count"] = c.count or 0
        except Exception:
            g["member_count"] = None

    return {"status": "success", "data": {"team_id": team_id, "items": items, "total": len(items)}}


@router.get("/members")
def list_my_members(
    group_id: Optional[str] = Query(None, description="특정 그룹으로 좁힐 때"),
    ctx: dict = Depends(leader_context),
):
    """내 팀 그룹원 목록.

    group_id 는 클라이언트가 지정할 수 있으나, 그 그룹이 내 팀 소속인지
    서버가 반드시 재확인한다. 확인 없이 쓰면 남의 팀 그룹 id 를 넣어
    그룹원 명단을 가져갈 수 있다.
    """
    supabase = get_supabase()
    team_id = _require_team(ctx)
    my_groups = _my_group_ids(supabase, team_id)

    if not my_groups:
        return {"status": "success", "data": {"team_id": team_id, "items": [], "total": 0}}

    if group_id:
        if group_id not in my_groups:
            # 존재 여부를 알려주지 않는다. 남의 팀 그룹 id 를 넣어 존재를
            # 확인하는 것도 정보 노출이다.
            raise HTTPException(status_code=403, detail="접근할 수 없는 그룹입니다")
        target_ids = [group_id]
    else:
        target_ids = list(my_groups.keys())

    try:
        wg = supabase.table("worker_group").select("id,worker_id,group_id,is_lead,assigned_at") \
            .in_("group_id", target_ids).execute()
        rows = wg.data or []
    except Exception as e:
        log.error(f"[leader] worker_group 조회 실패 team_id={team_id}: {e}")
        raise HTTPException(status_code=500, detail="그룹원 목록을 불러오지 못했습니다")

    worker_ids = list({r["worker_id"] for r in rows if r.get("worker_id")})
    workers = {}
    if worker_ids:
        try:
            w = supabase.table("worker_registry").select("id,name,phone,user_id,app_installed") \
                .in_("id", worker_ids).execute()
            workers = {x["id"]: x for x in (w.data or [])}
        except Exception as e:
            log.error(f"[leader] worker_registry 조회 실패: {e}")

    items = []
    for r in rows:
        w = workers.get(r.get("worker_id")) or {}
        items.append({
            "id":            r["id"],
            "worker_id":     r.get("worker_id"),
            "group_id":      r.get("group_id"),
            "group_name":    my_groups.get(r.get("group_id")),
            "is_lead":       r.get("is_lead"),
            "assigned_at":   r.get("assigned_at"),
            "name":          w.get("name"),
            "phone":         w.get("phone"),
            # 앱 설치 여부는 푸시 도달 가능성을 뜻한다. 리더가 서명 요청 전에
            # 누구에게 푸시가 갈 수 있는지 판단해야 한다.
            "app_installed": w.get("app_installed"),
        })

    items.sort(key=lambda x: (x.get("group_name") or "", not x.get("is_lead"), x.get("name") or ""))

    return {"status": "success", "data": {"team_id": team_id, "items": items, "total": len(items)}}


@router.get("/templates")
def list_my_templates(ctx: dict = Depends(leader_context)):
    """내 팀에서 쓸 수 있는 TBM 템플릿.

    팀 전용 템플릿 + 팀 미지정(전역·시설) 템플릿을 함께 준다.
    기존 GET /tbm-templates 의 스코핑 규칙(v1.3.0)과 같은 의미이며,
    team_id 를 클라이언트가 넘기지 않도록 감싼 것이다.
    """
    supabase = get_supabase()
    team_id = _require_team(ctx)

    try:
        q = supabase.table("tbm_templates").select(
            "id,template_name,team_id,factory_id,work_location,work_description,use_count,last_used_at"
        ).eq("is_active", True).neq("template_name", "__LIBRARY__")

        # 팀 전용 + 팀 미지정. 팀 미지정은 시설이 같거나 시설도 없는 것으로 한정한다.
        if ctx.get("factory_id"):
            q = q.or_(
                f"team_id.eq.{team_id},"
                f"and(team_id.is.null,or(factory_id.is.null,factory_id.eq.{ctx['factory_id']}))"
            )
        else:
            q = q.or_(f"team_id.eq.{team_id},and(team_id.is.null,factory_id.is.null)")

        r = q.order("use_count", desc=True).limit(50).execute()
        items = r.data or []
    except Exception as e:
        log.error(f"[leader] tbm_templates 조회 실패 team_id={team_id}: {e}")
        raise HTTPException(status_code=500, detail="템플릿 목록을 불러오지 못했습니다")

    return {"status": "success", "data": {"team_id": team_id, "items": items, "total": len(items)}}


# ══════════════════════════════════════════
# TBM 생성 — 기존 use_template 로직 재사용
# ══════════════════════════════════════════

class LeaderTbmCreate(BaseModel):
    template_id: str
    group_id: str                                  # 소집 대상 그룹. 내 팀 소속이어야 한다.
    work_date: Optional[str] = None                # YYYY-MM-DD, 없으면 today
    override_location: Optional[str] = None
    override_description: Optional[str] = None


@router.post("/tbm")
async def create_team_tbm(
    body: LeaderTbmCreate,
    ctx: dict = Depends(leader_context),
):
    """리더가 자기 팀 그룹의 TBM 을 만든다.

    기존 POST /tbm-templates/{id}/use 를 그대로 쓴다. 그 경로가 group_id 지정 시
    그룹원을 자동 소집하는 로직을 이미 갖고 있어 다시 만들지 않는다.

    다만 /use 는 group_id 소유권을 검증하지 않는다 — body.group_id 를 그대로 쓰고
    groups 에서 team_id 를 역으로 읽을 뿐이며 인증도 없다. 리더가 그 경로를 직접
    부르면 남의 팀 group_id 로 그 그룹원 전체를 소집할 수 있다.
    그래서 여기서 소유권을 먼저 확인한 뒤 위임한다.

    기존 /use 자체는 바꾸지 않는다. 웹 관리자(안전관리자) 경로이며 거기서는
    전체 권한을 갖는 것이 정상이다.
    """
    supabase = get_supabase()
    team_id = _require_team(ctx)

    # 1) group_id 가 내 팀 소속인지 확인. 이것이 이 경로의 존재 이유다.
    my_groups = _my_group_ids(supabase, team_id)
    if body.group_id not in my_groups:
        # 존재 여부를 알려주지 않는다.
        raise HTTPException(status_code=403, detail="접근할 수 없는 그룹입니다")

    # 2) template_id 도 확인한다. 남의 팀 전용 템플릿을 끌어다 쓰면
    #    그 팀의 위험요인·안전수칙이 우리 TBM 기록에 남는다.
    try:
        t = supabase.table("tbm_templates").select("id,team_id,factory_id,template_name") \
            .eq("id", body.template_id).eq("is_active", True).limit(1).execute()
    except Exception as e:
        log.error(f"[leader] 템플릿 조회 실패 template_id={body.template_id}: {e}")
        raise HTTPException(status_code=500, detail="템플릿을 확인하지 못했습니다")

    if not t.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다")

    tmpl = t.data[0]
    tmpl_team = tmpl.get("team_id")
    if tmpl_team and tmpl_team != team_id:
        raise HTTPException(status_code=403, detail="접근할 수 없는 템플릿입니다")

    # 3) 기존 로직에 위임. conductor_name 은 토큰에서 온 리더 이름을 쓴다 —
    #    클라이언트가 보낸 이름을 쓰면 진행자를 사칭할 수 있다.
    from routers.tbm_templates import use_template, TbmUseBody

    use_body = TbmUseBody(
        work_date=body.work_date,
        conductor_name=ctx.get("name"),
        override_location=body.override_location,
        override_description=body.override_description,
        group_id=body.group_id,
        team_id=team_id,
    )

    result = await use_template(body.template_id, use_body)

    log.info(f"[leader] TBM 생성 team_id={team_id} group_id={body.group_id} "
             f"template={tmpl.get('template_name')} by={ctx.get('name')}")

    return result
