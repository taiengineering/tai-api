"""
WO-TAI-SEC-SEARCHPATH-REM97-B19-C3-SOURCE-001
B19 get_precompiled_factory_ids() search_path 고정 정적 계약 테스트.

대상:
  public.get_precompiled_factory_ids()  OID=70200  (B19)

검증 항목:
  - Migration 파일 존재 및 SHA256 불변
  - ALTER 대상 시그니처·search_path 값
  - 함수 본문 MD5 기준선
  - anon/authenticated 권한 확대 없음 계약 포함 여부
"""
import hashlib
import pathlib
import re


MIGRATION_FILE = pathlib.Path(
    "supabase/migrations/"
    "20261025000000_sec_searchpath_rem97_b19_get_precompiled_factory_ids.sql"
)
MIGRATION_SHA256 = (
    "593c57f92ec4ace4fa8a9d8e05b6e0cc5fc99876498fa9c2cceb598c11ded42b"
)

BODY_MD5 = "fa38689f8ad0f1fd6b904df01237bbde"
TARGET_SEARCH_PATH = "pg_catalog, engine_isolated, public, pg_temp"
TARGET_OID = 70200
TARGET_PROCONFIG = f"search_path={TARGET_SEARCH_PATH}"


def _migration_text() -> str:
    return MIGRATION_FILE.read_text(encoding="utf-8")


def test_migration_file_exists():
    assert MIGRATION_FILE.exists(), f"Migration not found: {MIGRATION_FILE}"


def test_migration_sha256():
    content = MIGRATION_FILE.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    assert digest == MIGRATION_SHA256, (
        f"SHA256 mismatch: expected {MIGRATION_SHA256}, got {digest}"
    )


def test_migration_targets_correct_function():
    text = _migration_text()
    assert "public.get_precompiled_factory_ids()" in text


def test_migration_sets_engine_isolated_search_path():
    text = _migration_text()
    assert f"SET search_path = {TARGET_SEARCH_PATH}" in text


def test_migration_does_not_set_plain_public_only_path():
    text = _migration_text()
    plain_path = "SET search_path = pg_catalog, public, pg_temp"
    assert plain_path not in text, (
        "Migration must not use public-only search_path for B19"
    )


def test_migration_oid_baseline():
    text = _migration_text()
    assert str(TARGET_OID) in text, f"OID {TARGET_OID} baseline not found"


def test_migration_body_md5_baseline():
    text = _migration_text()
    assert BODY_MD5 in text, f"body_md5 {BODY_MD5} baseline not found"


def test_migration_no_grant_change():
    text = _migration_text()
    # GRANT 문이 없어야 함 (ACL 변경 없음)
    grant_lines = [
        line.strip() for line in text.splitlines()
        if re.match(r"^GRANT\b", line.strip(), re.IGNORECASE)
    ]
    assert len(grant_lines) == 0, (
        f"Migration must not contain GRANT statements: {grant_lines}"
    )


def test_migration_no_create_view_or_function():
    text = _migration_text()
    assert "CREATE VIEW" not in text.upper()
    assert "CREATE FUNCTION" not in text.upper()
    assert "CREATE OR REPLACE FUNCTION" not in text.upper()


def test_migration_has_anon_authenticated_permission_check():
    text = _migration_text()
    assert "anon" in text
    assert "authenticated" in text
    assert "engine_isolated" in text


def test_migration_is_in_transaction():
    text = _migration_text()
    assert "BEGIN;" in text
    assert "COMMIT;" in text


def test_migration_b19_hold_released():
    """B19는 HOLD_SCHEMA_RESOLUTION에서 C3 Owner 승인으로 해제됐음을 문서화."""
    text = _migration_text()
    assert "B19" in text
    assert "engine_isolated" in text
    assert "service_role" in text
