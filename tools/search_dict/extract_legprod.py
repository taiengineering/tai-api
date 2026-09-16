#!/usr/bin/env python3
"""Deterministic full-corpus extractor for the TAI Search Dictionary (WO P4).

Runs against the live leg-prod database (read-only) and reproduces the pinned
extract snapshots consumed by seed_v2.py, verifying byte-exactness via the same
server-side SHA-256 used when they were materialised:

  extract/GROUND_TRUTH_464.tsv  sha256 9cf9d73cb35a8884164dd999ff8aa10b59e0098c9
                                       6e3a940205f801825fea178
  extract/LAW_ALIAS_15.tsv      sha256 e3006ed67d4b93f435419ce47288aced44bcb3bdb
                                       97e97e3308bc31780cbabbe

It can ALSO emit the full corpus at scale (14,942 rows: 1,725 verified +
13,213 unverified PROPOSED kiwi-extractions). Verified rows feed the APPROVED
production index; unverified rows are emitted with status PROPOSED and are
NEVER placed in the production tiers (WO §21/§30/§52).

This environment (the authoring session) has no DB driver / network, so this
script is the reproducible mechanism for the full-scale run under Cursor /
Claude Code, which has both. Read-only: SELECT only; never writes, never applies
migrations (WO §44/§122).

Usage:
  DATABASE_URL=postgres://... python3 extract_legprod.py verify   # reproduce+check snapshots
  DATABASE_URL=postgres://... python3 extract_legprod.py full OUT  # emit full corpus TSV
"""
from __future__ import annotations

import hashlib
import os
import sys

PROJECT = "wrfcedzgdrfupenzqhur"  # leg-prod (reference only)

PINNED = {
    "GROUND_TRUTH_464.tsv":
        "9cf9d73cb35a8884164dd999ff8aa10b59e0098c96e3a940205f801825fea178",
    "LAW_ALIAS_15.tsv":
        "e3006ed67d4b93f435419ce47288aced44bcb3bdb97e97e3308bc31780cbabbe",
}

# ORDER BY clauses fixed for determinism (same snapshot -> same bytes, WO §17/§94)
Q_GROUND_TRUTH = """
SELECT term, pos_tag, term_type, source
FROM public.dict_legal_terms
WHERE verified = true AND term_type IN ('LAW_NAME','AGENCY_NAME','TECH_TERM')
ORDER BY term_type, term
"""
Q_ALIAS = """
SELECT short_name, full_name FROM public.law_alias ORDER BY short_name
"""
Q_VERIFIED_GENERIC = """
SELECT term, pos_tag, term_type, frequency, source
FROM public.dict_legal_terms
WHERE verified = true AND term_type = 'GENERIC'
ORDER BY frequency DESC, term
"""
Q_FULL = """
SELECT term, pos_tag, term_type, frequency, source, verified
FROM public.dict_legal_terms
ORDER BY verified DESC, term_type, frequency DESC, term
"""


def _connect():
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        sys.exit("ERROR: set DATABASE_URL (read-only leg-prod DSN) to run.")
    try:
        import psycopg  # psycopg3
        return psycopg.connect(dsn)
    except ImportError:
        import psycopg2  # fallback
        return psycopg2.connect(dsn)


def _sha256_lines(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def cmd_verify():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(Q_GROUND_TRUTH)
    gt = ["\t".join(str(c) for c in row) for row in cur.fetchall()]
    cur.execute(Q_ALIAS)
    al = ["\t".join(str(c) for c in row) for row in cur.fetchall()]
    conn.close()
    checks = {
        "GROUND_TRUTH_464.tsv": _sha256_lines(gt),
        "LAW_ALIAS_15.tsv": _sha256_lines(al),
    }
    ok = True
    for name, got in checks.items():
        exp = PINNED[name]
        match = got == exp
        ok = ok and match
        print(f"{name}: {'OK' if match else 'MISMATCH'} sha256={got}")
        if not match:
            print(f"   expected {exp}")
    print("VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_full(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(Q_FULL)
    rows = cur.fetchall()
    conn.close()
    path = os.path.join(out_dir, "TERM_SOURCE_EXTRACT_FULL.tsv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("term\tpos_tag\tterm_type\tfrequency\tsource\tverified\n")
        for r in rows:
            f.write("\t".join(str(c) for c in r) + "\n")
    verified = sum(1 for r in rows if r[-1])
    print(f"FULL extract: {len(rows)} rows ({verified} verified, "
          f"{len(rows) - verified} PROPOSED) -> {path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("verify", "full"):
        sys.exit(__doc__)
    if sys.argv[1] == "verify":
        sys.exit(cmd_verify())
    sys.exit(cmd_full(sys.argv[2] if len(sys.argv) > 2 else "."))
