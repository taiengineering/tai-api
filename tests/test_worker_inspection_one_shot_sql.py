"""OBJ-01 KNOT-3B COMMIT A — worker one-shot SQL artifact contract (static).

DDL 을 실행하지 않고 docs/sql UP/DOWN 아티팩트의 구조 계약을 검증한다.
프로덕션 적용은 별도 승인 게이트에서 이뤄진다.

A-REV: BLOCKER 1..5 hardening (post-lock recheck ordering, exact canonical
result, service_role in REVOKE, no FORCE RLS, no submitted_by).
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
SQL_DIR = os.path.abspath(os.path.join(HERE, "..", "docs", "sql"))
UP = os.path.join(SQL_DIR, "20260827_worker_inspection_one_shot_up.sql")
DOWN = os.path.join(SQL_DIR, "20260827_worker_inspection_one_shot_down.sql")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_up_and_down_exist():
    assert os.path.exists(UP), UP
    assert os.path.exists(DOWN), DOWN


def test_creation_receipt_table_contract():
    up = _read(UP)
    assert "CREATE TABLE public.safety_inspection_creation_receipt" in up
    # PK
    assert re.search(r"id\s+uuid\s+PRIMARY KEY\s+DEFAULT gen_random_uuid\(\)", up)
    # submission_id UNIQUE NOT NULL
    assert re.search(r"submission_id\s+uuid\s+NOT NULL\s+UNIQUE", up)
    # inspection_id FK ON DELETE RESTRICT
    assert re.search(
        r"inspection_id\s+uuid\s+NOT NULL\s+REFERENCES public\.safety_inspections\(id\)\s+ON DELETE RESTRICT",
        up,
    )
    for col in ("source", "request_hash", "request_payload", "response_snapshot", "created_at"):
        assert re.search(rf"\b{col}\b", up), col


def test_rls_enabled_zero_policies_service_role_select_only():
    up = _read(UP)
    assert "ENABLE ROW LEVEL SECURITY" in up
    # no policies at all
    assert "CREATE POLICY" not in up
    # direct grants revoked (incl. service_role), then service_role SELECT only
    assert re.search(r"REVOKE ALL ON TABLE public\.safety_inspection_creation_receipt FROM PUBLIC, anon, authenticated, service_role", up)
    assert re.search(r"GRANT SELECT ON TABLE public\.safety_inspection_creation_receipt TO service_role", up)
    # no table-level INSERT/UPDATE/DELETE grant to anyone
    assert not re.search(r"GRANT[^;]*\b(INSERT|UPDATE|DELETE)\b[^;]*ON TABLE public\.safety_inspection_creation_receipt", up)


def test_append_only_trigger_reuses_foundation_reject_fn():
    up = _read(UP)
    assert re.search(
        r"CREATE TRIGGER trg_sicreation_append_only\s+BEFORE UPDATE OR DELETE ON public\.safety_inspection_creation_receipt\s+FOR EACH ROW EXECUTE FUNCTION public\.fn_reject_inspection_record_mutation\(\)",
        up,
    )


def test_rpc_attributes():
    up = _read(UP)
    assert "CREATE OR REPLACE FUNCTION public.fn_create_worker_inspection_record(" in up
    assert "RETURNS jsonb" in up
    assert "VOLATILE" in up
    assert "SECURITY DEFINER" in up
    assert "SET search_path = public, pg_temp" in up
    assert re.search(
        r"REVOKE ALL ON FUNCTION public\.fn_create_worker_inspection_record\([^)]*\) FROM PUBLIC, anon, authenticated",
        up,
    )
    assert re.search(
        r"GRANT EXECUTE ON FUNCTION public\.fn_create_worker_inspection_record\([^)]*\) TO service_role",
        up,
    )


def test_rpc_internal_order_and_invariants():
    up = _read(UP)
    # schedule serialization
    assert "FOR UPDATE" in up
    # receipt replay lookup precedes any INSERT
    idx_lookup = up.find("FROM public.safety_inspection_creation_receipt\n    WHERE submission_id = p_submission_id")
    idx_base_insert = up.find("INSERT INTO public.safety_inspections")
    assert idx_lookup != -1 and idx_base_insert != -1 and idx_lookup < idx_base_insert
    # base header exactly COMPLETED
    assert "'COMPLETED'" in up
    # canonical result validation
    assert "NOT IN ('NORMAL','ABNORMAL','HOLD')" in up
    assert "RESULT_CODE_UNRESOLVED" in up
    # base + results + creation receipt all inserted in the same function
    assert "INSERT INTO public.safety_inspections" in up
    assert "INSERT INTO public.safety_inspection_results" in up
    assert "INSERT INTO public.safety_inspection_creation_receipt" in up
    # conflict codes present
    for code in ("SUBMISSION_ID_REUSE_CONFLICT", "WORK_SCHEDULE_NOT_FOUND",
                 "FACTORY_MISMATCH", "INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE"):
        assert code in up, code


def test_rpc_writes_no_journal_or_command_receipt():
    up = _read(UP)
    assert "INSERT INTO public.safety_inspection_record_journal" not in up
    assert "INSERT INTO public.safety_inspection_command_receipt" not in up
    # creation is revision 0, no journal
    assert "'revision',          0" in up or "'revision', 0" in up


def test_down_drops_new_objects_only():
    down = _read(DOWN)
    assert "DROP FUNCTION IF EXISTS public.fn_create_worker_inspection_record(" in down
    assert "DROP TRIGGER IF EXISTS trg_sicreation_append_only" in down
    assert "DROP TABLE IF EXISTS public.safety_inspection_creation_receipt" in down
    # foundation objects and the shared reject fn must NOT be dropped
    assert "safety_inspection_record_journal" not in down
    assert "safety_inspection_command_receipt" not in down
    assert "fn_resolve_inspection_record" not in down
    assert "fn_apply_inspection_record_command" not in down
    assert "DROP FUNCTION IF EXISTS public.fn_reject_inspection_record_mutation" not in down
    assert "DROP TRIGGER" not in down.replace("DROP TRIGGER IF EXISTS trg_sicreation_append_only", "")


# ── A-REV hardening (BLOCKER 1..5) ─────────────────────────────────────────

def _receipt_lookup_positions(up):
    """모든 receipt lookup(SELECT ... FROM creation_receipt WHERE submission_id) 시작 위치."""
    return [m.start() for m in re.finditer(
        r"FROM public\.safety_inspection_creation_receipt\s+WHERE submission_id = p_submission_id", up)]


def test_arev_t1_receipt_lookup_before_lock():
    up = _read(UP)
    looks = _receipt_lookup_positions(up)
    lock = up.find("FOR UPDATE")
    assert len(looks) >= 2, "expected two receipt lookups (pre-lock + post-lock)"
    assert looks[0] < lock, "first receipt lookup must precede FOR UPDATE"


def test_arev_t2_receipt_lookup_again_after_lock_before_dupcheck():
    up = _read(UP)
    looks = _receipt_lookup_positions(up)
    lock = up.find("FOR UPDATE")
    dupcheck = up.find("SELECT count(*) INTO v_count")
    assert len(looks) >= 2
    # second lookup sits AFTER the lock and BEFORE the duplicate-inspection check
    assert lock < looks[1] < dupcheck, "second receipt lookup must be post-lock and pre-duplicate-check"


def test_arev_t3_and_t4_post_lock_replay_and_conflict_paths():
    up = _read(UP)
    lock = up.find("FOR UPDATE")
    dupcheck = up.find("SELECT count(*) INTO v_count")
    post_lock_block = up[lock:dupcheck]
    # post-lock block must contain BOTH a replay return and a reuse-conflict return
    assert "'replayed', true" in post_lock_block
    assert "SUBMISSION_ID_REUSE_CONFLICT" in post_lock_block


def test_arev_t5_no_upper_normalization_exact_canonical():
    up = _read(UP)
    assert "upper(" not in up, "no upper() normalization anywhere (exact canonical contract)"
    # explicit string-type + exact-value validation
    assert "jsonb_typeof(v_elem->'result_code') <> 'string'" in up
    assert "v_code := v_elem->>'result_code';" in up
    assert "v_code NOT IN ('NORMAL','ABNORMAL','HOLD')" in up


def test_arev_t6_service_role_in_revoke_then_select_grant():
    up = _read(UP)
    assert re.search(
        r"REVOKE ALL ON TABLE public\.safety_inspection_creation_receipt FROM PUBLIC, anon, authenticated, service_role",
        up,
    )
    revoke_pos = up.find("REVOKE ALL ON TABLE public.safety_inspection_creation_receipt")
    grant_pos = up.find("GRANT SELECT ON TABLE public.safety_inspection_creation_receipt TO service_role")
    assert revoke_pos != -1 and grant_pos != -1 and revoke_pos < grant_pos


def test_arev_t7_no_force_row_level_security():
    up = _read(UP)
    assert "FORCE ROW LEVEL SECURITY" not in up
    assert "ENABLE ROW LEVEL SECURITY" in up


def test_arev_t8_base_insert_omits_submitted_by():
    up = _read(UP)
    # locate the base header INSERT column list
    m = re.search(r"INSERT INTO public\.safety_inspections\s*\(([^)]*)\)", up)
    assert m, "base INSERT column list not found"
    cols = m.group(1)
    assert "submitted_by" not in cols, "submitted_by must not be written this KNOT"
    for c in ("id", "assignment_id", "inspector_id", "inspection_date", "status_code", "factory_id"):
        assert c in cols, c


if __name__ == "__main__":
    import sys
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); passed += 1
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}"); traceback.print_exc(); failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
