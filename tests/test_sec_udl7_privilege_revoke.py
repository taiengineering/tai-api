"""SEC-04 UDL7 PRIVILEGE REVOKE
WO-TAI-SEC04-UDL7-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022000002_sec04_udl7_privilege_function_revoke.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 RUNTIME_UNVERIFIED.

SOURCE GATE 기준:
  - REVOKE EXECUTE 문 정확히 7개
  - 대상 함수 7개 명시
  - 시그니처 전부 ()
  - FROM PUBLIC, anon, authenticated (3종 명시)
  - service_role REVOKE 없음
  - postgres REVOKE 없음
  - 함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  - 트리거 DDL 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  - GRANT 신규 없음
  - 데이터·테이블·RLS 변경 없음
  - 기존 CSI4 Migration 변경 없음
  - trg_udl_audit = AFTER INSERT OR UPDATE (GPT 정정 반영)

테스트 목록:
  UDL7-SQL-01  Migration 파일 존재
  UDL7-SQL-02  대상 함수 7개 전부 명시
  UDL7-SQL-03  시그니처 — fn_udl_audit_deny_mutate()
  UDL7-SQL-04  시그니처 — fn_udl_audit_state_change()
  UDL7-SQL-05  시그니처 — fn_udl_deny_delete()
  UDL7-SQL-06  시그니처 — fn_udl_immutability_guard()
  UDL7-SQL-07  시그니처 — fn_udl_insert_guard()
  UDL7-SQL-08  시그니처 — fn_udl_state_guard()
  UDL7-SQL-09  시그니처 — fn_udl_version_bump()
  UDL7-SQL-10  REVOKE EXECUTE 문 정확히 7개
  UDL7-SQL-11  PUBLIC 포함 (상속 차단)
  UDL7-SQL-12  anon 포함
  UDL7-SQL-13  authenticated 포함
  UDL7-SQL-14  service_role REVOKE 없음
  UDL7-SQL-15  postgres REVOKE 없음
  UDL7-SQL-16  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  UDL7-SQL-17  트리거 DDL 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  UDL7-SQL-18  GRANT 신규 없음
  UDL7-SQL-19  데이터 변경 없음 (TRUNCATE/DELETE/DROP TABLE 없음)
  UDL7-SQL-20  RLS 변경 없음 (ALTER TABLE ... ENABLE/DISABLE ROW LEVEL SECURITY 없음)
  UDL7-SRC-01  기존 CSI4 Migration 변경 없음
  UDL7-DOC-01  trg_udl_audit 이벤트 계약 — AFTER INSERT OR UPDATE
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000002_sec04_udl7_privilege_function_revoke.sql"
)
_CSI4_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000001_sec04_csi_privilege_function_revoke.sql"
)

TARGET_FUNCTIONS = [
    "fn_udl_audit_deny_mutate",
    "fn_udl_audit_state_change",
    "fn_udl_deny_delete",
    "fn_udl_immutability_guard",
    "fn_udl_insert_guard",
    "fn_udl_state_guard",
    "fn_udl_version_bump",
]


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


# ── UDL7-SQL ──────────────────────────────────────────────────────────────────


def test_udl7_sql_01_migration_file_exists():
    """UDL7-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_udl7_sql_02_all_seven_functions_present():
    """UDL7-SQL-02: 대상 함수 7개 전부 명시"""
    sql = _sql()
    for fn in TARGET_FUNCTIONS:
        assert fn in sql, f"대상 함수 없음: {fn}"


def test_udl7_sql_03_signature_audit_deny_mutate():
    """UDL7-SQL-03: fn_udl_audit_deny_mutate() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_audit_deny_mutate\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_audit_deny_mutate() 시그니처 없음"
    )


def test_udl7_sql_04_signature_audit_state_change():
    """UDL7-SQL-04: fn_udl_audit_state_change() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_audit_state_change\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_audit_state_change() 시그니처 없음"
    )


def test_udl7_sql_05_signature_deny_delete():
    """UDL7-SQL-05: fn_udl_deny_delete() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_deny_delete\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_deny_delete() 시그니처 없음"
    )


def test_udl7_sql_06_signature_immutability_guard():
    """UDL7-SQL-06: fn_udl_immutability_guard() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_immutability_guard\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_immutability_guard() 시그니처 없음"
    )


def test_udl7_sql_07_signature_insert_guard():
    """UDL7-SQL-07: fn_udl_insert_guard() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_insert_guard\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_insert_guard() 시그니처 없음"
    )


def test_udl7_sql_08_signature_state_guard():
    """UDL7-SQL-08: fn_udl_state_guard() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_state_guard\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_state_guard() 시그니처 없음"
    )


def test_udl7_sql_09_signature_version_bump():
    """UDL7-SQL-09: fn_udl_version_bump() 시그니처"""
    sql = _sql()
    assert re.search(r"fn_udl_version_bump\s*\(\s*\)", sql, re.IGNORECASE), (
        "fn_udl_version_bump() 시그니처 없음"
    )


def test_udl7_sql_10_revoke_execute_count():
    """UDL7-SQL-10: REVOKE EXECUTE 문 정확히 7개"""
    sql_u = _sql_upper()
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\b", sql_u))
    assert count == 7, f"REVOKE EXECUTE 문 수가 7이어야 합니다. 실제: {count}"


def test_udl7_sql_11_public_included():
    """UDL7-SQL-11: PUBLIC 포함 (상속 차단)"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?PUBLIC\b", sql_u), (
        "REVOKE 대상에 PUBLIC이 없습니다"
    )


def test_udl7_sql_12_anon_included():
    """UDL7-SQL-12: anon 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?ANON\b", sql_u), (
        "REVOKE 대상에 anon이 없습니다"
    )


def test_udl7_sql_13_authenticated_included():
    """UDL7-SQL-13: authenticated 포함"""
    sql_u = _sql_upper()
    assert re.search(r"FROM\s+(?:[A-Z,\s]*\b)?AUTHENTICATED\b", sql_u), (
        "REVOKE 대상에 authenticated가 없습니다"
    )


def test_udl7_sql_14_no_service_role_revoke():
    """UDL7-SQL-14: service_role REVOKE 없음 (기존 GRANT 유지)"""
    nc = _non_comment_lines(_sql()).upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_udl7_sql_15_no_postgres_revoke():
    """UDL7-SQL-15: postgres REVOKE 없음"""
    nc = _non_comment_lines(_sql()).upper()
    pg_revokes = re.findall(r"REVOKE[^;]*\bPOSTGRES\b", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_udl7_sql_16_no_function_ddl():
    """UDL7-SQL-16: 함수 정의 변경 없음"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_udl7_sql_17_no_trigger_ddl():
    """UDL7-SQL-17: 트리거 DDL 없음"""
    sql_u = _sql_upper()
    assert "CREATE TRIGGER" not in sql_u, "CREATE TRIGGER 발견"
    assert "ALTER TRIGGER" not in sql_u, "ALTER TRIGGER 발견"
    assert "DROP TRIGGER" not in sql_u, "DROP TRIGGER 발견"


def test_udl7_sql_18_no_new_grant():
    """UDL7-SQL-18: GRANT 신규 없음"""
    nc = _non_comment_lines(_sql()).upper()
    grants = re.findall(r"\bGRANT\b", nc)
    assert not grants, f"GRANT 발견: {grants}"


def test_udl7_sql_19_no_data_mutation():
    """UDL7-SQL-19: 데이터 변경 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"
    nc = _non_comment_lines(_sql()).upper()
    assert not re.search(r"\bDELETE\b", nc), "DELETE 발견"


def test_udl7_sql_20_no_rls_change():
    """UDL7-SQL-20: RLS 변경 없음"""
    sql_u = _sql_upper()
    assert "ROW LEVEL SECURITY" not in sql_u, "ROW LEVEL SECURITY 변경 발견"
    assert "ENABLE ROW" not in sql_u, "ENABLE ROW LEVEL SECURITY 발견"
    assert "DISABLE ROW" not in sql_u, "DISABLE ROW LEVEL SECURITY 발견"


# ── UDL7-SRC ──────────────────────────────────────────────────────────────────


def test_udl7_src_01_csi4_migration_unchanged():
    """UDL7-SRC-01: 기존 CSI4 Migration 변경 없음"""
    import hashlib
    assert _CSI4_MIGRATION.exists(), f"CSI4 Migration 파일 없음: {_CSI4_MIGRATION}"
    content = _CSI4_MIGRATION.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    expected = "55cc93031d178022a59f958e0e04376d55db028c9da5ace972dd6afe1fccccf1"
    assert sha256 == expected, (
        f"CSI4 Migration이 변경됐습니다.\n  기대: {expected}\n  실제: {sha256}"
    )


# ── UDL7-DOC ──────────────────────────────────────────────────────────────────


def test_udl7_doc_01_trg_udl_audit_event_contract():
    """UDL7-DOC-01: trg_udl_audit 이벤트 계약 — AFTER INSERT OR UPDATE"""
    sql = _sql()
    # Migration 주석에 'INSERT OR UPDATE' 문자열이 있는지 확인 (GPT 정정 반영)
    assert "INSERT OR UPDATE" in sql, (
        "trg_udl_audit AFTER INSERT OR UPDATE 이벤트 계약이 Migration 주석에 없습니다"
    )
