"""WO-RISK-KALIS-MATERIALIZE-001 KALIS approved mappings → production.

Row-level authority is the frozen Owner approval binding
(RISK_KALIS_OWNER_APPROVAL_v1.tsv, SHA ac75691c...4f03e). This tool
filters to the 9 APPROVE rows and INSERTs them into
`public.risk_source_mappings` inside a single transaction under
`LOCK TABLE public.risk_source_mappings IN EXCLUSIVE MODE`, verifies
them in-transaction, then commits. Same CIC_W / KOSHA row-shape
conventions.

Scope: source_id = KALIS_RISK_PROFILE only. CIC_W 1139 + KOSHA 46
rows untouched. Canonical / sector / KALIS canonical mutation = 0.
HOLD rows (39) never enter the execute set.

CLI:
  python -m tools.risk_map.kalis_materialize_approved --preflight
  python -m tools.risk_map.kalis_materialize_approved --dry-run
  python -m tools.risk_map.kalis_materialize_approved --execute
  python -m tools.risk_map.kalis_materialize_approved --verify
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
from tools.risk_map.kalis_owner_approval import (
    APPROVAL_ID,
    APPROVE_FAMILY_NAME,
    APPROVE_TARGET_CANONICAL_ID,
    APPROVE_TARGET_CANONICAL_NAME,
    OWNER_APPROVAL_DATE,
    OWNER_APPROVAL_FIELDS,
    OWNER_APPROVAL_PATH,
    owner_approval_sha,
)

WO_ID = "WO-RISK-KALIS-MATERIALIZE-001"
MATERIALIZATION_ID = "RISK-KALIS-MAP-MATERIALIZE-001"

FROZEN_OWNER_APPROVAL_SHA = (
    "ac75691caef78a44fa4036ab81435549f1f4d93f1a28a026c4b0f1602e34f03e"
)

KALIS_SOURCE_ID = "KALIS_RISK_PROFILE"

EXPECTED_TOTAL_BINDING = 48
EXPECTED_APPROVED = 9
EXPECTED_HOLD = 39

# Baseline production counts before this WO (delta-only guard).
BASELINE_MAPPING_TOTAL = 1185       # CIC_W 1139 + KOSHA 46
BASELINE_CIC_W = 1139
BASELINE_KOSHA = 46
BASELINE_KALIS = 0
POST_MAPPING_TOTAL = BASELINE_MAPPING_TOTAL + EXPECTED_APPROVED  # 1194

RECEIPT_PATH = Path("docs/knowledge/risk/RISK_KALIS_MATERIALIZATION_RECEIPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/RISK_KALIS_MATERIALIZATION_RECEIPT_v1.md")

RECEIPT_FIELDS: tuple[str, ...] = (
    "materialization_id",
    "owner_approval_id",
    "review_key",
    "source_id",
    "source_key",
    "canonical_id",
    "canonical_name",
    "mapping_type",
    "mapping_status",
    "mapping_method",
    "owner_approval_binding_sha",
    "production_verified",
)


# ---------------------------------------------------------------------------
# Repository anchors
# ---------------------------------------------------------------------------


def _verify_repository_anchors() -> dict:
    rows = load_tsv(OWNER_APPROVAL_PATH)
    if len(rows) != EXPECTED_TOTAL_BINDING:
        raise SystemExit(f"OWNER_BINDING_ROW_DRIFT {len(rows)}")
    got = owner_approval_sha(rows)
    if got != FROZEN_OWNER_APPROVAL_SHA:
        raise SystemExit(f"OWNER_APPROVAL_SHA_DRIFT {got}")
    if list(rows[0].keys()) != list(OWNER_APPROVAL_FIELDS):
        raise SystemExit("OWNER_BINDING_FIELD_DRIFT")

    decisions = Counter(r["owner_decision"] for r in rows)
    if decisions != Counter({"APPROVE": EXPECTED_APPROVED, "HOLD": EXPECTED_HOLD}):
        raise SystemExit(f"OWNER_DECISION_CENSUS_DRIFT {dict(decisions)}")

    approved = [r for r in rows if r["owner_decision"] == "APPROVE"]
    hold = [r for r in rows if r["owner_decision"] == "HOLD"]

    if len(approved) != EXPECTED_APPROVED:
        raise SystemExit(f"APPROVED_COUNT_DRIFT {len(approved)}")
    if len(hold) != EXPECTED_HOLD:
        raise SystemExit(f"HOLD_COUNT_DRIFT {len(hold)}")

    if {r["name_normalized"] for r in approved} != {APPROVE_FAMILY_NAME}:
        raise SystemExit("APPROVE_FAMILY_UNEXPECTED")
    if {r["mapping_type"] for r in approved} != {"NARROWER_THAN"}:
        raise SystemExit("APPROVE_MAPPING_TYPE_DRIFT")
    if {r["target_canonical_id"] for r in approved} != {APPROVE_TARGET_CANONICAL_ID}:
        raise SystemExit("APPROVE_TARGET_DRIFT")
    if len({r["source_key"] for r in approved}) != EXPECTED_APPROVED:
        raise SystemExit("APPROVED_SOURCE_KEY_NOT_UNIQUE")

    hold_keys = {r["source_key"] for r in hold}
    approved_keys = {r["source_key"] for r in approved}
    if hold_keys & approved_keys:
        raise SystemExit("HOLD_LEAKED_INTO_APPROVED_SET")

    return {
        "binding": rows,
        "approved": sorted(approved, key=lambda r: r["review_key"]),
        "hold": hold,
        "owner_approval_binding_sha": FROZEN_OWNER_APPROVAL_SHA,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _require_database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("BLOCKED: DATABASE_URL not set")
    return url


def _connect_autocommit(readonly: bool = False):
    import psycopg2

    conn = psycopg2.connect(_require_database_url())
    conn.autocommit = True
    if readonly:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
    return conn


def _connect_txn():
    import psycopg2

    return psycopg2.connect(_require_database_url())


def _fetch_scalar(cur, sql: str, params: tuple = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _fetch_rows(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _preflight_db(conn, anchors: dict) -> dict:
    approved = anchors["approved"]
    hold = anchors["hold"]

    with conn.cursor() as cur:
        total = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        kalis = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            (KALIS_SOURCE_ID,),
        )
        cic_w = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("CIC_W",),
        )
        kosha = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("KOSHA_CONSTRUCTION_PROCESS",),
        )

    if total != BASELINE_MAPPING_TOTAL:
        raise SystemExit(f"MAPPING_BASELINE_DRIFT {total}")
    if kalis != BASELINE_KALIS:
        raise SystemExit(f"UNEXPECTED_EXISTING_KALIS_MAPPING {kalis}")
    if cic_w != BASELINE_CIC_W:
        raise SystemExit(f"CIC_W_BASELINE_DRIFT {cic_w}")
    if kosha != BASELINE_KOSHA:
        raise SystemExit(f"KOSHA_BASELINE_DRIFT {kosha}")

    # Guard B: target canonical exists as DRAFT TASK.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, node_kind, name FROM public.risk_canonical_nodes "
            "WHERE id::text = %s",
            (APPROVE_TARGET_CANONICAL_ID,),
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"CANONICAL_TARGET_MISSING {APPROVE_TARGET_CANONICAL_ID}")
    status, node_kind, name = row
    if status != "DRAFT":
        raise SystemExit(f"CANONICAL_TARGET_STATUS_DRIFT {status}")
    if node_kind != "TASK":
        raise SystemExit(f"CANONICAL_TARGET_KIND_DRIFT {node_kind}")
    if name != APPROVE_TARGET_CANONICAL_NAME:
        raise SystemExit(f"CANONICAL_TARGET_NAME_DRIFT {name}")

    # Guard C: all 9 approved source_keys exist in KALIS source_nodes.
    approved_source_keys = sorted({r["source_key"] for r in approved})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_key FROM public.risk_source_nodes "
            "WHERE source_id = %s AND source_key = ANY(%s)",
            (KALIS_SOURCE_ID, approved_source_keys),
        )
        found = {r[0] for r in cur.fetchall()}
    missing = set(approved_source_keys) - found
    if missing:
        raise SystemExit(f"MISSING_KALIS_SOURCE_NODES {len(missing)}")

    # HOLD source_keys must not already be in production KALIS mappings.
    hold_keys = sorted({r["source_key"] for r in hold})
    if hold_keys:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.risk_source_mappings "
                "WHERE source_id = %s AND source_key = ANY(%s)",
                (KALIS_SOURCE_ID, hold_keys),
            )
            hold_present = cur.fetchone()[0]
        if hold_present:
            raise SystemExit(f"HOLD_ROWS_PRESENT_IN_PROD {hold_present}")

    return {
        "mappings_before": total,
        "kalis_before": kalis,
        "cic_w_before": cic_w,
        "kosha_before": kosha,
        "kalis_source_key_matches": len(found),
        "canonical_target_status": status,
        "canonical_target_kind": node_kind,
        "would_insert": EXPECTED_APPROVED,
        "hold_excluded": EXPECTED_HOLD,
    }


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def _row_to_db_tuple(row: dict, anchors: dict) -> tuple:
    evidence = {
        "evidence_basis": "OWNER_APPROVED_SEMANTIC_MAPPING",
        "review_key": row["review_key"],
        "source_name": row["name_raw"],
        "source_path": row["path_raw"],
        "canonical_name": row["target_canonical_name"],
        "work_big": row["work_big"],
        "work_mid": row["work_mid"],
        "family_name": row["name_normalized"],
        "review_authority": "GPT",
    }
    metadata = {
        "materialization_id": MATERIALIZATION_ID,
        "owner_approval_id": APPROVAL_ID,
        "owner_approval_binding_sha": anchors["owner_approval_binding_sha"],
        "owner_approval_date": OWNER_APPROVAL_DATE,
        "owner_decision": row["owner_decision"],
    }
    return (
        KALIS_SOURCE_ID,
        row["source_key"],
        row["target_canonical_id"],
        row["mapping_type"],
        "APPROVED",
        "MANUAL_REVIEW",
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )


def execute_materialization(anchors: dict) -> dict:
    from psycopg2.extras import execute_values

    approved = anchors["approved"]
    tuples = [_row_to_db_tuple(r, anchors) for r in approved]

    conn = _connect_txn()
    inserted = 0
    verified = 0
    try:
        with conn.cursor() as cur:
            baseline = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_source_mappings"
            )
            kalis_baseline = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                (KALIS_SOURCE_ID,),
            )
        if baseline != BASELINE_MAPPING_TOTAL:
            raise SystemExit(f"CONCURRENT_MAPPING_BASELINE {baseline}")
        if kalis_baseline != BASELINE_KALIS:
            raise SystemExit(f"CONCURRENT_KALIS_BASELINE {kalis_baseline}")

        with conn.cursor() as cur:
            cur.execute("LOCK TABLE public.risk_source_mappings IN EXCLUSIVE MODE")

        with conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO public.risk_source_mappings ("
                "source_id, source_key, canonical_id, mapping_type, "
                "mapping_status, mapping_method, evidence, metadata"
                ") VALUES %s",
                tuples,
                template="(%s, %s, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb)",
                page_size=100,
            )
        inserted = len(tuples)

        with conn.cursor() as cur:
            total_after = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_source_mappings"
            )
            kalis_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                (KALIS_SOURCE_ID,),
            )
            cic_w_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                ("CIC_W",),
            )
            kosha_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                ("KOSHA_CONSTRUCTION_PROCESS",),
            )
        if total_after != POST_MAPPING_TOTAL:
            raise SystemExit(f"IN_TXN_TOTAL_DRIFT {total_after}")
        if kalis_after != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_KALIS_DRIFT {kalis_after}")
        if cic_w_after != BASELINE_CIC_W:
            raise SystemExit(f"IN_TXN_CIC_W_DRIFT {cic_w_after}")
        if kosha_after != BASELINE_KOSHA:
            raise SystemExit(f"IN_TXN_KOSHA_DRIFT {kosha_after}")

        with conn.cursor() as cur:
            db_rows = _fetch_rows(
                cur,
                "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
                "mapping_type, mapping_status, mapping_method, evidence, metadata "
                "FROM public.risk_source_mappings WHERE source_id = %s",
                (KALIS_SOURCE_ID,),
            )
        if len(db_rows) != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_KALIS_ROW_COUNT_DRIFT {len(db_rows)}")

        by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
        for target in approved:
            key = (KALIS_SOURCE_ID, target["source_key"])
            db_row = by_key.get(key)
            if db_row is None:
                raise SystemExit(f"IN_TXN_ROW_MISSING {key}")
            if db_row["canonical_id"] != target["target_canonical_id"]:
                raise SystemExit(f"IN_TXN_CANONICAL_MISMATCH {key}")
            if db_row["mapping_type"] != "NARROWER_THAN":
                raise SystemExit(f"IN_TXN_TYPE_MISMATCH {key}")
            if db_row["mapping_status"] != "APPROVED":
                raise SystemExit(f"IN_TXN_STATUS_MISMATCH {key}")
            if db_row["mapping_method"] != "MANUAL_REVIEW":
                raise SystemExit(f"IN_TXN_METHOD_MISMATCH {key}")
            ev = db_row["evidence"] if isinstance(db_row["evidence"], dict) else json.loads(db_row["evidence"])
            if ev.get("evidence_basis") != "OWNER_APPROVED_SEMANTIC_MAPPING":
                raise SystemExit(f"IN_TXN_EVIDENCE_BASIS_MISMATCH {key}")
            if ev.get("review_key") != target["review_key"]:
                raise SystemExit(f"IN_TXN_REVIEW_KEY_MISMATCH {key}")
            md = db_row["metadata"] if isinstance(db_row["metadata"], dict) else json.loads(db_row["metadata"])
            if md.get("owner_approval_binding_sha") != anchors["owner_approval_binding_sha"]:
                raise SystemExit(f"IN_TXN_BINDING_SHA_MISMATCH {key}")
            verified += 1

        if verified != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_VERIFIED_DRIFT {verified}")

        # Canonical / sector / ACTIVE invariants inside the transaction.
        with conn.cursor() as cur:
            can_total = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_canonical_nodes"
            )
            can_active = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'",
            )
            sectors = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
            )
        if can_total != 1110:
            raise SystemExit(f"IN_TXN_CANONICAL_TOTAL_DRIFT {can_total}")
        if can_active != 0:
            raise SystemExit(f"IN_TXN_CANONICAL_ACTIVE_DRIFT {can_active}")
        if sectors != 0:
            raise SystemExit(f"IN_TXN_SECTOR_DRIFT {sectors}")

        conn.commit()
        return {"inserted": inserted, "verified": verified, "transaction": "COMMITTED"}
    except SystemExit:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Verify + receipt
# ---------------------------------------------------------------------------


def _verify_production(conn, anchors: dict) -> dict:
    approved = anchors["approved"]

    with conn.cursor() as cur:
        total = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        cic_w = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("CIC_W",),
        )
        kosha = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("KOSHA_CONSTRUCTION_PROCESS",),
        )
        kalis = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            (KALIS_SOURCE_ID,),
        )
        kalis_narrower = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_type = 'NARROWER_THAN'",
            (KALIS_SOURCE_ID,),
        )
        kalis_approved = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_status = 'APPROVED'",
            (KALIS_SOURCE_ID,),
        )
        kalis_manual = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_method = 'MANUAL_REVIEW'",
            (KALIS_SOURCE_ID,),
        )
        distinct_targets = _fetch_scalar(
            cur,
            "SELECT count(DISTINCT canonical_id) FROM public.risk_source_mappings "
            "WHERE source_id = %s",
            (KALIS_SOURCE_ID,),
        )
        hold_source_keys = sorted({r["source_key"] for r in anchors["hold"]})
        hold_present = 0
        if hold_source_keys:
            hold_present = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings "
                "WHERE source_id = %s AND source_key = ANY(%s)",
                (KALIS_SOURCE_ID, hold_source_keys),
            )
        db_rows = _fetch_rows(
            cur,
            "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
            "mapping_type, mapping_status, mapping_method "
            "FROM public.risk_source_mappings WHERE source_id = %s",
            (KALIS_SOURCE_ID,),
        )
        can_total = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_canonical_nodes")
        can_active = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'",
        )
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )

    if total != POST_MAPPING_TOTAL:
        raise SystemExit(f"POST_TOTAL_DRIFT {total}")
    if cic_w != BASELINE_CIC_W:
        raise SystemExit(f"POST_CIC_W_DRIFT {cic_w}")
    if kosha != BASELINE_KOSHA:
        raise SystemExit(f"POST_KOSHA_DRIFT {kosha}")
    if kalis != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KALIS_DRIFT {kalis}")
    if kalis_narrower != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KALIS_NARROWER_DRIFT {kalis_narrower}")
    if kalis_approved != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KALIS_APPROVED_DRIFT {kalis_approved}")
    if kalis_manual != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KALIS_METHOD_DRIFT {kalis_manual}")
    if distinct_targets != 1:
        raise SystemExit(f"POST_KALIS_DISTINCT_TARGET_DRIFT {distinct_targets}")
    if hold_present:
        raise SystemExit(f"POST_HOLD_LEAKED {hold_present}")
    if can_total != 1110:
        raise SystemExit(f"POST_CANONICAL_TOTAL_DRIFT {can_total}")
    if can_active != 0:
        raise SystemExit(f"POST_CANONICAL_ACTIVE_DRIFT {can_active}")
    if sectors != 0:
        raise SystemExit(f"POST_SECTOR_DRIFT {sectors}")

    by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
    row_matches = 0
    for target in approved:
        key = (KALIS_SOURCE_ID, target["source_key"])
        db_row = by_key.get(key)
        if db_row is None:
            raise SystemExit(f"POST_ROW_MISSING {key}")
        if db_row["canonical_id"] != target["target_canonical_id"]:
            raise SystemExit(f"POST_CANONICAL_MISMATCH {key}")
        row_matches += 1

    return {
        "mappings_after": total,
        "cic_w_after": cic_w,
        "kosha_after": kosha,
        "kalis_after": kalis,
        "kalis_narrower": kalis_narrower,
        "kalis_approved": kalis_approved,
        "kalis_manual": kalis_manual,
        "kalis_distinct_targets": distinct_targets,
        "hold_leaked": hold_present,
        "canonical_total": can_total,
        "canonical_active": can_active,
        "sectors": sectors,
        "row_matches": row_matches,
    }


def _write_receipt(anchors: dict) -> str:
    rows = [
        {
            "materialization_id": MATERIALIZATION_ID,
            "owner_approval_id": APPROVAL_ID,
            "review_key": r["review_key"],
            "source_id": KALIS_SOURCE_ID,
            "source_key": r["source_key"],
            "canonical_id": r["target_canonical_id"],
            "canonical_name": r["target_canonical_name"],
            "mapping_type": "NARROWER_THAN",
            "mapping_status": "APPROVED",
            "mapping_method": "MANUAL_REVIEW",
            "owner_approval_binding_sha": anchors["owner_approval_binding_sha"],
            "production_verified": "YES",
        }
        for r in anchors["approved"]
    ]
    rows.sort(key=lambda r: (r["source_key"], r["canonical_id"]))
    write_tsv(rows, RECEIPT_PATH, RECEIPT_FIELDS)
    return universe_sha(rows, *RECEIPT_FIELDS)


def _write_report(anchors: dict, audit: dict, receipt_sha: str) -> None:
    body = f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MATERIALIZE-001 KALIS production mapping materialization
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KALIS Owner-Approved Source Mapping Materialization

Owner-approved KALIS source→canonical mapping package has been
materialized to production `risk_source_mappings`. 9 rows inserted
(all NARROWER_THAN → 발파굴착). 39 HOLD rows (POSSIBLE_RELATED:
용접작업 / 양생작업 / 인발작업) remained HOLD and were not written.
No canonical mutation, no sector write, no ACTIVE transition.

## Anchors

```text
owner approval id             = {APPROVAL_ID}
owner approval date           = {OWNER_APPROVAL_DATE}
owner approval binding SHA    = {anchors["owner_approval_binding_sha"]}
approved family               = {APPROVE_FAMILY_NAME}
approved target               = {APPROVE_TARGET_CANONICAL_ID}  {APPROVE_TARGET_CANONICAL_NAME}
```

## Production result

```text
mappings_before               = {BASELINE_MAPPING_TOTAL}
mappings_after                = {audit["mappings_after"]}
CIC_W (unchanged)             = {audit["cic_w_after"]}
KOSHA (unchanged)             = {audit["kosha_after"]}
KALIS (new)                   = {audit["kalis_after"]}

KALIS NARROWER_THAN           = {audit["kalis_narrower"]}
KALIS mapping_status APPROVED = {audit["kalis_approved"]}
KALIS mapping_method MANUAL   = {audit["kalis_manual"]}
KALIS distinct canonical      = {audit["kalis_distinct_targets"]}
HOLD leaked into production   = {audit["hold_leaked"]}

canonical_nodes total         = {audit["canonical_total"]}
canonical_nodes ACTIVE        = {audit["canonical_active"]}
risk_canonical_node_sectors   = {audit["sectors"]}
```

## Owner approval accounting

```text
APPROVED (input)              = {EXPECTED_APPROVED}
INSERTED                      = {audit["kalis_after"]}
HOLD (excluded)               = {EXPECTED_HOLD}
REJECTED                      = 0

CANONICAL MUTATION            = 0
SECTOR WRITE                  = 0
ACTIVE TRANSITION             = 0
NEW CANONICAL                 = 0
```

## Receipt

```text
RISK KALIS MATERIALIZATION RECEIPT SHA = {receipt_sha}
receipt file                            = {RECEIPT_PATH}
```

## Reused frozen evidence (not reverified)

```text
PR #362 / #363 / #364 / #366 / #374 = MERGED
CIC_W production mappings           = 1139 (unchanged)
KOSHA production mappings           =   46 (unchanged)
```

## Verdict

```text
{WO_ID} = PASS / PRODUCTION_MATERIALIZED / GPT_MERGE_REVIEW_READY
MERGE = NOT AUTHORIZED (GPT verify first)
NEXT  = GPT DELTA-ONLY VERIFY → PR #376 MERGE
STOP
```
"""
    REPORT_PATH.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(tag: str, payload: dict) -> None:
    print(f"[{tag}] " + json.dumps(payload, ensure_ascii=True, sort_keys=True))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} executor")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not any([args.preflight, args.dry_run, args.execute, args.verify]):
        parser.print_help()
        return 2

    anchors = _verify_repository_anchors()
    _emit(
        "anchors",
        {
            "binding_sha": anchors["owner_approval_binding_sha"],
            "approved_rows": len(anchors["approved"]),
            "hold_rows": len(anchors["hold"]),
        },
    )

    # Idempotency short-circuit — if production already has the exact 9
    # KALIS rows, --execute is a no-op and --preflight would drift on the
    # pre-write baseline. Both --preflight and --execute honor this.
    if args.preflight or args.execute:
        conn = _connect_autocommit(readonly=True)
        try:
            with conn.cursor() as cur:
                kalis_now = _fetch_scalar(
                    cur,
                    "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                    (KALIS_SOURCE_ID,),
                )
        finally:
            conn.close()
        if kalis_now == EXPECTED_APPROVED:
            _emit("already_materialized", {"kalis": kalis_now})
            if args.execute:
                # Skip preflight (post-write baseline differs) and skip execute.
                pass
        elif kalis_now != 0:
            raise SystemExit(
                f"UNEXPECTED_PARTIAL_KALIS_MAPPINGS {kalis_now} — refuse to auto-heal"
            )
        else:
            conn = _connect_autocommit(readonly=True)
            try:
                pre = _preflight_db(conn, anchors)
            finally:
                conn.close()
            _emit("preflight", pre)
            if args.execute:
                result = execute_materialization(anchors)
                _emit("execute", result)

    if args.dry_run:
        # Dry-run always runs preflight to prove the plan is safe.
        conn = _connect_autocommit(readonly=True)
        try:
            with conn.cursor() as cur:
                kalis_now = _fetch_scalar(
                    cur,
                    "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                    (KALIS_SOURCE_ID,),
                )
        finally:
            conn.close()
        if kalis_now == 0:
            conn = _connect_autocommit(readonly=True)
            try:
                pre = _preflight_db(conn, anchors)
            finally:
                conn.close()
            _emit("dry_run_preflight", pre)
            _emit(
                "dry_run",
                {
                    "binding_sha": "MATCH",
                    "would_insert": EXPECTED_APPROVED,
                    "hold_excluded": EXPECTED_HOLD,
                    "production_writes": 0,
                },
            )
        elif kalis_now == EXPECTED_APPROVED:
            _emit(
                "dry_run",
                {
                    "binding_sha": "MATCH",
                    "state": "ALREADY_MATERIALIZED",
                    "would_insert": 0,
                    "hold_excluded": EXPECTED_HOLD,
                    "production_writes": 0,
                },
            )
        else:
            raise SystemExit(
                f"UNEXPECTED_PARTIAL_KALIS_MAPPINGS {kalis_now}"
            )

    if args.verify:
        conn = _connect_autocommit(readonly=True)
        try:
            audit = _verify_production(conn, anchors)
        finally:
            conn.close()
        receipt_sha = _write_receipt(anchors)
        _write_report(anchors, audit, receipt_sha)
        audit["receipt_sha"] = receipt_sha
        _emit("verify", audit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
