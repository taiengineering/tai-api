"""SEC-03 D3-B P0 — 가격 API 인증·인가 소스 계약 테스트
WO-TAI-SEC03-D3B-P0-PRICE-AUTH-CORRECT-001 (R1 포함)

검증 방식: 정적 AST 분석 (소스 파일 기반, 라이브 DB 불필요)

테스트 목록:
  PAC-01  admin_pricing — db.supabase_client 사용
  PAC-02  admin_pricing — GET /pricing/keys: _require_admin 호출 존재
  PAC-03  admin_pricing — PATCH /pricing: _require_admin 호출 존재
  PAC-04  admin_pricing — _require_admin 위치: patch_pricing 내 DB 작업 이전
  PAC-05  price_setting — 쓰기 엔드포인트 6개: Depends(get_current_user) 존재
  PAC-06  price_setting — 쓰기 엔드포인트 6개: _require_admin 호출 존재
  PAC-07  price_master_admin — 전체 엔드포인트 6개: Depends(get_current_user) 존재
  PAC-08  price_master_admin — 전체 엔드포인트 6개: _require_admin 호출 존재
  PAC-09  diagnosis_fields — db.supabase_client 사용 (anon 키 제거)
  PAC-10  diagnosis_fields — 쓰기 경로 없음 (INSERT/UPDATE/DELETE 미사용)
  PAC-11  price_setting — 읽기 엔드포인트 7개: Depends(get_current_user) 존재 (R1)
  PAC-12  price_setting — 읽기 엔드포인트 7개: _require_admin 호출 존재 (R1)
  PAC-NC1 NC: admin_pricing — db.database 사용 시 FAIL
  PAC-NC2 NC: price_setting — 쓰기 엔드포인트 auth 없음 시 FAIL
  PAC-NC3 NC: _require_admin 주석 처리 시 FAIL
  PAC-NC4 NC: price_setting — 읽기 엔드포인트 auth 없음 시 FAIL (R1)
"""
from __future__ import annotations

import ast
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_ADMIN_PRICING   = _ROOT / "routers" / "admin_pricing.py"
_PRICE_SETTING   = _ROOT / "routers" / "price_setting.py"
_PRICE_MASTER    = _ROOT / "routers" / "price_master_admin.py"
_DIAG_FIELDS     = _ROOT / "routers" / "diagnosis_fields.py"

_PRICE_WRITE_ENDPOINTS = {
    "update_saas_plan",
    "create_saas_plan",
    "update_diagnosis_report",
    "update_repair_brokerage",
    "update_safety_management",
    "update_consulting",
}

_PRICE_READ_ENDPOINTS = {
    "list_saas_plans",
    "get_saas_plan",
    "list_diagnosis_reports",
    "list_change_logs",
    "list_repair_brokerage",
    "list_safety_management",
    "list_consulting",
}

_PRICE_MASTER_ENDPOINTS = {
    "list_prices",
    "get_price",
    "create_price",
    "update_price",
    "deactivate_price",
    "replace_features",
}


def _src(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(_src(path))


def _func_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _has_depends_get_current_user(func: ast.FunctionDef) -> bool:
    for arg_default in func.args.defaults:
        if (isinstance(arg_default, ast.Call)
                and isinstance(arg_default.func, ast.Name)
                and arg_default.func.id == "Depends"
                and arg_default.args
                and isinstance(arg_default.args[0], ast.Name)
                and arg_default.args[0].id == "get_current_user"):
            return True
    return False


def _require_admin_linenos(func: ast.FunctionDef) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_require_admin"
    ]


def _table_write_linenos(func: ast.FunctionDef) -> list[int]:
    """테이블 DML(.insert/.update/.delete) 첫 호출 라인 수집."""
    lines = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("insert", "update", "delete")):
            lines.append(node.lineno)
    return lines


# ── PAC-01 ~ PAC-04: admin_pricing ────────────────────────────────────

def test_pac_01_admin_pricing_uses_supabase_client():
    """PAC-01: admin_pricing.py가 db.supabase_client를 사용한다."""
    src = _src(_ADMIN_PRICING)
    assert "from db.supabase_client import get_supabase" in src, (
        "admin_pricing.py가 db.database(anon key)를 사용 중 — db.supabase_client로 교체 필요"
    )
    assert "from db.database import get_supabase" not in src, (
        "admin_pricing.py에 db.database import가 남아 있음"
    )


def test_pac_02_admin_pricing_list_keys_requires_admin():
    """PAC-02: GET /pricing/keys — _require_admin 호출 존재."""
    funcs = _func_nodes(_tree(_ADMIN_PRICING))
    f = funcs.get("list_pricing_keys")
    assert f is not None, "list_pricing_keys 함수 없음"
    assert _require_admin_linenos(f), "list_pricing_keys에 _require_admin() 호출 없음"


def test_pac_03_admin_pricing_patch_requires_admin():
    """PAC-03: PATCH /pricing — _require_admin 호출 존재."""
    funcs = _func_nodes(_tree(_ADMIN_PRICING))
    f = funcs.get("patch_pricing")
    assert f is not None, "patch_pricing 함수 없음"
    assert _require_admin_linenos(f), "patch_pricing에 _require_admin() 호출 없음"


def test_pac_04_admin_pricing_require_admin_before_write():
    """PAC-04: patch_pricing — _require_admin이 첫 DB 쓰기 이전 위치."""
    funcs = _func_nodes(_tree(_ADMIN_PRICING))
    f = funcs["patch_pricing"]
    admin_lines = _require_admin_linenos(f)
    write_lines = _table_write_linenos(f)
    assert admin_lines, "_require_admin() 호출 없음"
    assert write_lines, "DB 쓰기 호출 없음"
    assert min(admin_lines) < min(write_lines), (
        f"_require_admin(line {min(admin_lines)})이 DB 쓰기(line {min(write_lines)}) 이후에 위치"
    )


# ── PAC-05 ~ PAC-06: price_setting ────────────────────────────────────

def test_pac_05_price_setting_write_endpoints_have_auth():
    """PAC-05: price_setting.py 쓰기 엔드포인트 6개 — Depends(get_current_user) 존재. (write: PATCH/POST)"""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    missing = []
    for name in _PRICE_WRITE_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _has_depends_get_current_user(f):
            missing.append(name)
    assert not missing, f"Depends(get_current_user) 없는 쓰기 엔드포인트: {missing}"


def test_pac_06_price_setting_write_endpoints_have_require_admin():
    """PAC-06: price_setting.py 쓰기 엔드포인트 6개 — _require_admin() 호출 존재. (write: PATCH/POST)"""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    missing = []
    for name in _PRICE_WRITE_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _require_admin_linenos(f):
            missing.append(name)
    assert not missing, f"_require_admin() 없는 쓰기 엔드포인트: {missing}"


# ── PAC-07 ~ PAC-08: price_master_admin ───────────────────────────────

def test_pac_07_price_master_admin_all_endpoints_have_auth():
    """PAC-07: price_master_admin.py 전체 엔드포인트 6개 — Depends(get_current_user) 존재."""
    funcs = _func_nodes(_tree(_PRICE_MASTER))
    missing = []
    for name in _PRICE_MASTER_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _has_depends_get_current_user(f):
            missing.append(name)
    assert not missing, f"Depends(get_current_user) 없는 엔드포인트: {missing}"


def test_pac_08_price_master_admin_all_endpoints_have_require_admin():
    """PAC-08: price_master_admin.py 전체 엔드포인트 6개 — _require_admin() 호출 존재."""
    funcs = _func_nodes(_tree(_PRICE_MASTER))
    missing = []
    for name in _PRICE_MASTER_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _require_admin_linenos(f):
            missing.append(name)
    assert not missing, f"_require_admin() 없는 엔드포인트: {missing}"


# ── PAC-09 ~ PAC-10: diagnosis_fields ─────────────────────────────────

def test_pac_09_diagnosis_fields_uses_supabase_client():
    """PAC-09: diagnosis_fields.py가 db.supabase_client를 사용한다."""
    src = _src(_DIAG_FIELDS)
    assert "from db.supabase_client import get_supabase" in src, (
        "diagnosis_fields.py가 db.database(anon key)를 사용 중"
    )
    assert "from db.database import get_supabase" not in src, (
        "diagnosis_fields.py에 db.database import가 남아 있음"
    )


def test_pac_10_diagnosis_fields_no_write_paths():
    """PAC-10: diagnosis_fields.py에 쓰기 경로 없음 (INSERT/UPDATE/DELETE 미사용)."""
    src = _src(_DIAG_FIELDS)
    non_comment = "\n".join(
        l for l in src.splitlines() if not l.strip().startswith("#")
    )
    tree = ast.parse(non_comment)
    write_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("insert", "update", "delete", "upsert")
    ]
    assert not write_calls, (
        f"diagnosis_fields.py에 쓰기 호출 발견: {[n.func.attr for n in write_calls]}"
    )


# ── Negative Controls ──────────────────────────────────────────────────

def test_pac_nc1_db_database_in_admin_pricing_fails():
    """PAC-NC1 (NC): admin_pricing.py에 db.database가 있으면 PAC-01이 실패해야 함."""
    src = _src(_ADMIN_PRICING)
    assert "db.database" not in src, (
        "NC-01 위반: admin_pricing.py에 db.database 잔존 — PAC-01이 PASS해야 함"
    )


def test_pac_nc2_price_setting_patch_no_unguarded_writes():
    """PAC-NC2 (NC): price_setting.py 쓰기 엔드포인트에 auth guard 없으면 탐지."""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    for name in _PRICE_WRITE_ENDPOINTS:
        f = funcs.get(name)
        assert f is not None, f"{name} 함수 없음"
        assert _has_depends_get_current_user(f), f"{name}: auth guard 없음 (NC-02)"
        assert _require_admin_linenos(f), f"{name}: _require_admin 없음 (NC-02)"


# ── PAC-11 ~ PAC-12: price_setting GET 엔드포인트 (R1) ────────────────

def test_pac_11_price_setting_read_endpoints_have_auth():
    """PAC-11 (R1): price_setting.py 읽기 엔드포인트 7개 — Depends(get_current_user) 존재."""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    missing = []
    for name in _PRICE_READ_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _has_depends_get_current_user(f):
            missing.append(name)
    assert not missing, f"Depends(get_current_user) 없는 읽기 엔드포인트: {missing}"


def test_pac_12_price_setting_read_endpoints_have_require_admin():
    """PAC-12 (R1): price_setting.py 읽기 엔드포인트 7개 — _require_admin() 호출 존재."""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    missing = []
    for name in _PRICE_READ_ENDPOINTS:
        f = funcs.get(name)
        if f is None or not _require_admin_linenos(f):
            missing.append(name)
    assert not missing, f"_require_admin() 없는 읽기 엔드포인트: {missing}"


# ── Negative Controls ──────────────────────────────────────────────────

def test_pac_nc3_require_admin_not_commented_out():
    """PAC-NC3 (NC): _require_admin 호출이 주석 처리되지 않음."""
    for path, names in [
        (_ADMIN_PRICING, ["list_pricing_keys", "patch_pricing"]),
        (_PRICE_SETTING, list(_PRICE_WRITE_ENDPOINTS) + list(_PRICE_READ_ENDPOINTS)),
        (_PRICE_MASTER, list(_PRICE_MASTER_ENDPOINTS)),
    ]:
        funcs = _func_nodes(_tree(path))
        for name in names:
            f = funcs.get(name)
            assert f and _require_admin_linenos(f), (
                f"{path.name}:{name} — _require_admin AST 호출 없음 (주석 처리 의심)"
            )


def test_pac_nc4_price_setting_read_no_unguarded_reads():
    """PAC-NC4 (NC, R1): price_setting.py 읽기 엔드포인트에 auth guard 없으면 탐지."""
    funcs = _func_nodes(_tree(_PRICE_SETTING))
    for name in _PRICE_READ_ENDPOINTS:
        f = funcs.get(name)
        assert f is not None, f"{name} 함수 없음"
        assert _has_depends_get_current_user(f), f"{name}: auth guard 없음 (NC-04)"
        assert _require_admin_linenos(f), f"{name}: _require_admin 없음 (NC-04)"
