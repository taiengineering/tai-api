"""TAI Search Dictionary — v2 snapshot built from REAL leg-prod extraction.

MASTER-WO-TAI-SEARCH-DICT-001 Phase 4 (full extraction). Unlike the v1 seed,
this snapshot is materialised from the ACTUAL leg-prod (wrfcedzgdrfupenzqhur)
corpus, pulled read-only and byte-verified against server-side SHA-256:

  extract/GROUND_TRUTH_464.tsv  — 464 verified ground-truth terms
      (26 AGENCY_NAME + 423 LAW_NAME/law_name_short + 15 legal-instrument
       TECH_TERM). server sha256 = 9cf9d73cb35a8884164dd999ff8aa10b59e0098c96
                                   e3a940205f801825fea178
  extract/LAW_ALIAS_15.tsv      — 15 verified short<->full law_alias pairs.
      server sha256 = e3006ed67d4b93f435419ce47288aced44bcb3bdb97e97e3308bc
                      31780cbabbe

Both files are reproducible-input snapshots (WO §17 snapshot identity): the
build is deterministic given these fixed, checksum-pinned inputs. The full
14,942-row corpus (incl. 1,250 verified high-frequency GENERIC and 13,213
unverified PROPOSED kiwi-extractions) is loaded at production scale by
tools/search_dict/extract_legprod.py against the live DB; this snapshot pins
the verified, APPROVED-eligible ground-truth backbone plus a curated
equipment/chemical overlay so the deterministic compiler, tiers and gates run
end-to-end offline.

Honesty (WO §71/§73/§124): every ground-truth term is verified=true in
leg-prod; no counts inflated; overlay terms are real KOSHA/official terms with
conservative status (PROPOSED/REVIEWED where linkage needs runtime review).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import normalize as N  # noqa: E402

SNAPSHOT_ID = "SEARCH-DICT-LEGPROD-2026-09-16"
SNAPSHOT_DATE = "2026-09-16"

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTRACT = os.path.join(_HERE, "extract")

# Pinned server-side checksums of the extract snapshots (WO §17).
EXTRACT_CHECKSUMS = {
    "GROUND_TRUTH_464.tsv":
        "9cf9d73cb35a8884164dd999ff8aa10b59e0098c96e3a940205f801825fea178",
    "LAW_ALIAS_15.tsv":
        "e3006ed67d4b93f435419ce47288aced44bcb3bdb97e97e3308bc31780cbabbe",
}

SOURCES = {
    "SRC-LEG-LAWMASTER": {
        "source_name": "leg-prod public.law_master (ground_truth names)",
        "source_type": "DB_TABLE", "authority_level": 1,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.dict_legal_terms(law_master.*:ground_truth)",
        "note": "Official law names / short names / ministry names; verified=true.",
    },
    "SRC-MANUAL-WHITELIST": {
        "source_name": "leg-prod dict_legal_terms manual:whitelist",
        "source_type": "DB_TABLE", "authority_level": 2,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.dict_legal_terms(manual:whitelist)",
        "note": "Legal-instrument generic terms (법/규칙/시행령 …); verified=true.",
    },
    "SRC-LEG-ALIAS": {
        "source_name": "leg-prod public.law_alias",
        "source_type": "DB_TABLE", "authority_level": 1,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.law_alias",
        "note": "Verified short<->full law name pairs (15 rows).",
    },
    "SRC-LEG-DICT": {
        "source_name": "leg-prod public.dict_legal_terms (verified GENERIC)",
        "source_type": "DB_TABLE", "authority_level": 2,
        "location": "supabase:wrfcedzgdrfupenzqhur/public.dict_legal_terms",
        "note": "High-frequency verified generic legal terms.",
    },
    "SRC-DOMAIN-KOSHA": {
        "source_name": "KOSHA / official industrial-safety glossary",
        "source_type": "GLOSSARY", "authority_level": 3,
        "location": "domain-research (KOSHA guides, official terminology)",
        "note": "Compound equipment/work phrases + English/abbrev; conservative status.",
    },
}

# tuple order (matches build_dictionary consumer):
# (source_id, source_key, term_type, original_term, language, pos_hint,
#  subject_type, subject_key, status, quality_flag, curation_method,
#  confidence, evidence_ref)


def _read_tsv(name):
    path = os.path.join(_EXTRACT, name)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line:
                yield line.split("\t")


def _alias_shortnames():
    return {short for short, _full in _read_tsv("LAW_ALIAS_15.tsv")}


def _ground_truth_terms():
    rows = []
    alias_shorts = _alias_shortnames()
    for term, pos_tag, ttype, source in _read_tsv("GROUND_TRUTH_464.tsv"):
        # A short-name that is a known law_alias resolves to the FULL law via the
        # alias term (subject=full); do not also emit it as a self-subject term
        # (removes duplicate surface + EXACT tie ambiguity). WO §42/§68.
        if term in alias_shorts:
            continue
        if ttype == "AGENCY_NAME":
            sid, subt, cur = "SRC-LEG-LAWMASTER", "GENERAL_TERM", "OFFICIAL_GLOSSARY"
        elif ttype == "LAW_NAME":
            sid, subt, cur = "SRC-LEG-LAWMASTER", "LEGAL_TERM", "OFFICIAL_GLOSSARY"
        else:  # TECH_TERM (legal-instrument generic)
            sid, subt, cur = "SRC-MANUAL-WHITELIST", "GENERAL_TERM", "SOURCE_EXACT"
        rows.append((sid, term, "SOURCE_NAME", term, "ko", pos_tag, subt, term,
                     "APPROVED", "OK", cur, "HIGH",
                     f"{source} verified=true"))
    return rows


def _alias_terms_and_relations():
    terms, rels = [], []
    for short, full in _read_tsv("LAW_ALIAS_15.tsv"):
        spacing = N.compact(short) == N.compact(full)
        term_type = "SPACING_VARIANT" if spacing else "ABBREVIATION"
        rel_type = "SPACING_VARIANT_OF" if spacing else "ABBREVIATION_OF"
        terms.append(("SRC-LEG-ALIAS", short, term_type, short, "ko", "NNP",
                      "LEGAL_TERM", full, "APPROVED", "OK", "SOURCE_EXACT",
                      "HIGH", f"law_alias short_name={short}"))
        rels.append((short, "SRC-LEG-ALIAS", full, "SRC-LEG-LAWMASTER",
                     rel_type, "APPROVED", "SOURCE_EXACT", "HIGH", "law_alias"))
    return terms, rels


# --- Curated overlay: real equipment/chemical/high-freq domain terms --------
# status conservative where subject-linkage or Kiwi effect needs runtime review.
_OVERLAY_TERMS = [
    # high-frequency verified GENERIC (freq from dict_legal_terms verified=true)
    ("SRC-LEG-DICT", "근로자", "SOURCE_NAME", "근로자", "ko", "NNG", "GENERAL_TERM", "근로자", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=2892"),
    ("SRC-LEG-DICT", "사업주", "SOURCE_NAME", "사업주", "ko", "NNG", "GENERAL_TERM", "사업주", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=2293"),
    ("SRC-LEG-DICT", "화재", "SOURCE_NAME", "화재", "ko", "NNG", "ACCIDENT_TERM", "화재", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=1966"),
    ("SRC-LEG-DICT", "폭발", "SOURCE_NAME", "폭발", "ko", "NNG", "ACCIDENT_TERM", "폭발", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=411"),
    ("SRC-LEG-DICT", "감전", "SOURCE_NAME", "감전", "ko", "NNG", "ACCIDENT_TERM", "감전", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=167"),
    ("SRC-LEG-DICT", "보호구", "SOURCE_NAME", "보호구", "ko", "NNG", "EQUIPMENT_TERM", "보호구", "APPROVED", "OK", "SOURCE_EXACT", "HIGH", "dict_legal_terms verified=true freq=159"),
    # equipment / work compound phrases (Kiwi over-segments -> SEARCH_PHRASE)
    ("SRC-DOMAIN-KOSHA", "국소배기장치", "SEARCH_PHRASE", "국소배기장치", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA glossary; over-segmented in extraction"),
    ("SRC-DOMAIN-KOSHA", "국소 배기 장치", "SPACING_VARIANT", "국소 배기 장치", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant of 국소배기장치"),
    ("SRC-DOMAIN-KOSHA", "국소배기", "ABBREVIATION", "국소배기", "ko", "NNG", "EQUIPMENT_TERM", "국소배기장치", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "common short form"),
    ("SRC-DOMAIN-KOSHA", "LEV", "ENGLISH_TERM", "LEV", "en", "SL", "EQUIPMENT_TERM", "국소배기장치", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "Local Exhaust Ventilation"),
    ("SRC-DOMAIN-KOSHA", "위험성평가", "SEARCH_PHRASE", "위험성평가", "ko", "NNG", "GENERAL_TERM", "위험성평가", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; over-segmented (위험성/평가)"),
    ("SRC-DOMAIN-KOSHA", "위험성 평가", "SPACING_VARIANT", "위험성 평가", "ko", "NNG", "GENERAL_TERM", "위험성평가", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant of 위험성평가"),
    ("SRC-DOMAIN-KOSHA", "밀폐공간작업", "SEARCH_PHRASE", "밀폐공간작업", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; compound work term"),
    ("SRC-DOMAIN-KOSHA", "밀폐 공간 작업", "SPACING_VARIANT", "밀폐 공간 작업", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant"),
    ("SRC-DOMAIN-KOSHA", "밀폐공간", "SEARCH_PHRASE", "밀폐공간", "ko", "NNG", "GENERAL_TERM", "밀폐공간작업", "REVIEWED", "OK", "DOMAIN_RESEARCH", "LOW", "narrower context — NOT synonym"),
    ("SRC-DOMAIN-KOSHA", "산업용로봇", "SEARCH_PHRASE", "산업용로봇", "ko", "NNG", "EQUIPMENT_TERM", "산업용로봇", "PROPOSED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "KOSHA; compound equipment term"),
    ("SRC-DOMAIN-KOSHA", "산업용 로봇", "SPACING_VARIANT", "산업용 로봇", "ko", "NNG", "EQUIPMENT_TERM", "산업용로봇", "APPROVED", "OK", "RULE_DERIVED", "HIGH", "spacing variant"),
    # chemical
    ("SRC-DOMAIN-KOSHA", "물질안전보건자료", "SOURCE_NAME", "물질안전보건자료", "ko", "NNG", "CHEM_TERM", "물질안전보건자료", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "official term for MSDS"),
    ("SRC-DOMAIN-KOSHA", "MSDS", "ABBREVIATION", "MSDS", "en", "SL", "CHEM_TERM", "물질안전보건자료", "APPROVED", "OK", "OFFICIAL_GLOSSARY", "HIGH", "Material Safety Data Sheet"),
    ("SRC-DOMAIN-KOSHA", "SDS", "SYNONYM", "SDS", "en", "SL", "CHEM_TERM", "물질안전보건자료", "REVIEWED", "OK", "DOMAIN_RESEARCH", "MEDIUM", "Safety Data Sheet (GHS)"),
]

_OVERLAY_RELATIONS = [
    ("국소 배기 장치", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("국소배기", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "ABBREVIATION_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "short form"),
    ("LEV", "SRC-DOMAIN-KOSHA", "국소배기장치", "SRC-DOMAIN-KOSHA", "ENGLISH_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "Local Exhaust Ventilation"),
    ("위험성 평가", "SRC-DOMAIN-KOSHA", "위험성평가", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("밀폐 공간 작업", "SRC-DOMAIN-KOSHA", "밀폐공간작업", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("밀폐공간", "SRC-DOMAIN-KOSHA", "밀폐공간작업", "SRC-DOMAIN-KOSHA", "NARROWER_SEARCH_TERM", "REVIEWED", "DOMAIN_RESEARCH", "LOW", "narrower"),
    ("산업용 로봇", "SRC-DOMAIN-KOSHA", "산업용로봇", "SRC-DOMAIN-KOSHA", "SPACING_VARIANT_OF", "APPROVED", "RULE_DERIVED", "HIGH", "spacing"),
    ("MSDS", "SRC-DOMAIN-KOSHA", "물질안전보건자료", "SRC-DOMAIN-KOSHA", "ABBREVIATION_OF", "APPROVED", "OFFICIAL_GLOSSARY", "HIGH", "official"),
    ("SDS", "SRC-DOMAIN-KOSHA", "MSDS", "SRC-DOMAIN-KOSHA", "SYNONYM_OF", "REVIEWED", "DOMAIN_RESEARCH", "MEDIUM", "GHS SDS ~ MSDS"),
]

KIWI_CANDIDATES = [
    ("국소배기장치", "NNP", "COMPOUND_SEGMENTATION", "국소배기장치", "SRC-DOMAIN-KOSHA"),
    ("위험성평가", "NNP", "COMPOUND_SEGMENTATION", "위험성평가", "SRC-DOMAIN-KOSHA"),
    ("밀폐공간작업", "NNP", "COMPOUND_SEGMENTATION", "밀폐공간작업", "SRC-DOMAIN-KOSHA"),
    ("산업용로봇", "NNP", "COMPOUND_SEGMENTATION", "산업용로봇", "SRC-DOMAIN-KOSHA"),
]

_gt = _ground_truth_terms()
_alias_terms, _alias_rels = _alias_terms_and_relations()
TERMS = _gt + _alias_terms + _OVERLAY_TERMS
RELATIONS = _alias_rels + _OVERLAY_RELATIONS


def verify_extracts():
    """Recompute extract SHA-256 and compare to pinned checksums (WO §17)."""
    import hashlib
    out = {}
    for name, expected in EXTRACT_CHECKSUMS.items():
        lines = [l.rstrip("\n") for l in
                 open(os.path.join(_EXTRACT, name), encoding="utf-8") if l.strip("\n")]
        got = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
        out[name] = (got == expected, got)
    return out


if __name__ == "__main__":
    print(f"snapshot={SNAPSHOT_ID} terms={len(TERMS)} relations={len(RELATIONS)}")
    for name, (ok, got) in verify_extracts().items():
        print(f"  extract {name}: {'OK' if ok else 'MISMATCH'} {got}")
