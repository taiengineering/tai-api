"""OBJ-01 KNOT-3C1 REV-1C — Worker RPC pair-lock corrective patch contract tests.

patch up/down 아티팩트 텍스트 정적 검증. DB 접속 없음.
UP  = pair lock + pair duplicate guard (CREATE OR REPLACE, service_role EXECUTE only)
DOWN = id-only lock + id-only duplicate guard (현행 prod 복구)
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260827_worker_inspection_pair_lock_patch_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260827_worker_inspection_pair_lock_patch_down.sql"))


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _norm(s):
    return re.sub(r"\s+", " ", s).lower()


# UP1 — CREATE OR REPLACE the exact function (does not DROP/rename)
def test_up_create_or_replace_same_function():
    n = _norm(_read(UP))
    assert "create or replace function public.fn_create_worker_inspection_record" in n
    assert "drop function" not in n


# UP2 — parent lock uses the pair (id AND factory_id) FOR UPDATE
def test_up_parent_pair_lock():
    n = _norm(_read(UP))
    assert "from public.work_schedules where id = p_schedule_id and factory_id = p_factory_id for update" in n


# UP3 — duplicate schedule guard uses the pair (assignment_id AND factory_id)
def test_up_duplicate_guard_pair():
    n = _norm(_read(UP))
    assert "count(*) into v_count from public.safety_inspections where assignment_id = p_schedule_id and factory_id = p_factory_id" in n


# UP4 — service_role EXECUTE only preserved
def test_up_execute_service_role_only():
    n = _norm(_read(UP))
    assert "revoke all on function public.fn_create_worker_inspection_record" in n
    assert "grant execute on function public.fn_create_worker_inspection_record" in n
    assert "to service_role" in n


# UP5 — unchanged semantics still present (receipt replay, factory mismatch, dup error, base insert)
def test_up_keeps_existing_semantics():
    n = _norm(_read(UP))
    assert "submission_id_reuse_conflict" in n
    assert "factory_mismatch" in n
    assert "inspection_already_exists_for_schedule" in n
    assert "insert into public.safety_inspections" in n
    assert "insert into public.safety_inspection_creation_receipt" in n


# DOWN1 — restores id-only lock (no factory_id in the lock predicate)
def test_down_parent_id_only_lock():
    n = _norm(_read(DOWN))
    assert "from public.work_schedules where id = p_schedule_id for update" in n
    assert "where id = p_schedule_id and factory_id = p_factory_id for update" not in n


# DOWN2 — restores id-only duplicate guard
def test_down_duplicate_guard_id_only():
    n = _norm(_read(DOWN))
    assert "count(*) into v_count from public.safety_inspections where assignment_id = p_schedule_id;" in n
    assert "assignment_id = p_schedule_id and factory_id = p_factory_id" not in n


# CROSS — up and down genuinely differ on the two predicates
def test_up_down_differ_on_pair_predicates():
    up, down = _norm(_read(UP)), _norm(_read(DOWN))
    assert ("id = p_schedule_id and factory_id = p_factory_id for update" in up) and \
           ("id = p_schedule_id and factory_id = p_factory_id for update" not in down)


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
