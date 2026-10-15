"""WO-E2E2000-C10-PR626-627-FINAL-TEST-GATE-001 — SEC01-SEC18 (API 전용).

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
  SEC13  GET /admin/detail/{id} — admin(001) 정상 조회 → 200
  SEC14  PATCH /admin/{id}       — admin(001) 상태 변경 → 200
  SEC15  DELETE /admin/{id}      — admin(001) 삭제 → 200
  SEC16  PATCH /admin/{id}       — non-admin → 403 AND get_supabase 미호출 (DB 변경 전 차단)
  SEC17  DELETE /admin/{id}      — non-admin → 403 AND get_supabase 미호출 (DB 변경 전 차단)
  SEC18  인증 없음 detail/patch/delete → 401 (엔드포인트별 무인증 차단 전수)
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


# ═══════════════════════════════════════════════════════════════════════
# SEC13-SEC15: 관리자(001) 정상 경로 — detail/patch/delete
# ═══════════════════════════════════════════════════════════════════════

class _RowResult:
    def __init__(self, rows: list):
        self.data = rows
        self.count = len(rows)


class _RowQ:
    """반환값을 테이블별로 주입받는 fake query."""
    def __init__(self, rows: list):
        self._rows = rows

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
    def execute(self): return _RowResult(self._rows)


class _MultiTableSB:
    """테이블 이름별로 다른 반환 행을 지원하는 fake SB."""
    def __init__(self, tables: dict):
        self._tables = tables

    def table(self, name: str) -> _RowQ:
        return _RowQ(self._tables.get(name, []))


def _make_app_rows(role_code: str, monkeypatch, tables: dict):
    """테이블별 반환값을 지정할 수 있는 TestClient 팩토리."""
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    sb = _MultiTableSB(tables)
    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", lambda: sb)

    app = FastAPI()
    app.include_router(router)

    if role_code == "__NO_AUTH__":
        def _raise_401():
            raise HTTPException(status_code=401, detail="토큰이 없습니다.")
        app.dependency_overrides[get_current_user] = _raise_401
    else:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": "admin-user",
            "role_code": role_code,
        }

    return TestClient(app, raise_server_exceptions=False), app


_FAKE_ROW = {"id": "rec-001", "auth_log_id": None, "status": "ACTIVE", "public_token": "tok"}


def test_SEC13_detail_admin_001_returns_200(monkeypatch):
    """admin(001) 상세 조회 — DB 행 존재 시 200."""
    client, app = _make_app_rows("001", monkeypatch, {
        "anonymous_diagnosis_results": [_FAKE_ROW],
        "diagnosis_auth_log": [],
    })
    resp = client.get("/anonymous-diagnosis/admin/detail/rec-001", headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("status") == "success"
    assert body["data"]["id"] == "rec-001"
    app.dependency_overrides.clear()


def test_SEC14_patch_admin_001_returns_200(monkeypatch):
    """admin(001) 상태 변경 — DB 행 존재 시 200."""
    patched_row = {"id": "rec-001", "status": "EXPIRED"}
    client, app = _make_app_rows("001", monkeypatch, {
        "anonymous_diagnosis_results": [patched_row],
    })
    resp = client.patch(
        "/anonymous-diagnosis/admin/rec-001",
        json={"status": "EXPIRED"},
        headers={"Authorization": "Bearer valid"},
    )
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("status") == "success"
    assert body["data"]["status"] == "EXPIRED"
    app.dependency_overrides.clear()


def test_SEC15_delete_admin_001_returns_200(monkeypatch):
    """admin(001) 삭제 — DB 행 존재 시 200."""
    client, app = _make_app_rows("001", monkeypatch, {
        "anonymous_diagnosis_results": [_FAKE_ROW],
    })
    resp = client.delete("/anonymous-diagnosis/admin/rec-001", headers={"Authorization": "Bearer valid"})
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    assert resp.json().get("status") == "success"
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# SEC16-SEC17: non-admin → 403 AND get_supabase 미호출 (DB 변경 전 차단)
# ═══════════════════════════════════════════════════════════════════════

def test_SEC16_nonadmin_patch_403_before_db(monkeypatch):
    """non-admin PATCH → 403이 DB 변경보다 먼저 발생."""
    call_log: list = []

    def _tracking_sb():
        call_log.append("get_supabase")
        return _FakeSB()

    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", _tracking_sb)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u", "role_code": "099"}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.patch(
        "/anonymous-diagnosis/admin/rec-001",
        json={"status": "EXPIRED"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    assert "get_supabase" not in call_log, (
        "non-admin PATCH에서 get_supabase가 호출됨 — role 검사 전에 DB 접근 발생"
    )
    app.dependency_overrides.clear()


def test_SEC17_nonadmin_delete_403_before_db(monkeypatch):
    """non-admin DELETE → 403이 DB 변경보다 먼저 발생."""
    call_log: list = []

    def _tracking_sb():
        call_log.append("get_supabase")
        return _FakeSB()

    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", _tracking_sb)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u", "role_code": "099"}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.delete("/anonymous-diagnosis/admin/rec-001", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"
    assert "get_supabase" not in call_log, (
        "non-admin DELETE에서 get_supabase가 호출됨 — role 검사 전에 DB 접근 발생"
    )
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# SEC18: 무인증 detail/patch/delete → 401 전수
# ═══════════════════════════════════════════════════════════════════════

def test_SEC18_unauthenticated_admin_endpoints_401(monkeypatch):
    """무인증 요청은 모든 관리자 엔드포인트(list 제외)에서 401."""
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", lambda: _FakeSB())

    app = FastAPI()
    app.include_router(router)

    def _raise_401():
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    app.dependency_overrides[get_current_user] = _raise_401
    client = TestClient(app, raise_server_exceptions=False)

    cases = [
        ("GET",    "/anonymous-diagnosis/admin/detail/x"),
        ("PATCH",  "/anonymous-diagnosis/admin/x"),
        ("DELETE", "/anonymous-diagnosis/admin/x"),
    ]
    for method, path in cases:
        if method == "GET":
            resp = client.get(path)
        elif method == "PATCH":
            resp = client.patch(path, json={"status": "EXPIRED"})
        else:
            resp = client.delete(path)
        assert resp.status_code == 401, (
            f"{method} {path}: 기대 401, 실제 {resp.status_code}"
        )
    app.dependency_overrides.clear()
