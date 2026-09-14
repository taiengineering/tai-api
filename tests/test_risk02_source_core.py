"""WO-RISK-02 source catalog / snapshot / identity fixtures. No LLM, no DB write."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from tools.risk02.contract import C_HEADERS, SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import (
    b_row_identity,
    c_content_key,
    c_raw_payload,
    forbidden_identity_inputs,
    node_content_hash,
    path_source_key,
    sha256_parts,
)
from tools.risk02.plan_source_core import (
    _a_nodes,
    _b_nodes,
    _c_plan,
    b_membership_occurrence,
    build_plan,
)

SQL = Path("supabase/migrations/20260915_risk_source_catalog.sql")
PLANNER = Path("tools/risk02/plan_source_core.py")
IDENTITY = Path("tools/risk02/identity.py")
ARTIFACTS = Path("artifacts/risk01")


def _c_row(**over):
    raw = {h: "값" for h in C_HEADERS}
    raw["공종분류(대)"] = "건축"
    raw["공종분류(중)"] = "토공사"
    raw["작업프로세스명"] = "터파기"
    raw["사고가능성"] = "M(3)"
    raw["사고심각성"] = "H(4)"
    raw.update(over)
    return [raw[h] for h in C_HEADERS]


def test_sql_physical_schema_is_risk_family_not_graph():
    text = SQL.read_text(encoding="utf-8")
    for table in (
        "risk_sources",
        "risk_snapshots",
        "risk_source_nodes",
        "risk_records",
        "risk_snapshot_memberships",
    ):
        assert f"public.{table}" in text
    assert "CHECK (status IN ('STAGED', 'VALIDATED', 'ACCEPTED', 'REJECTED'))" in text
    assert "'PUBLISHED'" not in text
    assert "knowledge_relation" not in text
    assert "kosha_msds" not in text
    assert "occurrence_count" in text
    assert "raw_payload jsonb" in text
    assert "UNIQUE (id, source_id)" in text
    assert "CONSTRAINT risk_snapshot_memberships_snapshot_source_fkey" in text
    assert "FOREIGN KEY (snapshot_id, source_id)" in text
    assert "REFERENCES public.risk_snapshots (id, source_id)" in text
    assert "CONSTRAINT risk_records_task_node_fkey" in text
    assert "FOREIGN KEY (source_id, task_source_key)" in text
    assert "REFERENCES public.risk_source_nodes (source_id, source_key)" in text
    assert '"identity_status":"HOLD"' in text
    assert '"duplicate_path_groups":3' in text
    assert '"rows_in_duplicate_paths":9' in text


def test_sql_forbids_cross_source_snapshot_membership():
    text = SQL.read_text(encoding="utf-8")
    assert "CONSTRAINT risk_snapshot_memberships_snapshot_source_fkey" in text
    assert "FOREIGN KEY (snapshot_id, source_id)" in text
    assert "REFERENCES public.risk_snapshots (id, source_id)" in text
    assert "Cross-source membership is forbidden" in text


def test_a_native_code_identity_and_parent():
    text = "라. 공종분류(W) 01.토공사 011.굴착 0111.터파기 마. 자원분류"
    nodes, metrics = _a_nodes(text)
    assert [n["source_key"] for n in nodes] == ["01", "011", "0111"]
    assert nodes[2]["parent_source_key"] == "011"
    assert nodes[2]["native_code"] == "0111"
    assert metrics["identity"] == "PASS"
    assert metrics["orphan_parent"] == 0
    assert metrics["duplicate_source_key"] == 0


def test_b_path_identity_excludes_row_number():
    ident = b_row_identity("아파트", "토공사", "터파기")
    assert ident["source_id"] == SOURCE_KOSHA
    assert ident["source_key"] == path_source_key("아파트", "토공사", "터파기")
    assert ident["row_number_excluded"] is True
    header = ["번호", "공사종류", "공종명", "세부공정명"]
    rows = [["1", "아파트", "토공사", "터파기"], ["99", "아파트", "토공사", "터파기"]]
    _nodes, metrics = _b_nodes(header, rows)
    assert metrics["duplicate_path_groups"] == 1
    assert metrics["identity"] == "HOLD"


def test_b_duplicate_path_preserves_leaf_occurrence():
    header = ["번호", "공사종류", "공종명", "세부공정명"]
    rows = [
        ["148", "빌딩", "조적", "미장 및 견출작업"],
        ["149", "빌딩", "조적", "미장 및 견출작업"],
        ["150", "빌딩", "조적", "미장 및 견출작업"],
    ]
    nodes, metrics = _b_nodes(header, rows)
    leaves = [n for n in nodes if n["node_type"] == "DETAIL_PROCESS"]
    parents = [n for n in nodes if n["node_type"] != "DETAIL_PROCESS"]
    assert metrics["rows"] == 3
    assert metrics["leaf_membership_rows"] == 1
    assert metrics["leaf_occurrence_sum"] == 3
    assert metrics["duplicate_extras"] == 2
    assert metrics["occurrence_preservation"] == "PASS"
    assert metrics["identity"] == "HOLD"
    assert len(leaves) == 1
    leaf_occ = metrics["leaf_occurrence_counts"]
    assert b_membership_occurrence(leaves[0], leaf_occ) == 3
    assert all(b_membership_occurrence(n, leaf_occ) == 1 for n in parents)


def test_b_unique_path_is_pass():
    header = ["번호", "공사종류", "공종명", "세부공정명"]
    rows = [
        ["1", "아파트", "토공사", "터파기"],
        ["2", "아파트", "토공사", "되메움"],
    ]
    nodes, metrics = _b_nodes(header, rows)
    assert metrics["identity"] == "PASS"
    assert metrics["path_identities"] == 2
    assert metrics["orphan_parent"] == 0
    assert metrics["occurrence_preservation"] == "PASS"
    assert metrics["leaf_membership_rows"] == 2
    assert metrics["leaf_occurrence_sum"] == 2
    assert any(n["node_type"] == "DETAIL_PROCESS" for n in nodes)


def test_c_content_hash_and_duplicate_occurrence():
    row = _c_row()
    key = c_content_key(row)
    assert key == sha256_parts(*row)
    records, nodes, metrics = _c_plan(list(C_HEADERS), [row, row, _c_row(작업프로세스명="되메움")])
    assert metrics["raw_rows"] == 3
    assert metrics["unique_content"] == 2
    assert metrics["duplicate_groups"] == 1
    assert metrics["duplicate_extras"] == 1
    assert metrics["occurrence_sum"] == 3
    assert metrics["raw_19_fields_preserved"] is True
    payload = records[0]["raw_payload"]
    assert set(payload) == set(C_HEADERS)
    assert metrics["orphan_task_link"] == 0
    assert any(n["node_type"] == "TASK" for n in nodes)
    assert records[0]["likelihood"] == "M(3)"
    assert records[0]["task_source_key"]


def test_normalization_does_not_overwrite_raw():
    ident = b_row_identity(" 아파트 ", "토공사", "터파기")
    assert "아파트" in ident["path_raw"]
    rec = c_raw_payload(_c_row(작업프로세스명=" 터파기 "))
    assert rec["작업프로세스명"] == " 터파기 "


def test_timestamp_uuid_row_number_excluded_from_hash():
    row = _c_row()
    key1 = c_content_key(row)
    extra = {
        "created_at": "now",
        "updated_at": "now",
        "downloaded_at": "now",
        "id": "uuid",
        "uuid": "x",
        "row_number": 7,
        "번호": "1",
    }
    assert forbidden_identity_inputs(extra)
    assert c_content_key(row) == key1
    node_hash = node_content_hash(SOURCE_CIC_W, "21", None, "21", "W_ROOT", 1, "토공사", "토공사")
    assert "now" not in node_hash


def test_model_d_sources_stay_separate():
    a_key = "21"
    assert SOURCE_CIC_W != SOURCE_KOSHA
    assert SOURCE_KOSHA != SOURCE_KALIS
    assert (SOURCE_CIC_W, a_key) != (SOURCE_KOSHA, a_key)
    src = PLANNER.read_text(encoding="utf-8").lower() + IDENTITY.read_text(encoding="utf-8").lower()
    assert "openai" not in src
    assert "embedding" not in src
    assert "rapidfuzz" not in src
    assert "tai_process" not in src
    assert "tai_task" not in src
    assert inspect.getsource(build_plan)


def test_no_cross_source_auto_merge_helpers():
    src = PLANNER.read_text(encoding="utf-8") + IDENTITY.read_text(encoding="utf-8")
    lower = src.lower()
    assert "openai" not in lower
    assert "embedding" not in lower
    assert "rapidfuzz" not in lower
    assert "tai_process" not in lower
    assert "tai_task" not in lower


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required for full census",
)
def test_full_dry_run_census_and_determinism():
    first = build_plan(ARTIFACTS)
    second = build_plan(ARTIFACTS)
    assert first["A"]["nodes"] == 1722
    assert first["A"]["identity"] == "PASS"
    assert first["A"]["duplicate_source_key"] == 0
    assert first["B"]["rows"] == 626
    assert first["B"]["path_identities"] == 620
    assert first["B"]["duplicate_path_groups"] == 3
    assert first["B"]["rows_in_duplicate_paths"] == 9
    assert first["B"]["duplicate_extras"] == 6
    assert first["B"]["leaf_membership_rows"] == 620
    assert first["B"]["leaf_occurrence_sum"] == 626
    assert first["B"]["occurrence_preservation"] == "PASS"
    assert first["B"]["identity"] == "HOLD"
    b_nodes = first["_plan"]["b_nodes"]
    leaf_keys = {n["source_key"] for n in b_nodes if n["node_type"] == "DETAIL_PROCESS"}
    b_leaf_mem = [
        m
        for m in first["_plan"]["membership"]
        if m["source_id"] == SOURCE_KOSHA
        and m["member_kind"] == "NODE"
        and m["member_key"] in leaf_keys
    ]
    b_parent_mem = [
        m
        for m in first["_plan"]["membership"]
        if m["source_id"] == SOURCE_KOSHA
        and m["member_kind"] == "NODE"
        and m["member_key"] not in leaf_keys
    ]
    assert len(b_leaf_mem) == 620
    assert sum(m["occurrence_count"] for m in b_leaf_mem) == 626
    assert all(m["occurrence_count"] == 1 for m in b_parent_mem)
    assert first["C"]["raw_rows"] == 47559
    assert first["C"]["unique_content"] == 30696
    assert first["C"]["duplicate_groups"] == 5730
    assert first["C"]["duplicate_extras"] == 16863
    assert first["C"]["occurrence_sum"] == 47559
    assert first["C"]["membership_rows"] == 30696
    assert first["C"]["raw_19_fields_preserved"] is True
    assert first["C"]["content_identity"] == "PASS"
    assert first["integrity"]["C_orphan_task_link"] == 0
    assert first["determinism_sha"] == second["determinism_sha"]
    assert first["db_write"] == 0
    assert first["cross_source_merge"] == 0
    assert first["C"]["sha256"] == first["C"]["expected_sha256"]
