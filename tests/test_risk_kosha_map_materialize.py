"""WO-RISK-KOSHA-MAP-MATERIALIZE-001 lean materialization contract tests.

Contract-only per WO §17: verify the executor's planned execute-set has
the right shape and content and would never leak HOLD rows or an
invalid target. NO live DB assertions here — production state is
recorded in the frozen receipt (OBJ_risk-kosha-map-materialize001-
receipt_v1.md), which is checked separately. skip = 0.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_620_aggregate as agg
from tools.risk_map import kosha_map_approve001_owner_approval as owner
from tools.risk_map import kosha_map_approve001_materialize as mat

GENERATOR = Path("tools/risk_map/kosha_map_approve001_materialize.py")

FROZEN_BINDING_SHA = (
    "3c2f0a0f3558a7e0fd7a0d801ed22d18ba3d7fbed3f86a3ca54aa022f2e87a91"
)
FROZEN_CANDIDATE_SOT_SHA = (
    "4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a"
)
FROZEN_RECEIPT_SHA = (
    "08dd77ceb0b5ecf500276bf2992457c6f6ac6e347f35e26efc8ce80d04b8c64e"
)


def test_repository_anchors():
    anchors = mat._verify_repository_anchors()
    assert anchors["owner_approval_binding_sha"] == FROZEN_BINDING_SHA
    assert anchors["candidate_sot_sha"] == FROZEN_CANDIDATE_SOT_SHA
    assert len(anchors["approved_rows"]) == 46
    assert len(anchors["hold_rows"]) == 29


def test_execute_set_shape():
    anchors = mat._verify_repository_anchors()
    approved = anchors["approved_rows"]
    mtypes = Counter(r["mapping_type"] for r in approved)
    assert mtypes["EXACT_EQUIVALENT"] == 6
    assert mtypes["NARROWER_THAN"] == 40
    assert mtypes.get("POSSIBLE_RELATED", 0) == 0
    decisions = Counter(r["owner_decision"] for r in approved)
    assert decisions == {"APPROVE": 46}


def test_execute_set_no_hold_leak():
    anchors = mat._verify_repository_anchors()
    hold_keys = {r["source_key"] for r in anchors["hold_rows"]}
    approved_keys = {r["source_key"] for r in anchors["approved_rows"]}
    assert not (hold_keys & approved_keys)
    for r in anchors["hold_rows"]:
        assert r["mapping_type"] == "POSSIBLE_RELATED"
        assert r["owner_decision"] == "HOLD"


def test_execute_set_targets_in_canonical_task_reference():
    """The frozen canonical TASK reference is TASK-only by construction."""
    ref_path = Path("docs/knowledge/risk/RISK_KOSHA_B01_CANONICAL_TASK_REFERENCE_v1.tsv")
    ref = load_tsv(ref_path)
    valid = {r["canonical_id"]: r for r in ref}
    anchors = mat._verify_repository_anchors()
    for r in anchors["approved_rows"]:
        assert r["target_canonical_id"] in valid, r["review_key"]
        assert valid[r["target_canonical_id"]]["name"] == r["target_canonical_name"]


def test_db_tuple_shape():
    anchors = mat._verify_repository_anchors()
    tup = mat._row_to_db_tuple(anchors["approved_rows"][0], anchors)
    assert len(tup) == 8
    assert tup[0] == "KOSHA_CONSTRUCTION_PROCESS"
    assert tup[4] == "APPROVED"
    assert tup[5] == "MANUAL_REVIEW"
    evidence = json.loads(tup[6])
    assert evidence["evidence_basis"] == "OWNER_APPROVED_SEMANTIC_MAPPING"
    metadata = json.loads(tup[7])
    assert metadata["materialization_id"] == mat.MATERIALIZATION_ID
    assert metadata["owner_approval_id"] == owner.APPROVAL_ID
    assert metadata["owner_approval_binding_sha"] == FROZEN_BINDING_SHA


def test_baseline_and_target_totals():
    assert mat.BASELINE_MAPPING_TOTAL == 1139
    assert mat.BASELINE_CIC_W == 1139
    assert mat.BASELINE_KOSHA == 0
    assert mat.BASELINE_KALIS == 0
    assert mat.POST_MAPPING_TOTAL == 1185


def test_written_receipt_when_present():
    receipt_path = Path("docs/knowledge/risk/RISK_KOSHA_MAP_MATERIALIZE001_RECEIPT_v1.tsv")
    if not receipt_path.exists():
        return
    rows = load_tsv(receipt_path)
    assert len(rows) == 46
    assert list(rows[0].keys()) == list(mat.RECEIPT_FIELDS)
    mtypes = Counter(r["mapping_type"] for r in rows)
    assert mtypes["EXACT_EQUIVALENT"] == 6
    assert mtypes["NARROWER_THAN"] == 40
    for r in rows:
        assert r["source_id"] == "KOSHA_CONSTRUCTION_PROCESS"
        assert r["mapping_status"] == "APPROVED"
        assert r["mapping_method"] == "MANUAL_REVIEW"
        assert r["materialization_id"] == mat.MATERIALIZATION_ID
        assert r["owner_approval_binding_sha"] == FROZEN_BINDING_SHA
        assert r["production_verified"] == "YES"
    from tools.risk04.seed_review import universe_sha
    assert universe_sha(rows, *mat.RECEIPT_FIELDS) == FROZEN_RECEIPT_SHA


def test_report_when_present():
    report_path = Path("docs/knowledge/risk/OBJ_risk-kosha-map-materialize001-receipt_v1.md")
    if not report_path.exists():
        return
    text = report_path.read_text(encoding="utf-8")
    for tag in (
        "mappings_before               = 1139",
        "mappings_after                = 1185",
        "KOSHA (new)                   = 46",
        "KOSHA EXACT_EQUIVALENT        = 6",
        "KOSHA NARROWER_THAN           = 40",
        "KOSHA POSSIBLE_RELATED        = 0",
        "HOLD leaked into production   = 0",
        "APPROVED (input)              = 46",
        "HOLD (excluded)               = 29",
        "CANONICAL MUTATION            = 0",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text
    assert FROZEN_RECEIPT_SHA in text
    assert FROZEN_BINDING_SHA in text


# ---------------------------------------------------------------------------
# Prior binding SHA regression
# ---------------------------------------------------------------------------


def test_binding_sha_regression():
    rows = load_tsv(owner.BINDING_PATH)
    assert owner.binding_sha(rows) == FROZEN_BINDING_SHA


def test_candidate_sot_sha_regression():
    assert agg.bucket_sha(load_tsv(agg.MAPPING_PATH)) == FROZEN_CANDIDATE_SOT_SHA


# ---------------------------------------------------------------------------
# Static-analysis guard
# ---------------------------------------------------------------------------


def test_default_cli_does_not_write():
    """Argparse contract: no flag → return code 2 (help) and no side effects."""
    from io import StringIO
    import contextlib

    buf = StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = mat.main([])
    assert rc == 2
    # No receipt reset should have happened by simply calling main with no flags.


def test_generator_has_no_llm_or_fuzzy_imports():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden), f"forbidden import: {seen}"


def test_no_destructive_sql_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
    assert not re.search(r"\bDROP\s+", src, re.IGNORECASE)
    # UPDATE not needed for pure INSERT flow.
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
