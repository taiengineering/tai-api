"""SEC-03 D3-A — WO-TAI-SEC03-D3A-MATERIALIZED-VIEW-LOCKDOWN-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261020000008_sec03_d3a_mv_lockdown.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 TEST_DB_ENVIRONMENT_REQUIRED.

SOURCE GATE 기준:
  - 변경 대상 MV 정확히 2개
  - REVOKE 문 정확히 4개 (FIX-A anon/authenticated × FIX-B anon/authenticated)
  - 총 32개 권한 FALSE 기대 (2 MV × 2 역할 × 8종)
  - postgres / service_role / PUBLIC 미변경
  - MV 정의 변경 없음
  - 데이터 변경 SQL 없음
  - API 소스 변경 없음

테스트 목록:
  D3A-SQL-01  Migration 파일 존재
  D3A-SQL-02  대상 MV 2개 명시 — dashboard_stats
  D3A-SQL-03  대상 MV 2개 명시 — engine_equipment_summary
  D3A-SQL-04  REVOKE 문 정확히 4개
  D3A-SQL-05  FIX-A — dashboard_stats FROM anon 존재
  D3A-SQL-06  FIX-A — dashboard_stats FROM authenticated 존재
  D3A-SQL-07  FIX-B — engine_equipment_summary FROM anon 존재
  D3A-SQL-08  FIX-B — engine_equipment_summary FROM authenticated 존재
  D3A-SQL-09  postgres 권한 REVOKE 없음
  D3A-SQL-10  service_role 권한 REVOKE 없음
  D3A-SQL-11  MV 정의 변경 없음 (CREATE / ALTER MATERIALIZED VIEW 없음)
  D3A-SQL-12  데이터 변경 SQL 없음 (TRUNCATE / DELETE / DROP TABLE 없음)
  D3A-SQL-13  GRANT 신규 추가 없음
  D3A-SQL-14  REVOKE 대상 외 테이블 변경 없음
  D3A-SQL-15  BASE_SHA 주석 포함
  D3A-S01     소비처 dashboard_stats — service_role 경유 (admin_stats.py)
  D3A-S02     소비처 dashboard_stats — service_role 경유 (ops_home_svc.py)
  D3A-S03     소비처 engine_equipment_summary — service_role 경유 (equipment_engine_svc.py)
  D3A-S04     소비처 engine_equipment_summary — service_role 경유 (equipment_catalog_svc.py)
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261020000008_sec03_d3a_mv_lockdown.sql"
)

TARGET_MVS = ["dashboard_stats", "engine_equipment_summary"]
TARGET_ROLES = ["anon", "authenticated"]
BASE_SHA = "48441217f70abcef60f344d77b9f58470a35aaf3"


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _count_revoke_statements(sql: str) -> int:
    return len(re.findall(r"\bREVOKE\b", sql, re.IGNORECASE))


def _count_grant_statements(sql: str) -> int:
    return len(re.findall(r"\bGRANT\b", sql, re.IGNORECASE))


# ── D3A-SQL ─────────────────────────────────────────────────────────────────


def test_d3a_sql_01_migration_file_exists():
    """D3A-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일이 없습니다: {_MIGRATION}"


def test_d3a_sql_02_target_mv_dashboard_stats():
    """D3A-SQL-02: dashboard_stats 명시"""
    assert "dashboard_stats" in _sql(), "dashboard_stats 가 Migration에 없습니다"


def test_d3a_sql_03_target_mv_engine_equipment_summary():
    """D3A-SQL-03: engine_equipment_summary 명시"""
    assert "engine_equipment_summary" in _sql(), "engine_equipment_summary 가 Migration에 없습니다"


def test_d3a_sql_04_revoke_count_exactly_4():
    """D3A-SQL-04: REVOKE 문 정확히 4개"""
    count = _count_revoke_statements(_sql())
    assert count == 4, f"REVOKE 문 수가 4개여야 합니다. 실제: {count}"


def test_d3a_sql_05_fix_a_dashboard_stats_anon():
    """D3A-SQL-05: FIX-A dashboard_stats FROM anon"""
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.DASHBOARD_STATS\s+FROM\s+ANON",
        sql_u,
    ), "dashboard_stats FROM anon REVOKE 문 없음"


def test_d3a_sql_06_fix_a_dashboard_stats_authenticated():
    """D3A-SQL-06: FIX-A dashboard_stats FROM authenticated"""
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.DASHBOARD_STATS\s+FROM\s+AUTHENTICATED",
        sql_u,
    ), "dashboard_stats FROM authenticated REVOKE 문 없음"


def test_d3a_sql_07_fix_b_engine_equipment_anon():
    """D3A-SQL-07: FIX-B engine_equipment_summary FROM anon"""
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.ENGINE_EQUIPMENT_SUMMARY\s+FROM\s+ANON",
        sql_u,
    ), "engine_equipment_summary FROM anon REVOKE 문 없음"


def test_d3a_sql_08_fix_b_engine_equipment_authenticated():
    """D3A-SQL-08: FIX-B engine_equipment_summary FROM authenticated"""
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.ENGINE_EQUIPMENT_SUMMARY\s+FROM\s+AUTHENTICATED",
        sql_u,
    ), "engine_equipment_summary FROM authenticated REVOKE 문 없음"


def test_d3a_sql_09_no_postgres_revoke():
    """D3A-SQL-09: postgres 권한 REVOKE 없음"""
    sql_u = _sql_upper()
    postgres_revokes = re.findall(r"REVOKE[^;]*FROM\s+POSTGRES", sql_u)
    assert not postgres_revokes, f"postgres 권한 REVOKE가 포함돼 있습니다: {postgres_revokes}"


def test_d3a_sql_10_no_service_role_revoke():
    """D3A-SQL-10: service_role 권한 REVOKE 없음"""
    sql_u = _sql_upper()
    sr_revokes = re.findall(r"REVOKE[^;]*FROM\s+SERVICE_ROLE", sql_u)
    assert not sr_revokes, f"service_role 권한 REVOKE가 포함돼 있습니다: {sr_revokes}"


def test_d3a_sql_11_no_materialized_view_ddl():
    """D3A-SQL-11: MV 정의 변경 없음 (CREATE/ALTER MATERIALIZED VIEW 없음)"""
    sql_u = _sql_upper()
    assert "CREATE MATERIALIZED VIEW" not in sql_u, "CREATE MATERIALIZED VIEW 발견"
    assert "ALTER MATERIALIZED VIEW" not in sql_u, "ALTER MATERIALIZED VIEW 발견"
    assert "DROP MATERIALIZED VIEW" not in sql_u, "DROP MATERIALIZED VIEW 발견"


def test_d3a_sql_12_no_data_mutation():
    """D3A-SQL-12: 데이터 변경 SQL 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    # DELETE는 주석에도 없어야 함 (실제 SQL 키워드 기준)
    # 주석 포함하지 않는 검사: 비-주석 라인에서 DELETE 키워드 확인
    non_comment_lines = [
        line for line in _sql().splitlines()
        if not line.strip().startswith("--")
    ]
    non_comment_sql = "\n".join(non_comment_lines).upper()
    assert re.search(r"\bDELETE\b", non_comment_sql) is None, "DELETE 발견 (비주석)"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"


def test_d3a_sql_13_no_grant_added():
    """D3A-SQL-13: GRANT 신규 추가 없음"""
    count = _count_grant_statements(_sql())
    assert count == 0, f"GRANT 문이 있습니다 (허용되지 않음). 수: {count}"


def test_d3a_sql_14_no_other_table_changes():
    """D3A-SQL-14: 대상 외 테이블 REVOKE/ALTER 없음"""
    sql = _sql()
    # REVOKE 문에서 대상 테이블 추출
    revoke_tables = re.findall(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+(?:PUBLIC\.)?(\w+)",
        sql, re.IGNORECASE,
    )
    for tbl in revoke_tables:
        assert tbl.lower() in TARGET_MVS, (
            f"허용되지 않은 대상 테이블: {tbl} (허용: {TARGET_MVS})"
        )


def test_d3a_sql_15_base_sha_in_comment():
    """D3A-SQL-15: BASE_SHA 주석 포함"""
    short_sha = BASE_SHA[:8]
    assert short_sha in _sql(), f"BASE_SHA ({short_sha}...) 주석이 없습니다"


# ── D3A-S (소스 정적 검증) ────────────────────────────────────────────────────


def test_d3a_s01_admin_stats_uses_service_role():
    """D3A-S01: admin_stats.py — dashboard_stats 조회가 get_supabase() 경유"""
    src = (_ROOT / "routers" / "admin_stats.py").read_text(encoding="utf-8")
    assert 'supabase.table("dashboard_stats")' in src, (
        "admin_stats.py 에서 dashboard_stats 조회 코드가 없습니다"
    )
    assert "get_supabase" in src, "admin_stats.py 에서 get_supabase() 미사용"
    # anon/authenticated 직접 key 없음
    assert "anon" not in src.lower().replace("# anon", ""), True


def test_d3a_s02_ops_home_svc_uses_service_role():
    """D3A-S02: ops_home_svc.py — dashboard_stats 조회가 get_supabase() 경유"""
    src = (_ROOT / "services" / "ops_home_svc.py").read_text(encoding="utf-8")
    assert 'table("dashboard_stats")' in src, (
        "ops_home_svc.py 에서 dashboard_stats 조회 코드가 없습니다"
    )
    assert "get_supabase" in src, "ops_home_svc.py 에서 get_supabase() 미사용"


def test_d3a_s03_equipment_engine_svc_uses_service_role():
    """D3A-S03: equipment_engine_svc.py — engine_equipment_summary 조회 경로"""
    src = (_ROOT / "services" / "equipment_engine_svc.py").read_text(encoding="utf-8")
    assert 'table("engine_equipment_summary")' in src, (
        "equipment_engine_svc.py 에서 engine_equipment_summary 조회 코드가 없습니다"
    )
    # 라우터에서 get_supabase()로 주입 확인
    router_src = (_ROOT / "routers" / "engine_equipment.py").read_text(encoding="utf-8")
    assert "get_supabase" in router_src, "engine_equipment.py 에서 get_supabase() 미사용"


def test_d3a_s04_equipment_catalog_svc_uses_service_role():
    """D3A-S04: equipment_catalog_svc.py — engine_equipment_summary 조회 경로"""
    src = (_ROOT / "services" / "equipment_catalog_svc.py").read_text(encoding="utf-8")
    assert 'table("engine_equipment_summary")' in src, (
        "equipment_catalog_svc.py 에서 engine_equipment_summary 조회 코드가 없습니다"
    )
    router_src = (_ROOT / "routers" / "engine_equipment.py").read_text(encoding="utf-8")
    assert "get_supabase" in router_src, "engine_equipment.py 에서 get_supabase() 미사용"
