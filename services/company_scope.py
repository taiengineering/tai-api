"""회사 스코프 가드 — P13 공통 (정본: routers/leader_scope.py).

ALL(플랫폼 총관리자)만 전사. 그 외는 토큰 company_id 강제·소유권 404.
"""
from fastapi import HTTPException


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


def _is_admin(ctx_scope) -> bool:
    return ctx_scope == "ALL"  # 플랫폼 총관리자만 전사


def _require_admin(current: dict, supabase) -> None:
    if not _is_admin(_scope(supabase, current.get("role_code"))):
        raise HTTPException(status_code=403, detail="권한이 없습니다")


def _ensure_own_company(resource_company_id, current: dict, supabase, not_found: str) -> None:
    """비-ALL 이 타사 자원을 보면 404(존재 숨김)."""
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return
    token_cid = current.get("company_id")
    if not token_cid or resource_company_id != token_cid:
        raise HTTPException(status_code=404, detail=not_found)


def _ensure_factory_own(sb, factory_id, current) -> None:
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
# 기존 함수 불변. 아래 2개는 생성/목록 배선의 보일러플레이트를 표준화한다.

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


def scoped_list_company(current: dict, supabase, company_id=None):
    """목록용: (scoped_company_id, deny_all) 반환.

    None-skip 전체노출 차단 — 비-ALL·무회사는 deny_all=True 이며, 라우터는
    이때 쿼리를 실행하지 말고 빈 결과를 반환해야 한다(company_id=None 을 그대로
    필터로 넘기면 run_list_query 등이 None 을 skip 해 전사 노출됨).
    ALL 은 클라 company_id 유지(None = 전체).
    """
    if _is_admin(_scope(supabase, current.get("role_code"))):
        return company_id, False
    cid = current.get("company_id")
    if not cid:
        return None, True
    return cid, False
