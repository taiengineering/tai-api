"""WO-RISK-04-REVIEW-017 final blocker resolution pack. No new semantic decision."""
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
from tools.risk04.review013_resolution_freeze import (
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_UNIVERSE_SHA,
    H05_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    L02_KEY,
    evidence_sha,
)
from tools.risk04.review015_remaining5_resolution_freeze import (
    FROZEN_EVIDENCE_SHA,
    REMAINING5_PATH,
    remaining5_sha,
)
from tools.risk04.review016_preapproval_manifest_audit import (
    BLOCKER_PATH,
    FROZEN_REMAINING5_SHA,
    MANIFEST_PATH,
    blocker_sha,
    manifest_sha,
    readiness_counts,
)
from tools.risk04.review017_final_blocker_resolution_pack import (
    FAMILY_FIELDS,
    FAMILY_PATH,
    FROZEN_BLOCKER_SHA,
    FROZEN_MANIFEST_SHA,
    LABEL_A_KEY,
    LABEL_B_KEY,
    PACK_FIELDS,
    PACK_PATH,
    REPORT_PATH,
    build_pack,
    family_sha,
    pack_counts,
    pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

PACK_SHA = "fdbb378f6da3d172441a7c725b747a9db0673b3e77dfc224c9ee2ad7c9ce738a"
FAMILY_SHA = "a84e23cf3e1f3532475ebdb408a3da2e9fb8cb7b60fa64627605964c6c1b4e44"
FORBIDDEN_H05_FRAGMENT = "d7abd"
GENERATOR = Path("tools/risk04/review017_final_blocker_resolution_pack.py")


def test_frozen_review016_unchanged():
    assert manifest_sha(load_tsv(MANIFEST_PATH)) == FROZEN_MANIFEST_SHA
    assert blocker_sha(load_tsv(BLOCKER_PATH)) == FROZEN_BLOCKER_SHA
    assert FROZEN_MANIFEST_SHA == "1c1227a4667ce9527348885ad4b818c7da40e3b1db1940eed75648c6f0d666e2"
    assert FROZEN_BLOCKER_SHA == "dae96dedb93a19db1fb845448db7d27a2fc0ffca447a9f732a33b74a5d8e749b"
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA


def test_frozen_review013_014_015_unchanged():
    assert resolution_sha(load_tsv(RESOLUTION_PATH)) == FROZEN_RESOLUTION_SHA
    assert evidence_sha(load_tsv(EVIDENCE_PATH)) == FROZEN_EVIDENCE_SHA
    assert remaining5_sha(load_tsv(REMAINING5_PATH)) == FROZEN_REMAINING5_SHA


def test_pack_identity_and_keyset():
    pack = load_tsv(PACK_PATH)
    rebuilt, _ = build_pack()
    blockers = load_tsv(BLOCKER_PATH)
    assert list(pack[0].keys()) == list(PACK_FIELDS)
    assert len(pack) == 26
    assert {row["review_concept_key"] for row in pack} == {row["review_concept_key"] for row in blockers}
    types = {row["blocker_type"] for row in pack}
    assert sum(1 for row in pack if row["blocker_type"] == "PARENT") == 23
    assert sum(1 for row in pack if row["blocker_type"] == "LABEL_VARIANT") == 2
    assert sum(1 for row in pack if row["blocker_type"] == "FROZEN_LABEL_HOLD") == 1
    assert types == {"PARENT", "LABEL_VARIANT", "FROZEN_LABEL_HOLD"}
    assert pack_sha(pack) == pack_sha(rebuilt) == PACK_SHA
    assert sum(1 for row in pack if row["gpt_decision"] == GPT_PENDING) == 25
    l02 = next(row for row in pack if row["review_concept_key"] == L02_KEY)
    assert l02["gpt_decision"] == "HOLD_LABEL_CONFIRMED"
    assert l02["review_scope"] == "FROZEN_HOLD"
    assert l02["gpt_label_candidate"] == GPT_EMPTY


def test_parent_families_cover_exactly_23():
    families = load_tsv(FAMILY_PATH)
    rebuilt_pack, rebuilt_fam = build_pack()
    assert list(families[0].keys()) == list(FAMILY_FIELDS)
    children = []
    for row in families:
        children.extend([part for part in row["child_review_concept_keys"].split(" | ") if part])
    assert sum(int(row["child_count"]) for row in families) == 23
    assert len(children) == 23
    assert len(set(children)) == 23
    pack_parents = {row["review_concept_key"] for row in load_tsv(PACK_PATH) if row["blocker_type"] == "PARENT"}
    assert set(children) == pack_parents
    assert "F-UNASSIGNED" not in {row["family_id"] for row in families}
    assert family_sha(families) == family_sha(rebuilt_fam) == FAMILY_SHA
    f371 = next(row for row in families if row["family_id"] == "F-371")
    assert f371["child_count"] == "6"
    assert f371["excluded_parent_source_key"] == "371"
    assert f371["mechanical_parent_candidate_name"] == "댐공사"
    assert f371["nearest_candidate_ancestor_distance"] == "2"
    f011 = next(row for row in families if row["family_id"] == "F-011")
    assert f011["child_count"] == "8"
    assert f011["root_candidate_status"] == "EXCLUDED"
    assert f011["nearest_candidate_ancestor_count"] == "0"
    assert f011["mechanical_rule_status"] == "GPT_REQUIRED"


def test_mechanical_candidate_rules():
    pack = load_tsv(PACK_PATH)
    universe = {row["review_concept_key"] for row in load_tsv(UNIVERSE_PATH)}
    for row in pack:
        if row["mechanical_rule_status"] == "SINGLE_ANCESTOR_DERIVED":
            assert row["nearest_candidate_ancestor_count"] == "1"
            assert row["mechanical_parent_candidate"] in universe
            assert row["mechanical_parent_candidate"] not in {GPT_EMPTY, ""}
        if row["mechanical_parent_candidate"] not in {GPT_EMPTY, ""}:
            assert row["mechanical_parent_candidate"] in universe
            assert row["mechanical_rule_status"] == "SINGLE_ANCESTOR_DERIVED"
    counts = pack_counts(pack, load_tsv(FAMILY_PATH))
    assert counts["mechanical"] == 13
    assert counts["gpt_required_parent"] == 10
    assert counts["MULTI_NEAREST_CANDIDATE_ANCESTOR"] == 0
    assert counts["external_yes"] == 0


def test_label_variant_evidence():
    pack = {row["review_concept_key"]: row for row in load_tsv(PACK_PATH)}
    a = pack[LABEL_A_KEY]
    b = pack[LABEL_B_KEY]
    assert "811=배관․전로공사" in a["raw_label_variants"]
    assert "8111=배관및전로공사" in a["raw_label_variants"]
    assert "punctuation_removed_equal=NO" in a["label_variant_analysis"]
    assert "connector_normalized_equal=YES" in a["label_variant_analysis"]
    assert "hierarchy_relation=PARENT_CHILD" in a["label_variant_analysis"]
    assert "812=배선․가선공사" in b["raw_label_variants"]
    assert "8121=배선및가선공사" in b["raw_label_variants"]
    assert "connector_normalized_equal=YES" in b["label_variant_analysis"]
    assert a["gpt_label_candidate"] == GPT_EMPTY
    assert b["gpt_label_candidate"] == GPT_EMPTY
    assert a["gpt_decision"] == GPT_PENDING
    src = GENERATOR.read_text(encoding="utf-8")
    assert "canonical label = A" not in src
    assert "canonical label = B" not in src


def test_h05_ready_and_identity_guards():
    assert "d3abd" in H05_KEY
    assert FORBIDDEN_H05_FRAGMENT not in H05_KEY
    assert FORBIDDEN_H05_FRAGMENT not in PACK_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in FAMILY_PATH.read_text(encoding="utf-8")
    assert FORBIDDEN_H05_FRAGMENT not in GENERATOR.read_text(encoding="utf-8")
    manifest = load_tsv(MANIFEST_PATH)
    assert readiness_counts(manifest)["READY_FOR_OWNER_REVIEW"] == 1085
    kinds = {row["effective_semantic_kind"] for row in load_tsv(UNIVERSE_PATH)}
    universe = load_tsv(UNIVERSE_PATH)
    assert len(universe) == 1111
    assert sum(1 for row in universe if row["effective_semantic_kind"] == "PROCESS") == 557
    assert sum(1 for row in universe if row["effective_semantic_kind"] == "TASK") == 554
    assert len(load_tsv(MEMBERS_PATH)) == 1140
    assert kinds <= {"PROCESS", "TASK"}
    pack = load_tsv(PACK_PATH)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in pack)
    assert sum(1 for row in pack if row["owner_approval_state"] == "APPROVED") == 0


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
    assert "psycopg" not in lowered
    assert "supabase" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*review017*"))
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "mechanical_parent_candidate ≠ GPT semantic decision" in report
    assert "LABEL VARIANT EVIDENCE COMPLETE = 2 / 2" in report
    assert "semantic decisions by Cursor = 0" in report
    assert "ACTIVE GPT REVIEW = 25" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "canonical UUID = 0" in report
    assert "vector model calls = 0" in report
    assert "Kiwi runtime calls = 0" in report


def test_determinism_two_runs():
    first_pack, first_fam = build_pack()
    second_pack, second_fam = build_pack()
    assert pack_sha(first_pack) == pack_sha(second_pack) == PACK_SHA
    assert family_sha(first_fam) == family_sha(second_fam) == FAMILY_SHA
