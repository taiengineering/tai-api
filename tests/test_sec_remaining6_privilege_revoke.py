"""SEC-04 REMAINING6 PRIVILEGE REVOKE
WO-TAI-SEC04-REMAINING6-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022000003_sec04_remaining6_privilege_function_revoke.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 RUNTIME_UNVERIFIED.

SOURCE GATE 기준:
  - REVOKE EXECUTE 문 정확히 6개
  - 대상 함수 6개 명시
  - CSI RPC 시그니처: (integer) × 3
  - Trigger 시그니처: () × 3
  - 각 REVOKE 문에 PUBLIC / anon / authenticated 3종 명시
  - service_role REVOKE 없음
  - postgres REVOKE 없음
  - 함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  - 트리거 DDL 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  - GRANT 신규 없음
  - 데이터·테이블·RLS 변경 없음
  - current_user_id() 변경 없음 (HOLD 유지)
  - 기존 CSI4·UDL7 Migration 변경 없음
  - 비주석 SQL = 승인된 REVOKE 6건과 동일

테스트 목록:
  R6-SQL-01  Migration 파일 존재
  R6-SQL-02  대상 함수 6개 전부 명시
  R6-SQL-03  시그니처 — get_csi_blocklist_keyword_rows_json(integer)
  R6-SQL-04  시그니처 — get_unprocessed_csi_keyword_rows(integer)
  R6-SQL-05  시그니처 — get_unprocessed_csi_keyword_rows_json(integer)
  R6-SQL-06  시그니처 — handle_new_user()
  R6-SQL-07  시그니처 — notify_inbox_trigger()
  R6-SQL-08  시그니처 — set_guest_user_null()
  R6-SQL-09  REVOKE EXECUTE 문 정확히 6개
  R6-SQL-10  각 REVOKE 문에 PUBLIC 포함 (6건 전부)
  R6-SQL-11  각 REVOKE 문에 anon 포함 (6건 전부)
  R6-SQL-12  각 REVOKE 문에 authenticated 포함 (6건 전부)
  R6-SQL-13  service_role REVOKE 없음
  R6-SQL-14  postgres REVOKE 없음
  R6-SQL-15  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  R6-SQL-16  트리거 DDL 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  R6-SQL-17  GRANT 신규 없음
  R6-SQL-18  데이터 변경 없음 (TRUNCATE/DELETE/DROP TABLE 없음)
  R6-SQL-19  RLS 변경 없음
  R6-SQL-20  current_user_id() 변경 없음 (HOLD)
  R6-SRC-01  기존 CSI4 Migration 변경 없음
  R6-SRC-02  기존 UDL7 Migration 변경 없음
  R6-CTR-01  비주석 SQL = 승인된 REVOKE 6건과 동일
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
    / "20261022000003_sec04_remaining6_privilege_function_revoke.sql"
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

TARGET_FUNCTIONS = [
    "get_csi_blocklist_keyword_rows_json",
    "get_unprocessed_csi_keyword_rows",
    "get_unprocessed_csi_keyword_rows_json",
    "handle_new_user",
    "notify_inbox_trigger",
    "set_guest_user_null",
]

# 승인된 REVOKE 6건 (정규화된 형식)
_APPROVED_REVOKES = [
    ("public.get_csi_blocklist_keyword_rows_json(integer)", "PUBLIC, anon, authenticated"),
    ("public.get_unprocessed_csi_keyword_rows(integer)", "PUBLIC, anon, authenticated"),
    ("public.get_unprocessed_csi_keyword_rows_json(integer)", "PUBLIC, anon, authenticated"),
    ("public.handle_new_user()", "PUBLIC, anon, authenticated"),
    ("public.notify_inbox_trigger()", "PUBLIC, anon, authenticated"),
    ("public.set_guest_user_null()", "PUBLIC, anon, authenticated"),
]


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


def _parse_revoke_blocks(sql: str) -> list[dict]:
    """각 REVOKE EXECUTE 문에서 함수 시그니처와 FROM 절을 파싱.

    반환: [{"fn": "public.fn_name(params)", "from": "PUBLIC, anon, authenticated"}, ...]
    """
    pattern = (
        r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+"
        r"(public\.\w+\s*\([^)]*\))\s+"
        r"FROM\s+([^;]+);"
    )
    results = []
    for m in re.finditer(pattern, sql, re.IGNORECASE | re.DOTALL):
        fn_raw = re.sub(r"\s+", "", m.group(1))  # 공백 정규화
        from_raw = re.sub(r"\s+", " ", m.group(2).strip())
        results.append({"fn": fn_raw.lower(), "from": from_raw})
    return results


# ── R6-SQL ────────────────────────────────────────────────────────────────────


def test_r6_sql_01_migration_file_exists():
    """R6-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_r6_sql_02_all_six_functions_present():
    """R6-SQL-02: 대상 함수 6개 전부 명시"""
    sql = _sql()
    for fn in TARGET_FUNCTIONS:
        assert fn in sql, f"대상 함수 없음: {fn}"


def test_r6_sql_03_signature_csi_blocklist_json():
    """R6-SQL-03: get_csi_blocklist_keyword_rows_json(integer) 시그니처"""
    sql = _sql()
    assert re.search(
        r"get_csi_blocklist_keyword_rows_json\s*\(\s*integer\s*\)", sql, re.IGNORECASE
    ), "get_csi_blocklist_keyword_rows_json(integer) 시그니처 없음"


def test_r6_sql_04_signature_csi_unprocessed_rows():
    """R6-SQL-04: get_unprocessed_csi_keyword_rows(integer) 시그니처"""
    sql = _sql()
    assert re.search(
        r"get_unprocessed_csi_keyword_rows\s*\(\s*integer\s*\)", sql, re.IGNORECASE
    ), "get_unprocessed_csi_keyword_rows(integer) 시그니처 없음"


def test_r6_sql_05_signature_csi_unprocessed_rows_json():
    """R6-SQL-05: get_unprocessed_csi_keyword_rows_json(integer) 시그니처"""
    sql = _sql()
    assert re.search(
        r"get_unprocessed_csi_keyword_rows_json\s*\(\s*integer\s*\)", sql, re.IGNORECASE
    ), "get_unprocessed_csi_keyword_rows_json(integer) 시그니처 없음"


def test_r6_sql_06_signature_handle_new_user():
    """R6-SQL-06: handle_new_user() 시그니처"""
    sql = _sql()
    assert re.search(
        r"handle_new_user\s*\(\s*\)", sql, re.IGNORECASE
    ), "handle_new_user() 시그니처 없음"


def test_r6_sql_07_signature_notify_inbox_trigger():
    """R6-SQL-07: notify_inbox_trigger() 시그니처"""
    sql = _sql()
    assert re.search(
        r"notify_inbox_trigger\s*\(\s*\)", sql, re.IGNORECASE
    ), "notify_inbox_trigger() 시그니처 없음"


def test_r6_sql_08_signature_set_guest_user_null():
    """R6-SQL-08: set_guest_user_null() 시그니처"""
    sql = _sql()
    assert re.search(
        r"set_guest_user_null\s*\(\s*\)", sql, re.IGNORECASE
    ), "set_guest_user_null() 시그니처 없음"


def test_r6_sql_09_revoke_execute_count():
    """R6-SQL-09: REVOKE EXECUTE 문 정확히 6개"""
    sql_u = _sql_upper()
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\b", sql_u))
    assert count == 6, f"REVOKE EXECUTE 문 수가 6이어야 합니다. 실제: {count}"


def test_r6_sql_10_public_in_each_revoke():
    """R6-SQL-10: 각 REVOKE 문에 PUBLIC 포함 (6건 전부)"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 6, f"파싱된 REVOKE 블록 수: {len(blocks)}"
    for b in blocks:
        assert "PUBLIC" in b["from"].upper(), (
            f"{b['fn']}: FROM 절에 PUBLIC 없음 — {b['from']}"
        )


def test_r6_sql_11_anon_in_each_revoke():
    """R6-SQL-11: 각 REVOKE 문에 anon 포함 (6건 전부)"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 6, f"파싱된 REVOKE 블록 수: {len(blocks)}"
    for b in blocks:
        assert "ANON" in b["from"].upper(), (
            f"{b['fn']}: FROM 절에 anon 없음 — {b['from']}"
        )


def test_r6_sql_12_authenticated_in_each_revoke():
    """R6-SQL-12: 각 REVOKE 문에 authenticated 포함 (6건 전부)"""
    blocks = _parse_revoke_blocks(_sql())
    assert len(blocks) == 6, f"파싱된 REVOKE 블록 수: {len(blocks)}"
    for b in blocks:
        assert "AUTHENTICATED" in b["from"].upper(), (
            f"{b['fn']}: FROM 절에 authenticated 없음 — {b['from']}"
        )


def test_r6_sql_13_no_service_role_revoke():
    """R6-SQL-13: service_role REVOKE 없음 (기존 GRANT 유지)"""
    nc = _non_comment_lines(_sql()).upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_r6_sql_14_no_postgres_revoke():
    """R6-SQL-14: postgres REVOKE 없음"""
    nc = _non_comment_lines(_sql()).upper()
    pg_revokes = re.findall(r"REVOKE[^;]*\bPOSTGRES\b", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_r6_sql_15_no_function_ddl():
    """R6-SQL-15: 함수 정의 변경 없음"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_r6_sql_16_no_trigger_ddl():
    """R6-SQL-16: 트리거 DDL 없음"""
    sql_u = _sql_upper()
    assert "CREATE TRIGGER" not in sql_u, "CREATE TRIGGER 발견"
    assert "ALTER TRIGGER" not in sql_u, "ALTER TRIGGER 발견"
    assert "DROP TRIGGER" not in sql_u, "DROP TRIGGER 발견"


def test_r6_sql_17_no_new_grant():
    """R6-SQL-17: GRANT 신규 없음"""
    nc = _non_comment_lines(_sql()).upper()
    grants = re.findall(r"\bGRANT\b", nc)
    assert not grants, f"GRANT 발견: {grants}"


def test_r6_sql_18_no_data_mutation():
    """R6-SQL-18: 데이터 변경 없음"""
    sql_u = _sql_upper()
    assert "TRUNCATE" not in sql_u, "TRUNCATE 발견"
    assert "DROP TABLE" not in sql_u, "DROP TABLE 발견"
    nc = _non_comment_lines(_sql()).upper()
    assert not re.search(r"\bDELETE\b", nc), "DELETE 발견"


def test_r6_sql_19_no_rls_change():
    """R6-SQL-19: RLS 변경 없음"""
    sql_u = _sql_upper()
    assert "ROW LEVEL SECURITY" not in sql_u, "ROW LEVEL SECURITY 변경 발견"
    assert "ENABLE ROW" not in sql_u, "ENABLE ROW LEVEL SECURITY 발견"
    assert "DISABLE ROW" not in sql_u, "DISABLE ROW LEVEL SECURITY 발견"


def test_r6_sql_20_current_user_id_unchanged():
    """R6-SQL-20: current_user_id() 변경 없음 (HOLD 유지) — 비주석 SQL 기준"""
    nc = _non_comment_lines(_sql())
    assert "current_user_id" not in nc, (
        "current_user_id가 비주석 SQL에 포함됐습니다 — HOLD 대상입니다"
    )


# ── R6-SRC ────────────────────────────────────────────────────────────────────


def test_r6_src_01_csi4_migration_unchanged():
    """R6-SRC-01: 기존 CSI4 Migration 변경 없음"""
    assert _CSI4_MIGRATION.exists(), f"CSI4 Migration 파일 없음: {_CSI4_MIGRATION}"
    sha256 = hashlib.sha256(_CSI4_MIGRATION.read_bytes()).hexdigest()
    expected = "55cc93031d178022a59f958e0e04376d55db028c9da5ace972dd6afe1fccccf1"
    assert sha256 == expected, (
        f"CSI4 Migration이 변경됐습니다.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_r6_src_02_udl7_migration_unchanged():
    """R6-SRC-02: 기존 UDL7 Migration 변경 없음"""
    assert _UDL7_MIGRATION.exists(), f"UDL7 Migration 파일 없음: {_UDL7_MIGRATION}"
    sha256 = hashlib.sha256(_UDL7_MIGRATION.read_bytes()).hexdigest()
    expected = "daa604b86b2ae479c8d594f47f298c3b271c2fe347fcddac9bc86c9d7f45e28c"
    assert sha256 == expected, (
        f"UDL7 Migration이 변경됐습니다.\n  기대: {expected}\n  실제: {sha256}"
    )


# ── R6-CTR ────────────────────────────────────────────────────────────────────


def test_r6_ctr_01_sql_content_matches_approved_revokes():
    """R6-CTR-01: 비주석 SQL = 승인된 REVOKE 6건과 동일"""
    blocks = _parse_revoke_blocks(_non_comment_lines(_sql()))
    assert len(blocks) == 6, f"비주석 REVOKE 블록 수: {len(blocks)} (기대: 6)"

    actual_fns = [b["fn"] for b in blocks]
    for fn_sig, from_clause in _APPROVED_REVOKES:
        normalized_fn = re.sub(r"\s+", "", fn_sig).lower()
        assert normalized_fn in actual_fns, (
            f"승인된 함수 {fn_sig} 가 비주석 SQL에 없습니다"
        )
        matched = next(b for b in blocks if b["fn"] == normalized_fn)
        from_upper = matched["from"].upper()
        for grantee in ("PUBLIC", "ANON", "AUTHENTICATED"):
            assert grantee in from_upper, (
                f"{fn_sig}: FROM 절에 {grantee} 없음 — {matched['from']}"
            )
