"""SEC-04 CSI4 PRIVILEGE REVOKE
WO-TAI-SUPABASE-SEC04-CSI4-REVOKE-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022000001_sec04_csi_privilege_function_revoke.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 TEST_DB_ENVIRONMENT_REQUIRED.

SOURCE GATE 기준:
  - REVOKE EXECUTE 문 정확히 4개
  - 대상 함수 4개 명시
  - 시그니처 일치: (integer) / (integer) / () / ()
  - FROM PUBLIC, anon, authenticated (3종 명시)
  - service_role REVOKE 없음
  - postgres REVOKE 없음
  - 함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  - GRANT 신규 없음 (anon/authenticated 재허용 없음)
  - MV·데이터 변경 없음

테스트 목록:
  CSI4-SQL-01  Migration 파일 존재
  CSI4-SQL-02  대상 함수 4개 전부 명시
  CSI4-SQL-03  시그니처 — invoke_csi_keyword_extract(integer)
  CSI4-SQL-04  시그니처 — repair_csi_blocklist_keywords(integer)
  CSI4-SQL-05  시그니처 — start_csi_keyword_extract_job()
  CSI4-SQL-06  시그니처 — status_csi_keyword_extract_job()
  CSI4-SQL-07  REVOKE EXECUTE 문 정확히 4개
  CSI4-SQL-08  PUBLIC 포함 (상속 차단)
  CSI4-SQL-09  anon 포함
  CSI4-SQL-10  authenticated 포함
  CSI4-SQL-11  service_role REVOKE 없음
  CSI4-SQL-12  postgres REVOKE 없음
  CSI4-SQL-13  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  CSI4-SQL-14  GRANT 신규 없음 (anon/authenticated에 재허용 없음)
  CSI4-SQL-15  데이터 변경 없음 (TRUNCATE/DELETE/DROP TABLE 없음)
  CSI4-SQL-16  MV 변경 없음
  CSI4-SRC-01  Python API가 4개 함수를 직접 호출하지 않음
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000001_sec04_csi_privilege_function_revoke.sql"
)

TARGET_FUNCTIONS = [
    "invoke_csi_keyword_extract",
    "repair_csi_blocklist_keywords",
    "start_csi_keyword_extract_job",
    "status_csi_keyword_extract_job",
]

CSI_ADMIN_ROUTER = _ROOT / "routers" / "admin_csi_keyword_extract.py"


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


# ── CSI4-SQL ──────────────────────────────────────────────────────────────────


def test_csi4_sql_01_migration_file_exists():
    """CSI4-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_csi4_sql_02_all_four_functions_present():
    """CSI4-SQL-02: 대상 함수 4개 전부 명시"""
    sql = _sql()
    for fn in TARGET_FUNCTIONS:
        assert fn in sql, f"대상 함수 없음: {fn}"


def test_csi4_sql_03_signature_invoke():
    """CSI4-SQL-03: invoke_csi_keyword_extract(integer) 시그니처"""
    sql = _sql()
    assert re.search(r"invoke_csi_keyword_extract\s*\(\s*integer\s*\)", sql, re.IGNORECASE), (
        "invoke_csi_keyword_extract(integer) 시그니처 없음"
    )


def test_csi4_sql_04_signature_repair():
    """CSI4-SQL-04: repair_csi_blocklist_keywords(integer) 시그니처"""
    sql = _sql()
    assert re.search(r"repair_csi_blocklist_keywords\s*\(\s*integer\s*\)", sql, re.IGNORECASE), (
        "repair_csi_blocklist_keywords(integer) 시그니처 없음"
    )


def test_csi4_sql_05_signature_start():
    """CSI4-SQL-05: start_csi_keyword_extract_job() 시그니처"""
    sql = _sql()
    assert re.search(r"start_csi_keyword_extract_job\s*\(\s*\)", sql, re.IGNORECASE), (
        "start_csi_keyword_extract_job() 시그니처 없음"
    )


def test_csi4_sql_06_signature_status():
    """CSI4-SQL-06: status_csi_keyword_extract_job() 시그니처"""
    sql = _sql()
    assert re.search(r"status_csi_keyword_extract_job\s*\(\s*\)", sql, re.IGNORECASE), (
        "status_csi_keyword_extract_job() 시그니처 없음"
    )


def test_csi4_sql_07_revoke_execute_count():
    """CSI4-SQL-07: REVOKE EXECUTE 문 정확히 4개"""
    sql_u = _sql_upper()
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\b", sql_u))
    assert count == 4, f"REVOKE EXECUTE 문 수가 4여야 합니다. 실제: {count}"


def test_csi4_sql_08_public_included():
    """CSI4-SQL-08: PUBLIC 포함 (상속 차단)"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?PUBLIC\b", sql_u), (
        "REVOKE 대상에 PUBLIC이 없습니다"
    )


def test_csi4_sql_09_anon_included():
    """CSI4-SQL-09: anon 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?ANON\b", sql_u), (
        "REVOKE 대상에 anon이 없습니다"
    )


def test_csi4_sql_10_authenticated_included():
    """CSI4-SQL-10: authenticated 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?AUTHENTICATED\b", sql_u), (
        "REVOKE 대상에 authenticated가 없습니다"
    )


def test_csi4_sql_11_no_service_role_revoke():
    """CSI4-SQL-11: service_role REVOKE 없음 (기존 GRANT 유지)"""
    nc = _non_comment_lines(_sql()).upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_csi4_sql_12_no_postgres_revoke():
    """CSI4-SQL-12: postgres REVOKE 없음"""
    nc = _non_comment_lines(_sql()).upper()
    pg_revokes = re.findall(r"REVOKE[^;]*POSTGRES", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_csi4_sql_13_no_function_ddl():
    """CSI4-SQL-13: 함수 정의 변경 없음"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_csi4_sql_14_no_new_grant_to_anon_authenticated():
    """CSI4-SQL-14: GRANT 신규 없음 (anon/authenticated 재허용 없음)"""
    nc = _non_comment_lines(_sql()).upper()
    grants = re.findall(r"\bGRANT\b[^;]*(?:ANON|AUTHENTICATED)", nc)
    assert not grants, f"anon/authenticated에 GRANT 발견: {grants}"


def test_csi4_sql_15_no_data_mutation():
    """CSI4-SQL-15: 데이터 변경 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"
    nc = _non_comment_lines(_sql()).upper()
    assert not re.search(r"\bDELETE\b", nc), "DELETE 발견"


def test_csi4_sql_16_no_mv_change():
    """CSI4-SQL-16: MV 변경 없음"""
    sql_u = _sql_upper()
    assert "REFRESH MATERIALIZED VIEW" not in sql_u, "REFRESH MATERIALIZED VIEW 발견"
    assert "CREATE MATERIALIZED VIEW" not in sql_u, "CREATE MATERIALIZED VIEW 발견"
    assert "DROP MATERIALIZED VIEW" not in sql_u, "DROP MATERIALIZED VIEW 발견"


# ── CSI4-SRC ──────────────────────────────────────────────────────────────────


def test_csi4_src_01_python_does_not_call_target_functions():
    """CSI4-SRC-01: Python API가 4개 함수를 직접 호출하지 않음"""
    src = CSI_ADMIN_ROUTER.read_text(encoding="utf-8")
    for fn in TARGET_FUNCTIONS:
        assert fn not in src, (
            f"admin_csi_keyword_extract.py가 {fn}을 참조합니다 — 기존 의존성 검토 필요"
        )
