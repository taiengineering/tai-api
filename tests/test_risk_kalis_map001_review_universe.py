"""WO-RISK-KALIS-MAP-001-R1 lean review-universe tests.

Delta-only per WO §16 / §21: verify only what this WO produces. No
regression across CIC_W / KOSHA / RISK-01/02/03. skip = 0.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kalis_map001_review_universe as gen

GENERATOR = Path("tools/risk_map/kalis_map001_review_universe.py")

FROZEN_TASK_UNIVERSE_SHA = (
    "6efd9047b4f6c001321c43496f27c21b538556b76fd2b90a6035cc2972db6ad4"
)
FROZEN_REVIEW_UNIVERSE_SHA = (
    "50446a5c9fa421f09beb1425ffe8d90649b29e50bafe93f46d8913a085ed497d"
)
FROZEN_REVIEW_SUMMARY_SHA = (
    "96b5dc4403078e33c325e22265b316dc1ba970aef4ee347e2e9143caae2aa8a0"
)


def test_input_universe_matches_expected_census():
    tasks = gen._load_kalis_task_nodes()
    assert len(tasks) == 761
    work_big = {t["work_big"] for t in tasks}
    assert len(work_big) == 7
    work_mid_pairs = {(t["work_big"], t["work_mid"]) for t in tasks}
    assert len(work_mid_pairs) == 48
    assert len({t["source_key"] for t in tasks}) == 761
    assert len({t["name_normalized"] for t in tasks}) == 40


def test_frozen_task_universe_sha():
    """The 761-row TASK universe is a committed intermediate SoT so CI can
    reproduce the review artifacts without the 10MB raw CSV."""
    from tools.risk04.seed_review import universe_sha
    rows = load_tsv(gen.TASK_UNIVERSE_PATH)
    assert len(rows) == 761
    assert list(rows[0].keys()) == list(gen.TASK_UNIVERSE_FIELDS)
    assert universe_sha(rows, *gen.TASK_UNIVERSE_FIELDS) == FROZEN_TASK_UNIVERSE_SHA


def test_review_universe_row_shape():
    rows = gen.build_review_universe()
    assert len(rows) == 761
    assert list(rows[0].keys()) == list(gen.REVIEW_UNIVERSE_FIELDS)


def test_review_universe_identity_uniqueness():
    rows = gen.build_review_universe()
    assert len({r["review_key"] for r in rows}) == 761
    assert len({r["source_key"] for r in rows}) == 761
    assert len({(r["review_key"], r["source_key"]) for r in rows}) == 761
    # review_key MUST NOT equal source_key on any row (WO §7 identity lock).
    assert not any(r["review_key"] == r["source_key"] for r in rows)


def test_family_key_is_grouping_aid_not_row_identity():
    rows = gen.build_review_universe()
    families = {r["family_key"] for r in rows}
    assert len(families) == 40  # <-- fewer than 761: grouping aid
    # Every task_name_normalized maps to exactly one family_key and vice versa.
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name_normalized"], set()).add(r["family_key"])
    for name, fkeys in by_name.items():
        assert len(fkeys) == 1, name
    by_family = {}
    for r in rows:
        by_family.setdefault(r["family_key"], set()).add(r["name_normalized"])
    for fkey, names in by_family.items():
        assert len(names) == 1, fkey


def test_family_coverage_sums_to_761():
    rows = gen.build_review_universe()
    summary = gen.build_review_summary(rows)
    assert len(summary) == 40
    assert sum(int(r["occurrence_count"]) for r in summary) == 761


def test_semantic_decision_fields_blank():
    rows = gen.build_review_universe()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_confidence_class"] == ""
        assert r["gpt_reason"] == ""


def test_candidate_count_in_range_and_ids_match_names():
    rows = gen.build_review_universe()
    for r in rows:
        n = int(r["candidate_count"])
        assert 0 <= n <= 10
        ids = r["candidate_canonical_ids"].split("|") if r["candidate_canonical_ids"] else []
        names = r["candidate_canonical_names"].split("|") if r["candidate_canonical_names"] else []
        assert len(ids) == n
        assert len(names) == n


def test_candidates_all_present_in_canonical_task_reference():
    ref = load_tsv(gen.CANONICAL_TASK_REFERENCE_PATH)
    valid = {r["canonical_id"] for r in ref}
    rows = gen.build_review_universe()
    for r in rows:
        for cid in filter(None, r["candidate_canonical_ids"].split("|")):
            assert cid in valid, (r["review_key"], cid)


def test_deterministic_shas():
    a = gen.build_review_universe()
    b = gen.build_review_universe()
    assert a == b
    assert gen.review_universe_sha(a) == gen.review_universe_sha(b) == FROZEN_REVIEW_UNIVERSE_SHA
    s_a = gen.build_review_summary(a)
    s_b = gen.build_review_summary(a)
    assert s_a == s_b
    assert gen.review_summary_sha(s_a) == gen.review_summary_sha(s_b) == FROZEN_REVIEW_SUMMARY_SHA


def test_written_universe_when_present():
    if not gen.REVIEW_UNIVERSE_PATH.exists():
        return
    rows = load_tsv(gen.REVIEW_UNIVERSE_PATH)
    assert len(rows) == 761
    assert list(rows[0].keys()) == list(gen.REVIEW_UNIVERSE_FIELDS)
    assert gen.review_universe_sha(rows) == FROZEN_REVIEW_UNIVERSE_SHA


def test_written_summary_when_present():
    if not gen.REVIEW_SUMMARY_PATH.exists():
        return
    rows = load_tsv(gen.REVIEW_SUMMARY_PATH)
    assert len(rows) == 40
    assert list(rows[0].keys()) == list(gen.REVIEW_SUMMARY_FIELDS)
    assert gen.review_summary_sha(rows) == FROZEN_REVIEW_SUMMARY_SHA
    assert sum(int(r["occurrence_count"]) for r in rows) == 761


def test_report_when_present():
    if not gen.REPORT_PATH.exists():
        return
    text = gen.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "THIS IS NOT SEMANTIC DECISION",
        "THIS IS NOT OWNER APPROVAL",
        "THIS IS NOT PRODUCTION MAPPING",
        "FAMILY IS REVIEW COMPRESSION AID",
        "FAMILY IS NOT CANONICAL IDENTITY",
        "KALIS production mappings =    0",
        "SEMANTIC DECISION = NOT EXECUTED",
        "MERGE = NOT AUTHORIZED",
        "FROZEN EVIDENCE REVERIFIED =\nNO",
    ):
        assert tag in text
    assert FROZEN_REVIEW_UNIVERSE_SHA in text
    assert FROZEN_REVIEW_SUMMARY_SHA in text


def test_existing_mapping_evidence_source_counts_match_frozen_totals():
    """WO §11: existing CIC_W / KOSHA APPROVED mappings are used as evidence
    only. Guard against silent drift in either side."""
    evidence = gen._load_existing_mapping_evidence()
    total_cic_w = sum(len(v["cic_w"]) for v in evidence.values())
    total_kosha = sum(len(v["kosha"]) for v in evidence.values())
    # Deduped source_name lists; each is ≤ its raw mapping count. CIC_W has 1139
    # rows but distinct source_name-per-canonical is a smaller number.
    # Assert lower bound = every canonical with at least one evidence row.
    assert total_cic_w > 0
    assert total_kosha > 0
    # KOSHA has 46 approved rows across 11 distinct canonicals — dedup by name
    # per canonical should stay ≥ 11.
    assert total_kosha >= 11


# ---------------------------------------------------------------------------
# Static-analysis guards
# ---------------------------------------------------------------------------


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


def test_no_production_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
    assert "DATABASE_URL" not in src
    assert "psycopg" not in src
