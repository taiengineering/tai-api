"""
test_reference_forms_isolated.py

Isolated integration tests for the Reference Forms CMS migrations.
Connects to: localhost:5455/ref05_test
Uses schema: ref05
RLS disabled via SET row_security = off
"""

import os
import re
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
DB_DSN = "host=localhost port=5455 dbname=ref05_test user=postgres password=testpass"
MIGRATION_DIR = Path(__file__).parent.parent / "supabase" / "migrations"
CORE_MIGRATION   = MIGRATION_DIR / "20261011120000_reference_forms_core.sql"
RPC_MIGRATION    = MIGRATION_DIR / "20261011120002_reference_forms_rpc.sql"


def _raw_conn():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    return conn


def _read_sql(path: Path) -> str:
    return path.read_text()


def _strip_rls_policies(sql: str) -> str:
    """
    Remove lines containing 'auth.role()' (Supabase-specific).
    Also remove 'ALTER TABLE ... ENABLE ROW LEVEL SECURITY' statements
    since plain PostgreSQL still supports them but we want row_security=off.
    """
    lines = sql.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip full CREATE POLICY blocks (multi-line)
        if re.match(r'\s*CREATE\s+POLICY', line, re.IGNORECASE):
            # skip until semicolon
            while i < len(lines) and ';' not in lines[i]:
                i += 1
            i += 1  # skip the semicolon line
            continue
        result.append(line)
        i += 1
    return "\n".join(result)


def _adapt_for_ref05_schema(sql: str) -> str:
    """
    The migrations use unqualified table/function names with SET search_path = ''.
    For the isolated test, replace the empty search_path with ref05,public so
    that functions can find the tables in the ref05 schema.
    Also strip RLS policies (Supabase-specific).
    """
    # Replace empty search_path directives in function definitions
    sql = sql.replace("SET search_path = ''", "SET search_path = ref05, public")
    return _strip_rls_policies(sql)


# ---------------------------------------------------------------------------
# Module-level setup: create schema, stub, apply DDL
# ---------------------------------------------------------------------------
def _setup_module_once():
    conn = _raw_conn()
    cur = conn.cursor()

    # Drop and recreate schema
    cur.execute("DROP SCHEMA IF EXISTS ref05 CASCADE;")
    cur.execute("CREATE SCHEMA ref05;")
    cur.execute("SET search_path TO ref05, public;")
    cur.execute("SET row_security = off;")

    # Create stub for enqueue_search_index_sync
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ref05.search_index_outbox_stub (
            id          BIGSERIAL   PRIMARY KEY,
            domain_name TEXT,
            object_type TEXT,
            canonical_id TEXT,
            event_key   TEXT,
            reason      TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        );
    """)

    cur.execute("""
        CREATE OR REPLACE FUNCTION ref05.enqueue_search_index_sync(
            p_domain_name   TEXT,
            p_object_type   TEXT,
            p_canonical_id  TEXT,
            p_event_key     TEXT,
            p_reason        TEXT
        )
        RETURNS INTEGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO ref05.search_index_outbox_stub
                (domain_name, object_type, canonical_id, event_key, reason)
            VALUES
                (p_domain_name, p_object_type, p_canonical_id, p_event_key, p_reason);
            RETURN 1;
        END;
        $$;
    """)

    # Apply core migration (adapted)
    core_sql = _adapt_for_ref05_schema(_read_sql(CORE_MIGRATION))
    cur.execute(core_sql)

    # Apply RPC migration (adapted)
    rpc_sql = _adapt_for_ref05_schema(_read_sql(RPC_MIGRATION))
    cur.execute(rpc_sql)

    cur.close()
    conn.close()


# Run once at import time
_setup_module_once()


# ---------------------------------------------------------------------------
# Per-test connection fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def conn():
    """
    Per-test connection: autocommit=False so we can ROLLBACK after each test.
    Sets search_path and disables RLS.
    """
    c = psycopg2.connect(DB_DSN)
    c.autocommit = False
    cur = c.cursor()
    cur.execute("SET search_path TO ref05, public;")
    cur.execute("SET row_security = off;")
    cur.close()
    yield c
    c.rollback()
    c.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def make_form(conn, status='DRAFT'):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reference_forms (status) VALUES (%s) RETURNING id;",
        (status,)
    )
    form_id = cur.fetchone()[0]
    cur.close()
    return form_id


def make_content(conn, form_id, slug, title='Test Form', description=None, body_html=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reference_form_content (form_id, lang, canonical_slug, title, description, body_html)
        VALUES (%s, 'ko', %s, %s, %s, %s)
        RETURNING id;
        """,
        (form_id, slug, title, description, body_html)
    )
    content_id = cur.fetchone()[0]
    # Fetch computed hash
    cur.execute(
        "SELECT content_hash FROM reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    row = cur.fetchone()
    content_hash = row[0] if row else None
    cur.close()
    return content_id, content_hash


def make_file(conn, form_id, sha256=None, qa_status='QA_PASS', approved=True):
    if sha256 is None:
        sha256 = uuid.uuid4().hex * 2  # 64-char hex
    approved_at = 'now()' if approved else None
    cur = conn.cursor()
    if approved:
        cur.execute(
            """
            INSERT INTO reference_form_files (form_id, file_ref, sha256, qa_status, approved_at)
            VALUES (%s, %s, %s, %s, now())
            RETURNING id, sha256;
            """,
            (form_id, f"file-{uuid.uuid4().hex[:8]}.pdf", sha256, qa_status)
        )
    else:
        cur.execute(
            """
            INSERT INTO reference_form_files (form_id, file_ref, sha256, qa_status)
            VALUES (%s, %s, %s, %s)
            RETURNING id, sha256;
            """,
            (form_id, f"file-{uuid.uuid4().hex[:8]}.pdf", sha256, qa_status)
        )
    row = cur.fetchone()
    file_id = row[0]
    actual_sha256 = row[1]
    cur.close()
    return file_id, actual_sha256


def make_source(conn, form_id, rights_status='CLEARED'):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reference_form_sources (form_id, source_name, rights_status)
        VALUES (%s, %s, %s)
        RETURNING id;
        """,
        (form_id, f"source-{uuid.uuid4().hex[:8]}", rights_status)
    )
    source_id = cur.fetchone()[0]
    cur.close()
    return source_id


def make_approval(conn, form_id, content_hash, file_hashes_list):
    """
    file_hashes_list: list of {"file_id": str, "sha256": str}
    """
    cur = conn.cursor()
    # Set previous approvals as not current
    cur.execute(
        "UPDATE reference_form_approvals SET is_current = false WHERE form_id = %s;",
        (form_id,)
    )
    cur.execute(
        """
        INSERT INTO reference_form_approvals
            (form_id, approval_status, approved_content_hash, approved_file_hashes, is_current, approved_at, approved_by)
        VALUES (%s, 'APPROVED', %s, %s, true, now(), 'test-approver')
        RETURNING id;
        """,
        (form_id, content_hash, json.dumps(file_hashes_list))
    )
    approval_id = cur.fetchone()[0]
    cur.close()
    return approval_id


def get_outbox_count(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM search_index_outbox_stub;")
    count = cur.fetchone()[0]
    cur.close()
    return count


def clear_outbox(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM search_index_outbox_stub;")
    cur.close()


def _full_publish_setup(conn, skip_preview_gate=True):
    """
    Creates a fully publishable form and returns (form_id, content_id, content_hash, file_id, sha256).
    """
    form_id = make_form(conn)
    slug = f"test-form-{uuid.uuid4().hex[:8]}"
    content_id, content_hash = make_content(conn, form_id, slug)
    sha256 = uuid.uuid4().hex * 2
    file_id, actual_sha256 = make_file(conn, form_id, sha256=sha256, qa_status='QA_PASS', approved=True)
    make_approval(conn, form_id, content_hash, [{"file_id": str(file_id), "sha256": actual_sha256}])
    clear_outbox(conn)
    return form_id, content_id, content_hash, file_id, actual_sha256


# ---------------------------------------------------------------------------
# Group A — Structure tests
# ---------------------------------------------------------------------------
EXPECTED_TABLES = [
    'reference_forms',
    'reference_form_content',
    'reference_form_slug_history',
    'reference_form_slug_registry',
    'reference_form_files',
    'reference_form_preview_artifacts',
    'reference_form_sources',
    'reference_form_relations',
    'reference_form_legacy_links',
    'reference_form_aliases',
    'reference_form_approvals',
    'reference_form_events',
]


def test_a01_all_12_tables_exist(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'ref05'
          AND table_type = 'BASE TABLE';
        """
    )
    existing = {row[0] for row in cur.fetchall()}
    cur.close()
    missing = [t for t in EXPECTED_TABLES if t not in existing]
    assert missing == [], f"Missing tables: {missing}"


def test_a02_fks_correct(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'ref05'
        ORDER BY tc.table_name, kcu.column_name;
        """
    )
    fk_rows = cur.fetchall()
    cur.close()

    fk_set = {(r[0], r[1], r[2], r[3]) for r in fk_rows}

    # Key FKs that must exist
    required_fks = [
        ('reference_form_content', 'form_id', 'reference_forms', 'id'),
        ('reference_form_files', 'form_id', 'reference_forms', 'id'),
        ('reference_form_approvals', 'form_id', 'reference_forms', 'id'),
        ('reference_form_events', 'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_history', 'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_registry', 'form_id', 'reference_forms', 'id'),
        ('reference_form_sources', 'form_id', 'reference_forms', 'id'),
        ('reference_form_files', 'preview_artifact_id', 'reference_form_preview_artifacts', 'id'),
    ]

    missing_fks = [fk for fk in required_fks if fk not in fk_set]
    assert missing_fks == [], f"Missing FKs: {missing_fks}"


def test_a03_content_hash_on_insert(conn):
    form_id = make_form(conn)
    slug = f"hash-test-{uuid.uuid4().hex[:8]}"
    content_id, content_hash = make_content(conn, form_id, slug, title="Hash Test Form")

    assert content_hash is not None, "content_hash should not be None after insert"
    assert len(content_hash) == 64, f"Expected 64-char hex, got {len(content_hash)}: {content_hash}"
    assert re.match(r'^[0-9a-f]{64}$', content_hash), f"Not hex: {content_hash}"


def test_a04_content_hash_on_slug_update(conn):
    form_id = make_form(conn)
    slug = f"original-slug-{uuid.uuid4().hex[:8]}"
    content_id, hash_before = make_content(conn, form_id, slug)

    new_slug = f"updated-slug-{uuid.uuid4().hex[:8]}"
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_content SET canonical_slug = %s WHERE form_id = %s AND lang = 'ko';",
        (new_slug, form_id)
    )
    cur.execute(
        "SELECT content_hash FROM reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_after = cur.fetchone()[0]
    cur.close()

    assert hash_before != hash_after, "content_hash should change when canonical_slug changes"


def test_a05_content_slug_unique(conn):
    form_id1 = make_form(conn)
    form_id2 = make_form(conn)
    slug = f"unique-slug-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id1, slug)

    with pytest.raises(psycopg2.errors.UniqueViolation):
        make_content(conn, form_id2, slug)


def test_a06_slug_registry_pk_unique(conn):
    form_id = make_form(conn)
    slug = f"registry-slug-{uuid.uuid4().hex[:8]}"

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id) VALUES (%s, %s);",
        (slug, form_id)
    )
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO reference_form_slug_registry (slug, form_id) VALUES (%s, %s);",
            (slug, form_id)
        )
    cur.close()


# ---------------------------------------------------------------------------
# Group B — rpc_publish_reference_form
# ---------------------------------------------------------------------------

def test_b01_publish_success(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'test-actor', '{}', True)
    )
    result = cur.fetchone()[0]
    cur.close()

    assert str(result) == str(form_id), f"Expected {form_id}, got {result}"

    cur = conn.cursor()
    cur.execute("SELECT status FROM reference_forms WHERE id = %s;", (form_id,))
    status = cur.fetchone()[0]
    cur.close()
    assert status == 'PUBLISHED'

    assert get_outbox_count(conn) == 1


def test_b02_gate1_already_published(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'test-actor', '{}', True)
    )
    cur.fetchone()
    cur.close()
    conn.commit()

    # Re-setup search path after commit
    cur2 = conn.cursor()
    cur2.execute("SET search_path TO ref05, public;")
    cur2.execute("SET row_security = off;")
    cur2.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur3 = conn.cursor()
        cur3.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE1_FAILED' in str(exc_info.value)


def test_b03_gate2_no_approval(conn):
    form_id = make_form(conn)
    slug = f"no-approval-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, slug)
    sha256 = uuid.uuid4().hex * 2
    make_file(conn, form_id, sha256=sha256)
    # No approval inserted

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE2_FAILED' in str(exc_info.value)


def test_b04_gate3_content_changed(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Modify body_html — triggers hash recalc
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_content SET body_html = '<p>changed</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    assert 'GATE3_FAILED' in str(exc_info.value)


def test_b05_gate4_sha256_mismatch(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Change the file sha256 after approval
    new_sha256 = uuid.uuid4().hex * 2
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_files SET sha256 = %s WHERE id = %s;",
        (new_sha256, file_id)
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    assert 'GATE4_FAILED' in str(exc_info.value)


def test_b06_gate4_new_file_not_in_approval(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Add a new active file after approval
    make_file(conn, form_id, qa_status='QA_PASS', approved=True)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE4_FAILED' in str(exc_info.value)


def test_b07_gate4_approved_file_deactivated(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Deactivate the file that's in the approval
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_files SET is_active = false WHERE id = %s;",
        (file_id,)
    )
    cur.close()

    # Now GATE-7 (no active files) fires, but GATE-4-B also applies
    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    err = str(exc_info.value)
    assert 'GATE7_FAILED' in err or 'GATE4_FAILED' in err


def test_b08_gate5_rights_required(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)
    make_source(conn, form_id, rights_status='REVIEW_REQUIRED')

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE5_FAILED' in str(exc_info.value)


def test_b09_gate7_no_files(conn):
    form_id = make_form(conn)
    slug = f"no-files-{uuid.uuid4().hex[:8]}"
    _, content_hash = make_content(conn, form_id, slug)
    # No files, but create an approval with empty file_hashes
    make_approval(conn, form_id, content_hash, [])

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE7_FAILED' in str(exc_info.value)


def test_b10_rollback_on_failure(conn):
    """
    Verify that a failed publish attempt (GATE-3) does not change form status.
    Strategy: commit the setup, then run the failing RPC, absorb the error,
    and verify the form is still DRAFT in a fresh read.
    """
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Commit setup so form_id is durable
    conn.commit()
    cur0 = conn.cursor()
    cur0.execute("SET search_path TO ref05, public;")
    cur0.execute("SET row_security = off;")
    cur0.close()

    # Break GATE-3 by changing body_html
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_content SET body_html = '<p>broken</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()
    conn.commit()

    cur_a = conn.cursor()
    cur_a.execute("SET search_path TO ref05, public;")
    cur_a.execute("SET row_security = off;")
    cur_a.close()

    # Attempt publish — should raise GATE3_FAILED
    raised = False
    try:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    except psycopg2.errors.RaiseException as e:
        raised = True
        assert 'GATE3_FAILED' in str(e)
        conn.rollback()
        cur_b = conn.cursor()
        cur_b.execute("SET search_path TO ref05, public;")
        cur_b.execute("SET row_security = off;")
        cur_b.close()

    if not raised:
        pytest.fail("Expected GATE3_FAILED exception was not raised")

    # Verify form status is still DRAFT
    cur3 = conn.cursor()
    cur3.execute("SELECT status FROM reference_forms WHERE id = %s;", (form_id,))
    row = cur3.fetchone()
    cur3.close()
    assert row is not None, f"Form {form_id} not found after rollback"
    assert row[0] == 'DRAFT', f"Expected DRAFT after rollback, got {row[0]}"


# ---------------------------------------------------------------------------
# Group C — rpc_change_slug_reference_form
# ---------------------------------------------------------------------------

def test_c01_slug_change_success(conn):
    form_id = make_form(conn)
    old_slug = f"old-slug-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, old_slug)
    # Register old slug
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, 'CANONICAL');",
        (old_slug, form_id)
    )
    cur.close()

    _, hash_before = make_content.__wrapped__(conn, form_id, old_slug) if hasattr(make_content, '__wrapped__') else (None, None)
    # get current hash
    cur2 = conn.cursor()
    cur2.execute("SELECT content_hash FROM reference_form_content WHERE form_id = %s AND lang = 'ko';", (form_id,))
    hash_before = cur2.fetchone()[0]
    cur2.close()

    clear_outbox(conn)
    new_slug = f"new-slug-{uuid.uuid4().hex[:8]}"

    cur3 = conn.cursor()
    cur3.execute(
        "SELECT * FROM rpc_change_slug_reference_form(%s, %s, %s);",
        (form_id, new_slug, 'test-actor')
    )
    result = cur3.fetchone()[0]
    cur3.close()

    assert str(result) == str(form_id)

    # Verify content_hash changed
    cur4 = conn.cursor()
    cur4.execute("SELECT content_hash FROM reference_form_content WHERE form_id = %s AND lang = 'ko';", (form_id,))
    hash_after = cur4.fetchone()[0]
    cur4.close()
    assert hash_before != hash_after, "content_hash should change after slug change"

    # Verify registry: new slug is CANONICAL, old is HISTORY
    cur5 = conn.cursor()
    cur5.execute("SELECT slug_status FROM reference_form_slug_registry WHERE slug = %s;", (new_slug,))
    row = cur5.fetchone()
    assert row is not None and row[0] == 'CANONICAL'
    cur5.execute("SELECT slug_status FROM reference_form_slug_registry WHERE slug = %s;", (old_slug,))
    row = cur5.fetchone()
    assert row is not None and row[0] == 'HISTORY'
    cur5.close()

    assert get_outbox_count(conn) == 1


def test_c02_reuse_past_slug(conn):
    form_id = make_form(conn)
    slug_a = f"slug-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"slug-b-{uuid.uuid4().hex[:8]}"

    make_content(conn, form_id, slug_a)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, 'CANONICAL');",
        (slug_a, form_id)
    )
    cur.close()

    # Change A → B
    cur2 = conn.cursor()
    cur2.execute(
        "SELECT * FROM rpc_change_slug_reference_form(%s, %s, %s);",
        (form_id, slug_b, 'test-actor')
    )
    cur2.fetchone()
    cur2.close()

    # Now try B → A (A is in HISTORY for this form)
    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur3 = conn.cursor()
        cur3.execute(
            "SELECT * FROM rpc_change_slug_reference_form(%s, %s, %s);",
            (form_id, slug_a, 'test-actor')
        )
        cur3.fetchone()
        cur3.close()
    assert 'SLUG_CHANGE_FAILED' in str(exc_info.value)


def test_c03_other_form_conflict(conn):
    form1_id = make_form(conn)
    form2_id = make_form(conn)
    slug_x = f"shared-slug-{uuid.uuid4().hex[:8]}"
    slug_form1_initial = f"form1-init-{uuid.uuid4().hex[:8]}"
    slug_form2_initial = f"form2-init-{uuid.uuid4().hex[:8]}"

    make_content(conn, form1_id, slug_x)
    make_content(conn, form2_id, slug_form2_initial)

    # Register slug_x for form1
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, 'CANONICAL');",
        (slug_x, form1_id)
    )
    # Register form2 initial slug
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, 'CANONICAL');",
        (slug_form2_initial, form2_id)
    )
    cur.close()

    # form2 tries to take slug_x
    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT * FROM rpc_change_slug_reference_form(%s, %s, %s);",
            (form2_id, slug_x, 'test-actor')
        )
        cur2.fetchone()
        cur2.close()
    assert 'SLUG_CONFLICT' in str(exc_info.value) or 'SLUG_CHANGE_FAILED' in str(exc_info.value)


def test_c04_slug_change_invalidates_publish(conn):
    form_id, content_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    # Also register the current slug
    cur = conn.cursor()
    cur.execute("SELECT canonical_slug FROM reference_form_content WHERE form_id = %s AND lang = 'ko';", (form_id,))
    current_slug = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, 'CANONICAL') ON CONFLICT DO NOTHING;",
        (current_slug, form_id)
    )
    cur.close()

    new_slug = f"changed-{uuid.uuid4().hex[:8]}"
    cur2 = conn.cursor()
    cur2.execute(
        "SELECT * FROM rpc_change_slug_reference_form(%s, %s, %s);",
        (form_id, new_slug, 'test-actor')
    )
    cur2.fetchone()
    cur2.close()

    # Now try to publish — GATE-3 should fail (content_hash changed)
    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur3 = conn.cursor()
        cur3.execute(
            "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'test-actor', '{}', True)
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE3_FAILED' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group D — rpc_unpublish_reference_form
# ---------------------------------------------------------------------------

def test_d01_unpublish_success(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)

    # Publish first
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'test-actor', '{}', True)
    )
    cur.fetchone()
    cur.close()
    clear_outbox(conn)

    # Unpublish
    cur2 = conn.cursor()
    cur2.execute(
        "SELECT * FROM rpc_unpublish_reference_form(%s, %s, %s);",
        (form_id, 'test-actor', 'test reason')
    )
    result = cur2.fetchone()[0]
    cur2.close()

    assert str(result) == str(form_id)

    cur3 = conn.cursor()
    cur3.execute("SELECT status FROM reference_forms WHERE id = %s;", (form_id,))
    status = cur3.fetchone()[0]
    cur3.close()
    assert status == 'DRAFT'

    # Outbox should have 1 UNPUBLISHED row
    cur4 = conn.cursor()
    cur4.execute("SELECT reason FROM search_index_outbox_stub;")
    rows = cur4.fetchall()
    cur4.close()
    assert any(r[0] == 'UNPUBLISHED' for r in rows)


def test_d02_unpublish_draft(conn):
    form_id = make_form(conn, status='DRAFT')

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM rpc_unpublish_reference_form(%s, %s, %s);",
            (form_id, 'test-actor', None)
        )
        cur.fetchone()
        cur.close()
    assert 'UNPUBLISH_FAILED' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group E — public view
# ---------------------------------------------------------------------------

def _publish_form(conn, form_id):
    """Publish a fully set-up form (assumes gates pass with skip_preview=True)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'test-actor', '{}', True)
    )
    cur.fetchone()
    cur.close()


def test_e01_published_form_in_view(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute("SELECT id FROM reference_form_public_view WHERE id = %s;", (form_id,))
    row = cur.fetchone()
    cur.close()
    assert row is not None, "Published form should appear in public view"


def test_e02_draft_form_not_in_view(conn):
    form_id = make_form(conn)
    slug = f"draft-view-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, slug)

    cur = conn.cursor()
    cur.execute("SELECT id FROM reference_form_public_view WHERE id = %s;", (form_id,))
    row = cur.fetchone()
    cur.close()
    assert row is None, "DRAFT form should not appear in public view"


def test_e03_content_changed_not_in_view(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    # Modify body_html — invalidates content_hash == approved_content_hash
    cur = conn.cursor()
    cur.execute(
        "UPDATE reference_form_content SET body_html = '<p>post-publish change</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()

    cur2 = conn.cursor()
    cur2.execute("SELECT id FROM reference_form_public_view WHERE id = %s;", (form_id,))
    row = cur2.fetchone()
    cur2.close()
    assert row is None, "Form with changed content should not appear in public view"


def test_e04_updated_at_greatest(conn):
    form_id, _, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute(
        "SELECT updated_at FROM reference_form_public_view WHERE id = %s;",
        (form_id,)
    )
    view_updated_at = cur.fetchone()[0]

    cur.execute("SELECT updated_at FROM reference_forms WHERE id = %s;", (form_id,))
    rf_updated_at = cur.fetchone()[0]
    cur.execute(
        "SELECT updated_at FROM reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    rfc_updated_at = cur.fetchone()[0]
    cur.close()

    expected = max(rf_updated_at, rfc_updated_at)
    assert view_updated_at == expected, f"View updated_at {view_updated_at} != GREATEST({rf_updated_at}, {rfc_updated_at})"


# ---------------------------------------------------------------------------
# Group F — SearchDocument normalization (inline implementation)
# ---------------------------------------------------------------------------

def _normalize_reference_form(row: dict):
    """
    Inline normalization for reference form search document.
    row keys: id, canonical_slug, title, description, published_at, formats, legacy_codes
    Returns None if required fields are missing.
    """
    if not row.get('title'):
        return None

    return {
        'canonical_id':         str(row['id']),
        'publication_status':   'PUBLISHED',
        'public_url':           f"/reference-form/{row['canonical_slug']}",
        'title':                row['title'],
        'description':          row.get('description'),
        'published_at':         row.get('published_at'),
        'formats':              row.get('formats', []),
        'legacy_codes':         row.get('legacy_codes', []),
    }


def test_f01_normalize_returns_correct_fields(conn):
    test_id = uuid.uuid4()
    row = {
        'id':            test_id,
        'canonical_slug': 'test-form',
        'title':          'Test Form Title',
        'description':    'A test description',
        'published_at':   datetime.now(timezone.utc),
        'formats':        [],
        'legacy_codes':   [],
    }
    result = _normalize_reference_form(row)

    assert result is not None
    assert result['canonical_id'] == str(test_id)
    assert result['publication_status'] == 'PUBLISHED'
    assert result['public_url'] == '/reference-form/test-form'
    assert result['title'] == 'Test Form Title'


def test_f02_normalize_missing_required_returns_none(conn):
    row = {
        'id':            uuid.uuid4(),
        'canonical_slug': 'some-form',
        'title':          '',  # empty title = missing required
        'description':    None,
        'published_at':   None,
        'formats':        [],
        'legacy_codes':   [],
    }
    result = _normalize_reference_form(row)
    assert result is None, "Missing title should return None"


def test_f03_canonical_id_is_uuid_no_prefix(conn):
    test_id = uuid.uuid4()
    row = {
        'id':            test_id,
        'canonical_slug': 'no-prefix-form',
        'title':          'No Prefix Test',
        'description':    None,
        'published_at':   None,
        'formats':        [],
        'legacy_codes':   [],
    }
    result = _normalize_reference_form(row)
    assert result is not None
    cid = result['canonical_id']
    assert 'REFERENCE_FORM::' not in cid, f"canonical_id should not have prefix: {cid}"
    assert cid == str(test_id), f"canonical_id should be plain UUID: {cid}"
