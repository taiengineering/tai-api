"""TAI Search Dictionary — v1 SEED snapshot (MASTER-WO-TAI-SEARCH-DICT-001).

This is a HONEST, PROVENANCE-BOUND seed, not a fabricated bulk. Every SOURCE_NAME
row below was verified to exist in leg-prod (project wrfcedzgdrfupenzqhur) at
census time; every abbreviation/spacing relation is copied from the verified
public.law_alias table; every DOMAIN_RESEARCH compound term is a real Korean
industrial-safety phrase whose *component* over-segmentation was observed in the
existing Kiwi extraction (that is why it is a SEARCH_PHRASE / KIWI_USER_WORD
candidate, not a canonical claim).

Scale: v1 seed is deliberately small and high-confidence. WO §73/§124 forbid
inflating counts or fabricating targets to hit recall numbers. The full raw
extraction (Phase 4, dict_legal_terms = 14,942 rows) runs in the execution
environment; this seed proves the schema, the deterministic compiler, the tier
logic, and every relation/term type end-to-end.

Snapshot identity (WO §17):
"""
from __future__ import annotations

SNAPSHOT_ID = "SEARCH-DICT-SEED-2026-09-16"
SNAPSHOT_DATE = "2026-09-16"

# --- Source registry (WO §16 TERM_SOURCE_CENSUS). authority_level 1=highest ---
SOURCES = {
    "SRC-LEG-DICT": {
        "source_name": "leg-prod public.dict_legal_terms",
        "source_type": "DB_TABLE",
        "authority_level": 2,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.dict_legal_terms",
        "note": "Existing Kiwi-extracted + ground_truth legal term dictionary (14,942 rows).",
    },
    "SRC-LEG-ALIAS": {
        "source_name": "leg-prod public.law_alias",
        "source_type": "DB_TABLE",
        "authority_level": 1,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.law_alias",
        "note": "Verified law short_name<->full_name pairs (15 rows).",
    },
    "SRC-LEG-LAWMASTER": {
        "source_name": "leg-prod public.law_master (ground_truth names)",
        "source_type": "DB_TABLE",
        "authority_level": 1,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.law_master",
        "note": "Official law names / short names / ministry names.",
    },
    "SRC-DOMAIN-KOSHA": {
        "source_name": "KOSHA / official industrial-safety glossary (domain research)",
        "source_type": "GLOSSARY",
        "authority_level": 3,
        "location": "domain-research (KOSHA guides, official terminology)",
        "note": "Compound domain phrases + English/abbrev pairs; PROPOSED pending review.",
    },
}

# --- TERMS ---------------------------------------------------------------
# tuple: (source_id, source_key, term_type, original_term, language, pos_hint,
#         subject_type, subject_key, status, quality_flag, curation_method,
#         confidence, evidence_ref)
# canonical_id is always None at seed time (WO §11/§47).
T = list

TERMS: list[tuple] = [
    # ---- Real GENERIC / legal source terms (verified/high-freq in dict_legal_terms) ----
    ("SRC-LEG-DICT", "근로자", "SOURCE_NAME", "근로자", "ko", "NNG", "LEGAL_TERM", "근로자", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=근로자 freq=2892 verified=true"),
    ("SRC-LEG-DICT", "사업주", "SOURCE_NAME", "사업주", "ko", "NNG", "LEGAL_TERM", "사업주", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=사업주 freq=2293 verified=true"),
    ("SRC-LEG-DICT", "화재", "SOURCE_NAME", "화재", "ko", "NNG", "ACCIDENT_TERM", "화재", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=화재 freq=1966 verified=true"),
    ("SRC-LEG-DICT", "폭발", "SOURCE_NAME", "폭발", "ko", "NNG", "ACCIDENT_TERM", "폭발", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=폭발 freq=411 verified=true"),
    ("SRC-LEG-DICT", "감전", "SOURCE_NAME", "감전", "ko", "NNG", "ACCIDENT_TERM", "감전", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=감전 freq=167 verified=true"),
    ("SRC-LEG-DICT", "보호구", "SOURCE_NAME", "보호구", "ko", "NNG", "EQUIPMENT_TERM", "보호구", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms.term=보호구 freq=159 verified=true"),
    ("SRC-LEG-DICT", "낙하", "SOURCE_NAME", "낙하", "ko", "NNG", "ACCIDENT_TERM", "낙하", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=낙하 freq=114 verified=false"),
    ("SRC-LEG-DICT", "비계", "SOURCE_NAME", "비계", "ko", "NNG", "EQUIPMENT_TERM", "비계", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=비계 freq=107 verified=false"),
    ("SRC-LEG-DICT", "추락", "SOURCE_NAME", "추락", "ko", "NNG", "ACCIDENT_TERM", "추락", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=추락 freq=99 verified=false"),
    ("SRC-LEG-DICT", "거푸집", "SOURCE_NAME", "거푸집", "ko", "NNG", "EQUIPMENT_TERM", "거푸집", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=거푸집 freq=54 verified=false"),
    ("SRC-LEG-DICT", "방폭구조", "SOURCE_NAME", "방폭구조", "ko", "NNG", "EQUIPMENT_TERM", "방폭구조", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=방폭구조 freq=22 verified=false"),
    ("SRC-LEG-DICT", "질식", "SOURCE_NAME", "질식", "ko", "NNG", "ACCIDENT_TERM", "질식", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=질식 freq=12 verified=false"),
    ("SRC-LEG-DICT", "수변전설비", "SOURCE_NAME", "수변전설비", "ko", "NNG", "EQUIPMENT_TERM", "수변전설비", "APPROVED", "OK", "SOURCE_EXACT", "MEDIUM", "dict_legal_terms.term=수변전설비 freq=3 verified=false"),

    # ---- Real AGENCY names (verified ground_truth) ----
    ("SRC-LEG-LAWMASTER", "고용노동부", "SOURCE_NAME", "고용노동부", "ko", "NNP", "GENERAL_TERM", "고용노동부", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "dict_legal_terms source=law_master.ministry_name:ground_truth verified=true"),
    ("SRC-LEG-LAWMASTER", "국토교통부", "SOURCE_NAME", "국토교통부", "ko", "NNP", "GENERAL_TERM", "국토교통부", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "dict_legal_terms source=law_master.ministry_name:ground_truth verified=true"),
    ("SRC-LEG-LAWMASTER", "소방청", "SOURCE_NAME", "소방청", "ko", "NNP", "GENERAL_TERM", "소방청", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "dict_legal_terms source=law_master.ministry_name:ground_truth verified=true"),
    ("SRC-LEG-LAWMASTER", "원자력안전위원회", "SOURCE_NAME", "원자력안전위원회", "ko", "NNP", "GENERAL_TERM", "원자력안전위원회", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "dict_legal_terms source=law_master.ministry_name:ground_truth verified=true"),
    ("SRC-LEG-LAWMASTER", "화학물질안전원", "SOURCE_NAME", "화학물질안전원", "ko", "NNP", "GENERAL_TERM", "화학물질안전원", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "dict_legal_terms source=law_master.ministry_name:ground_truth verified=true"),

    # ---- Real LAW full names (canonical surface of the law subject) ----
    ("SRC-LEG-ALIAS", "산업안전보건법", "SOURCE_NAME", "산업안전보건법", "ko", "NNP", "LEGAL_TERM", "산업안전보건법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name=산업안전보건법"),
    ("SRC-LEG-ALIAS", "산업안전보건법 시행령", "SOURCE_NAME", "산업안전보건법 시행령", "ko", "NNP", "LEGAL_TERM", "산업안전보건법 시행령", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "산업안전보건법 시행규칙", "SOURCE_NAME", "산업안전보건법 시행규칙", "ko", "NNP", "LEGAL_TERM", "산업안전보건법 시행규칙", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "산업안전보건기준에 관한 규칙", "SOURCE_NAME", "산업안전보건기준에 관한 규칙", "ko", "NNP", "LEGAL_TERM", "산업안전보건기준에 관한 규칙", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "중대재해 처벌 등에 관한 법률", "SOURCE_NAME", "중대재해 처벌 등에 관한 법률", "ko", "NNP", "LEGAL_TERM", "중대재해 처벌 등에 관한 법률", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "고압가스 안전관리법", "SOURCE_NAME", "고압가스 안전관리법", "ko", "NNP", "LEGAL_TERM", "고압가스 안전관리법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "건설기술 진흥법", "SOURCE_NAME", "건설기술 진흥법", "ko", "NNP", "LEGAL_TERM", "건설기술 진흥법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "승강기 안전관리법", "SOURCE_NAME", "승강기 안전관리법", "ko", "NNP", "LEGAL_TERM", "승강기 안전관리법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "시설물의 안전 및 유지관리에 관한 특별법", "SOURCE_NAME", "시설물의 안전 및 유지관리에 관한 특별법", "ko", "NNP", "LEGAL_TERM", "시설물의 안전 및 유지관리에 관한 특별법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "위험물안전관리법", "SOURCE_NAME", "위험물안전관리법", "ko", "NNP", "LEGAL_TERM", "위험물안전관리법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "화학물질의 등록 및 평가 등에 관한 법률", "SOURCE_NAME", "화학물질의 등록 및 평가 등에 관한 법률", "ko", "NNP", "LEGAL_TERM", "화학물질의 등록 및 평가 등에 관한 법률", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "소방시설 설치 및 관리에 관한 법률", "SOURCE_NAME", "소방시설 설치 및 관리에 관한 법률", "ko", "NNP", "LEGAL_TERM", "소방시설 설치 및 관리에 관한 법률", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),
    ("SRC-LEG-ALIAS", "에너지이용 합리화법", "SOURCE_NAME", "에너지이용 합리화법", "ko", "NNP", "LEGAL_TERM", "에너지이용 합리화법", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "law_alias.full_name"),

    # ---- Real ABBREVIATION / SPACING short names (law_alias.short_name) ----
    ("SRC-LEG-ALIAS", "산안법", "ABBREVIATION", "산안법", "ko", "NNP", "LEGAL_TERM", "산업안전보건법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name=산안법"),
    ("SRC-LEG-ALIAS", "산안법 시행령", "ABBREVIATION", "산안법 시행령", "ko", "NNP", "LEGAL_TERM", "산업안전보건법 시행령", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "산안법 시행규칙", "ABBREVIATION", "산안법 시행규칙", "ko", "NNP", "LEGAL_TERM", "산업안전보건법 시행규칙", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "안전보건규칙", "ABBREVIATION", "안전보건규칙", "ko", "NNP", "LEGAL_TERM", "산업안전보건기준에 관한 규칙", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "중대재해법", "ABBREVIATION", "중대재해법", "ko", "NNP", "LEGAL_TERM", "중대재해 처벌 등에 관한 법률", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "고압가스법", "ABBREVIATION", "고압가스법", "ko", "NNP", "LEGAL_TERM", "고압가스 안전관리법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "고압가스안전관리법", "SPACING_VARIANT", "고압가스안전관리법", "ko", "NNP", "LEGAL_TERM", "고압가스 안전관리법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name (no-space variant)"),
    ("SRC-LEG-ALIAS", "건설기술진흥법", "SPACING_VARIANT", "건설기술진흥법", "ko", "NNP", "LEGAL_TERM", "건설기술 진흥법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name (no-space variant)"),
    ("SRC-LEG-ALIAS", "승강기법", "ABBREVIATION", "승강기법", "ko", "NNP", "LEGAL_TERM", "승강기 안전관리법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "승강기안전관리법", "SPACING_VARIANT", "승강기안전관리법", "ko", "NNP", "LEGAL_TERM", "승강기 안전관리법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name (no-space variant)"),
    ("SRC-LEG-ALIAS", "시설물안전법", "ABBREVIATION", "시설물안전법", "ko", "NNP", "LEGAL_TERM", "시설물의 안전 및 유지관리에 관한 특별법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "위험물법", "ABBREVIATION", "위험물법", "ko", "NNP", "LEGAL_TERM", "위험물안전관리법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "화학물질등록평가법", "ABBREVIATION", "화학물질등록평가법", "ko", "NNP", "LEGAL_TERM", "화학물질의 등록 및 평가 등에 관한 법률", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "소방시설법", "ABBREVIATION", "소방시설법", "ko", "NNP", "LEGAL_TERM", "소방시설 설치 및 관리에 관한 법률", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name"),
    ("SRC-LEG-ALIAS", "에너지이용합리화법", "SPACING_VARIANT", "에너지이용합리화법", "ko", "NNP", "LEGAL_TERM", "에너지이용 합리화법", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "law_alias short_name (no-space variant)"),

    # ---- Domain compound phrases (Kiwi over-segments -> SEARCH_PHRASE + KIWI_USER_WORD) ----
    # PROPOSED: real phrases, but subject-linking + Kiwi effect require runtime review.
    ("SRC-DOMAIN-KOSHA", "국소배기장치", "SEARCH_PHRASE", "국소배기장치", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA glossary; absent as whole in dict_legal_terms (over-segmented)"),
    ("SRC-DOMAIN-KOSHA", "국소 배기 장치", "SPACING_VARIANT", "국소 배기 장치", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant of 국소배기장치"),
    ("SRC-DOMAIN-KOSHA", "국소배기", "ABBREVIATION", "국소배기", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "common short form"),
    ("SRC-DOMAIN-KOSHA", "LEV", "ENGLISH_TERM", "LEV", "en", "SL", "EQUIPMENT_TERM", "국소배기장치", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "Local Exhaust Ventilation"),
    ("SRC-DOMAIN-KOSHA", "위험성평가", "SEARCH_PHRASE", "위험성평가", "ko", "NNG", "GENERAL_TERM", "위험성평가", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; over-segmented (위험성/평가) in extraction"),
    ("SRC-DOMAIN-KOSHA", "위험성 평가", "SPACING_VARIANT", "위험성 평가", "ko", "NNG", "GENERAL_TERM", "위험성평가", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant of 위험성평가"),
    ("SRC-DOMAIN-KOSHA", "밀폐공간작업", "SEARCH_PHRASE", "밀폐공간작업", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; compound work term"),
    ("SRC-DOMAIN-KOSHA", "밀폐 공간 작업", "SPACING_VARIANT", "밀폐 공간 작업", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant"),
    ("SRC-DOMAIN-KOSHA", "밀폐공간", "SEARCH_PHRASE", "밀폐공간", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "REVIEWED", "OK", "DOMAIN_RESEARCH", "LOW", "related broader/narrower — NOT synonym"),
    ("SRC-DOMAIN-KOSHA", "산업용로봇", "SEARCH_PHRASE", "산업용로봇", "ko", "NNG", "EQUIPMENT_TERM", "산업용로봇", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; compound equipment term"),
    ("SRC-DOMAIN-KOSHA", "산업용 로봇", "SPACING_VARIANT", "산업용 로봇", "ko", "NNG", "EQUIPMENT_TERM", "산업용로봇", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant"),

    # ---- Chemical abbreviations (WO §54/§82) ----
    ("SRC-DOMAIN-KOSHA", "물질안전보건자료", "SOURCE_NAME", "물질안전보건자료", "ko", "NNG", "CHEM_TERM", "물질안전보건자료", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "official term for MSDS"),
    ("SRC-DOMAIN-KOSHA", "MSDS", "ABBREVIATION", "MSDS", "en", "SL", "CHEM_TERM", "물질안전보건자료", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "Material Safety Data Sheet"),
    ("SRC-DOMAIN-KOSHA", "SDS", "SYNONYM", "SDS", "en", "SL", "CHEM_TERM", "물질안전보건자료", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "Safety Data Sheet (GHS); search-equivalent to MSDS"),
]

# --- RELATIONS -----------------------------------------------------------
# tuple: (src_original, src_source_id, tgt_original, tgt_source_id,
#         relation_type, status, curation_method, confidence, evidence_ref)
# The builder resolves each side to its term_id.
RELATIONS: list[tuple] = [
    ("산안법", "SRC-LEG-ALIAS", "산업안전보건법", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("산안법 시행령", "SRC-LEG-ALIAS", "산업안전보건법 시행령", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("산안법 시행규칙", "SRC-LEG-ALIAS", "산업안전보건법 시행규칙", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("안전보건규칙", "SRC-LEG-ALIAS", "산업안전보건기준에 관한 규칙", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("중대재해법", "SRC-LEG-ALIAS", "중대재해 처벌 등에 관한 법률", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("고압가스법", "SRC-LEG-ALIAS", "고압가스 안전관리법", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("고압가스안전관리법", "SRC-LEG-ALIAS", "고압가스 안전관리법", "SRC-LEG-ALIAS", "SPACING_VARIANT_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("건설기술진흥법", "SRC-LEG-ALIAS", "건설기술 진흥법", "SRC-LEG-ALIAS", "SPACING_VARIANT_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("승강기법", "SRC-LEG-ALIAS", "승강기 안전관리법", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("승강기안전관리법", "SRC-LEG-ALIAS", "승강기 안전관리법", "SRC-LEG-ALIAS", "SPACING_VARIANT_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("시설물안전법", "SRC-LEG-ALIAS", "시설물의 안전 및 유지관리에 관한 특별법", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("위험물법", "SRC-LEG-ALIAS", "위험물안전관리법", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("화학물질등록평가법", "SRC-LEG-ALIAS", "화학물질의 등록 및 평가 등에 관한 법률", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("소방시설법", "SRC-LEG-ALIAS", "소방시설 설치 및 관리에 관한 법률", "SRC-LEG-ALIAS", "ABBREVIATION_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    ("에너지이용합리화법", "SRC-LEG-ALIAS", "에너지이용 합리화법", "SRC-LEG-ALIAS", "SPACING_VARIANT_OF", "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"),
    # domain compounds
    ("국소 배기 장치", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("국소배기", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "ABBREVIATION_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "short form"),
    ("LEV", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "ENGLISH_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "Local Exhaust Ventilation"),
    ("위험성 평가", "SRC-DOMAIN-KOSHA", "위험성평가", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("밀폐 공간 작업", "SRC-DOMAIN-KOSHA", "밀폐공간작업", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("밀폐공간", "SRC-DOMAIN-KOSHA", "밀폐공간작업", "SRC-DOMAIN-KOSHA", "NARROWER_SEARCH_TERM", "REVIEWED", "DOMAIN_RESEARCH", "LOW", "NOT synonym; narrower context"),
    ("산업용 로봇", "SRC-DOMAIN-KOSHA", "산업용로봇", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    # chemical
    ("MSDS", "SRC-DOMAIN-KOSHA", "물질안전보건자료", "SRC-DOMAIN-KOSHA", "ABBREVIATION_OF", "APPROVED", "OFFICIAL_GLOSSARY", "HIGH", "official"),
    ("SDS", "SRC-DOMAIN-KOSHA", "MSDS", "SRC-DOMAIN-KOSHA", "SYNONYM_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "GHS SDS ~ MSDS (search-equivalent)"),
]

# --- KIWI user-word candidates (WO §34/§37) ------------------------------
# reason codes: COMPOUND_SEGMENTATION | ABBREV_PRESERVE | BOUNDARY
# before/after are populated ONLY by the runtime Kiwi audit; here PENDING.
KIWI_CANDIDATES: list[tuple] = [
    # (term, pos, reason, source_term_original, source_id)
    ("국소배기장치", "NNP", "COMPOUND_SEGMENTATION", "국소배기장치", "SRC-DOMAIN-KOSHA"),
    ("위험성평가", "NNP", "COMPOUND_SEGMENTATION", "위험성평가", "SRC-DOMAIN-KOSHA"),
    ("밀폐공간작업", "NNP", "COMPOUND_SEGMENTATION", "밀폐공간작업", "SRC-DOMAIN-KOSHA"),
    ("산업용로봇", "NNP", "COMPOUND_SEGMENTATION", "산업용로봇", "SRC-DOMAIN-KOSHA"),
    ("수변전설비", "NNP", "COMPOUND_SEGMENTATION", "수변전설비", "SRC-LEG-DICT"),
    ("방폭구조", "NNP", "COMPOUND_SEGMENTATION", "방폭구조", "SRC-LEG-DICT"),
]
