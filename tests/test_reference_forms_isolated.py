"""
test_reference_forms_isolated.py

Isolated integration tests for the Reference Forms CMS migrations.
Connects to: localhost:5455/ref05_test (ext-sql-final-pg Docker)
Schema: public — no search_path substitution; matches production layout.
pgcrypto: extensions schema (Supabase production compatible via wrapper).
auth.role(): stubbed to return 'service_role'.
Supabase roles (anon, authenticated, service_role) created for permission tests.
RLS disabled per-session via SET row_security = off.
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
MIGRATION_DIR    = Path(__file__).parent.parent / "supabase" / "migrations"
CORE_MIGRATION    = MIGRATION_DIR / "20261011120000_reference_forms_core.sql"
STORAGE_MIGRATION = MIGRATION_DIR / "20261011120001_reference_forms_storage.sql"
RPC_MIGRATION     = MIGRATION_DIR / "20261011120002_reference_forms_rpc.sql"


def _raw_conn():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------
def _setup_module_once():
    conn = _raw_conn()
    cur = conn.cursor()

    # 1. extensions schema + pgcrypto wrapper (matches Supabase production layout)
    cur.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
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

    # 2. auth schema + auth.role() stub
    cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
    cur.execute("""
        CREATE OR REPLACE FUNCTION auth.role()
        RETURNS TEXT LANGUAGE sql STABLE AS $$
            SELECT 'service_role'::TEXT;
        $$;
    """)

    # 3. Supabase-equivalent roles for permission tests
    for role in ('anon', 'authenticated', 'service_role'):
        cur.execute(f"""
            DO $$ BEGIN
                CREATE ROLE {role};
            EXCEPTION WHEN duplicate_object THEN NULL;
            END; $$;
        """)

    # 4. Drop existing reference form objects (idempotent)
    # Also drop the old 4-param publish signature from prior migrations.
    cur.execute("""
        DROP VIEW     IF EXISTS public.reference_form_public_view CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_publish_reference_form(UUID,TEXT,JSONB,BOOLEAN) CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_publish_reference_form(UUID,TEXT,JSONB) CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_unpublish_reference_form(UUID,TEXT,TEXT) CASCADE;
        DROP FUNCTION IF EXISTS public.rpc_change_slug_reference_form(UUID,TEXT,TEXT) CASCADE;
        DROP FUNCTION IF EXISTS public.fn_assert_slug_globally_unique(TEXT,UUID) CASCADE;
        DROP FUNCTION IF EXISTS public.fn_reference_form_content_hash() CASCADE;
        DROP FUNCTION IF EXISTS public.fn_reference_forms_set_updated_at() CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_events          CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_approvals       CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_aliases         CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_legacy_links    CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_relations       CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_sources         CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_preview_artifacts CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_files           CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_slug_registry   CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_slug_history    CASCADE;
        DROP TABLE    IF EXISTS public.reference_form_content         CASCADE;
        DROP TABLE    IF EXISTS public.reference_forms                CASCADE;
    """)

    # 5. Outbox stub (replaces real search_index_outbox)
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

    # 6. Apply all 3 migrations directly — no SQL rewriting
    #    STORAGE_MIGRATION self-skips (storage.buckets absent in plain PG)
    cur.execute(CORE_MIGRATION.read_text())
    cur.execute(STORAGE_MIGRATION.read_text())
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
        VALUES (%s, 'ko', %s, %s, %s, %s);
        """,
        (form_id, slug, title, description, body_html)
    )
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
    return row[0], row[1]


def make_preview_artifact(conn, form_id, source_file_sha256=None,
                          is_published=True, qa_status='QA_PASS'):
    if source_file_sha256 is None:
        source_file_sha256 = uuid.uuid4().hex * 2
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO public.reference_form_preview_artifacts
            (form_id, preview_ref, source_file_sha256, is_published, qa_status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (form_id,
         f"reference-forms-preview/{uuid.uuid4().hex[:8]}.png",
         source_file_sha256, is_published, qa_status)
    )
    preview_id = cur.fetchone()[0]
    cur.close()
    return preview_id


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
    cur.fetchone()
    cur.close()


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
    """
    Creates a fully publishable form including a published QA_PASS preview artifact.
    All GATE-1~7 requirements satisfied.
    """
    form_id      = make_form(conn)
    slug         = f"test-form-{uuid.uuid4().hex[:8]}"
    content_hash = make_content(conn, form_id, slug)
    sha256       = uuid.uuid4().hex * 2
    file_id, actual_sha256 = make_file(conn, form_id, sha256=sha256)
    make_approval(conn, form_id, content_hash,
                  [{"file_id": str(file_id), "sha256": actual_sha256}])
    make_preview_artifact(conn, form_id)
    clear_outbox(conn)
    return form_id, content_hash, file_id, actual_sha256


def _setup_no_preview(conn):
    """Like _full_publish_setup but without a preview artifact (for GATE-6 test)."""
    form_id      = make_form(conn)
    slug         = f"no-prev-{uuid.uuid4().hex[:8]}"
    content_hash = make_content(conn, form_id, slug)
    sha256       = uuid.uuid4().hex * 2
    file_id, actual_sha256 = make_file(conn, form_id, sha256=sha256)
    make_approval(conn, form_id, content_hash,
                  [{"file_id": str(file_id), "sha256": actual_sha256}])
    clear_outbox(conn)
    return form_id


# ---------------------------------------------------------------------------
# Group A — Structure (6)
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
               ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema   = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = 'public'
          AND tc.table_name LIKE 'reference_form%';
        """
    )
    fk_set = {tuple(r) for r in cur.fetchall()}
    cur.close()

    required = [
        ('reference_form_content',  'form_id', 'reference_forms', 'id'),
        ('reference_form_files',    'form_id', 'reference_forms', 'id'),
        ('reference_form_approvals','form_id', 'reference_forms', 'id'),
        ('reference_form_events',   'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_history',  'form_id', 'reference_forms', 'id'),
        ('reference_form_slug_registry', 'form_id', 'reference_forms', 'id'),
        ('reference_form_sources',  'form_id', 'reference_forms', 'id'),
        ('reference_form_files', 'preview_artifact_id',
         'reference_form_preview_artifacts', 'id'),
    ]
    missing = [fk for fk in required if fk not in fk_set]
    assert missing == [], f"Missing FKs: {missing}"


def test_a03_content_hash_on_insert(conn):
    form_id = make_form(conn)
    h = make_content(conn, form_id, f"hash-test-{uuid.uuid4().hex[:8]}", title="Hash Test")
    assert h is not None
    assert len(h) == 64
    assert re.match(r'^[0-9a-f]{64}$', h), f"Not hex SHA256: {h}"


def test_a04_content_hash_on_slug_update(conn):
    form_id = make_form(conn)
    hash_before = make_content(conn, form_id, f"orig-{uuid.uuid4().hex[:8]}")
    cur = conn.cursor()
    cur.execute(
        "UPDATE public.reference_form_content SET canonical_slug = %s WHERE form_id = %s AND lang = 'ko';",
        (f"updated-{uuid.uuid4().hex[:8]}", form_id)
    )
    cur.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_after = cur.fetchone()[0]
    cur.close()
    assert hash_before != hash_after


def test_a05_content_slug_unique(conn):
    slug = f"unique-{uuid.uuid4().hex[:8]}"
    make_content(conn, make_form(conn), slug)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        make_content(conn, make_form(conn), slug)


def test_a06_slug_registry_pk_unique(conn):
    form_id = make_form(conn)
    slug = f"reg-{uuid.uuid4().hex[:8]}"
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
# Group B — rpc_publish_reference_form (11)
# ---------------------------------------------------------------------------

def test_b01_publish_success(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
        (form_id, 'actor', '{}')
    )
    assert str(cur.fetchone()[0]) == str(form_id)
    cur.close()

    cur2 = conn.cursor()
    cur2.execute("SELECT status FROM public.reference_forms WHERE id = %s;", (form_id,))
    assert cur2.fetchone()[0] == 'PUBLISHED'
    cur2.close()
    assert get_outbox_count(conn) == 1


def test_b02_gate1_already_published(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
        (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE1_FAILED' in str(exc_info.value)


def test_b03_gate2_no_approval(conn):
    form_id = make_form(conn)
    make_content(conn, form_id, f"no-appr-{uuid.uuid4().hex[:8]}")
    make_file(conn, form_id)
    make_preview_artifact(conn, form_id)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
        )
        cur2.fetchone()
        cur2.close()
    assert 'GATE4_FAILED' in str(exc_info.value)


def test_b06_gate4_new_file_not_in_approval(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    make_file(conn, form_id)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
        )
        cur.fetchone()
        cur.close()
    assert 'GATE5_FAILED' in str(exc_info.value)


def test_b09_gate6_no_preview_artifact(conn):
    """GATE-6 always fires — no bypass parameter exists in the current signature."""
    form_id = _setup_no_preview(conn)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
        )
        cur.fetchone()
        cur.close()
    assert 'GATE6_FAILED' in str(exc_info.value)


def test_b10_gate7_no_files(conn):
    form_id = make_form(conn)
    content_hash = make_content(conn, form_id, f"no-files-{uuid.uuid4().hex[:8]}")
    make_approval(conn, form_id, content_hash, [])
    make_preview_artifact(conn, form_id)

    with pytest.raises(psycopg2.errors.RaiseException) as exc_info:
        cur = conn.cursor()
        cur.execute(
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
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
    assert cur3.fetchone()[0] == 'DRAFT'
    cur3.close()


# ---------------------------------------------------------------------------
# Group C — rpc_change_slug_reference_form (4)
# ---------------------------------------------------------------------------

def _register_slug(conn, slug, form_id, status='CANONICAL'):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO public.reference_form_slug_registry (slug, form_id, slug_status) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
        (slug, form_id, status)
    )
    cur.close()


def test_c01_slug_change_success(conn):
    form_id    = make_form(conn)
    old_slug   = f"old-{uuid.uuid4().hex[:8]}"
    hash_before = make_content(conn, form_id, old_slug)
    _register_slug(conn, old_slug, form_id)
    clear_outbox(conn)

    new_slug = f"new-{uuid.uuid4().hex[:8]}"
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_change_slug_reference_form(%s, %s, %s);",
        (form_id, new_slug, 'actor')
    )
    assert str(cur.fetchone()[0]) == str(form_id)
    cur.execute(
        "SELECT content_hash FROM public.reference_form_content WHERE form_id = %s AND lang = 'ko';",
        (form_id,)
    )
    hash_after = cur.fetchone()[0]
    cur.execute("SELECT slug_status FROM public.reference_form_slug_registry WHERE slug = %s;", (new_slug,))
    assert cur.fetchone()[0] == 'CANONICAL'
    cur.execute("SELECT slug_status FROM public.reference_form_slug_registry WHERE slug = %s;", (old_slug,))
    assert cur.fetchone()[0] == 'HISTORY'
    cur.close()

    assert hash_before != hash_after
    assert get_outbox_count(conn) == 1


def test_c02_reuse_past_slug(conn):
    form_id = make_form(conn)
    slug_a  = f"slug-a-{uuid.uuid4().hex[:8]}"
    slug_b  = f"slug-b-{uuid.uuid4().hex[:8]}"
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
    form1  = make_form(conn)
    form2  = make_form(conn)
    slug_x = f"shared-{uuid.uuid4().hex[:8]}"
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
    form_id, _, _, _ = _full_publish_setup(conn)

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
            "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
            (form_id, 'actor', '{}')
        )
        cur3.fetchone()
        cur3.close()
    assert 'GATE3_FAILED' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group D — rpc_unpublish_reference_form (2)
# ---------------------------------------------------------------------------

def _publish_form(conn, form_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_publish_reference_form(%s, %s, %s::jsonb);",
        (form_id, 'actor', '{}')
    )
    cur.fetchone()
    cur.close()


def test_d01_unpublish_success(conn):
    form_id, _, _, _ = _full_publish_setup(conn)
    _publish_form(conn, form_id)
    clear_outbox(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT public.rpc_unpublish_reference_form(%s, %s, %s);",
        (form_id, 'actor', 'test reason')
    )
    assert str(cur.fetchone()[0]) == str(form_id)
    cur.execute("SELECT status FROM public.reference_forms WHERE id = %s;", (form_id,))
    assert cur.fetchone()[0] == 'DRAFT'
    cur.execute("SELECT reason FROM public.search_index_outbox_stub;")
    assert 'UNPUBLISHED' in [r[0] for r in cur.fetchall()]
    cur.close()


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
# Group E — public view (5)
# ---------------------------------------------------------------------------

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
    """qa_pass_files returns JSONB with file_id/sha256/approved_at — no file_ref."""
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
    assert isinstance(qa_files, list)
    assert len(qa_files) >= 1
    for entry in qa_files:
        assert 'file_id'    in entry
        assert 'sha256'     in entry
        assert 'approved_at' in entry
        assert 'file_ref'   not in entry, "file_ref storage path must not appear in public view"


# ---------------------------------------------------------------------------
# Group F — SearchDocument normalization (3)
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


def test_f02_normalize_missing_required_returns_none(conn):
    result = _normalize_reference_form({
        'id': uuid.uuid4(), 'canonical_slug': 'x',
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
    assert 'REFERENCE_FORM::' not in result['canonical_id']
    assert result['canonical_id'] == str(tid)


# ---------------------------------------------------------------------------
# Group G — EXECUTE permission verification (6)
# Validates: PUBLIC revoked, anon/authenticated denied, service_role granted.
# ---------------------------------------------------------------------------

def _fn_sig(fn_name: str, args: str) -> str:
    return f"public.{fn_name}({args})"


PUBLISH_SIG    = _fn_sig('rpc_publish_reference_form',    'uuid,text,jsonb')
UNPUBLISH_SIG  = _fn_sig('rpc_unpublish_reference_form',  'uuid,text,text')
SLUG_SIG       = _fn_sig('rpc_change_slug_reference_form','uuid,text,text')
ASSERT_SIG     = _fn_sig('fn_assert_slug_globally_unique','text,uuid')


def test_g01_anon_no_execute_publish(conn):
    cur = conn.cursor()
    cur.execute("SELECT has_function_privilege('anon', %s, 'EXECUTE');", (PUBLISH_SIG,))
    assert cur.fetchone()[0] is False, "anon must not have EXECUTE on rpc_publish"
    cur.close()


def test_g02_authenticated_no_execute_publish(conn):
    cur = conn.cursor()
    cur.execute("SELECT has_function_privilege('authenticated', %s, 'EXECUTE');", (PUBLISH_SIG,))
    assert cur.fetchone()[0] is False, "authenticated must not have EXECUTE on rpc_publish"
    cur.close()


def test_g03_service_role_execute_publish(conn):
    cur = conn.cursor()
    cur.execute("SELECT has_function_privilege('service_role', %s, 'EXECUTE');", (PUBLISH_SIG,))
    assert cur.fetchone()[0] is True, "service_role must have EXECUTE on rpc_publish"
    cur.close()


def test_g04_anon_no_execute_unpublish(conn):
    cur = conn.cursor()
    cur.execute("SELECT has_function_privilege('anon', %s, 'EXECUTE');", (UNPUBLISH_SIG,))
    assert cur.fetchone()[0] is False, "anon must not have EXECUTE on rpc_unpublish"
    cur.close()


def test_g05_anon_no_execute_change_slug(conn):
    cur = conn.cursor()
    cur.execute("SELECT has_function_privilege('anon', %s, 'EXECUTE');", (SLUG_SIG,))
    assert cur.fetchone()[0] is False, "anon must not have EXECUTE on rpc_change_slug"
    cur.close()


def test_g06_service_role_execute_all_rpcs(conn):
    """service_role must have EXECUTE on all 4 admin functions."""
    cur = conn.cursor()
    for sig in (PUBLISH_SIG, UNPUBLISH_SIG, SLUG_SIG, ASSERT_SIG):
        cur.execute("SELECT has_function_privilege('service_role', %s, 'EXECUTE');", (sig,))
        row = cur.fetchone()
        assert row[0] is True, f"service_role lacks EXECUTE on {sig}"
    cur.close()
