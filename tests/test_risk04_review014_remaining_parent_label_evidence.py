"""WO-RISK-04-REVIEW-014 remaining parent/label evidence. No new semantic decision."""
from __future__ import annotations

from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, GPT_PENDING
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
    H05_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    DEMOLITION_COMMON,
    EVIDENCE_FIELDS,
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    H02_COMMON,
    H02_PARENTS,
    REPORT_PATH,
    build_evidence,
    evidence_sha,
    inspect_architecture,
    parsed_l02_names,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

EVIDENCE_SHA = "f78396c18cf8cdb30eb25d7e59d944edabf492d0ec4d32286cf55290c273ec72"
FORBIDDEN_H05_FRAGMENT = "d7abd"


def test_frozen_review010_unchanged():
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA
    assert len(load_tsv(UNIVERSE_PATH)) == 1111


def test_frozen_review011_unchanged():
    assert member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) == FROZEN_MEMBER_HIERARCHY_SHA
    assert concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) == FROZEN_CONCEPT_HIERARCHY_SHA
    assert label_sha(load_tsv(LABEL_PATH)) == FROZEN_LABEL_SHA
    assert search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) == FROZEN_SEARCH_EXPORT_SHA
    queue = load_tsv(CRITICAL_QUEUE_PATH)
    assert critical_queue_sha(queue) == FROZEN_QUEUE_SHA
    assert len(queue) == 16


def test_frozen_review013_unchanged():
    rows = load_tsv(RESOLUTION_PATH)
    assert resolution_sha(rows) == FROZEN_RESOLUTION_SHA
    assert len(rows) == 16


def test_evidence_exact():
    rows = load_tsv(EVIDENCE_PATH)
    rebuilt = build_evidence()
    assert list(rows[0].keys()) == list(EVIDENCE_FIELDS)
    assert len(rows) == 5
    assert len({row["case_id"] for row in rows}) == 5
    assert [row["case_id"] for row in rows] == ["H-02", "H-03", "H-04", "H-05", "L-02"]
    assert evidence_sha(rows) == evidence_sha(rebuilt) == EVIDENCE_SHA


def test_parent_counts_and_common_ancestors():
    rows = {row["case_id"]: row for row in load_tsv(EVIDENCE_PATH)}
    for case_id in ("H-02", "H-03", "H-04", "H-05"):
        assert rows[case_id]["direct_parent_count"] == "2"
        assert rows[case_id]["common_ancestor_evidence_status"] == "NEAREST_COMMON_CANDIDATE_ANCESTOR"
        assert rows[case_id]["common_candidate_ancestor_distance"] == "1 | 1"
    assert set(rows["H-02"]["direct_parent_concept_keys"].split(" | ")) == set(H02_PARENTS)
    assert rows["H-02"]["common_candidate_ancestor_key"] == H02_COMMON
    assert rows["H-02"]["common_candidate_ancestor_name"] == "계측"
    for case_id in ("H-03", "H-04", "H-05"):
        assert rows[case_id]["common_candidate_ancestor_key"] == DEMOLITION_COMMON
        assert rows[case_id]["common_candidate_ancestor_name"] == "철거해체공사및시설물보호"


def test_h05_exact_key():
    rows = {row["case_id"]: row for row in load_tsv(EVIDENCE_PATH)}
    assert rows["H-05"]["review_concept_key"] == H05_KEY
    blob = EVIDENCE_PATH.read_text(encoding="utf-8") + Path("tools/risk04/review014_remaining_parent_label_evidence.py").read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in blob
    assert "d3abd" in H05_KEY


def test_l02_raw_and_child():
    rows = {row["case_id"]: row for row in load_tsv(EVIDENCE_PATH)}
    parsed_name, parsed_child = parsed_l02_names()
    assert "673" in rows["L-02"]["source_keys"]
    assert rows["L-02"]["raw_child_source_keys"] == "6731"
    assert parsed_name == rows["L-02"]["raw_name"]
    assert parsed_child == rows["L-02"]["raw_child_names"]
    assert rows["L-02"]["raw_provenance_status"] == "RAW_SOURCE_SHOWS_PARSER_CORRUPTION"
    assert rows["L-02"]["external_evidence_required"] == "NO"
    assert "671" in rows["L-02"]["parent_family_sibling_names"]
    assert "675" in rows["L-02"]["parent_family_sibling_names"]


def test_no_semantic_selection():
    rows = load_tsv(EVIDENCE_PATH)
    assert all(row["semantic_decision"] == "NOT_SELECTED" for row in rows)
    assert all(row["canonical_parent_candidate"] == GPT_EMPTY for row in rows)
    assert all(row["canonical_label_candidate"] == GPT_EMPTY for row in rows)
    assert all(row["gpt_resolution_status"] == GPT_PENDING for row in rows)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in rows)


def test_architecture_measured():
    measured = inspect_architecture()
    rows = load_tsv(EVIDENCE_PATH)
    assert measured["current_canonical_structure"] == "SINGLE_PARENT_ONLY"
    assert measured["source_context_preservable"] == "YES"
    assert all(row["current_canonical_structure"] == "SINGLE_PARENT_ONLY" for row in rows)
    assert all(row["source_context_preservable"] == "YES" for row in rows)


def test_no_classifier_or_approval():
    src = Path("tools/risk04/review014_remaining_parent_label_evidence.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "kiwipiepy" not in lowered
    assert "kiwi(" not in src
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "canonical_nodes" not in src or "risk_canonical_nodes" in src
    assert "approved_seed_manifest" not in src
    assert "This is an explicit evidence pack, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "NEAREST_COMMON_CANDIDATE_ANCESTOR ≠ canonical parent_id" in report
    assert "H-02 | PARENT_MODELING" in report
    assert "L-02 | LABEL_HOLD" in report
    assert "GPT DECISION" in report
    assert "PENDING" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report
    assert "canonical_label_candidate = EMPTY" in report


def test_determinism_two_runs():
    first = build_evidence()
    second = build_evidence()
    assert evidence_sha(first) == evidence_sha(second) == EVIDENCE_SHA
