"""OBJ-01 DEBT-W3-02 — SAFE result batch idempotency SQL contract tests.

up/down 아티팩트 텍스트 정적 검증. DB 접속 없음.
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260827_safe_result_batch_idempotency_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260827_safe_result_batch_idempotency_down.sql"))
FN = "fn_record_safe_inspection_result_batch"


def _up() -> str:
    with open(UP, encoding="utf-8") as f:
        return f.read()


def _down() -> str:
    with open(DOWN, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


# S1 — SECURITY DEFINER + fixed search_path
def test_security_definer_search_path():
    n = _norm(_up())
    assert "security definer" in n
    assert "set search_path = public, pg_temp" in n


# S2 — service_role EXECUTE only
def test_execute_service_role_only():
    n = _norm(_up())
    assert f"revoke all on function public.{FN}(uuid, jsonb) from public, anon, authenticated" in n
    assert f"grant execute on function public.{FN}(uuid, jsonb) to service_role" in n


# S3 — parent inspection FOR UPDATE lock (concurrency R7/R8)
def test_parent_for_update_lock():
    n = _norm(_up())
    assert "from public.safety_inspections where id = p_inspection_id for update" in n


# S4 — canonical result_code validation (R13)
def test_canonical_result_code_validation():
    n = _norm(_up())
    assert "not in ('normal','abnormal','hold')" in n
    assert "result_code_unresolved" in n


# S5 — empty results rejected (R12)
def test_empty_results_rejected():
    n = _norm(_up())
    assert "jsonb_array_length(p_results) = 0" in n
    assert "empty_results" in n


# S6 — existing=0 → INSERT batch → CREATED (R1)
def test_fresh_insert_created():
    n = _norm(_up())
    assert "v_count = 0" in n
    assert "insert into public.safety_inspection_results" in n
    assert "'mode', 'created'" in n


# S7 — single transaction-time checked_at for the batch
def test_single_checked_at():
    n = _norm(_up())
    assert "v_checked_at := now()" in n


# S8 — worker-shaped existing rows → conflict (R11); empty photo_urls '[]' is W3-shape (B3)
def test_worker_shaped_conflict():
    n = _norm(_up())
    assert "item_name is not null or value_text is not null" in n
    assert "photo_urls is not null and photo_urls <> '[]'::jsonb" in n
    assert "result_initial_batch_conflict" in n


# S9 — canonical order-independent STRUCTURED comparison → REPLAY / CONFLICT (R2..R6, R9, R10)
def test_canonical_compare_replay_conflict():
    up = _up()
    n = _norm(up)
    # structured tuples (no text separator), aggregated sorted (order-independent)
    assert "jsonb_build_array" in n
    assert "array_agg(t order by t)" in n
    # compares the W3 business fields only
    assert "result_code" in n and "note" in n and "photo_url" in n and "inspection_set_item_id" in n
    # equal -> replay, else conflict
    assert "is not distinct from" in n
    assert "'mode', 'replay'" in n
    assert n.count("result_initial_batch_conflict") >= 2   # worker-shape + differ


# S13 — B2: no text-separator key building (collision-proof structured comparison)
def test_no_text_separator_key():
    n = _norm(_up())
    assert "concat_ws" not in n
    assert "chr(31)" not in n
    assert "jsonb[]" in n            # keys declared as jsonb arrays, not text


# S10 — REPLAY inserts nothing: only one INSERT statement in the whole function,
#        and it lives in the fresh (v_count=0) branch before the comparison
def test_replay_inserts_nothing():
    up = _up()
    assert up.count("INSERT INTO public.safety_inspection_results") == 1
    idx_insert = up.find("INSERT INTO public.safety_inspection_results")
    idx_replay = up.find("'mode', 'REPLAY'")
    assert 0 < idx_insert < idx_replay   # insert is only in the fresh branch, before replay


# S11 — INSERT-only: no UPDATE/DELETE of base tables (immutability compatible, R17/R18)
def test_no_base_update_delete():
    n = _norm(_up() + "\n" + _down())
    assert not re.search(r"update\s+public\.safety_inspection", n)
    assert not re.search(r"delete\s+from\s+public\.safety_inspection", n)


# S12 — INSPECTION_NOT_FOUND when parent absent
def test_inspection_not_found():
    assert "inspection_not_found" in _norm(_up())


# DOWN — drops exact signature only
def test_down_drops_exact_signature():
    n = _norm(_down())
    assert f"drop function if exists public.{FN}(uuid, jsonb)" in n
    assert n.count("drop function") == 1


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
