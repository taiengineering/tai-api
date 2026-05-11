"""Phase 2.1 — rule_classify_subtype 패턴 UPDATE·INSERT 페이로드 (conjoining jamo).

명세: Cursor_Phase_2_1_Rule_Redesign_Spec.md §4
"""

from __future__ import annotations

# rule_name -> 새 pattern (text). match_strategy·pattern_position 유지.
RULE_PATTERN_UPDATES: dict[str, str] = {
    "OBLIGATION_HEADER_TAIL3": "어야/EC + 하/VX + ᆫ다/EF",
    "PROHIBITION_HEADER_NOT_ALLOW": "ᆯ/ETM + 수/NNB + 없/VA + 다/EF",
    "PROHIBITION_HEADER_NOT_DOEN": "하/XSV + 지/EC + 아니하/VX + ᆫ다/EF",
    "PROHIBITION_HEADER_KEUMJI": "금지/NNG + 하/XSV + ᆫ다/EF",
    "PENALTY_HEADER_CHEOHADA": "처하/VV + ᆫ다/EF",
    "PENALTY_HEADER_GWAHADA": "과하/VV + ᆫ다/EF",
    "PENALTY_HEADER_BUGWAHADA": "부과/NNG + 하/XSV + ᆫ다/EF",
    "AUTHORITY_HEADER_TAIL4": "ᆯ/ETM + 수/NNB + 있/VA + 다/EF",
    "EXEMPTION_HEADER_NOT_APPLY": "지/EC + 아니하/VX + ᆫ다/EF",
    "EXEMPTION_HEADER_EXCLUDE": "제외/NNG + 하/XSV + ᆫ다/EF",
    "DEFINITION_HEADER_MALHADA": "말/NNG + 하/XSV + ᆫ다/EF",
    "DEFINITION_HEADER_RAHADA": "라/EC + 하/VV + ᆫ다/EF",
    "DELEGATION_ACTIVE_TAIL3": "으로/JKB + 정하/VV + ᆫ다/EF",
    "AS_본다_TAIL3": "으로/JKB + 보/VV + ᆫ다/EF",
    "OBLIGATION_DETAIL_ITEM_GEOT": "하/XSV + ᆯ/ETM + 것/NNB",
    "PENALTY_VIOLATOR_ITEM_JA": "하/XSV + ᆫ/ETM + 자/NNB",
    "WEAK_한다단순": "하/VV + ᆫ다/EF",
    "WEAK_있다단순": "있/VA + 다/EF",
}

# 신규 룰 (다양성). tuple: rule_name, sub_type, pattern, pattern_position, priority, description
RULE_INSERTS: list[tuple[str, str, str, str, int, str]] = [
    (
        "PROHIBITION_HEADER_MAG_DOEI",
        "PROHIBITION_HEADER",
        "아니/MAG + 되/VV + ᆫ다/EF",
        "TAIL_3",
        19,
        "Phase2.1: MAG+되 종결 (sample 빈도)",
    ),
    (
        "PENALTY_VIOLATOR_VV_HANJA",
        "PENALTY_VIOLATOR_ITEM",
        "하/VV + ᆫ/ETM + 자/NNB",
        "TAIL_3",
        111,
        "Phase2.1: ~한 자 (VV)",
    ),
    (
        "PENALTY_VIOLATOR_ANIHA_JA",
        "PENALTY_VIOLATOR_ITEM",
        "아니하/VX + ᆫ/ETM + 자/NNB",
        "TAIL_3",
        112,
        "Phase2.1: ~아니한 자",
    ),
    # 잔여 UNCLASSIFIED 상위 tail (15k 샘플 빈도 기준, §3.4 ≥ 다수 건)
    (
        "AS_본다_WA_GATDA",
        "AS_본다",
        "와/JKB + 같/VA + 다/EF",
        "TAIL_3",
        81,
        "Phase2.1 보강: ~와 같다",
    ),
    (
        "AS_본다_GWA_GATDA",
        "AS_본다",
        "과/JKB + 같/VA + 다/EF",
        "TAIL_3",
        82,
        "Phase2.1 보강: ~과 같다",
    ),
    (
        "AS_본다_TTOHAN_GATDA",
        "AS_본다",
        "또한/MAG + 같/VA + 다/EF",
        "TAIL_3",
        83,
        "Phase2.1 보강: 또한 같다",
    ),
    (
        "DELEGATION_ETRAHADA",
        "DELEGATION_ACTIVE",
        "에/JKB + 따르/VV + ᆫ다/EF",
        "TAIL_3",
        71,
        "Phase2.1 보강: 에 따라 한다",
    ),
    (
        "DEFINITION_GOSI_HADA",
        "DEFINITION_HEADER",
        "고시/NNG + 하/XSV + ᆫ다/EF",
        "TAIL_3",
        62,
        "Phase2.1 보강: 고시한다",
    ),
    (
        "OBLIGATION_DETAIL_GWAN_SAHANG",
        "OBLIGATION_DETAIL_ITEM",
        "관하/VV + ᆫ/ETM + 사항/NNG",
        "TAIL_3",
        101,
        "Phase2.1 보강: 관한 사항",
    ),
    (
        "OBLIGATION_DETAIL_HVV_GEOT",
        "OBLIGATION_DETAIL_ITEM",
        "하/VV + ᆯ/ETM + 것/NNB",
        "TAIL_3",
        103,
        "Phase2.1 보강: 할 것 (VV)",
    ),
    (
        "WEAK_JUNYONG_HADA",
        "WEAK_한다단순",
        "준용/NNG + 하/XSV + ᆫ다/EF",
        "TAIL_3",
        199,
        "Phase2.1 보강: 준용한다 (WEAK 전)",
    ),
]
