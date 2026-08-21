"""헤더가드 Layer0 entitlement + Layer1 action.

ADVISORY(기본): 로그-only, fail-open. PERMISSION_GUARD_MODE=ENFORCE 이고
PERMISSION_GUARD_ENFORCE 에 자원이 있을 때만 실제 403/401.
Layer2 데이터 스코프(company_scope)는 여기 두지 않는다.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timezone
from typing import Dict, Optional, Set, Tuple

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("permission_guard")

_MODE = os.getenv("PERMISSION_GUARD_MODE", "ADVISORY").strip().upper() or "ADVISORY"
_ENFORCE_RES = {
    s.strip().lower()
    for s in os.getenv("PERMISSION_GUARD_ENFORCE", "").split(",")
    if s.strip()
}

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# (method or *, path). path 가 / 로 끝나면 prefix, 아니면 exact.
# OPTIONS 전부 통과(CORS). /auth 로그인·OTP만 — /auth/me 는 비공개.
_PUBLIC: Tuple[Tuple[str, str], ...] = (
    ("GET", "/health"),
    ("GET", "/"),
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/send-otp"),
    ("POST", "/auth/verify-otp"),
    ("POST", "/auth/check-phone"),
    ("POST", "/auth/reset-password"),
    ("POST", "/auth/send-verify-email"),
    ("POST", "/auth/verify-email"),
    ("GET", "/auth/test"),
    ("POST", "/auth/inicis/"),
    ("GET", "/auth/inicis/"),
    ("GET", "/diagnosis/auth/"),
    ("POST", "/diagnosis/auth/"),
    ("POST", "/diagnosis/run"),
    ("POST", "/diagnosis/run-leg"),
    ("GET", "/diagnosis/price-tier"),
    ("GET", "/diagnosis/pricing"),
    ("GET", "/diagnosis/fields"),
    ("GET", "/diagnosis/equipment-options"),
    ("GET", "/diagnosis/process-options"),
    ("GET", "/diagnosis/mvp-exists-fields"),
    ("GET", "/diagnosis/autofill/"),
    ("POST", "/diagnosis/disclaimer"),
    ("GET", "/diagnosis/result/"),
    ("GET", "/diagnosis/paid-result/"),
    ("GET", "/diagnosis/report-pdf/"),
    ("GET", "/diagnosis/proposal-pdf/"),
    ("GET", "/diagnosis/factory-test-verify/"),
    ("POST", "/payments/inicis/noti"),
    ("POST", "/payments/inicis/return"),
    ("POST", "/payments/inicis/billing/return"),
    ("POST", "/mail/webhook/"),
    ("GET", "/public/"),
    ("POST", "/public/"),
    ("GET", "/helpcenter/"),
    ("POST", "/helpcenter/feedback"),
    ("GET", "/help/search"),
    ("GET", "/help/doc/"),
    ("GET", "/faqs"),
    ("POST", "/contacts"),
)

_RESOURCE_PREFIX = {
    "companies": "companies",
    "factories": "factories",
    "users": "users",
    "equipment-assets": "equipment",
    "engine-equipment": "equipment",
    "inspection": "inspections",
    "inspection-sets": "inspections",
    "inspection-schedule": "inspections",
    "inspection-checklist": "inspections",
    "work-schedules": "work",
    "work-assignments": "work",
    "defects": "defects",
}

_PARAM_RE = re.compile(r"\{[^/]+\}")

_route_templates: list[Tuple[Set[str], str, re.Pattern]] = []
_perm_map: Dict[Tuple[str, str], str] = {}
_role_perms: Dict[str, Set[str]] = {}
_cache_at = 0.0
_CACHE_TTL = 60.0


def normalize_path(path: str) -> str:
    """가드·api_permissions 공통 정규화: /api 접두 제거, trailing slash 제거."""
    if not path:
        return "/"
    p = path.split("?", 1)[0].strip() or "/"
    if p.startswith("/api/"):
        p = p[4:]
    elif p == "/api":
        p = "/"
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


def _is_advisory(kind: str, resource: Optional[str]) -> bool:
    """kind: 'auth' | 'entitlement' | 'action'."""
    if _MODE != "ENFORCE" or not _ENFORCE_RES:
        return True
    if kind == "entitlement":
        return not ("entitlement" in _ENFORCE_RES or (resource and resource in _ENFORCE_RES))
    if kind == "action":
        return not (resource and resource in _ENFORCE_RES)
    return not (resource and resource in _ENFORCE_RES)


def _resource_of(path: str) -> str:
    seg = path.strip("/").split("/", 1)[0] if path.strip("/") else ""
    return _RESOURCE_PREFIX.get(seg, seg)


def is_public(method: str, path: str) -> bool:
    m = method.upper()
    if m == "OPTIONS":
        return True
    p = normalize_path(path)
    for em, ep in _PUBLIC:
        if em not in ("*", m):
            continue
        if ep == "/":
            if p == "/":
                return True
            continue
        if ep.endswith("/"):
            if p == ep.rstrip("/") or p.startswith(ep):
                return True
        elif p == ep:
            return True
    return False


def _compile_template(tmpl: str) -> re.Pattern:
    parts = _PARAM_RE.split(tmpl)
    escaped = [re.escape(x) for x in parts]
    body = "[^/]+".join(escaped)
    return re.compile("^" + body + "$")


def bind_app(app) -> None:
    """app.routes 인트로스펙션 — 요청 path → 템플릿 매칭용."""
    global _route_templates
    compiled = []
    seen = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        npath = normalize_path(path)
        key = (frozenset(m.upper() for m in methods if m.upper() != "HEAD"), npath)
        if key in seen:
            continue
        seen.add(key)
        compiled.append((set(key[0]), npath, _compile_template(npath)))
    compiled.sort(key=lambda x: (x[1].count("{"), -len(x[1])))
    _route_templates = compiled
    _refresh_maps(force=True)
    _log_t4_coverage()


def _log_t4_coverage() -> None:
    route_keys = {(m, p) for methods, p, _ in _route_templates for m in methods}
    stale = []
    for (method, path), code in _perm_map.items():
        if (method, path) not in route_keys:
            stale.append(f"{method} {path} ({code})")
    if stale:
        log.warning("[GUARD-T4] api_permissions 미매칭 %d건: %s", len(stale), "; ".join(stale[:20]))
    else:
        log.info("[GUARD-T4] api_permissions %d건 모두 app.routes 와 매칭", len(_perm_map))


def _refresh_maps(force: bool = False) -> None:
    global _perm_map, _role_perms, _cache_at
    now = time.time()
    if not force and now - _cache_at < _CACHE_TTL and _perm_map:
        return
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        ap = sb.table("api_permissions").select(
            "http_method, api_path, permission_code"
        ).limit(2000).execute()
        pmap: Dict[Tuple[str, str], str] = {}
        for row in ap.data or []:
            method = (row.get("http_method") or "").upper()
            path = normalize_path(row.get("api_path") or "")
            code = row.get("permission_code")
            if method and path and code:
                pmap[(method, path)] = code
        rp = sb.table("role_permissions").select("role_code, permission_code").limit(5000).execute()
        rmap: Dict[str, Set[str]] = {}
        for row in rp.data or []:
            rmap.setdefault(row.get("role_code") or "", set()).add(row.get("permission_code") or "")
        _perm_map, _role_perms, _cache_at = pmap, rmap, now
    except Exception:
        log.exception("[GUARD] permission cache refresh 실패 — 기존 캐시 유지")


def template_for(method: str, raw_path: str) -> str:
    """요청 URL 을 app.routes 템플릿으로 정규화. 실패 시 normalize(raw)."""
    m = method.upper()
    p = normalize_path(raw_path)
    for methods, tmpl, cre in _route_templates:
        if m in methods and cre.match(p):
            return tmpl
    return p


def lookup_permission(method: str, path_template: str) -> Optional[str]:
    _refresh_maps()
    return _perm_map.get((method.upper(), normalize_path(path_template)))


def has_permission(role_code: Optional[str], permission_code: str) -> bool:
    if not role_code or not permission_code:
        return False
    _refresh_maps()
    return permission_code in _role_perms.get(role_code, set())


def active_entitlement(company_id: Optional[str]) -> bool:
    if not company_id:
        return False
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        today = date.today().isoformat()
        now = datetime.now(timezone.utc).isoformat()
        sub = (
            sb.table("subscriptions")
            .select("id, ended_at")
            .eq("company_id", company_id)
            .eq("status", "ACTIVE")
            .ilike("product_type", "SAAS%")
            .limit(20)
            .execute()
        )
        for row in sub.data or []:
            ended = row.get("ended_at")
            if not ended or str(ended) > now:
                return True
        con = (
            sb.table("contracts")
            .select("id, end_date")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .ilike("service_type", "SAAS%")
            .limit(20)
            .execute()
        )
        for row in con.data or []:
            end = row.get("end_date")
            if not end or str(end)[:10] >= today:
                return True
    except Exception:
        log.exception("[GUARD] entitlement 조회 실패 — fail-open")
        return True
    return False


def _resolve_user(request: Request) -> Optional[dict]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    try:
        from routers.auth import get_current_user
        return get_current_user(authorization=auth)
    except HTTPException:
        return None
    except Exception:
        log.exception("[GUARD] 토큰 해석 실패")
        return None


def _deny(advisory: bool, code: int, msg: str, extra: str = "") -> Optional[Response]:
    if advisory:
        log.warning("[GUARD-ADVISORY] %s %s", msg, extra)
        return None
    return JSONResponse({"detail": msg}, status_code=code)


async def permission_guard_middleware(request: Request, call_next):
    method = request.method.upper()
    raw = request.url.path
    try:
        if is_public(method, raw):
            return await call_next(request)

        path = template_for(method, raw)
        resource = _resource_of(path)
        user = _resolve_user(request)

        if user is None:
            denied = _deny(_is_advisory("auth", resource), 401, "토큰이 없습니다.", f"{method} {path}")
            if denied is not None:
                return denied
            return await call_next(request)

        if method in WRITE_METHODS:
            cached = getattr(request.state, "_guard_entitlement", None)
            if cached is None:
                ok = active_entitlement(user.get("company_id"))
                request.state._guard_entitlement = ok
            else:
                ok = cached
            if not ok:
                denied = _deny(
                    _is_advisory("entitlement", resource),
                    403,
                    "구독이 만료되어 조회만 가능합니다.",
                    f"company={user.get('company_id')} {method} {path}",
                )
                if denied is not None:
                    return denied
                return await call_next(request)

        perm = lookup_permission(method, path)
        if perm and not has_permission(user.get("role_code"), perm):
            denied = _deny(
                _is_advisory("action", resource),
                403,
                "권한이 없습니다.",
                f"role={user.get('role_code')} perm={perm} {method} {path}",
            )
            if denied is not None:
                return denied
    except HTTPException:
        raise
    except Exception:
        log.exception("[GUARD] 예외 — fail-open %s %s", method, raw)
    return await call_next(request)


def mount_permission_guard(app) -> None:
    try:
        bind_app(app)
    except Exception:
        log.exception("[GUARD] bind 실패 — 미들웨어는 마운트 (fail-open)")
    app.middleware("http")(permission_guard_middleware)
    log.info(
        "[GUARD] mounted mode=%s enforce=%s maps=%d routes=%d",
        _MODE,
        ",".join(sorted(_ENFORCE_RES)) or "(none)",
        len(_perm_map),
        len(_route_templates),
    )
