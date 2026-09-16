"""WO-RISK-04-REVIEW-015 remaining-5 GPT resolution freeze. No new semantic decision."""
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
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    H02_COMMON,
    evidence_sha,
)
from tools.risk04.review015_remaining5_resolution_freeze import (
    FROZEN_EVIDENCE_SHA,
    GPT_CASES,
    REMAINING5_FIELDS,
    REMAINING5_PATH,
    REPORT_PATH,
    build_remaining5,
    remaining5_counts,
    remaining5_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

REMAINING5_SHA = "d3f2492893f0959d7737d15299f998b5fbfabea3b0dcfcde57ede63ccce37ec4"
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
    assert critical_queue_sha(load_tsv(CRITICAL_QUEUE_PATH)) == FROZEN_QUEUE_SHA


def test_frozen_review013_and_014_unchanged():
    assert resolution_sha(load_tsv(RESOLUTION_PATH)) == FROZEN_RESOLUTION_SHA
    assert evidence_sha(load_tsv(EVIDENCE_PATH)) == FROZEN_EVIDENCE_SHA
    assert FROZEN_RESOLUTION_SHA == "28d0bc4e45206894cbcd1668be1fc744ac0dce5f2fc84021745011feeb3fd686"
    assert FROZEN_EVIDENCE_SHA == "f78396c18cf8cdb30eb25d7e59d944edabf492d0ec4d32286cf55290c273ec72"


def test_remaining5_exact():
    rows = load_tsv(REMAINING5_PATH)
    rebuilt = build_remaining5()
    assert list(rows[0].keys()) == list(REMAINING5_FIELDS)
    assert len(rows) == 5
    assert len({row["review_concept_key"] for row in rows}) == 5
    assert [row["case_id"] for row in rows] == [case["case_id"] for case in GPT_CASES]
    assert remaining5_sha(rows) == remaining5_sha(rebuilt) == REMAINING5_SHA


def test_parent_and_label_decisions():
    rows = {row["case_id"]: row for row in load_tsv(REMAINING5_PATH)}
    for case_id in ("H-02", "H-03", "H-04", "H-05"):
        assert rows[case_id]["gpt_final_decision"] == "COMMON_ANCESTOR_PARENT_CONFIRMED"
        assert rows[case_id]["canonical_label_candidate"] == GPT_EMPTY
    assert rows["H-02"]["canonical_parent_candidate"] == H02_COMMON
    assert rows["H-02"]["canonical_parent_candidate_name"] == "계측"
    for case_id in ("H-03", "H-04", "H-05"):
        assert rows[case_id]["canonical_parent_candidate"] == DEMOLITION_COMMON
        assert rows[case_id]["canonical_parent_candidate_name"] == "철거해체공사및시설물보호"
    assert rows["L-02"]["gpt_final_decision"] == "HOLD_LABEL_CONFIRMED"
    assert rows["L-02"]["canonical_label_candidate"] == GPT_EMPTY
    assert rows["L-02"]["label_resolution_status"] == "HOLD_LABEL_CONFIRMED"
    counts = remaining5_counts(load_tsv(REMAINING5_PATH))
    assert counts["parent_candidates"] == 4
    assert counts["label_candidates"] == 0
    assert counts["계측"] == 1
    assert counts["철거해체공사및시설물보호"] == 3


def test_h05_exact_key():
    rows = {row["case_id"]: row for row in load_tsv(REMAINING5_PATH)}
    assert rows["H-05"]["review_concept_key"] == H05_KEY
    freeze = Path("tools/risk04/review015_remaining5_resolution_freeze.py").read_text(encoding="utf-8")
    tsv = REMAINING5_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in tsv
    assert FORBIDDEN_H05_FRAGMENT not in freeze
    assert "d3abd" in H05_KEY


def test_gpt_complete_and_approval_guards():
    rows = load_tsv(REMAINING5_PATH)
    counts = remaining5_counts(rows)
    assert counts["GPT_RESOLVED"] == 5
    assert counts["GPT_PENDING"] == 0
    assert all(row["resolution_status"] != GPT_PENDING for row in rows)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["source_preservation"] == "YES" for row in rows)
    assert len(load_tsv(UNIVERSE_PATH)) == 1111


def test_no_classifier_or_approval():
    src = Path("tools/risk04/review015_remaining5_resolution_freeze.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "kiwipiepy" not in lowered
    assert "kiwi(" not in src
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "canonical_parent_id" not in src
    assert "approved_parent" not in src
    assert "active_parent" not in src
    assert "approved_seed_manifest" not in src
    assert "This is an explicit GPT freeze overlay, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "THIS IS NOT CANONICAL CREATION" in report
    assert "THIS IS NOT AN APPROVED CANONICAL PARENT MANIFEST" in report
    assert "THIS IS NOT A CANONICAL LABEL MANIFEST" in report
    assert "THIS IS NOT AN APPROVED MAPPING" in report
    assert "COMMON_ANCESTOR_PARENT_CONFIRMED" in report
    assert "CANONICAL PARENT APPROVED" in report
    assert "HOLD_LABEL_CONFIRMED" in report
    assert "LABEL INVENTED" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "PR MERGE = NOT AUTHORIZED" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report
    assert "GPT PENDING = 0" in report


def test_determinism_two_runs():
    first = build_remaining5()
    second = build_remaining5()
    assert remaining5_sha(first) == remaining5_sha(second) == REMAINING5_SHA
