#!/usr/bin/env python3
"""TAI Search Dictionary — deterministic compiler / validator / CLI.

MASTER-WO-TAI-SEARCH-DICT-001 §66 (deterministic compiler), §67 (CLI),
§68 (validation), §94 (determinism: same snapshot -> identical output SHA).

Commands:
  census     print source registry + term/relation counts
  validate   run all structural validations (§68); non-zero exit on failure
  build      emit all artifacts (TSV + runtime projection JSON)
  export-kiwi  emit Kiwi user dictionary (.txt) + machine TSV
  benchmark  emit the benchmark query set (targets only; scoring is runtime)

Determinism: every artifact is emitted with sorted, stable ordering; no
timestamps, no randomness, no dict-iteration-order dependence. Running `build`
twice yields byte-identical files (proven by scripts/determinism_check).

Runtime dependency: NONE. This compiler is pure stdlib. Kiwi before/after
measurement and DB/pg_trgm search are runtime concerns and are NOT invented here.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import normalize as N  # noqa: E402
import seed_v1 as S  # noqa: E402

# ---- Contract enums (must match SEARCH_TERM_CONTRACT_v1.md) --------------
TERM_TYPES = {
    "CANONICAL_NAME", "SOURCE_NAME", "ALIAS", "SYNONYM", "ABBREVIATION",
    "FIELD_TERM", "ENGLISH_TERM", "SPELLING_VARIANT", "SPACING_VARIANT",
    "PUNCTUATION_VARIANT", "SEARCH_PHRASE", "KIWI_USER_WORD",
}
RELATION_TYPES = {
    "EXACT_ALIAS", "SYNONYM_OF", "ABBREVIATION_OF", "ENGLISH_OF",
    "FIELD_TERM_OF", "SPELLING_VARIANT_OF", "SPACING_VARIANT_OF",
    "PUNCTUATION_VARIANT_OF", "RELATED_TERM", "BROADER_SEARCH_TERM",
    "NARROWER_SEARCH_TERM", "AMBIGUOUS_WITH",
}
STATUSES = {"PROPOSED", "REVIEWED", "APPROVED", "REJECTED", "HOLD"}
SUBJECT_TYPES = {
    "RISK_REVIEW_CONCEPT", "RISK_SOURCE", "LEGAL_TERM", "KOSHA_TERM",
    "KALIS_TERM", "CHEM_TERM", "ACCIDENT_TERM", "EQUIPMENT_TERM",
    "GENERAL_TERM",
}
# expansion-eligible relations for search Tier 3/5 (only APPROVED used at runtime)
EXPANSION_RELATIONS = {
    "EXACT_ALIAS", "SYNONYM_OF", "ABBREVIATION_OF", "ENGLISH_OF",
    "SPELLING_VARIANT_OF", "SPACING_VARIANT_OF", "PUNCTUATION_VARIANT_OF",
}

MASTER_COLS = [
    "term_id", "term_original", "term_normalized", "term_compact",
    "term_latin_lower", "term_no_punctuation", "term_type", "language",
    "pos_hint", "subject_type", "subject_key", "canonical_id", "status",
    "source_id", "source_key", "evidence_ref", "quality_flag",
    "curation_method", "confidence", "created_from_snapshot",
]
REL_COLS = [
    "relation_id", "source_term_id", "target_term_id", "relation_type",
    "status", "evidence_ref", "confidence", "curation_method",
]


def build_terms():
    rows = []
    for (sid, skey, ttype, orig, lang, pos, subt, subk, status, qflag,
         cur, conf, ev) in S.TERMS:
        tid = N.term_id(sid, skey, ttype, orig)
        rows.append({
            "term_id": tid,
            "term_original": orig,
            "term_normalized": N.normalize_basic(orig),
            "term_compact": N.compact(orig),
            "term_latin_lower": N.latin_lower(orig),
            "term_no_punctuation": N.no_punctuation(orig),
            "term_type": ttype,
            "language": lang,
            "pos_hint": pos,
            "subject_type": subt,
            "subject_key": subk,
            "canonical_id": "",  # nullable (WO §47)
            "status": status,
            "source_id": sid,
            "source_key": skey,
            "evidence_ref": ev,
            "quality_flag": qflag,
            "curation_method": cur,
            "confidence": conf,
            "created_from_snapshot": S.SNAPSHOT_ID,
        })
    rows.sort(key=lambda r: (r["term_id"]))
    return rows


def _resolve_index(terms):
    # (original, source_id) -> term_id  (original+source is the seed natural key)
    idx = {}
    for (sid, skey, ttype, orig, *_rest) in S.TERMS:
        idx[(orig, sid)] = N.term_id(sid, skey, ttype, orig)
    return idx


def build_relations():
    idx = _resolve_index(None)
    rows = []
    for (so, ssid, to, tsid, rtype, status, cur, conf, ev) in S.RELATIONS:
        stid = idx.get((so, ssid))
        ttid = idx.get((to, tsid))
        rid = N.relation_id(stid or so, ttid or to, rtype)
        rows.append({
            "relation_id": rid,
            "source_term_id": stid or f"UNRESOLVED:{so}",
            "target_term_id": ttid or f"UNRESOLVED:{to}",
            "relation_type": rtype,
            "status": status,
            "evidence_ref": ev,
            "confidence": conf,
            "curation_method": cur,
        })
    rows.sort(key=lambda r: (r["relation_id"]))
    return rows


def validate(terms, relations):
    errors = []
    seen = set()
    tids = set()
    for r in terms:
        if not r["term_original"].strip():
            errors.append(f"empty term: {r}")
        if r["term_type"] not in TERM_TYPES:
            errors.append(f"unknown term_type {r['term_type']} ({r['term_original']})")
        if r["status"] not in STATUSES:
            errors.append(f"invalid status {r['status']} ({r['term_original']})")
        if r["subject_type"] not in SUBJECT_TYPES:
            errors.append(f"unknown subject_type {r['subject_type']} ({r['term_original']})")
        if r["term_id"] in seen:
            errors.append(f"duplicate term_id {r['term_id']} ({r['term_original']})")
        seen.add(r["term_id"])
        tids.add(r["term_id"])
        # untraceable APPROVED term (§68 / §110): APPROVED must have source + evidence
        if r["status"] == "APPROVED" and not (r["source_id"] and r["evidence_ref"]):
            errors.append(f"untraceable APPROVED term {r['term_original']}")
        # subject required (§68 missing subject)
        if not r["subject_type"] or not r["subject_key"]:
            errors.append(f"missing subject for {r['term_original']}")
    rids = set()
    for r in relations:
        if r["relation_type"] not in RELATION_TYPES:
            errors.append(f"unknown relation_type {r['relation_type']}")
        if r["status"] not in STATUSES:
            errors.append(f"invalid relation status {r['status']}")
        if r["source_term_id"].startswith("UNRESOLVED") or r["target_term_id"].startswith("UNRESOLVED"):
            errors.append(f"dangling relation endpoint {r}")
        if r["source_term_id"] == r["target_term_id"]:
            errors.append(f"self relation {r['relation_id']}")
        if r["source_term_id"] not in tids or r["target_term_id"] not in tids:
            errors.append(f"relation endpoint not in master {r['relation_id']}")
        if r["relation_id"] in rids:
            errors.append(f"duplicate relation_id {r['relation_id']}")
        rids.add(r["relation_id"])
    return errors


def build_projection(terms, relations):
    """Runtime search projection (WO §48). Deterministic, sorted, in-memory dict.

    Only APPROVED terms/relations feed production tiers (Constitution art.11,
    WO §52). PROPOSED phrases are carried but flagged non_production=true.
    """
    by_id = {t["term_id"]: t for t in terms}
    # subject -> approved surface terms
    subjects = {}
    for t in terms:
        key = f"{t['subject_type']}::{t['subject_key']}"
        subjects.setdefault(key, {
            "subject_type": t["subject_type"],
            "subject_key": t["subject_key"],
            "canonical_id": None,
            "terms": [],
        })
        subjects[key]["terms"].append({
            "term_normalized": t["term_normalized"],
            "term_compact": t["term_compact"],
            "term_type": t["term_type"],
            "status": t["status"],
            "non_production": t["status"] != "APPROVED",
        })
    # approved expansion edges: normalized_query -> [subject_keys]
    expansions = []
    for r in relations:
        if r["status"] != "APPROVED" or r["relation_type"] not in EXPANSION_RELATIONS:
            continue
        s = by_id.get(r["source_term_id"])
        tt = by_id.get(r["target_term_id"])
        if not s or not tt:
            continue
        expansions.append({
            "from_compact": s["term_compact"],
            "to_subject": f"{tt['subject_type']}::{tt['subject_key']}",
            "relation_type": r["relation_type"],
        })
    for v in subjects.values():
        v["terms"].sort(key=lambda x: (x["term_normalized"], x["term_type"]))
    expansions.sort(key=lambda x: (x["from_compact"], x["to_subject"], x["relation_type"]))
    return {
        "snapshot_id": S.SNAPSHOT_ID,
        "snapshot_date": S.SNAPSHOT_DATE,
        "subjects": [subjects[k] for k in sorted(subjects.keys())],
        "expansions": expansions,
    }


# ---- serialization (deterministic) --------------------------------------
def tsv_bytes(cols, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, delimiter="\t", lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def kiwi_txt_bytes():
    lines = [f"{t}\t{pos}" for (t, pos, *_ ) in sorted(S.KIWI_CANDIDATES)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def kiwi_tsv_bytes():
    cols = ["term", "pos", "score", "source_term_id", "reason",
            "before_analysis", "after_analysis", "status"]
    rows = []
    idx = _resolve_index(None)
    for (term, pos, reason, sorig, sid) in sorted(S.KIWI_CANDIDATES):
        # find the source term_id if present
        stid = ""
        for (s2, sk2, tt2, o2, *_r) in S.TERMS:
            if o2 == sorig and s2 == sid:
                stid = N.term_id(s2, sk2, tt2, o2)
                break
        rows.append({
            "term": term, "pos": pos, "score": "",
            "source_term_id": stid, "reason": reason,
            "before_analysis": "PENDING_RUNTIME",
            "after_analysis": "PENDING_RUNTIME",
            "status": "PROPOSED",
        })
    return tsv_bytes(cols, rows)


def write(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)


def cmd_build(outdir):
    os.makedirs(outdir, exist_ok=True)
    terms = build_terms()
    rels = build_relations()
    errs = validate(terms, rels)
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print("  -", e)
        return 1
    proj = build_projection(terms, rels)
    artifacts = {
        "TAI_TERM_MASTER_v1.tsv": tsv_bytes(MASTER_COLS, terms),
        "TAI_TERM_RELATIONS_v1.tsv": tsv_bytes(REL_COLS, rels),
        "TAI_SEARCH_RUNTIME_PROJECTION_v1.json": json_bytes(proj),
        "TAI_KIWI_USER_DICTIONARY_v1.txt": kiwi_txt_bytes(),
        "TAI_KIWI_TERMS_v1.tsv": kiwi_tsv_bytes(),
    }
    shas = {}
    for name, data in artifacts.items():
        write(os.path.join(outdir, name), data)
        shas[name] = sha256_hex(data)
    write(os.path.join(outdir, "BUILD_SHA256SUMS.txt"),
          ("\n".join(f"{shas[n]}  {n}" for n in sorted(shas)) + "\n").encode("utf-8"))
    print("BUILD OK")
    print(f"  terms={len(terms)} relations={len(rels)} subjects={len(proj['subjects'])} expansions={len(proj['expansions'])}")
    for n in sorted(shas):
        print(f"  {shas[n]}  {n}")
    return 0


def cmd_validate():
    terms = build_terms()
    rels = build_relations()
    errs = validate(terms, rels)
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print("  -", e)
        return 1
    print(f"VALIDATION PASS: terms={len(terms)} relations={len(rels)}")
    return 0


def cmd_census():
    terms = build_terms()
    rels = build_relations()
    from collections import Counter
    tt = Counter(t["term_type"] for t in terms)
    st = Counter(t["status"] for t in terms)
    rt = Counter(r["relation_type"] for r in rels)
    print(f"snapshot={S.SNAPSHOT_ID} ({S.SNAPSHOT_DATE})")
    print(f"sources={len(S.SOURCES)} terms={len(terms)} relations={len(rels)}")
    print("term_type:", dict(sorted(tt.items())))
    print("status:", dict(sorted(st.items())))
    print("relation_type:", dict(sorted(rt.items())))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "census"
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "out")
    rc = {
        "census": cmd_census,
        "validate": cmd_validate,
        "build": lambda: cmd_build(outdir),
        "export-kiwi": lambda: (write(os.path.join(outdir, "TAI_KIWI_USER_DICTIONARY_v1.txt"), kiwi_txt_bytes()) or 0),
    }.get(cmd, cmd_census)()
    sys.exit(rc or 0)
