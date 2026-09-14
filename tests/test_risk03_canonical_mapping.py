"""WO-RISK-03 canonical identity and controlled mapping fixtures. No LLM, no DB write."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import path_source_key
from tools.risk03.candidates import (
    approved_exact_equivalent_conflicts,
    build_candidate_plan,
    classify_source_node,
    generate_candidates,
    mapping_nodes_for_source,
    summarize_candidates,
)
from tools.risk03.contract import (
    B_IDENTITY,
    B_LEAF_OCCURRENCE_SUM,
    B_PATH_IDENTITIES,
    C_OCCURRENCE,
    C_UNIQUE,
    EXISTING_PROCESS_TASK_OBJECTS,
    FIXTURE_PROCESS_ID,
    FIXTURE_TASK_ID,
    INSTANCE_VS_CANONICAL,
    PHYSICAL_MODEL_DECISION,
)
from tools.risk03.fixtures import ambiguity_canonical_nodes, synthetic_canonical_nodes
from tools.risk03.identity import (
    canonical_path,
    is_consumer_eligible,
    mapping_target_allowed,
    proposal_key,
)

SQL = Path("supabase/migrations/20260916_risk_canonical_mapping.sql")
RISK02_SQL = Path("supabase/migrations/20260915_risk_source_catalog.sql")
CANDIDATES = Path("tools/risk03/candidates.py")
IDENTITY = Path("tools/risk03/identity.py")
ARTIFACTS = Path("artifacts/risk01")


def _source_node(**over):
    node = {
        "source_id": SOURCE_KALIS,
        "source_key": path_source_key("건축", "토공사", "터파기"),
        "parent_source_key": path_source_key("건축", "토공사"),
        "native_code": None,
        "node_type": "TASK",
        "depth": 3,
        "name_raw": "터파기",
        "name_normalized": "터파기",
        "path_raw": "건축 > 토공사 > 터파기",
        "path_normalized": "건축 > 토공사 > 터파기",
    }
    node.update(over)
    return node


def test_existing_schema_decision_is_new_risk_canonical():
    kinds = {item[1] for item in EXISTING_PROCESS_TASK_OBJECTS}
    names = {item[0] for item in EXISTING_PROCESS_TASK_OBJECTS}
    assert PHYSICAL_MODEL_DECISION == "NEW_RISK_CANONICAL"
    assert INSTANCE_VS_CANONICAL == "PASS"
    assert "INSTANCE" in kinds
    assert "factory_process" in names
    assert "kcsc_process_master" in names
    assert "ksic_process_map" in names
    assert "risk_source_nodes" in names
    assert "tai_process" not in names
    assert "tai_task" not in names


def test_sql_canonical_identity_and_mapping_contract():
    text = SQL.read_text(encoding="utf-8")
    risk02 = RISK02_SQL.read_text(encoding="utf-8")
    assert "public.risk_canonical_nodes" in text
    assert "public.risk_source_mappings" in text
    assert "public.risk_canonical_node_sectors" in text
    assert "CHECK (node_kind IN ('PROCESS', 'TASK'))" in text
    assert "CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED'))" in text
    assert "DEFAULT 'DRAFT'" in text
    assert "FOREIGN KEY (source_id, source_key)" in text
    assert "REFERENCES public.risk_source_nodes (source_id, source_key)" in text
    mappings_sql = text.split("CREATE TABLE IF NOT EXISTS public.risk_source_mappings")[1]
    mappings_sql = mappings_sql.split("CREATE UNIQUE INDEX")[0]
    assert "canonical_id uuid REFERENCES public.risk_canonical_nodes (id)" in mappings_sql
    assert "canonical_id uuid NOT NULL" not in mappings_sql
    assert "CONSTRAINT risk_source_mappings_target_contract" in text
    assert "mapping_type = 'NO_MATCH'" in text
    assert "canonical_id IS NULL" in text
    assert "mapping_status IN ('HOLD', 'REJECTED')" in text
    assert "mapping_type <> 'NO_MATCH'" in text
    assert "canonical_id IS NOT NULL" in text
    assert "risk_source_mappings_one_approved_exact" in text
    assert "WHERE mapping_status = 'APPROVED' AND mapping_type = 'EXACT_EQUIVALENT'" in text
    assert "risk_source_mappings_one_no_match" in text
    assert "WHERE mapping_type = 'NO_MATCH'" in text
    assert "CHECK (sector_code" not in text
    assert "CONSTRUCTION')" not in text.split("risk_canonical_nodes")[1][:800]
    assert "FACILITY" not in text
    assert "datetime.now" not in text
    assert "created_at" not in text
    assert "knowledge_relation" not in text
    assert "kosha_msds" not in text
    assert "No TAI canonical process/task tables" in risk02


def test_canonical_id_survives_source_rename_and_reparent():
    nodes = synthetic_canonical_nodes()
    process = dict(nodes[0])
    task = dict(nodes[1])
    original_id = task["id"]
    task["name"] = "굴착"
    task["name_normalized"] = "굴착"
    task["parent_id"] = None
    source_changed = _source_node(source_key="changed-source-key")
    assert task["id"] == original_id == FIXTURE_TASK_ID
    assert process["id"] == FIXTURE_PROCESS_ID
    assert task["id"] != source_changed["source_key"]
    assert task["id"] != path_source_key("토공사", "터파기")
    assert "번호" not in task["id"]


def test_mapping_status_consumer_rule():
    assert is_consumer_eligible("APPROVED") is True
    assert is_consumer_eligible("PROPOSED") is False
    assert is_consumer_eligible("HOLD") is False
    assert is_consumer_eligible("REJECTED") is False


def test_exact_name_is_proposed_possible_related_not_approved():
    rows = classify_source_node(_source_node(), synthetic_canonical_nodes())
    assert len(rows) == 1
    assert rows[0]["candidate_class"] == "EXACT_NAME_CANDIDATE"
    assert rows[0]["mapping_type"] == "POSSIBLE_RELATED"
    assert rows[0]["mapping_status"] == "PROPOSED"
    assert rows[0]["mapping_method"] == "EXACT_NAME"
    assert is_consumer_eligible(rows[0]["mapping_status"]) is False
    assert rows[0]["evidence"]["source_path"]
    assert rows[0]["evidence"]["canonical_path"] == "토공사 > 터파기"
    assert rows[0]["evidence"]["canonical_parent"] == "토공사"


def test_exact_path_is_still_not_auto_equivalent():
    node = _source_node(
        path_normalized="토공사 > 터파기",
        name_normalized="터파기",
    )
    rows = classify_source_node(node, synthetic_canonical_nodes())
    assert rows[0]["candidate_class"] == "EXACT_PATH_CANDIDATE"
    assert rows[0]["mapping_type"] == "POSSIBLE_RELATED"
    assert rows[0]["mapping_status"] == "PROPOSED"
    assert rows[0]["mapping_type"] != "EXACT_EQUIVALENT"


def test_ambiguous_same_name_multiple_canonical_contexts():
    rows = classify_source_node(_source_node(), ambiguity_canonical_nodes())
    assert {row["candidate_class"] for row in rows} == {"AMBIGUOUS"}
    assert {row["mapping_type"] for row in rows} == {"AMBIGUOUS"}
    assert {row["mapping_status"] for row in rows} == {"HOLD"}
    assert len(rows) == 2
    assert all(not is_consumer_eligible(row["mapping_status"]) for row in rows)


def test_b_hold_maps_path_nodes_not_row_numbers():
    leaf_key = path_source_key("빌딩", "조적", "미장 및 견출작업")
    b_leaf = _source_node(
        source_id=SOURCE_KOSHA,
        source_key=leaf_key,
        node_type="DETAIL_PROCESS",
        name_raw="미장 및 견출작업",
        name_normalized="미장 및 견출작업",
        path_normalized="빌딩 > 조적 > 미장 및 견출작업",
    )
    parents = [
        _source_node(
            source_id=SOURCE_KOSHA,
            source_key=path_source_key("빌딩"),
            node_type="PROJECT_KIND",
            name_normalized="빌딩",
            path_normalized="빌딩",
        )
    ]
    mapped = mapping_nodes_for_source(SOURCE_KOSHA, parents + [b_leaf])
    assert mapped == [b_leaf]
    assert "번호" not in b_leaf["source_key"]
    assert B_IDENTITY == "HOLD"


def test_c_records_are_not_canonicalized():
    task = _source_node()
    recordish = _source_node(node_type="RECORD", source_key="content-key")
    mapped = mapping_nodes_for_source(SOURCE_KALIS, [task, recordish])
    assert mapped == [task]
    rows = generate_candidates([task])
    assert all(row["source_key"] != "content-key" for row in rows)


def test_unmatched_is_no_match_hold_evidence():
    node = _source_node(name_normalized="존재하지않는작업", path_normalized="건축 > 토공사 > 존재하지않는작업")
    rows = classify_source_node(node, synthetic_canonical_nodes())
    assert rows[0]["candidate_class"] == "UNMATCHED"
    assert rows[0]["mapping_type"] == "NO_MATCH"
    assert rows[0]["mapping_status"] == "HOLD"
    assert rows[0]["canonical_id"] is None
    assert mapping_target_allowed("NO_MATCH", None, "HOLD") is True
    assert is_consumer_eligible(rows[0]["mapping_status"]) is False


def test_no_match_target_contract():
    assert mapping_target_allowed("NO_MATCH", None, "HOLD") is True
    assert mapping_target_allowed("NO_MATCH", None, "REJECTED") is True
    assert mapping_target_allowed("NO_MATCH", FIXTURE_PROCESS_ID, "HOLD") is False
    assert mapping_target_allowed("NO_MATCH", None, "APPROVED") is False
    assert mapping_target_allowed("POSSIBLE_RELATED", None, "PROPOSED") is False
    assert mapping_target_allowed("EXACT_EQUIVALENT", None, "APPROVED") is False
    assert mapping_target_allowed("AMBIGUOUS", None, "HOLD") is False
    assert mapping_target_allowed("POSSIBLE_RELATED", FIXTURE_PROCESS_ID, "PROPOSED") is True
    text = SQL.read_text(encoding="utf-8")
    assert "CONSTRAINT risk_source_mappings_target_contract" in text
    assert "AND mapping_status IN ('HOLD', 'REJECTED')" in text


def test_no_match_unique_index_one_row_per_source_node():
    text = SQL.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS risk_source_mappings_one_no_match" in text
    assert "ON public.risk_source_mappings (source_id, source_key)" in text
    assert "WHERE mapping_type = 'NO_MATCH'" in text


def test_approved_exact_equivalent_cannot_fork():
    rows = [
        {
            "source_id": SOURCE_CIC_W,
            "source_key": "21",
            "canonical_id": FIXTURE_PROCESS_ID,
            "mapping_type": "EXACT_EQUIVALENT",
            "mapping_status": "APPROVED",
        },
        {
            "source_id": SOURCE_CIC_W,
            "source_key": "21",
            "canonical_id": FIXTURE_TASK_ID,
            "mapping_type": "EXACT_EQUIVALENT",
            "mapping_status": "APPROVED",
        },
    ]
    assert approved_exact_equivalent_conflicts(rows)


def test_proposal_key_excludes_timestamp_and_is_deterministic():
    key1 = proposal_key(SOURCE_CIC_W, "21", FIXTURE_PROCESS_ID, "POSSIBLE_RELATED")
    key2 = proposal_key(SOURCE_CIC_W, "21", FIXTURE_PROCESS_ID, "POSSIBLE_RELATED")
    assert key1 == key2
    assert key1 != proposal_key(SOURCE_CIC_W, "22", FIXTURE_PROCESS_ID, "POSSIBLE_RELATED")


def test_no_llm_fuzzy_embedding_in_risk03_logic():
    src = CANDIDATES.read_text(encoding="utf-8") + IDENTITY.read_text(encoding="utf-8")
    lower = src.lower()
    assert "openai" not in lower
    assert "embedding" not in lower
    assert "rapidfuzz" not in lower
    assert "levenshtein" not in lower
    assert "semantic_auto_merge" not in lower
    assert inspect.getsource(generate_candidates)


def test_a_w_code_is_mapping_evidence_not_canonical_id():
    a_node = _source_node(
        source_id=SOURCE_CIC_W,
        source_key="21",
        native_code="21",
        node_type="W_ROOT",
        name_normalized="토공사",
        path_normalized="토공사",
    )
    rows = classify_source_node(a_node, synthetic_canonical_nodes())
    assert a_node["source_key"] == "21"
    assert rows[0]["canonical_id"] == FIXTURE_PROCESS_ID
    assert rows[0]["canonical_id"] != "21"


def test_canonical_path_uses_hierarchy_not_leaf_only():
    nodes = {n["id"]: n for n in synthetic_canonical_nodes()}
    assert canonical_path(nodes, nodes[FIXTURE_TASK_ID]) == "토공사 > 터파기"


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required for full candidate census",
)
def test_full_candidate_census_and_determinism():
    first = build_candidate_plan(ARTIFACTS)
    second = build_candidate_plan(ARTIFACTS)
    assert first["PHYSICAL_MODEL_DECISION"] == "NEW_RISK_CANONICAL"
    assert first["AUTO_APPROVED"] == 0
    assert first["B"]["identity"] == "HOLD"
    assert first["B"]["raw_rows"] == 626
    assert first["B"]["path_identities"] == B_PATH_IDENTITIES
    assert first["B"]["leaf_occurrence_sum"] == B_LEAF_OCCURRENCE_SUM
    assert first["B"]["source_nodes_analyzed"] == 620
    assert first["C"]["unique_content"] == C_UNIQUE
    assert first["C"]["occurrence_sum"] == C_OCCURRENCE
    assert first["C"]["record_direct_canonical"] == 0
    assert first["A"]["approved_mappings"] == 0
    assert first["B"]["approved_mappings"] == 0
    assert first["C"]["approved_mappings"] == 0
    assert first["determinism_sha"] == second["determinism_sha"]
    assert first["db_write"] == 0
    metrics = summarize_candidates(first["_plan"]["candidates"], SOURCE_CIC_W)
    assert metrics["source_nodes_analyzed"] == first["A"]["source_nodes_analyzed"]
