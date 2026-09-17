"""WO-RISK-KOSHA-B03-REVIEW-001 GPT KOSHA B03 semantic decision freeze.

Transcription-only tool — same contract as B01/B02 freeze. GPT is the
semantic authority; this tool ONLY:

  * Verifies frozen input SHAs.
  * Verifies the 100-key GPT_DECISIONS manifest matches the B03 source set.
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
from tools.risk_map.kosha_b01_gpt_review_freeze import CENSUS_FIELDS, DECISION_FIELDS
from tools.risk_map.kosha_b01_semantic_evidence import (
    CANONICAL_TASK_REFERENCE_PATH,
    canonical_task_reference_sha,
)
from tools.risk_map.kosha_b03_semantic_evidence import (
    B03_EVIDENCE_PATH,
    b03_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B03-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B03"

FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b03-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# ---------------------------------------------------------------------------


_TARGET_BLASTING = "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"          # 발파
_TARGET_SITE_GRADING = "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"      # 일반부지정지
_TARGET_FLOOR_PLATE = "813be6a8-13c4-4c96-9c90-36bd04348fb5"       # 바닥판깔기
_TARGET_STEEL_ASSEMBLY = "af9b0594-96e9-4564-bea6-f80a261c55fc"    # 건축철골조립및설치
_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"             # 철근가공및조립
_TARGET_GROUTING_DRILL = "0ca62c6e-768e-4f68-8198-9abed44589b1"    # 그라우팅천공


# §5 NARROWER_THAN (6 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "641919de6e83ffb96c9ca7a6cf041a5defe192a379ca46b9dbdc92db4576a9f5",
        _TARGET_BLASTING,
        "EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "c24324369b26b27ab179942337a72783dc87fc46c97e2f6e5ce296025a9329f4",
        _TARGET_BLASTING,
        "BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "7efc915d5a83fd9a932fef678784a410008457f2e355f3c249e90f18393b1faf",
        _TARGET_SITE_GRADING,
        "LANDSCAPE_SITE_PREPARATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_GENERAL_SITE_GRADING",
        "MEDIUM",
    ),
    (
        "044cd69cac9e0eee8d561010be2296bdbf0163125f3e67ff40eaf8098bb83964",
        _TARGET_FLOOR_PLATE,
        "STEEL_DECK_PLATE_INSTALLATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_CANONICAL_METAL_FLOOR_PLATE_LAYING",
        "HIGH",
    ),
    (
        "8305162695fd8b6264d3bfb4ba1339e6cf9d4b1166202b1b723f5dfb5f27003b",
        _TARGET_STEEL_ASSEMBLY,
        "STRUCTURAL_STEEL_LIFTING_IS_A_SPECIFIC_SUBACTIVITY_OF_BUILDING_STEEL_ASSEMBLY_AND_INSTALLATION",
        "MEDIUM",
    ),
    (
        "b95ce311e9ca694ae6390886be6f640d03463a19c93613107684f97881e6ca5a",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
)


# §6 POSSIBLE_RELATED (4 rows) — all MEDIUM
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "4111216b25c72b30f66021e3293e45aa37a8ef71272a8fa2e2092394f2bb44dd",
        _TARGET_GROUTING_DRILL,
        "COMPOSITE_SOURCE_INCLUDES_GROUTING_DRILLING_BUT_ALSO_INCLUDES_ADDITIONAL_GROUTING_EXECUTION",
    ),
    (
        "87afd5a166ca917afa304f192a68292050ebd4ed90717d059accf459a896b981",
        _TARGET_BLASTING,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_BLASTING_BUT_IS_NOT_THE_SAME_TASK",
    ),
    (
        "70ffac8dcffb8e1b8ab004f6596dda93e798963b82f1742bd37c04a6cf046fc3",
        _TARGET_BLASTING,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_BLASTING_BUT_IS_NOT_A_BLASTING_EXECUTION_TASK",
    ),
    (
        "f9e364e5d200df306ba374afc3c060a3a65c8c963eb440e2270ca3f32591b09b",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
)


# §7 AMBIGUOUS (18 rows) — semantic-family reasons.
_REASON_EXCAVATION = (
    "GENERIC_EXCAVATION_SPANS_MULTIPLE_SPECIFIC_CANONICAL_EXCAVATION_TASKS"
)
_REASON_METAL = (
    "BROAD_METAL_AND_MISCELLANEOUS_STEEL_WORK_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)
_REASON_MECHANICAL = (
    "GENERIC_MECHANICAL_EQUIPMENT_INSTALLATION_SPANS_MULTIPLE_SPECIFIC_INSTALLATION_TASKS"
)
_REASON_PAINT_SURFACE = (
    "GENERIC_PAINT_SURFACE_PREPARATION_DOES_NOT_IDENTIFY_THE_SUBSTRATE_SPECIFIC_CANONICAL_TASK"
)
_REASON_PAINTING = (
    "LOCATION_ONLY_PAINTING_LABEL_DOES_NOT_IDENTIFY_A_SINGLE_PAINTING_CANONICAL_TASK"
)
_REASON_MANHOLE = (
    "COMPOSITE_MANHOLE_AND_PIPE_LAYING_SOURCE_DOES_NOT_IDENTIFY_PIPE_MATERIAL_OR_SINGLE_CANONICAL_TASK"
)
_REASON_PAVING = (
    "GENERIC_SITE_PAVING_DOES_NOT_IDENTIFY_MATERIAL_OR_PAVING_METHOD"
)
_REASON_STONE_TILE_ADHESION = (
    "GENERIC_STONE_AND_TILE_ADHESION_SPANS_MULTIPLE_MATERIAL_AND_SURFACE_SPECIFIC_CANONICAL_TASKS"
)
_REASON_STONE_TILE_JOINT = (
    "GENERIC_STONE_AND_TILE_JOINT_WORK_SPANS_MULTIPLE_STONE_TILE_SEALING_CANONICAL_TASKS"
)
_REASON_GYPSUM_BOARD = (
    "GYPSUM_BOARD_SOURCE_IS_INCOMPLETE_AND_DOES_NOT_DISTINGUISH_WALL_FROM_CEILING_INSTALLATION"
)
_REASON_ELECTRICAL = (
    "GENERIC_ELECTRICAL_EQUIPMENT_INSTALLATION_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)
_REASON_LANDSCAPE = (
    "BROAD_COMPOSITE_LANDSCAPE_CONSTRUCTION_LABEL_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)
_REASON_PLASTERING = (
    "COMPOSITE_PLASTERING_AND_SURFACE_FINISHING_LABEL_SPANS_MULTIPLE_CANONICAL_TASKS"
)
_REASON_UTILITY = (
    "GENERIC_UTILITY_PROTECTION_SPANS_MULTIPLE_UTILITY_PROTECTION_INTERPRETATIONS"
)
_REASON_WINDOW_GLASS = (
    "COMPOSITE_WINDOW_AND_GLASS_INSTALLATION_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)
_REASON_CONCRETE = (
    "GENERIC_CONCRETE_PLACEMENT_DOES_NOT_DISTINGUISH_AMONG_MULTIPLE_"
    "CONCRETE_PLACEMENT_CANONICAL_TASKS"
)
_REASON_EXTERNAL_PANEL = (
    "BROAD_EXTERNAL_PANEL_AND_FINISHING_LABEL_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)


_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 굴착
    ("7eb696e29d8a77d6bf88a8fdaf074b983d3cd8001d05c45b06d0e06290ce4276", _REASON_EXCAVATION, "HIGH"),
    # 금속 및 잡철물 시공
    ("99e019d368c50220d70cf8e1160fbab71490d47e806bfa989e48b1023ac6af86", _REASON_METAL, "MEDIUM"),
    # 기계설비 설치
    ("eab270443b4c66fa9088364549c476b0b5f61648af77b8d0f62225767262d17d", _REASON_MECHANICAL, "MEDIUM"),
    # 도장 면처리
    ("d56ac19c1d1349f8807744a652aecf4a772d72fc4be86edb9e8b5c18ac5d6b4e", _REASON_PAINT_SURFACE, "MEDIUM"),
    # 실내도장
    ("f111969fbf57d94093f07978fa820b0f607a4f5f9ebd7327196cba281ba415c7", _REASON_PAINTING, "MEDIUM"),
    # 실외도장
    ("51032bb5574d52f44470ce40c38d41198788827aa94a8a163ddf3e4c62632b79", _REASON_PAINTING, "MEDIUM"),
    # 맨홀 및 관부설
    ("b851dff1572b81adb3965d44f8894e01d5596a14a09a96162afdfc3f53083af1", _REASON_MANHOLE, "MEDIUM"),
    # 부대토목 구내포장
    ("7fd3740000a9057803956d0a99397cbd1f2b2a487caa1b7db03e343012c3f6a0", _REASON_PAVING, "MEDIUM"),
    # 석재 및 타일 붙임
    ("6a8a0838d39ea35fec218518045c6450f4e323306af6bdc142eff976ce3e043d", _REASON_STONE_TILE_ADHESION, "MEDIUM"),
    # 석재 및 타일 줄눈
    ("eca4302e6b1b61c2e1638f43e71ff02c0c06258f13984248f2422409a3ad69fd", _REASON_STONE_TILE_JOINT, "MEDIUM"),
    # 수장시공(석고보드
    ("d36bed370f6fdf32a02b7383ebfc94c06fb1e96a4befe2efd21c6582743017f3", _REASON_GYPSUM_BOARD, "MEDIUM"),
    # 전기설비 설치
    ("1f82b7297fd13199847c5a69a8dbe91ed56b7c1e902187126ea6dc572df8d679", _REASON_ELECTRICAL, "MEDIUM"),
    # 조경시공 및 설치
    ("ec5612b5ee2b71c4a0df3bb9182ce0bae57cef7accc142c48e08bca49f3b48f1", _REASON_LANDSCAPE, "MEDIUM"),
    # 미장 및 견출작업
    ("e9fcfabf57036c076a432585fe3c6b3cf2af51e8792010994a5981d53a6ee6a1", _REASON_PLASTERING, "MEDIUM"),
    # 지장물 보호
    ("30a8d460acac6328c2e22da98c5b8078e0db0483f687ac79ba5a4a6c986edec7", _REASON_UTILITY, "MEDIUM"),
    # 창호 및 유리 설치
    ("457270c99c0529ab3b4ae102cf88edbc2f2e49018d66d554434a0a11268ca041", _REASON_WINDOW_GLASS, "MEDIUM"),
    # 콘크리트타설
    ("8167d0552e3fe6125d19227d0dee39fd50b236a1741d3a841d52c5e3dfae7df1", _REASON_CONCRETE, "HIGH"),
    # 판넬 등 외부마감 시공
    ("d27445da57a40d7408d35dd44efe69c0424e316fcde7d995b01f861d9d2d2ecf", _REASON_EXTERNAL_PANEL, "MEDIUM"),
)


# §8 CANONICAL_GAP (36 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "e95b51f462f3a7d210ff6d259c8bbba36940f769bf5d01f91f1619564c9b4ec9",
    "08ffc6af8f6f903ddfb9a259065cab8ce35deea3475f2e2be91c86fd62020007",
    "0f914af5b13d89ed79842b0530cce3b041aa855f524964f4f95da19713cbcad0",
    "40c6ce60da288aea3ed42453b89147edeb0880e2d8ee19ded35c3ba7d2136d9e",
    "42d292a945dac92493a21b90d356b24cc2e748b9429e1a022627e348857d5e16",
    "f45b9d79931fd037574ff0ba333e91e0e09f05a68829825b4c78f0832b957dfd",
    "afde1d03c39b207a680a3fafab73b7bc4d0ca09e8ccde7500d34450df2438e0c",
    "af53170a57d62b569f5ce8d38ad0e0aa058b032bf7855cc5e865a4c83b561372",
    "2fb6696b3ecd07c993ec45709c0919ce61c8440cc7940b579662d1809a33ec36",
    "eeea4ec77d269a7a02a83b6c2467a2108c3b45d98d2e79553d39ae11a921ed13",
    "87817b191eba6709da65c0ca08adef5884dfc47a35cdda85584ad945996d88ba",
    "a3c2d03e8f4c15994ceaed38e61a543f38cc894c1972ddb987353448be784383",
    "54899044adf4059bdf3750ca6a569593202a93aad4687dd50556d01da38d6cb0",
    "e91b31abec319ef7f8c06a7582968654f9b350ae4b50f5d098d103608cc06db0",
    "15e2fa0f400a8cc72d760d6ea384b39f1d1e045ec3b5e17cf6a7bb62f664e95f",
    "81447bdc8507ddfe3eba050f52ad8547f8e7a3c92f0f653d5b9be9b7578c3be4",
    "3ea97b59aeb58b392d05259ef4897f0fe190714fba478f82894811eb0705e64d",
    "9f9077c91bcde34a29c7c35c73408188aa5b7b099106287f6a80c9f60128677d",
    "300cc441c555190f291ecee74d93ea73459afbdaf39c68c507e45cdfbed4250b",
    "2b67ccd0fb6da13ba4783952c552bf2c388da55aecf978439890deacabcbb0f7",
    "c4b98bf861ba4d6a4794c5a9b0559fee550f97d0315f6ebacaf06bb58107fa58",
    "dec6962dcc78af7d9a88e0cac150d60a8f74a79ba8b1efb5b5040127f4b076ee",
    "51a42fc969d56f80d66fef67a7bdd106b7aff7fcea948c4481283031a35c4133",
    "e9caa71556b8def0db63c1f8a96b737e50e2062dfd3c65f167db812fec1754cf",
    "cef2a43ee14b5827ca4f6396013927c1b1f98b0cc81dea94c65bcd1e91ab81d5",
    "7d50bc2e1134e118de971888e37367424ad4a6991e4c69b6c804f6b955eb67a6",
    "cb505df03e7e9ee6fb80dcf5ad9a251b1bff529d28a305d60940c8ee3fd28991",
    "c1f9b2d9b036ebd931dc4ea08eeef1f78b2438cf364ff3c71c0e101f28f91692",
    "db63511d421c1d3dfa3cb2a67f1ec8f589e930fbc1e22dd52e4840e75d417e1e",
    "d3c4b64dc019c432fb35495006d0ed8716e01d87f149bf12c811e634de299f0e",
    "d538734d61212ec43db49ae775657cdf24a62873f97726028b25841086cbf16f",
    "322c75bb0ae22db5df5bcb5cb0a5fe33acb69ae55b722e8c80dadf78d8e60b30",
    "647e47a05715dc19246202143cff19451daa8179de1a2abacdcc14f03dabba5f",
    "7d96faeffcce08c4e02c5bf853603a47358cae7d4c55817e903c86662cf0d394",
    "a294df26da424643dc84d475bf8f4c2206c88b306011ba0f722fc03f3493a2b4",
    "ce68c1d84cb548f46f0db48d63e3c9d1ddd0311f68eed8e815d5660cfa6635a9",
)


# §9 NO_MATCH (36 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "ea6f02036d002043a0007cbd8d3672ede902720f74f559df623c82a377c749c6",
    "c07699a02282e60619084ad295f1a4eb2bf0e5042f5d45aa2af473f525565d51",
    "cada1cd7f6d0fe613d9951e45554a562f9f50c2c4098f74140c358529138d317",
    "6d7b3cb1434173048e13c3c5195f25c0454652b6bd8791505974fc43cbf2959c",
    "445c759f7f43ba2c694678f0514e0baa4c4119bee2a9ff5ff362aa81845b92f2",
    "e00b161f7e4f267073b0896af31ec117beea9c6aeb9d44224acac6d5eb9a63b9",
    "fa06a31de85c676f97e7157fe59ed2f4f109d7ee6bef3d451fea58814bb493b1",
    "da7f0d4923a73926ee6a7665a109e727140d0dfba9a6002c05fc3e9764c07268",
    "b0b41a0e5d65bb105ed02d089cd2dcb263a56e9deb403b7ab7d93fa2a3264ad4",
    "4482536e5dfc1af60e1c3b73e2a34cff839b0912dc319265c8b4e6ad9e2a2a1e",
    "073fe39243dc26126e077c5e3a9d7e9b22721ba1252e08b81e97df17a9b56498",
    "f00495f47da5244e3ff84747c8091d272a9ac8e91aca585e27160ea50abfde9a",
    "c80c0e578482743b07e8e277aaa0c5c10cb444988fc97d3ae480abd99503b789",
    "b629276f616d4f721ef1c527b72858d058cbb57859fdb22c07bf3ca39ea05488",
    "b23825a05a5dfc9402c0ac1c4108f2d34ea7bc9176b9ed18a4488df9456b1d43",
    "d4d8fa7a2b72730b357ede5c942dc26c13c44b991d06200745da86aa271d4a3c",
    "b73e7c0bcfd0b88f163e3058fbb8941e2d8e9d129adb84bc793c2e2949deda3b",
    "3320adc21f5c71d9693bc373dea401d4a512de1e509be14f252103b4b727b3c6",
    "73c02722f5c8e28a32ea5b5ae1430347d930317b21669ab89f7881ce63c406f2",
    "eccd6d7cfb6dbe07483ebd032a3774d50276527f231151ecb0604e923611eb1c",
    "3449d51406695c376a6d6b58b955ce797fe3d587ece4cd85e9c0069e0f3d6bb6",
    "b8fff74387f80a130c0f59ee2f39e64e1af9f102729cfe1b3c8bff94e982bd50",
    "c8b7f0b3475ab1614bf4af66e468bca51f07fcb7f2e3a6969213795f4470056c",
    "f43ada026dd073162b39c258aebf80c883007ed37134a6b4e019b9ca035c5bf2",
    "18d621c09ea5c09722c6485972f3ba15c59228f8c337bc03f1b8bb0a4a87e20f",
    "a52efcc258b97140579fa0bffaebada0141ebb6e469b16cd6735eec61f143a02",
    "4ca5a37cdc34595e425eb02d1220608e2c0acd8de85f190371d0feb9e423a9e4",
    "f84b015f7fe29a75b20cb0e1a3fc444b1ae35ad05bccaf64eecba25aebd1b9f3",
    "88b763dabd9492e7013c18c47dac92e5c6a8f1c01ea78351d1fb8fc6bc24141f",
    "1ace5bcd4713cfa6c71f3bf780ec408d5b7fa3bd2c6bd2c1882ff1867212815b",
    "fbea6462a5a2ca60052e24d3b4fed9cf0e1a23e68f24ade0aaf570895ff2161c",
    "7d60667ab44630bb92a9adfec7c0ce987d4316ef963edce323675a91d276ae28",
    "124c4b8606a9c6f4da6f32369564062d831a879aafc100287615055491399cd7",
    "5fb5fea53b1173cc06b632a7f1170b23c709d83f53a6856eb72213cdbf57a998",
    "540f5bac99a27522818a09d2ac60d538a936564ffde9aa374bd1f5a1abb1ed0c",
    "43092bae16ae67b732779e0e21173346f90260a141d7435dc92e119fca13c915",
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 6,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 4,
    ("AMBIGUOUS", "AMBIGUOUS"): 18,
    ("CANONICAL_GAP", ""): 36,
    ("NO_MATCH", "NO_MATCH"): 36,
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
        "POSSIBLE_RELATED": 4,
        "AMBIGUOUS": 18,
        "CANONICAL_GAP": 36,
        "NO_MATCH": 36,
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


def _load_b03_evidence() -> list[dict]:
    rows = load_tsv(B03_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B03_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b03_evidence_sha(rows) != FROZEN_B03_EVIDENCE_SHA:
        raise SystemExit("B03_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b03 = _load_b03_evidence()
    canonical_names = _canonical_name_lookup()

    b03_keys = {r["source_key"] for r in b03}
    if len(b03_keys) != 100:
        raise SystemExit("B03_SOURCE_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b03_keys - manifest_keys
    unexpected = manifest_keys - b03_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_SOURCE_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b03:
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
                "input_evidence_sha": FROZEN_B03_EVIDENCE_SHA,
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
    if len(targeted) != 10:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['source_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 90:
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
title: WO-RISK-KOSHA-B03-REVIEW-001 GPT KOSHA B03 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B03 Semantic Review (Frozen)

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
B03 SEMANTIC EVIDENCE SHA         = {FROZEN_B03_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b03_gpt_review_freeze.py
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
targeted (canonical_id present)             = 10 / 100
blank-target                                = 90 / 100
```

## Frozen SHA

```text
RISK KOSHA B03 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review

```text
B01 reviewed          = 100
B02 reviewed          = 100
B03 reviewed          = 100
TOTAL KOSHA REVIEWED  = 300 / 620
REMAINING             = 320 (B04..B07)
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B04 SEMANTIC EVIDENCE
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
