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
    up = _up()
    # no ALTER/UPDATE/DELETE against base ledger in UP
    assert "ALTER TABLE public.safety_inspections" not in up
    assert "ALTER TABLE public.safety_inspection_results" not in up
    assert "UPDATE public.safety_inspections" not in up
    assert "UPDATE safety_inspections" not in up
    assert "DELETE FROM public.safety_inspections" not in up
    assert "DELETE FROM public.safety_inspection_results" not in up
    # base tables are only REFERENCE'd (FK) / SELECT'd, never mutated
    assert "REFERENCES public.safety_inspections(id)" in up


def test_down_drops_only_no_base_no_create():
    down = _down()
    assert "CREATE TABLE" not in down
    assert "CREATE FUNCTION" not in down
    assert "CREATE TRIGGER" not in down
    # DOWN must not touch base ledger at all
    assert "safety_inspections" not in down
    assert "safety_inspection_results" not in down
    # DOWN drops foundation objects
    assert "DROP TABLE IF EXISTS public.safety_inspection_command_receipt" in down
    assert "DROP TABLE IF EXISTS public.safety_inspection_record_journal" in down
    assert "DROP FUNCTION IF EXISTS public.fn_apply_inspection_record_command" in down
    assert "DROP FUNCTION IF EXISTS public.fn_resolve_inspection_record" in down
