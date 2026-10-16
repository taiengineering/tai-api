"""WO-E2E2000-WP01-A-FINAL-INTEGRATION-GATE-001 Task 2: 격리 PostgreSQL 마이그레이션 검증.

실행 조건: ISOLATED_TEST_DATABASE_URL 환경 변수 설정 필요.
  예: ISOLATED_TEST_DATABASE_URL=postgresql://postgres:pass@localhost:5432/testdb

운영 DB 사용 금지:
  - URL에 'supabase.co' 포함 → 자동 차단
  - URL에 'railway.app' 포함 → 자동 차단

검증 항목:
  M01: 기존 C10 스키마(컬럼 없음) → 마이그레이션 실행 후 신규 컬럼 추가됨
  M02: 마이그레이션 반복 실행 안전성 (ADD COLUMN IF NOT EXISTS)
  M03: 기존 행 → inspection_materialization_status = NULL 유지 (backfill 0)
  M04: PENDING INSERT 정상 저장
  M05: MATERIALIZED UPDATE 정상 저장
  M06: FAILED UPDATE 정상 저장
  M07: BLOCKED_LEGACY_ROWS UPDATE 정상 저장
  M08: 기존 status/full_result 컬럼 무변경 (마이그레이션 부작용 없음)

CI 연동: ISOLATED_TEST_DATABASE_URL 미설정 시 전체 skip.
  로컬 실행 예시 (Docker):
    docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=test postgres:15
    ISOLATED_TEST_DATABASE_URL=postgresql://postgres:test@localhost:5432/postgres \
      pytest tests/test_wp01a_c10_migration_postgres.py -v
"""
from __future__ import annotations

import os
import pathlib
import uuid

import pytest

# ── 격리 DB URL 안전 검증 ──────────────────────────────────────────────────────

_URL = os.environ.get("ISOLATED_TEST_DATABASE_URL", "")
_PRODUCTION_KEYWORDS = ("supabase.co", "railway.app")

_SKIP_REASON = (
    "ISOLATED_TEST_DATABASE_URL 미설정 — "
    "격리 PostgreSQL 환경에서만 실행 가능. README 참고."
)

pytestmark = pytest.mark.skipif(not _URL, reason=_SKIP_REASON)


def _assert_not_production(url: str) -> None:
    """운영 DB 연결 방지 안전장치."""
    for kw in _PRODUCTION_KEYWORDS:
        if kw in url:
            raise RuntimeError(
                f"[SAFETY] ISOLATED_TEST_DATABASE_URL에 '{kw}'이 포함됐습니다. "
                "운영 DB는 사용 금지입니다."
            )


# ── psycopg2 import (requirements.txt 에 포함) ────────────────────────────────

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

pytestmark = [
    pytest.mark.skipif(not _URL, reason=_SKIP_REASON),
    pytest.mark.skipif(not _HAS_PSYCOPG2, reason="psycopg2 미설치"),
]

# ── 마이그레이션 SQL 경로 ──────────────────────────────────────────────────────

_MIGRATION_FILE = (
    pathlib.Path(__file__).parent.parent
    / "supabase" / "migrations"
    / "20261016000003_wp01a_c10_materialization_status.sql"
)

# ── 테스트 스키마 격리용 테이블명 ─────────────────────────────────────────────

_TEST_TABLE = "test_anon_diag_" + uuid.uuid4().hex[:8]


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def conn():
    """격리 PostgreSQL 연결 + 테스트 테이블 생성 → 완료 후 DROP."""
    _assert_not_production(_URL)
    c = psycopg2.connect(_URL)
    c.autocommit = False
    cur = c.cursor()

    # 테스트용 C10 최소 스키마 생성 (운영 스키마 모방)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TEST_TABLE} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            source_type TEXT,
            full_result JSONB,
            input_data JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    # 기존 행 1개 삽입 (마이그레이션 전)
    cur.execute(f"""
        INSERT INTO {_TEST_TABLE} (status, source_type, full_result)
        VALUES ('ACTIVE', 'saas', '{{"facility_used": {{"worker_count": 30}}}}')
    """)
    c.commit()

    yield c, cur, _TEST_TABLE

    # 정리
    cur.execute(f"DROP TABLE IF EXISTS {_TEST_TABLE}")
    c.commit()
    cur.close()
    c.close()


def _run_migration_on_table(cur, table_name: str) -> None:
    """마이그레이션 SQL을 읽어서 테스트 테이블에 적용 (public.anonymous_diagnosis_results → 테스트 테이블명 대체)."""
    sql = _MIGRATION_FILE.read_text()
    # 테스트용 테이블명으로 교체 (마이그레이션은 public.anonymous_diagnosis_results 대상)
    sql = sql.replace(
        "public.anonymous_diagnosis_results",
        table_name,
    )
    cur.execute(sql)


# ── M01: 컬럼 추가 ────────────────────────────────────────────────────────────

def test_M01_column_added_after_migration(conn):
    """마이그레이션 실행 후 inspection_materialization_status 컬럼이 추가된다."""
    c, cur, table = conn

    # 마이그레이션 전: 컬럼 없음 확인
    cur.execute(f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '{table}'
          AND column_name = 'inspection_materialization_status'
    """)
    assert cur.fetchone() is None, "마이그레이션 전에 컬럼이 이미 존재함"

    # 마이그레이션 적용
    _run_migration_on_table(cur, table)
    c.commit()

    # 컬럼 존재 확인
    cur.execute(f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = '{table}'
          AND column_name = 'inspection_materialization_status'
    """)
    row = cur.fetchone()
    assert row is not None, "마이그레이션 후 컬럼이 없음"
    col_name, data_type, is_nullable = row
    assert col_name == "inspection_materialization_status"
    assert "text" in data_type.lower(), f"컬럼 타입 오류: {data_type}"
    assert is_nullable == "YES", "컬럼이 NOT NULL — NULL 허용이어야 함"


# ── M02: 반복 실행 안전성 ─────────────────────────────────────────────────────

def test_M02_migration_idempotent(conn):
    """마이그레이션 반복 실행 → 오류 없이 완료 (ADD COLUMN IF NOT EXISTS)."""
    c, cur, table = conn
    # M01 에서 이미 적용됨 — 재실행
    _run_migration_on_table(cur, table)
    c.commit()  # 오류 없으면 성공


# ── M03: 기존 행 NULL 유지 ────────────────────────────────────────────────────

def test_M03_existing_rows_remain_null(conn):
    """마이그레이션 후 기존 행의 inspection_materialization_status = NULL 유지."""
    _, cur, table = conn
    cur.execute(f"""
        SELECT inspection_materialization_status
        FROM {table}
        WHERE source_type = 'saas'
        ORDER BY created_at ASC
        LIMIT 1
    """)
    row = cur.fetchone()
    assert row is not None, "기존 행이 없음"
    assert row[0] is None, f"기존 행이 NULL이 아님: {row[0]}"


# ── M04: PENDING INSERT ───────────────────────────────────────────────────────

def test_M04_pending_insert(conn):
    """PENDING INSERT 정상 저장."""
    c, cur, table = conn
    row_id = str(uuid.uuid4())
    cur.execute(f"""
        INSERT INTO {table} (id, status, source_type, inspection_materialization_status)
        VALUES (%s, 'ACTIVE', 'saas', 'PENDING')
    """, (row_id,))
    c.commit()
    cur.execute(f"SELECT inspection_materialization_status FROM {table} WHERE id = %s", (row_id,))
    assert cur.fetchone()[0] == "PENDING"


# ── M05: MATERIALIZED UPDATE ──────────────────────────────────────────────────

def test_M05_materialized_update(conn):
    """MATERIALIZED UPDATE 정상 저장."""
    c, cur, table = conn
    row_id = str(uuid.uuid4())
    cur.execute(f"""
        INSERT INTO {table} (id, status, source_type, inspection_materialization_status)
        VALUES (%s, 'ACTIVE', 'saas', 'PENDING')
    """, (row_id,))
    cur.execute(f"""
        UPDATE {table}
        SET inspection_materialization_status = 'MATERIALIZED'
        WHERE id = %s
    """, (row_id,))
    c.commit()
    cur.execute(f"SELECT inspection_materialization_status FROM {table} WHERE id = %s", (row_id,))
    assert cur.fetchone()[0] == "MATERIALIZED"


# ── M06: FAILED UPDATE ────────────────────────────────────────────────────────

def test_M06_failed_update(conn):
    """FAILED UPDATE 정상 저장."""
    c, cur, table = conn
    row_id = str(uuid.uuid4())
    cur.execute(f"""
        INSERT INTO {table} (id, status, source_type, inspection_materialization_status)
        VALUES (%s, 'ACTIVE', 'saas', 'PENDING')
    """, (row_id,))
    cur.execute(f"""
        UPDATE {table}
        SET inspection_materialization_status = 'FAILED'
        WHERE id = %s
    """, (row_id,))
    c.commit()
    cur.execute(f"SELECT inspection_materialization_status FROM {table} WHERE id = %s", (row_id,))
    assert cur.fetchone()[0] == "FAILED"


# ── M07: BLOCKED_LEGACY_ROWS UPDATE ──────────────────────────────────────────

def test_M07_blocked_legacy_rows_update(conn):
    """BLOCKED_LEGACY_ROWS UPDATE 정상 저장."""
    c, cur, table = conn
    row_id = str(uuid.uuid4())
    cur.execute(f"""
        INSERT INTO {table} (id, status, source_type, inspection_materialization_status)
        VALUES (%s, 'ACTIVE', 'saas', 'PENDING')
    """, (row_id,))
    cur.execute(f"""
        UPDATE {table}
        SET inspection_materialization_status = 'BLOCKED_LEGACY_ROWS'
        WHERE id = %s
    """, (row_id,))
    c.commit()
    cur.execute(f"SELECT inspection_materialization_status FROM {table} WHERE id = %s", (row_id,))
    assert cur.fetchone()[0] == "BLOCKED_LEGACY_ROWS"


# ── M08: 기존 컬럼 무변경 ─────────────────────────────────────────────────────

def test_M08_existing_columns_unchanged(conn):
    """마이그레이션 후 기존 status/source_type/full_result 컬럼 무변경."""
    _, cur, table = conn
    for col in ("status", "source_type", "full_result"):
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND column_name = '{col}'
        """)
        assert cur.fetchone() is not None, f"기존 컬럼 '{col}' 이 사라짐"
    # 기존 status 값이 손상되지 않았는지 확인
    cur.execute(f"SELECT status FROM {table} WHERE source_type = 'saas' LIMIT 1")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "ACTIVE"
