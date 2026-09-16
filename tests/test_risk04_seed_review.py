"""WO-RISK-04 seed review and ingest readiness. No LLM, no DB write."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import path_source_key
from tools.risk03.candidates import mapping_nodes_for_source
from tools.risk04.identity import parent_path, proposed_kind, seed_proposal_key
from tools.risk04.ingest_readiness import migration_order_ok, schema_tables_present
from tools.risk04.review_batch import batch_rows, batch_sha, select_batch
from tools.risk04.seed_review import (
    build_mapping_candidates,
    build_report,
    build_seed_proposals,
    no_match_candidate,
)

SQL02 = Path("supabase/migrations/20260915_risk_source_catalog.sql")
SQL03 = Path("supabase/migrations/20260916_risk_canonical_mapping.sql")
RISK04 = Path("tools/risk04")
ARTIFACTS = Path("artifacts/risk01")
BATCH_TSV = Path("docs/knowledge/risk/RISK04_BATCH001.tsv")


def _node(source_id, node_type, name, path, source_key=None, **over):
    node = {
        "source_id": source_id,
        "source_key": source_key or path_source_key(*path.split(" > ")),
        "node_type": node_type,
        "name_raw": name,
        "name_normalized": name,
        "path_normalized": path,
        "path_raw": path,
    }
    node.update(over)
    return node


def test_schema_exists_and_no_new_migration():
    tables = schema_tables_present()
    assert all(tables.values())
    assert migration_order_ok() is True
    assert SQL02.exists() and SQL03.exists()
    added = list(Path("supabase/migrations").glob("2026091*_risk04*")) + list(
        Path("supabase/migrations").glob("*risk04*")
    )
    assert added == []


def test_proposal_key_deterministic_and_not_uuid():
    key1 = seed_proposal_key(SOURCE_CIC_W, "21", "PROCESS")
    key2 = seed_proposal_key(SOURCE_CIC_W, "21", "PROCESS")
    assert key1 == key2
    assert key1 != seed_proposal_key(SOURCE_CIC_W, "22", "PROCESS")
    assert "-" not in key1
    assert "번호" not in key1
    src = (RISK04 / "identity.py").read_text(encoding="utf-8")
    assert "import uuid" not in src
    assert "uuid4" not in src
    assert "uuid5" not in src
    assert "timestamp" not in src.lower()
    assert "row_number" not in src.lower()
    assert "datetime" not in src.lower()


def test_same_name_different_parent_is_flag_not_auto_hold():
    nodes = [
        _node(SOURCE_KALIS, "TASK", "터파기", "건축 > 토공사 > 터파기"),
        _node(SOURCE_KALIS, "TASK", "터파기", "토목 > 굴착공사 > 터파기"),
    ]
    proposals = build_seed_proposals(nodes)
    assert all(row["metadata"]["same_name_multi_parent"] is True for row in proposals)
    assert all(row["review_status"] != "HOLD" for row in proposals)
    assert all(row["review_status"] == "REVIEW_READY" for row in proposals)
    assert all(row["canonical_uuid"] is None for row in proposals)


def test_cross_source_exact_name_does_not_auto_merge():
    nodes = [
        _node(SOURCE_CIC_W, "W_ROOT", "토공사", "토공사", source_key="21"),
        _node(SOURCE_KOSHA, "DETAIL_PROCESS", "토공사", "아파트 > 토공사 > 토공사"),
    ]
    proposals = build_seed_proposals(nodes)
    assert len(proposals) == 2
    keys = {row["seed_proposal_key"] for row in proposals}
    assert len(keys) == 2
    assert all(row["metadata"]["auto_merged"] is False for row in proposals)
    kinds = {row["proposed_node_kind"] for row in proposals}
    assert kinds == {"PROCESS", "TASK"}


def test_exact_path_not_auto_approved():
    node = _node(SOURCE_CIC_W, "W_ROOT", "토공사", "토공사", source_key="21")
    proposals = build_seed_proposals([node])
    mappings = build_mapping_candidates(proposals)
    assert mappings[0]["recommended_mapping_type"] == "POSSIBLE_RELATED"
    assert mappings[0]["review_status"] != "APPROVED"
    assert proposals[0]["review_status"] == "REVIEW_READY"


def test_b_collision_one_proposal_occurrence_three():
    key = path_source_key("빌딩", "조적", "미장 및 견출작업")
    node = _node(
        SOURCE_KOSHA,
        "DETAIL_PROCESS",
        "미장 및 견출작업",
        "빌딩 > 조적 > 미장 및 견출작업",
        source_key=key,
    )
    proposals = build_seed_proposals([node], b_leaf_occ={key: 3})
    assert len(proposals) == 1
    assert proposals[0]["source_occurrence_support"] == 3
    assert proposals[0]["b_identity"] == "HOLD"
    assert "번호" not in proposals[0]["origin_source_key"]


def test_c_records_are_not_proposals():
    task = _node(SOURCE_KALIS, "TASK", "되메움", "건축 > 토공사 > 되메움")
    record = _node(SOURCE_KALIS, "RECORD", "되메움", "record-path", source_key="content")
    mapped = mapping_nodes_for_source(SOURCE_KALIS, [task, record])
    assert mapped == [task]
    assert proposed_kind(task) == "TASK"


def test_no_match_has_null_target_proposal():
    row = no_match_candidate(SOURCE_CIC_W, "99")
    assert row["target_seed_proposal_key"] is None
    assert row["recommended_mapping_type"] == "NO_MATCH"
    assert row["review_status"] == "HOLD"


def test_review_batch_deterministic_and_capped():
    nodes = [
        _node(SOURCE_CIC_W, "W_ROOT", f"공정{i:03d}", f"공정{i:03d}", source_key=str(i))
        for i in range(60)
    ] + [
        _node(SOURCE_KALIS, "TASK", f"작업{i:03d}", f"건축 > 토공사 > 작업{i:03d}")
        for i in range(60)
    ]
    proposals = build_seed_proposals(nodes)
    first = select_batch(proposals)
    second = select_batch(proposals)
    assert [row["seed_proposal_key"] for row in first] == [row["seed_proposal_key"] for row in second]
    view = batch_rows(first)
    assert len(view) == 100
    assert sum(1 for row in view if row["kind"] == "PROCESS") == 50
    assert sum(1 for row in view if row["kind"] == "TASK") == 50
    assert batch_sha(view) == batch_sha(batch_rows(second))
    assert parent_path("건축 > 토공사 > 터파기") == "건축 > 토공사"


def test_no_llm_or_approved_in_risk04_logic():
    blob = ""
    for path in RISK04.glob("*.py"):
        blob += path.read_text(encoding="utf-8").lower()
    assert "openai" not in blob
    assert "embedding" not in blob
    assert "rapidfuzz" not in blob
    assert "levenshtein" not in blob
    assert "semantic_auto_merge" not in blob


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required for full seed census",
)
def test_full_seed_census_and_determinism():
    first = build_report(ARTIFACTS)
    second = build_report(ARTIFACTS)
    assert first["A"]["source_nodes"] == 1722
    assert first["B"]["raw_rows"] == 626
    assert first["B"]["proposal_nodes"] == 620
    assert first["B"]["identity"] == "HOLD"
    assert first["B"]["occurrence_sum"] == 626
    assert first["C"]["task_nodes"] == 761
    assert first["C"]["unique_content"] == 30696
    assert first["C"]["occurrence_sum"] == 47559
    assert first["CANONICAL_UUID_CREATED"] == 0
    assert first["AUTO_APPROVED"] == 0
    assert first["ACTIVE_CANONICALS"] == 0
    assert first["APPROVED_DB_MAPPINGS"] == 0
    assert first["AUTO_MERGED"] == 0
    assert first["SEED_UNIVERSE"]["total"] == 1722 + 620 + 761
    assert first["REVIEW_BATCH_001"]["count"] == 100
    assert first["SOURCE_INGEST"] == "READY_WITH_HOLD"
    assert first["CANONICAL_INGEST"] == "NOT AUTHORIZED"
    assert first["MAPPING_INGEST"] == "NOT AUTHORIZED"
    assert first["mapping_approval_coverage"] == 0
    assert first["SOURCE_RELATION_REVIEW_UNIVERSE"] == 3103
    assert first["SEED_UNIVERSE_SHA"] == second["SEED_UNIVERSE_SHA"]
    assert first["MAPPING_REVIEW_SHA"] == second["MAPPING_REVIEW_SHA"]
    assert first["READINESS_SHA"] == second["READINESS_SHA"]
    assert first["REVIEW_BATCH_001"]["sha256"] == second["REVIEW_BATCH_001"]["sha256"]
    assert first["db_write"] == 0


def test_committed_batch_tsv_shape():
    rows = list(csv.DictReader(BATCH_TSV.open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 100
    assert sum(1 for row in rows if row["kind"] == "PROCESS") == 50
    assert sum(1 for row in rows if row["kind"] == "TASK") == 50
    assert all(row["review_status"] not in {"ACTIVE", "APPROVED"} for row in rows)
    assert all(row["seed_proposal_key"] for row in rows)
    assert len({row["seed_proposal_key"] for row in rows}) == 100
