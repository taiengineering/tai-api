"""RISK-04-MATERIALIZE-001 approved DRAFT canonical plan. No ACTIVE and no mapping write."""
from __future__ import annotations

from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    FROZEN_FINAL_MANIFEST_SHA,
    FROZEN_HOLD_PACKAGE_SHA,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha,
    build_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import (
    FROZEN_BINDING_SHA,
    L02_CHILD_KEY,
    PLAN_FIELDS,
    PLAN_PATH,
    SQL_PATH,
    assemble_plan,
    assert_write_ready,
    l02_parent_leak,
    plan_audit,
    plan_sha,
    render_sql,
    sql_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    FINAL_MANIFEST_PATH,
    HOLD_PACKAGE_PATH,
    OWNER_PACKAGE_PATH,
    RESOLUTION_PATH,
    final_manifest_sha,
    hold_package_sha,
    owner_package_sha,
    resolution_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

GENERATOR = Path("tools/risk04/materialize001_approved_canonical_draft.py")
FROZEN_RESOLUTION_SHA = "d8e8558cba209fdae76a3f97b8255fa7d05aa3081b0c7868821e7d322cd3de55"


def test_approval_binding_exact():
    owner = load_tsv(OWNER_PACKAGE_PATH)
    hold = load_tsv(HOLD_PACKAGE_PATH)
    assert owner_package_sha(owner) == FROZEN_OWNER_PACKAGE_SHA
    assert hold_package_sha(hold) == FROZEN_HOLD_PACKAGE_SHA
    assert final_manifest_sha(load_tsv(FINAL_MANIFEST_PATH)) == FROZEN_FINAL_MANIFEST_SHA
    assert resolution_sha(load_tsv(RESOLUTION_PATH)) == FROZEN_RESOLUTION_SHA
    assert binding_sha(build_binding()) == FROZEN_BINDING_SHA
    assert len(owner) == 1110
    assert len(hold) == 1
    assert hold[0]["review_concept_key"] == L02_KEY
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in owner)
    assert L02_KEY not in {row["review_concept_key"] for row in owner}


def test_materialization_plan_contract():
    plan = load_tsv(PLAN_PATH)
    rebuilt = assemble_plan()
    audit = plan_audit(plan)
    leak = l02_parent_leak(plan)
    assert list(plan[0].keys()) == list(PLAN_FIELDS)
    assert len(plan) == 1110
    assert audit["rows"] == 1110
    assert audit["unique_keys"] == 1110
    assert audit["empty_label"] == 0
    assert audit["l02"] == 0
    assert audit["process"] + audit["task"] == 1110
    assert audit["promoted"] + audit["merged"] == 1110
    assert audit["tai_native"] == 0
    assert audit["draft"] == 1110
    assert audit["active"] == 0
    assert audit["code_assigned"] == 0
    assert audit["unknown_parent"] == 1
    assert audit["self_parent"] == 0
    assert audit["cycle"] == 0
    assert audit["mapping_rows"] == 0
    assert audit["sector_rows"] == 0
    assert L02_KEY not in {row["review_concept_key"] for row in plan}
    assert len(leak) == 1
    assert leak[0]["review_concept_key"] == L02_CHILD_KEY
    assert leak[0]["parent_review_concept_key"] == L02_KEY
    assert all(row["status"] == "DRAFT" for row in plan)
    assert all(row["canonical_code"] == "" for row in plan)
    assert all(row["origin_type"] != "TAI_NATIVE" for row in plan)
    assert {row["review_concept_key"] for row in plan} == {row["review_concept_key"] for row in rebuilt}
    assert plan_sha(plan) == plan_sha(rebuilt)


def test_write_gate_blocks_l02_parent():
    try:
        assert_write_ready(assemble_plan())
    except ValueError as exc:
        assert "PARENT_POINTS_TO_HOLD_L02" in str(exc)
        assert L02_CHILD_KEY in str(exc)
    else:
        raise AssertionError("write gate must block L-02 parent leak")


def test_sql_transaction_and_closed_writes():
    sql = SQL_PATH.read_text(encoding="utf-8")
    rebuilt = render_sql(assemble_plan())
    lowered = sql.lower()
    assert sql.strip().startswith("BEGIN") or "\nBEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql
    assert "RAISE EXCEPTION" in sql
    assert "gen_random_uuid()" in sql
    assert "uuid5" not in lowered
    assert "uuid4" not in sql
    assert "INSERT INTO public.risk_canonical_nodes" in sql
    assert "INSERT INTO public.risk_source_mappings" not in sql
    assert "INSERT INTO public.risk_canonical_node_sectors" not in sql
    assert "TAI-P-" not in sql
    assert "TAI-T-" not in sql
    assert "'ACTIVE'" not in sql or sql.count("status = 'ACTIVE'") >= 1
    assert "status,\n  origin_type" in sql or "'DRAFT'" in sql
    assert L02_KEY not in {row["review_concept_key"] for row in assemble_plan()}
    assert sql_sha(sql) == sql_sha(rebuilt)
    assert "DUPLICATE MATERIALIZATION GUARD" in sql
    assert "RISK03_SCHEMA_NOT_APPLIED_OR_DRIFTED" in sql


def test_generator_closed_surfaces():
    src = GENERATOR.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "uuid4" not in src
    assert "uuid5" not in lowered
    assert "psycopg" not in lowered
    assert "supabase" not in lowered
    assert "kiwipiepy" not in lowered
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*materialize001*"))


def test_determinism_two_runs():
    first = assemble_plan()
    second = assemble_plan()
    first_sql = render_sql(first)
    second_sql = render_sql(second)
    assert plan_sha(first) == plan_sha(second)
    assert sql_sha(first_sql) == sql_sha(second_sql)
    assert plan_sha(first) == plan_sha(load_tsv(PLAN_PATH))
    assert sql_sha(first_sql) == sql_sha(SQL_PATH.read_text(encoding="utf-8"))
