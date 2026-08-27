"""OBJ-01 KNOT-3D — base ledger immutability SQL contract tests (T1-T25).

up/down 아티팩트 텍스트 정적 검증. DB 접속 없음. production Python/Router/Service
변경 0 (이 테스트만 신규).
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260827_inspection_base_immutability_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260827_inspection_base_immutability_down.sql"))

FN = "fn_reject_inspection_base_mutation"
T_HDR = "trg_safety_inspections_immutable"
T_RES = "trg_safety_inspection_results_immutable"


def _up() -> str:
    with open(UP, encoding="utf-8") as f:
        return f.read()


def _down() -> str:
    with open(DOWN, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def _code(sql: str) -> str:
    """Normalized SQL with -- line comments removed (so prose in comments cannot
    trip absence checks). No -- appears inside this migration's string literals."""
    stripped = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return _norm(stripped)


# T1 — trigger function exact name + no-arg signature
def test_function_exact_name_signature():
    n = _norm(_up())
    assert f"create function public.{FN}()" in n
    assert "create or replace function" not in n   # (also part of T14 discipline)


# T2 — RETURNS trigger
def test_returns_trigger():
    assert re.search(r"create function public\.fn_reject_inspection_base_mutation\(\)\s+returns trigger",
                     _norm(_up()))


# T3 — SECURITY INVOKER, never DEFINER
def test_security_invoker_not_definer():
    n = _norm(_up())
    assert "security invoker" in n
    assert "security definer" not in n


# T4 — error marker
def test_error_marker():
    assert "INSPECTION_BASE_IMMUTABLE" in _up()


# T5 — ERRCODE 55000
def test_errcode_55000():
    assert re.search(r"using\s+errcode\s*=\s*'55000'", _norm(_up()))


# T6 — header trigger BEFORE UPDATE OR DELETE on safety_inspections
def test_header_trigger_events():
    n = _norm(_up())
    assert re.search(
        r"create trigger trg_safety_inspections_immutable before update or delete on public\.safety_inspections",
        n)


# T7 — result trigger BEFORE UPDATE OR DELETE on safety_inspection_results
def test_result_trigger_events():
    n = _norm(_up())
    assert re.search(
        r"create trigger trg_safety_inspection_results_immutable before update or delete on public\.safety_inspection_results",
        n)


# T8 — both FOR EACH ROW
def test_both_for_each_row():
    n = _norm(_up())
    assert n.count("for each row") == 2


# T9 — both triggers execute the same reject function
def test_both_use_reject_function():
    n = _norm(_up())
    assert n.count(f"execute function public.{FN}()") == 2


# T10 — no INSERT trigger event
def test_no_insert_trigger_event():
    n = _code(_up())
    # trigger event clauses are exactly "before update or delete"; none mention insert
    assert "before insert" not in n
    assert "or insert" not in n
    assert "insert or" not in n


# T11 — no TRUNCATE trigger event
def test_no_truncate_trigger_event():
    assert "truncate" not in _code(_up())


# T12 — no role / service_role / GUC bypass in the function
def test_no_role_or_guc_bypass():
    n = _code(_up())
    for tok in ("current_user", "session_user", "service_role", "current_setting", "set_config", "bypass"):
        assert tok not in n, tok


# T13 — no WHEN bypass on the triggers
def test_no_when_clause():
    assert "when (" not in _code(_up())


# T14 — function pre-existence fail-closed precheck
def test_precheck_function_absent():
    n = _norm(_up())
    assert "precheck p1 failed" in n
    assert f"p.proname = '{FN}'" in n


# T15 — header trigger pre-existence fail-closed precheck
def test_precheck_header_trigger_absent():
    n = _norm(_up())
    assert "precheck p2 failed" in n
    assert f"t.tgname = '{T_HDR}'" in n


# T16 — result trigger pre-existence fail-closed precheck
def test_precheck_result_trigger_absent():
    n = _norm(_up())
    assert "precheck p3 failed" in n
    assert f"t.tgname = '{T_RES}'" in n


# T17 — pair UNIQUE existence/definition precheck
def test_precheck_pair_unique():
    n = _norm(_up())
    assert "precheck p4 failed" in n
    assert "uq_safety_inspections_assignment_factory" in n
    assert "indisunique" in n
    assert "(assignment_id is not null)" in n


# ---- statement-level data mutation checks (NOT trigger-event words) ----
def _stmt_mutations(sql: str, table: str):
    n = _norm(sql)
    return [
        f"insert into public.{table}" in n,
        bool(re.search(rf"update public\.{table}\s+set", n)),
        bool(re.search(rf"delete from public\.{table}", n)),
    ]


# T18 — no INSERT/UPDATE/DELETE data statement on safety_inspections
def test_no_base_data_statement():
    for present in _stmt_mutations(_up() + "\n" + _down(), "safety_inspections"):
        assert present is False


# T19 — no INSERT/UPDATE/DELETE data statement on safety_inspection_results
def test_no_result_data_statement():
    for present in _stmt_mutations(_up() + "\n" + _down(), "safety_inspection_results"):
        assert present is False


# T20 — no pair UNIQUE DROP/ALTER
def test_no_pair_unique_drop_or_alter():
    n = _norm(_up() + "\n" + _down())
    assert not re.search(r"drop\s+index[^;]*uq_safety_inspections_assignment_factory", n)
    assert not re.search(r"alter\s+index[^;]*uq_safety_inspections_assignment_factory", n)


# T21 — no journal/receipt/RPC ALTER/DROP
def test_no_journal_receipt_rpc_drop_alter():
    n = _norm(_up() + "\n" + _down())
    for obj in ("safety_inspection_record_journal", "safety_inspection_command_receipt",
                "safety_inspection_creation_receipt", "fn_apply_inspection_record_command",
                "fn_create_worker_inspection_record", "fn_start_safe_inspection_record"):
        assert not re.search(rf"drop\s+\w+[^;]*{obj}", n), obj
        assert not re.search(rf"alter\s+\w+[^;]*{obj}", n), obj


# T22 — DOWN drops header trigger
def test_down_drops_header_trigger():
    n = _norm(_down())
    assert f"drop trigger if exists {T_HDR} on public.safety_inspections" in n


# T23 — DOWN drops result trigger
def test_down_drops_result_trigger():
    n = _norm(_down())
    assert f"drop trigger if exists {T_RES} on public.safety_inspection_results" in n


# T24 — DOWN drops the reject function AFTER both triggers
def test_down_drops_function_after_triggers():
    d = _down()
    i_hdr = d.find(T_HDR)
    i_res = d.find(T_RES)
    i_fn = d.find(f"DROP FUNCTION IF EXISTS public.{FN}")
    assert 0 <= i_hdr and 0 <= i_res and 0 <= i_fn
    assert i_fn > i_hdr and i_fn > i_res


# T25 — DOWN touches no other object (only 2 triggers + 1 function dropped)
def test_down_touches_no_other_object():
    n = _norm(_down())
    assert n.count("drop trigger") == 2
    assert n.count("drop function") == 1
    assert "drop table" not in n
    assert "drop index" not in n
    assert "create " not in n
    assert "alter " not in n


# LOCK — UP takes SHARE MODE lock on both base tables
def test_up_locks_both_tables_share_mode():
    n = _norm(_up())
    assert re.search(
        r"lock table public\.safety_inspections, public\.safety_inspection_results in share mode", n)


# T26 — header trigger set to ENABLE ALWAYS (fires regardless of replication role)
def test_header_trigger_enable_always():
    n = _norm(_up())
    assert "alter table public.safety_inspections enable always trigger trg_safety_inspections_immutable" in n


# T27 — result trigger set to ENABLE ALWAYS
def test_result_trigger_enable_always():
    n = _norm(_up())
    assert "alter table public.safety_inspection_results enable always trigger trg_safety_inspection_results_immutable" in n


# T28 — both triggers are ENABLE ALWAYS; neither left ordinary/replica/disabled
def test_no_ordinary_enable_only():
    n = _norm(_up())
    assert n.count("enable always trigger") == 2
    assert "enable replica trigger" not in n
    assert "disable trigger" not in n


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((k, v) for k, v in g.items() if k.startswith("test_") and callable(v))
    p = f = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); p += 1
        except Exception as e:
            import traceback
            print(f"FAIL {name}: {e}"); traceback.print_exc(); f += 1
    print(f"\n== {p} passed, {f} failed / {p + f} total ==")
    raise SystemExit(1 if f else 0)
