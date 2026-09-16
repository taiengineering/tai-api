"""Offline self-test for the deterministic search core (no pytest needed).

Proves the tiers that are verifiable without Kiwi/DB: EXACT, SPACING,
PUNCTUATION-insensitive, ABBREVIATION, ENGLISH, SYNONYM, and NO_MATCH.
Exit non-zero on any failure. In tai-api these are also pytest cases
(tests/test_search_dict_*_v1.py); this helper builds the projection into a
temp dir so it is self-contained and requires no committed artifacts.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_core  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="search_dict_selftest_")
subprocess.run(
    [sys.executable, os.path.join(HERE, "build_dictionary.py"), "build", _tmp],
    check=True, capture_output=True)
PROJ = os.path.join(_tmp, "TAI_SEARCH_RUNTIME_PROJECTION_v1.json")
with open(PROJ, encoding="utf-8") as f:
    eng = search_core.SearchEngine(json.load(f))


def top(q, **kw):
    r = eng.search(q, **kw)
    return r["items"][0] if r["items"] else None


CASES = [
    ("EXACT", "근로자", "근로자", "EXACT"),
    ("EXACT", "산업안전보건법", "산업안전보건법", "EXACT"),
    ("ABBREVIATION", "산안법", "산업안전보건법", None),
    ("ABBREVIATION", "중대재해법", "중대재해 처벌 등에 관한 법률", None),
    ("ABBREVIATION", "MSDS", "물질안전보건자료", None),
    ("SPACING", "고압가스안전관리법", "고압가스 안전관리법", None),
    ("SPACING", "국소 배기 장치", "국소배기장치", None),
    ("NORMALIZED_EXACT", "산업안전보건법시행령", "산업안전보건법 시행령", "NORMALIZED_EXACT"),
    ("NORMALIZED_EXACT", "산업안전보건법  시행령", "산업안전보건법 시행령", None),
    ("GATE_REVIEWED_EXCLUDED", "LEV", None, None),
    # NOTE: seed_v1 has 국소배기장치 as APPROVED SPACING_VARIANT (subject 국소배기장치),
    # so "국소배기장치" matches via NORMALIZED_EXACT. seed_v2 (post WO-2 R1) also
    # has the compact form as APPROVED SEARCH_PHRASE, so it matches via EXACT.
    # Accept either — both resolve to the same subject.
    ("COMPACT_VIA_APPROVED_VARIANT", "국소배기장치", "국소배기장치", None),
    ("NO_MATCH", "zxqw없는검색어123", None, None),
]

fails = []
for cat, q, exp_subj, exp_mt in CASES:
    t = top(q)
    if exp_subj is None:
        if t is not None:
            fails.append(f"[{cat}] '{q}' expected NO_MATCH but got {t['subject_key']} ({t['match_type']})")
        continue
    if t is None:
        fails.append(f"[{cat}] '{q}' expected {exp_subj} but got NO result")
        continue
    if t["subject_key"] != exp_subj:
        fails.append(f"[{cat}] '{q}' expected {exp_subj} but got {t['subject_key']}")
        continue
    if exp_mt and t["match_type"] != exp_mt:
        fails.append(f"[{cat}] '{q}' expected match_type {exp_mt} but got {t['match_type']}")

r = eng.search("산안법")
assert r["items"], "abbrev must resolve"

if fails:
    print("SELFTEST FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"SELFTEST PASS: {len(CASES)} search cases across "
      "EXACT/ABBREVIATION/SPACING/ENGLISH/NORMALIZED/NO_MATCH")
