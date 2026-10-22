"""SEC-04 CURRENT_USER_ID PRIVILEGE REVOKE
WO-TAI-SEC04-CURRENT-USER-ID-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022010122_sec04_current_user_id_privilege_function_revoke.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 RUNTIME_UNVERIFIED.

SOURCE GATE 기준:
  - 대상 함수 정확히 public.current_user_id()
  - 시그니처 ()
  - REVOKE EXECUTE 정확히 1건
  - FROM PUBLIC, anon, authenticated (3종 명시)
  - service_role REVOKE 없음
  - postgres REVOKE 없음
  - GRANT 신규 없음
  - CREATE/ALTER/DROP FUNCTION 없음
  - CREATE/ALTER/DROP TRIGGER 없음
  - RLS 변경 없음
  - Auth 스키마 변경 없음
  - 데이터·테이블 변경 없음
  - 다른 함수 권한 변경 없음
  - 기존 CSI4·UDL7·Remaining6 Migration 변경 없음
  - 비주석 SQL = 승인된 REVOKE 1건과 정확히 일치

테스트 목록:
  CUI-SQL-01  Migration 파일 존재
  CUI-SQL-02  대상 함수 current_user_id 명시
  CUI-SQL-03  시그니처 () 확인
  CUI-SQL-04  REVOKE EXECUTE 정확히 1건
  CUI-SQL-05  REVOKE 대상 함수가 current_user_id()인지 확인
  CUI-SQL-06  PUBLIC 포함 (상속 차단)
  CUI-SQL-07  anon 포함
  CUI-SQL-08  authenticated 포함
  CUI-SQL-09  service_role REVOKE 없음
  CUI-SQL-10  postgres REVOKE 없음
  CUI-SQL-11  GRANT 신규 없음
  CUI-SQL-12  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  CUI-SQL-13  트리거 DDL 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  CUI-SQL-14  RLS 변경 없음
  CUI-SQL-15  Auth 스키마 변경 없음
  CUI-SQL-16  데이터 변경 없음 (TRUNCATE/DELETE/DROP TABLE 없음)
  CUI-SQL-17  다른 함수 권한 변경 없음 (current_user_id 외 REVOKE 없음)
  CUI-SRC-01  기존 CSI4 Migration 변경 없음
  CUI-SRC-02  기존 UDL7 Migration 변경 없음
  CUI-SRC-03  기존 Remaining6 Migration 변경 없음
  CUI-CTR-01  비주석 SQL = 승인된 REVOKE 1건과 정확히 일치
"""
from __future__ import annotations

import hashlib
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022010122_sec04_current_user_id_privilege_function_revoke.sql"
)
_CSI4_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000001_sec04_csi_privilege_function_revoke.sql"
)
_UDL7_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000002_sec04_udl7_privilege_function_revoke.sql"
)
_REMAINING6_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022000003_sec04_remaining6_privilege_function_revoke.sql"
)

# 승인된 REVOKE 1건
_APPROVED_FUNCTION = "public.current_user_id()"
_APPROVED_GRANTEES = ("PUBLIC", "ANON", "AUTHENTICATED")


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


def _parse_revoke_blocks(sql: str) -> list[dict]:
    """각 REVOKE EXECUTE 문에서 함수 시그니처와 FROM 절을 파싱."""
    pattern = (
        r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+"
        r"(public\.\w+\s*\([^)]*\))\s+"
        r"FROM\s+([^;]+);"
    )
    results = []
    for m in re.finditer(pattern, sql, re.IGNORECASE | re.DOTALL):
        fn_raw = re.sub(r"\s+", "", m.group(1))
        from_raw = re.sub(r"\s+", " ", m.group(2).strip())
        results.append({"fn": fn_raw.lower(), "from": from_raw})
    return results


# ── CUI-SQL ────────────────────────────────────────────────────────────────────


def test_cui_sql_01_migration_file_exists():
    """CUI-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_cui_sql_02_target_function_present():
    """CUI-SQL-02: 대상 함수 current_user_id 명시"""
    assert "current_user_id" in _sql(), "current_user_id 함수명 없음"


def test_cui_sql_03_signature_no_args():
    """CUI-SQL-03: current_user_id() 시그니처 (빈 인수)"""
    assert re.search(r"current_user_id\s*\(\s*\)", _sql(), re.IGNORECASE), (
        "current_user_id() 시그니처 없음"
    )


def test_cui_sql_04_revoke_execute_count():
    """CUI-SQL-04: REVOKE EXECUTE 문 정확히 1건"""
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\b", _sql_upper()))
    assert count == 1, f"REVOKE EXECUTE 문 수가 1이어야 합니다. 실제: {count}"


def test_cui_sql_05_revoke_targets_current_user_id():
    """CUI-SQL-05: REVOKE 대상 함수가 current_user_id()"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 1, f"파싱된 REVOKE 블록 수: {len(blocks)}"
    fn = blocks[0]["fn"]
    assert "current_user_id" in fn, f"REVOKE 대상 함수가 current_user_id가 아님: {fn}"
    assert "()" in fn or re.search(r"\(\s*\)", fn), f"빈 인수 시그니처 아님: {fn}"


def test_cui_sql_06_public_included():
    """CUI-SQL-06: PUBLIC 포함 (상속 차단)"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 1
    assert "PUBLIC" in blocks[0]["from"].upper(), (
        f"REVOKE FROM 절에 PUBLIC 없음: {blocks[0]['from']}"
    )


def test_cui_sql_07_anon_included():
    """CUI-SQL-07: anon 포함"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 1
    assert "ANON" in blocks[0]["from"].upper(), (
        f"REVOKE FROM 절에 anon 없음: {blocks[0]['from']}"
    )


def test_cui_sql_08_authenticated_included():
    """CUI-SQL-08: authenticated 포함"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 1
    assert "AUTHENTICATED" in blocks[0]["from"].upper(), (
        f"REVOKE FROM 절에 authenticated 없음: {blocks[0]['from']}"
    )


def test_cui_sql_09_no_service_role_revoke():
    """CUI-SQL-09: service_role REVOKE 없음 (기존 GRANT 유지)"""
    nc = _non_comment_lines(_sql()).upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_cui_sql_10_no_postgres_revoke():
    """CUI-SQL-10: postgres REVOKE 없음"""
    nc = _non_comment_lines(_sql()).upper()
    pg_revokes = re.findall(r"REVOKE[^;]*\bPOSTGRES\b", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_cui_sql_11_no_new_grant():
    """CUI-SQL-11: GRANT 신규 없음"""
    nc = _non_comment_lines(_sql()).upper()
    grants = re.findall(r"\bGRANT\b", nc)
    assert not grants, f"GRANT 발견: {grants}"


def test_cui_sql_12_no_function_ddl():
    """CUI-SQL-12: 함수 정의 변경 없음"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_cui_sql_13_no_trigger_ddl():
    """CUI-SQL-13: 트리거 DDL 없음"""
    sql_u = _sql_upper()
    assert "CREATE TRIGGER" not in sql_u, "CREATE TRIGGER 발견"
    assert "ALTER TRIGGER" not in sql_u, "ALTER TRIGGER 발견"
    assert "DROP TRIGGER" not in sql_u, "DROP TRIGGER 발견"


def test_cui_sql_14_no_rls_change():
    """CUI-SQL-14: RLS 변경 없음"""
    sql_u = _sql_upper()
    assert "ROW LEVEL SECURITY" not in sql_u, "ROW LEVEL SECURITY 변경 발견"
    assert "ENABLE ROW" not in sql_u, "ENABLE ROW LEVEL SECURITY 발견"
    assert "DISABLE ROW" not in sql_u, "DISABLE ROW LEVEL SECURITY 발견"


def test_cui_sql_15_no_auth_schema_change():
    """CUI-SQL-15: Auth 스키마 변경 없음"""
    nc = _non_comment_lines(_sql()).upper()
    auth_changes = re.findall(
        r"(CREATE|ALTER|DROP)\s+(TABLE|FUNCTION|TRIGGER|POLICY)\s+AUTH\.", nc
    )
    assert not auth_changes, f"auth 스키마 DDL 발견: {auth_changes}"
    assert "SET SEARCH_PATH" not in nc, "SET SEARCH_PATH 발견"


def test_cui_sql_16_no_data_mutation():
    """CUI-SQL-16: 데이터 변경 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"
    nc = _non_comment_lines(_sql()).upper()
    assert not re.search(r"\bDELETE\b", nc), "DELETE 발견"


def test_cui_sql_17_only_current_user_id_revoked():
    """CUI-SQL-17: 다른 함수 권한 변경 없음 — current_user_id 외 REVOKE 없음"""
    blocks = _parse_revoke_blocks(_non_comment_lines(_sql()))
    assert len(blocks) == 1, f"비주석 REVOKE 블록 수: {len(blocks)} (기대: 1)"
    fn = blocks[0]["fn"]
    assert "current_user_id" in fn, (
        f"REVOKE 대상이 current_user_id가 아님: {fn}"
    )


# ── CUI-SRC ────────────────────────────────────────────────────────────────────


def test_cui_src_01_csi4_migration_unchanged():
    """CUI-SRC-01: 기존 CSI4 Migration 변경 없음"""
    assert _CSI4_MIGRATION.exists(), f"CSI4 Migration 파일 없음: {_CSI4_MIGRATION}"
    sha256 = hashlib.sha256(_CSI4_MIGRATION.read_bytes()).hexdigest()
    expected = "55cc93031d178022a59f958e0e04376d55db028c9da5ace972dd6afe1fccccf1"
    assert sha256 == expected, (
        f"CSI4 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_cui_src_02_udl7_migration_unchanged():
    """CUI-SRC-02: 기존 UDL7 Migration 변경 없음"""
    assert _UDL7_MIGRATION.exists(), f"UDL7 Migration 파일 없음: {_UDL7_MIGRATION}"
    sha256 = hashlib.sha256(_UDL7_MIGRATION.read_bytes()).hexdigest()
    expected = "daa604b86b2ae479c8d594f47f298c3b271c2fe347fcddac9bc86c9d7f45e28c"
    assert sha256 == expected, (
        f"UDL7 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_cui_src_03_remaining6_migration_unchanged():
    """CUI-SRC-03: 기존 Remaining6 Migration 변경 없음"""
    assert _REMAINING6_MIGRATION.exists(), (
        f"Remaining6 Migration 파일 없음: {_REMAINING6_MIGRATION}"
    )
    sha256 = hashlib.sha256(_REMAINING6_MIGRATION.read_bytes()).hexdigest()
    expected = "06d89b0a2168592ac05845ba9c847601aa1468ff708556921a1acf5e6335b24e"
    assert sha256 == expected, (
        f"Remaining6 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


# ── CUI-CTR ────────────────────────────────────────────────────────────────────


def test_cui_ctr_01_sql_content_matches_approved_revoke():
    """CUI-CTR-01: 비주석 SQL = 승인된 REVOKE 1건과 정확히 일치"""
    blocks = _parse_revoke_blocks(_non_comment_lines(_sql()))
    assert len(blocks) == 1, f"비주석 REVOKE 블록 수: {len(blocks)} (기대: 1)"

    b = blocks[0]
    # 함수 시그니처
    assert "current_user_id" in b["fn"], (
        f"REVOKE 대상 함수가 current_user_id 아님: {b['fn']}"
    )
    assert re.search(r"\(\s*\)", b["fn"]), (
        f"빈 인수 시그니처 아님: {b['fn']}"
    )
    # FROM 절 3종 전부 포함
    from_upper = b["from"].upper()
    for grantee in _APPROVED_GRANTEES:
        assert grantee in from_upper, (
            f"FROM 절에 {grantee} 없음: {b['from']}"
        )
