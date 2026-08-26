"""OBJ-01 KNOT-3C1 — SAFE start atomic creator SQL contract tests.

up.sql 아티팩트 텍스트에 대한 정적 계약 검증(T1-T10). DB 접속 없음.
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260827_safe_inspection_start_atomic_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260827_safe_inspection_start_atomic_down.sql"))


def _up() -> str:
    with open(UP, encoding="utf-8") as f:
        return f.read()


def _down() -> str:
    with open(DOWN, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


# T1 — SECURITY DEFINER + fixed search_path
def test_security_definer_and_fixed_search_path():
    n = _norm(_up())
    assert "security definer" in n
    assert "set search_path = public, pg_temp" in n


# T2 — service_role EXECUTE only (revoke public/anon/authenticated, grant service_role)
def test_execute_grants_service_role_only():
    n = _norm(_up())
    assert "revoke all on function public.fn_start_safe_inspection_record" in n
    assert "from public, anon, authenticated" in n
    assert "grant execute on function public.fn_start_safe_inspection_record" in n
    assert "to service_role" in n


# T3 — parent pair SELECT ... FOR UPDATE (id AND factory_id, no fallback)
def test_parent_pair_for_update_lock():
    n = _norm(_up())
    assert "from public.work_schedules where id = p_schedule_id and factory_id = p_factory_id for update" in n


# T4 — cardinality check under lock, keyed on (assignment_id, factory_id)
def test_cardinality_check_keyed_on_pair():
    n = _norm(_up())
    assert "count(*) into v_count from public.safety_inspections where assignment_id = p_schedule_id and factory_id = p_factory_id" in n


# T5 — existing=1 → replay / mutation 0 (returns existing, replayed true)
def test_existing_one_replays_zero_mutation():
    up = _up()
    n = _norm(up)
    assert "v_count = 1" in n
    assert "'replayed', true" in n
    # replay branch must NOT insert/update (the insert/update live only in the fresh-create path)
    # ensure the replay RETURN happens before the schedule UPDATE / base INSERT text order
    idx_replay = up.find("'replayed', true")
    idx_update = up.find("UPDATE public.work_schedules")
    idx_insert = up.find("INSERT INTO public.safety_inspections")
    assert 0 < idx_replay < idx_update < idx_insert


# T6 — existing>1 → INSPECTION_CARDINALITY_VIOLATION
def test_existing_many_cardinality_violation():
    n = _norm(_up())
    assert "v_count > 1" in n
    assert "inspection_cardinality_violation" in n


# T7 — schedule UPDATE + base INSERT are in the SAME rpc body (one function, one txn)
def test_schedule_update_and_base_insert_same_body():
    up = _up()
    assert "UPDATE public.work_schedules" in up
    assert "INSERT INTO public.safety_inspections" in up
    # both between the single BEGIN ... $fn$ function body
    assert up.count("CREATE OR REPLACE FUNCTION public.fn_start_safe_inspection_record") == 1


# T8 — base lifecycle is exact uppercase IN_PROGRESS
def test_base_lifecycle_exact_in_progress():
    up = _up()
    assert "'IN_PROGRESS', p_factory_id)" in up
    # canonical uppercase; not the lowercase legacy string on the base insert
    m = re.search(r"INSERT INTO public\.safety_inspections.*?VALUES.*?;", up, re.S)
    assert m and "'IN_PROGRESS'" in m.group(0)
    assert "'in_progress'" not in m.group(0)


# T9 — no submitted_by write on the base insert
def test_no_submitted_by_write():
    up = _up()
    m = re.search(r"INSERT INTO public\.safety_inspections\s*\((.*?)\)", up, re.S)
    assert m and "submitted_by" not in m.group(1)


# T10 — no journal / command receipt / creation receipt / results write
def test_no_journal_receipt_results_write():
    n = _norm(_up())
    assert "safety_inspection_record_journal" not in n
    assert "safety_inspection_command_receipt" not in n
    assert "safety_inspection_creation_receipt" not in n
    assert "insert into public.safety_inspection_results" not in n


# DOWN — drops exact signature only
def test_down_drops_exact_signature():
    n = _norm(_down())
    assert "drop function if exists public.fn_start_safe_inspection_record(uuid, uuid, timestamptz, text)" in n


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
