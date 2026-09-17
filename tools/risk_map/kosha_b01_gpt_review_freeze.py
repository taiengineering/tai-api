"""WO-RISK-KOSHA-B01-REVIEW-001 GPT KOSHA B01 semantic decision freeze.

Transcription-only tool. Semantic decisions are the GPT reviewer's authority
and are captured verbatim in GPT_DECISIONS below. This tool does NOT infer,
score, or re-derive any decision. It ONLY:

  * Verifies the frozen B01 evidence and canonical TASK reference SHAs.
  * Verifies the manifest keys match the B01 source_key set exactly.
  * Echoes GPT decisions row-by-row into the freeze artifact + census +
    report.
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
from tools.risk_map.kosha_b01_semantic_evidence import (
    B01_EVIDENCE_FIELDS,
    B01_EVIDENCE_PATH,
    CANONICAL_TASK_REFERENCE_FIELDS,
    CANONICAL_TASK_REFERENCE_PATH,
    b01_evidence_sha,
    canonical_task_reference_sha,
)

WO_ID = "WO-RISK-KOSHA-B01-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B01"

FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b01-gpt-semantic-review_v1.md"
)

DECISION_FIELDS: tuple[str, ...] = (
    "review_key",
    "source_key",
    "project_kind",
    "work_type",
    "source_name",
    "source_path",
    "gpt_semantic_decision",
    "gpt_target_canonical_id",
    "gpt_target_canonical_name",
    "gpt_mapping_type",
    "gpt_reason",
    "gpt_confidence_class",
    "input_evidence_sha",
    "canonical_reference_sha",
    "review_authority",
    "review_batch",
)

CENSUS_FIELDS: tuple[str, ...] = ("gpt_semantic_decision", "gpt_mapping_type", "count")

# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# Any change here is a new WO, not a code refactor.
# ---------------------------------------------------------------------------

_TARGET_CURING = "3258e587-68ab-40c8-80df-dd4fa0db60b7"       # 콘크리트양생
_TARGET_STEEL_BRIDGE = "995ba818-1aac-4a5b-82cf-6e83ee485bbc"  # 강교조립및설치
_TARGET_BLASTING = "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"      # 발파
_TARGET_PC_TRANSPORT = "2517aed8-23bc-4e23-a7c7-fcd8743847a7"  # PC부재운반
_TARGET_TOPSOIL = "a7106b20-76ca-427f-aa45-2f0b1d417f15"       # 표토제거
_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"         # 철근가공및조립

_EXACT_EQUIVALENT_KEYS: tuple[str, ...] = (
    "26577e536beb035265d4252724aebd6fe842aecc139876c6c98cb6d154176afb",
    "671dcd6c9997ede5e685b234e1d1cbf9364e32c806850b641a72b4bacf1d6702",
    "bd53cd0415ea1ff132f95ca99b6f8fa377d6706faf79b7c21df2afb4522e39b8",
    "285e80db3db34518bb6e10df63cbca2627a0c74254de770bb1f63ced445d9165",
    "c0edca8f389a36179400591a367c6c0328d74366b5e3d4a319790efbece6313e",
    "f69625a34c19ff0a83728d54a04452cdb1b4b04fdf58da8ffc5d53eac4aceedb",
)

_AMBIGUOUS_BLASTING_KEYS: tuple[str, ...] = (
    "ec78ad39f92a0dc8099740d1d9ecb29561726cb4f81588b0089809b72be8b37c",
    "db5892c1ba71a85ba1f8a739d3a4b3d227a7f303f1007ae15307825b33233d51",
    "ed5fcfed0565a57a3b7a713b84aaf18daee31db3f70256b7712138f8a69e65b5",
    "6fb1ed75c42513bf51b1b98f46c74b8a96aabedeba9a56b67deacefbc1aa7521",
    "fc3f3dc1922de2b6290051e78475f59e83c5b5ca9c8f37756f2e873f696aa922",
    "a9883fcefdbe237836139b69b9924669e5b504663a218da56e68eb88cee25ad9",
)

# §7 AMBIGUOUS - other (6 rows, each has its own reason/confidence)
_AMBIGUOUS_OTHER: tuple[tuple[str, str, str], ...] = (
    (
        "7ae6a94de7404f042d115235075024bae9fbfa9e98072428336607a3e6c10e07",
        "PSC_MEMBER_INSTALLATION_HAS_MULTIPLE_PC_PSC_ASSEMBLY_CANONICAL_INTERPRETATIONS",
        "MEDIUM",
    ),
    (
        "d36d83795e5353c29c81c891bb876a6c6dc5adac64517cf9d52d636b89968400",
        "PSC_GIRDER_LIFTING_AND_PLACEMENT_DOES_NOT_UNIQUELY_SELECT_A_CURRENT_PC_PSC_CANONICAL_TASK",
        "MEDIUM",
    ),
    (
        "5bca42b61bb9ff7076ad4dc7189329fd80e253af88f00e41fefae55ee87f7527",
        "SLAB_CONSTRUCTION_COULD_MEAN_PC_ASSEMBLY_OR_CAST_IN_PLACE_WORK_AND_SOURCE_DOES_NOT_DISAMBIGUATE",
        "MEDIUM",
    ),
    (
        "3451e54a0b6243825471230c6a013af585c16a9aab44684f888540ca9c7c79cd",
        "GENERIC_EXCAVATION_SOURCE_SPANS_MULTIPLE_SPECIFIC_CANONICAL_EXCAVATION_TASKS",
        "HIGH",
    ),
    (
        "901cb91207a35e91cdac2fd3bccf6583a48f7c073ed8dc79bca7f6fc698f4b7c",
        "GENERIC_SITE_PAVING_DOES_NOT_IDENTIFY_MATERIAL_OR_PAVING_METHOD_AMONG_MULTIPLE_CANONICAL_TASKS",
        "MEDIUM",
    ),
    (
        "562f0e8d7ba06c730135553e1c41cd33a4e97158ee89c332ec758ffbda516add",
        "GENERIC_UTILITY_PROTECTION_SPANS_EXISTING_PIPE_ABOVE_GROUND_AND_UNDERGROUND_PROTECTION_CANONICAL_TASKS",
        "MEDIUM",
    ),
)

# §8 NARROWER_THAN (3 rows)
_NARROWER_THAN: tuple[tuple[str, str, str], ...] = (
    (
        "117406f2e819009f2ddab47b1f76558bb8357a553b4fed9892d713cd51954a59",
        _TARGET_STEEL_BRIDGE,
        "STEEL_BRIDGE_MEMBER_ASSEMBLY_IS_A_NARROWER_COMPONENT_OF_CANONICAL_STEEL_BRIDGE_ASSEMBLY_AND_INSTALLATION",
    ),
    (
        "c4b70e8dc6758d004799ee4d2983759fd58654017e1b4b421d92d4d3f84f1190",
        _TARGET_BLASTING,
        "EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
    ),
    (
        "af804b488a17b2ec4da7642d45e7ab537de018710aa6965d7d522287326d78da",
        _TARGET_BLASTING,
        "BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
    ),
)

# §9 POSSIBLE_RELATED (6 rows)
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "5f42f02170a6d35a1da1d418fb421462b2abde0949ef7fc707e447cbed5ab861",
        _TARGET_PC_TRANSPORT,
        "PSC_GIRDER_TRANSPORT_IS_STRONGLY_RELATED_TO_PC_MEMBER_TRANSPORT_BUT_PC_PSC_SCOPE_EQUIVALENCE_IS_NOT_ASSUMED",
    ),
    (
        "3fbab883ebce04d2d75a4203c4e55166ffe6b8f379746511a25889702a843ab2",
        _TARGET_PC_TRANSPORT,
        "GIRDER_LIFTING_AND_LOADING_IS_RELATED_TO_MEMBER_TRANSPORT_BUT_NOT_EQUIVALENT_TO_THE_FULL_TRANSPORT_TASK",
    ),
    (
        "a2dbb2d7ab94cf648aef33afdb32b004bea08d6b7455d44c72f7e5dd6b3ce919",
        _TARGET_TOPSOIL,
        "COMPOSITE_SOURCE_INCLUDES_TOPSOIL_REMOVAL_BUT_ALSO_INCLUDES_TREE_CLEARING",
    ),
    (
        "15dc1da3628724396d21e84348a3638c7daa943e3c8785f9b248206402a7dfcf",
        _TARGET_BLASTING,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_BLASTING_BUT_IS_NOT_THE_SAME_TASK",
    ),
    (
        "680726b3338f703a8760b842ea1a5ef3385c97ca41a477444e854583e080bb53",
        _TARGET_BLASTING,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_BLASTING_BUT_IS_NOT_A_BLASTING_EXECUTION_TASK",
    ),
    (
        "aa4c8b0134ef2667a2a95ae200c4ef3a04932e39129f7821c319b09612f15838",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
)

_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "236ef8a995c2c401fcaa7c63537ef37ec49702de7c1a8a477b7eea49d7883f49",
    "2f2539a928530b962d08f2fc5b3b8d6dbdeefedc328e2fefc39b6d5cf5e2a750",
    "8e89eaa62441655166dd67dae3e374dd772af33ce210dd7d7c6a3694cc69192e",
    "c9d75b183cc7c7703b9253ae0854a600aba68b3b37e23271aaff82ce1ce83eed",
    "0b7b703019d74370ac5c5b800396e3f5d447111ba87601a916ee917ea6cc676e",
    "783a4308b5156f917e797c5bdf96fa0e83e60a115f2c0fedb0915f646213d676",
    "7d74fcc2e05c3711afe1ee592d6e6594fcd0821002d1cd8dad56291aa76ab235",
    "96bdcb2b67727f386a9d0d699b6a437e0a25d898abb341efd80e5e09014994d7",
    "246911b38de7918628fa28af43bc677def32355c703c6db479bfef59220e8b17",
    "9d09ae53fe0db130fff1b5fa3cd18532d9cb1cef4b258569f4c440db56b531e4",
    "95325382db45d5a69e350a470584c1bc2565647ae5ee56fbb20e912048421eb5",
    "738888c38d5e6b7e20cf7e64e71e9e4b25d28fa0c610c9e9c1f6a8434709624a",
    "fbce1fe5a661c25e07e10ab8d02b972cf8fa7a2552501235271d082b4f80874d",
    "fade0c4775fa9b581c6a3b27998eac7671631e72bb3fbdbd2d50c6b511520a2d",
    "b093b482b8aaa19f1d9e5153942bbd6825ff556aa89dcf82e95b6c46542cf94e",
    "ccb479b1ce1354d7c06005824916589ce4f9163213692fe0f5a09685e046235b",
    "f318a6367c5dc2cccdf6486b79be8581edb32c38213e97cba71d7fe93aa0cc32",
    "816586652bf0e6f867af223af78be91f930db02cab14af74e0459b5ce3ae6d13",
    "d8e9235523a44019d116f25c9e2dd5f780707469164f40606f555b27ed12c5ed",
    "8597a4b65d8bec9af879b88a4d1512c6157b1c0a58d97089c3ab815c5b048fe3",
    "de77eab02b4344088f3bb7451a86ebe0c95472da53cdf15be5cffb45f92ff16b",
    "3c9afd24913e114514da195cf6444d90787d9b1526dfe6d8f401363e7258d6a8",
    "a4e505fdc68d1fae7afb31a7f033be5d78fffdffe2bba4c1749d1c20953042f9",
    "51774c38ff2614a66f3ccfc31914e7a8b9cf378129dc4bf15c6da28addbe13f0",
    "13f5acc508f0074b90815f2648d37686736e58fbd47b6ae477c3f8418c734c2c",
    "bd1d6d90e1b97c6d17285aaf5d3ff795c27af4b19b1112017d0655a1d0c01746",
    "2eefe143d41fac357b70f84850955ed33845878c299f2f6862a1c140f1371a1c",
    "0945929bed943c4472bf187e5de0350a7dfb1be91e8b7e088fcfd8e889d29ba8",
    "a8e4cfab5b9671483a47a3e896172f4cdc68824c836a98058ded45d9ddbe4a1c",
)

_NO_MATCH_KEYS: tuple[str, ...] = (
    "3a246af5cd4d88cdb28f6a604ef760436407366119009b2bbfeae768eea12232",
    "59603fcac4f8e6ee8cc7e467659ed32142b84e4f5f0b8a00a887d5f4cf83ed63",
    "085ce79620c193a053febdd3b79a09903359c3efa25ef3a1172e24ced15686d0",
    "4eef074aeffde5b8b5573dd0e64584f92310315277a9d99b06c4415f0232d54f",
    "04ee780b216197114f8b99d27fd454116817892455074d7e81650c15153146bf",
    "6bfbb2a76f1d34975f0393350e800983072a1be640b4a44bf145def3d948c5d1",
    "bb16fcf5d1f6bf604585a7d3c493f722587f1c50d12c074423789b10e251100f",
    "ec97dd7791f31e74d8aadff7b2e9dcf13953124082ddc6383aeb2b95b99f0bfb",
    "bc78f44c9167a4f55446f25b21aeccf6070d6fd9f7c86859affb1183d1e6a559",
    "1b5d4020f5c95c145e356cf5e3af056dd74268530ce278c01b31b435a1a380e9",
    "b9d2df01c6381b471a856bb11472b91880cd4067ad7f7da3e686dc2e39cfb6ec",
    "f217269ef64ca9569d41e3dae50b2a16cd2ff269068f10d1eca7c5cdc89f1f82",
    "78b434ca0fc713e089c1e63faf7f01fc5cbac9be97a5a0d9d8482418792a3c6d",
    "b5f1210b27d626cea8c4aec82ea4607c30b2364d97ef85c666310da9f1e21350",
    "0286a110e0040c6c283cd38b1c5d64c97be5662b5bed3f52ca59eaf0b0a9ae81",
    "35e08e3f2b7a7487336c53c07d7483b3a4337bcd3ac6e4055501bb91ba63a19d",
    "7917b6b3052241b851eb8cf220e41d61c46cddf38623a2c831dfc13ef03b1224",
    "aeb39e422eee00f41c9ef9d5e401f8a29001c55356521d83f9160c5ed678cbe0",
    "75f98d169c983113d072aa5f671e4a923fc038162471af9eb2fc88ffa41c004c",
    "391c743f4ee848fe0a0c59b57b2e41b7f5b49c8424534d7d03b4da0ca7afbdb4",
    "714d8c08d67942ed14f6ec300bf91d81c0aa4372c04fb5e1fea08db1008f6b63",
    "3d2551353832f2f9a0fc994de2b1289a089261fcf0bfb5d9fea96215502f12e8",
    "7a9f719d322d041cb5ec491eb76a112d1fc16c5f33c5c2ddf342434b333c078b",
    "ffeb9df6082ba9d3f99bb8a9cac2ffbb257154df81409d99f0d7533a2305edfd",
    "0803bdd6d3d40ba15db3e42a50928c73bc8072614d7cf86727a2a64719e350de",
    "c7597142fbf291f590268ceeb5a736a6d7f0712d9ae60c261a50a89a1eef3612",
    "43784c7564410a0ec1871ff8b41104d551f6ee09eb643a75c2cd629eb8c998b4",
    "74179e5d289b11be8b08c6906c38f78aa4a4425277bcc7549050127916639d80",
    "f73f605ec6e5e73c669be7bcd8061fa991e32d58780f1df11f4ed1c26fae186b",
    "2c3954323b33723af6e203f3ef3577270d3f1a3e428deccb204567a485be531d",
    "6f2abb0edc62bd731feba5238646f6c1aaaecb3e63a1662639c6361f6ef24106",
    "0fb20702a43232d966ca868f1593e655aeed3e49b10e89b7c65146216c1d093b",
    "4d84eacd00fcd96a2d339fd875ac80e6d832b4ecd8c4839b4cad4541c2cf4f9c",
    "d35c4fc79dc02972722afee7b4944499f457262a1318b0cef9cf350d6f1af389",
    "821f6aa390740b166a4b434f47639e50db7e9dc52445bc0ae52e4f0fbdaf3c87",
    "fde2bd33e1fd96f3abd29bcd72d48c21d9602bf484821bb3eef5bb6e3b32dde7",
    "8753bd7c25a8c318abfb28d70e6156e954b5ac7e28945f44fa7a82df409e2e36",
    "93c13180caae91b05ffa08f81056279c805504fe0d94e305431f31368316163e",
    "dcdebc3b57b27b9c35155669f6f9c81437131d77c91b144529b223b2dcefd8ce",
    "91f7f540feca418fc9b1037f0a9259c4ccbf458c14dbfe3a107586f73dc209f7",
    "fe53d49171b2e45171072e5dfd4ba9e5e1c07ba554e79904b9a893b58532de69",
    "9a7457fd852f7d90c4e3aad4f59604f7bda18beaaed57fbe01a8b053d02c4ba4",
    "e8ec7b6323c40e040c0848d6e6f5693d9601e5faadc53b633a36900a931ea701",
    "d9c541d180afdaaca7e1a27a3b9e6c40610337ff837f948187a5e7fa5b90a3eb",
)

_EXACT_EQUIVALENT_REASON = (
    "SAME_CURING_TASK_SEMANTICS_AND_COMPATIBLE_CANONICAL_CONTEXT"
)
_AMBIGUOUS_BLASTING_REASON = (
    "SAME_LEAF_NAME_BUT_SOURCE_CONTEXT_DOES_NOT_UNIQUELY_SELECT_AMONG_"
    "MULTIPLE_BLASTING_CANONICAL_TASKS"
)
_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)

# Expected census by (semantic_decision, mapping_type).
EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT"): 6,
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 3,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 6,
    ("AMBIGUOUS", "AMBIGUOUS"): 12,
    ("CANONICAL_GAP", ""): 29,
    ("NO_MATCH", "NO_MATCH"): 44,
}


def _build_manifest() -> dict[str, dict[str, str]]:
    """Literal transcription — no semantic inference."""
    manifest: dict[str, dict[str, str]] = {}

    for key in _EXACT_EQUIVALENT_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": _TARGET_CURING,
            "gpt_mapping_type": "EXACT_EQUIVALENT",
            "gpt_reason": _EXACT_EQUIVALENT_REASON,
            "gpt_confidence_class": "HIGH",
        }

    for key in _AMBIGUOUS_BLASTING_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "AMBIGUOUS",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "AMBIGUOUS",
            "gpt_reason": _AMBIGUOUS_BLASTING_REASON,
            "gpt_confidence_class": "HIGH",
        }

    for key, reason, confidence in _AMBIGUOUS_OTHER:
        manifest[key] = {
            "gpt_semantic_decision": "AMBIGUOUS",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "AMBIGUOUS",
            "gpt_reason": reason,
            "gpt_confidence_class": confidence,
        }

    for key, target, reason in _NARROWER_THAN:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "NARROWER_THAN",
            "gpt_reason": reason,
            "gpt_confidence_class": "HIGH",
        }

    for key, target, reason in _POSSIBLE_RELATED:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "POSSIBLE_RELATED",
            "gpt_reason": reason,
            "gpt_confidence_class": "MEDIUM",
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


# ---------------------------------------------------------------------------
# Manifest arithmetic invariants — checked at import time.
# ---------------------------------------------------------------------------


def _assert_manifest_shape() -> None:
    counts_by_source = {
        "EXACT_EQUIVALENT": len(_EXACT_EQUIVALENT_KEYS),
        "AMBIGUOUS_BLASTING": len(_AMBIGUOUS_BLASTING_KEYS),
        "AMBIGUOUS_OTHER": len(_AMBIGUOUS_OTHER),
        "NARROWER_THAN": len(_NARROWER_THAN),
        "POSSIBLE_RELATED": len(_POSSIBLE_RELATED),
        "CANONICAL_GAP": len(_CANONICAL_GAP_KEYS),
        "NO_MATCH": len(_NO_MATCH_KEYS),
    }
    total = sum(counts_by_source.values())
    if total != 100:
        raise SystemExit(f"MANIFEST_TOTAL_DRIFT {total} — {counts_by_source}")
    if len(GPT_DECISIONS) != 100:
        raise SystemExit(f"MANIFEST_KEY_DUPLICATE {len(GPT_DECISIONS)}")
    if counts_by_source != {
        "EXACT_EQUIVALENT": 6,
        "AMBIGUOUS_BLASTING": 6,
        "AMBIGUOUS_OTHER": 6,
        "NARROWER_THAN": 3,
        "POSSIBLE_RELATED": 6,
        "CANONICAL_GAP": 29,
        "NO_MATCH": 44,
    }:
        raise SystemExit(f"MANIFEST_GROUP_COUNT_DRIFT {counts_by_source}")


_assert_manifest_shape()


# ---------------------------------------------------------------------------
# Freeze artifact
# ---------------------------------------------------------------------------


def _canonical_name_lookup() -> dict[str, str]:
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    if canonical_task_reference_sha(ref) != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit("CANONICAL_TASK_REFERENCE_SHA_DRIFT")
    return {r["canonical_id"]: r["name"] for r in ref}


def _load_b01_evidence() -> list[dict]:
    rows = load_tsv(B01_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B01_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b01_evidence_sha(rows) != FROZEN_B01_EVIDENCE_SHA:
        raise SystemExit("B01_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b01 = _load_b01_evidence()
    canonical_names = _canonical_name_lookup()

    b01_keys = {r["source_key"] for r in b01}
    if len(b01_keys) != 100:
        raise SystemExit("B01_SOURCE_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b01_keys - manifest_keys
    unexpected = manifest_keys - b01_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_SOURCE_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b01:
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
                "input_evidence_sha": FROZEN_B01_EVIDENCE_SHA,
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
    if len(targeted) != 15:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['source_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 85:
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
title: WO-RISK-KOSHA-B01-REVIEW-001 GPT KOSHA B01 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B01 Semantic Review (Frozen)

## THIS IS GPT SEMANTIC REVIEW

```text
THIS IS GPT SEMANTIC REVIEW
THIS IS NOT OWNER MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
CANONICAL_GAP IS REVIEW-ONLY (not a DB mapping_type)
NO_MATCH DECISIONS ARE NOT PRODUCTION NO_MATCH ROWS UNTIL OWNER APPROVAL
```

## Inputs (frozen)

```text
B01 SEMANTIC EVIDENCE SHA         = {FROZEN_B01_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b01_gpt_review_freeze.py
```

Claude performed no semantic inference. The GPT reviewer supplied 100 explicit
per-source_key decisions; this tool echoes them into the freeze artifact.

## Decision census

```text
EXACT_EQUIVALENT (MAP_EXISTING_CANONICAL)  = {counts.get(("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT"), 0)}
NARROWER_THAN    (MAP_EXISTING_CANONICAL)  = {counts.get(("MAP_EXISTING_CANONICAL", "NARROWER_THAN"), 0)}
POSSIBLE_RELATED (MAP_EXISTING_CANONICAL)  = {counts.get(("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"), 0)}
AMBIGUOUS        (AMBIGUOUS)               = {counts.get(("AMBIGUOUS", "AMBIGUOUS"), 0)}
CANONICAL_GAP                              = {counts.get(("CANONICAL_GAP", ""), 0)}
NO_MATCH         (NO_MATCH)                = {counts.get(("NO_MATCH", "NO_MATCH"), 0)}
TOTAL                                      = {sum(counts.values())}

targeted (canonical_id present)            = 15 / 100
blank-target                               = 85 / 100
```

## Frozen SHA

```text
RISK KOSHA B01 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B02 SEMANTIC EVIDENCE
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
