"""WO-RISK-KOSHA-B02-REVIEW-001 GPT KOSHA B02 semantic decision freeze.

Transcription-only tool — same contract as B01 freeze. GPT is the semantic
authority; this tool ONLY:

  * Verifies frozen input SHAs.
  * Verifies the 100-key GPT_DECISIONS manifest matches the B02 source set.
  * Emits the freeze TSV + census + report.
  * Never touches production or any writable DB surface.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_b01_gpt_review_freeze import (
    CENSUS_FIELDS,
    DECISION_FIELDS,
)
from tools.risk_map.kosha_b01_semantic_evidence import (
    CANONICAL_TASK_REFERENCE_PATH,
    canonical_task_reference_sha,
)
from tools.risk_map.kosha_b02_semantic_evidence import (
    B02_EVIDENCE_PATH,
    b02_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B02-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B02"

FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b02-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# ---------------------------------------------------------------------------


_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"          # 철근가공및조립
_TARGET_CAISSON = "97cf2571-0f3a-4bb2-8a85-837bbd502bb0"         # 케이슨제작및설치
_TARGET_BLASTING = "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"        # 발파
_TARGET_SITE_GRADING = "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"    # 일반부지정지
_TARGET_TOPSOIL = "a7106b20-76ca-427f-aa45-2f0b1d417f15"         # 표토제거


# §5 NARROWER_THAN (6 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "356e247dc8ffcb04de5f66a0ea98e29b25e646b0f5ab6d9ce5f80f86ba6ad022",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
    (
        "c79380a2d93663891d26bf3b427845f18ab58012637df588431c778cc930399e",
        _TARGET_CAISSON,
        "CAISSON_FABRICATION_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_CAISSON_FABRICATION_AND_INSTALLATION",
        "HIGH",
    ),
    (
        "f0c418636e58bcdc1e89f25952cc9948f6af85680a965f9a9fd19bb64ae27710",
        _TARGET_BLASTING,
        "EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "eead61646f3d44d3b0f018b70f6c9a2dcd90d1836469daf4707f539da44a43a9",
        _TARGET_BLASTING,
        "BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "18dd13b6ceb8f503f56e417710183abacead45d069088f51fb4568deeeb260bc",
        _TARGET_SITE_GRADING,
        "LANDSCAPE_SITE_PREPARATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_GENERAL_SITE_GRADING",
        "MEDIUM",
    ),
    (
        "0620aa3261e75db6a1c3d87922764cc28204c2cb6e48deca3cbd847b267566d9",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
)


# §6 POSSIBLE_RELATED (5 rows) — all MEDIUM
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "019b2c465ec252bcbe6fe426e1af76d0be56255c03e9f24ff6609d2bfefbb6e9",
        _TARGET_CAISSON,
        "CAISSON_TRANSPORT_AND_PLACEMENT_OVERLAPS_INSTALLATION_BUT_IS_NOT_EQUIVALENT_TO_FULL_FABRICATION_AND_INSTALLATION",
    ),
    (
        "af0b41941bc3abfb477dad8f32db3cea62f2ad82b81eeab423b9f8663c4acd77",
        _TARGET_TOPSOIL,
        "COMPOSITE_SOURCE_INCLUDES_TOPSOIL_REMOVAL_BUT_ALSO_TREE_CLEARING",
    ),
    (
        "edea1aa11b35d92d4ab96af29234e35d2a6a2a49207a223ba11b34c087e659f6",
        _TARGET_BLASTING,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_BLASTING_BUT_IS_NOT_THE_SAME_TASK",
    ),
    (
        "c826a967fda0d866048a7925a1ab1119e64cb164510814d6b25ef3887ac81071",
        _TARGET_BLASTING,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_BLASTING_BUT_IS_NOT_A_BLASTING_EXECUTION_TASK",
    ),
    (
        "82e7b20228f8611ddc7f3baf5857f0a3e80247526510a1e6955538bb35d18cb3",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
)


# §7 AMBIGUOUS (8 rows) — semantic family mapping via ordering with the WO's
# "Meaning respectively includes" list.
_REASON_CONCRETE = (
    "GENERIC_CONCRETE_PLACEMENT_DOES_NOT_DISTINGUISH_AMONG_MULTIPLE_"
    "CONCRETE_PLACEMENT_CANONICAL_TASKS"
)
_REASON_PLACEMENT_COMPACTION = (
    "GENERIC_PLACEMENT_AND_COMPACTION_DOES_NOT_IDENTIFY_A_SINGLE_MATERIAL_OR_CANONICAL_TASK"
)
_REASON_PAVING = "GENERIC_PAVING_DOES_NOT_IDENTIFY_MATERIAL_OR_PAVING_METHOD"
_REASON_EXCAVATION = (
    "GENERIC_EXCAVATION_SPANS_MULTIPLE_SPECIFIC_CANONICAL_EXCAVATION_TASKS"
)
_REASON_MECHANICAL_INSTALL = (
    "GENERIC_MECHANICAL_EQUIPMENT_INSTALLATION_SPANS_MULTIPLE_SPECIFIC_INSTALLATION_TASKS"
)
_REASON_LANDSCAPE = (
    "BROAD_COMPOSITE_LANDSCAPE_CONSTRUCTION_LABEL_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)

_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 콘크리트타설 — 교량 및 도로
    ("d1a6603ef36c99cb34ab1596f47c56495aa362cdfa86709a095977ac3ae5ed96", _REASON_CONCRETE, "HIGH"),
    # 포설 및 다짐
    ("a8baeeb266fa35be2e5824cc69a5ad421dd5550b8d30d4f43004f63f94f9979c", _REASON_PLACEMENT_COMPACTION, "MEDIUM"),
    # 포장시공
    ("5a3a8db8415739b0a13f7747410f5b1071946ce1c1da5d5feb740eb069c2d3bd", _REASON_PAVING, "MEDIUM"),
    # 굴착 — 댐
    ("05f3d761f2d16da8e5629696c606cfef6416ec1ecb262322f43e4f08c829684a", _REASON_EXCAVATION, "HIGH"),
    # 기계설비 설치
    ("6d8bd4289c45ece3194cc66e14fe721d9c306cfed6a10dda96a8668dab8448ad", _REASON_MECHANICAL_INSTALL, "MEDIUM"),
    # 부대토목 구내포장 (paving family)
    ("6ce9caa3f42e1164040a6b1664e071eedf5c4f229d883481e3611799df7cc8a7", _REASON_PAVING, "MEDIUM"),
    # 조경시공 및 설치
    ("a19e3bec31a41204ecb62af0018841e4ad28103b100fc954724cfcd8ee0f3d9a", _REASON_LANDSCAPE, "MEDIUM"),
    # 콘크리트타설 — 댐
    ("ac0b554f4e3de2d03db0634535bd37f8d9bb54f52e906993d7529e507160f275", _REASON_CONCRETE, "HIGH"),
)


# §8 CANONICAL_GAP (25 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "2bbd903f93001e1712f3b807486b81f26322602862ae829c489412942d0a77c1",
    "ec6aac07bf727828066997afccbf7af61c67fdc934bc8a7e6a76c1f33fd5a996",
    "0f2268603a0346622e6415e618c8de7354a0f49b50792c040194017066b00843",
    "0aa5703f0c7c15e779d5a9108102e5f40e12dca57b370c1eac8b58c5c34790fa",
    "a026a5290bf9abb0f54cb9ec8badf530e5ffdfd569d98fb80584e19ad64384dc",
    "7ab1f5df5699375be53371c214287302f4d413f7b10064d87153956830b53f83",
    "9f6ecb0176e2e1ad4bb6b4377b00ae5f884e307d07c2691bbdc43ef9111c2fc2",
    "1cb50770f1bb524d051beff50b61612c90b8925b5d62e539d645860553041f8b",
    "b92d9c88d5f2d71854c125df522c72ddccfccff4ceb35cef6ea22c88c6044453",
    "897d23e85306524399afcc3a16caf076a3ba4210066c74cced9e43c0be6f6b72",
    "77ce2cec08de3c8a19f009a9193cc8d23db48cc779e6948ad3a3ef0f1e239a04",
    "1fd6bacc7ebe9bbb0c2c264933fb6d7ef1e4394fed0661f377d56138bf02fb7d",
    "1a45ff6d501b77388b0ac957c996341f936e9aae79bf57d78ae4b4d2b1b99091",
    "360c8dc59fb900f1a4893d7b29fb6f680d25bb0e94e2c190010f4573baebb71f",
    "63186b78bdb7538e80f124db2a10be5b1620b6ccf288e139a6a998356cdf7403",
    "a3c7e9ff9b7d02963259eb5e0d769ea140e2df54ea03fe4e79908c85c53c4dd9",
    "3a503445eed80fa60534191572650d7760bf52e3515357b17b011edf62b6ee7c",
    "61e2fdfa472e05a18ee0e0bec7fcdd099172f9382cdfa1b596bb2060978bd5f5",
    "647a7b943ebe8b1f0672df792245f227a0c88178f655f8703af42099382d8575",
    "e0ba6c5ab3af7883250aef0ba6dd9cb99c80e4d1fd071a227bdc81562ce0b963",
    "b73d5cc831ca678631570a1bb16247b75aeea1c58f5086dcf2a8661422dcc7f3",
    "b6e94551bd9c706e712eb384cf1a6e5ac049e9e4c26481032cfafd7920f93518",
    "243a1099c6e0e60cd875d8dc76f76996e3311f4134431cb8bc9721a68f2725ee",
    "7411f7f6feccaa9569111925fafd1de3051530b9942f8e2e19467a1217509e5e",
    "547b85d08747c4d11e5fdc2974a22d1164e6f5c29a4678ae98cc2577e94fe3ef",
)


# §9 NO_MATCH (56 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "94069902d9500afe2939647113637aa30d982bf8999e4471008392be74667893",
    "0961c3f8642dcbb60df9a878ac350f8a11b8556687c450f66809045f893f7dcc",
    "d09522c57917a9fa6768769062f740aa37817f1b84e010f165e04486d40584be",
    "7f5732149c3d9867c5267f99bebde3e84412dde7c36dc5620ee2f5aabc16cf00",
    "f9e36bb6b7c628c475e84fdac2d8afc8531ad7de0a81c23658ed52e01e3837cf",
    "2644afc54e043783211e17c16ea64156c9a4bdd1d912d842d335300720844666",
    "0694f415bddc74eae3f7ae4e981914cfed1e82bbd37c67aee59340535b117908",
    "8a2c047d5e1a264ffcd39e9410c5c101383b5c4c27aa1c2d6d22ffb63c7cfb5b",
    "4f32189647c85f9b2f65a6587306f18cca8f21ddd570ff36904e86ad523c61bd",
    "bfa5cf3d95dcd5652ce9929437171c95aa4ec7329c74eee2430052d2ba0b634d",
    "f615fc7b0aa845b2c2884faed314ffade898072fc246fe500e3637270370b17a",
    "c7520213ea812ef7e35329b306e27995055b1d1721d9fe804679d304e276a650",
    "3a5c9f5a4b8df57ee09cb6b40925b863322cf53dc30a98b80577fce256c26373",
    "8c97a2cb4abbee0941d6172ac2fe0ab19c3f9f73024710bd4906a8d44f364269",
    "c50cf3765ba0e886e63fcc7bc89389e6ba903855e8057e7fcc00cf3bced53a71",
    "8993d1081a9116937431842abe367e7eeee504bf4884195b0fb9db94a5c394af",
    "273ec1788daebd1c297192185338ab5c52b386a7889ad363a69ee7fce9ce5e08",
    "b2fa0d981d88286a47696ecb6c14dc5303b1af9580a7a20d4b511682d1dfceb6",
    "af27b18df7f84c7eb22d81b98bef2c11f74950f7cc7b69e690183e7889258a7a",
    "5626a6aaf92bd1d33219d6aa9f71a3577a4e10f0645afa1ab0b5c0b173cbe317",
    "6e734c7903e28812c7960605d44c2ea724134ec3d4e62990bbcd3d26fe48b1e1",
    "255848a98f2e526ca2752eec36094ed0de8922ec444c2cd2cd64e13b927c306b",
    "1afe0741d0a293ca0144abcdabaa8ab5c1e7d52ec5f86f037d825b1973dc3ef0",
    "bfca56d66c55eb640dcc8eded6d1c031a66a6a27829cd72aa44dbd6983c89d04",
    "54a94bfc9d43e393580686e89aadddca71b5807b162a7ac1e443d16f006a8cc6",
    "93a704dc81656b77da166bb54935fb2312f613a6eecb5397b337efb681dd8ae0",
    "c8e23200a7649947de623e28712498dd8069f3f3682a149b12da33978b0c3d06",
    "3186efe1682bd1de714ab85d3c840495ee8e01e8d8c7f2e864edd43cb996e4f6",
    "b1dd52abf778ddf3ca3fab2e816faad1a725afca4c5054076483ad938d3f9c0d",
    "77d7cd347a662ef5da6ac0cb6f06ca14f40d365483326d3bf62c379ecbe655ed",
    "65f0ad508f7a1e287e50c129eddb1bdf533397e85519ed5c879ff5a60a82df12",
    "63704ae21827dc2741e02e1db3e78a833a5b592adc86e6f52065945a6bb822ff",
    "3d773c30583b296c54450071de671fcf31ec52357456dedd776630e4b9efab82",
    "2e8a36ab5d5b120795b5da295ff0270afeeb53493506260b698fb3e539c35d04",
    "c7967fefa9488acb201f1d6775fa50e483ff1d0dbdd92a77d18c0bbffeea9059",
    "3c93ff67bf9ffe67b27392d50512a8eb2abe359989bba5fb295e7a709c7ac11b",
    "38e90e4e8d816c715dee7a9a7da36692e36082736d3a23b436ea457ca2e7790c",
    "b20583a238529782a83c794f5669ff5ec4077d02453756b5d81b33e028baa577",
    "a0c1b7a2f500a47401ec43aa9678fb0934863f948acb658efe01df96a19a655c",
    "a83ee8924733fb414aec18c77c0eac9e88196a33316661435c9ffe931d69bbb6",
    "3edd5d020fdf3efdb0696191d7a1be4a862a5a19d630460d943069bd12ff2b35",
    "ce438244bbd24e91e41c0abbcda1a7cfbd01337de9e079ff9db0c9a7e3f474eb",
    "8fed92326f54524d0cace202220491cd29cc3a9734d01e4b11f91b075cff8a94",
    "bec679c4032ad363445ba55af36471a67c0752c15ac0392ab7d40e463ad371f9",
    "3c8ccd69e1699f0c21395796ac454657aed0be772c6fb50e706b4f7f4232ca19",
    "eb6dfd7b3151e79a2ef7d7599f6f0ec8dccbe060bc4ae5fa735eabb2f1ebe48a",
    "9e01767898a2c7a396e789f8bdd7c1e537c7ccfe4e27cd6c02ca32e927ed0450",
    "4820f2c79ab6cffd9ecd2c8c44ee2a8b9b754eb875332f2053442330f14f5761",
    "4cde003709330e8d03949e555d12365ecee9b939706782c61ccdf8e63dfc3ee2",
    "12c6336e05655e770be6885f1f9bec9b9ee0c70890620e60e8673e85b1f22369",
    "87f146cb315b5b7a0965b7c06ae4b25bab7aeea77c4d809a68fa334c33680005",
    "a9a5acab808229853051c0edc657bd04a3ef31ff8e88465773c5eb61e51829d9",
    "a2b912e1442896548721c4444c43d38627bc338412a4ad939a7cdbe676bfa85f",
    "4371d96a206ce7b093598935451c5e861f6362bd4664460afef95a5ce3859ac7",
    "33f4fd724677670a11297ac8f7add04b88d9a409f3dd295c02821f12443f85a3",
    "c1656fa75662092a0caeb36129573c20838ca8f8da78bf7e66c37784766ad342",
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 6,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 5,
    ("AMBIGUOUS", "AMBIGUOUS"): 8,
    ("CANONICAL_GAP", ""): 25,
    ("NO_MATCH", "NO_MATCH"): 56,
}


def _build_manifest() -> dict[str, dict[str, str]]:
    manifest: dict[str, dict[str, str]] = {}
    for key, target, reason, confidence in _NARROWER_THAN:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "NARROWER_THAN",
            "gpt_reason": reason,
            "gpt_confidence_class": confidence,
        }
    for key, target, reason in _POSSIBLE_RELATED:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "POSSIBLE_RELATED",
            "gpt_reason": reason,
            "gpt_confidence_class": "MEDIUM",
        }
    for key, reason, confidence in _AMBIGUOUS:
        manifest[key] = {
            "gpt_semantic_decision": "AMBIGUOUS",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "AMBIGUOUS",
            "gpt_reason": reason,
            "gpt_confidence_class": confidence,
        }
    for key in _CANONICAL_GAP_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "CANONICAL_GAP",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "",
            "gpt_reason": _CANONICAL_GAP_REASON,
            "gpt_confidence_class": "MEDIUM",
        }
    for key in _NO_MATCH_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "NO_MATCH",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "NO_MATCH",
            "gpt_reason": _NO_MATCH_REASON,
            "gpt_confidence_class": "HIGH",
        }
    return manifest


GPT_DECISIONS: dict[str, dict[str, str]] = _build_manifest()


def _assert_manifest_shape() -> None:
    groups = {
        "NARROWER_THAN": len(_NARROWER_THAN),
        "POSSIBLE_RELATED": len(_POSSIBLE_RELATED),
        "AMBIGUOUS": len(_AMBIGUOUS),
        "CANONICAL_GAP": len(_CANONICAL_GAP_KEYS),
        "NO_MATCH": len(_NO_MATCH_KEYS),
    }
    total = sum(groups.values())
    if total != 100:
        raise SystemExit(f"MANIFEST_TOTAL_DRIFT {total} — {groups}")
    if len(GPT_DECISIONS) != 100:
        raise SystemExit(f"MANIFEST_KEY_DUPLICATE {len(GPT_DECISIONS)}")
    if groups != {
        "NARROWER_THAN": 6,
        "POSSIBLE_RELATED": 5,
        "AMBIGUOUS": 8,
        "CANONICAL_GAP": 25,
        "NO_MATCH": 56,
    }:
        raise SystemExit(f"MANIFEST_GROUP_COUNT_DRIFT {groups}")


_assert_manifest_shape()


# ---------------------------------------------------------------------------
# Freeze artifact
# ---------------------------------------------------------------------------


def _canonical_name_lookup() -> dict[str, str]:
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    if canonical_task_reference_sha(ref) != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit("CANONICAL_TASK_REFERENCE_SHA_DRIFT")
    return {r["canonical_id"]: r["name"] for r in ref}


def _load_b02_evidence() -> list[dict]:
    rows = load_tsv(B02_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B02_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b02_evidence_sha(rows) != FROZEN_B02_EVIDENCE_SHA:
        raise SystemExit("B02_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b02 = _load_b02_evidence()
    canonical_names = _canonical_name_lookup()

    b02_keys = {r["source_key"] for r in b02}
    if len(b02_keys) != 100:
        raise SystemExit("B02_SOURCE_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b02_keys - manifest_keys
    unexpected = manifest_keys - b02_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_SOURCE_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b02:
        decision = GPT_DECISIONS[row["source_key"]]
        target_id = decision["gpt_target_canonical_id"]
        if target_id:
            name = canonical_names.get(target_id)
            if not name:
                raise SystemExit(
                    f"TARGET_CANONICAL_ID_UNKNOWN {target_id} for {row['source_key']}"
                )
        else:
            name = ""
        out.append(
            {
                "review_key": row["review_key"],
                "source_key": row["source_key"],
                "project_kind": row["project_kind"],
                "work_type": row["work_type"],
                "source_name": row["source_name"],
                "source_path": row["source_path"],
                "gpt_semantic_decision": decision["gpt_semantic_decision"],
                "gpt_target_canonical_id": target_id,
                "gpt_target_canonical_name": name,
                "gpt_mapping_type": decision["gpt_mapping_type"],
                "gpt_reason": decision["gpt_reason"],
                "gpt_confidence_class": decision["gpt_confidence_class"],
                "input_evidence_sha": FROZEN_B02_EVIDENCE_SHA,
                "canonical_reference_sha": FROZEN_CANONICAL_TASK_REFERENCE_SHA,
                "review_authority": REVIEW_AUTHORITY,
                "review_batch": REVIEW_BATCH,
            }
        )

    out.sort(key=lambda r: r["review_key"])
    _assert_decision_census(out)
    return out


def _assert_decision_census(rows: list[dict]) -> None:
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    if dict(seen) != EXPECTED_CENSUS:
        raise SystemExit(
            f"DECISION_CENSUS_DRIFT expected={EXPECTED_CENSUS} got={dict(seen)}"
        )
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    if len(targeted) != 11:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['source_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 89:
        raise SystemExit(f"BLANK_TARGET_ROW_DRIFT {len(blank)}")


def build_census(rows: list[dict]) -> list[dict]:
    counts = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    keys_sorted = sorted(counts, key=lambda k: (k[0], k[1]))
    census = [
        {
            "gpt_semantic_decision": decision,
            "gpt_mapping_type": mtype,
            "count": str(counts[(decision, mtype)]),
        }
        for decision, mtype in keys_sorted
    ]
    census.append(
        {
            "gpt_semantic_decision": "TOTAL",
            "gpt_mapping_type": "",
            "count": str(sum(counts.values())),
        }
    )
    return census


def decision_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *DECISION_FIELDS)


def census_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CENSUS_FIELDS)


def render_report(rows: list[dict], census: list[dict], sha_value: str) -> str:
    counts = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B02-REVIEW-001 GPT KOSHA B02 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B02 Semantic Review (Frozen)

## THIS IS GPT SEMANTIC REVIEW

```text
THIS IS GPT SEMANTIC REVIEW
THIS IS NOT OWNER MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
CANONICAL_GAP IS REVIEW-ONLY (not a DB mapping_type)
NO_MATCH IS REVIEW-ONLY UNTIL OWNER APPROVAL
```

## Inputs (frozen)

```text
B02 SEMANTIC EVIDENCE SHA         = {FROZEN_B02_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b02_gpt_review_freeze.py
```

Claude performed no semantic inference. The GPT reviewer supplied 100 explicit
per-source_key decisions; this tool echoes them into the freeze artifact.

## Decision census

```text
MAP_EXISTING_CANONICAL / NARROWER_THAN      = {counts.get(("MAP_EXISTING_CANONICAL", "NARROWER_THAN"), 0)}
MAP_EXISTING_CANONICAL / POSSIBLE_RELATED   = {counts.get(("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"), 0)}
AMBIGUOUS       (AMBIGUOUS)                 = {counts.get(("AMBIGUOUS", "AMBIGUOUS"), 0)}
CANONICAL_GAP                               = {counts.get(("CANONICAL_GAP", ""), 0)}
NO_MATCH        (NO_MATCH)                  = {counts.get(("NO_MATCH", "NO_MATCH"), 0)}
TOTAL                                       = {sum(counts.values())}
EXACT_EQUIVALENT                            = 0
targeted (canonical_id present)             = 11 / 100
blank-target                                = 89 / 100
```

## Frozen SHA

```text
RISK KOSHA B02 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review

```text
B01 reviewed          = 100
B02 reviewed          = 100
TOTAL KOSHA REVIEWED  = 200 / 620
REMAINING             = 420 (B03..B07)
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B03 SEMANTIC EVIDENCE
STOP
```
"""


def write_all() -> dict:
    rows_a = build_decisions()
    rows_b = build_decisions()
    if rows_a != rows_b:
        raise SystemExit("DECISION_ROW_ORDER_DRIFT")
    sha_a = decision_sha(rows_a)
    sha_b = decision_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"DECISION_SHA_DRIFT {sha_a} vs {sha_b}")

    census = build_census(rows_a)
    write_tsv(rows_a, DECISION_TSV_PATH, DECISION_FIELDS)
    write_tsv(census, CENSUS_TSV_PATH, CENSUS_FIELDS)
    REPORT_PATH.write_text(render_report(rows_a, census, sha_a), encoding="utf-8")

    return {
        "decision_rows": len(rows_a),
        "targeted_rows": sum(1 for r in rows_a if r["gpt_target_canonical_id"]),
        "blank_target_rows": sum(1 for r in rows_a if not r["gpt_target_canonical_id"]),
        "decision_sha_run1": sha_a,
        "decision_sha_run2": sha_b,
        "census_sha": census_sha(census),
        "decision_path": str(DECISION_TSV_PATH),
        "census_path": str(CENSUS_TSV_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} freeze")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
