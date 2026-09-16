"""WO-RISK-MAP-MATERIALIZE-001 CIC_W approved mapping → production materialization.

Row-level authority is the frozen RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv
(proposal SHA 036d293c...1f026) bound to the frozen owner approval
(binding identity SHA 402b4004...1f9ed). This tool does not re-derive semantic
identity; it INSERTs the exact 1139 approved rows in one transaction, verifies
them in-transaction, then commits.

Scope: source_id = CIC_W only. Canonical / sector / KOSHA / KALIS / source 673
untouched. Migration / schema unchanged (columns follow the existing
supabase/migrations/20260916_risk_canonical_mapping.sql contract).

CLI:
  python -m tools.risk_map.map_materialize001 --preflight
  python -m tools.risk_map.map_materialize001 --execute
  python -m tools.risk_map.map_materialize001 --verify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.map001_cicw_governance import (
    COVERAGE_PATH,
    EXPECTED_APPROVED_CONCEPTS,
    EXPECTED_HOLD_SOURCE_KEY,
    EXPECTED_MAPPING_ROWS,
    EXPECTED_MERGED_MAPPING_ROWS,
    EXPECTED_MERGED_TARGETS,
    EXPECTED_PROMOTED_MAPPING_ROWS,
    EXPECTED_PROMOTED_TARGETS,
    PROPOSAL_PATH,
    build_proposal,
    proposal_sha,
)
from tools.risk_map.map_approve001_owner_binding import (
    APPROVAL_ID,
    BINDING_PATH,
    FROZEN_PROPOSAL_SHA,
    FROZEN_SOURCE_INGEST_RECEIPT_SHA,
    binding_identity_sha,
    build_binding,
)
from tools.risk04.approve001_owner_approval_binding import FROZEN_OWNER_PACKAGE_SHA
from tools.risk04.materialize001_resume_effective_plan import (
    FROZEN_RECEIPT_SHA as FROZEN_CANONICAL_RECEIPT_SHA,
)

WO_ID = "WO-RISK-MAP-MATERIALIZE-001"
MATERIALIZATION_ID = "RISK-MAP-MATERIALIZE-001"

FROZEN_APPROVAL_BINDING_SHA = (
    "402b4004b987169e1cc5b9b0356061794218ef45ee473839b80b72a91cf1f9ed"
)

RECEIPT_PATH = Path("docs/knowledge/risk/RISK_MAP001_MATERIALIZATION_RECEIPT_v1.tsv")
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-map-materialize001-production-mapping_v1.md"
)

RECEIPT_FIELDS: tuple[str, ...] = (
    "mapping_plan_key",
    "source_id",
    "source_key",
    "canonical_id",
    "mapping_type",
    "mapping_status",
    "mapping_method",
    "evidence_basis",
    "materialization_id",
    "owner_approval_id",
    "proposal_sha",
    "approval_binding_sha",
    "production_verified",
)


# ---------------------------------------------------------------------------
# Repository-anchor verification (identical for --preflight / --execute / --verify)
# ---------------------------------------------------------------------------


def _verify_repository_anchors() -> dict:
    """Rebuild proposal + binding from repo evidence and verify all frozen SHAs."""
    proposal_rows = build_proposal()
    if len(proposal_rows) != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"PROPOSAL_ROW_COUNT_DRIFT {len(proposal_rows)}")
    computed_proposal_sha = proposal_sha(proposal_rows)
    if computed_proposal_sha != FROZEN_PROPOSAL_SHA:
        raise SystemExit(f"PROPOSAL_SHA_DRIFT {computed_proposal_sha}")

    disk_proposal = load_tsv(PROPOSAL_PATH)
    if proposal_sha(disk_proposal) != FROZEN_PROPOSAL_SHA:
        raise SystemExit("PROPOSAL_DISK_SHA_DRIFT")
    if proposal_rows != disk_proposal:
        raise SystemExit("PROPOSAL_DISK_ROW_DRIFT")

    binding = build_binding()
    computed_binding_sha = binding_identity_sha(binding)
    if computed_binding_sha != FROZEN_APPROVAL_BINDING_SHA:
        raise SystemExit(f"APPROVAL_BINDING_SHA_DRIFT {computed_binding_sha}")
    if binding[0]["approval_state"] != "OWNER_APPROVED":
        raise SystemExit("APPROVAL_STATE_DRIFT")
    if binding[0]["scope_source_id"] != "CIC_W":
        raise SystemExit("APPROVAL_SCOPE_DRIFT")

    # Scope + composition on proposal
    if any(r["source_id"] != "CIC_W" for r in proposal_rows):
        raise SystemExit("PROPOSAL_NON_CIC_W_ROW")
    if {r["mapping_type"] for r in proposal_rows} != {"EXACT_EQUIVALENT"}:
        raise SystemExit("PROPOSAL_TYPE_DRIFT")
    if {r["mapping_status"] for r in proposal_rows} != {"PROPOSED"}:
        raise SystemExit("PROPOSAL_STATUS_DRIFT")
    if {r["mapping_method"] for r in proposal_rows} != {"MANUAL_REVIEW"}:
        raise SystemExit("PROPOSAL_METHOD_DRIFT")
    if {r["evidence_basis"] for r in proposal_rows} != {
        "OWNER_APPROVED_CONCEPT_MEMBERSHIP"
    }:
        raise SystemExit("PROPOSAL_EVIDENCE_BASIS_DRIFT")

    source_keys = [r["source_key"] for r in proposal_rows]
    if len(set(source_keys)) != EXPECTED_MAPPING_ROWS:
        raise SystemExit("PROPOSAL_SOURCE_KEY_DUPLICATE")
    if EXPECTED_HOLD_SOURCE_KEY in set(source_keys):
        raise SystemExit("HOLD_SOURCE_LEAKED_INTO_PROPOSAL")

    canonical_targets = {r["canonical_id"] for r in proposal_rows}
    if len(canonical_targets) != EXPECTED_APPROVED_CONCEPTS:
        raise SystemExit(f"PROPOSAL_CANONICAL_COVERAGE_DRIFT {len(canonical_targets)}")

    promoted_rows = [
        r for r in proposal_rows if r["canonical_origin_type"] == "PROMOTED_FROM_SOURCE"
    ]
    merged_rows = [
        r for r in proposal_rows if r["canonical_origin_type"] == "MERGED_FROM_REVIEWED_SOURCES"
    ]
    if len(promoted_rows) != EXPECTED_PROMOTED_MAPPING_ROWS:
        raise SystemExit(f"PROPOSAL_PROMOTED_ROWS_DRIFT {len(promoted_rows)}")
    if len(merged_rows) != EXPECTED_MERGED_MAPPING_ROWS:
        raise SystemExit(f"PROPOSAL_MERGED_ROWS_DRIFT {len(merged_rows)}")
    if len({r["canonical_id"] for r in promoted_rows}) != EXPECTED_PROMOTED_TARGETS:
        raise SystemExit("PROPOSAL_PROMOTED_TARGETS_DRIFT")
    if len({r["canonical_id"] for r in merged_rows}) != EXPECTED_MERGED_TARGETS:
        raise SystemExit("PROPOSAL_MERGED_TARGETS_DRIFT")

    if not COVERAGE_PATH.exists():
        raise SystemExit("COVERAGE_MANIFEST_MISSING")
    if not BINDING_PATH.exists():
        raise SystemExit("APPROVAL_BINDING_FILE_MISSING")

    return {
        "proposal_rows": proposal_rows,
        "binding_row": binding[0],
        "proposal_sha": FROZEN_PROPOSAL_SHA,
        "approval_binding_sha": FROZEN_APPROVAL_BINDING_SHA,
        "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
        "source_ingest_receipt_sha": FROZEN_SOURCE_INGEST_RECEIPT_SHA,
        "canonical_owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
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
    proposal_rows = anchors["proposal_rows"]
    with conn.cursor() as cur:
        mappings = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )
        canonical_total = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_nodes"
        )
        canonical_draft = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'DRAFT'"
        )
        canonical_active = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'"
        )
        cic_w_nodes = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_nodes WHERE source_id = %s",
            ("CIC_W",),
        )
        accepted = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_accepted_snapshots"
        )

    if mappings != 0:
        raise SystemExit(f"MAPPING_BASELINE_NOT_ZERO {mappings}")
    if sectors != 0:
        raise SystemExit(f"SECTOR_BASELINE_NOT_ZERO {sectors}")
    if canonical_total != 1110 or canonical_draft != 1110 or canonical_active != 0:
        raise SystemExit(
            f"CANONICAL_BASELINE_DRIFT total={canonical_total} draft={canonical_draft} active={canonical_active}"
        )
    if cic_w_nodes != 1722:
        raise SystemExit(f"CIC_W_SOURCE_NODE_COUNT_DRIFT {cic_w_nodes}")
    if accepted != 3:
        raise SystemExit(f"ACCEPTED_SNAPSHOT_DRIFT {accepted}")

    # Every proposal source_key exists in production risk_source_nodes / CIC_W.
    proposal_source_keys = sorted({r["source_key"] for r in proposal_rows})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_key FROM public.risk_source_nodes "
            "WHERE source_id = 'CIC_W' AND source_key = ANY(%s)",
            (proposal_source_keys,),
        )
        found = {r[0] for r in cur.fetchall()}
    missing = set(proposal_source_keys) - found
    if missing:
        raise SystemExit(f"MISSING_SOURCE_NODES {len(missing)}")

    # Every proposal source_key is provable membership of the ACCEPTED CIC_W snapshot.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT m.member_key) "
            "FROM public.risk_snapshot_memberships m "
            "JOIN public.risk_accepted_snapshots a ON a.id = m.snapshot_id "
            "WHERE m.source_id = 'CIC_W' AND m.member_kind = 'NODE' "
            "AND m.member_key = ANY(%s)",
            (proposal_source_keys,),
        )
        provable = cur.fetchone()[0]
    if provable != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"ACCEPTED_PROVENANCE_DRIFT provable={provable}")

    # Every proposal canonical_id exists in production canonical_nodes / DRAFT.
    proposal_canonical_ids = sorted({r["canonical_id"] for r in proposal_rows})
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, status, node_kind, origin_type, name "
            "FROM public.risk_canonical_nodes WHERE id::text = ANY(%s)",
            (proposal_canonical_ids,),
        )
        prod_canonical = {r[0]: r for r in cur.fetchall()}
    missing_can = set(proposal_canonical_ids) - set(prod_canonical)
    if missing_can:
        raise SystemExit(f"MISSING_CANONICAL_IDS {len(missing_can)}")

    for r in proposal_rows:
        prod = prod_canonical.get(r["canonical_id"])
        if prod is None:
            raise SystemExit(f"CANONICAL_MISSING {r['canonical_id']}")
        _cid, status, node_kind, origin_type, name = prod
        if status != "DRAFT":
            raise SystemExit(f"CANONICAL_STATUS_DRIFT {r['canonical_id']} {status}")
        if r["canonical_kind"] != node_kind:
            raise SystemExit(f"CANONICAL_KIND_DRIFT {r['canonical_id']}")
        if r["canonical_origin_type"] != origin_type:
            raise SystemExit(f"CANONICAL_ORIGIN_DRIFT {r['canonical_id']}")
        if r["canonical_name"] != name:
            raise SystemExit(f"CANONICAL_NAME_DRIFT {r['canonical_id']}")

    return {
        "mappings_before": mappings,
        "sectors_before": sectors,
        "canonical_total": canonical_total,
        "canonical_draft": canonical_draft,
        "canonical_active": canonical_active,
        "cic_w_source_nodes": cic_w_nodes,
        "accepted_snapshots": accepted,
        "source_proposal_matches": len(found),
        "accepted_provenance_matches": provable,
        "canonical_matches": len(prod_canonical),
    }


# ---------------------------------------------------------------------------
# Execute (single transaction, INSERT + in-txn verify + COMMIT)
# ---------------------------------------------------------------------------


def _row_to_db_tuple(row: dict, anchors: dict) -> tuple:
    evidence = {
        "evidence_basis": row["evidence_basis"],
        "review_concept_key": row["review_concept_key"],
        "source_name": row["source_name"],
        "canonical_name": row["canonical_name"],
        "source_context_policy": row["source_context_policy"],
    }
    metadata = {
        "materialization_id": MATERIALIZATION_ID,
        "mapping_plan_key": row["mapping_plan_key"],
        "owner_approval_id": APPROVAL_ID,
        "proposal_sha": anchors["proposal_sha"],
        "approval_binding_sha": anchors["approval_binding_sha"],
        "canonical_receipt_sha": anchors["canonical_receipt_sha"],
        "source_ingest_receipt_sha": anchors["source_ingest_receipt_sha"],
    }
    return (
        row["source_id"],
        row["source_key"],
        row["canonical_id"],
        row["mapping_type"],
        row["mapping_status_target"],
        row["mapping_method"],
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )


def _proposal_rows_for_db(proposal_rows: list[dict]) -> list[dict]:
    """Copy of proposal rows with mapping_status overwritten to APPROVED (target)."""
    out = []
    for r in proposal_rows:
        cp = dict(r)
        cp["mapping_status_target"] = "APPROVED"  # ONLY the target row's status
        out.append(cp)
    return out


def execute_materialization(anchors: dict) -> dict:
    """Single-transaction INSERT + in-txn exact-set verification. Commits only on PASS."""
    from psycopg2.extras import execute_values

    proposal_rows = anchors["proposal_rows"]
    target_rows = _proposal_rows_for_db(proposal_rows)

    conn = _connect_txn()
    inserted = 0
    verified = 0
    try:
        # Concurrency guard: within our transaction, count mappings.
        with conn.cursor() as cur:
            baseline = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_source_mappings"
            )
        if baseline != 0:
            raise SystemExit(f"CONCURRENT_MAPPING_BASELINE {baseline}")

        # Lock the mapping table for the duration of the transaction so no
        # concurrent writer can slip in between our INSERT and post-verify.
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE public.risk_source_mappings IN EXCLUSIVE MODE")

        tuples = [_row_to_db_tuple(r, anchors) for r in target_rows]
        with conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO public.risk_source_mappings ("
                "source_id, source_key, canonical_id, mapping_type, mapping_status, "
                "mapping_method, evidence, metadata"
                ") VALUES %s",
                tuples,
                template="(%s, %s, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb)",
                page_size=200,
            )
        # execute_values batches internally; cur.rowcount only reflects the last
        # batch. Trust the post-INSERT COUNT and per-row set-verify below as the
        # authoritative in-transaction check.
        inserted = len(tuples)

        # In-transaction exact-set verification.
        with conn.cursor() as cur:
            db_rows = _fetch_rows(
                cur,
                "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
                "mapping_type, mapping_status, mapping_method, evidence, metadata "
                "FROM public.risk_source_mappings",
            )
        if len(db_rows) != EXPECTED_MAPPING_ROWS:
            raise SystemExit(f"IN_TXN_ROW_COUNT_DRIFT {len(db_rows)}")

        by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
        for target in target_rows:
            key = (target["source_id"], target["source_key"])
            db_row = by_key.get(key)
            if db_row is None:
                raise SystemExit(f"IN_TXN_ROW_MISSING {key}")
            if db_row["canonical_id"] != target["canonical_id"]:
                raise SystemExit(f"IN_TXN_CANONICAL_MISMATCH {key}")
            if db_row["mapping_type"] != "EXACT_EQUIVALENT":
                raise SystemExit(f"IN_TXN_TYPE_MISMATCH {key}")
            if db_row["mapping_status"] != "APPROVED":
                raise SystemExit(f"IN_TXN_STATUS_MISMATCH {key}")
            if db_row["mapping_method"] != "MANUAL_REVIEW":
                raise SystemExit(f"IN_TXN_METHOD_MISMATCH {key}")

            ev = db_row["evidence"] if isinstance(db_row["evidence"], dict) else json.loads(db_row["evidence"])
            if ev.get("evidence_basis") != "OWNER_APPROVED_CONCEPT_MEMBERSHIP":
                raise SystemExit(f"IN_TXN_EVIDENCE_BASIS_MISMATCH {key}")
            if ev.get("review_concept_key") != target["review_concept_key"]:
                raise SystemExit(f"IN_TXN_REVIEW_CONCEPT_MISMATCH {key}")
            if ev.get("source_name") != target["source_name"]:
                raise SystemExit(f"IN_TXN_SOURCE_NAME_MISMATCH {key}")
            if ev.get("canonical_name") != target["canonical_name"]:
                raise SystemExit(f"IN_TXN_CANONICAL_NAME_MISMATCH {key}")
            if ev.get("source_context_policy") != target["source_context_policy"]:
                raise SystemExit(f"IN_TXN_CONTEXT_POLICY_MISMATCH {key}")

            md = db_row["metadata"] if isinstance(db_row["metadata"], dict) else json.loads(db_row["metadata"])
            if md.get("materialization_id") != MATERIALIZATION_ID:
                raise SystemExit(f"IN_TXN_MATERIALIZATION_ID_MISMATCH {key}")
            if md.get("owner_approval_id") != APPROVAL_ID:
                raise SystemExit(f"IN_TXN_APPROVAL_ID_MISMATCH {key}")
            if md.get("proposal_sha") != anchors["proposal_sha"]:
                raise SystemExit(f"IN_TXN_PROPOSAL_SHA_MISMATCH {key}")
            if md.get("approval_binding_sha") != anchors["approval_binding_sha"]:
                raise SystemExit(f"IN_TXN_BINDING_SHA_MISMATCH {key}")

            verified += 1

        if verified != EXPECTED_MAPPING_ROWS:
            raise SystemExit(f"IN_TXN_VERIFIED_COUNT_DRIFT {verified}")

        # Same-txn invariants.
        with conn.cursor() as cur:
            can_total = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_canonical_nodes"
            )
            can_active = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_canonical_nodes WHERE status = 'ACTIVE'"
            )
            sectors = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
            )
            nodes = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_nodes")
            records = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
            memberships = _fetch_scalar(
                cur, "SELECT count(*) FROM public.risk_snapshot_memberships"
            )
        if can_total != 1110 or can_active != 0:
            raise SystemExit(
                f"IN_TXN_CANONICAL_DRIFT total={can_total} active={can_active}"
            )
        if sectors != 0:
            raise SystemExit(f"IN_TXN_SECTOR_DRIFT {sectors}")
        if nodes != 3325 or records != 30696 or memberships != 34021:
            raise SystemExit(
                f"IN_TXN_SOURCE_CORE_DRIFT nodes={nodes} records={records} memberships={memberships}"
            )

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
# Verify (read-only, generates receipt + report)
# ---------------------------------------------------------------------------


def _verify_production(conn, anchors: dict) -> dict:
    proposal_rows = anchors["proposal_rows"]

    with conn.cursor() as cur:
        mappings = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        approved = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE mapping_status = 'APPROVED'",
        )
        exact = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE mapping_type = 'EXACT_EQUIVALENT'",
        )
        manual = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE mapping_method = 'MANUAL_REVIEW'",
        )
        cic_w = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = 'CIC_W'",
        )
        kosha = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = 'KOSHA_CONSTRUCTION_PROCESS'",
        )
        kalis = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = 'KALIS_RISK_PROFILE'",
        )
        hold_source = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings WHERE source_id = 'CIC_W' AND source_key = %s",
            (EXPECTED_HOLD_SOURCE_KEY,),
        )
        unique_source_keys = _fetch_scalar(
            cur,
            "SELECT count(DISTINCT source_key) FROM public.risk_source_mappings WHERE source_id = 'CIC_W'",
        )
        canonical_targets = _fetch_scalar(
            cur,
            "SELECT count(DISTINCT canonical_id) FROM public.risk_source_mappings",
        )
        promoted = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings m "
            "JOIN public.risk_canonical_nodes c ON c.id = m.canonical_id "
            "WHERE c.origin_type = 'PROMOTED_FROM_SOURCE'",
        )
        promoted_targets = _fetch_scalar(
            cur,
            "SELECT count(DISTINCT m.canonical_id) FROM public.risk_source_mappings m "
            "JOIN public.risk_canonical_nodes c ON c.id = m.canonical_id "
            "WHERE c.origin_type = 'PROMOTED_FROM_SOURCE'",
        )
        merged = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_source_mappings m "
            "JOIN public.risk_canonical_nodes c ON c.id = m.canonical_id "
            "WHERE c.origin_type = 'MERGED_FROM_REVIEWED_SOURCES'",
        )
        merged_targets = _fetch_scalar(
            cur,
            "SELECT count(DISTINCT m.canonical_id) FROM public.risk_source_mappings m "
            "JOIN public.risk_canonical_nodes c ON c.id = m.canonical_id "
            "WHERE c.origin_type = 'MERGED_FROM_REVIEWED_SOURCES'",
        )

        # Row-set exact verification
        db_rows = _fetch_rows(
            cur,
            "SELECT source_id, source_key, canonical_id::text AS canonical_id, "
            "mapping_type, mapping_status, mapping_method, evidence, metadata "
            "FROM public.risk_source_mappings",
        )

    audit = {
        "mappings": mappings,
        "approved": approved,
        "exact": exact,
        "manual": manual,
        "cic_w": cic_w,
        "kosha": kosha,
        "kalis": kalis,
        "hold_source": hold_source,
        "unique_source_keys": unique_source_keys,
        "canonical_targets": canonical_targets,
        "promoted": promoted,
        "promoted_targets": promoted_targets,
        "merged": merged,
        "merged_targets": merged_targets,
    }

    if mappings != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"POST_MAPPING_COUNT {mappings}")
    if approved != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"POST_APPROVED_COUNT {approved}")
    if exact != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"POST_EXACT_COUNT {exact}")
    if manual != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"POST_MANUAL_COUNT {manual}")
    if cic_w != EXPECTED_MAPPING_ROWS or kosha != 0 or kalis != 0 or hold_source != 0:
        raise SystemExit(f"POST_SCOPE_DRIFT {audit}")
    if unique_source_keys != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"POST_UNIQUE_SOURCE_KEYS_DRIFT {unique_source_keys}")
    if canonical_targets != EXPECTED_APPROVED_CONCEPTS:
        raise SystemExit(f"POST_CANONICAL_COVERAGE {canonical_targets}")
    if promoted != EXPECTED_PROMOTED_MAPPING_ROWS or promoted_targets != EXPECTED_PROMOTED_TARGETS:
        raise SystemExit(f"POST_PROMOTED_DRIFT {audit}")
    if merged != EXPECTED_MERGED_MAPPING_ROWS or merged_targets != EXPECTED_MERGED_TARGETS:
        raise SystemExit(f"POST_MERGED_DRIFT {audit}")

    by_key = {(r["source_id"], r["source_key"]): r for r in db_rows}
    exact_row_matches = 0
    for target in proposal_rows:
        key = (target["source_id"], target["source_key"])
        db_row = by_key.get(key)
        if db_row is None:
            raise SystemExit(f"POST_ROW_MISSING {key}")
        if db_row["canonical_id"] != target["canonical_id"]:
            raise SystemExit(f"POST_CANONICAL_MISMATCH {key}")
        if db_row["mapping_status"] != "APPROVED":
            raise SystemExit(f"POST_STATUS_MISMATCH {key}")
        ev = db_row["evidence"] if isinstance(db_row["evidence"], dict) else json.loads(db_row["evidence"])
        md = db_row["metadata"] if isinstance(db_row["metadata"], dict) else json.loads(db_row["metadata"])
        if ev.get("review_concept_key") != target["review_concept_key"]:
            raise SystemExit(f"POST_EVIDENCE_MISMATCH {key}")
        if md.get("proposal_sha") != anchors["proposal_sha"]:
            raise SystemExit(f"POST_METADATA_PROPOSAL_SHA_MISMATCH {key}")
        if md.get("approval_binding_sha") != anchors["approval_binding_sha"]:
            raise SystemExit(f"POST_METADATA_BINDING_SHA_MISMATCH {key}")
        exact_row_matches += 1

    audit["exact_row_matches"] = exact_row_matches
    return audit


def _write_receipt(anchors: dict) -> str:
    proposal_rows = anchors["proposal_rows"]
    rows = [
        {
            "mapping_plan_key": r["mapping_plan_key"],
            "source_id": r["source_id"],
            "source_key": r["source_key"],
            "canonical_id": r["canonical_id"],
            "mapping_type": "EXACT_EQUIVALENT",
            "mapping_status": "APPROVED",
            "mapping_method": "MANUAL_REVIEW",
            "evidence_basis": r["evidence_basis"],
            "materialization_id": MATERIALIZATION_ID,
            "owner_approval_id": APPROVAL_ID,
            "proposal_sha": anchors["proposal_sha"],
            "approval_binding_sha": anchors["approval_binding_sha"],
            "production_verified": "YES",
        }
        for r in proposal_rows
    ]
    rows.sort(key=lambda r: (r["source_id"], r["source_key"], r["canonical_id"]))
    write_tsv(rows, RECEIPT_PATH, RECEIPT_FIELDS)
    sha = universe_sha(rows, *RECEIPT_FIELDS)
    return sha


def _write_report(anchors: dict, receipt_sha: str) -> None:
    body = f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-MAP-MATERIALIZE-001 CIC_W production source mapping materialization
version: 1
status: active
owner: taiwang
---

# {WO_ID} — CIC_W Approved Source Mapping Materialization

Owner-approved CIC_W source→canonical mapping package has been materialized to
production `risk_source_mappings`. Row-level authority: frozen proposal +
frozen owner approval binding. No canonical / sector write. No B/C. No HOLD
source. Merge is a separate future decision.

## Anchors

```text
proposal SHA                = {anchors["proposal_sha"]}
approval binding SHA        = {anchors["approval_binding_sha"]}
canonical receipt SHA       = {anchors["canonical_receipt_sha"]}
source ingest receipt SHA   = {anchors["source_ingest_receipt_sha"]}
canonical owner package SHA = {anchors["canonical_owner_package_sha"]}
```

## Production result

```text
materialized mappings         = {EXPECTED_MAPPING_ROWS}
production status             = APPROVED
mapping_type                  = EXACT_EQUIVALENT
mapping_method                = MANUAL_REVIEW
scope_source_id               = CIC_W
KOSHA                         = 0
KALIS                         = 0
source 673                    = UNMAPPED
canonical                     = 1110 DRAFT
ACTIVE                        = 0
canonical_node_sectors        = 0
```

Breakdown:

```text
PROMOTED targets / mappings   = {EXPECTED_PROMOTED_TARGETS} / {EXPECTED_PROMOTED_MAPPING_ROWS}
MERGED   targets / mappings   = {EXPECTED_MERGED_TARGETS} / {EXPECTED_MERGED_MAPPING_ROWS}
```

## Receipt

```text
RISK MAP MATERIALIZATION RECEIPT SHA = {receipt_sha}
receipt file                         = {RECEIPT_PATH}
```

## Verdict

```text
{WO_ID} = PASS / PRODUCTION_MATERIALIZED / EVIDENCE_READY
MERGE = NOT AUTHORIZED
NEXT  = GPT INDEPENDENT FINAL VERIFY
STOP
```
"""
    REPORT_PATH.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(tag: str, payload: dict) -> None:
    print(
        f"[{tag}] "
        + json.dumps(payload, ensure_ascii=True, sort_keys=True)
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} executor")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not any([args.preflight, args.execute, args.verify]):
        parser.print_help()
        return 2

    anchors = _verify_repository_anchors()

    if args.preflight or args.execute:
        conn = _connect_autocommit(readonly=True)
        try:
            pre = _preflight_db(conn, anchors)
        finally:
            conn.close()
        _emit("preflight", pre)

    if args.execute:
        # Idempotency: if the exact 1139 rows are already committed, skip the INSERT.
        conn = _connect_autocommit(readonly=True)
        try:
            with conn.cursor() as cur:
                mappings_now = _fetch_scalar(
                    cur, "SELECT count(*) FROM public.risk_source_mappings"
                )
        finally:
            conn.close()
        if mappings_now == EXPECTED_MAPPING_ROWS:
            _emit("already_materialized", {"mappings": mappings_now})
        elif mappings_now == 0:
            result = execute_materialization(anchors)
            _emit("execute", result)
        else:
            raise SystemExit(
                f"UNEXPECTED_PARTIAL_MAPPINGS {mappings_now} — refuse to auto-heal"
            )

    if args.verify:
        conn = _connect_autocommit(readonly=True)
        try:
            audit = _verify_production(conn, anchors)
        finally:
            conn.close()
        receipt_sha = _write_receipt(anchors)
        _write_report(anchors, receipt_sha)
        audit["receipt_sha"] = receipt_sha
        _emit("verify", audit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
