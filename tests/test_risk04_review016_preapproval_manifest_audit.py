"""WO-RISK-04-REVIEW-016 preapproval manifest blocker audit. No new semantic decision."""
from __future__ import annotations

from collections import Counter
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
    H01_PARENT_KEY,
    H05_KEY,
    H06_PARENT_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    DEMOLITION_COMMON,
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    H02_COMMON,
    H02_KEY,
    H03_KEY,
    H04_KEY,
    L02_KEY,
    evidence_sha,
)
from tools.risk04.review015_remaining5_resolution_freeze import (
    FROZEN_EVIDENCE_SHA,
    REMAINING5_PATH,
    remaining5_sha,
)
from tools.risk04.review016_preapproval_manifest_audit import (
    BLOCKER_FIELDS,
    BLOCKER_PATH,
    FROZEN_REMAINING5_SHA,
    H01_KEY,
    H06_KEY,
    MANIFEST_FIELDS,
    MANIFEST_PATH,
    READINESS,
    REPORT_PATH,
    blocker_sha,
    build_blockers,
    build_manifest,
    graph_audit,
    manifest_sha,
    membership_audit,
    readiness_counts,
    unresolved_counts,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

MANIFEST_SHA = "1c1227a4667ce9527348885ad4b818c7da40e3b1db1940eed75648c6f0d666e2"
BLOCKER_SHA = "dae96dedb93a19db1fb845448db7d27a2fc0ffca447a9f732a33b74a5d8e749b"
FORBIDDEN_H05_FRAGMENT = "d7abd"
GENERATOR = Path("tools/risk04/review016_preapproval_manifest_audit.py")


def test_frozen_review010_unchanged():
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA
    assert FROZEN_UNIVERSE_SHA == "0f05f4443cbac19b1b3fa97f1204f2c75785a027889f0be35f1e0acd0d7e61a8"
    assert FROZEN_MEMBERS_SHA == "b341204156611e12057f9113a6692b2c1d04e07f63eec151a53994928b9fde84"
    assert FROZEN_EXCLUSIONS_SHA == "123b8c0361d829cd751970baf138373e3f98911ab787a1e5b7dabfc27489daca"
    assert len(load_tsv(UNIVERSE_PATH)) == 1111
    assert len(load_tsv(MEMBERS_PATH)) == 1140
    assert len(load_tsv(EXCLUSIONS_PATH)) == 582


def test_frozen_review011_unchanged():
    assert member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) == FROZEN_MEMBER_HIERARCHY_SHA
    assert concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) == FROZEN_CONCEPT_HIERARCHY_SHA
    assert label_sha(load_tsv(LABEL_PATH)) == FROZEN_LABEL_SHA
    assert search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) == FROZEN_SEARCH_EXPORT_SHA
    assert critical_queue_sha(load_tsv(CRITICAL_QUEUE_PATH)) == FROZEN_QUEUE_SHA


def test_frozen_review013_014_015_unchanged():
    assert resolution_sha(load_tsv(RESOLUTION_PATH)) == FROZEN_RESOLUTION_SHA
    assert evidence_sha(load_tsv(EVIDENCE_PATH)) == FROZEN_EVIDENCE_SHA
    assert remaining5_sha(load_tsv(REMAINING5_PATH)) == FROZEN_REMAINING5_SHA
    assert FROZEN_RESOLUTION_SHA == "28d0bc4e45206894cbcd1668be1fc744ac0dce5f2fc84021745011feeb3fd686"
    assert FROZEN_EVIDENCE_SHA == "f78396c18cf8cdb30eb25d7e59d944edabf492d0ec4d32286cf55290c273ec72"
    assert FROZEN_REMAINING5_SHA == "d3f2492893f0959d7737d15299f998b5fbfabea3b0dcfcde57ede63ccce37ec4"


def test_manifest_identity():
    rows = load_tsv(MANIFEST_PATH)
    rebuilt = build_manifest()
    universe = load_tsv(UNIVERSE_PATH)
    assert list(rows[0].keys()) == list(MANIFEST_FIELDS)
    assert len(rows) == 1111
    assert len({row["review_concept_key"] for row in rows}) == 1111
    assert {row["review_concept_key"] for row in rows} == {row["review_concept_key"] for row in universe}
    kinds = Counter(row["semantic_kind"] for row in rows)
    assert kinds["PROCESS"] == 557
    assert kinds["TASK"] == 554
    assert manifest_sha(rows) == manifest_sha(rebuilt) == MANIFEST_SHA


def test_membership_and_exclusion_boundary():
    rows = load_tsv(MANIFEST_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    audit = membership_audit(rows, members, exclusions)
    assert len(members) == 1140
    assert audit["missing"] == 0
    assert audit["multi"] == 0
    assert audit["exclusion_leak"] == 0
    graph = graph_audit(rows)
    assert graph["self_parent"] == 0
    assert graph["unknown_parent"] == 0
    assert graph["cycle"] == 0


def test_unresolved_hierarchy_and_parents():
    rows = load_tsv(MANIFEST_PATH)
    by_key = {row["review_concept_key"]: row for row in rows}
    hierarchy = load_tsv(CONCEPT_HIERARCHY_PATH)
    labels = load_tsv(LABEL_PATH)
    extra = unresolved_counts(rows, hierarchy, labels)
    assert extra["NO_CANDIDATE_PARENT"] == 23
    assert extra["MULTI_RAW_VARIANTS"] == 2
    unresolved_multi = unresolved_cross = 0
    hier = {row["review_concept_key"]: row for row in hierarchy}
    for row in rows:
        prior = hier[row["review_concept_key"]]["hierarchy_readiness"]
        if prior == "MULTI_PARENT_REVIEW_REQUIRED" and row["parent_readiness"] == "HOLD":
            unresolved_multi += 1
        if prior == "CROSS_ROOT_REVIEW_REQUIRED" and row["parent_readiness"] == "HOLD":
            unresolved_cross += 1
    assert unresolved_multi == 0
    assert unresolved_cross == 0
    assert by_key[H01_KEY]["canonical_parent_candidate"] == H01_PARENT_KEY
    assert by_key[H06_KEY]["canonical_parent_candidate"] == H06_PARENT_KEY
    assert by_key[H02_KEY]["canonical_parent_candidate"] == H02_COMMON
    assert by_key[H02_KEY]["canonical_parent_candidate_name"] == "계측"
    assert by_key[H03_KEY]["canonical_parent_candidate"] == DEMOLITION_COMMON
    assert by_key[H04_KEY]["canonical_parent_candidate"] == DEMOLITION_COMMON
    assert by_key[H05_KEY]["canonical_parent_candidate"] == DEMOLITION_COMMON
    assert by_key[H05_KEY]["canonical_parent_candidate_name"] == "철거해체공사및시설물보호"
    assert by_key[H02_KEY]["source_context_policy"] == "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE"
    assert by_key[H05_KEY]["source_context_policy"] == "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE"


def test_h05_and_l02_guards():
    rows = load_tsv(MANIFEST_PATH)
    by_key = {row["review_concept_key"]: row for row in rows}
    assert by_key[H05_KEY]["review_concept_key"] == H05_KEY
    assert "d3abd" in H05_KEY
    assert FORBIDDEN_H05_FRAGMENT not in H05_KEY
    assert FORBIDDEN_H05_FRAGMENT not in MANIFEST_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in BLOCKER_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in GENERATOR.read_text(encoding="utf-8")
    l02 = by_key[L02_KEY]
    assert l02["canonical_label_candidate"] == GPT_EMPTY
    assert l02["label_readiness"] == "HOLD"
    assert "HOLD_LABEL_CONFIRMED" in l02["hold_reason"]
    assert l02["preapproval_readiness"] == "HOLD_LABEL"


def test_blocker_queue_matches_hold_subset():
    manifest = load_tsv(MANIFEST_PATH)
    blockers = load_tsv(BLOCKER_PATH)
    rebuilt = build_blockers(manifest)
    hold = {row["review_concept_key"] for row in manifest if row["preapproval_readiness"] != "READY_FOR_OWNER_REVIEW"}
    assert list(blockers[0].keys()) == list(BLOCKER_FIELDS)
    assert len(blockers) == 26
    assert {row["review_concept_key"] for row in blockers} == hold
    assert all(row["required_next_decision"] in {"GPT_LABEL_REVIEW", "GPT_PARENT_REVIEW", "GPT_LABEL_AND_PARENT_REVIEW"} for row in blockers)
    assert blocker_sha(blockers) == blocker_sha(rebuilt) == BLOCKER_SHA
    counts = readiness_counts(manifest)
    assert counts["READY_FOR_OWNER_REVIEW"] == 1085
    assert counts["HOLD_LABEL"] == 3
    assert counts["HOLD_PARENT"] == 23
    assert counts["HOLD_LABEL_AND_PARENT"] == 0
    assert counts["TOTAL_BLOCKERS"] == 26
    assert counts["READY_FOR_OWNER_REVIEW"] + counts["HOLD_LABEL"] + counts["HOLD_PARENT"] + counts["HOLD_LABEL_AND_PARENT"] == 1111
    assert all(row["preapproval_readiness"] in READINESS for row in manifest)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in manifest)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in blockers)
    assert sum(1 for row in manifest if row["owner_approval_state"] == "APPROVED") == 0
    assert all(row["semantic_resolution_status"] != GPT_PENDING for row in manifest)


def test_no_classifier_approval_or_production():
    src = GENERATOR.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "kiwipiepy" not in lowered
    assert "kiwi(" not in src
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "canonical_uuid" not in lowered
    assert "risk_canonical_nodes" not in lowered
    assert "approved_mapping" not in lowered
    assert "psycopg" not in lowered
    assert "supabase" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*review016*"))
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "THIS IS NOT CANONICAL CREATION" in report
    assert "READY_FOR_OWNER_REVIEW ≠ APPROVED" in report
    assert "FULL OWNER APPROVAL READINESS = BLOCKED" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "PR MERGE = NOT AUTHORIZED" in report
    assert "canonical UUID = 0" in report
    assert "approved mapping = 0" in report
    assert "production write = 0" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report
    assert "GPT semantic pending = 0" in report
    assert "candidate concepts = 1111" in report
    assert "TOTAL BLOCKERS = 26" in report


def test_determinism_two_runs():
    first = build_manifest()
    second = build_manifest()
    first_b = build_blockers(first)
    second_b = build_blockers(second)
    assert manifest_sha(first) == manifest_sha(second) == MANIFEST_SHA
    assert blocker_sha(first_b) == blocker_sha(second_b) == BLOCKER_SHA
