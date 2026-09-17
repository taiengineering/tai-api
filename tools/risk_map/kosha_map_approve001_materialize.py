"""WO-RISK-KOSHA-MAP-MATERIALIZE-001 KOSHA approved mappings → production.

Row-level authority is the frozen owner-approval binding
(RISK_KOSHA_MAP_APPROVE001_OWNER_APPROVAL_BINDING_v1.tsv, SHA
3c2f0a0f...7a91). This tool does not re-derive semantic identity; it
filters the binding to the 46 APPROVED rows (6 EXACT + 40 NARROWER),
INSERTs them into `public.risk_source_mappings` inside a single
transaction under a table lock, verifies them in-transaction, then
commits. Existing CIC_W row shape / method / status conventions are
reused verbatim.

Scope: source_id = KOSHA_CONSTRUCTION_PROCESS only. CIC_W's existing
1139 rows are not touched. Canonical / sector / KALIS / new-canonical
mutation = 0. Migration / schema unchanged.

CLI:
  python -m tools.risk_map.kosha_map_approve001_materialize --preflight
  python -m tools.risk_map.kosha_map_approve001_materialize --dry-run
  python -m tools.risk_map.kosha_map_approve001_materialize --execute
  python -m tools.risk_map.kosha_map_approve001_materialize --verify

Defaults: no writes. `--execute` is required to touch production.
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
from tools.risk_map.kosha_map_approve001_owner_approval import (
    APPROVAL_ID,
    BINDING_FIELDS,
    BINDING_PATH,
    DECISION_APPROVE,
    DECISION_HOLD,
    FROZEN_MAPPING_CANDIDATES_SHA,
    binding_sha,
)

WO_ID = "WO-RISK-KOSHA-MAP-MATERIALIZE-001"
MATERIALIZATION_ID = "RISK-KOSHA-MAP-MATERIALIZE-001"

FROZEN_OWNER_APPROVAL_BINDING_SHA = (
    "3c2f0a0f3558a7e0fd7a0d801ed22d18ba3d7fbed3f86a3ca54aa022f2e87a91"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_SOURCE_INGEST_RECEIPT_SHA = (
    "9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4"
)
FROZEN_CANONICAL_RECEIPT_SHA = (
    "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
)

KOSHA_SOURCE_ID = "KOSHA_CONSTRUCTION_PROCESS"

EXPECTED_BINDING_ROWS = 75
EXPECTED_APPROVED = 46
EXPECTED_HOLD = 29
EXPECTED_EXACT = 6
EXPECTED_NARROWER = 40

# Baseline counts in production before this WO (WO §7).
BASELINE_MAPPING_TOTAL = 1139
BASELINE_CIC_W = 1139
BASELINE_KOSHA = 0
BASELINE_KALIS = 0
BASELINE_CANONICAL = 1110
BASELINE_CANONICAL_DRAFT = 1110
BASELINE_CANONICAL_ACTIVE = 0
BASELINE_SECTORS = 0

# Post-write expected counts (WO §11).
POST_MAPPING_TOTAL = BASELINE_MAPPING_TOTAL + EXPECTED_APPROVED  # 1185

RECEIPT_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_MAP_MATERIALIZE001_RECEIPT_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-map-materialize001-receipt_v1.md"
)

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
    "gpt_confidence_class",
    "owner_approval_binding_sha",
    "candidate_sot_sha",
    "production_verified",
)


# ---------------------------------------------------------------------------
# Repository-anchor verification
# ---------------------------------------------------------------------------


def _verify_repository_anchors() -> dict:
    rows = load_tsv(BINDING_PATH)
    if len(rows) != EXPECTED_BINDING_ROWS:
        raise SystemExit(f"BINDING_ROW_DRIFT {len(rows)}")
    computed_sha = binding_sha(rows)
    if computed_sha != FROZEN_OWNER_APPROVAL_BINDING_SHA:
        raise SystemExit(f"BINDING_SHA_DRIFT {computed_sha}")
    if list(rows[0].keys()) != list(BINDING_FIELDS):
        raise SystemExit("BINDING_FIELD_DRIFT")

    decisions = Counter(r["owner_decision"] for r in rows)
    if decisions.get(DECISION_APPROVE, 0) != EXPECTED_APPROVED:
        raise SystemExit(f"APPROVED_COUNT_DRIFT {decisions.get(DECISION_APPROVE)}")
    if decisions.get(DECISION_HOLD, 0) != EXPECTED_HOLD:
        raise SystemExit(f"HOLD_COUNT_DRIFT {decisions.get(DECISION_HOLD)}")

    approved_rows = [r for r in rows if r["owner_decision"] == DECISION_APPROVE]
    hold_rows = [r for r in rows if r["owner_decision"] == DECISION_HOLD]

    for r in hold_rows:
        if r["mapping_type"] != "POSSIBLE_RELATED":
            raise SystemExit(f"HOLD_TYPE_UNEXPECTED {r['review_key']}")

    mtypes = Counter(r["mapping_type"] for r in approved_rows)
    if mtypes.get("EXACT_EQUIVALENT", 0) != EXPECTED_EXACT:
        raise SystemExit(f"EXACT_APPROVED_DRIFT {mtypes.get('EXACT_EQUIVALENT')}")
    if mtypes.get("NARROWER_THAN", 0) != EXPECTED_NARROWER:
        raise SystemExit(f"NARROWER_APPROVED_DRIFT {mtypes.get('NARROWER_THAN')}")
    if mtypes.get("POSSIBLE_RELATED", 0):
        raise SystemExit("POSSIBLE_RELATED_IN_APPROVED_SET")

    # Every approved row must carry a target and its aggregate SHA must match.
    for r in approved_rows:
        if not r["target_canonical_id"]:
            raise SystemExit(f"APPROVED_TARGET_BLANK {r['review_key']}")
        if not r["target_canonical_name"]:
            raise SystemExit(f"APPROVED_TARGET_NAME_BLANK {r['review_key']}")
        if r["source_aggregate_sha"] != FROZEN_MAPPING_CANDIDATES_SHA:
            raise SystemExit(f"APPROVED_CANDIDATE_SHA_DRIFT {r['review_key']}")
        if r["approval_id"] != APPROVAL_ID:
            raise SystemExit(f"APPROVED_APPROVAL_ID_DRIFT {r['review_key']}")

    # Uniqueness on the approved set.
    approved_keys = [r["source_key"] for r in approved_rows]
    if len(set(approved_keys)) != EXPECTED_APPROVED:
        raise SystemExit("APPROVED_SOURCE_KEY_DUPLICATE")
    approved_pairs = {(r["source_key"], r["target_canonical_id"]) for r in approved_rows}
    if len(approved_pairs) != EXPECTED_APPROVED:
        raise SystemExit("APPROVED_SOURCE_CANONICAL_PAIR_DUPLICATE")

    # HOLD source_keys MUST NOT appear in approved set.
    hold_keys = {r["source_key"] for r in hold_rows}
    if hold_keys & set(approved_keys):
        raise SystemExit("HOLD_ROW_LEAKED_INTO_APPROVED_SET")

    return {
        "binding_rows": rows,
        "approved_rows": sorted(approved_rows, key=lambda r: r["review_key"]),
        "hold_rows": hold_rows,
        "owner_approval_binding_sha": FROZEN_OWNER_APPROVAL_BINDING_SHA,
        "candidate_sot_sha": FROZEN_MAPPING_CANDIDATES_SHA,
        "canonical_reference_sha": FROZEN_CANONICAL_TASK_REFERENCE_SHA,
        "source_ingest_receipt_sha": FROZEN_SOURCE_INGEST_RECEIPT_SHA,
        "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
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
# Preflight (read-only)
# ---------------------------------------------------------------------------


def _preflight_db(conn, anchors: dict) -> dict:
    approved_rows = anchors["approved_rows"]
    hold_rows = anchors["hold_rows"]

    with conn.cursor() as cur:
        mappings = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        cic_w = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("CIC_W",),
        )
        kosha = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            (KOSHA_SOURCE_ID,),
        )
        kalis = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("KALIS_RISK_PROFILE",),
        )
        canonical_total = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_nodes"
        )
        canonical_draft = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'DRAFT'",
        )
        canonical_active = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'",
        )
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )

    if mappings != BASELINE_MAPPING_TOTAL:
        raise SystemExit(f"MAPPING_BASELINE_DRIFT {mappings}")
    if cic_w != BASELINE_CIC_W:
        raise SystemExit(f"CIC_W_BASELINE_DRIFT {cic_w}")
    if kosha != BASELINE_KOSHA:
        raise SystemExit(f"UNEXPECTED_EXISTING_KOSHA_MAPPING {kosha}")
    if kalis != BASELINE_KALIS:
        raise SystemExit(f"UNEXPECTED_EXISTING_KALIS_MAPPING {kalis}")
    if canonical_total != BASELINE_CANONICAL:
        raise SystemExit(f"CANONICAL_TOTAL_DRIFT {canonical_total}")
    if canonical_draft != BASELINE_CANONICAL_DRAFT:
        raise SystemExit(f"CANONICAL_DRAFT_DRIFT {canonical_draft}")
    if canonical_active != BASELINE_CANONICAL_ACTIVE:
        raise SystemExit(f"CANONICAL_ACTIVE_DRIFT {canonical_active}")
    if sectors != BASELINE_SECTORS:
        raise SystemExit(f"SECTOR_BASELINE_DRIFT {sectors}")

    # All 46 approved source_keys must exist in production risk_source_nodes / KOSHA.
    approved_source_keys = sorted({r["source_key"] for r in approved_rows})
    if len(approved_source_keys) != EXPECTED_APPROVED:
        raise SystemExit("APPROVED_SOURCE_KEY_UNIQUENESS_DRIFT")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_key FROM public.risk_source_nodes "
            "WHERE source_id = %s AND source_key = ANY(%s)",
            (KOSHA_SOURCE_ID, approved_source_keys),
        )
        found_keys = {r[0] for r in cur.fetchall()}
    missing_keys = set(approved_source_keys) - found_keys
    if missing_keys:
        raise SystemExit(
            f"MISSING_KOSHA_SOURCE_NODES {len(missing_keys)}"
        )

    # Every approved canonical_id must exist as DRAFT TASK in production.
    approved_canonical_ids = sorted({r["target_canonical_id"] for r in approved_rows})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, status, node_kind, name "
            "FROM public.risk_canonical_nodes WHERE id::text = ANY(%s)",
            (approved_canonical_ids,),
        )
        prod_canonical = {r[0]: r for r in cur.fetchall()}
    missing_can = set(approved_canonical_ids) - set(prod_canonical)
    if missing_can:
        raise SystemExit(f"MISSING_APPROVED_CANONICAL_IDS {len(missing_can)}")
    for r in approved_rows:
        prod = prod_canonical.get(r["target_canonical_id"])
        if prod is None:
            raise SystemExit(f"CANONICAL_MISSING {r['target_canonical_id']}")
        _cid, status, node_kind, name = prod
        if status != "DRAFT":
            raise SystemExit(
                f"CANONICAL_STATUS_DRIFT {r['target_canonical_id']} {status}"
            )
        if node_kind != "TASK":
            raise SystemExit(
                f"CANONICAL_KIND_DRIFT {r['target_canonical_id']} {node_kind}"
            )
        if name != r["target_canonical_name"]:
            raise SystemExit(
                f"CANONICAL_NAME_DRIFT {r['target_canonical_id']}"
            )

    # HOLD source_keys must NOT be present in production KOSHA mappings.
    hold_source_keys = sorted({r["source_key"] for r in hold_rows})
    if hold_source_keys:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.risk_source_mappings "
                "WHERE source_id = %s AND source_key = ANY(%s)",
                (KOSHA_SOURCE_ID, hold_source_keys),
            )
            hold_present = cur.fetchone()[0]
        if hold_present:
            raise SystemExit(f"HOLD_ROWS_PRESENT_IN_PROD {hold_present}")

    return {
        "mappings_before": mappings,
        "cic_w_before": cic_w,
        "kosha_before": kosha,
        "kalis_before": kalis,
        "canonical_total": canonical_total,
        "canonical_draft": canonical_draft,
        "canonical_active": canonical_active,
        "sectors_before": sectors,
        "kosha_source_key_matches": len(found_keys),
        "approved_canonical_matches": len(prod_canonical),
        "hold_rows_present_in_prod": 0,
        "would_insert": EXPECTED_APPROVED,
        "hold_excluded": EXPECTED_HOLD,
    }


# ---------------------------------------------------------------------------
# Execute (single transaction, INSERT + in-txn verify + COMMIT)
# ---------------------------------------------------------------------------


def _row_to_db_tuple(row: dict, anchors: dict) -> tuple:
    evidence = {
        "evidence_basis": "OWNER_APPROVED_SEMANTIC_MAPPING",
        "review_key": row["review_key"],
        "source_name": row["source_name"],
        "source_path": row["source_path"],
        "canonical_name": row["target_canonical_name"],
        "project_kind": row["project_kind"],
        "work_type": row["work_type"],
        "gpt_confidence_class": row["gpt_confidence_class"],
        "review_authority": "GPT",
    }
    metadata = {
        "materialization_id": MATERIALIZATION_ID,
        "owner_approval_id": APPROVAL_ID,
        "owner_approval_binding_sha": anchors["owner_approval_binding_sha"],
        "candidate_sot_sha": anchors["candidate_sot_sha"],
        "canonical_reference_sha": anchors["canonical_reference_sha"],
        "source_ingest_receipt_sha": anchors["source_ingest_receipt_sha"],
        "canonical_receipt_sha": anchors["canonical_receipt_sha"],
        "owner_decision": row["owner_decision"],
    }
    return (
        KOSHA_SOURCE_ID,
        row["source_key"],
        row["target_canonical_id"],
        row["mapping_type"],
        "APPROVED",
        "MANUAL_REVIEW",
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )


def execute_materialization(anchors: dict) -> dict:
    """Single-transaction INSERT + in-txn exact-set verify. Commits only on PASS."""
    from psycopg2.extras import execute_values

    approved_rows = anchors["approved_rows"]
    tuples = [_row_to_db_tuple(r, anchors) for r in approved_rows]

    conn = _connect_txn()
    inserted = 0
    verified = 0
    try:
        with conn.cursor() as cur:
            baseline = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_source_mappings"
            )
            kosha_baseline = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                (KOSHA_SOURCE_ID,),
            )
        if baseline != BASELINE_MAPPING_TOTAL:
            raise SystemExit(f"CONCURRENT_MAPPING_BASELINE {baseline}")
        if kosha_baseline != BASELINE_KOSHA:
            raise SystemExit(f"CONCURRENT_KOSHA_BASELINE {kosha_baseline}")

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
                page_size=200,
            )
        inserted = len(tuples)

        with conn.cursor() as cur:
            total_after = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_source_mappings"
            )
            kosha_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                (KOSHA_SOURCE_ID,),
            )
            cic_w_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                ("CIC_W",),
            )
            kalis_after = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                ("KALIS_RISK_PROFILE",),
            )
        if total_after != POST_MAPPING_TOTAL:
            raise SystemExit(f"IN_TXN_TOTAL_DRIFT {total_after}")
        if kosha_after != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_KOSHA_DRIFT {kosha_after}")
        if cic_w_after != BASELINE_CIC_W:
            raise SystemExit(f"IN_TXN_CIC_W_DRIFT {cic_w_after}")
        if kalis_after != BASELINE_KALIS:
            raise SystemExit(f"IN_TXN_KALIS_DRIFT {kalis_after}")

        # In-transaction per-row verify for KOSHA rows only.
        with conn.cursor() as cur:
            db_rows = _fetch_rows(
                cur,
                "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
                "mapping_type, mapping_status, mapping_method, evidence, metadata "
                "FROM public.risk_source_mappings WHERE source_id = %s",
                (KOSHA_SOURCE_ID,),
            )
        if len(db_rows) != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_KOSHA_ROW_COUNT_DRIFT {len(db_rows)}")

        by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
        for target in approved_rows:
            key = (KOSHA_SOURCE_ID, target["source_key"])
            db_row = by_key.get(key)
            if db_row is None:
                raise SystemExit(f"IN_TXN_ROW_MISSING {key}")
            if db_row["canonical_id"] != target["target_canonical_id"]:
                raise SystemExit(f"IN_TXN_CANONICAL_MISMATCH {key}")
            if db_row["mapping_type"] != target["mapping_type"]:
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
            if ev.get("canonical_name") != target["target_canonical_name"]:
                raise SystemExit(f"IN_TXN_CANONICAL_NAME_MISMATCH {key}")
            md = db_row["metadata"] if isinstance(db_row["metadata"], dict) else json.loads(db_row["metadata"])
            if md.get("materialization_id") != MATERIALIZATION_ID:
                raise SystemExit(f"IN_TXN_MATERIALIZATION_ID_MISMATCH {key}")
            if md.get("owner_approval_id") != APPROVAL_ID:
                raise SystemExit(f"IN_TXN_APPROVAL_ID_MISMATCH {key}")
            if md.get("owner_approval_binding_sha") != anchors["owner_approval_binding_sha"]:
                raise SystemExit(f"IN_TXN_BINDING_SHA_MISMATCH {key}")
            verified += 1

        if verified != EXPECTED_APPROVED:
            raise SystemExit(f"IN_TXN_VERIFIED_DRIFT {verified}")

        # In-txn canonical invariants: no canonical mutation, no sector write.
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
        if can_total != BASELINE_CANONICAL:
            raise SystemExit(f"IN_TXN_CANONICAL_TOTAL_DRIFT {can_total}")
        if can_active != BASELINE_CANONICAL_ACTIVE:
            raise SystemExit(f"IN_TXN_CANONICAL_ACTIVE_DRIFT {can_active}")
        if sectors != BASELINE_SECTORS:
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
# Verify (read-only, produces receipt + report)
# ---------------------------------------------------------------------------


def _verify_production(conn, anchors: dict) -> dict:
    approved_rows = anchors["approved_rows"]

    with conn.cursor() as cur:
        mappings = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        cic_w = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("CIC_W",),
        )
        kosha = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            (KOSHA_SOURCE_ID,),
        )
        kalis = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
            ("KALIS_RISK_PROFILE",),
        )
        kosha_approved = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_status = 'APPROVED'",
            (KOSHA_SOURCE_ID,),
        )
        kosha_manual = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_method = 'MANUAL_REVIEW'",
            (KOSHA_SOURCE_ID,),
        )
        kosha_exact = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_type = 'EXACT_EQUIVALENT'",
            (KOSHA_SOURCE_ID,),
        )
        kosha_narrower = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_type = 'NARROWER_THAN'",
            (KOSHA_SOURCE_ID,),
        )
        kosha_possible = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings "
            "WHERE source_id = %s AND mapping_type = 'POSSIBLE_RELATED'",
            (KOSHA_SOURCE_ID,),
        )
        can_total = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_canonical_nodes")
        can_active = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'",
        )
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )
        hold_source_keys = sorted({r["source_key"] for r in anchors["hold_rows"]})
        hold_present = 0
        if hold_source_keys:
            hold_present = _fetch_scalar(
                cur,
                "SELECT count(*) FROM public.risk_source_mappings "
                "WHERE source_id = %s AND source_key = ANY(%s)",
                (KOSHA_SOURCE_ID, hold_source_keys),
            )
        db_rows = _fetch_rows(
            cur,
            "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
            "mapping_type, mapping_status, mapping_method, evidence, metadata "
            "FROM public.risk_source_mappings WHERE source_id = %s",
            (KOSHA_SOURCE_ID,),
        )

    if mappings != POST_MAPPING_TOTAL:
        raise SystemExit(f"POST_TOTAL_DRIFT {mappings}")
    if cic_w != BASELINE_CIC_W:
        raise SystemExit(f"POST_CIC_W_DRIFT {cic_w}")
    if kosha != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KOSHA_DRIFT {kosha}")
    if kalis != BASELINE_KALIS:
        raise SystemExit(f"POST_KALIS_DRIFT {kalis}")
    if kosha_approved != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KOSHA_APPROVED_DRIFT {kosha_approved}")
    if kosha_manual != EXPECTED_APPROVED:
        raise SystemExit(f"POST_KOSHA_METHOD_DRIFT {kosha_manual}")
    if kosha_exact != EXPECTED_EXACT:
        raise SystemExit(f"POST_KOSHA_EXACT_DRIFT {kosha_exact}")
    if kosha_narrower != EXPECTED_NARROWER:
        raise SystemExit(f"POST_KOSHA_NARROWER_DRIFT {kosha_narrower}")
    if kosha_possible != 0:
        raise SystemExit(f"POST_KOSHA_POSSIBLE_LEAK {kosha_possible}")
    if can_total != BASELINE_CANONICAL:
        raise SystemExit(f"POST_CANONICAL_TOTAL_DRIFT {can_total}")
    if can_active != BASELINE_CANONICAL_ACTIVE:
        raise SystemExit(f"POST_CANONICAL_ACTIVE_DRIFT {can_active}")
    if sectors != BASELINE_SECTORS:
        raise SystemExit(f"POST_SECTOR_DRIFT {sectors}")
    if hold_present:
        raise SystemExit(f"POST_HOLD_LEAKED {hold_present}")

    by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
    row_matches = 0
    for target in approved_rows:
        key = (KOSHA_SOURCE_ID, target["source_key"])
        db_row = by_key.get(key)
        if db_row is None:
            raise SystemExit(f"POST_ROW_MISSING {key}")
        if db_row["canonical_id"] != target["target_canonical_id"]:
            raise SystemExit(f"POST_CANONICAL_MISMATCH {key}")
        if db_row["mapping_type"] != target["mapping_type"]:
            raise SystemExit(f"POST_TYPE_MISMATCH {key}")
        if db_row["mapping_status"] != "APPROVED":
            raise SystemExit(f"POST_STATUS_MISMATCH {key}")
        ev = db_row["evidence"] if isinstance(db_row["evidence"], dict) else json.loads(db_row["evidence"])
        if ev.get("review_key") != target["review_key"]:
            raise SystemExit(f"POST_REVIEW_KEY_MISMATCH {key}")
        md = db_row["metadata"] if isinstance(db_row["metadata"], dict) else json.loads(db_row["metadata"])
        if md.get("owner_approval_binding_sha") != anchors["owner_approval_binding_sha"]:
            raise SystemExit(f"POST_BINDING_SHA_MISMATCH {key}")
        row_matches += 1

    return {
        "mappings_after": mappings,
        "cic_w_after": cic_w,
        "kosha_after": kosha,
        "kalis_after": kalis,
        "kosha_approved": kosha_approved,
        "kosha_manual": kosha_manual,
        "kosha_exact": kosha_exact,
        "kosha_narrower": kosha_narrower,
        "canonical_total": can_total,
        "canonical_active": can_active,
        "sectors_after": sectors,
        "hold_leaked": hold_present,
        "row_matches": row_matches,
    }


def _write_receipt(anchors: dict) -> str:
    rows = [
        {
            "materialization_id": MATERIALIZATION_ID,
            "owner_approval_id": APPROVAL_ID,
            "review_key": r["review_key"],
            "source_id": KOSHA_SOURCE_ID,
            "source_key": r["source_key"],
            "canonical_id": r["target_canonical_id"],
            "canonical_name": r["target_canonical_name"],
            "mapping_type": r["mapping_type"],
            "mapping_status": "APPROVED",
            "mapping_method": "MANUAL_REVIEW",
            "gpt_confidence_class": r["gpt_confidence_class"],
            "owner_approval_binding_sha": anchors["owner_approval_binding_sha"],
            "candidate_sot_sha": anchors["candidate_sot_sha"],
            "production_verified": "YES",
        }
        for r in anchors["approved_rows"]
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
title: WO-RISK-KOSHA-MAP-MATERIALIZE-001 KOSHA production mapping materialization
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA Owner-Approved Source Mapping Materialization

Owner-approved KOSHA source→canonical mapping package has been
materialized to production `risk_source_mappings`. Row-level authority:
frozen owner approval binding. 46 rows inserted (6 EXACT + 40
NARROWER). 29 POSSIBLE_RELATED rows remained HOLD and were not written.
No canonical / sector / KALIS mutation. Existing CIC_W 1139 rows
untouched.

## Anchors

```text
owner approval id             = {APPROVAL_ID}
owner approval binding SHA    = {anchors["owner_approval_binding_sha"]}
candidate SoT SHA             = {anchors["candidate_sot_sha"]}
canonical task reference SHA  = {anchors["canonical_reference_sha"]}
canonical receipt SHA         = {anchors["canonical_receipt_sha"]}
source ingest receipt SHA     = {anchors["source_ingest_receipt_sha"]}
```

## Production result

```text
mappings_before               = {BASELINE_MAPPING_TOTAL}
mappings_after                = {audit["mappings_after"]}
CIC_W (unchanged)             = {audit["cic_w_after"]}
KOSHA (new)                   = {audit["kosha_after"]}
KALIS (unchanged)             = {audit["kalis_after"]}

KOSHA mapping_status APPROVED = {audit["kosha_approved"]}
KOSHA mapping_method MANUAL   = {audit["kosha_manual"]}
KOSHA EXACT_EQUIVALENT        = {audit["kosha_exact"]}
KOSHA NARROWER_THAN           = {audit["kosha_narrower"]}
KOSHA POSSIBLE_RELATED        = 0
HOLD leaked into production   = {audit["hold_leaked"]}

canonical_nodes total         = {audit["canonical_total"]}
canonical_nodes ACTIVE        = {audit["canonical_active"]}
risk_canonical_node_sectors   = {audit["sectors_after"]}
```

## Owner approval accounting

```text
APPROVED (input)              = {EXPECTED_APPROVED}
INSERTED                      = {audit["kosha_after"]}
HOLD (excluded)               = {EXPECTED_HOLD}
REJECTED                      = 0

EXACT_EQUIVALENT approved     = {EXPECTED_EXACT}
NARROWER_THAN approved        = {EXPECTED_NARROWER}
POSSIBLE_RELATED HOLD         = {EXPECTED_HOLD}

CANONICAL MUTATION            = 0
NEW CANONICAL                 = 0
```

## Receipt

```text
RISK KOSHA MATERIALIZATION RECEIPT SHA = {receipt_sha}
receipt file                            = {RECEIPT_PATH}
```

## Verdict

```text
{WO_ID} = PASS / PRODUCTION_MATERIALIZED / EVIDENCE_READY
MERGE = NOT AUTHORIZED
NEXT  = GPT LEAN MATERIALIZATION VERIFY
THEN  = PR #374 CLOSEOUT / MERGE GATE
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
            "candidate_sot_sha": anchors["candidate_sot_sha"],
            "approved_rows": len(anchors["approved_rows"]),
            "hold_rows": len(anchors["hold_rows"]),
        },
    )

    if args.preflight or args.dry_run or args.execute:
        conn = _connect_autocommit(readonly=True)
        try:
            pre = _preflight_db(conn, anchors)
        finally:
            conn.close()
        _emit("preflight", pre)

    if args.dry_run:
        # Full simulation payload — no writes.
        _emit(
            "dry_run",
            {
                "binding_sha": "MATCH",
                "approved_rows": EXPECTED_APPROVED,
                "exact_equivalent": EXPECTED_EXACT,
                "narrower_than": EXPECTED_NARROWER,
                "hold_excluded": EXPECTED_HOLD,
                "would_insert": EXPECTED_APPROVED,
                "production_writes": 0,
            },
        )

    if args.execute:
        conn = _connect_autocommit(readonly=True)
        try:
            with conn.cursor() as cur:
                kosha_now = _fetch_scalar(
                    cur,
                    "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = %s",
                    (KOSHA_SOURCE_ID,),
                )
        finally:
            conn.close()
        if kosha_now == EXPECTED_APPROVED:
            _emit("already_materialized", {"kosha": kosha_now})
        elif kosha_now == 0:
            result = execute_materialization(anchors)
            _emit("execute", result)
        else:
            raise SystemExit(
                f"UNEXPECTED_PARTIAL_KOSHA_MAPPINGS {kosha_now} — refuse to auto-heal"
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
