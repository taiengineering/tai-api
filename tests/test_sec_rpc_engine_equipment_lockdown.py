"""SEC-03 RPC-ENGINE-EQUIPMENT-LOCKDOWN
WO-TAI-SEC03-RPC-ENGINE-EQUIPMENT-LOCKDOWN-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261020000009_sec03_rpc_engine_equipment_lockdown.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 TEST_DB_ENVIRONMENT_REQUIRED.

SOURCE GATE 기준:
  - REVOKE EXECUTE 문 1개 (PUBLIC, anon, authenticated 포함)
  - PUBLIC 반드시 포함 (상속 차단)
  - anon / authenticated 포함
  - postgres REVOKE 없음
  - service_role REVOKE 없음
  - 함수 정의 변경 없음 (CREATE/ALTER FUNCTION 없음)
  - MV 변경 없음
  - DB 데이터 변경 없음

테스트 목록:
  RPC-SQL-01  Migration 파일 존재
  RPC-SQL-02  대상 함수 명시 — refresh_engine_equipment_summary
  RPC-SQL-03  REVOKE EXECUTE 문 1개
  RPC-SQL-04  PUBLIC 포함
  RPC-SQL-05  anon 포함
  RPC-SQL-06  authenticated 포함
  RPC-SQL-07  postgres REVOKE 없음
  RPC-SQL-08  service_role REVOKE 없음
  RPC-SQL-09  GRANT 신규 없음
  RPC-SQL-10  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  RPC-SQL-11  MV 변경 없음 (REFRESH MATERIALIZED VIEW 없음)
  RPC-SQL-12  데이터 변경 없음 (TRUNCATE/DELETE/DROP TABLE 없음)
  RPC-SQL-13  BASE_SHA 주석 포함
  RPC-SQL-14  대상 외 함수 변경 없음
  RPC-S01     소비처 service_role 경유 확인 (equipment_catalog_svc.py)
  RPC-S02     POST /refresh 인증 및 관리자 권한 계약 확인
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261020000009_sec03_rpc_engine_equipment_lockdown.sql"
)

TARGET_FUNC = "refresh_engine_equipment_summary"
BASE_SHA = "e820ed064eab4f22eadb4facf8d6515583a00adf"


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return "\n".join(lines)


# ── RPC-SQL ──────────────────────────────────────────────────────────────────


def test_rpc_sql_01_migration_file_exists():
    """RPC-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_rpc_sql_02_target_function_named():
    """RPC-SQL-02: 대상 함수 명시"""
    assert TARGET_FUNC in _sql(), f"{TARGET_FUNC} 이 Migration에 없습니다"


def test_rpc_sql_03_revoke_execute_count():
    """RPC-SQL-03: REVOKE EXECUTE 문 정확히 1개"""
    sql_u = _sql_upper()
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\b", sql_u))
    assert count == 1, f"REVOKE EXECUTE 문 수가 1개여야 합니다. 실제: {count}"


def test_rpc_sql_04_public_included():
    """RPC-SQL-04: PUBLIC 포함 (상속 차단)"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?PUBLIC\b", sql_u), (
        "REVOKE 대상에 PUBLIC이 없습니다 — PUBLIC 상속 차단 누락"
    )


def test_rpc_sql_05_anon_included():
    """RPC-SQL-05: anon 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?ANON\b", sql_u), (
        "REVOKE 대상에 anon이 없습니다"
    )


def test_rpc_sql_06_authenticated_included():
    """RPC-SQL-06: authenticated 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?AUTHENTICATED\b", sql_u), (
        "REVOKE 대상에 authenticated가 없습니다"
    )


def test_rpc_sql_07_no_postgres_revoke():
    """RPC-SQL-07: postgres EXECUTE REVOKE 없음"""
    sql_u = _non_comment_lines(_sql()).upper()
    postgres_revokes = re.findall(r"REVOKE[^;]*POSTGRES", sql_u)
    assert not postgres_revokes, f"postgres 권한 REVOKE 발견: {postgres_revokes}"


def test_rpc_sql_08_no_service_role_revoke():
    """RPC-SQL-08: service_role EXECUTE REVOKE 없음"""
    sql_u = _non_comment_lines(_sql()).upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", sql_u)
    assert not sr_revokes, f"service_role 권한 REVOKE 발견: {sr_revokes}"


def test_rpc_sql_09_no_grant_added():
    """RPC-SQL-09: GRANT 신규 없음"""
    sql_u = _non_comment_lines(_sql()).upper()
    grant_count = len(re.findall(r"\bGRANT\b", sql_u))
    assert grant_count == 0, f"GRANT 문 발견: {grant_count}개"


def test_rpc_sql_10_no_function_ddl():
    """RPC-SQL-10: 함수 정의 변경 없음"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_rpc_sql_11_no_mv_refresh():
    """RPC-SQL-11: MV 변경/Refresh 없음"""
    sql_u = _sql_upper()
    assert "REFRESH MATERIALIZED VIEW" not in sql_u, "REFRESH MATERIALIZED VIEW 발견"
    assert "CREATE MATERIALIZED VIEW" not in sql_u, "CREATE MATERIALIZED VIEW 발견"
    assert "DROP MATERIALIZED VIEW" not in sql_u, "DROP MATERIALIZED VIEW 발견"


def test_rpc_sql_12_no_data_mutation():
    """RPC-SQL-12: 데이터 변경 SQL 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"
    nc = _non_comment_lines(_sql()).upper()
    assert re.search(r"\bDELETE\b", nc) is None, "DELETE 발견"


def test_rpc_sql_13_base_sha_in_comment():
    """RPC-SQL-13: BASE_SHA 주석 포함"""
    short_sha = BASE_SHA[:8]
    assert short_sha in _sql(), f"BASE_SHA ({short_sha}...) 주석 없음"


def test_rpc_sql_14_no_other_function_changes():
    """RPC-SQL-14: 대상 함수 외 REVOKE/GRANT 없음"""
    sql = _sql()
    revoke_funcs = re.findall(
        r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+(?:PUBLIC\.)?(\w+)",
        sql, re.IGNORECASE,
    )
    for fn in revoke_funcs:
        assert fn.lower() == TARGET_FUNC.lower(), (
            f"허용되지 않은 대상 함수: {fn} (허용: {TARGET_FUNC})"
        )


# ── RPC-S (소스 정적 검증) ────────────────────────────────────────────────────


def test_rpc_s01_consumer_uses_service_role():
    """RPC-S01: 소비처 service_role 경유 — equipment_catalog_svc.py"""
    src = (_ROOT / "services" / "equipment_catalog_svc.py").read_text(encoding="utf-8")
    assert 'rpc("refresh_engine_equipment_summary")' in src, (
        "equipment_catalog_svc.py 에서 RPC 호출 코드 없음"
    )
    router_src = (_ROOT / "routers" / "engine_equipment.py").read_text(encoding="utf-8")
    assert "get_supabase" in router_src, (
        "engine_equipment.py 에서 get_supabase() 미사용"
    )


def test_rpc_s02_api_refresh_requires_auth_and_admin():
    """RPC-S02: POST /engine-equipment/refresh 인증 및 관리자 권한 계약 확인

    SEC-03(PR #667) 완료 후 갱신된 계약 (전체 AST 기반):
    1. @router.post("/refresh") 데코레이터 존재
    2. Depends(get_current_user) 파라미터 기본값 존재
    3. run_refresh_engine_equipment(current=...) 실제 호출 + current 전달
    4. _require_admin() 실제 AST Call 존재 (주석 제외)
    5. RPC rpc("refresh_engine_equipment_summary") 실제 AST Call 존재 (주석 제외)
    6. _require_admin() lineno < rpc() lineno

    Negative Control 보장 (NC-01~08):
    NC-01: Depends(get_current_user) 제거, 주석 유지 → FAIL
    NC-02: 서비스 호출 제거, 주석 유지 → FAIL
    NC-03: _require_admin() 호출 제거, import 유지 → FAIL
    NC-04: _require_admin() 호출을 RPC 뒤로 이동 → FAIL
    NC-05: @router.post 경로 변경 → FAIL
    NC-06: current 인수 전달 제거 → FAIL
    NC-07: _require_admin() 호출을 주석 처리 → FAIL
    NC-08: RPC 호출을 주석 처리 → FAIL
    """
    import ast as _ast

    router_src = (_ROOT / "routers" / "engine_equipment.py").read_text(encoding="utf-8")
    svc_src = (_ROOT / "services" / "equipment_catalog_svc.py").read_text(encoding="utf-8")

    # ── Router 검증 ────────────────────────────────────────────────────────────

    router_tree = _ast.parse(router_src)

    # 1. refresh_engine_equipment 핸들러 AST 노드 추출
    refresh_handler = None
    for node in _ast.walk(router_tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            if node.name == "refresh_engine_equipment":
                refresh_handler = node
                break
    assert refresh_handler is not None, "refresh_engine_equipment 핸들러를 찾을 수 없습니다"

    # R1: @router.post("/refresh") 데코레이터 AST 검증 (NC-05: 경로 변경 시 FAIL)
    has_route = any(
        isinstance(dec, _ast.Call)
        and isinstance(dec.func, _ast.Attribute) and dec.func.attr == "post"
        and dec.args
        and isinstance(dec.args[0], _ast.Constant) and dec.args[0].value == "/refresh"
        for dec in refresh_handler.decorator_list
    )
    assert has_route, (
        "refresh_engine_equipment 에 @router.post('/refresh') 데코레이터 없음"
    )

    # 2. Depends(get_current_user) — AST 파라미터 기본값 (NC-01: 주석 유지해도 FAIL)
    has_auth_dep = any(
        isinstance(d, _ast.Call)
        and isinstance(d.func, _ast.Name) and d.func.id == "Depends"
        and d.args
        and isinstance(d.args[0], _ast.Name) and d.args[0].id == "get_current_user"
        for d in refresh_handler.args.defaults
    )
    assert has_auth_dep, (
        "POST /refresh 에 Depends(get_current_user) 없음 — 인증 누락"
    )

    # R2 + 3: run_refresh_engine_equipment(current) AST Call 검증
    # NC-02: 주석 유지해도 FAIL, NC-06: current 제거 시 FAIL
    svc_call_node = None
    for node in _ast.walk(refresh_handler):
        if (isinstance(node, _ast.Call)
                and isinstance(node.func, _ast.Attribute)
                and node.func.attr == "run_refresh_engine_equipment"):
            svc_call_node = node
            break
    assert svc_call_node is not None, (
        "POST /refresh 핸들러에 run_refresh_engine_equipment AST 호출 없음"
    )
    has_current_arg = any(
        isinstance(arg, _ast.Name) and arg.id == "current"
        for arg in svc_call_node.args
    )
    assert has_current_arg, (
        "run_refresh_engine_equipment 호출에 current 인수 없음"
    )

    # ── Service 검증 ───────────────────────────────────────────────────────────

    svc_tree = _ast.parse(svc_src)

    # run_refresh_engine_equipment 함수 AST 노드 추출
    svc_func = None
    for node in _ast.walk(svc_tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "run_refresh_engine_equipment":
            svc_func = node
            break
    assert svc_func is not None, "run_refresh_engine_equipment 함수를 찾을 수 없습니다"

    # R3: _require_admin() 실제 AST Call 수집 (NC-03: import만 남기면 FAIL, NC-07: 주석 처리 시 FAIL)
    admin_linenos = [
        node.lineno
        for node in _ast.walk(svc_func)
        if isinstance(node, _ast.Call)
        and isinstance(node.func, _ast.Name)
        and node.func.id == "_require_admin"
    ]
    assert admin_linenos, (
        "run_refresh_engine_equipment 에 _require_admin() AST 호출 없음 — 관리자 검사 누락"
    )

    # R3: RPC rpc("refresh_engine_equipment_summary") 실제 AST Call 수집
    # NC-08: 주석 처리 시 FAIL
    rpc_linenos = [
        node.lineno
        for node in _ast.walk(svc_func)
        if isinstance(node, _ast.Call)
        and isinstance(node.func, _ast.Attribute)
        and node.func.attr == "rpc"
        and node.args
        and isinstance(node.args[0], _ast.Constant)
        and node.args[0].value == "refresh_engine_equipment_summary"
    ]
    assert rpc_linenos, (
        "run_refresh_engine_equipment 에 rpc('refresh_engine_equipment_summary') AST 호출 없음"
    )

    # R3: _require_admin() lineno < rpc() lineno (NC-04: 순서 역전 시 FAIL)
    assert min(admin_linenos) < min(rpc_linenos), (
        "_require_admin() 이 RPC 호출보다 나중 라인에 위치 — 권한 검사 순서 위반"
    )
