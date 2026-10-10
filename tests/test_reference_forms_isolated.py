"""
test_reference_forms_isolated.py

Isolated integration tests for the Reference Forms CMS migrations.
Connects to: localhost:5455/ref05_test (ext-sql-final-pg Docker)
Schema: public  (matches production — no search_path substitution)
pgcrypto: extensions schema (matches Supabase production)
auth.role(): stubbed to return 'service_role'
RLS disabled per-session via SET row_security = off
"""

import uuid
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

# ---------------------------------------------------------------------------
# Connection / migration paths
# ---------------------------------------------------------------------------
DB_DSN = "host=localhost port=5455 dbname=ref05_test user=postgres password=testpass"
MIGRATION_DIR = Path(__file__).parent.parent / "supabase" / "migrations"
CORE_MIGRATION = MIGRATION_DIR / "20261011120000_reference_forms_core.sql"
RPC_MIGRATION  = MIGRATION_DIR / "20261011120002_reference_forms_rpc.sql"


def _raw_conn():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# Module-level setup: apply migrations to public schema, no SQL rewriting
# ---------------------------------------------------------------------------
def _setup_module_once():
    conn = _raw_conn()
    cur = conn.cursor()

    # 1. extensions schema + pgcrypto (matches Supabase production layout)
    # If pgcrypto is already installed in public (plain PG default), create a
    # wrapper so extensions.digest() resolves — matching Supabase's layout.
    cur.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")  # installs to public if not present
    cur.execute("""
        CREATE OR REPLACE FUNCTION extensions.digest(data TEXT, algorithm TEXT)
        RETURNS BYTEA LANGUAGE sql STRICT IMMUTABLE AS $$
            SELECT public.digest(data, algorithm);
        $$;
    """)
    cur.execute("""
        CREATE OR REPLACE FUNCTION extensions.digest(data BYTEA, algorithm TEXT)
        RETURNS BYTEA LANGUAGE sql STRICT IMMUTABLE AS $$
            SELECT public.digest(data, algorithm);
        $$;
    """)

    # 2. auth schema + auth.role() stub (Supabase built-in, not present in plain PG)
    cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
    cur.execute("""
        CREATE OR REPLACE FUNCTION auth.role()
        RETURNS TEXT LANGUAGE sql STABLE AS $$
            SELECT 'service_role'::TEXT;
        $$;
    """)

    # 3. Drop existing reference form objects so migration is idempotent
    cur.execute("""
        DROP VIEW   IF EXISTS public.reference_form_public_view CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_publish_reference_form(UUID,TEXT,JSONB,BOOLEAN) CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_unpublish_reference_form(UUID,TEXT,TEXT) CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_change_slug_reference_form(UUID,TEXT,TEXT) CASCADE;
        DROP FUNCTION IF EXISTS public.fn_assert_slug_globally_unique(TEXT,UUID) CASCADE;
        DROP FUNCTION IF EXISTS public.fn_reference_form_content_hash() CASCADE;
        DROP FUNCTION IF EXISTS public.fn_reference_forms_set_updated_at() CASCADE;
        DROP TABLE IF EXISTS public.reference_form_events          CASCADE;
        DROP TABLE IF EXISTS public.reference_form_approvals       CASCADE;
        DROP TABLE IF EXISTS public.reference_form_aliases         CASCADE;
        DROP TABLE IF EXISTS public.reference_form_legacy_links    CASCADE;
        DROP TABLE IF EXISTS public.reference_form_relations       CASCADE;
        DROP TABLE IF EXISTS public.reference_form_sources         CASCADE;
        DROP TABLE IF EXISTS public.reference_form_preview_artifacts CASCADE;
        DROP TABLE IF EXISTS public.reference_form_files           CASCADE;
        DROP TABLE IF EXISTS public.reference_form_slug_registry   CASCADE;
        DROP TABLE IF EXISTS public.reference_form_slug_history    CASCADE;
        DROP TABLE IF EXISTS public.reference_form_content         CASCADE;
        DROP TABLE IF EXISTS public.reference_forms                CASCADE;
    """)

    # 4. Outbox stub (replaces real search_index_outbox for isolated tests)
    cur.execute("""
        DROP TABLE IF EXISTS public.search_index_outbox_stub CASCADE;
        CREATE TABLE public.search_index_outbox_stub (
            id           BIGSERIAL   PRIMARY KEY,
            domain_name  TEXT,
            object_type  TEXT,
            canonical_id TEXT,
            event_key    TEXT,
            reason       TEXT,
            created_at   TIMESTAMPTZ DEFAULT now()
        );
    """)
    cur.execute("""
        DROP FUNCTION IF EXISTS public.enqueue_search_index_sync(TEXT,TEXT,TEXT,TEXT,TEXT) CASCADE;
        CREATE FUNCTION public.enqueue_search_index_sync(
            p_domain_name  TEXT,
            p_object_type  TEXT,
            p_canonical_id TEXT,
            p_event_key    TEXT,
            p_reason       TEXT DEFAULT NULL
        )
        RETURNS BIGINT LANGUAGE plpgsql AS $$
        DECLARE v_id BIGINT;
        BEGIN
            INSERT INTO public.search_index_outbox_stub
                (domain_name, object_type, canonical_id, event_key, reason)
            VALUES (p_domain_name, p_object_type, p_canonical_id, p_event_key, p_reason)
            RETURNING id INTO v_id;
            RETURN v_id;
        END;
        $$;
    """)

    # 5. Apply migrations directly — no SQL rewriting
    cur.execute(CORE_MIGRATION.read_text())
    cur.execute(RPC_MIGRATION.read_text())

    cur.close()
    conn.close()


_setup_module_once()


# ---------------------------------------------------------------------------
# Per-test fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def conn():
    c = psycopg2.connect(DB_DSN)
    c.autocommit = False
    cur = c.cursor()
    cur.execute("SET row_security = off;")
    cur.close()
    yield c
    c.rollback()
    c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_form(conn, status='DRAFT'):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.reference_forms (status) VALUES (%s) RETURNING id;",
        (status,)
    )
    form_id = cur.fetchone()[0]
    cur.close()
    return form_id


def make_content(conn, form_id, slug, title='Test Form', description=None, body_html=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO public.reference_form_content
            (form_id, lang, canonical_slug, title, description, body_html)
        VALUES (%s, 'ko', %s, %s, %s, %s)
        RETURNING id;
        """,
        (form_id, slug, title, description, body_html)
    )
    cur.fetchone()
    cur.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    content_hash = cur.fetchone()[0]
    cur.close()
    return content_hash


def make_file(conn, form_id, sha256=None, qa_status='QA_PASS', approved=True):
    if sha256 is None:
        sha256 = uuid.uuid4().hex * 2
    cur = conn.cursor()
    if approved:
        cur.execute(
            """
            INSERT INTO public.reference_form_files
                (form_id, file_ref, sha256, qa_status, approved_at)
            VALUES (%s, %s, %s, %s, now())
            RETURNING id, sha256;
            """,
            (form_id, f"reference-forms/{uuid.uuid4().hex[:8]}.pdf", sha256, qa_status)
        )
    else:
        cur.execute(
            """
            INSERT INTO public.reference_form_files
                (form_id, file_ref, sha256, qa_status)
            VALUES (%s, %s, %s, %s)
            RETURNING id, sha256;
            """,
            (form_id, f"reference-forms/{uuid.uuid4().hex[:8]}.pdf", sha256, qa_status)
        )
    row = cur.fetchone()
    cur.close()
    return row[0], row[1]  # file_id, sha256


def make_source(conn, form_id, rights_status='CLEARED'):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO public.reference_form_sources (form_id, source_name, rights_status)
        VALUES (%s, %s, %s) RETURNING id;
        """,
        (form_id, f"src-{uuid.uuid4().hex[:8]}", rights_status)
    )
    source_id = cur.fetchone()[0]
    cur.close()
    return source_id


def make_approval(conn, form_id, content_hash, file_hashes_list):
    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_approvals SET is_current = false WHERE form_id = %s;",
        (form_id,)
    )
    cur.execute(
        """
        INSERT INTO public.reference_form_approvals
            (form_id, approval_status, approved_content_hash,
             approved_file_hashes, is_current, approved_at, approved_by)
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
    cur.execute("SELECT COUNT(*) FROM public.search_index_outbox_stub;")
    n = cur.fetchone()[0]
    cur.close()
    return n


def clear_outbox(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM public.search_index_outbox_stub;")
    cur.close()


def _full_publish_setup(conn):
    """Creates a fully publishable form (no preview artifact — call with skip_preview_gate=True)."""
    form_id = make_form(conn)
    slug = f"test-form-{uuid.uuid4().hex[:8]}"
    content_hash = make_content(conn, form_id, slug)
    sha256 = uuid.uuid4().hex * 2
    file_id, actual_sha256 = make_file(conn, form_id, sha256=sha256)
    make_approval(conn, form_id, content_hash, [{"file_id": str(file_id), "sha256": actual_sha256}])
    clear_outbox(conn)
    return form_id, content_hash, file_id, actual_sha256


# ---------------------------------------------------------------------------
# Group A — Structure
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
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
          AND table_name LIKE 'reference_form%';
        """
    )
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    missing = [t for t in EXPECTED_TABLES if t not in existing]
    assert missing == [], f"Missing tables: {missing}"


def test_a02_fks_correct(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tc.table_name, kcu.column_name,
               ccu.table_name AS foreign_table, ccu.column_name AS foreign_col
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name LIKE 'reference_form%';
        """
    )
    fk_set = {(r[0], r[1], r[2], r[3]) for r in cur.fetchall()}
    cur.close()

    required = [
        ('reference_form_content',  'form_id', 'reference_forms', 'id'),
        ('reference_form_files',    'form_id', 'reference_forms', 'id'),
        ('reference_form_approvals','form_id', 'reference_forms', 'id'),
        ('reference_form_events',   'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_history',   'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_registry',  'form_id', 'reference_forms', 'id'),
        ('reference_form_sources',  'form_id', 'reference_forms', 'id'),
        ('reference_form_files', 'preview_artifact_id',
         'reference_form_preview_artifacts', 'id'),
    ]
    missing = [fk for fk in required if fk not in fk_set]
    assert missing == [], f"Missing FKs: {missing}"


def test_a03_content_hash_on_insert(conn):
    form_id = make_form(conn)
    slug = f"hash-test-{uuid.uuid4().hex[:8]}"
    content_hash = make_content(conn, form_id, slug, title="Hash Test Form")

    assert content_hash is not None
    assert len(content_hash) == 64, f"Expected 64-char hex, got {len(content_hash)}"
    assert re.match(r'^[0-9a-f]{64}$', content_hash), f"Not hex: {content_hash}"


def test_a04_content_hash_on_slug_update(conn):
    form_id = make_form(conn)
    slug = f"orig-slug-{uuid.uuid4().hex[:8]}"
    hash_before = make_content(conn, form_id, slug)

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_content SET canonical_slug = %s WHERE form_id = %s AND lang = 'ko';",
        (f"updated-slug-{uuid.uuid4().hex[:8]}", form_id)
    )
    cur.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_after = cur.fetchone()[0]
    cur.close()

    assert hash_before != hash_after


def test_a05_content_slug_unique(conn):
    form_id1 = make_form(conn)
    form_id2 = make_form(conn)
    slug = f"unique-slug-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id1, slug)

    with pytest.raises(psycopg2.errors.UniqueViolation):
        make_content(conn, form_id2, slug)


def test_a06_slug_registry_pk_unique(conn):
    form_id = make_form(conn)
    slug = f"reg-slug-{uuid.uuid4().hex[:8]}"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.reference_form_slug_registry (slug, form_id) VALUES (%s, %s);",
        (slug, form_id)
    )
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO public.reference_form_slug_registry (slug, form_id) VALUES (%s, %s);",
            (slug, form_id)
        )
    cur.close()


# ---------------------------------------------------------------------------
# Group B — rpc_publish_reference_form
# ---------------------------------------------------------------------------

def test_b01_publish_success(conn):
    form_id, _, _, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'actor', '{}', True)
    )
    result = cur.fetchone()[0]
    cur.close()
    assert str(result) == str(form_id)

    cur = conn.cursor()
    cur.execute("SELECT status FROM public.reference_forms WHERE id = %s;", (form_id,))
    assert cur.fetchone()[0] == 'PUBLISHED'
    cur.close()
    assert get_outbox_count(conn) == 1


def test_b02_gate1_already_published(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'actor', '{}', True)
    )
    cur.fetchone()
    cur.close()
    conn.commit()

    cur2 = conn.cursor()
    cur2.execute("SET row_security = off;")
    cur2.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur3 = conn.cursor()
        cur3.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE1_FAILED' in str(exc_info.value)


def test_b03_gate2_no_approval(conn):
    form_id = make_form(conn)
    slug = f"no-appr-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, slug)
    make_file(conn, form_id)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE2_FAILED' in str(exc_info.value)


def test_b04_gate3_content_changed(conn):
    form_id, _, _, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_content SET body_html = '<p>changed</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    assert 'GATE3_FAILED' in str(exc_info.value)


def test_b05_gate4_sha256_mismatch(conn):
    form_id, _, file_id, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_files SET sha256 = %s WHERE id = %s;",
        (uuid.uuid4().hex * 2, file_id)
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    assert 'GATE4_FAILED' in str(exc_info.value)


def test_b06_gate4_new_file_not_in_approval(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    make_file(conn, form_id, qa_status='QA_PASS', approved=True)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE4_FAILED' in str(exc_info.value)


def test_b07_gate4_approved_file_deactivated(conn):
    form_id, _, file_id, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_files SET is_active = false WHERE id = %s;",
        (file_id,)
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    err = str(exc_info.value)
    assert 'GATE7_FAILED' in err or 'GATE4_FAILED' in err


def test_b08_gate5_rights_required(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    make_source(conn, form_id, rights_status='REVIEW_REQUIRED')

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE5_FAILED' in str(exc_info.value)


def test_b09_gate6_no_preview_artifact(conn):
    """GATE-6 fires when p_skip_preview_gate=false and no preview artifact exists."""
    form_id, _, _, _ = _full_publish_setup(conn)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', False)  # skip=False → GATE-6 enforced
        )
        cur.fetchone()
        cur.close()
    assert 'GATE6_FAILED' in str(exc_info.value)


def test_b10_gate7_no_files(conn):
    form_id = make_form(conn)
    slug = f"no-files-{uuid.uuid4().hex[:8]}"
    content_hash = make_content(conn, form_id, slug)
    make_approval(conn, form_id, content_hash, [])

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur.fetchone()
        cur.close()
    assert 'GATE7_FAILED' in str(exc_info.value)


def test_b11_rollback_on_failure(conn):
    """Failed publish (GATE-3) must not change form status."""
    form_id, _, _, _ = _full_publish_setup(conn)
    conn.commit()

    cur0 = conn.cursor()
    cur0.execute("SET row_security = off;")
    cur0.close()

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_content SET body_html = '<p>broken</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()
    conn.commit()

    cur_a = conn.cursor()
    cur_a.execute("SET row_security = off;")
    cur_a.close()

    raised = False
    try:
        cur2 = conn.cursor()
        cur2.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur2.fetchone()
        cur2.close()
    except psycopg2.errors.RaiseException as e:
        raised = True
        assert 'GATE3_FAILED' in str(e)
        conn.rollback()
        cur_b = conn.cursor()
        cur_b.execute("SET row_security = off;")
        cur_b.close()

    assert raised, "Expected GATE3_FAILED was not raised"

    cur3 = conn.cursor()
    cur3.execute("SELECT status FROM public.reference_forms WHERE id = %s;", (form_id,))
    row = cur3.fetchone()
    cur3.close()
    assert row is not None
    assert row[0] == 'DRAFT'


# ---------------------------------------------------------------------------
# Group C — rpc_change_slug_reference_form
# ---------------------------------------------------------------------------

def _register_slug(conn, slug, form_id, status='CANONICAL'):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
        (slug, form_id, status)
    )
    cur.close()


def test_c01_slug_change_success(conn):
    form_id = make_form(conn)
    old_slug = f"old-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, old_slug)
    _register_slug(conn, old_slug, form_id)

    cur = conn.cursor()
    cur.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_before = cur.fetchone()[0]
    cur.close()

    clear_outbox(conn)
    new_slug = f"new-{uuid.uuid4().hex[:8]}"

    cur2 = conn.cursor()
    cur2.execute(
        "SELECT public.rpc_change_slug_reference_form(%s, %s, %s);",
        (form_id, new_slug, 'actor')
    )
    assert str(cur2.fetchone()[0]) == str(form_id)
    cur2.close()

    cur3 = conn.cursor()
    cur3.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_after = cur3.fetchone()[0]
    cur3.execute("SELECT slug_status FROM public.reference_form_slug_registry WHERE slug = %s;", (new_slug,))
    assert cur3.fetchone()[0] == 'CANONICAL'
    cur3.execute("SELECT slug_status FROM public.reference_form_slug_registry WHERE slug = %s;", (old_slug,))
    assert cur3.fetchone()[0] == 'HISTORY'
    cur3.close()

    assert hash_before != hash_after
    assert get_outbox_count(conn) == 1


def test_c02_reuse_past_slug(conn):
    form_id = make_form(conn)
    slug_a = f"slug-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"slug-b-{uuid.uuid4().hex[:8]}"
    make_content(conn, form_id, slug_a)
    _register_slug(conn, slug_a, form_id)

    cur = conn.cursor()
    cur.execute("SELECT public.rpc_change_slug_reference_form(%s, %s, %s);", (form_id, slug_b, 'actor'))
    cur.fetchone()
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur2 = conn.cursor()
        cur2.execute("SELECT public.rpc_change_slug_reference_form(%s, %s, %s);", (form_id, slug_a, 'actor'))
        cur2.fetchone()
        cur2.close()
    assert 'SLUG_CHANGE_FAILED' in str(exc_info.value)


def test_c03_other_form_conflict(conn):
    form1 = make_form(conn)
    form2 = make_form(conn)
    slug_x  = f"shared-{uuid.uuid4().hex[:8]}"
    slug_f2 = f"f2init-{uuid.uuid4().hex[:8]}"

    make_content(conn, form1, slug_x)
    make_content(conn, form2, slug_f2)
    _register_slug(conn, slug_x,  form1)
    _register_slug(conn, slug_f2, form2)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute("SELECT public.rpc_change_slug_reference_form(%s, %s, %s);", (form2, slug_x, 'actor'))
        cur.fetchone()
        cur.close()
    assert 'SLUG_CONFLICT' in str(exc_info.value) or 'SLUG_CHANGE_FAILED' in str(exc_info.value)


def test_c04_slug_change_invalidates_publish(conn):
    form_id, content_hash, file_id, sha256 = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT canonical_slug FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    current_slug = cur.fetchone()[0]
    cur.close()
    _register_slug(conn, current_slug, form_id)

    new_slug = f"changed-{uuid.uuid4().hex[:8]}"
    cur2 = conn.cursor()
    cur2.execute("SELECT public.rpc_change_slug_reference_form(%s, %s, %s);", (form_id, new_slug, 'actor'))
    cur2.fetchone()
    cur2.close()

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur3 = conn.cursor()
        cur3.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
            (form_id, 'actor', '{}', True)
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE3_FAILED' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group D — rpc_unpublish_reference_form
# ---------------------------------------------------------------------------

def test_d01_unpublish_success(conn):
    form_id, _, _, _ = _full_publish_setup(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'actor', '{}', True)
    )
    cur.fetchone()
    cur.close()
    clear_outbox(conn)

    cur2 = conn.cursor()
    cur2.execute(
        "SELECT public.rpc_unpublish_reference_form(%s, %s, %s);",
        (form_id, 'actor', 'test reason')
    )
    assert str(cur2.fetchone()[0]) == str(form_id)
    cur2.close()

    cur3 = conn.cursor()
    cur3.execute("SELECT status FROM public.reference_forms WHERE id = %s;", (form_id,))
    assert cur3.fetchone()[0] == 'DRAFT'
    cur3.execute("SELECT reason FROM public.search_index_outbox_stub;")
    reasons = [r[0] for r in cur3.fetchall()]
    cur3.close()
    assert 'UNPUBLISHED' in reasons


def test_d02_unpublish_draft(conn):
    form_id = make_form(conn, status='DRAFT')

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_unpublish_reference_form(%s, %s, %s);",
            (form_id, 'actor', None)
        )
        cur.fetchone()
        cur.close()
    assert 'UNPUBLISH_FAILED' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group E — public view
# ---------------------------------------------------------------------------

def _publish_form(conn, form_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb, %s);",
        (form_id, 'actor', '{}', True)
    )
    cur.fetchone()
    cur.close()


def test_e01_published_form_in_view(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute("SELECT id FROM public.reference_form_public_view WHERE id = %s;", (form_id,))
    assert cur.fetchone() is not None
    cur.close()


def test_e02_draft_form_not_in_view(conn):
    form_id = make_form(conn)
    make_content(conn, form_id, f"draft-{uuid.uuid4().hex[:8]}")

    cur = conn.cursor()
    cur.execute("SELECT id FROM public.reference_form_public_view WHERE id = %s;", (form_id,))
    assert cur.fetchone() is None
    cur.close()


def test_e03_content_changed_not_in_view(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_content SET body_html = '<p>post-publish</p>' WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    cur.close()

    cur2 = conn.cursor()
    cur2.execute("SELECT id FROM public.reference_form_public_view WHERE id = %s;", (form_id,))
    assert cur2.fetchone() is None
    cur2.close()


def test_e04_updated_at_greatest(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute("SELECT updated_at FROM public.reference_form_public_view WHERE id = %s;", (form_id,))
    view_ts = cur.fetchone()[0]
    cur.execute("SELECT updated_at FROM public.reference_forms WHERE id = %s;", (form_id,))
    rf_ts = cur.fetchone()[0]
    cur.execute(
        "SELECT updated_at FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    rfc_ts = cur.fetchone()[0]
    cur.close()

    assert view_ts == max(rf_ts, rfc_ts)


def test_e05_public_view_no_file_ref(conn):
    """qa_pass_files must be JSONB with file_id/sha256/approved_at — no file_ref storage path."""
    form_id, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)

    cur = conn.cursor()
    cur.execute(
        "SELECT qa_pass_files FROM public.reference_form_public_view WHERE id = %s;",
        (form_id,)
    )
    row = cur.fetchone()
    cur.close()

    assert row is not None
    qa_files = row[0]
    assert isinstance(qa_files, list), f"Expected list from JSONB, got {type(qa_files)}"
    assert len(qa_files) >= 1
    for entry in qa_files:
        assert 'file_id' in entry
        assert 'sha256'  in entry
        assert 'approved_at' in entry
        assert 'file_ref' not in entry, "file_ref (storage path) must not be exposed in public view"


# ---------------------------------------------------------------------------
# Group F — SearchDocument normalization (inline)
# ---------------------------------------------------------------------------

def _normalize_reference_form(row: dict):
    if not row.get('title'):
        return None
    return {
        'canonical_id':       str(row['id']),
        'publication_status': 'PUBLISHED',
        'public_url':         f"/reference-form/{row['canonical_slug']}",
        'title':              row['title'],
        'description':        row.get('description'),
        'published_at':       row.get('published_at'),
        'formats':            row.get('formats', []),
        'legacy_codes':       row.get('legacy_codes', []),
    }


def test_f01_normalize_returns_correct_fields(conn):
    tid = uuid.uuid4()
    result = _normalize_reference_form({
        'id': tid, 'canonical_slug': 'test-form',
        'title': 'Test Form Title', 'description': 'desc',
        'published_at': datetime.now(timezone.utc),
        'formats': [], 'legacy_codes': [],
    })
    assert result is not None
    assert result['canonical_id'] == str(tid)
    assert result['publication_status'] == 'PUBLISHED'
    assert result['public_url'] == '/reference-form/test-form'
    assert result['title'] == 'Test Form Title'


def test_f02_normalize_missing_required_returns_none(conn):
    result = _normalize_reference_form({
        'id': uuid.uuid4(), 'canonical_slug': 'some-form',
        'title': '', 'description': None,
        'published_at': None, 'formats': [], 'legacy_codes': [],
    })
    assert result is None


def test_f03_canonical_id_is_uuid_no_prefix(conn):
    tid = uuid.uuid4()
    result = _normalize_reference_form({
        'id': tid, 'canonical_slug': 'no-prefix',
        'title': 'No Prefix Test', 'description': None,
        'published_at': None, 'formats': [], 'legacy_codes': [],
    })
    assert result is not None
    cid = result['canonical_id']
    assert 'REFERENCE_FORM::' not in cid
    assert cid == str(tid)
