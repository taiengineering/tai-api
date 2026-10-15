"""WO-E2E2000-C10-SECURITY-CONTAINMENT-PATCH-001 — SEC01-SEC12.

S2 관리자 권한 강화:
  SEC01  list_anonymous_diagnoses — role_code != "001" 검사 구문 존재 (AST)
  SEC02  admin_get_anonymous_diagnosis_detail — role_code != "001" 검사 (AST)
  SEC03  admin_patch_anonymous_diagnosis — role_code != "001" 검사 (AST)
  SEC04  delete_anonymous_diagnosis — role_code != "001" 검사 (AST)
  SEC05  expire_stale_records — role_code 검사 없음 (크론 의존 — 변경 금지)
  SEC06  GET /admin/list   — non-admin → 403 (HTTP)
  SEC07  GET /admin/detail/{id} — non-admin → 403 (HTTP)
  SEC08  PATCH /admin/{id} — non-admin → 403 (HTTP)
  SEC09  DELETE /admin/{id} — non-admin → 403 (HTTP)
  SEC10  GET /admin/list   — admin(001) → role check 통과 후 DB 분기 진입 (HTTP)

S1 마이그레이션 계약:
  SEC11  마이그레이션 파일 존재 + DROP POLICY 구문 포함
  SEC12  마이그레이션 파일에 anon USING (true) 구문 없음 (USING true 기존 정책 재도입 금지)
"""
from __future__ import annotations

import ast
import pathlib
import re

# ── 대상 파일 경로 ────────────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ADMIN_SRC = (_ROOT / "routers" / "anonymous_diagnosis_admin.py").read_text(encoding="utf-8")
_TREE = ast.parse(_ADMIN_SRC)
_MIGRATION = _ROOT / "supabase" / "migrations" / "20261016000001_c10_rls_hardening.sql"


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
        # Compare: current_user.get("role_code") != "001"
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        ops = [type(op).__name__ for op in test.ops]
        if "NotEq" not in ops:
            continue
        comparators = [_const_value(c) for c in test.comparators]
        if "001" not in comparators:
            continue
        # 분기 바디에 HTTPException(status_code=403) 호출 존재
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
# SEC06-SEC10: HTTP 계약 (TestClient, DB 목업)
# ═══════════════════════════════════════════════════════════════════════

def _build_app(role_code: str, mock_db_return=None):
    """TestClient 전용 미니 앱. DB 호출은 dummy로 대체."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user
    from db.supabase_client import get_supabase

    class _FakeResult:
        def __init__(self, data, count=0):
            self.data = data
            self.count = count

    class _FakeQ:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *a, **kw):
            return self

        def eq(self, *a, **kw):
            return self

        def ilike(self, *a, **kw):
            return self

        def order(self, *a, **kw):
            return self

        def range(self, *a, **kw):
            return self

        def limit(self, *a, **kw):
            return self

        def update(self, *a, **kw):
            return self

        def delete(self, *a, **kw):
            return self

        def execute(self):
            rows = self._rows if self._rows is not None else []
            return _FakeResult(data=rows, count=len(rows))

        def in_(self, *a, **kw):
            return self

    class _FakeSB:
        def table(self, name):
            return _FakeQ(mock_db_return if mock_db_return is not None else [])

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user",
        "role_code": role_code,
    }
    app.dependency_overrides[get_supabase] = lambda: _FakeSB()
    return TestClient(app, raise_server_exceptions=False)


def test_SEC06_list_non_admin_403():
    client = _build_app(role_code="099")
    resp = client.get(
        "/anonymous-diagnosis/admin/list",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"


def test_SEC07_detail_non_admin_403():
    client = _build_app(role_code="099")
    resp = client.get(
        "/anonymous-diagnosis/admin/detail/some-id",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"


def test_SEC08_patch_non_admin_403():
    client = _build_app(role_code="099")
    resp = client.patch(
        "/anonymous-diagnosis/admin/some-id",
        json={"status": "EXPIRED"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"


def test_SEC09_delete_non_admin_403():
    client = _build_app(role_code="099")
    resp = client.delete(
        "/anonymous-diagnosis/admin/some-id",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 403, f"기대 403, 실제 {resp.status_code}"


def test_SEC10_list_admin_001_passes_role_check(monkeypatch):
    """role_code=001 사용자는 role 검사 통과 후 DB 단계 진입 — 200 반환."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.anonymous_diagnosis_admin import router
    from routers.auth import get_current_user

    class _FakeResult:
        data = []
        count = 0

    class _FakeQ:
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def ilike(self, *a, **kw): return self
        def order(self, *a, **kw): return self
        def range(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def in_(self, *a, **kw): return self
        def execute(self): return _FakeResult()

    class _FakeSB:
        def table(self, name): return _FakeQ()

    monkeypatch.setattr("routers.anonymous_diagnosis_admin.get_supabase", lambda: _FakeSB())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin", "role_code": "001"}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/anonymous-diagnosis/admin/list",
        headers={"Authorization": "Bearer valid"},
    )
    assert resp.status_code == 200, f"기대 200, 실제 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("status") == "success"
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════
# SEC11-SEC12: 마이그레이션 파일 계약
# ═══════════════════════════════════════════════════════════════════════

def test_SEC11_migration_file_exists_with_drop_policy():
    assert _MIGRATION.exists(), f"마이그레이션 파일 없음: {_MIGRATION}"
    sql = _MIGRATION.read_text(encoding="utf-8").upper()
    assert "DROP POLICY" in sql, "DROP POLICY 구문 없음 — 기존 과다 허용 정책 제거 보장 필요"


def test_SEC12_migration_no_anon_using_true():
    """마이그레이션에서 anon 롤에 USING (true) 정책을 재생성하지 않는다."""
    sql = _MIGRATION.read_text(encoding="utf-8")
    # "TO anon" + "USING (true)" 또는 "USING(true)" 가 같은 CREATE POLICY 블록에 없어야 함
    # 검사: USING (true)/USING(true) 앞에 TO anon 이 있는 CREATE POLICY 블록 탐지
    blocks = re.split(r"(?i)CREATE\s+POLICY", sql)
    for block in blocks[1:]:  # 첫 요소는 파일 선두
        has_anon = bool(re.search(r"\bTO\s+anon\b", block, re.IGNORECASE))
        has_using_true = bool(re.search(r"USING\s*\(\s*true\s*\)", block, re.IGNORECASE))
        assert not (has_anon and has_using_true), (
            f"마이그레이션에 anon USING(true) 정책 재생성 발견: ...{block[:200]}..."
        )
