"""WO-RISK-04-REVIEW-013 GPT hierarchy/label resolution freeze. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBERS_PATH,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review011_hierarchy_label_search_readiness import (
    CONCEPT_HIERARCHY_PATH,
    CRITICAL_QUEUE_PATH,
    LABEL_PATH,
    MEMBER_HIERARCHY_PATH,
    SEARCH_EXPORT_PATH,
    concept_hierarchy_sha,
    critical_queue_sha,
    label_sha,
    member_hierarchy_sha,
    search_export_sha,
)
from tools.risk04.review013_resolution_freeze import (
    FROZEN_CONCEPT_HIERARCHY_SHA,
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_LABEL_SHA,
    FROZEN_MEMBER_HIERARCHY_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_QUEUE_SHA,
    FROZEN_SEARCH_EXPORT_SHA,
    FROZEN_UNIVERSE_SHA,
    GPT_CASES,
    H01_PARENT_KEY,
    H05_KEY,
    H06_PARENT_KEY,
    REPORT_PATH,
    RESOLUTION_FIELDS,
    RESOLUTION_PATH,
    build_resolution,
    resolution_counts,
    resolution_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

RESOLUTION_SHA = "28d0bc4e45206894cbcd1668be1fc744ac0dce5f2fc84021745011feeb3fd686"
FORBIDDEN_H05_FRAGMENT = "d7abd"


def test_pr_source_artifacts_exist():
    assert UNIVERSE_PATH.is_file()
    assert MEMBERS_PATH.is_file()
    assert EXCLUSIONS_PATH.is_file()
    assert CRITICAL_QUEUE_PATH.is_file()
    assert RESOLUTION_PATH.is_file()
    assert REPORT_PATH.is_file()
    assert Path("tools/risk04/review013_resolution_freeze.py").is_file()


def test_frozen_review010_unchanged():
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA
    assert len(load_tsv(UNIVERSE_PATH)) == 1111
    assert len(load_tsv(MEMBERS_PATH)) == 1140
    assert len(load_tsv(EXCLUSIONS_PATH)) == 582


def test_frozen_review011_unchanged():
    queue = load_tsv(CRITICAL_QUEUE_PATH)
    assert member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) == FROZEN_MEMBER_HIERARCHY_SHA
    assert concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) == FROZEN_CONCEPT_HIERARCHY_SHA
    assert label_sha(load_tsv(LABEL_PATH)) == FROZEN_LABEL_SHA
    assert search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) == FROZEN_SEARCH_EXPORT_SHA
    assert critical_queue_sha(queue) == FROZEN_QUEUE_SHA
    assert len(queue) == 16
    assert len({row["review_concept_key"] for row in queue}) == 16
    assert all(row["gpt_resolution_status"] == "PENDING" for row in queue)


def test_resolution_exact():
    queue = load_tsv(CRITICAL_QUEUE_PATH)
    rows = load_tsv(RESOLUTION_PATH)
    rebuilt = build_resolution()
    assert list(rows[0].keys()) == list(RESOLUTION_FIELDS)
    assert len(rows) == 16
    assert len({row["review_concept_key"] for row in rows}) == 16
    assert {row["review_concept_key"] for row in rows} == {row["review_concept_key"] for row in queue}
    assert [row["case_id"] for row in rows] == [case["case_id"] for case in GPT_CASES]
    assert resolution_sha(rows) == resolution_sha(rebuilt) == RESOLUTION_SHA


def test_h05_exact_key_and_forbidden_typo():
    rows = load_tsv(RESOLUTION_PATH)
    h05 = next(row for row in rows if row["case_id"] == "H-05")
    assert h05["review_concept_key"] == H05_KEY
    tsv = RESOLUTION_PATH.read_text(encoding="utf-8")
    freeze = Path("tools/risk04/review013_resolution_freeze.py").read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in tsv
    assert FORBIDDEN_H05_FRAGMENT not in freeze
    assert FORBIDDEN_H05_FRAGMENT not in H05_KEY
    assert "d3abd" in H05_KEY


def test_hierarchy_counts_and_parents():
    rows = load_tsv(RESOLUTION_PATH)
    hierarchy = [row for row in rows if row["issue_type"] in {"CROSS_ROOT", "MULTI_PARENT"}]
    assert len(hierarchy) == 6
    assert all(row["gpt_decision"] == "KEEP_CONCEPT" for row in hierarchy)
    assert sum(1 for row in hierarchy if row["gpt_decision"] == "SPLIT_REQUIRED") == 0
    parents = Counter(row["canonical_parent_resolution"] for row in hierarchy)
    assert parents["SINGLE_PARENT_CANDIDATE"] == 2
    assert parents["PARENT_REQUIRES_LATER_MODELING"] == 4
    by_id = {row["case_id"]: row for row in rows}
    assert by_id["H-01"]["recommended_parent_concept_key"] == H01_PARENT_KEY
    assert by_id["H-06"]["recommended_parent_concept_key"] == H06_PARENT_KEY
    assert by_id["H-02"]["recommended_parent_concept_key"] == GPT_EMPTY
    assert by_id["H-03"]["recommended_parent_concept_key"] == GPT_EMPTY
    assert by_id["H-04"]["recommended_parent_concept_key"] == GPT_EMPTY
    assert by_id["H-05"]["recommended_parent_concept_key"] == GPT_EMPTY


def test_label_counts():
    rows = load_tsv(RESOLUTION_PATH)
    labels = [row for row in rows if row["issue_type"] == "LEXICAL_NOISE"]
    assert len(labels) == 10
    decisions = Counter(row["gpt_decision"] for row in labels)
    assert decisions["CLEAN_LABEL_CONFIRMED"] == 8
    assert decisions["EXISTING_CLEAN_MEMBER_CONFIRMED"] == 1
    assert decisions["HOLD_LABEL"] == 1
    hold = next(row for row in labels if row["case_id"] == "L-02")
    assert hold["gpt_decision"] == "HOLD_LABEL"
    assert hold["proposed_canonical_label"] == GPT_EMPTY
    assert hold["label_basis"] == GPT_EMPTY
    clean = next(row for row in labels if row["case_id"] == "L-03")
    assert clean["gpt_decision"] == "EXISTING_CLEAN_MEMBER_CONFIRMED"
    assert clean["proposed_canonical_label"] == "건축물전기설비공사"
    assert clean["label_basis"] == "EXISTING_CLEAN_SOURCE_MEMBER"


def test_concept_count_and_approval_guards():
    rows = load_tsv(RESOLUTION_PATH)
    counts = resolution_counts(rows)
    assert len(load_tsv(UNIVERSE_PATH)) == 1111
    assert counts["SPLIT_REQUIRED"] == 0
    assert counts["source_preservation_yes"] == 16
    assert counts["owner_not_approved"] == 16
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["source_preservation"] == "YES" for row in rows)
    assert all(row["resolution_status"] == "GPT_RESOLVED" for row in rows)


def test_no_classifier_or_approval():
    src = Path("tools/risk04/review013_resolution_freeze.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "kiwipiepy" not in lowered
    assert "kiwi(" not in src
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "canonical_nodes" not in src
    assert "approved_seed_manifest" not in src
    assert "This is an explicit GPT freeze overlay, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "FULL CANONICAL READINESS = NOT YET" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "remaining parent modeling = 4" in report
    assert "remaining label hold = 1" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report
    assert "candidate concepts = 1111" in report


def test_determinism_two_runs():
    first = build_resolution()
    second = build_resolution()
    assert resolution_sha(first) == resolution_sha(second) == RESOLUTION_SHA
