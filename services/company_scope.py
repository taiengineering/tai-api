"""회사 스코프 가드 — P13 공통 (정본: routers/leader_scope.py).

Layer2 데이터 행 필터. role_data_scope 5단:
  ALL / COMPANY / FACTORY / TEAM / ASSIGNED

E-1 (2026-08-22): FACTORY 실동작. TEAM은 테이블에 team_id 없으면 FACTORY→COMPANY
폴백. ASSIGNED는 E-3(work_assignments) 전까지 동일 폴백.
메뉴 강제(Layer1)와 독립 — 테넌트 메뉴가 열려 있어도 행 필터는 tier로 좁힌다.

기존 시그니처(_is_admin / scoped_list_company / require_company_id 등)는 유지.
scoped_list_company 는 company_id 컬럼만 인지하므로 FACTORY도 COMPANY로 폴백
(전면 일괄 금지 — 자원별 opt-in 은 scoped_filter 사용).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set, Union

from fastapi import HTTPException


# 목록/상세에서 "빈 결과"를 뜻하는 센티널. Falsey 이지만 {}(ALL) 과 구분한다.
class _Deny:
    __slots__ = ()

    def __bool__(self) -> bool:  # noqa: D401
        return False

    def __repr__(self) -> str:
        return "DENY"


DENY = _Deny()

ScopeFilter = Union[Dict[str, Any], _Deny]


def _scope(supabase, role_code) -> str:
    """role_data_scope.scope_type. 미정의는 가장 좁게(TEAM)."""
    if not role_code:
        return "TEAM"
    try:
        r = (
            supabase.table("role_data_scope")
            .select("scope_type")
            .eq("role_code", role_code)
            .limit(1)
            .execute()
        )
        return (r.data[0]["scope_type"] if r.data and r.data[0].get("scope_type") else "TEAM")
    except Exception:
        return "TEAM"


def _tier(sb, role) -> str:
    """5단 별칭 — ALL/COMPANY/FACTORY/TEAM/ASSIGNED. _scope 와 동일."""
    return _scope(sb, role)


def _is_admin(ctx_scope) -> bool:
    return ctx_scope == "ALL"  # 플랫폼 총관리자만 전사


def _require_admin(current: dict, supabase) -> None:
    if not _is_admin(_scope(supabase, current.get("role_code"))):
        raise HTTPException(status_code=403, detail="권한이 없습니다")


def _cols(table_cols: Iterable[str]) -> Set[str]:
    return set(table_cols) if not isinstance(table_cols, set) else table_cols


def _via_factory(sb, company_id: str) -> ScopeFilter:
    """company_id 컬럼이 없고 factory_id 만 있는 테이블 — 회사 소속 factory_id IN."""
    try:
        r = sb.table("factories").select("id").eq("company_id", company_id).execute()
    except Exception:
        return DENY
    ids = [row["id"] for row in (r.data or []) if row.get("id")]
    if not ids:
        return DENY
    return {"factory_id__in": ids}


def scoped_filter(current: dict, sb, table_cols: Iterable[str]) -> ScopeFilter:
    """목록/상세용 행 필터. {}=필터없음(ALL), DENY=빈결과, dict=eq/in 조건.

    폴백 규칙(자원에 필터 컬럼 없으면 상위 tier):
      FACTORY & factory_id 없음 → COMPANY
      TEAM    & team_id 없음    → FACTORY(있으면) 아니면 COMPANY
      ASSIGNED (E-3 전)         → TEAM과 동일 폴백
    FACTORY·TEAM 인데 자기 factory_id/team_id 미배정이면 DENY(빈 결과).
    """
    cols = _cols(table_cols)
    tier = _tier(sb, current.get("role_code"))

    if tier == "ALL":
        return {}

    cid = current.get("company_id")
    if not cid:
        return DENY

    # COMPANY, 또는 factory/team 컬럼이 없어 더 좁힐 수 없는 경우
    if tier == "COMPANY" or (
        tier in ("FACTORY", "TEAM", "ASSIGNED")
        and "factory_id" not in cols
        and "team_id" not in cols
    ):
        if "company_id" in cols:
            return {"company_id": cid}
        if "factory_id" in cols:
            return _via_factory(sb, cid)
        return DENY

    if tier == "FACTORY":
        if "factory_id" not in cols:
            # 방어: 위 분기에서 걸러지지만 명시
            if "company_id" in cols:
                return {"company_id": cid}
            return DENY
        fid = current.get("factory_id")
        if not fid:
            return DENY  # factory 미배정 → 빈결과 (리스크#2: 배포 전 backfill)
        out: Dict[str, Any] = {"factory_id": fid}
        if "company_id" in cols:
            out["company_id"] = cid  # 방어적 이중 경계
        return out

    if tier == "TEAM":
        if "team_id" in cols:
            tid = current.get("team_id")
            if not tid:
                return DENY
            out = {"team_id": tid}
            if "company_id" in cols:
                out["company_id"] = cid
            return out
        # team_id 컬럼 없음 → FACTORY 폴백
        if "factory_id" in cols:
            fid = current.get("factory_id")
            if not fid:
                return DENY
            out = {"factory_id": fid}
            if "company_id" in cols:
                out["company_id"] = cid
            return out
        if "company_id" in cols:
            return {"company_id": cid}
        return DENY

    if tier == "ASSIGNED":
        # E-3 stub: work_assignments 미연결 — TEAM과 동일 폴백(과노출 방지보다
        # 기존 COMPANY 가시성을 깨지 않으려면 호출측이 company_id-only cols 로
        # scoped_list_company 를 쓰면 됨. factory cols opt-in 시엔 FACTORY 폴백).
        if "factory_id" in cols:
            fid = current.get("factory_id")
            if fid:
                out = {"factory_id": fid}
                if "company_id" in cols:
                    out["company_id"] = cid
                return out
            # factory 미배정이면 COMPANY 폴백(ASSIGNED는 E-3 전 과도한 DENY 회피)
            if "company_id" in cols:
                return {"company_id": cid}
            return DENY
        if "company_id" in cols:
            return {"company_id": cid}
        return DENY

    # 알 수 없는 tier → 가장 좁게 DENY
    return DENY


def apply_scoped_filter(query, filt: ScopeFilter):
    """supabase query 에 scoped_filter 결과 적용. DENY 이면 None 반환."""
    if filt is DENY:
        return None
    if not filt:
        return query
    for col, val in filt.items():
        if col.endswith("__in"):
            query = query.in_(col[: -len("__in")], val)
        else:
            query = query.eq(col, val)
    return query


def _ensure_own_company(
    resource_company_id,
    current: dict,
    supabase,
    not_found: str,
    resource_factory_id=None,
) -> None:
    """비-ALL 이 타사 자원을 보면 404(존재 숨김).

    E-1: resource_factory_id 가 주어지고 tier 가 FACTORY/TEAM 이면
    자기 factory_id 일치까지 확인. 미전달 시 회사만 검사(하위호환).
    """
    tier = _tier(supabase, current.get("role_code"))
    if tier == "ALL":
        return
    token_cid = current.get("company_id")
    if not token_cid or resource_company_id != token_cid:
        raise HTTPException(status_code=404, detail=not_found)
    # TEAM 은 E-2까지 FACTORY 취급(상세에 factory_id 가 넘어온 경우)
    if tier in ("FACTORY", "TEAM") and resource_factory_id is not None:
        token_fid = current.get("factory_id")
        if not token_fid or resource_factory_id != token_fid:
            raise HTTPException(status_code=404, detail=not_found)


def _ensure_factory_own(sb, factory_id, current) -> None:
    """시설이 토큰 회사 소속인지. (회사 경계 — 기존 동작 유지)

    FACTORY tier 의 '자기 factory만' 강제는 자원별 opt-in:
    _ensure_own_company(..., resource_factory_id=...) 또는 scoped_filter.
    전면 일괄 금지를 위해 여기서는 company 일치만 본다.
    """
    if _is_admin(_scope(sb, current.get("role_code"))):
        return
    f = sb.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
    if not f.data or f.data[0].get("company_id") != current.get("company_id"):
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")


def _forced_company_id(current: dict, supabase, company_id=None):
    """비-ALL 이면 토큰 company_id(클라 값 무시). ALL 이면 클라 값 유지."""
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return company_id
    return current.get("company_id")


# ── 전체 적용(safe 라우터 인증·회사스코프) 표준 헬퍼 (2026-08-20 가산) ──
# 설계: taieng/docs/2026-08-20_safe-auth-scope-module-design.md
# 기존 함수 불변. 아래는 생성/목록 배선의 보일러플레이트를 표준화한다.

def require_company_id(current: dict, supabase):
    """생성용: 비-ALL 은 토큰 company_id 필수. 무회사 → 403(회사 등록 필요).

    ALL 은 None 허용(있으면 그대로 반환). 반환값을 payload 의 company_id 로
    강제 주입해 client 가 보낸 company_id 를 무시한다(P13).
    """
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return current.get("company_id")
    cid = current.get("company_id")
    if not cid:
        raise HTTPException(status_code=403, detail="회사 등록이 필요합니다.")
    return cid


def require_scope_ids(current: dict, supabase, table_cols: Iterable[str] = ()) -> Dict[str, Any]:
    """생성용: tier 에 맞는 company_id / factory_id / team_id 주입 dict.

    FACTORY role 은 자기 factory_id 필수(미배정 403).
    TEAM 이고 table 에 team_id 있으면 team_id 주입(미배정 403).
    ALL 은 토큰에 있는 값만 선택적으로 포함(강제 없음).
    """
    cols = _cols(table_cols)
    tier = _tier(supabase, current.get("role_code"))
    out: Dict[str, Any] = {}

    if tier == "ALL":
        if current.get("company_id"):
            out["company_id"] = current["company_id"]
        if current.get("factory_id") and "factory_id" in cols:
            out["factory_id"] = current["factory_id"]
        if current.get("team_id") and "team_id" in cols:
            out["team_id"] = current["team_id"]
        return out

    cid = current.get("company_id")
    if not cid:
        raise HTTPException(status_code=403, detail="회사 등록이 필요합니다.")
    out["company_id"] = cid

    if tier == "FACTORY" or (tier == "TEAM" and "team_id" not in cols):
        if "factory_id" in cols:
            fid = current.get("factory_id")
            if not fid:
                raise HTTPException(
                    status_code=403,
                    detail="시설 배정이 필요합니다. 관리자에게 factory_id 지정을 요청하세요.",
                )
            out["factory_id"] = fid
    elif tier == "TEAM" and "team_id" in cols:
        tid = current.get("team_id")
        if not tid:
            raise HTTPException(
                status_code=403,
                detail="팀 배정이 필요합니다. 관리자에게 team_id 지정을 요청하세요.",
            )
        out["team_id"] = tid
        if current.get("factory_id") and "factory_id" in cols:
            out["factory_id"] = current["factory_id"]

    return out


def scoped_list_company(current: dict, supabase, company_id=None):
    """목록용: (scoped_company_id, deny_all) 반환.

    None-skip 전체노출 차단 — 비-ALL·무회사는 deny_all=True 이며, 라우터는
    이때 쿼리를 실행하지 말고 빈 결과를 반환해야 한다(company_id=None 을 그대로
    필터로 넘기면 run_list_query 등이 None 을 skip 해 전사 노출됨).
    ALL 은 클라 company_id 유지(None = 전체).

    E-1 하위호환: company_id 컬럼만 인지 → FACTORY/TEAM 도 COMPANY 폴백.
    FACTORY 실동작이 필요한 자원은 scoped_filter(..., {"company_id","factory_id"}) 사용.
    """
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return company_id, False
    # scoped_filter 로 위임(company_id only → FACTORY 도 COMPANY)
    filt = scoped_filter(current, supabase, {"company_id"})
    if filt is DENY:
        return None, True
    return filt.get("company_id"), False
