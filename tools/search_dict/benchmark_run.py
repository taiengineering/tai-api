#!/usr/bin/env python3
"""Offline benchmark for the deterministic search tiers (WO §69-75, P10).

MEASURES (not fabricates) recall + latency for the tiers verifiable without
Kiwi/DB: EXACT, SPACING, PUNCTUATION, ABBREVIATION, ENGLISH_KOREAN, SYNONYM,
NO_MATCH. Categories that require Kiwi morphology (MORPHOLOGY, COMPOUND_NOUN)
or a live pg_trgm index (TYPO, TRIGRAM) are emitted as PENDING_RUNTIME rows —
never assigned an invented recall (WO §71 forbids fabricated targets).

Usage: SEARCH_DICT_SEED=seed_v2 python3 benchmark_run.py <out_dir>
Emits <out_dir>/SEARCH_BENCHMARK_v1.tsv and SEARCH_BENCHMARK_RESULT_v1.tsv.
Deterministic query set; latency is wall-clock (informational, host-dependent).
"""
from __future__ import annotations

import importlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_core  # noqa: E402

S = importlib.import_module(os.environ.get("SEARCH_DICT_SEED", "seed_v2"))

# WO §69-73 quality gates (Top-N recall thresholds), offline-measurable subset.
GATES = {
    "EXACT":          ("top1", 1.00),
    "SPACING":        ("top3", 0.98),
    "PUNCTUATION":    ("top3", 0.98),
    "ABBREVIATION":   ("top3", 0.95),
    "SYNONYM":        ("top3", 0.95),
    "ENGLISH_KOREAN": ("top3", 0.95),
    "NO_MATCH":       ("precision", 1.00),
}
# Categories that cannot be measured in this environment (documented, not scored)
PENDING = ["MORPHOLOGY", "COMPOUND_NOUN", "TYPO", "TRIGRAM"]

NO_MATCH_QUERIES = ["zzxxqq", "없는법령명입니다", "qwerty12345", "해당사항없음 abcxyz"]


def build_cases():
    cases = []  # (category, query, expected_subject_or_None)
    for t in S.TERMS:
        (sid, skey, ttype, orig, lang, pos, subt, subk, status,
         qf, cur, conf, ev) = t
        if status != "APPROVED":
            continue
        expected = f"{subt}::{subk}"
        if ttype == "SOURCE_NAME":
            cases.append(("EXACT", orig, expected))
        elif ttype == "SPACING_VARIANT":
            cases.append(("SPACING", orig, expected))
        elif ttype == "ABBREVIATION":
            cases.append(("ABBREVIATION", orig, expected))
        elif ttype == "ENGLISH_TERM":
            cases.append(("ENGLISH_KOREAN", orig, expected))
        elif ttype == "SYNONYM":
            cases.append(("SYNONYM", orig, expected))
        # PUNCTUATION: KR law-name separator dropped by the user
        if "\u318d" in orig and status == "APPROVED" and ttype == "SOURCE_NAME":
            cases.append(("PUNCTUATION", orig.replace("\u318d", ""), expected))
    for q in NO_MATCH_QUERIES:
        cases.append(("NO_MATCH", q, None))
    # stable order
    cases.sort(key=lambda c: (c[0], c[1]))
    return cases


def rank_of(items, expected):
    for i, it in enumerate(items):
        if f"{it['subject_type']}::{it['subject_key']}" == expected:
            return i + 1
    return None


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="bench_")
    subprocess.run([sys.executable, os.path.join(HERE, "build_dictionary.py"),
                    "build", tmp], check=True, capture_output=True,
                   env={**os.environ})
    proj = json.load(open(os.path.join(tmp, "TAI_SEARCH_RUNTIME_PROJECTION_v1.json"),
                          encoding="utf-8"))
    eng = search_core.SearchEngine(proj)
    cases = build_cases()

    # write query set (WO §69 SEARCH_BENCHMARK_v1.tsv)
    with open(os.path.join(out_dir, "SEARCH_BENCHMARK_v1.tsv"), "w",
              encoding="utf-8", newline="") as f:
        f.write("category\tquery\texpected_subject\n")
        for cat, q, exp in cases:
            f.write(f"{cat}\t{q}\t{exp or ''}\n")

    # measure recall
    from collections import defaultdict
    tot = defaultdict(int)
    top1 = defaultdict(int)
    top3 = defaultdict(int)
    top5 = defaultdict(int)
    nomatch_ok = 0
    nomatch_tot = 0
    for cat, q, exp in cases:
        r = eng.search(q, limit=5)
        items = r["items"]
        if cat == "NO_MATCH":
            nomatch_tot += 1
            if not items:
                nomatch_ok += 1
            continue
        tot[cat] += 1
        rk = rank_of(items, exp)
        if rk is not None:
            if rk <= 1:
                top1[cat] += 1
            if rk <= 3:
                top3[cat] += 1
            if rk <= 5:
                top5[cat] += 1

    # measure latency: deterministic repeated runs over the measurable queries
    qlist = [q for (cat, q, _e) in cases if cat != "NO_MATCH"]
    lat = []
    ITER = 6
    for _ in range(ITER):
        for q in qlist:
            t0 = time.perf_counter()
            eng.search(q, limit=10)
            lat.append((time.perf_counter() - t0) * 1000.0)
    lat.sort()

    def pct(p):
        if not lat:
            return 0.0
        k = min(len(lat) - 1, int(round(p / 100.0 * (len(lat) - 1))))
        return lat[k]

    # write result (WO §97 SEARCH_BENCHMARK_RESULT_v1.tsv) + gate verdicts
    rows = []
    overall_pass = True
    for cat, (metric, thr) in GATES.items():
        if cat == "NO_MATCH":
            n = nomatch_tot
            val = (nomatch_ok / n) if n else 0.0
            passed = val >= thr
            rows.append((cat, n, "precision(empty)", f"{val:.4f}", f">={thr:.2f}",
                         "PASS" if passed else "FAIL", "MEASURED"))
        else:
            n = tot[cat]
            if n == 0:
                rows.append((cat, 0, metric, "N/A", f">={thr:.2f}", "NO_CASES",
                             "MEASURED"))
                continue
            hit = {"top1": top1, "top3": top3, "top5": top5}[metric][cat]
            val = hit / n
            passed = val >= thr
            rows.append((cat, n, metric, f"{val:.4f}", f">={thr:.2f}",
                         "PASS" if passed else "FAIL", "MEASURED"))
        if rows[-1][5] == "FAIL":
            overall_pass = False
    for cat in PENDING:
        rows.append((cat, 0, "recall", "PENDING_RUNTIME", "-", "PENDING",
                     "REQUIRES_KIWI_OR_PGTRGM"))

    with open(os.path.join(out_dir, "SEARCH_BENCHMARK_RESULT_v1.tsv"), "w",
              encoding="utf-8", newline="") as f:
        f.write("category\tn\tmetric\tvalue\tgate\tverdict\tnote\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
        f.write(f"#LATENCY_MS\tn={len(lat)}\tmean={statistics.mean(lat):.4f}"
                f"\tp50={pct(50):.4f}\tp95={pct(95):.4f}\tp99={pct(99):.4f}\n")
        f.write(f"#SNAPSHOT\t{S.SNAPSHOT_ID}\tterms={len(S.TERMS)}"
                f"\trelations={len(S.RELATIONS)}\n")

    # console summary
    print(f"BENCHMARK snapshot={S.SNAPSHOT_ID} cases={len(cases)}")
    print(f"{'category':<14}{'n':>5}  {'metric':<10}{'value':>10}  gate      verdict")
    for cat, n, metric, val, gate, verdict, note in rows:
        print(f"{cat:<14}{n:>5}  {metric:<10}{val:>10}  {gate:<8}  {verdict}")
    print(f"LATENCY(ms) n={len(lat)} mean={statistics.mean(lat):.4f} "
          f"p50={pct(50):.4f} p95={pct(95):.4f} p99={pct(99):.4f}")
    print("OFFLINE GATES:", "PASS" if overall_pass else "FAIL")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(main(out))
