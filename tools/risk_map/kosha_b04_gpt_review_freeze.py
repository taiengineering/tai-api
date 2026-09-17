"""WO-RISK-KOSHA-B04-REVIEW-001 GPT KOSHA B04 semantic decision freeze.

Transcription-only tool — same contract as B01/B02/B03 freeze. GPT is the
semantic authority; this tool ONLY:

  * Verifies frozen input SHAs.
  * Verifies the 100-key GPT_DECISIONS manifest matches the B04 source set.
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
from tools.risk_map.kosha_b04_semantic_evidence import (
    B04_EVIDENCE_PATH,
    b04_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B04-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B04"

FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b04-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# ---------------------------------------------------------------------------


_TARGET_BLASTING = "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"          # 발파
_TARGET_SITE_GRADING = "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"      # 일반부지정지
_TARGET_TOPSOIL = "a7106b20-76ca-427f-aa45-2f0b1d417f15"           # 표토제거
_TARGET_GROUTING_DRILL = "0ca62c6e-768e-4f68-8198-9abed44589b1"    # 그라우팅천공


# §5 NARROWER_THAN (3 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "dac358b068a2a0d16a872cad08be58355993bdcb3f30f403b4f345fbd8ddfa46",
        _TARGET_BLASTING,
        "EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "c627b12da00d39f633c0d5cb113cb8a8751051d207d3d5bf4e332d9b742c4fef",
        _TARGET_BLASTING,
        "BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "f49a179de6093d47a278c11d9365575a90b90336630b7307e62e0d408bcf118e",
        _TARGET_SITE_GRADING,
        "LANDSCAPE_SITE_PREPARATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_GENERAL_SITE_GRADING",
        "MEDIUM",
    ),
)


# §6 POSSIBLE_RELATED (4 rows) — all MEDIUM
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "dcafdcc9bd780cc457898c8134b6beb99bd2a6c3d853b4aa2e5d3fb940cfd162",
        _TARGET_TOPSOIL,
        "COMPOSITE_SOURCE_INCLUDES_TOPSOIL_REMOVAL_BUT_ALSO_TREE_CLEARING",
    ),
    (
        "38c49be164542c0b351fb4ff3c363b57d8b4175e22ae0290eb583a8f26fcb4de",
        _TARGET_GROUTING_DRILL,
        "COMPOSITE_SOURCE_INCLUDES_GROUTING_DRILLING_BUT_ALSO_ADDITIONAL_GROUTING_EXECUTION",
    ),
    (
        "c3acea604bd3cde456b9e3dbf2e132643569cb8b08a2a467166b42c0eca1b6ca",
        _TARGET_BLASTING,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_BLASTING_BUT_IS_NOT_THE_SAME_TASK",
    ),
    (
        "c31ba1c6c3445549b2f8c7d07b58a07b9c70c770b0feaee67a78a3bae8d622fb",
        _TARGET_BLASTING,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_BLASTING_BUT_IS_NOT_A_BLASTING_EXECUTION_TASK",
    ),
)


# §7 AMBIGUOUS (16 rows) — semantic-family reasons matched by source name order.
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


_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 굴착
    ("d112394908ff4025366bff4f7a2f8e291fb2b0fba69adfb6fc87da0eb6c579e4", _REASON_EXCAVATION, "HIGH"),
    # 금속 및 잡철물 시공
    ("dec16f7b86d1f135da0c745ae44877337b08f49cfe3b8c402376b992fe3e04c3", _REASON_METAL, "MEDIUM"),
    # 기계설비 설치
    ("08bd3d179f6c4e12b0f2400ad1ad0e91d804ace409c4eb2a03d48751887d467f", _REASON_MECHANICAL, "MEDIUM"),
    # 도장 면처리
    ("3db0653349f8d4c86f85617042af9158557506c3ad1b57837b51d70dc1fcede3", _REASON_PAINT_SURFACE, "MEDIUM"),
    # 실내도장
    ("980fd27bcbc9f38633c387245b693272b18882f9d65d747c5b616238c5c47b50", _REASON_PAINTING, "MEDIUM"),
    # 실외도장
    ("67a5ae300a5be9ddbcaf1367b12b3ac240279cb0e428feaa25a2be155f7e2572", _REASON_PAINTING, "MEDIUM"),
    # 맨홀 및 관부설
    ("e5ad6b11f8acb74cd4df9c45e25e65230cbe99ef5c5c39aa0d9f6c081cadc16c", _REASON_MANHOLE, "MEDIUM"),
    # 부대토목 구내포장
    ("49b47a1f9cb0426343aaab25c94591530421ec9d26695d3b8996e182fbc0a8a6", _REASON_PAVING, "MEDIUM"),
    # 석재 및 타일 붙임
    ("b439ae20f59071a21eabd2b8236e351dfd1ac0a38c3747bdfdad9f93e6e7673b", _REASON_STONE_TILE_ADHESION, "MEDIUM"),
    # 석재 및 타일 줄눈
    ("4a3dbd922c659097d1433bcf1ab545cdc988aac7912806e9f5316923df385e44", _REASON_STONE_TILE_JOINT, "MEDIUM"),
    # 수장시공(석고보드
    ("a9e21fc4337e48cb8d364706242f68e719f6ac182395a7839467370d59e08659", _REASON_GYPSUM_BOARD, "MEDIUM"),
    # 전기설비 설치
    ("c469423c996f4827ed7cefc2fe69a483650af49c1587107d4e175cebe032a7a8", _REASON_ELECTRICAL, "MEDIUM"),
    # 조경시공 및 설치
    ("e1e8494c4682b61509797c0083fd99e6444219af53d56a2ec5f314885a3b363a", _REASON_LANDSCAPE, "MEDIUM"),
    # 미장 및 견출작업
    ("286428d849d269933a6938c6bd28f240a595510328eed027cbfc6d3b202b6ff2", _REASON_PLASTERING, "MEDIUM"),
    # 지장물 보호
    ("490d9717a56d63cdcb8c7fb13277fcbf3a28f06db2fc8ed14f0beedb4bc892ef", _REASON_UTILITY, "MEDIUM"),
    # 창호 및 유리 설치
    ("019f81e967d0613b9e8f8704c283433f5d133afb3812f31a2b98e57bde4392e3", _REASON_WINDOW_GLASS, "MEDIUM"),
)


# §8 CANONICAL_GAP (35 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "adf138af62fff2a82c4227b13705c62452d832b3d5bb8018cb306bdb2e899167",
    "8f4716b1b13605c48c674023bea46275087187fbdaf29b853aa0cac1454beb6f",
    "ef0dca172a1e7c92398c3c24b536447a426a232cf874cd5100beffe3e598a138",
    "47f8cf7b99ffa8da408f45464b47bacf2cb14cfa2f23ffbe4a3c55b450867fb4",
    "cb5606407d4712b93b42636b00cbe08d73a0942eef9871404d36b4035e0f133e",
    "1222b83e4dafed6e2f0c28e6c8cd0b9f55c480ab468725dcc11baa6eb2863723",
    "e899c4555560678cac9e7bfc4d5dc35420b4233548f372eb89626cf6069c5568",
    "8c1870e9e0a8dba161bbcf0cff1f0c252147b167a32cefd06cc8974c5dfbe335",
    "38364b46ef78650d06a0fbbaf20effc96c13553cd290c2cbe4a8261e1ae22a27",
    "1be243ef9c1a86350d3f6a0013db41b7710a90c11246437e93d38db487dcc387",
    "4c6fc21e4b2c02321bad2aeefc9a04b010b119d2259438a62860e4d745845d46",
    "24737f2782a5e165b432823c01bb0ead175079c15315b1161a4b48d296c09f5d",
    "a5e4987bd41f3117d452b453898fb254595827d82827acb038db8b2cca143027",
    "159bbf40c54e5d41103ac09b1362af1849698955ea5b38e978d7c1d60db85af0",
    "fccabf461287db4559e99721dd62712ead4ed633d132e1bd6e843b73e9a5231a",
    "81fd2ac32f8435cf648f45c596e8db2cc71f90d5c20344e7b64628547b748f94",
    "b09f78343467b7ee078a78ee81b33b3196a05ee4a7c70fa80f843e9df800d0db",
    "b7ca3a94df179acee12b52174739b90a7d98d6a695b2d54fa3bc980ce8b09597",
    "c52163d322a199cc5e0886a2e7131da67e28a3e849466c5c1843a569606cdf4f",
    "58b626e740b9e2b64c2b860870edd3a4263718c7095c946d329630853afc76b9",
    "6d2c8e67e629ceaa6e14af02eb50dd52486a5e1ddb44c8e6968f7fa57bd305c5",
    "623fe784c71c2bcdfd7a56a705abaa590342f8b5c4b52d1dc527920569ff7777",
    "538c52013b7c4cc06d4209279261fa7c61c53acca688a79aa48e8c3d20a3f185",
    "fb59516e87511b16b5358a328613fcce302cf67a1fc65627c09a2a8d56563b8d",
    "e9530f19d314cba21f1f5ae979263f7e5c042fb4edb953581f020ac41895f85f",
    "778eddad35144cc6ab125ed81e9776740c9df50826e63e5b1e84286f5f55efc2",
    "6bb391825a6189c52fc7df1d16a18e8b38840194819d817aa947ed4f71d8790b",
    "40336be964a68926fb84ab18c32ff6bd445b2c3ee197bb8aae32893a4a7fafe4",
    "28b02366a6737971d409e792d89b64020e4823d5d5f67d21f7f94f6aa462cf55",
    "633c402b5189ba7fba22484b108229cf68850d497b43ac1e22a2c4062b160ed5",
    "14cfd0e4afaa4f8a7a60d9038c5857282322e1913e9b78aacbe21fde6b9c0c42",
    "6811a3d5f71808690edd53b71cce882ee4d5020c5d50b51cae2ca773f15e1710",
    "3864517fdfa26f5eee51df732d2c7358a93d72a9f0b1d45926ea7bd5fc6d3178",
    "97215d36192af91ac0bc1604636d6de2990a32db422d0faaeccbab315bed457a",
    "9762a98a4285f1eec3acf5ae34a9f8b631587a169788227a07538e3f22d9d47e",
)


# §9 NO_MATCH (42 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "cb385c6026aff9239bb2001fa85d8d5bd0a270b9a3874bfe8b72bf1d3f3b78db",
    "e1f84c8e7c24dac21a1685226b001daf072ae296f357b7aebf2312596111f9df",
    "14da7e29d2fb1f30d9277b6418fcc3f0e789f3c0f448f1b2a98bacaa25c216e2",
    "65fe2f95b9469dc3db6ebf294276a2f619b1d928a82aef392a8dc9a9bab2004f",
    "1e36fcb209cbef0338ba3a17b14450c0e4f063d4a94e4d9e788428924aa66b1d",
    "a1bbed7286d6231ff794ba56f60ffe86080e07751c444506651c3d232dc6a149",
    "903955464a6d486b12c7b44250919b0fc66157e9f5ed4b756d7b284de481ce73",
    "90de93f8f59b62bea8cddb696eaa3388642ef19b6bf4316efde52fba07e8a281",
    "5a8cecc9525bb45ffa825d9eaebc84e28ed622d0530f80466aebb567e427a896",
    "82cd1b3a10bebc24d585aaa3f94eff29acba12e6fd22b60625bf7ee27207b17e",
    "56dbb446af9811709d22e7634d1a7934f28e9832090c9acb5a588a15fd83b61b",
    "83b5312231d6cadc17c4f77b775ce355b46a195e5bda9ff7cd23ac5128e0ca03",
    "e3a9752786d2d0a42979415ca8d7ae7b37ea78e242c46d4309ed356dcc9cf8d1",
    "0fbf56aa888ace63fc9f6420d1826e730dcd18de638bd19fdc051de9aeab85cf",
    "3290efaeffd119872ee5bfc138a200880363182f7f6cd643f35c5536c85ec920",
    "2725a167b89e81667f068ebb355cf352cdbcc40971dc2f713985ad1bfe5fd3b1",
    "5935f427d146860c004bf85d9213ee01e6a2fdd3798f71a05af14ea0e34b06f8",
    "d8125c0492071664a5fca41960e73a7c3241e0c7e8c785eade83c1701f330e21",
    "5ea411d54b3c859a2c3fe4530b7fd61066bbd21d27fbbefdd504d7df4e0095fd",
    "05e3619800e14b269ce3281da7770b324138aa5eb249fc57d5b8c80a7d0e633b",
    "c31a68194e27e1c85a1de05bbbaaaa38318a1e4a04b765e49e2e50773cd840d8",
    "2271e711b3742463351a83e3f64b0309393015917b193229a0347d0c9fabd115",
    "1ada6e9838b9e2b3434a2c7e1bbf0efa6c53721628ebbba4963b6fa376711d52",
    "057c8b2452e839c86043367e0b4b9448b3c3073e51d5c491866598f6196c4e3a",
    "2ae1edd0c1d28922f6244cdd073e282222c8d4134f9799e215f2f3f7a0050114",
    "b33fcd40d98b4db170b171a34ff03ab5d7297d19e01fbf1462d7fd537c8aef94",
    "901a83f96dce87dd7b7757770aaee4ae5fe9c67d83dad582d02ec78836719ea6",
    "224eb2a7155a72d28f15f6489ac8501297ce85eb348da2e749e333bf055fece6",
    "b0a3330bec95ccd075bf4d69c4b280bdfad5ba7ba7c72d3ca685a8fc4097d373",
    "6199b56acf90614316d21db982a227222346ca35ddbec719b84157a57d54ff27",
    "faf00d6b07d1884c46415783ff601f4f6455e07a0620e426181cbf5f64ee2e87",
    "366e0193a0135dc61cd3fa86b8dd482ecd6a0a045b996379220144be502444c6",
    "e7e1a3d92ea7a5b6dfb22dc8a6ee1b3e4d737b638729ebeb6c160d7188473286",
    "cc7e75f371aa005ccfb842368b9f2f8842f8f33d3ac23fcbac559d31a1ed4007",
    "861bb01ec296a1634a1073bbae6e3a0655ce9fb303d8b7498ed69c9f0e294a5d",
    "f86f1107a55bbc577b9ddcbc457941ea31bc599622cd8423908dbc4afcce10b8",
    "9782fca06b81e271b48e09f88ea18403ef6b542e3458ded0d8b11a4c00b654b6",
    "2c1445b55e302ce3158176371ce9edcf52c7c29cc93b268755c1852076c35c80",
    "3ebe9fc0862fdc1f89fb1afc0e8ccc773403df022562e02a4f6468ce6aead7e6",
    "7d12e8aeabfefb2d34e5bd4b1c0abe1c9c97053059c92a40091bf37e81e2e105",
    "c0d6be81f2967d720ba5761ff6a56fb1a07b08cae394f63b5fe10506324d19eb",
    "9d4d1116c36361c04be1d19dd9e59b8b1c96212d2cdbc74d0711878c5086fabb",
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 3,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 4,
    ("AMBIGUOUS", "AMBIGUOUS"): 16,
    ("CANONICAL_GAP", ""): 35,
    ("NO_MATCH", "NO_MATCH"): 42,
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
        "NARROWER_THAN": 3,
        "POSSIBLE_RELATED": 4,
        "AMBIGUOUS": 16,
        "CANONICAL_GAP": 35,
        "NO_MATCH": 42,
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


def _load_b04_evidence() -> list[dict]:
    rows = load_tsv(B04_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B04_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b04_evidence_sha(rows) != FROZEN_B04_EVIDENCE_SHA:
        raise SystemExit("B04_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b04 = _load_b04_evidence()
    canonical_names = _canonical_name_lookup()

    b04_keys = {r["source_key"] for r in b04}
    if len(b04_keys) != 100:
        raise SystemExit("B04_SOURCE_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b04_keys - manifest_keys
    unexpected = manifest_keys - b04_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_SOURCE_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b04:
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
                "input_evidence_sha": FROZEN_B04_EVIDENCE_SHA,
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
    if len(targeted) != 7:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['source_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 93:
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
title: WO-RISK-KOSHA-B04-REVIEW-001 GPT KOSHA B04 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B04 Semantic Review (Frozen)

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
B04 SEMANTIC EVIDENCE SHA         = {FROZEN_B04_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b04_gpt_review_freeze.py
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
targeted (canonical_id present)             = 7 / 100
blank-target                                = 93 / 100
```

## Frozen SHA

```text
RISK KOSHA B04 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review

```text
B01 reviewed          = 100
B02 reviewed          = 100
B03 reviewed          = 100
B04 reviewed          = 100
TOTAL KOSHA REVIEWED  = 400 / 620
REMAINING             = 220 (B05..B07)
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B05 SEMANTIC EVIDENCE
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
