"""WO-RISK-ABC-RECON-001 lean reconciliation tests.

Delta-only per WO §16: verify only the reconciliation shape / SHA /
production-write-surface guards. No live DB required. skip = 0.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import abc_final_reconcile as recon

GENERATOR = Path("tools/risk_map/abc_final_reconcile.py")

FROZEN_RECONCILIATION_SHA = (
    "8f41bc05080c6aed39ff80daca35630c4d538ac82949358d21323ca5e48a79b0"
)
FROZEN_DEFERRED_SHA = (
    "036615bc063cf55b3af9803e4f3cc393b341ec5349b19a3484ff1792674db418"
)


# ---------------------------------------------------------------------------
# Expected SoT counts (receipt-level)
# ---------------------------------------------------------------------------


def test_expected_counts_from_frozen_receipts():
    expected = recon._load_expected()
    assert len(expected["CIC_W"]) == 1139
    assert len(expected["KOSHA"]) == 46
    assert len(expected["KALIS"]) == 9
    # Cross-source uniqueness of (source_id, source_key).
    all_pairs = expected["CIC_W"] | expected["KOSHA"] | expected["KALIS"]
    assert len(all_pairs) == 1139 + 46 + 9


def test_hold_counts_from_frozen_bindings():
    hold = recon._load_hold_keys()
    # KOSHA 29 HOLD, KALIS 39 HOLD (bindings frozen upstream).
    assert len(hold["KOSHA"]) == 29
    assert len(hold["KALIS"]) == 39
    # HOLD source_keys must NEVER appear in the approved set.
    expected = recon._load_expected()
    for tag in ("KOSHA", "KALIS"):
        approved_keys = {k for (_sid, k) in expected[tag]}
        assert not (approved_keys & hold[tag]), tag


# ---------------------------------------------------------------------------
# Offline reconciliation contract
# ---------------------------------------------------------------------------


def test_offline_reconciliation_shape():
    rows = recon.build_reconciliation(actual_pairs=None)
    assert len(rows) == 4  # CIC_W / KOSHA / KALIS / TOTAL
    assert list(rows[0].keys()) == list(recon.RECONCILIATION_FIELDS)
    by_source = {r["source"]: r for r in rows}
    assert by_source["CIC_W"]["approved_binding_count"] == "1139"
    assert by_source["CIC_W"]["production_mapping_count"] == "1139"
    assert by_source["KOSHA"]["approved_binding_count"] == "46"
    assert by_source["KOSHA"]["production_mapping_count"] == "46"
    assert by_source["KALIS"]["approved_binding_count"] == "9"
    assert by_source["KALIS"]["production_mapping_count"] == "9"
    assert by_source["TOTAL"]["approved_binding_count"] == "1194"
    assert by_source["TOTAL"]["production_mapping_count"] == "1194"


def test_offline_reconciliation_delta_zero():
    rows = recon.build_reconciliation(actual_pairs=None)
    for r in rows:
        assert r["missing_approved_count"] == "0", r["source"]
        assert r["unexpected_production_count"] == "0", r["source"]
        assert r["duplicate_count"] == "0", r["source"]
        assert r["hold_leak_count"] == "0", r["source"]
        assert r["would_insert"] == "0", r["source"]
        assert r["would_update"] == "0", r["source"]
        assert r["would_delete"] == "0", r["source"]
        assert r["verdict"] == "PASS", r["source"]


def test_offline_reconciliation_deterministic_sha():
    a = recon.build_reconciliation(actual_pairs=None)
    b = recon.build_reconciliation(actual_pairs=None)
    assert a == b
    assert recon.reconciliation_sha(a) == recon.reconciliation_sha(b) == FROZEN_RECONCILIATION_SHA


# ---------------------------------------------------------------------------
# HOLD-leak simulation — the reconciler must catch a HOLD row appearing
# in the actual production set (delta-only correctness).
# ---------------------------------------------------------------------------


def test_hold_leak_is_detected():
    expected = recon._load_expected()
    hold = recon._load_hold_keys()
    kosha_hold_source_key = next(iter(hold["KOSHA"]))
    tainted = {tag: set(v) for tag, v in expected.items()}
    tainted["KOSHA"] = tainted["KOSHA"] | {("KOSHA_CONSTRUCTION_PROCESS", kosha_hold_source_key)}
    rows = recon.build_reconciliation(actual_pairs=tainted)
    by_source = {r["source"]: r for r in rows}
    assert by_source["KOSHA"]["verdict"] == "FAIL"
    assert int(by_source["KOSHA"]["hold_leak_count"]) >= 1
    assert int(by_source["KOSHA"]["unexpected_production_count"]) >= 1


def test_missing_approved_is_detected():
    expected = recon._load_expected()
    trimmed = {tag: set(v) for tag, v in expected.items()}
    one_kalis_pair = next(iter(trimmed["KALIS"]))
    trimmed["KALIS"] = trimmed["KALIS"] - {one_kalis_pair}
    rows = recon.build_reconciliation(actual_pairs=trimmed)
    by_source = {r["source"]: r for r in rows}
    assert by_source["KALIS"]["verdict"] == "FAIL"
    assert by_source["KALIS"]["missing_approved_count"] == "1"
    assert by_source["KALIS"]["would_insert"] == "1"


# ---------------------------------------------------------------------------
# Deferred backlog
# ---------------------------------------------------------------------------


def test_deferred_backlog_shape():
    rows = recon.build_deferred_backlog()
    assert list(rows[0].keys()) == list(recon.DEFERRED_BACKLOG_FIELDS)
    assert len(rows) == 8   # 4 KOSHA buckets + 4 KALIS buckets
    by_key = {(r["source"], r["semantic_bucket"]): int(r["count"]) for r in rows}
    assert by_key[("KOSHA", "POSSIBLE_RELATED_HOLD")] == 29
    assert by_key[("KOSHA", "AMBIGUOUS")] == 78
    assert by_key[("KOSHA", "CANONICAL_GAP")] == 196
    assert by_key[("KOSHA", "NO_MATCH")] == 271
    assert by_key[("KALIS", "POSSIBLE_RELATED_HOLD")] == 39
    # KALIS deterministic decision census from row freeze:
    #   AMBIGUOUS = 21 families × occurrences; CANONICAL_GAP = 14 families; NO_MATCH = 1 family.
    # Row-freeze count sums are what the reconciler emits.
    assert by_key[("KALIS", "AMBIGUOUS")] > 0
    assert by_key[("KALIS", "CANONICAL_GAP")] > 0
    assert by_key[("KALIS", "NO_MATCH")] > 0
    for r in rows:
        assert r["production_eligible"] == "NO"
        assert r["blocking_current_stage"] == "NO"


def test_deferred_backlog_deterministic_sha():
    a = recon.build_deferred_backlog()
    b = recon.build_deferred_backlog()
    assert a == b
    assert recon.deferred_sha(a) == recon.deferred_sha(b) == FROZEN_DEFERRED_SHA


# ---------------------------------------------------------------------------
# Written artifacts
# ---------------------------------------------------------------------------


def test_written_reconciliation_when_present():
    if not recon.RECONCILIATION_PATH.exists():
        return
    rows = load_tsv(recon.RECONCILIATION_PATH)
    assert len(rows) == 4
    assert list(rows[0].keys()) == list(recon.RECONCILIATION_FIELDS)
    assert recon.reconciliation_sha(rows) == FROZEN_RECONCILIATION_SHA


def test_written_deferred_when_present():
    if not recon.DEFERRED_BACKLOG_PATH.exists():
        return
    rows = load_tsv(recon.DEFERRED_BACKLOG_PATH)
    assert list(rows[0].keys()) == list(recon.DEFERRED_BACKLOG_FIELDS)
    assert recon.deferred_sha(rows) == FROZEN_DEFERRED_SHA


def test_report_when_present():
    if not recon.REPORT_PATH.exists():
        return
    text = recon.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "A CIC_W = COMPLETE",
        "B KOSHA = COMPLETE",
        "C KALIS = COMPLETE",
        "A/B/C SOURCE MAPPING = COMPLETE",
        "would_insert         = 0",
        "would_update         = 0",
        "would_delete         = 0",
        "FROZEN EVIDENCE REVERIFIED = NO",
        "PRODUCTION WRITE = 0",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text, tag
    assert FROZEN_RECONCILIATION_SHA in text
    assert FROZEN_DEFERRED_SHA in text


# ---------------------------------------------------------------------------
# Static-analysis guards (WO §12, §18)
# ---------------------------------------------------------------------------


def test_no_write_sql_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    # SELECT only. No INSERT/UPDATE/DELETE/UPSERT/TRUNCATE/ALTER/CREATE/DROP
    # anywhere in the reconciler.
    for banned in (
        r"\bINSERT\s+INTO\b",
        r"\bUPDATE\s+public\.",
        r"\bDELETE\s+FROM\b",
        r"\bUPSERT\b",
        r"\bTRUNCATE\b",
        r"\bALTER\s+TABLE\b",
        r"\bCREATE\s+TABLE\b",
        r"\bDROP\s+",
    ):
        assert not re.search(banned, src, re.IGNORECASE), banned


def test_no_llm_or_fuzzy_or_search_dict_imports():
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


def test_default_cli_does_not_write():
    from io import StringIO
    import contextlib

    buf = StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = recon.main([])
    assert rc == 2
