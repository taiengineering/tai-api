"""RISK-04-MATERIALIZE-001-R1 effective overlay plan. v1 frozen. No ACTIVE write."""
from __future__ import annotations

import uuid
from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha,
    build_binding,
)
from tools.risk04.approve002_parent_amendment_binding import (
    AMENDMENT_BINDING_PATH,
    FROZEN_AMENDMENT_SHA,
    amendment_binding_sha,
    build_amendment_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import (
    FROZEN_BINDING_SHA,
    PLAN_PATH as V1_PLAN_PATH,
    SQL_PATH as V1_SQL_PATH,
    plan_audit,
    plan_sha as v1_plan_sha,
    sql_sha,
)
from tools.risk04.materialize001_resume_effective_plan import (
    CHILD_KEY,
    FROZEN_AMENDMENT_BINDING_SHA,
    FROZEN_RECEIPT_SHA,
    FROZEN_V1_PLAN_SHA,
    FROZEN_V1_SQL_SHA,
    L02_KEY,
    NEW_PARENT_KEY,
    RECEIPT_FIELDS,
    RECEIPT_PATH,
    V2_PLAN_FIELDS,
    V2_PLAN_PATH,
    V2_SQL_PATH,
    assemble_v2_plan,
    l02_parent_leak,
    receipt_sha,
    render_v2_sql,
    v2_plan_sha,
)
from tools.risk04.recovery001_parent_amendment import amendment_sha, build_amendment
from tools.risk04.review018_final_resolution_owner_package import (
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import load_tsv

GENERATOR = Path("tools/risk04/materialize001_resume_effective_plan.py")


def test_frozen_anchors_unchanged():
    assert owner_package_sha(load_tsv(OWNER_PACKAGE_PATH)) == FROZEN_OWNER_PACKAGE_SHA
    assert binding_sha(load_tsv(BINDING_PATH)) == binding_sha(build_binding()) == FROZEN_BINDING_SHA
    assert amendment_sha(build_amendment()) == FROZEN_AMENDMENT_SHA
    assert amendment_binding_sha(load_tsv(AMENDMENT_BINDING_PATH)) == amendment_binding_sha(build_amendment_binding()) == FROZEN_AMENDMENT_BINDING_SHA
    assert v1_plan_sha(load_tsv(V1_PLAN_PATH)) == FROZEN_V1_PLAN_SHA
    assert sql_sha(V1_SQL_PATH.read_text(encoding="utf-8")) == FROZEN_V1_SQL_SHA


def test_v2_plan_contract():
    plan = load_tsv(V2_PLAN_PATH)
    rebuilt = assemble_v2_plan()
    audit = plan_audit(plan)
    child = next(row for row in plan if row["review_concept_key"] == CHILD_KEY)
    assert list(plan[0].keys()) == list(V2_PLAN_FIELDS)
    assert len(plan) == 1110
    assert audit["unique_keys"] == 1110
    assert audit["process"] == 556
    assert audit["task"] == 554
    assert audit["promoted"] == 1082
    assert audit["merged"] == 28
    assert audit["tai_native"] == 0
    assert audit["draft"] == 1110
    assert audit["active"] == 0
    assert audit["code_assigned"] == 0
    assert audit["unknown_parent"] == 0
    assert audit["self_parent"] == 0
    assert audit["cycle"] == 0
    assert len(l02_parent_leak(plan)) == 0
    assert L02_KEY not in {row["review_concept_key"] for row in plan}
    assert child["parent_review_concept_key"] == NEW_PARENT_KEY
    assert child["amendment_approval_id"] == "RISK-04-APPROVE-002"
    assert child["amendment_package_sha"] == FROZEN_AMENDMENT_SHA
    assert sum(1 for row in plan if row["amendment_approval_id"] == "RISK-04-APPROVE-002") == 1
    assert v2_plan_sha(plan) == v2_plan_sha(rebuilt)


def test_v2_sql_guards():
    sql = V2_SQL_PATH.read_text(encoding="utf-8")
    rebuilt = render_v2_sql(assemble_v2_plan())
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "RAISE EXCEPTION" in sql
    assert "gen_random_uuid()" in sql
    assert "uuid5" not in sql.lower()
    assert "uuid4" not in sql
    assert "INSERT INTO public.risk_canonical_nodes" in sql
    assert "INSERT INTO public.risk_source_mappings" not in sql
    assert "INSERT INTO public.risk_canonical_node_sectors" not in sql
    assert "DUPLICATE MATERIALIZATION GUARD" in sql
    assert "parent pointing to HOLD L-02" in sql
    assert CHILD_KEY in sql
    assert NEW_PARENT_KEY in sql
    assert sql_sha(sql) == sql_sha(rebuilt)


def test_generator_closed_surfaces():
    src = GENERATOR.read_text(encoding="utf-8")
    assert "uuid4" not in src
    assert "uuid5" not in src.lower()
    assert "psycopg" not in src.lower()
    assert "kiwipiepy" not in src.lower()
    assert "openai" not in src.lower()
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*materialize001*r1*"))


def test_determinism_two_runs():
    first = assemble_v2_plan()
    second = assemble_v2_plan()
    assert v2_plan_sha(first) == v2_plan_sha(second) == v2_plan_sha(load_tsv(V2_PLAN_PATH))
    assert sql_sha(render_v2_sql(first)) == sql_sha(render_v2_sql(second)) == sql_sha(V2_SQL_PATH.read_text(encoding="utf-8"))


def test_receipt_contract():
    receipt = load_tsv(RECEIPT_PATH)
    plan = {row["review_concept_key"]: row for row in load_tsv(V2_PLAN_PATH)}
    by_key = {row["review_concept_key"]: row for row in receipt}
    ids = [row["canonical_id"] for row in receipt]
    child = by_key[CHILD_KEY]
    parent = by_key[NEW_PARENT_KEY]
    parent_mismatch = 0
    for row in receipt:
        uuid.UUID(row["canonical_id"])
        if row["parent_canonical_id"] not in {"", "EMPTY"}:
            uuid.UUID(row["parent_canonical_id"])
            linked = by_key[row["parent_review_concept_key"]]
            if linked["canonical_id"] != row["parent_canonical_id"]:
                parent_mismatch += 1
        assert row["name"] == plan[row["review_concept_key"]]["name"]
        assert row["status"] == "DRAFT"
        assert row["approval_id"] == "RISK-04-APPROVE-001"
        assert row["approval_package_sha"] == FROZEN_OWNER_PACKAGE_SHA
        assert row["materialization_id"] == "RISK-04-MATERIALIZE-001"
        assert row["canonical_id"] != row["parent_canonical_id"]
    assert list(receipt[0].keys()) == list(RECEIPT_FIELDS)
    assert len(receipt) == 1110
    assert len(set(ids)) == 1110
    assert len(by_key) == 1110
    assert sum(1 for row in receipt if row["status"] == "ACTIVE") == 0
    assert L02_KEY not in by_key
    assert child["parent_canonical_id"] == parent["canonical_id"]
    assert child["parent_review_concept_key"] == NEW_PARENT_KEY
    assert child["amendment_approval_id"] == "RISK-04-APPROVE-002"
    assert child["amendment_package_sha"] == FROZEN_AMENDMENT_SHA
    assert parent_mismatch == 0
    assert receipt_sha(receipt) == FROZEN_RECEIPT_SHA
