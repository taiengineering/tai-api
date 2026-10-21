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

    SEC-03(PR #667) 완료 후 갱신된 계약:
    1. POST /refresh 엔드포인트 존재
    2. Depends(get_current_user) 명시
    3. run_refresh_engine_equipment 호출
    4. 해당 Service 내 _require_admin() 존재
    5. _require_admin() 이 RPC 실행보다 먼저 발생
    """
    router_src = (_ROOT / "routers" / "engine_equipment.py").read_text(encoding="utf-8")
    svc_src = (_ROOT / "services" / "equipment_catalog_svc.py").read_text(encoding="utf-8")

    # 1. POST /refresh 엔드포인트 블록 추출
    refresh_block = re.search(
        r'@router\.post\("/refresh"\).*?(?=@router|\Z)',
        router_src, re.DOTALL,
    )
    assert refresh_block is not None, "POST /refresh 엔드포인트를 찾을 수 없습니다"
    block_text = refresh_block.group(0)

    # 2. Depends(get_current_user) 필수
    assert "get_current_user" in block_text, (
        "POST /refresh 에 Depends(get_current_user) 없음 — 인증 누락"
    )

    # 3. run_refresh_engine_equipment 호출 필수
    assert "run_refresh_engine_equipment" in block_text, (
        "POST /refresh 가 run_refresh_engine_equipment 를 호출하지 않음"
    )

    # 4+5. Service 내 _require_admin → RPC 순서 확인
    svc_block = re.search(
        r'def run_refresh_engine_equipment\(.*?\n(?=def |\Z)',
        svc_src, re.DOTALL,
    )
    assert svc_block is not None, "run_refresh_engine_equipment 를 찾을 수 없습니다"
    svc_text = svc_block.group(0)
    assert "_require_admin" in svc_text, (
        "run_refresh_engine_equipment 에 _require_admin 없음 — 관리자 검사 누락"
    )
    admin_pos = svc_text.index("_require_admin")
    rpc_pos = svc_text.index("refresh_engine_equipment_summary")
    assert admin_pos < rpc_pos, (
        "_require_admin 이 RPC 호출보다 나중에 위치 — 권한 검사 순서 위반"
    )
