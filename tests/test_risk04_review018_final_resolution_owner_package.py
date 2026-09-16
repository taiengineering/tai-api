"""WO-RISK-04-REVIEW-018 final resolution freeze and owner package. No new semantic decision."""
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
from tools.risk04.review013_resolution_freeze import FROZEN_EXCLUSIONS_SHA, FROZEN_MEMBERS_SHA, FROZEN_UNIVERSE_SHA, H05_KEY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review016_preapproval_manifest_audit import (
    MANIFEST_PATH,
    graph_audit,
    membership_audit,
    manifest_sha,
    readiness_counts,
)
from tools.risk04.review017_final_blocker_resolution_pack import (
    FAMILY_PATH,
    FROZEN_MANIFEST_SHA,
    LABEL_A_KEY,
    LABEL_B_KEY,
    PACK_PATH,
    family_sha,
    pack_sha,
)
from tools.risk04.review018_final_resolution_owner_package import (
    AGGREGATE_KEY,
    CONCRETE_PARENT,
    DAM_PARENT,
    ELEC_KEY,
    EQUIP_KEY,
    F011_KEYS,
    F371_KEYS,
    F415_KEYS,
    F513_KEYS,
    FILTER_KEY,
    FINAL_MANIFEST_PATH,
    FROZEN_REVIEW017_FAMILY_SHA,
    FROZEN_REVIEW017_PACK_SHA,
    HOLD_FIELDS,
    HOLD_PACKAGE_PATH,
    MASONRY_PARENT,
    OWNER_PACKAGE_PATH,
    PACKAGE_FIELDS,
    PIPE_PARENT,
    PLASTER_PARENT,
    REPORT_PATH,
    RESOLUTION_FIELDS,
    RESOLUTION_PATH,
    RETAINING_PARENT,
    STONE_KEY,
    build_final_manifest,
    build_hold_package,
    build_owner_package,
    build_resolution,
    final_manifest_sha,
    hold_package_sha,
    owner_package_sha,
    resolution_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

RESOLUTION_SHA = "d8e8558cba209fdae76a3f97b8255fa7d05aa3081b0c7868821e7d322cd3de55"
FINAL_MANIFEST_SHA = "2db684e0d6026f2bea1686f8188f01686638611b7068f43803cc5a83e54069c0"
OWNER_SHA = "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
HOLD_SHA = "d588f9b0917ed2f0ea6e990c38db86a1700d0e74afdfe9eec536220970fd68da"
FORBIDDEN_H05_FRAGMENT = "d7abd"
GENERATOR = Path("tools/risk04/review018_final_resolution_owner_package.py")


def test_frozen_review017_unchanged():
    assert pack_sha(load_tsv(PACK_PATH)) == FROZEN_REVIEW017_PACK_SHA
    assert family_sha(load_tsv(FAMILY_PATH)) == FROZEN_REVIEW017_FAMILY_SHA
    assert FROZEN_REVIEW017_PACK_SHA == "fdbb378f6da3d172441a7c725b747a9db0673b3e77dfc224c9ee2ad7c9ce738a"
    assert FROZEN_REVIEW017_FAMILY_SHA == "a84e23cf3e1f3532475ebdb408a3da2e9fb8cb7b60fa64627605964c6c1b4e44"
    assert manifest_sha(load_tsv(MANIFEST_PATH)) == FROZEN_MANIFEST_SHA
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA


def test_resolution_counts():
    rows = load_tsv(RESOLUTION_PATH)
    rebuilt = build_resolution()
    assert list(rows[0].keys()) == list(RESOLUTION_FIELDS)
    assert len(rows) == 26
    cats = Counter(row["gpt_final_decision"] for row in rows)
    assert cats["NEAREST_CANDIDATE_PARENT_CONFIRMED"] == 13
    assert cats["ROOT_PROMOTION_CONFIRMED"] == 9
    assert cats["ROOT_STATUS_CONFIRMED"] == 1
    assert cats["CLEAN_LABEL_MEMBER_CONFIRMED"] == 2
    assert cats["HOLD_LABEL_CONFIRMED"] == 1
    assert sum(1 for row in rows if row["gpt_final_decision"] == GPT_PENDING) == 0
    assert resolution_sha(rows) == resolution_sha(rebuilt) == RESOLUTION_SHA
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in rows)


def test_final_manifest_identity_and_readiness():
    rows = load_tsv(FINAL_MANIFEST_PATH)
    rebuilt = build_final_manifest()
    assert len(rows) == 1111
    assert len({row["review_concept_key"] for row in rows}) == 1111
    kinds = Counter(row["semantic_kind"] for row in rows)
    assert kinds["PROCESS"] == 557
    assert kinds["TASK"] == 554
    counts = readiness_counts(rows)
    assert counts["READY_FOR_OWNER_REVIEW"] == 1110
    assert counts["HOLD_LABEL"] == 1
    assert counts["HOLD_PARENT"] == 0
    assert counts["HOLD_LABEL_AND_PARENT"] == 0
    assert sum(1 for row in rows if row["parent_readiness"] == "HOLD") == 0
    assert final_manifest_sha(rows) == final_manifest_sha(rebuilt) == FINAL_MANIFEST_SHA
    universe = load_tsv(UNIVERSE_PATH)
    assert {row["review_concept_key"] for row in rows} == {row["review_concept_key"] for row in universe}


def test_parent_and_label_overlays():
    by_key = {row["review_concept_key"]: row for row in load_tsv(FINAL_MANIFEST_PATH)}
    for key in F371_KEYS:
        assert by_key[key]["canonical_parent_candidate"] == DAM_PARENT
        assert by_key[key]["canonical_parent_candidate_name"] == "댐공사"
        assert by_key[key]["preapproval_readiness"] == "READY_FOR_OWNER_REVIEW"
    assert by_key[AGGREGATE_KEY]["canonical_parent_candidate"] == CONCRETE_PARENT
    assert by_key[FILTER_KEY]["canonical_parent_candidate"] == PIPE_PARENT
    assert by_key[STONE_KEY]["canonical_parent_candidate"] == RETAINING_PARENT
    for key in F415_KEYS:
        assert by_key[key]["canonical_parent_candidate"] == MASONRY_PARENT
    for key in F513_KEYS:
        assert by_key[key]["canonical_parent_candidate"] == PLASTER_PARENT
    for key in F011_KEYS:
        assert by_key[key]["parent_readiness"] == "READY_ROOT"
        assert by_key[key]["canonical_parent_candidate"] == GPT_EMPTY
    assert by_key[EQUIP_KEY]["parent_readiness"] == "READY_ROOT"
    assert by_key[ELEC_KEY]["parent_readiness"] == "READY_ROOT"
    assert by_key[LABEL_A_KEY]["canonical_label_candidate"] == "배관및전로공사"
    assert by_key[LABEL_B_KEY]["canonical_label_candidate"] == "배선및가선공사"
    assert by_key[L02_KEY]["canonical_label_candidate"] == GPT_EMPTY
    assert by_key[L02_KEY]["preapproval_readiness"] == "HOLD_LABEL"
    assert by_key[L02_KEY]["hold_reason"] == "HOLD_LABEL_CONFIRMED"


def test_graph_membership_and_packages():
    rows = load_tsv(FINAL_MANIFEST_PATH)
    graph = graph_audit(rows)
    assert graph["self_parent"] == 0
    assert graph["unknown_parent"] == 0
    assert graph["cycle"] == 0
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    audit = membership_audit(rows, members, exclusions)
    assert len(members) == 1140
    assert audit["missing"] == 0
    assert audit["multi"] == 0
    assert audit["exclusion_leak"] == 0
    owner = load_tsv(OWNER_PACKAGE_PATH)
    hold = load_tsv(HOLD_PACKAGE_PATH)
    assert list(owner[0].keys()) == list(PACKAGE_FIELDS)
    assert list(hold[0].keys()) == list(HOLD_FIELDS)
    assert len(owner) == 1110
    assert len(hold) == 1
    assert hold[0]["review_concept_key"] == L02_KEY
    assert hold[0]["hold_reason"] == "HOLD_LABEL_CONFIRMED"
    assert hold[0]["owner_approval_eligible"] == "NO"
    assert owner_package_sha(owner) == owner_package_sha(build_owner_package(rows)) == OWNER_SHA
    assert hold_package_sha(hold) == hold_package_sha(build_hold_package(rows)) == HOLD_SHA
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in owner)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in rows)
    assert sum(1 for row in rows if row["owner_approval_state"] == "APPROVED") == 0


def test_h05_and_no_classifier_or_production():
    assert "d3abd" in H05_KEY
    assert FORBIDDEN_H05_FRAGMENT not in H05_KEY
    for path in (RESOLUTION_PATH, FINAL_MANIFEST_PATH, OWNER_PACKAGE_PATH, HOLD_PACKAGE_PATH, GENERATOR):
        assert FORBIDDEN_H05_FRAGMENT not in path.read_text(encoding="utf-8")
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
    assert "psycopg" not in lowered
    assert "supabase" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*review018*"))
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "OWNER APPROVAL PACKAGE CREATED ≠ OWNER APPROVED" in report
    assert "FULL 1111 APPROVAL READINESS = BLOCKED_BY_1_HOLD" in report
    assert "OWNER APPROVAL PACKAGE READINESS = READY" in report
    assert "OWNER APPROVAL PACKAGE = 1110" in report
    assert "canonical UUID = 0" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report
    assert f"OWNER APPROVAL PACKAGE SHA256 = {OWNER_SHA}" in report


def test_determinism_two_runs():
    first_r = build_resolution()
    second_r = build_resolution()
    first_m = build_final_manifest()
    second_m = build_final_manifest()
    assert resolution_sha(first_r) == resolution_sha(second_r) == RESOLUTION_SHA
    assert final_manifest_sha(first_m) == final_manifest_sha(second_m) == FINAL_MANIFEST_SHA
    assert owner_package_sha(build_owner_package(first_m)) == OWNER_SHA
    assert hold_package_sha(build_hold_package(first_m)) == HOLD_SHA
