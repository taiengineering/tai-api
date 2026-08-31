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
from services.time import business_today, now_kst, serialize_external_utc

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
    ("GET", "/alert-messages/codes"),
    ("POST", "/overdue/check"),
    ("POST", "/anonymous-diagnosis/admin/expire-stale"),
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

# 근로자 앱(PWA) prefix — 인증은 유지, role_menu 게이트만 제외.
# /tbm 은 exact-or-child (/tbm-templates 와 구분). /worker 는 /worker-check·/worker-registry 와 구분.
# inspection-sets 확장 시 worker read(/inspection-sets/{id}/items)는 이 목록 또는 menu_code NULL.
_WORKER_PREFIXES = (
    "/work-assignments",
    "/worker-check",
    "/worker-attendance",
    "/attendance",
    "/work-permits",
    "/qr",
    "/tbm",
    "/worker",
    "/workers",
    "/uploads/inspection-photo",
    "/education/worker-complete",
    "/notifications",
    "/safety-reports",
    "/emergency",
)
_WORKER_GET_ONE = ("/risk-assessments", "/education")

_route_templates: list[Tuple[Set[str], str, re.Pattern]] = []
_perm_map: Dict[Tuple[str, str], str] = {}
_menu_map: Dict[Tuple[str, str], Optional[str]] = {}
_perm_res: list[Tuple[str, str, re.Pattern, str, Optional[str]]] = []
_role_perms: Dict[str, Set[str]] = {}
_role_menu: Dict[Tuple[str, str], dict] = {}
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


def _iter_http_routes(routes) -> list:
    found = []
    for r in routes or []:
        nested = getattr(r, "routes", None)
        if nested:
            found.extend(_iter_http_routes(nested))
            continue
        path = getattr(r, "path_format", None) or getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path and methods:
            found.append((path, methods))
    return found


def bind_app(app) -> None:
    """app.routes 인트로스펙션 — 요청 path → 템플릿 매칭용."""
    global _route_templates
    compiled = []
    seen = set()
    router = getattr(app, "router", app)
    raw_routes = getattr(router, "routes", None)
    n_raw = len(raw_routes) if raw_routes is not None else -1
    src = _iter_http_routes(raw_routes or [])
    paths_seen = {normalize_path(p) for p, _ in src}
    if "/companies" not in paths_seen:
        try:
            from fastapi.openapi.utils import get_openapi
            spec = get_openapi(
                title=getattr(app, "title", "TAI"),
                version=getattr(app, "version", "0"),
                routes=list(getattr(app, "routes", []) or []),
            )
            extra = []
            for p, item in (spec.get("paths") or {}).items():
                methods = {
                    m.upper()
                    for m in item.keys()
                    if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE")
                }
                if methods:
                    extra.append((p, methods))
            if extra:
                src = extra
        except Exception:
            log.exception("[GUARD] openapi fallback 실패")
    for path, methods in src:
        npath = normalize_path(path)
        key = (frozenset(m.upper() for m in methods if m.upper() not in ("HEAD", "OPTIONS")), npath)
        if not key[0] or key in seen:
            continue
        seen.add(key)
        compiled.append((set(key[0]), npath, _compile_template(npath)))
    compiled.sort(key=lambda x: (x[1].count("{"), -len(x[1])))
    _route_templates = compiled
    _refresh_maps(force=True)
    log.warning(
        "[GUARD] bind raw_routes=%d src=%d templates=%d perm_maps=%d menu_maps=%d",
        n_raw, len(src), len(_route_templates), len(_perm_map),
        sum(1 for v in _menu_map.values() if v),
    )
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
    global _perm_map, _menu_map, _perm_res, _role_perms, _role_menu, _cache_at
    now = time.time()
    if not force and now - _cache_at < _CACHE_TTL and _perm_map:
        return
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        ap = sb.table("api_permissions").select(
            "http_method, api_path, permission_code, menu_code"
        ).limit(2000).execute()
        pmap: Dict[Tuple[str, str], str] = {}
        mmap: Dict[Tuple[str, str], Optional[str]] = {}
        for row in ap.data or []:
            method = (row.get("http_method") or "").upper()
            path = normalize_path(row.get("api_path") or "")
            code = row.get("permission_code")
            menu = row.get("menu_code") or None
            if method and path and code:
                pmap[(method, path)] = code
                mmap[(method, path)] = menu
        compiled = [
            (method, path, _compile_template(path), code, mmap.get((method, path)))
            for (method, path), code in pmap.items()
        ]
        compiled.sort(key=lambda x: (x[1].count("{"), -len(x[1])))
        rp = sb.table("role_permissions").select("role_code, permission_code").limit(5000).execute()
        rmap: Dict[str, Set[str]] = {}
        for row in rp.data or []:
            rmap.setdefault(row.get("role_code") or "", set()).add(row.get("permission_code") or "")
        rm = sb.table("role_menu_permissions").select(
            "role_code, menu_code, can_list, can_create, can_update, can_delete"
        ).limit(5000).execute()
        rmenu: Dict[Tuple[str, str], dict] = {}
        for row in rm.data or []:
            role = row.get("role_code") or ""
            menu = row.get("menu_code") or ""
            if role and menu:
                rmenu[(role, menu)] = {
                    "can_list": bool(row.get("can_list")),
                    "can_create": bool(row.get("can_create")),
                    "can_update": bool(row.get("can_update")),
                    "can_delete": bool(row.get("can_delete")),
                }
        _perm_map, _menu_map, _perm_res = pmap, mmap, compiled
        _role_perms, _role_menu, _cache_at = rmap, rmenu, now
    except Exception:
        log.exception("[GUARD] permission cache refresh 실패 — 기존 캐시 유지")


def template_for(method: str, raw_path: str) -> str:
    """요청 URL 을 app.routes 또는 api_permissions 템플릿으로 정규화."""
    m = method.upper()
    p = normalize_path(raw_path)
    for methods, tmpl, cre in _route_templates:
        if m in methods and cre.match(p):
            return tmpl
    for em, tmpl, cre, _code, _menu in _perm_res:
        if em == m and cre.match(p):
            return tmpl
    return p


def lookup_permission(method: str, path_template: str) -> Optional[str]:
    _refresh_maps()
    m = method.upper()
    p = normalize_path(path_template)
    hit = _perm_map.get((m, p))
    if hit:
        return hit
    for em, _tmpl, cre, code, _menu in _perm_res:
        if em == m and cre.match(p):
            return code
    return None


def lookup_menu(method: str, path_template: str) -> Optional[str]:
    _refresh_maps()
    m = method.upper()
    p = normalize_path(path_template)
    if (m, p) in _menu_map:
        return _menu_map.get((m, p))
    for em, _tmpl, cre, _code, menu in _perm_res:
        if em == m and cre.match(p):
            return menu
    return None


def _crud_flag(method: str) -> str:
    m = method.upper()
    if m == "POST":
        return "can_create"
    if m in ("PUT", "PATCH"):
        return "can_update"
    if m == "DELETE":
        return "can_delete"
    return "can_list"


def has_menu_permission(role_code: Optional[str], menu_code: Optional[str], crud_col: str) -> bool:
    if not role_code or not menu_code or crud_col not in (
        "can_list", "can_create", "can_update", "can_delete",
    ):
        return False
    _refresh_maps()
    row = _role_menu.get((role_code, menu_code))
    if not row:
        return False
    return bool(row.get(crud_col))


def _path_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _is_worker_route(method: str, path: str) -> bool:
    """근로자 앱 route — 인증만 요구, role_menu 게이트 제외."""
    p = normalize_path(path)
    m = method.upper()
    for prefix in _WORKER_PREFIXES:
        if _path_under(p, prefix):
            return True
    if m == "GET":
        for base in _WORKER_GET_ONE:
            rest = p[len(base):] if p.startswith(base) else None
            # /risk-assessments/{id} 또는 실측 UUID 한 단 — 컬렉션·하위 path 제외
            if rest and rest.startswith("/") and rest.count("/") == 1 and rest[1:]:
                return True
    # 위험성평가 참여(작업자). GET {id} 와 별도.
    if _path_under(p, "/risk-assessments") and (
        p.endswith("/participate") or p.endswith("/participants")
    ):
        return True
    return False


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
        today = business_today().isoformat()
        now = serialize_external_utc(now_kst())
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


def _evaluate(request: Request) -> Optional[Response]:
    """가드 판정만. 거부 시 Response, 통과 시 None. call_next 호출하지 않는다."""
    method = request.method.upper()
    raw = request.url.path
    if is_public(method, raw):
        return None
    path = template_for(method, raw)
    perm = lookup_permission(method, path)
    resource = _resource_of(path)
    if perm and perm.startswith("PLATFORM_"):
        resource = "platform"
    user = _resolve_user(request)
    if user is None:
        return _deny(_is_advisory("auth", resource), 401,
                     "토큰이 없습니다.", f"{method} {path}")
    if method in WRITE_METHODS and resource != "platform":
        if not active_entitlement(user.get("company_id")):
            d = _deny(_is_advisory("entitlement", resource), 403,
                      "구독이 만료되어 조회만 가능합니다.",
                      f"company={user.get('company_id')} {method} {path}")
            if d is not None:
                return d
    # 근로자 앱: 인증·entitlement 이후 menu 게이트만 생략
    if _is_worker_route(method, path):
        return None
    menu = lookup_menu(method, path)
    user_role = user.get("role_code")
    if perm and perm.startswith("PLATFORM_"):
        if not has_permission(user_role, perm):
            return _deny(_is_advisory("action", "platform"), 403,
                         "권한이 없습니다.",
                         f"role={user_role} perm={perm} {method} {path}")
    elif menu:
        crud = _crud_flag(method)
        if not has_menu_permission(user_role, menu, crud):
            return _deny(_is_advisory("action", resource), 403,
                         "권한이 없습니다.",
                         f"role={user_role} menu={menu} {crud}")
    return None


async def permission_guard_middleware(request: Request, call_next):
    try:
        decision = _evaluate(request)
    except Exception:
        log.exception("[GUARD] 예외 — fail-open %s %s", request.method, request.url.path)
        decision = None
    return decision if decision is not None else await call_next(request)


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
