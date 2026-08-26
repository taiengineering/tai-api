"""OBJ-01 STEP-1A — SQL contract test (static, no DB required).

UP/DOWN SQL artifact 가 STEP-1A 계약을 만족하는지 텍스트로 검증한다.
production 적용 없이 실행 가능하다.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_UP = _ROOT / "docs" / "sql" / "20260826_inspection_record_foundation_up.sql"
_DOWN = _ROOT / "docs" / "sql" / "20260826_inspection_record_foundation_down.sql"


def _up() -> str:
    return _UP.read_text(encoding="utf-8")


def _down() -> str:
    return _DOWN.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Return only executable SQL: drop full-line and trailing `--` comments.

    This file contains no string literals with `--`, so a simple per-line cut is
    safe. Mentioning a base table name in a comment or FK is NOT a violation;
    only executable mutation statements are.
    """
    out = []
    for ln in sql.splitlines():
        idx = ln.find("--")
        if idx != -1:
            ln = ln[:idx]
        out.append(ln)
    return "\n".join(out)


def test_up_creates_two_tables():
    up = _up()
    assert "CREATE TABLE IF NOT EXISTS public.safety_inspection_record_journal" in up
    assert "CREATE TABLE IF NOT EXISTS public.safety_inspection_command_receipt" in up


def test_two_unique_contracts():
    up = _up()
    assert "uq_sirj_inspection_revision UNIQUE (inspection_id, revision)" in up
    assert "uq_sirj_inspection_command  UNIQUE (inspection_id, command_id)" in up
    assert "uq_sicr_inspection_command UNIQUE (inspection_id, command_id)" in up


def test_five_event_types():
    up = _up()
    for ev in (
        "INSPECTION_CORRECTION",
        "RESULT_CORRECTION",
        "STATUS_CHANGE",
        "INSPECTION_DEACTIVATION",
        "RESULT_DEACTIVATION",
    ):
        assert ev in up


def test_target_result_check():
    up = _up()
    assert "chk_sirj_target_result" in up
    assert "target_result_id IS NOT NULL" in up
    assert "target_result_id IS NULL" in up


def test_rls_enabled_both():
    up = _up()
    assert up.count("ENABLE ROW LEVEL SECURITY") >= 2


def test_no_direct_anon_auth_mutation():
    up = _up()
    # no policy nor grant giving anon/authenticated write; no GRANT ALL anywhere
    assert "GRANT ALL" not in up
    assert "GRANT INSERT" not in up
    assert "GRANT UPDATE" not in up
    assert "GRANT DELETE" not in up
    assert "TO anon" not in up
    assert "TO authenticated" not in up


def test_service_role_select_only_on_tables():
    up = _up()
    assert "GRANT SELECT ON TABLE public.safety_inspection_record_journal  TO service_role" in up
    assert "GRANT SELECT ON TABLE public.safety_inspection_command_receipt TO service_role" in up
    # revoke neutralizes supabase default grants
    assert "REVOKE ALL ON TABLE public.safety_inspection_record_journal  FROM PUBLIC, anon, authenticated, service_role" in up
    assert "REVOKE ALL ON TABLE public.safety_inspection_command_receipt FROM PUBLIC, anon, authenticated, service_role" in up


def test_rpc_service_role_only():
    up = _up()
    assert "GRANT EXECUTE ON FUNCTION public.fn_resolve_inspection_record(uuid) TO service_role" in up
    assert "GRANT EXECUTE ON FUNCTION public.fn_apply_inspection_record_command" in up
    assert "TO service_role" in up
    assert "REVOKE ALL ON FUNCTION public.fn_resolve_inspection_record(uuid) FROM PUBLIC, anon, authenticated" in up


def test_security_definer_search_path_fixed():
    up = _up()
    assert up.count("SECURITY DEFINER") >= 2
    assert up.count("SET search_path = public, pg_temp") >= 2


def test_append_only_triggers():
    up = _up()
    assert "fn_reject_inspection_record_mutation" in up
    assert up.count("BEFORE UPDATE OR DELETE") >= 2
    assert "trg_sirj_append_only" in up
    assert "trg_sicr_append_only" in up


def test_up_base_ledger_untouched():
    # executable statements only: base ledger must never be mutated in UP
    exe = _strip_sql_comments(_up())
    assert "ALTER TABLE public.safety_inspections" not in exe
    assert "ALTER TABLE public.safety_inspection_results" not in exe
    assert "UPDATE public.safety_inspections" not in exe
    assert "UPDATE safety_inspections" not in exe
    assert "DELETE FROM public.safety_inspections" not in exe
    assert "DELETE FROM public.safety_inspection_results" not in exe
    # base tables are only REFERENCE'd (FK) / SELECT'd, never mutated
    assert "REFERENCES public.safety_inspections(id)" in exe


def test_down_drops_only_no_base_no_create():
    # FIX-3: check EXECUTABLE statements only (strip `--` comments). Mentioning a
    # base table name in a comment is not a violation; mutating it is.
    exe = _strip_sql_comments(_down())
    # DOWN adds nothing
    assert "CREATE TABLE" not in exe
    assert "CREATE FUNCTION" not in exe
    assert "CREATE TRIGGER" not in exe
    # DOWN performs no base-ledger mutation of any kind
    assert "ALTER" not in exe
    assert "UPDATE" not in exe
    assert "DELETE" not in exe
    assert "DROP TABLE IF EXISTS public.safety_inspections" not in exe
    assert "DROP TABLE IF EXISTS public.safety_inspection_results" not in exe
    # DOWN drops exactly the foundation objects
    assert "DROP TABLE IF EXISTS public.safety_inspection_command_receipt" in exe
    assert "DROP TABLE IF EXISTS public.safety_inspection_record_journal" in exe
    assert "DROP FUNCTION IF EXISTS public.fn_apply_inspection_record_command" in exe
    assert "DROP FUNCTION IF EXISTS public.fn_resolve_inspection_record" in exe


# ----------------------------------------------------------------------------
# COMMIT 5/6 — sequential journal folding + hardening contract
# ----------------------------------------------------------------------------

def test_resolver_sequential_folding():
    up = _up()
    assert "ORDER BY revision ASC" in up
    assert "FOR v_j IN" in up                       # real journal traversal
    assert "before_snapshot IS DISTINCT FROM v_record" in up   # chain comparison
    # FIX-2: JSON exact comparison, no ::bigint cast
    assert "(v_j.after_snapshot->'revision') IS DISTINCT FROM to_jsonb(v_j.revision)" in up
    assert "v_record := v_j.after_snapshot" in up   # adopt only after validation


def test_no_latest_snapshot_shortcut():
    up = _up()
    # the removed latest-only pattern must not reappear
    assert "revision = v_max_rev" not in up
    assert "v_record := v_after" not in up
    assert "INTO v_after" not in up
    assert "v_max_rev" not in up


def test_fix2_no_unsafe_revision_cast():
    # FIX-2: the unsafe ::bigint cast on after_snapshot revision must be gone
    up = _up()
    assert "::bigint IS DISTINCT FROM v_j.revision" not in up


def test_fix1_result_code_hardening():
    # FIX-1: result_code correction rejects explicit null / non-string / non-canonical
    up = _up()
    assert "jsonb_typeof(p_changes->'result_code') <> 'string'" in up
    assert "(p_changes->>'result_code') IN ('NORMAL','ABNORMAL','HOLD')" in up
