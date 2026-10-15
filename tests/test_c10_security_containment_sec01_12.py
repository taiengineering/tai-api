"""WO-E2E2000-C10-PR626-SECURITY-GATE-CORRECTION-001 — SEC01-SEC12 (API 전용).

PR #626 범위: routers/anonymous_diagnosis_admin.py S2 RBAC 강화만 포함.
DB 마이그레이션(S1) 테스트는 별도 DB PR에 위치.

  SEC01  list_anonymous_diagnoses — role_code != "001" 검사 구문 존재 (AST)
  SEC02  admin_get_anonymous_diagnosis_detail — role_code != "001" 검사 (AST)
  SEC03  admin_patch_anonymous_diagnosis — role_code != "001" 검사 (AST)
  SEC04  delete_anonymous_diagnosis — role_code != "001" 검사 (AST)
  SEC05  expire_stale_records — role_code 검사 없음 (크론 의존 — 변경 금지)
  SEC06  GET /admin/list   — non-admin(099) → 403
  SEC07  GET /admin/detail/{id} — non-admin(099) → 403
  SEC08  PATCH /admin/{id} — non-admin(099) → 403
  SEC09  DELETE /admin/{id} — non-admin(099) → 403
  SEC10  GET /admin/list   — admin(001) → role check 통과 후 200
  SEC11  GET /admin/list   — 인증 없음 → 401 (토큰 없는 요청 차단)
  SEC12  POST /admin/expire-stale — 인증 없음에도 200 (크론 계약 불변)
"""
from __future__ import annotations

import ast
import pathlib

# ── 대상 파일 경로 ────────────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ADMIN_SRC = (_ROOT / "routers" / "anonymous_diagnosis_admin.py").read_text(encoding="utf-8")
_TREE = ast.parse(_ADMIN_SRC)


# ── AST 유틸 ─────────────────────────────────────────────────────────

def _fn(name: str) -> ast.FunctionDef:
    return next(
        n for n in ast.walk(_TREE)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _const_value(node: ast.expr):
    """ast.Constant 값 추출 (Python 3.8+ .value, deprecated .s 미사용)."""
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _has_role_001_check(fn_name: str) -> bool:
    """함수 내 role_code != "001" HTTPException(403) 분기 존재 여부."""
    fn = _fn(fn_name)
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        ops = [type(op).__name__ for op in test.ops]
        if "NotEq" not in ops:
            continue
        comparators = [_const_value(c) for c in test.comparators]
        if "001" not in comparators:
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Raise):
                exc = stmt.exc
                if exc is None:
                    continue
                call = exc if isinstance(exc, ast.Call) else None
                if call is None:
                    continue
                fn_id = getattr(call.func, "id", None)
                if "HTTPException" not in (fn_id or ""):
                    continue
                for kw in call.keywords:
                    if kw.arg == "status_code" and _const_value(kw.value) == 403:
                        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# SEC01-SEC05: AST 정적 검사
# ═══════════════════════════════════════════════════════════════════════

def test_SEC01_list_has_role_001_check():
    assert _has_role_001_check("list_anonymous_diagnoses"), (
        "list_anonymous_diagnoses: role_code != '001' → 403 분기 없음"
    )


def test_SEC02_detail_has_role_001_check():
    assert _has_role_001_check("admin_get_anonymous_diagnosis_detail"), (
        "admin_get_anonymous_diagnosis_detail: role_code != '001' → 403 분기 없음"
    )


def test_SEC03_patch_has_role_001_check():
    assert _has_role_001_check("admin_patch_anonymous_diagnosis"), (
        "admin_patch_anonymous_diagnosis: role_code != '001' → 403 분기 없음"
    )


def test_SEC04_delete_has_role_001_check():
    assert _has_role_001_check("delete_anonymous_diagnosis"), (
        "delete_anonymous_diagnosis: role_code != '001' → 403 분기 없음"
    )


def test_SEC05_expire_stale_no_role_check():
    """expire_stale_records는 크론 의존 — role_code 검사 없어야 한다."""
    assert not _has_role_001_check("expire_stale_records"), (
        "expire_stale_records에 role_code 검사가 추가됨 — 크론 파이프라인 파괴 위험"
    )


# ═══════════════════════════════════════════════════════════════════════
# SEC06-SEC10: HTTP 계약 (TestClient + monkeypatch)
# ═══════════════════════════════════════════════════════════════════════

class _FakeResult:
    data: list = []
    count: int = 0


class _FakeQ:
    def select(self, *a, **kw): return self
    def eq(self, *a, **kw): return self
    def neq(self, *a, **kw): return self
    def lt(self, *a, **kw): return self
    def lte(self, *a, **kw): return self
    def gt(self, *a, **kw): return self
    def gte(self, *a, **kw): return self
    def ilike(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def range(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def in_(self, *a, **kw): return self
    def update(self, *a, **kw): return self
    def delete(self, *a, **kw): return self
    def execute(self): return _FakeResult()


class _FakeSB:
    def table(self, name): return _FakeQ()


def _make_app(role_code: str, monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", lambda: _FakeSB())

    app = FastAPI()
    app.include_router(router)

    if role_code == "__NO_AUTH__":
        def _raise_401():
            raise HTTPException(status_code=401, detail="토큰이 없습니다.")
        app.dependency_overrides[get_current_user] = _raise_401
    else:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": "test-user",
            "role_code": role_code,
        }

    return TestClient(app, raise_server_exceptions=False), app


def test_SEC06_list_non_admin_403(monkeypatch):
    client, app = _make_app("099", monkeypatch)
    resp = client.get("/anonymous-diagnosis/admin/list", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    app.dependency_overrides.clear()


def test_SEC07_detail_non_admin_403(monkeypatch):
    client, app = _make_app("099", monkeypatch)
    resp = client.get("/anonymous-diagnosis/admin/detail/x", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    app.dependency_overrides.clear()


def test_SEC08_patch_non_admin_403(monkeypatch):
    client, app = _make_app("099", monkeypatch)
    resp = client.patch(
        "/anonymous-diagnosis/admin/x",
        json={"status": "EXPIRED"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    app.dependency_overrides.clear()


def test_SEC09_delete_non_admin_403(monkeypatch):
    client, app = _make_app("099", monkeypatch)
    resp = client.delete("/anonymous-diagnosis/admin/x", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    app.dependency_overrides.clear()


def test_SEC10_list_admin_001_passes_role_check(monkeypatch):
    """role_code=001 사용자는 role 검사 통과 후 DB 단계 진입 — 200 반환."""
    client, app = _make_app("001", monkeypatch)
    resp = client.get("/anonymous-diagnosis/admin/list", headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    assert resp.json().get("status") == "success"
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# SEC11-SEC12: 인증 경계 계약
# ═══════════════════════════════════════════════════════════════════════

def test_SEC11_list_no_token_401(monkeypatch):
    """인증 토큰 없는 요청은 401 — get_current_user 단계에서 거부."""
    client, app = _make_app("__NO_AUTH__", monkeypatch)
    resp = client.get("/anonymous-diagnosis/admin/list")
    assert resp.status_code == 401, f"기대 401, 실제 {resp.status_code}"
    app.dependency_overrides.clear()


def test_SEC12_expire_stale_no_auth_200(monkeypatch):
    """expire-stale은 인증 없이 200 반환 — 크론 의존 계약 불변.

    이 테스트가 실패하면 크론 파이프라인이 파괴된다.
    """
    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", lambda: _FakeSB())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/anonymous-diagnosis/admin/expire-stale")
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("status") == "success"
