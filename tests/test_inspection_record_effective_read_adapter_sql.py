"""OBJ-01 KNOT-2 — effective read adapter SQL contract (static, no DB)."""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_UP = _ROOT / "docs" / "sql" / "20260826_inspection_record_effective_read_adapter_up.sql"
_DOWN = _ROOT / "docs" / "sql" / "20260826_inspection_record_effective_read_adapter_down.sql"


def _up() -> str:
    return _UP.read_text(encoding="utf-8")


def _down() -> str:
    return _DOWN.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    out = []
    for ln in sql.splitlines():
        idx = ln.find("--")
        if idx != -1:
            ln = ln[:idx]
        out.append(ln)
    return "\n".join(out)


def test_function_signature():
    up = _up()
    assert "CREATE OR REPLACE FUNCTION public.fn_list_effective_inspection_records_by_inspector(" in up
    assert "p_inspector_id uuid" in up
    assert "integer" in up
    assert "RETURNS jsonb" in up


def test_stable_security_definer_search_path():
    up = _up()
    assert "STABLE" in up
    assert "SECURITY DEFINER" in up
    assert "SET search_path = public, pg_temp" in up


def test_service_role_execute_only():
    up = _up()
    assert "GRANT EXECUTE ON FUNCTION public.fn_list_effective_inspection_records_by_inspector(uuid, integer) TO service_role" in up
    assert "REVOKE ALL ON FUNCTION public.fn_list_effective_inspection_records_by_inspector(uuid, integer) FROM PUBLIC, anon, authenticated" in up
    assert "TO anon" not in up
    assert "TO authenticated" not in up
    assert "GRANT ALL" not in up


def test_no_mutation():
    exe = _strip_sql_comments(_up())
    assert "INSERT INTO" not in exe
    assert "DELETE FROM" not in exe
    assert "UPDATE " not in exe
    assert "UPSERT" not in exe


def test_calls_single_resolver_no_folding_reimpl():
    up = _up()
    assert "public.fn_resolve_inspection_record(v_id)" in up
    # folding must NOT be reimplemented here
    assert "ORDER BY revision ASC" not in up
    assert "before_snapshot" not in up
    assert "after_snapshot->'revision'" not in up


def test_candidate_union():
    up = _up()
    assert "si.inspector_id = p_inspector_id" in up
    assert "j.after_snapshot->>'inspector_id' = p_inspector_id::text" in up
    assert "UNION" in up


def test_effective_filter():
    up = _up()
    assert "(v_rec->>'is_active')::boolean" in up
    assert "(v_rec->>'inspector_id') = p_inspector_id::text" in up


def test_sort_and_tiebreak():
    up = _up()
    assert "(elem->>'inspection_date') DESC NULLS LAST" in up
    assert "(elem->>'inspection_id') DESC" in up


def test_no_silent_drop_on_resolver_error():
    up = _up()
    assert "IF v_rec ? 'error' THEN" in up
    assert "RETURN v_rec;" in up


def test_down_drops_only_no_base_no_create():
    exe = _strip_sql_comments(_down())
    assert "DROP FUNCTION IF EXISTS public.fn_list_effective_inspection_records_by_inspector(uuid, integer)" in exe
    assert "CREATE" not in exe
    # base ledger / foundation / single-record resolver untouched
    assert "safety_inspections" not in exe
    assert "safety_inspection_record_journal" not in exe
    assert "fn_resolve_inspection_record" not in exe
