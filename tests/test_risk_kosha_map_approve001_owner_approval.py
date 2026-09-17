"""WO-RISK-KOSHA-MAP-APPROVE-001 lean owner-approval binding tests.

Lean scope per WO §11: 75 rows, 46 APPROVED / 29 HOLD / 0 REJECTED,
mapping-type census 6 / 40 / 29, pair set matches the frozen SoT
exactly, targets unchanged, generator carries no SQL write surface.
skip = 0.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_620_aggregate as agg
from tools.risk_map import kosha_map_approve001_owner_approval as owner

GENERATOR = Path("tools/risk_map/kosha_map_approve001_owner_approval.py")

FROZEN_MAPPING_CANDIDATES_SHA = (
    "4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a"
)
FROZEN_BINDING_SHA = (
    "3c2f0a0f3558a7e0fd7a0d801ed22d18ba3d7fbed3f86a3ca54aa022f2e87a91"
)


def test_binding_row_shape():
    rows = owner.build_binding()
    assert len(rows) == 75
    assert list(rows[0].keys()) == list(owner.BINDING_FIELDS)
    for r in rows:
        assert r["approval_id"] == owner.APPROVAL_ID
        assert r["source_aggregate_sha"] == FROZEN_MAPPING_CANDIDATES_SHA


def test_decision_census():
    rows = owner.build_binding()
    decisions = Counter(r["owner_decision"] for r in rows)
    mtypes = Counter(r["mapping_type"] for r in rows)
    assert decisions.get("APPROVE", 0) == 46
    assert decisions.get("HOLD", 0) == 29
    assert sum(1 for r in rows if r["owner_decision"] == "REJECT") == 0
    assert mtypes.get("EXACT_EQUIVALENT", 0) == 6
    assert mtypes.get("NARROWER_THAN", 0) == 40
    assert mtypes.get("POSSIBLE_RELATED", 0) == 29


def test_decision_map_binding_rule():
    rows = owner.build_binding()
    for r in rows:
        if r["mapping_type"] in {"EXACT_EQUIVALENT", "NARROWER_THAN"}:
            assert r["owner_decision"] == "APPROVE", r["review_key"]
            assert r["owner_reason"] == owner.REASON_APPROVE
        else:
            assert r["mapping_type"] == "POSSIBLE_RELATED", r["review_key"]
            assert r["owner_decision"] == "HOLD", r["review_key"]
            assert r["owner_reason"] == owner.REASON_HOLD


def test_pair_set_matches_frozen_candidate_sot():
    candidates = load_tsv(agg.MAPPING_PATH)
    assert agg.bucket_sha(candidates) == FROZEN_MAPPING_CANDIDATES_SHA
    cand_pairs = {(r["review_key"], r["source_key"]) for r in candidates}
    rows = owner.build_binding()
    binding_pairs = {(r["review_key"], r["source_key"]) for r in rows}
    assert binding_pairs == cand_pairs


def test_targets_unchanged_from_source():
    candidates = {(r["review_key"], r["source_key"]): r for r in load_tsv(agg.MAPPING_PATH)}
    rows = owner.build_binding()
    for r in rows:
        src = candidates[(r["review_key"], r["source_key"])]
        assert r["target_canonical_id"] == src["gpt_target_canonical_id"], r["review_key"]
        assert r["target_canonical_name"] == src["gpt_target_canonical_name"], r["review_key"]
        assert r["mapping_type"] == src["gpt_mapping_type"], r["review_key"]
        assert r["gpt_confidence_class"] == src["gpt_confidence_class"], r["review_key"]


def test_binding_deterministic_sha():
    a = owner.build_binding()
    b = owner.build_binding()
    assert a == b
    assert owner.binding_sha(a) == owner.binding_sha(b) == FROZEN_BINDING_SHA


def test_written_binding_when_present():
    if not owner.BINDING_PATH.exists():
        return
    rows = load_tsv(owner.BINDING_PATH)
    assert len(rows) == 75
    assert list(rows[0].keys()) == list(owner.BINDING_FIELDS)
    assert owner.binding_sha(rows) == FROZEN_BINDING_SHA


def test_receipt_when_present():
    if not owner.RECEIPT_PATH.exists():
        return
    text = owner.RECEIPT_PATH.read_text(encoding="utf-8")
    for tag in (
        "OWNER MAPPING APPROVAL EXECUTED",
        "APPROVED                   = 46",
        "HOLD                       = 29",
        "REJECTED                   = 0",
        "EXACT_EQUIVALENT APPROVED  = 6",
        "NARROWER_THAN APPROVED     = 40",
        "POSSIBLE_RELATED HOLD      = 29",
        "PRODUCTION MATERIALIZATION           = NOT EXECUTED",
        "MERGE                                = NOT AUTHORIZED",
        "KOSHA PRODUCTION MAPPINGS            = 0",
    ):
        assert tag in text
    assert FROZEN_BINDING_SHA in text
    assert FROZEN_MAPPING_CANDIDATES_SHA in text


# ---------------------------------------------------------------------------
# Prior aggregate SHA regression (WO §1 anchor)
# ---------------------------------------------------------------------------


def test_frozen_candidate_sot_sha_regression():
    assert agg.bucket_sha(load_tsv(agg.MAPPING_PATH)) == FROZEN_MAPPING_CANDIDATES_SHA


# ---------------------------------------------------------------------------
# WO §13 production-write guard
# ---------------------------------------------------------------------------


def test_no_sql_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)


def test_no_llm_or_fuzzy_or_dbclient():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "psycopg2",
        "psycopg",
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
