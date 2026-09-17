"""WO-RISK-KOSHA-B05-REVIEW-001 GPT KOSHA B05 semantic decision freeze.

Transcription-only tool — same contract as B01-B04 freeze. GPT is the
semantic authority; this tool ONLY:

  * Verifies frozen input SHAs.
  * Verifies the 100-key GPT_DECISIONS manifest matches the B05 source set.
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
from tools.risk_map.kosha_b05_semantic_evidence import (
    B05_EVIDENCE_PATH,
    b05_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B05-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B05"

FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b05-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# ---------------------------------------------------------------------------


_TARGET_FLOOR_PLATE = "813be6a8-13c4-4c96-9c90-36bd04348fb5"       # 바닥판깔기
_TARGET_BLASTING = "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"          # 발파
_TARGET_STEEL_ASSEMBLY = "af9b0594-96e9-4564-bea6-f80a261c55fc"    # 건축철골조립및설치
_TARGET_CONCRETE_LINING = "892b579d-42bf-4c3e-8a71-e37d8ce00e1b"   # 현장타설콘크리트라이닝
_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"             # 철근가공및조립


# §5 NARROWER_THAN (7 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "5f95e1f68791e5dc47687829a2373a43772d56d0eadc87dc4adc6cd5a999a4eb",
        _TARGET_FLOOR_PLATE,
        "STEEL_DECK_PLATE_INSTALLATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_CANONICAL_METAL_FLOOR_PLATE_LAYING",
        "HIGH",
    ),
    (
        "00dbfaa40674ac08e63808ce67f5a096e61660f14dab5b31330f9fd992f91fd1",
        _TARGET_BLASTING,
        "EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "a3cfbabe3d622390ae9a8783452c489bda011d993c92ae1cc7468afa31e4e6da",
        _TARGET_STEEL_ASSEMBLY,
        "STRUCTURAL_STEEL_LIFTING_IS_A_SPECIFIC_SUBACTIVITY_OF_BUILDING_STEEL_ASSEMBLY_AND_INSTALLATION",
        "MEDIUM",
    ),
    (
        "96b9aaece79474e2ac748a47c1dad8c195020feaf1f7fd575a9c23b2290f3192",
        _TARGET_CONCRETE_LINING,
        "LINING_FORMWORK_INSTALLATION_IS_A_SPECIFIC_SUBACTIVITY_OF_CAST_IN_PLACE_CONCRETE_LINING",
        "MEDIUM",
    ),
    (
        "0723febc423eebfd3a26864631c8b3e27fc13221ed6a7cecb3bf646eb3c4488c",
        _TARGET_BLASTING,
        "BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_BLASTING",
        "HIGH",
    ),
    (
        "f674b465439adee738eeb791ef13287d851431821d3197e34b66470795450273",
        _TARGET_CONCRETE_LINING,
        "LINING_FORMWORK_REMOVAL_IS_A_SPECIFIC_SUBACTIVITY_OF_CAST_IN_PLACE_CONCRETE_LINING",
        "MEDIUM",
    ),
    (
        "8734033aadf41b2e9395e5a304eff82fe166c1ee2085d4954286dbb5e3c9fef0",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
)


# §6 POSSIBLE_RELATED (3 rows) — all MEDIUM
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "870480a0a4af34f3b42a13dab2b5d2b06570bed038d8dc6b12ce68376da950c8",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
    (
        "4528b248b07014e58b1a75dc326bb1757a2da6b7f43158d2ec908ac7b8aaa51d",
        _TARGET_BLASTING,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_BLASTING_BUT_IS_NOT_A_BLASTING_EXECUTION_TASK",
    ),
    (
        "89a48e95ddff09d8c03c3038f9c846990b96bf2da2b881d35fe02908173ba561",
        _TARGET_BLASTING,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_BLASTING_BUT_IS_NOT_THE_SAME_TASK",
    ),
)


# §7 AMBIGUOUS (11 rows) — semantic-family reasons matched by source name order.
_REASON_EXCAVATION = (
    "GENERIC_EXCAVATION_SPANS_MULTIPLE_SPECIFIC_CANONICAL_EXCAVATION_TASKS"
)
_REASON_CONCRETE = (
    "GENERIC_CONCRETE_PLACEMENT_DOES_NOT_DISTINGUISH_AMONG_MULTIPLE_"
    "CONCRETE_PLACEMENT_CANONICAL_TASKS"
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


_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 도장 면처리
    ("821fd22a65bf0e12b644a9601e1527e8c8bc8eb16a4f01d9e45310e677e1111c", _REASON_PAINT_SURFACE, "MEDIUM"),
    # 부대토목 구내포장
    ("2e0de1de8710c35908d01741f3fe1452ba34da1107c931d0f5c069830c7763d1", _REASON_PAVING, "MEDIUM"),
    # 석재 및 타일 줄눈
    ("501605f8705037e741664023abe0a4fd9f8015a82a0c8f2b6ca153ae6ae9092d", _REASON_STONE_TILE_JOINT, "MEDIUM"),
    # 실외도장
    ("c55e0931eb9bb020bb919cd063c7b6ab394b8af66f0673ec3ca540cfd623f6cc", _REASON_PAINTING, "MEDIUM"),
    # 맨홀 및 관부설
    ("bd581420a468473675b65f9f73fb4ed4539da921e90b5bab4a699de533a6984e", _REASON_MANHOLE, "MEDIUM"),
    # 석재 및 타일 붙임
    ("11b1262236faeebb5c26c364f3d176c9fcfbf859afb26eeb47b04288997030e1", _REASON_STONE_TILE_ADHESION, "MEDIUM"),
    # 실내도장
    ("fe7b0a49566187aedcc9df7a8bc2bba20f81c3956f41bc8879cdeed09d346465", _REASON_PAINTING, "MEDIUM"),
    # 굴착
    ("d338979f3800ba580e63593cbd99c086c4041d99375b9e8f516a8f9b1b031509", _REASON_EXCAVATION, "HIGH"),
    # 금속 및 잡철물 시공
    ("5c41ab4ae0caa5a982ae5649ed108b8a246dcadc6cf8fc461906418c2d10dbb9", _REASON_METAL, "MEDIUM"),
    # 기계설비 설치
    ("c1028b4628d28bd6381d2d9418db1d3257154accf5b29cc18903a0589ecf75eb", _REASON_MECHANICAL, "MEDIUM"),
    # 콘크리트타설
    ("489e1dc03927c8581c75eba9275893bf0004c3287116cc9139d14be846e0aa54", _REASON_CONCRETE, "HIGH"),
)


# §8 CANONICAL_GAP (35 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "ce0838dc444681a356a5af5c6e90ba0848a7ccd970387dfc9a729fbfd63f46ca",
    "c1a1ed369a73ee5f2940d2dc00baf1eb1e9a21a913382433bfde87db733a657c",
    "1af0746c7900f7455ad264fa90e83cb76cfa8784b80275ad00eb25589ee45ec9",
    "40f1df01d2a63507362f8a6ea21c8c8b22e22019e79eaf0ccddbdea7a276c332",
    "2569dbe0963b9e27252dcc99b43db11b0b5264d2e53f46e496676e4506998884",
    "7afc3b785111405b19c4e007ed840d8b3609f41291a854d3d1c25596ca3f6c97",
    "8b6f5880d0f2d2d0d60e4d5e272d67f8a8e92887e23693149d8558001112b7c7",
    "a058da2420c14409d88b3fa3b82db91297646a079b14ed68ac6ca5a26064aebc",
    "c6063ede44a167b45b82d9fcacb7186a5e41deb1dd2e01d7143d5e56387b2bc1",
    "2a5210b25364601afd98b2d5afec927c679c0acb6067ea70de41e3c60ed845d0",
    "4e95962ae29a277187a1b36fb4e6ad2ea92518efc176f32f224c16554896a006",
    "af6329accfbef83c71f3c7c8cb14060e9042e687c48306ec345d9f1f425ca552",
    "43e3f4ecc303b9e326fe5409fc30488bf4666695e062f8708ecf1d199c18bc92",
    "67f6ddff6eeb8ac5b0fa959c368c0aece46467fcc717b3893ee3b48a69693ead",
    "9ef9237de8d790658f13e1d1e20938a16b146ff98673e39ab2da362be6c83b1a",
    "bfec41cc48fbc3aceacf9244ef2fa61accc7e514ac00df5516c92da57272e946",
    "8af86d1a5e260608fcbe9db316d0102817449d301303f4e5392184b71685edec",
    "95b037a7520449c389c0e0993ad04e38fc5b6e6eecc0cf6b3223b2c330e17009",
    "351c54240527e26742fbd2679a54f6424f329e153d93cb90299c013945383ae0",
    "7d73b6723d356aaeb929c70b03d256a57af8aa11c5adcc6a4a6e39ddf421843d",
    "fd427389d8b9f9a0d43d73a78299b777a47c31bcd91142636936b063b3c8d09c",
    "345ef4b4068d1a59b153db2a83644838a637ba280719b81bb092e3ec7644cf7e",
    "98e081d43a7a0ce8c5a3dc87c8ff154da5743737788b460eea5770d6c39b2e5c",
    "5486dd6e1e153e2e7de7ed8f1069de1ace43fbed95bcc3677148fba8c2575b97",
    "63b656eb00f65454ef34f3669a96417448814ec4fd5c18e01ef0da951537978e",
    "ba74b0ed1cd2b4d877497eb48a03a98b047449be9e9aec419e7cb188491645b4",
    "996f7e1e0a6b2984564ff8b824a007001a8166da3650559c6d9b8c1c6b102612",
    "c7b8c7d084719e5f758e6dcc315b298d07e4cf91a14ccf4d8c5f9992557b0b3d",
    "81c6af6cb3808bbd51b404d52005737f8a25791fe7d9e2de0f66c5540d49aa1a",
    "37a63ee733edb8991edd0316acd84af6501c156fa79c7574b807968f79a6494a",
    "c2107a3f0debfc26ed7ea70fee6701a3f30b531ffbca57d0d40ff4c7b9e31c6f",
    "415931a36ce6062706ea45f3914089d48cb8bdf2882b2d0586ec819aebac65f4",
    "56a96bbdad4726a128f4ada31d2b47eac76e3677cd828bf3a62f7e87b71c1bc2",
    "2fa9a94b50505d8e96f24da66c6059319a250d0e941c184e4a92477e865c34ab",
    "cca8cc97a529f7467d39fb7ed2ed0363bd528824c0814593bb1d9cddb5052a79",
)


# §9 NO_MATCH (44 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "5ac8a449bfecc8a72fea9bf5090646c4d9d6e84f1b86c4763df591e9b9a10947",
    "dcaea764b9d35409e620781b9b286f3bc8caa353ccadb5f4d64d995bbd71693a",
    "4341fffa7b4b37cbbd157be146465b2867975fa9a69c8adbb1c4fd212cb7d989",
    "9e435281cc4f3261b3c319b2aa077d5ae149a5cb6ba68e03db9310b2240a0345",
    "317ec0d66fe02755e07468c9f83111a437668a53e638e44bcbfddb3c093b2d87",
    "6f038dc372f73f03c9138c752e96dd55b7288633bccdb4d6f47fe59f11e7ea74",
    "a4f4fc45188b1632caa9ab63f68ca268054024740cff842d49bfd2e544a72d8a",
    "9cd9b085c33cfeb626a01bc28283e668b6547498b4c9d461792f6c0f6da61d4c",
    "af33f135a6f8e565f71b3b5fcdf2cf86270cfe680465ff7496262df6ec181b9f",
    "3d28ff27ac74fd92b90d280382f08dc758fee1268e93998fe98f751758a63aac",
    "62c8d902ba32fa4390c5cdb199569e573d5de160ea1e3eaa565f0923cebefe83",
    "5ab96958d90884a0d432504a7cbfad0d4d11ea5455b947ab84c63e6f56cb59be",
    "6924c3a5724b4b780e232493dbdb7f99e58912535db2734e6b3c3988f9288d5a",
    "e34e0c97f475de5bd952df5a09e26f4de535cd3934a9c12bc6a2b97450457033",
    "80cb29753ea7063b08e7151a4a006ee0de2b84854500b972ef3ab2b6fce1e11d",
    "702fb8de47f765047bc3bf183ccfd8ed50efe55f07e90732feca926f13e255c5",
    "6eb276897203e8ce18704f7dae8bc57702dc3575dca0da67752236405306584c",
    "7c04fecca32c5ead4d4b592b0cdeeaacc9c941e899d330a8352a7ebe3355caa0",
    "879f54e43b8336c141aeed703c6937712661df1c3f3c1eea2a18facac6bbc289",
    "47d4f4721447d7696851fd3ada8bdcc7dcfd63778b7854b27a128ca43868d553",
    "e27ec13e1a3f258f6428d9015888090f30bca582151e510712dfc3d954309a29",
    "de670809ca1c96b6ae82a7e5e5dce48a029c24f8c220fef1a5ae9eee414b62c1",
    "a222fadd507d15f7e95353b7899c139c8ab3d6f7b27658bf557c9a2ade3a47d9",
    "a2fc3f8977d68c26c5aab2b4a03163a8a095556e556695c28f9aa6afc0df80c0",
    "4160cd3ade62892e9b0fa6fa8dd4b9e59a21ba76a1d139227dd116af831ae4b7",
    "c7c14e61ac0bc329d9aa5ff8a8c20beb0c7614a78b1e2ad2396a62c5ecfad8d6",
    "e5704c6da3a44329c8b384bb01a63540395cbdb5e73eb6df4fcfbb2e1d981d4c",
    "e6c4aa3229a87abdf3d6a2675358e7ffaca81c1c52f6e45d4ae7a4baf40fe024",
    "56c6c87b3563ac5309d5bc90ecb87187b55ac6b965443d6eabd2876dc959effe",
    "e2cfd82d8a4d30f1ca411546ebfc2ccd1cd56f56d8a8c5eb2246fac1acb62f03",
    "e2149d67155b75c62a15d6efeee5bb85a8466466c545487d5cb12b1fcdffe2c1",
    "f4c27132c554127f8056d351d97695b06615ac31ef0d82a5f242917c06f3c193",
    "e008f2587b767b73ade1361179cb669a7eda642562e84e11c69a05723406e02d",
    "ab0d07fadc9024c302351bcab75efe80bbcd880a5b739d416b0f6ea32f54d33e",
    "327911a8fa48041ff6a97e43efea18313d2b64de40b819f8fa0ce5ce1e98dd08",
    "2858264ab96a5d67aedc51229fd975e34da805d068fe5007f9dae99fb2d863ec",
    "12c7dd8d41405c5f14e8b01b06409c0191d379a5210b42c754074d69ec03c157",
    "545c88f860cdd92a690f3b2fe44225d19d64d9bccd07b3f9d3254be8aff90ef8",
    "4d03e888f99f9b1beb0f19e81b215849e0a759db782571579944f3ec57866f47",
    "911bce63556fb2de20ce75eb6cbc8a0d31cf5889844475857f4f5724bfaa37b7",
    "401e36ffb201df3f700deaa6c18bf569b8d0b25f5ef5731f1fcdbc3a274edcf4",
    "bbf6e226a5e499ee1107466d0f60efe66dd999d4c3b0d639b6b2dcab8c351563",
    "676045fdf3e299c919e6d92d8cd50ffc4d1847e6f8fdb7f291bbf8d3a6b80b75",
    "a44ef0ed291481f9609833e14df6862349790478ab85097c99dfb75ed45a6d11",
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 7,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 3,
    ("AMBIGUOUS", "AMBIGUOUS"): 11,
    ("CANONICAL_GAP", ""): 35,
    ("NO_MATCH", "NO_MATCH"): 44,
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
        "NARROWER_THAN": 7,
        "POSSIBLE_RELATED": 3,
        "AMBIGUOUS": 11,
        "CANONICAL_GAP": 35,
        "NO_MATCH": 44,
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


def _load_b05_evidence() -> list[dict]:
    rows = load_tsv(B05_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B05_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b05_evidence_sha(rows) != FROZEN_B05_EVIDENCE_SHA:
        raise SystemExit("B05_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b05 = _load_b05_evidence()
    canonical_names = _canonical_name_lookup()

    b05_keys = {r["source_key"] for r in b05}
    if len(b05_keys) != 100:
        raise SystemExit("B05_SOURCE_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b05_keys - manifest_keys
    unexpected = manifest_keys - b05_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_SOURCE_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b05:
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
                "input_evidence_sha": FROZEN_B05_EVIDENCE_SHA,
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
title: WO-RISK-KOSHA-B05-REVIEW-001 GPT KOSHA B05 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B05 Semantic Review (Frozen)

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
B05 SEMANTIC EVIDENCE SHA         = {FROZEN_B05_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b05_gpt_review_freeze.py
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
distinct canonical targets                  = 5
```

## Frozen SHA

```text
RISK KOSHA B05 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review

```text
B01 reviewed          = 100
B02 reviewed          = 100
B03 reviewed          = 100
B04 reviewed          = 100
B05 reviewed          = 100
TOTAL KOSHA REVIEWED  = 500 / 620
REMAINING             = 120 (B06..B07)
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B06 SEMANTIC EVIDENCE
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
