#!/usr/bin/env python3
"""T4 runtime benchmark — MORPHOLOGY / COMPOUND_NOUN via Kiwi TOKEN tier and
TYPO / TRIGRAM via pg_trgm on a scratch (non-production) Postgres DB.

MASTER-WO-TAI-SEARCH-DICT-001 §T4. Cases are DERIVED from the projection —
never invented (WO §71/§124):

  MORPHOLOGY    inflected form of an APPROVED subject surface (append -이,
                -을, -에서 to the last noun). Correct answer: same subject.
  COMPOUND_NOUN a KIWI_CANDIDATE compound term (국소배기장치 etc.), and
                variants embedded in a phrase ("<compound> 점검"). Correct
                answer: subject that shares the compound noun.
  TYPO          single-character deletion, single-character transposition of
                consecutive characters in an APPROVED surface. Correct answer:
                original subject.
  TRIGRAM       longer edit distance (2-char deletion) of an APPROVED surface.

Env: SEARCH_DICT_SEED=seed_v2, TAI_SEARCH_SCRATCH_DSN=postgres://.../scratch
Emits <out>/SEARCH_BENCHMARK_v2_kiwi_trgm.tsv and merges the MEASURED rows into
<out>/SEARCH_BENCHMARK_RESULT_v1.tsv (categories MORPHOLOGY/COMPOUND_NOUN/
TYPO/TRIGRAM change from PENDING_RUNTIME to MEASURED).
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_core  # noqa: E402
import search_runtime_ext as EXT  # noqa: E402

S = importlib.import_module(os.environ.get("SEARCH_DICT_SEED", "seed_v2"))


def _approved_subjects_by_type(proj):
    subs = []
    for s in proj["subjects"]:
        approved = [t for t in s["terms"] if not t.get("non_production")]
        if not approved:
            continue
        subs.append((s["subject_type"], s["subject_key"], approved))
    return subs


def _build_projection():
    tmp = tempfile.mkdtemp(prefix="bench_ext_")
    subprocess.run(
        [sys.executable, os.path.join(HERE, "build_dictionary.py"), "build", tmp],
        check=True, capture_output=True, env={**os.environ},
    )
    proj_path = os.path.join(tmp, "TAI_SEARCH_RUNTIME_PROJECTION_v1.json")
    dict_path = os.path.join(tmp, "TAI_KIWI_USER_DICTIONARY_v1.txt")
    with open(proj_path, encoding="utf-8") as f:
        return json.load(f), proj_path, dict_path


# -------------------- case generators (deterministic) --------------------

INFLECT_SUFFIXES = ["을", "이", "에서", "으로"]


def _first_letters(s: str, n: int) -> str:
    return s[:n]


def morphology_cases(proj):
    """Attach a common inflection to a compact surface; expect the same subject.
    Uses subject_key (short, controllable). Deterministic order.
    """
    out = []
    for stype, skey, _terms in _approved_subjects_by_type(proj):
        # only tokens that look like standalone nouns (avoid multi-word law names)
        if any(c.isspace() for c in skey):
            continue
        if len(skey) < 2 or len(skey) > 10:
            continue
        # skip English abbrevs
        if all(c.isascii() for c in skey):
            continue
        for suf in INFLECT_SUFFIXES[:2]:  # keep set tight
            out.append((f"{skey}{suf}", f"{stype}::{skey}"))
    return sorted(out)


def compound_cases(proj, kiwi_cands):
    """KIWI compound + phrase-embedded compound."""
    out = []
    subj_by_key = {s["subject_key"]: s for s in proj["subjects"]}
    for term, *_ in kiwi_cands:
        s = subj_by_key.get(term)
        if not s:
            continue
        skf = f"{s['subject_type']}::{s['subject_key']}"
        out.append((term, skf))
        out.append((f"{term} 점검", skf))
        out.append((f"{term} 안전관리", skf))
    return sorted(out)


def _typo_delete_one(s: str) -> str | None:
    # delete a middle char (deterministic: index len//2)
    if len(s) < 3:
        return None
    i = len(s) // 2
    return s[:i] + s[i + 1:]


def _typo_transpose(s: str) -> str | None:
    if len(s) < 3:
        return None
    i = len(s) // 2
    if i + 1 >= len(s):
        return None
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


def _typo_delete_two(s: str) -> str | None:
    if len(s) < 5:
        return None
    i = len(s) // 2
    return s[:i] + s[i + 2:]


def _iter_typo_targets(proj):
    """Yield (subject_key, subject_key_full) pairs eligible for typo variation.
    Uses subject_key (short surface) to keep edit-distance meaningful.
    """
    for stype, skey, _terms in _approved_subjects_by_type(proj):
        if any(c.isspace() for c in skey):
            continue
        if not (3 <= len(skey) <= 12):
            continue
        if all(c.isascii() for c in skey):
            continue
        yield skey, f"{stype}::{skey}"


def typo_cases(proj):
    out = []
    for skey, skf in _iter_typo_targets(proj):
        for gen in (_typo_delete_one, _typo_transpose):
            q = gen(skey)
            if q and q != skey:
                out.append((q, skf))
    return sorted(set(out))


def trigram_cases(proj):
    out = []
    for skey, skf in _iter_typo_targets(proj):
        q = _typo_delete_two(skey)
        if q and q != skey:
            out.append((q, skf))
    return sorted(set(out))


# --------------------------- measurement ---------------------------

def _rank_of(items, expected):
    for i, it in enumerate(items):
        skf = f"{it['subject_type']}::{it['subject_key']}"
        if skf == expected:
            return i + 1
    return None


def _measure_top3(candidates_fn, cases):
    n = 0
    top1 = 0
    top3 = 0
    for q, exp in cases:
        n += 1
        cands = candidates_fn(q)
        rk = _rank_of(cands, exp)
        if rk is not None and rk <= 1:
            top1 += 1
        if rk is not None and rk <= 3:
            top3 += 1
    return n, top1, top3


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    proj, proj_path, dict_path = _build_projection()

    # --- Tier 4 (Kiwi TOKEN) ---
    tok = EXT.TokenTier(proj, user_dict_path=dict_path)

    morph = morphology_cases(proj)
    comp = compound_cases(proj, S.KIWI_CANDIDATES)

    # For MORPHOLOGY/COMPOUND_NOUN we prefer combining the exact tiers with
    # the Kiwi TOKEN tier so a match_type=EXACT/NORMALIZED_EXACT counts too —
    # this mirrors production behaviour (TOKEN augments the exact tiers, does
    # not replace them). We rerank candidates by (score desc, subject_key).
    core = search_core.SearchEngine(proj)

    def kiwi_candidates(q):
        exacts = core.search(q, limit=10)["items"]
        seen = {(it["subject_type"], it["subject_key"]) for it in exacts}
        toks = tok.candidates(q, min_overlap=1)
        for c in toks:
            key = (c["subject_type"], c["subject_key"])
            if key in seen:
                continue
            exacts.append({
                "subject_type": c["subject_type"],
                "subject_key": c["subject_key"],
                "display_name": c["subject_key"],
                "matched_term": c["matched_term"],
                "match_type": c["match_type"],
                # TokenTier now returns a composite score (overlap + substring
                # bonus, WO-2 R2). Use it directly instead of overlap.
                "score": search_core.MATCH_SCORE["TOKEN"] + c.get("score", c["overlap"]),
            })
            seen.add(key)
        exacts.sort(key=lambda x: (-x["score"], x["subject_key"]))
        return exacts

    n_m, t1m, t3m = _measure_top3(kiwi_candidates, morph)
    n_c, t1c, t3c = _measure_top3(kiwi_candidates, comp)

    # --- Tier 6 (pg_trgm on scratch DB) ---
    dsn = os.environ.get("TAI_SEARCH_SCRATCH_DSN")
    if not dsn:
        sys.exit("ERROR: set TAI_SEARCH_SCRATCH_DSN (non-prod scratch DB) to run.")
    trg = EXT.TrigramTier(proj, dsn=dsn)

    typo = typo_cases(proj)
    tri = trigram_cases(proj)

    # Similar composition: combine exacts + trgm candidates so genuine EXACT
    # hits still count. If the typo query happens to still normalize to an
    # exact surface, that is a legitimate PASS.
    def trgm_candidates(q, limit=10):
        exacts = core.search(q, limit=limit)["items"]
        seen = {(it["subject_type"], it["subject_key"]) for it in exacts}
        for c in trg.candidates(q, limit=limit):
            key = (c["subject_type"], c["subject_key"])
            if key in seen:
                continue
            exacts.append({
                "subject_type": c["subject_type"],
                "subject_key": c["subject_key"],
                "display_name": c["subject_key"],
                "matched_term": c["matched_term"],
                "match_type": c["match_type"],
                "score": search_core.MATCH_SCORE["TRIGRAM"] + int(c["similarity"] * 10),
            })
            seen.add(key)
        exacts.sort(key=lambda x: (-x["score"], x["subject_key"]))
        return exacts

    n_t, t1t, t3t = _measure_top3(trgm_candidates, typo)
    n_g, t1g, t3g = _measure_top3(trgm_candidates, tri)

    # --- emit v2 supplementary query set ---
    v2_query_path = os.path.join(out_dir, "SEARCH_BENCHMARK_v2_kiwi_trgm.tsv")
    with open(v2_query_path, "w", encoding="utf-8", newline="") as f:
        f.write("category\tquery\texpected_subject\tsource_rule\n")
        for q, exp in morph:
            f.write(f"MORPHOLOGY\t{q}\t{exp}\tsubject_key + inflection\n")
        for q, exp in comp:
            f.write(f"COMPOUND_NOUN\t{q}\t{exp}\tKIWI_CANDIDATE compound\n")
        for q, exp in typo:
            f.write(f"TYPO\t{q}\t{exp}\tdelete-1 or transpose-2\n")
        for q, exp in tri:
            f.write(f"TRIGRAM\t{q}\t{exp}\tdelete-2\n")

    # --- rewrite RESULT tsv: replace PENDING rows with MEASURED rows ---
    result_path = os.path.join(out_dir, "SEARCH_BENCHMARK_RESULT_v1.tsv")
    # If the caller hasn't run benchmark_run.py first, start with just the pending set
    if not os.path.exists(result_path):
        subprocess.run(
            [sys.executable, os.path.join(HERE, "benchmark_run.py"), out_dir],
            check=True, env={**os.environ},
        )
    lines = open(result_path, encoding="utf-8").read().splitlines()
    measured = {
        "MORPHOLOGY":    (n_m, t3m),
        "COMPOUND_NOUN": (n_c, t3c),
        "TYPO":          (n_t, t3t),
        "TRIGRAM":       (n_g, t3g),
    }
    updated = []
    for line in lines:
        parts = line.split("\t")
        if parts and parts[0] in measured:
            n, t3 = measured[parts[0]]
            if n == 0:
                updated.append(f"{parts[0]}\t0\ttop3\tN/A\t-\tNO_CASES\tMEASURED (extension)")
            else:
                val = t3 / n
                # Confirmed gates (owner-fixed): MORPH/COMPOUND >=0.95,
                # TYPO/TRIGRAM >=0.85.
                thr = 0.95 if parts[0] in ("MORPHOLOGY", "COMPOUND_NOUN") else 0.85
                delta = val - thr
                verdict = "PASS" if val >= thr else "FAIL"
                marker = "+" if delta >= 0 else ""
                updated.append(
                    f"{parts[0]}\t{n}\ttop3\t{val:.4f}\t>={thr:.2f}\t"
                    f"{verdict}({marker}{delta:.4f})\tMEASURED (extension)"
                )
        else:
            updated.append(line)
    with open(result_path, "w", encoding="utf-8") as f:
        f.write("\n".join(updated) + "\n")

    # console summary
    print("=== T4 extension benchmark ===")
    for cat, (n, t3) in measured.items():
        val = (t3 / n) if n else 0.0
        print(f"  {cat:<14}n={n:<4} top3={val:.4f}")
    print(f"wrote v2 queries: {v2_query_path}")
    print(f"updated: {result_path}")
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(main(out))
