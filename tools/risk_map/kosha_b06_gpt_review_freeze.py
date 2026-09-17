"""WO-RISK-KOSHA-B06-REVIEW-001 GPT KOSHA B06 semantic decision freeze.

Transcription-only tool — same contract as B01-B05 freeze. GPT is the
semantic authority; this tool ONLY:

  * Verifies frozen input SHAs.
  * Verifies the 100-key GPT_DECISIONS manifest matches the B06 review_key
    universe (the WO §5-§9 keys are review_key values — a per-row identifier
    stable across the frozen evidence TSV).
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
from tools.risk_map.kosha_b06_semantic_evidence import (
    B06_EVIDENCE_PATH,
    b06_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B06-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B06"

FROZEN_B06_EVIDENCE_SHA = (
    "b0df9c2e77642184bc98fa67bc94e5073a41913ccc9a867da1ec5bf3bbfc34c2"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b06-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# ---------------------------------------------------------------------------


_TARGET_SITE_GRADING = "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"      # 일반부지정지
_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"             # 철근가공및조립
_TARGET_TUNNEL_BLAST_EXCAVATION = "473d69ee-4433-487f-bc43-c35c1f2ea28f"  # 발파굴착  (NEW in B06)
_TARGET_TUNNEL_WATERPROOF = "30fe37a0-0bd8-4c44-bd9b-76b3625115f5"        # 터널방수  (NEW in B06)
_TARGET_TOPSOIL = "a7106b20-76ca-427f-aa45-2f0b1d417f15"           # 표토제거
_TARGET_GROUTING_DRILL = "0ca62c6e-768e-4f68-8198-9abed44589b1"    # 그라우팅천공
_TARGET_CONCRETE_LINING = "892b579d-42bf-4c3e-8a71-e37d8ce00e1b"   # 현장타설콘크리트라이닝


# §5 NARROWER_THAN (10 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "0fc81a44983f02fb0813bf00f72b4c31c598c36acedba4574b7c0df4d295ccf9",
        _TARGET_SITE_GRADING,
        "LANDSCAPE_SITE_PREPARATION_IS_A_CONTEXT_SPECIFIC_FORM_OF_GENERAL_SITE_GRADING",
        "MEDIUM",
    ),
    (
        "4d02f51a104ce4e5d03b78619a3583f453fc4257553c3c3eadb2310415360612",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
    (
        "9d54c7749d12fab41798527831ff937f89024e5967b1d53eb632738c8783b6fe",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_BLASTING_IS_A_SPECIFIC_BLASTING_PHASE_WITHIN_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "f7d56f58e49b5750a233b61544f079a11d1d38e1de0b5405d98790ba5bbd59e9",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "b9d472e5e46bc3916f97415202c996d455d8ea24619e02e057716b14f6bb6117",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "f34ddc13a28da5a08134244516427b291eaedb860b115c3e9cdd97e0de23dae6",
        _TARGET_TUNNEL_WATERPROOF,
        "TUNNEL_WATERPROOF_SHEET_INSTALLATION_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_WATERPROOFING",
        "HIGH",
    ),
    (
        "61f1c0640b68ae4cdca7daae0a030ac6eb44b2b5be43dca5504517487fb6fd6e",
        _TARGET_CONCRETE_LINING,
        "LINING_FORMWORK_INSTALLATION_IS_A_SPECIFIC_SUBACTIVITY_OF_CAST_IN_PLACE_CONCRETE_LINING",
        "MEDIUM",
    ),
    (
        "9088a846120cb59ea4e7c2846405725694ad5b4a0213239f7d29c647563bf7ed",
        _TARGET_CONCRETE_LINING,
        "LINING_FORMWORK_REMOVAL_IS_A_SPECIFIC_SUBACTIVITY_OF_CAST_IN_PLACE_CONCRETE_LINING",
        "MEDIUM",
    ),
    (
        "4b7f35075945ac8574382ea86b452481102745416a47c7160c069a2b8c2f3185",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "EXPLOSIVE_CHARGING_IN_TUNNEL_CONTEXT_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "5c0e45143e5a61b513dbd8599311863f3a8437c6cb93e2d6ce9b27afe30e18da",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "BLAST_HOLE_DRILLING_IN_TUNNEL_CONTEXT_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
)


# §6 POSSIBLE_RELATED (6 rows) — all MEDIUM
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "b2f7a39d6bc5a8eddfd2f15103d407c0559f3f6331cd5a685a26af1c8775a71d",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
    (
        "2735eaa49ed2cc102f9e7b8c68804e3f50c88a4530078c1a2b9e80d5257ea48d",
        _TARGET_TOPSOIL,
        "COMPOSITE_SOURCE_INCLUDES_TOPSOIL_REMOVAL_BUT_ALSO_TREE_CLEARING",
    ),
    (
        "f82d63a60f213d46e42cdd7ec2d7480047d3060b53246db105f8b5b2b228c06d",
        _TARGET_TOPSOIL,
        "COMPOSITE_PORTAL_CLEARING_SOURCE_INCLUDES_TOPSOIL_REMOVAL_BUT_ALSO_TREE_CLEARING",
    ),
    (
        "b7f85fbe92d08c80b666a5eaecd48353672a011ec00e953d7ce40e883893a3b9",
        _TARGET_GROUTING_DRILL,
        "COMPOSITE_SOURCE_INCLUDES_GROUTING_DRILLING_BUT_ALSO_ADDITIONAL_GROUTING_EXECUTION",
    ),
    (
        "2737ea01efcec70667b65716ed9cf4c6376f7e6871dbaeeea7f2e0656d1674db",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "BLASTED_ROCK_HANDLING_IS_RELATED_TO_TUNNEL_BLAST_EXCAVATION_BUT_IS_NOT_EQUIVALENT_TO_THE_FULL_CANONICAL_TASK",
    ),
    (
        "ac53a96e16248a1aec21547d317bbd250bc2a6e5b3b4ee4535a589a60f80dc25",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "EXPLOSIVES_MAGAZINE_MANAGEMENT_SUPPORTS_TUNNEL_BLAST_EXCAVATION_BUT_IS_NOT_THE_EXECUTION_TASK_ITSELF",
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
_REASON_SPECIAL_TUNNEL_REINFORCEMENT = (
    "GENERIC_SPECIAL_TUNNEL_REINFORCEMENT_DOES_NOT_IDENTIFY_A_SINGLE_REINFORCEMENT_METHOD_OR_CANONICAL_TASK"
)
_REASON_EXTERNAL_PANEL = (
    "BROAD_EXTERNAL_PANEL_AND_FINISHING_LABEL_DOES_NOT_IDENTIFY_A_SINGLE_CANONICAL_TASK"
)
_REASON_TUNNEL_PORTAL_REINFORCEMENT = (
    "GENERIC_TUNNEL_PORTAL_REINFORCEMENT_DOES_NOT_IDENTIFY_A_SINGLE_REINFORCEMENT_METHOD_OR_CANONICAL_TASK"
)
_REASON_PAVING = (
    "GENERIC_SITE_PAVING_DOES_NOT_IDENTIFY_MATERIAL_OR_PAVING_METHOD"
)


_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 전기설비 설치
    ("4576ebe90839817c8de8830a6c63f3dbb7119654250c3fd01fa923e5de4acbd9", _REASON_ELECTRICAL, "MEDIUM"),
    # 조경시공 및 설치
    ("9944bac0c3bf19558150d7af8df4337ef7ca1fd70a8de36d6a2ceef34069a1ec", _REASON_LANDSCAPE, "MEDIUM"),
    # 미장 및 견출작업
    ("d0b7c0d78c7fc8780baf2e62e61ccef89664bf07bcf4660fe5aa3daae5013d9a", _REASON_PLASTERING, "MEDIUM"),
    # 지장물 보호
    ("b857feda90885f5b017cca1ef241af5c157b14fed5d12a0f44a90917afabf411", _REASON_UTILITY, "MEDIUM"),
    # 창호 및 유리 설치
    ("9259467b28edf13f9f10e9d40349ad7f7440b924483d90a653e922468074f9e7", _REASON_WINDOW_GLASS, "MEDIUM"),
    # 콘크리트타설
    ("58a88edbd40a2063b2a0d97f2f9def1608cdb984c4aa7c524798c4827e8bba01", _REASON_CONCRETE, "HIGH"),
    # 터널 특수보강
    ("5180e16bc943cf4cb929ecb22ab79517d5f5ea6c2252369f59baed472a862eb4", _REASON_SPECIAL_TUNNEL_REINFORCEMENT, "MEDIUM"),
    # 판넬 등 외부마감 시공
    ("4bf0123a90c029c35a5bde93b685fbd6bcd8f1471f368aac6fb70b9a71d40c15", _REASON_EXTERNAL_PANEL, "MEDIUM"),
    # 갱구부 보강
    ("04bff63c1a3c0280c553b368bb007a3fee147f22d97d12a2a10fcf7339c83533", _REASON_TUNNEL_PORTAL_REINFORCEMENT, "MEDIUM"),
    # 굴착
    ("f556d0f56dce9fa3be35cef61a4c35e92c55fddfe2b98d1c3ef3acf031e12cff", _REASON_EXCAVATION, "HIGH"),
    # 부대토목 구내포장
    ("b9d0626e802201461c34bed31d9783c8ef5f6e4e758b23697ef3a805e59ae385", _REASON_PAVING, "MEDIUM"),
)


# §8 CANONICAL_GAP (29 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "6d60bb73af5e251ee9158a7d1fab730596a9b0f6885929627da3597f2595e637",
    "0ef0cca646ab82cca3361898be97750f0e07113b1bb713494e0d0a5f0bd135ee",
    "51c4005f49a83754c140af8c1bcdafe9c30f40921588eb35fc8357ef53af9b80",
    "f44ef20ba60c50fc8f668716659a5c79d72b9d63fe9ce264a609e0bfd42a37ab",
    "9a5407126912ab35fede558b7b80f644fdba2f28831af2b65778df91711a3e97",
    "f5cd091f2219d9a448c406b4810d2fff29e5a4aa4cd28dea92249f82784643cc",
    "9aa1937e982069e12f1ea8b8c8643dc99235bbced09d39d90d2001897fec8512",
    "5f6322cc78d563c1f49749ac9c6b232256a34e6596a3f3ea231fea4edc087eda",
    "edef8ca64c894af0005a7370f4ea264ad546f119e013e77fd3675d79286218b1",
    "21da59a788236986040aeb0d1f2bbcbe659c16176d1b3e6926755d65d2b57f5a",
    "047619ff80cf6ead27a217a1a24d041c847fe300fd7f039410be4bda51340551",
    "a54cea37be223652d0b51adf73f013d47de45bb44be18a5a1e5b051925685f7b",
    "d0ac934fed48c82398393ddf591a1a97003b24f1e0a3cd3c4cf5354176823f02",
    "69c7e83db5740e15675c15004a1d289a5a9cdb6a42402d7d6cc8758e784b6e66",
    "2f5dc97466e7aeebbaaf36f18d5fe3c4f26fe759ac3369908d6887627f1dbec3",
    "f5a601b570fc55b35c1fc6682e02b06ad3773b51c4b4316fd48e8e85b1ddbac1",
    "c28f4dc9f5bd944da85c07bb15135f33ed269c5fcc8ad1889d96f18280d5bea6",
    "3cb3570f269d5a6876da31894f06b8d06fc46ddddc865f2b4b1e1ec855ff0902",
    "95eaf7620904d272d90ff9e24cfca53e92410ac1650e314bde67fd71375b6ac1",
    "7e8f8650a2bb7e0b43a97354dbff2094d6e890b9f9be81ac938572588925bb87",
    "67683500560a7293374bc933c79fc61f4b4beb2a40b3814e3ad7c809839c513b",
    "5d02b271651f09485127f3a62d1a4628ee6536347aa4b50a3fe6da5f6e2379f3",
    "d369b7dd2424277802594238d488ad34795ebbcf704ea9a7a5a038409353ac5c",
    "8e27b69bf4587ffe11511640ce21303a990e1c7fc1e3f86185932de447b6263f",
    "c1414acbd57a13414661dbf2abd16bda09687d1e1f8b973b649f4120584c73df",
    "001137af6fbea3e99ece7ceae0abc88461b8184a94c2c03dcfdaaec8da19dfe7",
    "e94a488cd34f0912217c894a058bcf3c7273949af4cbf4a25ed02dbe56970e6e",
    "bb07bebd5243cd358c6701022399ebff6d6dd0fe8ecb228ca5f8469c98ecb57d",
    "0e6b7ebcd9a6f26ec971d9a98ff4c048dc1db617543e2dc6ebe71947acec8483",
)


# §9 NO_MATCH (44 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "5dccea2ddf6d842eee1045b5713de253c079cf0a702e55ee0bf69b026d29ba3c",
    "30f687bf159d826438f2b964034be3aad5c723508f1000fa11cc9af3046f8b56",
    "f1b48276b68b5374fd00e34a7e12fcfe31398436da8d166751dda620ef3e73a7",
    "e0191f88cd072359bf9a3b9ac91f7623b364b48d31125938958d2594e9a9cabb",
    "31505f8fbc58bbeb40a3a3bc41148d3c5a99987512827c921715684b43c5ff5a",
    "ade5771a7ac3762ae522c5c9700d6f019c2da51ae04ab6f2a2ed50d04d148501",
    "bfe907294fa4356533e4dc80cab7d349bdae1c24b132ecacfb9d6de29b2045de",
    "9ad7abffcb9a8bd8fd761d1f85da905102865ce1198cf27f17a2a52131533922",
    "8e9dfdedfacc64cb936054140258838643ed1f5e92088f685dd725faafbfc4fb",
    "dedb03a690be9e27ce990afdb5e5f45ff058b7027cd31a3f00ded150b075884a",
    "def06a3c00ac617abd3363b1a56ee077b7c6db54b44f47ae50ea993beb48902c",
    "5039aa8e5cf917d7b4780ed32a19739439a266a64a7d52f3d9a10f99813a3f99",
    "5a0a4340adf9b597b86e800a459d2ca2ffdb5e4c4908193ccf7f21f947fdd924",
    "a224d701b2610fc61dab3dc3b7f34944f277cba0a98c0f2c893c4cf11d6f2019",
    "ae4bdebc88004019d46b944ad09e1e6d76456e1f69ec4aa32af418349541b3a9",
    "22e6be61b80b53f166426518a177c3c9e5975c9fd7ac12a7e8756a584cb91c15",
    "ed684b3b36397b3cbd8c15f1a1952ef395e17c7002ec3a7b4a71d7ead22afa85",
    "e584dd75cf76994f275fa712da80793edbede7ab190850db3fc5155421f8562c",
    "4567390fe8df67e946990de3bccf0174d2393106e85d54dc924cf228e962278d",
    "0db87c56a13b4c95d08235f72810ce15451ea4ca9f59099593f5eb2fe4a065ed",
    "71cfa013fd7253478c47cbf956c4a63a170621a8b7d71e9246e2903716323541",
    "5412857604b4b9d1b6c7dca1caf0ba625a39194d487d50e4e4b9f830916a834d",
    "954630dad6e76e39f0187bdeb50a8b705832882351a413182834e13cb23a98d6",
    "4935d0c38198cf4ed439b0cb93fe7b47003175f92fa830200ec46459a40a28c1",
    "b13fd42301976747bcb3ac8bacb31d261eb17f30523834b764be0aa58436aae8",
    "0dc5b59a1986705030c339281849ff268e013e33b492fbbae6e88abb236abf42",
    "ec2fc6853f9a262b48c9d52fa3cbca51e5dcdf7ff4849c540a5b0ac048858c48",
    "c76f78e917704740b2315ec8608fb4130c9626661564a0dd6c5271e77b526539",
    "d36bc1086f811de49ccc5296b26aa4c6d3952f61dc45fd3f358663dba59b4a1c",
    "72be10a34c65c2fee658c2fd1e491d8cf47afb26fc471e37fcdab07594febd32",
    "a46fb402f067d88e1bbc6081eeceaccb787605803cc272f0a7580841644beb5e",
    "33b35e1694bee0d3d3ac958bc5989696dd8fb87f4f43c0146131bdacd50118f6",
    "d96ac24fa254b608d00d2877b372171f9922a467354405853fe1cb8fbed480eb",
    "25557ea859cf6dd328fd65c0b17d625e8cb5f95d2c1885b13aa63cfa86c68108",
    "0601b84169785014ab3d3053231271981e2ca1d601eb316efe8c88035ba6f7e1",
    "b23f66ad9d34d0587b3c67f8e6cca1bc59e2e1f4e1af177cadff0e45ac1d7ae4",
    "294cf2330817a0b38428adee21b08546fdc219c36f771491c62ae99e5aedbfda",
    "a60d460a66e9754bd8cf2b39e815ea1bf3011b7d838b44da65097ec277e9dfb6",
    "9585ece24b489141145a98aff86e1953800a08ead414ab453148e55da2bd67ee",
    "ca80f21e2ef9d42f5ceab263ac2af41e3f44d2d54ec988bffcd19578ebdaa44f",
    "1c7427e20ef351c03570024684194c2bf8b11d50ef5f45bbb0efc4dbcf48770e",
    "08867936373da71e45b39bde6ceb5fe7c944f87804e06eddd071202589645361",
    "676b063d54d395d7dc3b8d9f6c5d89353f05091ec43eec6da55a98291932f673",
    "7817cb0506f995e477a387e39ca8165bc9c42882f0e0931bc5c9f91783cf8958",
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 10,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 6,
    ("AMBIGUOUS", "AMBIGUOUS"): 11,
    ("CANONICAL_GAP", ""): 29,
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
        "NARROWER_THAN": 10,
        "POSSIBLE_RELATED": 6,
        "AMBIGUOUS": 11,
        "CANONICAL_GAP": 29,
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


def _load_b06_evidence() -> list[dict]:
    rows = load_tsv(B06_EVIDENCE_PATH)
    if len(rows) != 100:
        raise SystemExit(f"B06_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b06_evidence_sha(rows) != FROZEN_B06_EVIDENCE_SHA:
        raise SystemExit("B06_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b06 = _load_b06_evidence()
    canonical_names = _canonical_name_lookup()

    b06_review_keys = {r["review_key"] for r in b06}
    if len(b06_review_keys) != 100:
        raise SystemExit("B06_REVIEW_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b06_review_keys - manifest_keys
    unexpected = manifest_keys - b06_review_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_REVIEW_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    out: list[dict] = []
    for row in b06:
        decision = GPT_DECISIONS[row["review_key"]]
        target_id = decision["gpt_target_canonical_id"]
        if target_id:
            name = canonical_names.get(target_id)
            if not name:
                raise SystemExit(
                    f"TARGET_CANONICAL_ID_UNKNOWN {target_id} for {row['review_key']}"
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
                "input_evidence_sha": FROZEN_B06_EVIDENCE_SHA,
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
    if len(targeted) != 16:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['review_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 84:
        raise SystemExit(f"BLANK_TARGET_ROW_DRIFT {len(blank)}")
    distinct = {r["gpt_target_canonical_id"] for r in targeted}
    if len(distinct) != 7:
        raise SystemExit(f"DISTINCT_TARGET_UUID_DRIFT {len(distinct)}")


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
title: WO-RISK-KOSHA-B06-REVIEW-001 GPT KOSHA B06 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B06 Semantic Review (Frozen)

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
B06 SEMANTIC EVIDENCE SHA         = {FROZEN_B06_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b06_gpt_review_freeze.py
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
targeted (canonical_id present)             = 16 / 100
blank-target                                = 84 / 100
distinct canonical targets                  = 7
```

Tunnel-specific note: 터널 발파 / 장약 / 천공 are NARROWER_THAN of 발파굴착.
터널 방수쉬트설치 is NARROWER_THAN of 터널방수. 라이닝거푸집 설치/해체 stay
attached to 현장타설콘크리트라이닝. 터널 숏크리트 is deliberately CANONICAL_GAP
— the current canonical 갱구숏크리트 covers only the portal, not the full tunnel.

## Frozen SHA

```text
RISK KOSHA B06 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review

```text
B01 reviewed          = 100
B02 reviewed          = 100
B03 reviewed          = 100
B04 reviewed          = 100
B05 reviewed          = 100
B06 reviewed          = 100
TOTAL KOSHA REVIEWED  = 600 / 620
REMAINING             = 20 (B07)
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / EVIDENCE_READY
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT TRANSCRIPTION VERIFY
THEN = KOSHA B07 SEMANTIC EVIDENCE
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
        "distinct_targets": len({r["gpt_target_canonical_id"] for r in rows_a if r["gpt_target_canonical_id"]}),
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
