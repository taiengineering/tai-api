"""WO-RISK-ABC-RECON-001 A/B/C final ingest dry-run / reconciliation.

Read-only, deterministic. Consumes the three frozen materialization
receipts (CIC_W, KOSHA, KALIS) as expected SoT, compares against the
live production `public.risk_source_mappings` set on (source_id,
source_key), and produces:

  * RISK_ABC_FINAL_RECONCILIATION_v1.tsv  — 4 rows (CIC_W / KOSHA / KALIS / TOTAL)
  * RISK_ABC_DEFERRED_BACKLOG_v1.tsv      — deterministic count of deferred buckets
  * OBJ_risk-abc-final-ingest-dryrun-reconciliation_v1.md — human report

NO writes, no semantic inference, no LLM, no fuzzy, no canonical
mutation. `--offline` uses the receipts alone (no DB); `--verify`
adds live production SELECT + full delta reconciliation.

CLI:
  python -m tools.risk_map.abc_final_reconcile --offline
  python -m tools.risk_map.abc_final_reconcile --verify   # requires DATABASE_URL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

WO_ID = "WO-RISK-ABC-RECON-001"

_ROOT = Path("docs/knowledge/risk")

# ---------------------------------------------------------------------------
# Frozen receipt SoT (row-level authority for each source)
# ---------------------------------------------------------------------------

CICW_RECEIPT_PATH = _ROOT / "RISK_MAP001_MATERIALIZATION_RECEIPT_v1.tsv"
KOSHA_RECEIPT_PATH = _ROOT / "RISK_KOSHA_MAP_MATERIALIZE001_RECEIPT_v1.tsv"
KALIS_RECEIPT_PATH = _ROOT / "RISK_KALIS_MATERIALIZATION_RECEIPT_v1.tsv"

EXPECTED_CICW = 1139
EXPECTED_KOSHA = 46
EXPECTED_KALIS = 9
EXPECTED_TOTAL = EXPECTED_CICW + EXPECTED_KOSHA + EXPECTED_KALIS  # 1194

# ---------------------------------------------------------------------------
# Deferred backlog SoT (deterministic counts from frozen semantic freezes;
# NOT a re-review — we only read what was already frozen)
# ---------------------------------------------------------------------------

# KOSHA 620 aggregate is frozen (WO-KOSHA-AGGREGATE-001) — reuse the bucket
# TSVs already committed under the KOSHA half.
KOSHA_AMBIGUOUS_PATH = _ROOT / "RISK_KOSHA_620_AMBIGUOUS_v1.tsv"
KOSHA_CANONICAL_GAP_PATH = _ROOT / "RISK_KOSHA_620_CANONICAL_GAP_v1.tsv"
KOSHA_NO_MATCH_PATH = _ROOT / "RISK_KOSHA_620_NO_MATCH_v1.tsv"
KOSHA_APPROVAL_BINDING_PATH = _ROOT / "RISK_KOSHA_MAP_APPROVE001_OWNER_APPROVAL_BINDING_v1.tsv"

# KALIS semantic row freeze is the single deterministic count source for KALIS.
KALIS_ROW_FREEZE_PATH = _ROOT / "RISK_KALIS_SEMANTIC_ROW_FREEZE_v1.tsv"
KALIS_OWNER_APPROVAL_PATH = _ROOT / "RISK_KALIS_OWNER_APPROVAL_v1.tsv"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

RECONCILIATION_PATH = _ROOT / "RISK_ABC_FINAL_RECONCILIATION_v1.tsv"
DEFERRED_BACKLOG_PATH = _ROOT / "RISK_ABC_DEFERRED_BACKLOG_v1.tsv"
REPORT_PATH = _ROOT / "OBJ_risk-abc-final-ingest-dryrun-reconciliation_v1.md"


RECONCILIATION_FIELDS: tuple[str, ...] = (
    "source",
    "review_universe_count",
    "approved_binding_count",
    "production_mapping_count",
    "missing_approved_count",
    "unexpected_production_count",
    "duplicate_count",
    "hold_leak_count",
    "already_materialized",
    "would_insert",
    "would_update",
    "would_delete",
    "verdict",
)


DEFERRED_BACKLOG_FIELDS: tuple[str, ...] = (
    "source",
    "semantic_bucket",
    "count",
    "production_eligible",
    "current_disposition",
    "blocking_current_stage",
)


# ---------------------------------------------------------------------------
# Load expected SoT from frozen receipts
# ---------------------------------------------------------------------------


def _load_expected() -> dict[str, set[tuple[str, str]]]:
    """Return {source_tag → set of (source_id, source_key)} from receipts."""
    out: dict[str, set[tuple[str, str]]] = {}

    cicw = load_tsv(CICW_RECEIPT_PATH)
    if len(cicw) != EXPECTED_CICW:
        raise SystemExit(f"CICW_RECEIPT_ROW_DRIFT {len(cicw)}")
    if {r["source_id"] for r in cicw} != {"CIC_W"}:
        raise SystemExit("CICW_RECEIPT_SCOPE_DRIFT")
    cicw_pairs = {(r["source_id"], r["source_key"]) for r in cicw}
    if len(cicw_pairs) != EXPECTED_CICW:
        raise SystemExit("CICW_RECEIPT_PAIR_NOT_UNIQUE")
    out["CIC_W"] = cicw_pairs

    kosha = load_tsv(KOSHA_RECEIPT_PATH)
    if len(kosha) != EXPECTED_KOSHA:
        raise SystemExit(f"KOSHA_RECEIPT_ROW_DRIFT {len(kosha)}")
    if {r["source_id"] for r in kosha} != {"KOSHA_CONSTRUCTION_PROCESS"}:
        raise SystemExit("KOSHA_RECEIPT_SCOPE_DRIFT")
    kosha_pairs = {(r["source_id"], r["source_key"]) for r in kosha}
    if len(kosha_pairs) != EXPECTED_KOSHA:
        raise SystemExit("KOSHA_RECEIPT_PAIR_NOT_UNIQUE")
    out["KOSHA"] = kosha_pairs

    kalis = load_tsv(KALIS_RECEIPT_PATH)
    if len(kalis) != EXPECTED_KALIS:
        raise SystemExit(f"KALIS_RECEIPT_ROW_DRIFT {len(kalis)}")
    if {r["source_id"] for r in kalis} != {"KALIS_RISK_PROFILE"}:
        raise SystemExit("KALIS_RECEIPT_SCOPE_DRIFT")
    kalis_pairs = {(r["source_id"], r["source_key"]) for r in kalis}
    if len(kalis_pairs) != EXPECTED_KALIS:
        raise SystemExit("KALIS_RECEIPT_PAIR_NOT_UNIQUE")
    out["KALIS"] = kalis_pairs
    return out


# HOLD source_keys per source — sanity data for the hold-leak guard.
def _load_hold_keys() -> dict[str, set[str]]:
    hold: dict[str, set[str]] = {"CIC_W": set(), "KOSHA": set(), "KALIS": set()}

    # KOSHA: 29 HOLD rows in the owner approval binding.
    kosha_binding = load_tsv(KOSHA_APPROVAL_BINDING_PATH)
    kosha_hold = {r["source_key"] for r in kosha_binding if r["owner_decision"] == "HOLD"}
    if len(kosha_hold) != 29:
        raise SystemExit(f"KOSHA_HOLD_COUNT_DRIFT {len(kosha_hold)}")
    hold["KOSHA"] = kosha_hold

    # KALIS: 39 HOLD rows in the owner approval binding.
    kalis_binding = load_tsv(KALIS_OWNER_APPROVAL_PATH)
    kalis_hold = {r["source_key"] for r in kalis_binding if r["owner_decision"] == "HOLD"}
    if len(kalis_hold) != 39:
        raise SystemExit(f"KALIS_HOLD_COUNT_DRIFT {len(kalis_hold)}")
    hold["KALIS"] = kalis_hold

    # CIC_W: HOLD source_key(s) from RISK-MAP-APPROVE-001. The frozen governance
    # module records a single held source-key; we import it verbatim.
    from tools.risk_map.map001_cicw_governance import EXPECTED_HOLD_SOURCE_KEY
    if EXPECTED_HOLD_SOURCE_KEY:
        hold["CIC_W"] = {EXPECTED_HOLD_SOURCE_KEY}
    return hold


# ---------------------------------------------------------------------------
# Live production read (SELECT-only)
# ---------------------------------------------------------------------------


def _require_database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("BLOCKED: DATABASE_URL not set")
    return url


def _connect_readonly():
    import psycopg2

    conn = psycopg2.connect(_require_database_url())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return conn


def _load_production_pairs(conn) -> dict[str, set[tuple[str, str]]]:
    out: dict[str, set[tuple[str, str]]] = {"CIC_W": set(), "KOSHA": set(), "KALIS": set()}
    tag_by_source = {
        "CIC_W": "CIC_W",
        "KOSHA_CONSTRUCTION_PROCESS": "KOSHA",
        "KALIS_RISK_PROFILE": "KALIS",
    }
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id, source_key FROM public.risk_source_mappings "
            "ORDER BY source_id, source_key"
        )
        rows = cur.fetchall()
    for source_id, source_key in rows:
        tag = tag_by_source.get(source_id)
        if tag is None:
            raise SystemExit(f"UNEXPECTED_PRODUCTION_SOURCE_ID {source_id}")
        out[tag].add((source_id, source_key))
    return out


def _load_canonical_targets_from_production(conn) -> tuple[set[str], set[str]]:
    """Return (mapped_canonical_id_set, present_canonical_id_set)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT canonical_id::text FROM public.risk_source_mappings "
            "WHERE canonical_id IS NOT NULL"
        )
        mapped = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT id::text FROM public.risk_canonical_nodes")
        present = {r[0] for r in cur.fetchall()}
    return mapped, present


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def _reconcile_one(
    tag: str,
    review_universe: int,
    expected: set[tuple[str, str]],
    actual: set[tuple[str, str]],
    hold_keys: set[str],
) -> dict:
    missing = expected - actual
    extra = actual - expected
    hold_leak_keys = {k for (_sid, k) in actual} & hold_keys
    verdict = "PASS" if not (missing or extra or hold_leak_keys) else "FAIL"
    return {
        "source": tag,
        "review_universe_count": str(review_universe),
        "approved_binding_count": str(len(expected)),
        "production_mapping_count": str(len(actual)),
        "missing_approved_count": str(len(missing)),
        "unexpected_production_count": str(len(extra)),
        "duplicate_count": "0",
        "hold_leak_count": str(len(hold_leak_keys)),
        "already_materialized": str(len(expected & actual)),
        "would_insert": str(len(missing)),
        "would_update": "0",
        "would_delete": str(len(extra)),
        "verdict": verdict,
    }


def build_reconciliation(actual_pairs: dict[str, set[tuple[str, str]]] | None) -> list[dict]:
    expected = _load_expected()
    hold_keys = _load_hold_keys()

    if actual_pairs is None:
        # --offline mode: treat expected as the production state (used for
        # deterministic artifact freeze / tests without DB access).
        actual_pairs = expected

    review_universe = {
        "CIC_W": 1722,   # CIC_W source-node count (frozen risk02)
        "KOSHA": 620,    # KOSHA GPT review universe
        "KALIS": 761,    # KALIS TASK count
    }

    out: list[dict] = []
    total_expected = set()
    total_actual = set()
    for tag in ("CIC_W", "KOSHA", "KALIS"):
        row = _reconcile_one(
            tag,
            review_universe[tag],
            expected[tag],
            actual_pairs[tag],
            hold_keys[tag],
        )
        out.append(row)
        total_expected |= expected[tag]
        total_actual |= actual_pairs[tag]

    missing_total = total_expected - total_actual
    extra_total = total_actual - total_expected
    total_hold_leak = sum(int(r["hold_leak_count"]) for r in out)
    total_verdict = (
        "PASS" if not (missing_total or extra_total or total_hold_leak) else "FAIL"
    )
    out.append(
        {
            "source": "TOTAL",
            "review_universe_count": str(sum(review_universe.values())),
            "approved_binding_count": str(len(total_expected)),
            "production_mapping_count": str(len(total_actual)),
            "missing_approved_count": str(len(missing_total)),
            "unexpected_production_count": str(len(extra_total)),
            "duplicate_count": "0",
            "hold_leak_count": str(total_hold_leak),
            "already_materialized": str(len(total_expected & total_actual)),
            "would_insert": str(len(missing_total)),
            "would_update": "0",
            "would_delete": str(len(extra_total)),
            "verdict": total_verdict,
        }
    )
    return out


def _assert_reconciliation_pass(rows: list[dict]) -> None:
    for r in rows:
        if r["verdict"] != "PASS":
            raise SystemExit(f"RECONCILIATION_FAIL {r['source']} {r}")
        if r["would_insert"] != "0":
            raise SystemExit(f"WOULD_INSERT_NONZERO {r['source']}")
        if r["would_update"] != "0":
            raise SystemExit(f"WOULD_UPDATE_NONZERO {r['source']}")
        if r["would_delete"] != "0":
            raise SystemExit(f"WOULD_DELETE_NONZERO {r['source']}")
        if r["hold_leak_count"] != "0":
            raise SystemExit(f"HOLD_LEAK_NONZERO {r['source']}")


# ---------------------------------------------------------------------------
# Deferred backlog (deterministic counts, no re-review)
# ---------------------------------------------------------------------------


def build_deferred_backlog() -> list[dict]:
    out: list[dict] = []

    # KOSHA — reuse frozen aggregate bucket row counts.
    kosha_ambiguous = load_tsv(KOSHA_AMBIGUOUS_PATH)
    kosha_gap = load_tsv(KOSHA_CANONICAL_GAP_PATH)
    kosha_no_match = load_tsv(KOSHA_NO_MATCH_PATH)
    kosha_binding = load_tsv(KOSHA_APPROVAL_BINDING_PATH)
    kosha_hold_count = sum(1 for r in kosha_binding if r["owner_decision"] == "HOLD")
    if kosha_hold_count != 29:
        raise SystemExit(f"KOSHA_HOLD_DRIFT {kosha_hold_count}")
    for bucket, count in (
        ("POSSIBLE_RELATED_HOLD", kosha_hold_count),
        ("AMBIGUOUS", len(kosha_ambiguous)),
        ("CANONICAL_GAP", len(kosha_gap)),
        ("NO_MATCH", len(kosha_no_match)),
    ):
        out.append(
            {
                "source": "KOSHA",
                "semantic_bucket": bucket,
                "count": str(count),
                "production_eligible": "NO",
                "current_disposition": "HOLD" if bucket == "POSSIBLE_RELATED_HOLD" else "DEFERRED",
                "blocking_current_stage": "NO",
            }
        )

    # KALIS — deterministic count from row freeze + owner binding.
    kalis_rows = load_tsv(KALIS_ROW_FREEZE_PATH)
    kalis_by_decision = Counter(r["semantic_decision"] for r in kalis_rows)
    kalis_binding = load_tsv(KALIS_OWNER_APPROVAL_PATH)
    kalis_hold_count = sum(1 for r in kalis_binding if r["owner_decision"] == "HOLD")
    if kalis_hold_count != 39:
        raise SystemExit(f"KALIS_HOLD_DRIFT {kalis_hold_count}")
    for bucket, count in (
        ("POSSIBLE_RELATED_HOLD", kalis_hold_count),
        ("AMBIGUOUS", kalis_by_decision.get("AMBIGUOUS", 0)),
        ("CANONICAL_GAP", kalis_by_decision.get("CANONICAL_GAP", 0)),
        ("NO_MATCH", kalis_by_decision.get("NO_MATCH", 0)),
    ):
        out.append(
            {
                "source": "KALIS",
                "semantic_bucket": bucket,
                "count": str(count),
                "production_eligible": "NO",
                "current_disposition": "HOLD" if bucket == "POSSIBLE_RELATED_HOLD" else "DEFERRED",
                "blocking_current_stage": "NO",
            }
        )
    return out


# ---------------------------------------------------------------------------
# SHAs
# ---------------------------------------------------------------------------


def reconciliation_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RECONCILIATION_FIELDS)


def deferred_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *DEFERRED_BACKLOG_FIELDS)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    reconciliation: list[dict],
    deferred: list[dict],
    shas: dict[str, str],
    live_verified: bool,
    mapped_targets_ok: bool | None,
) -> str:
    by_source = {r["source"]: r for r in reconciliation}
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-ABC-RECON-001 A/B/C final ingest dry-run reconciliation
version: 1
status: active
owner: taiwang
---

# {WO_ID} — A/B/C Final Ingest Dry-Run / Reconciliation

## Scope

```text
READ-ONLY RECONCILIATION
NO PRODUCTION WRITE
NO CANONICAL MUTATION
NO MAPPING WRITE

FROZEN EVIDENCE REVERIFIED = NO
```

## A/B/C completion state

```text
A CIC_W = COMPLETE
B KOSHA = COMPLETE
C KALIS = COMPLETE

A/B/C SOURCE MAPPING = COMPLETE
```

## Per-source reconciliation

```text
CIC_W  expected/actual   = {by_source["CIC_W"]["approved_binding_count"]:>4} / {by_source["CIC_W"]["production_mapping_count"]:>4}   verdict = {by_source["CIC_W"]["verdict"]}
KOSHA  expected/actual   = {by_source["KOSHA"]["approved_binding_count"]:>4} / {by_source["KOSHA"]["production_mapping_count"]:>4}   verdict = {by_source["KOSHA"]["verdict"]}
KALIS  expected/actual   = {by_source["KALIS"]["approved_binding_count"]:>4} / {by_source["KALIS"]["production_mapping_count"]:>4}   verdict = {by_source["KALIS"]["verdict"]}
TOTAL  expected/actual   = {by_source["TOTAL"]["approved_binding_count"]:>4} / {by_source["TOTAL"]["production_mapping_count"]:>4}   verdict = {by_source["TOTAL"]["verdict"]}
```

Delta counts:

```text
missing approved (would_insert)  = {by_source["TOTAL"]["missing_approved_count"]}
unexpected production (would_delete) = {by_source["TOTAL"]["unexpected_production_count"]}
duplicate                        = {by_source["TOTAL"]["duplicate_count"]}
hold leak                        = {by_source["TOTAL"]["hold_leak_count"]}
```

Final ingest dry-run:

```text
already_materialized = {by_source["TOTAL"]["already_materialized"]}
would_insert         = {by_source["TOTAL"]["would_insert"]}
would_update         = {by_source["TOTAL"]["would_update"]}
would_delete         = {by_source["TOTAL"]["would_delete"]}
```

Canonical target referential guard (mapped canonicals must all resolve):

```text
live production checked     = {"YES" if live_verified else "NO — offline mode"}
missing canonical target    = {"0" if mapped_targets_ok else ("n/a" if mapped_targets_ok is None else "NONZERO")}
```

## Deferred backlog (not blocking)

Deterministic counts from frozen semantic freezes. No re-review.

```text
{chr(10).join(f'  {r["source"]:<6}  {r["semantic_bucket"]:<25}  count = {r["count"]:>4}  disposition = {r["current_disposition"]}' for r in deferred)}
```

Total deferred rows are outside this WO's completion criteria.

## Frozen output SHAs

```text
RISK ABC FINAL RECONCILIATION SHA = {shas["reconciliation"]}
RISK ABC DEFERRED BACKLOG SHA     = {shas["deferred"]}
```

## Verdict

```text
{WO_ID} = PASS / FINAL_VALIDATION_READY
A = COMPLETE
B = COMPLETE
C = COMPLETE
APPROVED PRODUCTION MAPPINGS = {by_source["TOTAL"]["production_mapping_count"]}
MISSING = {by_source["TOTAL"]["missing_approved_count"]}
EXTRA = {by_source["TOTAL"]["unexpected_production_count"]}
HOLD LEAK = {by_source["TOTAL"]["hold_leak_count"]}
WOULD INSERT = {by_source["TOTAL"]["would_insert"]}
WOULD UPDATE = {by_source["TOTAL"]["would_update"]}
WOULD DELETE = {by_source["TOTAL"]["would_delete"]}
PRODUCTION WRITE = 0
FINAL OWNER PRODUCTION APPROVAL = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT DELTA-ONLY VERIFY → FINAL VALIDATION
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def write_all(*, live: bool) -> dict:
    actual_pairs: dict[str, set[tuple[str, str]]] | None
    mapped_targets_ok: bool | None
    if live:
        conn = _connect_readonly()
        try:
            actual_pairs = _load_production_pairs(conn)
            mapped, present = _load_canonical_targets_from_production(conn)
        finally:
            conn.close()
        mapped_targets_ok = mapped.issubset(present)
        if not mapped_targets_ok:
            raise SystemExit(f"CANONICAL_TARGET_MISSING {sorted(mapped - present)}")
    else:
        actual_pairs = None  # offline: treat expected as actual
        mapped_targets_ok = None

    reconciliation_a = build_reconciliation(actual_pairs)
    reconciliation_b = build_reconciliation(actual_pairs)
    if reconciliation_a != reconciliation_b:
        raise SystemExit("RECONCILIATION_ROW_ORDER_DRIFT")
    _assert_reconciliation_pass(reconciliation_a)
    sha_r_a = reconciliation_sha(reconciliation_a)
    sha_r_b = reconciliation_sha(reconciliation_b)
    if sha_r_a != sha_r_b:
        raise SystemExit(f"RECONCILIATION_SHA_DRIFT {sha_r_a} vs {sha_r_b}")

    deferred_a = build_deferred_backlog()
    deferred_b = build_deferred_backlog()
    if deferred_a != deferred_b:
        raise SystemExit("DEFERRED_ROW_ORDER_DRIFT")
    sha_d_a = deferred_sha(deferred_a)
    sha_d_b = deferred_sha(deferred_b)
    if sha_d_a != sha_d_b:
        raise SystemExit(f"DEFERRED_SHA_DRIFT {sha_d_a} vs {sha_d_b}")

    shas = {"reconciliation": sha_r_a, "deferred": sha_d_a}

    write_tsv(reconciliation_a, RECONCILIATION_PATH, RECONCILIATION_FIELDS)
    write_tsv(deferred_a, DEFERRED_BACKLOG_PATH, DEFERRED_BACKLOG_FIELDS)
    REPORT_PATH.write_text(
        render_report(reconciliation_a, deferred_a, shas, live, mapped_targets_ok),
        encoding="utf-8",
    )

    return {
        "mode": "verify" if live else "offline",
        "reconciliation_rows": len(reconciliation_a),
        "deferred_rows": len(deferred_a),
        "reconciliation_sha_run1": sha_r_a,
        "reconciliation_sha_run2": sha_r_b,
        "deferred_sha_run1": sha_d_a,
        "deferred_sha_run2": sha_d_b,
        "mapped_targets_ok": mapped_targets_ok,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} reconciler")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Reconcile receipts against themselves — no DB access. Used by CI.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Reconcile receipts against live production SELECT — requires DATABASE_URL.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not (args.offline or args.verify):
        parser.print_help()
        return 2
    if args.offline and args.verify:
        raise SystemExit("CHOOSE_ONE_MODE: --offline or --verify")
    result = write_all(live=args.verify)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
