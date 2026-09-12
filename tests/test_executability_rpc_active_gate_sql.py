"""PATCH-R3 — Stage1 atomic RPC active_yn fail-close (static SQL authority).

Authoritative registered migration (NOT production-applied in this WO):
  supabase/migrations/20260912070439_executability_rpc_active_gate.sql
Mirror:
  docs/sql/20260912_executability_rpc_active_gate_up.sql
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
MIG = os.path.abspath(
    os.path.join(
        HERE,
        "..",
        "supabase",
        "migrations",
        "20260912070439_executability_rpc_active_gate.sql",
    )
)
DOC = os.path.abspath(
    os.path.join(HERE, "..", "docs", "sql", "20260912_executability_rpc_active_gate_up.sql")
)


def _text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def test_migration_and_docs_sql_match():
    assert _text(MIG) == _text(DOC)


def test_start_rpc_active_yn_guard_before_side_effects():
    up = _text(MIG)
    n = _norm(up)
    assert "create or replace function public.fn_start_safe_inspection_record" in n
    assert "work_schedule_not_executable" in n
    assert "v_sched.active_yn is distinct from true" in n

    # start function segment
    idx_fn = up.find("CREATE OR REPLACE FUNCTION public.fn_start_safe_inspection_record")
    idx_worker = up.find("CREATE OR REPLACE FUNCTION public.fn_create_worker_inspection_record")
    start = up[idx_fn:idx_worker]
    idx_guard = start.find("WORK_SCHEDULE_NOT_EXECUTABLE")
    idx_update = start.find("UPDATE public.work_schedules")
    idx_insert = start.find("INSERT INTO public.safety_inspections")
    idx_replay = start.find("'replayed', true")
    assert 0 < idx_replay < idx_guard < idx_update < idx_insert


def test_worker_rpc_active_yn_guard_before_side_effects():
    up = _text(MIG)
    n = _norm(up)
    assert "create or replace function public.fn_create_worker_inspection_record" in n

    idx_worker = up.find("CREATE OR REPLACE FUNCTION public.fn_create_worker_inspection_record")
    worker = up[idx_worker:]
    # receipt replay remains before lock/guard (zero-mutation path)
    idx_receipt = worker.find("FROM public.safety_inspection_creation_receipt")
    idx_guard = worker.find("WORK_SCHEDULE_NOT_EXECUTABLE")
    idx_insert_insp = worker.find("INSERT INTO public.safety_inspections")
    idx_insert_res = worker.find("INSERT INTO public.safety_inspection_results")
    idx_insert_receipt = worker.find("INSERT INTO public.safety_inspection_creation_receipt")
    assert 0 <= idx_receipt < idx_guard < idx_insert_insp < idx_insert_res < idx_insert_receipt
    assert "v_sched.active_yn IS DISTINCT FROM TRUE" in worker


def test_pair_lock_and_grants_preserved():
    n = _norm(_text(MIG))
    assert (
        "from public.work_schedules where id = p_schedule_id and factory_id = p_factory_id for update"
        in n
    )
    assert "grant execute on function public.fn_start_safe_inspection_record" in n
    assert "grant execute on function public.fn_create_worker_inspection_record" in n
    assert "to service_role" in n
