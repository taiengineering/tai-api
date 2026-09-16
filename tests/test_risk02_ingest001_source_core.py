"""WO-RISK-02-INGEST-001 production source core. Mapping write = 0. No canonical mutation."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.risk02.contract import A_SHA256, B_SHA256, C_SHA256, SOURCE_KOSHA
from tools.risk02.ingest001_source_core import (
    A_FILE,
    B_FILE,
    B_NODES,
    C_FILE,
    C_NODES,
    C_TASK_NODES,
    CANONICAL_MATERIALIZATION_RECEIPT_SHA,
    CANONICAL_RECEIPT_PATH,
    FROZEN_DETERMINISM_SHA,
    INGEST_ID,
    MANIFEST_FIELDS,
    MANIFEST_PATH,
    PLANNED_MEMBERSHIPS,
    RECEIPT_PATH,
    REPORT_PATH,
    artifacts_available,
    build_manifest,
    memberships_insert_sql,
    nodes_insert_sql,
    records_insert_sql,
    two_run_plan,
    verify_source_hashes,
)
from tools.risk04.materialize001_resume_effective_plan import FROZEN_RECEIPT_SHA, receipt_sha
from tools.risk04.review_decisions import load_tsv

GENERATOR = Path("tools/risk02/ingest001_source_core.py")
PLANNER = Path("tools/risk02/plan_source_core.py")
IDENTITY = Path("tools/risk02/identity.py")


def test_frozen_source_hash_constants():
    assert A_SHA256 == "bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29"
    assert B_SHA256 == "8e98fbb66d9e152a03425338d27fc738172cdf6dd5d46a36e7a5a06d80012b91"
    assert C_SHA256 == "399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8"
    assert FROZEN_DETERMINISM_SHA == "886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa"
    assert CANONICAL_MATERIALIZATION_RECEIPT_SHA == FROZEN_RECEIPT_SHA
    assert receipt_sha(load_tsv(CANONICAL_RECEIPT_PATH)) == FROZEN_RECEIPT_SHA


def test_generator_closed_surfaces():
    src = GENERATOR.read_text(encoding="utf-8") + PLANNER.read_text(encoding="utf-8") + IDENTITY.read_text(encoding="utf-8")
    lower = src.lower()
    assert "openai" not in lower
    assert "embedding" not in lower
    assert "rapidfuzz" not in lower
    assert "uuid5" not in lower
    assert "psycopg" not in lower
    assert "create_client" not in lower
    assert "INSERT INTO public.risk_source_mappings" not in src
    assert "INSERT INTO public.risk_canonical_node_sectors" not in src
    assert "INSERT INTO public.risk_canonical_nodes" not in src
    assert "This is an explicit evidence pack, not a classifier." in src
    assert "identity_status" in src
    assert "HOLD" in src
    assert INGEST_ID in src


def test_sql_builders_do_not_open_mapping():
    nodes_sql = nodes_insert_sql(
        [
            {
                "source_id": "CIC_W",
                "source_key": "01",
                "parent_source_key": None,
                "native_code": "01",
                "node_type": "W_ROOT",
                "depth": 1,
                "name_raw": "토공사",
                "name_normalized": "토공사",
                "path_raw": "토공사",
                "path_normalized": "토공사",
                "content_hash": "abc",
            }
        ]
    )
    rec_sql = records_insert_sql(
        [
            {
                "content_key": "k",
                "task_source_key": "t",
                "raw_payload": {"작업프로세스명": "터파기"},
            }
        ]
    )
    mem_sql = memberships_insert_sql("00000000-0000-0000-0000-000000000001", SOURCE_KOSHA, [])
    joined = nodes_sql + rec_sql + mem_sql
    assert "INSERT INTO public.risk_source_nodes" in nodes_sql
    assert "INSERT INTO public.risk_records" in rec_sql
    assert "ON CONFLICT (source_id, source_key) DO NOTHING" in nodes_sql
    assert "ON CONFLICT (source_id, content_key) DO NOTHING" in rec_sql
    assert "risk_source_mappings" not in joined
    assert "risk_canonical_node_sectors" not in joined
    assert "status = 'ACTIVE'" not in joined
    assert "canonical_code" not in joined


def test_manifest_shape_when_present():
    if not MANIFEST_PATH.exists():
        pytest.skip("ingest manifest not frozen yet")
    rows = load_tsv(MANIFEST_PATH)
    assert list(rows[0].keys()) == list(MANIFEST_FIELDS)
    assert {row["source_id"] for row in rows} == {"CIC_W", "KOSHA_CONSTRUCTION_PROCESS", "KALIS_RISK_PROFILE"}
    kosha = next(row for row in rows if row["source_id"] == "KOSHA_CONSTRUCTION_PROCESS")
    assert kosha["identity_status"] == "HOLD"
    assert kosha["raw_row_count"] == "626"
    assert kosha["unique_record_count"] == "620"
    kalis = next(row for row in rows if row["source_id"] == "KALIS_RISK_PROFILE")
    assert kalis["planned_record_count"] == "30696"
    assert REPORT_PATH.exists()
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "mapping write = 0" in report
    assert "MERGE = NOT AUTHORIZED" in report


@pytest.mark.skipif(not artifacts_available(), reason="local RISK-01 artifacts required for full census")
def test_full_census_hashes_and_determinism():
    measured = verify_source_hashes()
    assert measured["CIC_W"] == A_SHA256
    assert measured["KOSHA_CONSTRUCTION_PROCESS"] == B_SHA256
    assert measured["KALIS_RISK_PROFILE"] == C_SHA256
    plan = two_run_plan()
    assert plan["A"]["nodes"] == 1722
    assert plan["A"]["identity"] == "PASS"
    assert plan["B"]["rows"] == 626
    assert plan["B"]["path_identities"] == 620
    assert plan["B"]["duplicate_path_groups"] == 3
    assert plan["B"]["duplicate_extras"] == 6
    assert plan["B"]["leaf_occurrence_sum"] == 626
    assert plan["B"]["identity"] == "HOLD"
    assert plan["B"]["nodes"] == B_NODES
    assert plan["C"]["raw_rows"] == 47559
    assert plan["C"]["unique_content"] == 30696
    assert plan["C"]["duplicate_groups"] == 5730
    assert plan["C"]["duplicate_extras"] == 16863
    assert plan["C"]["occurrence_sum"] == 47559
    assert plan["C"]["nodes"] == C_NODES
    assert sum(1 for n in plan["_plan"]["c_nodes"] if n["node_type"] == "TASK") == C_TASK_NODES
    assert plan["integrity"]["A_orphan_parent"] == 0
    assert plan["integrity"]["B_orphan_parent"] == 0
    assert plan["integrity"]["C_orphan_task_link"] == 0
    assert len(plan["_plan"]["membership"]) == PLANNED_MEMBERSHIPS
    assert plan["determinism_sha"] == FROZEN_DETERMINISM_SHA
    assert plan["db_write"] == 0
    assert plan["cross_source_merge"] == 0
    manifest = build_manifest(plan)
    assert manifest[1]["identity_status"] == "HOLD"
    assert A_FILE.exists() and B_FILE.exists() and C_FILE.exists()


@pytest.mark.skipif(not RECEIPT_PATH.exists(), reason="production receipt not frozen yet")
def test_production_receipt_contract():
    rows = load_tsv(RECEIPT_PATH)
    by_source = {row["source_id"]: row for row in rows}
    assert len(rows) == 3
    assert set(by_source) == {"CIC_W", "KOSHA_CONSTRUCTION_PROCESS", "KALIS_RISK_PROFILE"}
    assert all(row["snapshot_status"] == "ACCEPTED" for row in rows)
    assert all(row["validation_status"] == "PASS" for row in rows)
    assert by_source["CIC_W"]["node_count"] == "1722"
    assert by_source["CIC_W"]["record_count"] == "0"
    assert by_source["KOSHA_CONSTRUCTION_PROCESS"]["node_count"] == str(B_NODES)
    assert by_source["KALIS_RISK_PROFILE"]["record_count"] == "30696"
    assert by_source["KALIS_RISK_PROFILE"]["occurrence_sum"] == "47559"
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "canonical DRAFT = 1110" in report
    assert "mapping write = 0" in report
