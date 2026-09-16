"""WO-RISK-02-INGEST-001-R1 local executor.

Resumes the production source-core ingest via a direct psycopg2 connection so the
per-row work stays inside the Python process instead of being fanned out through
MCP or conversation batches.

Contract preserved from WO-RISK-02-INGEST-001:
  * No DELETE, no TRUNCATE, no UPDATE outside the STAGED→VALIDATED→ACCEPTED
    status transitions on public.risk_snapshots.
  * No writes to public.risk_source_mappings.
  * No writes/updates to public.risk_canonical_nodes.
  * No writes to public.risk_canonical_node_sectors.
  * All INSERTs reuse the builders from ingest001_source_core, which end in
    ON CONFLICT DO NOTHING, so resume is idempotent.
  * DATABASE_URL is read from os.environ only. No hard-coded credentials.

CLI:
  python -m tools.risk02.ingest001_source_core_local_exec --preflight
  python -m tools.risk02.ingest001_source_core_local_exec --resume
  python -m tools.risk02.ingest001_source_core_local_exec --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

from tools.risk02.contract import (
    A_SHA256,
    B_SHA256,
    C_HEADERS,
    C_RAW_ROWS,
    C_SHA256,
    SOURCE_CIC_W,
    SOURCE_KALIS,
    SOURCE_KOSHA,
)
from tools.risk02.ingest001_source_core import (
    B_NODES,
    C_NODES,
    FROZEN_DETERMINISM_SHA,
    PLANNED_MEMBERSHIPS,
    RECEIPT_FIELDS,
    RECEIPT_PATH,
    REPORT_PATH,
    memberships_insert_sql,
    planned_memberships,
    planned_nodes,
    planned_records,
    receipt_sha,
    records_insert_sql,
    render_report,
    two_run_plan,
)
from tools.risk04.review_decisions import load_tsv, write_tsv

RECORD_BATCH = 100
MEMBERSHIP_BATCH = 500
COMMIT_EVERY_N_BATCHES = 10

# Mapping from canonical Korean payload field → scalar column stored alongside
# raw_payload. Frozen from supabase/migrations/20260915_risk_source_catalog.sql
# and tools.risk02.ingest001_source_core.records_insert_sql.
PROJECTION_MAP: tuple[tuple[str, str], ...] = (
    ("시설물분류(대)", "facility_big"),
    ("시설물분류(중)", "facility_mid"),
    ("시설물분류(소)", "facility_small"),
    ("공종분류(대)", "work_big"),
    ("공종분류(중)", "work_mid"),
    ("작업프로세스명", "task"),
    ("위험발생객체분류(대)", "hazard_object_big"),
    ("위험발생객체분류(중)", "hazard_object_mid"),
    ("위험발생위치분류(대)", "hazard_location_big"),
    ("위험발생위치코드(중)", "hazard_location_mid_code"),
    ("위험발생위치분류(중)", "hazard_location_mid"),
    ("위험발생위치분류(소)", "hazard_location_small"),
    ("사고원인", "cause"),
    ("인적피해", "human_damage"),
    ("물적피해", "property_damage"),
    ("사고가능성", "likelihood"),
    ("사고심각성", "severity"),
    ("설계단계", "design_control"),
    ("시공단계", "construction_control"),
)

REPAIR_DRYRUN_PATH = Path("docs/knowledge/risk/RISK02_RECORD_REPAIR_DRYRUN_v1.tsv")
REPAIR_DRYRUN_FIELDS: tuple[str, ...] = (
    "content_key",
    "mismatch_population",
    "changed_payload_field_count",
    "projection_mismatch_count",
    "projection_mismatch_columns",
    "current_payload_sha256",
    "planned_payload_sha256",
    "planned_content_key_recompute",
    "db_payload_recompute",
    "task_source_key_match",
    "repair_eligible",
    "ineligibility_reason",
)

EXPECTED_NODES = 1722 + B_NODES + C_NODES
EXPECTED_RECORDS = 30696
EXPECTED_MEMBERSHIPS = PLANNED_MEMBERSHIPS
KALIS_RECORD_OCCURRENCE_SUM = C_RAW_ROWS
# KOSHA DETAIL_PROCESS (leaf) identities = 620; occurrence sum across leaves = 626.
KOSHA_LEAF_IDENTITIES = 620
KOSHA_LEAF_OCCURRENCE_SUM = 626
# All 787 KOSHA NODE memberships: leaves contribute 626 by occurrence, non-leaves
# (PROJECT_KIND + WORK_TYPE = 167) contribute 1 each. Total = 793.
KOSHA_NODE_OCCURRENCE_SUM_TOTAL = (
    KOSHA_LEAF_OCCURRENCE_SUM + (B_NODES - KOSHA_LEAF_IDENTITIES)
)


def _require_database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit(
            "BLOCKED: DATABASE_URL not set. WO-RISK-02-INGEST-001-R1 refuses MCP fallback."
        )
    return url


def _connect():
    import psycopg2

    return psycopg2.connect(_require_database_url())


def _chunks(rows: list, size: int) -> Iterator[list]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _emit(line: str) -> None:
    print(line, flush=True)


def _emit_repair_execute(result: dict) -> None:
    lines = [
        "=== W1 REPAIR EXECUTE ===",
        f"manifest_rows = {result['manifest_rows']}",
        f"concurrency_ok = {result['concurrency_ok']} / 30",
        f"rows_updated = {result['updated']} / 30",
        f"rows_verified_in_txn = {result['verified']} / 30",
        f"records_before = {result['records_before']}",
        f"records_after = {result['records_after']}",
        f"transaction = {result['transaction']}",
        "",
        "WRITE OUTSIDE THIS 30-ROW TXN = 0",
        "STOP",
    ]
    print("\n".join(lines), flush=True)


def _emit_repair_dryrun(result: dict) -> None:
    total = result["repair_candidates"]
    lines = [
        "=== REPAIR DRY-RUN (READ-ONLY) ===",
        f"repair_candidates = {total}",
        f"P1 = {result['P1']}",
        f"P2 = {result['P2']}",
        f"plan_key_recompute_match = {result['plan_key_recompute_match']} / {total}",
        f"db_payload_recompute_mismatch = {result['db_payload_recompute_mismatch']} / {total}",
        f"task_source_key_match = {result['task_source_key_match']} / {total}",
        f"projection_mismatch_rows = {result['projection_mismatch_rows']} / {total}",
        "projection_mismatch_columns (col_name = row_count):",
    ]
    if result["projection_mismatch_columns"]:
        for col, n in sorted(
            result["projection_mismatch_columns"].items(),
            key=lambda kv: (-kv[1], kv[0]),
        ):
            lines.append(f"  {col} = {n}")
    else:
        lines.append("  (none)")
    lines += [
        f"repair_eligible = {result['repair_eligible']} / {total}",
        f"concurrent_fingerprints_frozen = {result['concurrent_fingerprints_frozen']} / {total}",
        f"manifest_path = {result['manifest_path']}",
        "",
        "WRITE = 0",
        "NEXT = GPT REVIEW FOR REPAIR WRITE APPROVAL",
        "STOP",
    ]
    print("\n".join(lines), flush=True)


def _emit_diagnose(result: dict) -> None:
    lines = [
        "=== OPTION B — SANITIZED ROOT-CAUSE DIAGNOSIS (READ-ONLY) ===",
        f"P1 population size = {result['population_counts']['P1']}",
        f"P2 population size = {result['population_counts']['P2']}",
        f"P1 sample content_key = {result['p1_sample_key']}",
        f"P2 sample content_key = {result['p2_sample_key']}",
        "",
    ]
    p1 = result.get("p1")
    if p1:
        lines += [
            "--- P1 SAMPLE ---",
            f"literal_escaped_key_count = {p1['literal_escaped_key_count']}/19",
            f"decoded_keys_matching_canonical = {p1['decoded_keys_matching_canonical']}/19",
            f"values_matching_after_key_decode = {p1['values_matching_after_key_decode']}/19",
            f"plan_content_key_recompute = {p1['plan_content_key_recompute']}",
            f"db_raw_key_recompute = {p1['db_raw_key_recompute']}",
            f"db_decoded_key_recompute = {p1['db_decoded_key_recompute']}",
            f"root_cause = {p1['root_cause']}",
            "",
        ]
    else:
        lines += ["--- P1 SAMPLE = NONE ---", ""]

    p2 = result.get("p2")
    if p2:
        lines += [
            "--- P2 SAMPLE ---",
            f"differing_field_count = {p2['differing_field_count']}",
            f"plan_content_key_recompute = {p2['plan_content_key_recompute']}",
            f"db_payload_recompute = {p2['db_payload_recompute']}",
            "normalization_summary:",
        ]
        for k, v in p2["normalization_summary"].items():
            lines.append(f"  {k} = {v}")
        lines.append("")
        lines.append("per-field diff (values not emitted):")
        for d in p2["per_field"]:
            lines.append(
                f"  {d['field']}: "
                f"plan_len={d['plan_length']} db_len={d['db_length']} "
                f"plan_sha={d['plan_sha_prefix']} db_sha={d['db_sha_prefix']} "
                f"exact={d['exact_equal']} strip={d['strip_equal']} "
                f"nfc={d['nfc_equal']} nfkc={d['nfkc_equal']} "
                f"newline_norm={d['newline_normalized_equal']} "
                f"ws_collapsed={d['whitespace_collapsed_equal']} "
                f"plan_lead_ws={d['plan_leading_ws']} db_lead_ws={d['db_leading_ws']} "
                f"plan_trail_ws={d['plan_trailing_ws']} db_trail_ws={d['db_trailing_ws']} "
                f"plan_tab={d['plan_contains_tab']} db_tab={d['db_contains_tab']} "
                f"plan_nl={d['plan_contains_newline']} db_nl={d['db_contains_newline']} "
                f"plan_nbsp={d['plan_contains_nbsp']} db_nbsp={d['db_contains_nbsp']} "
                f"plan_zw={d['plan_contains_zero_width']} db_zw={d['db_contains_zero_width']} "
                f"plan_bs_u={d['plan_contains_backslash_u']} db_bs_u={d['db_contains_backslash_u']} "
                f"plan_ctrl={d['plan_contains_control']} db_ctrl={d['db_contains_control']}"
            )
        lines.append("")
        lines.append(f"root_cause = {p2['root_cause']}")
    else:
        lines += ["--- P2 SAMPLE = NONE ---"]

    lines += ["", "WRITE = 0", "STOP"]
    print("\n".join(lines), flush=True)


def _emit_audit(audit: dict) -> None:
    lines = [
        "=== MISMATCH SCOPE AUDIT (READ-ONLY) ===",
        f"planned_total = {audit['planned_total']}",
        f"production_total = {audit['production_total']}",
        f"checked = {audit['checked']}",
        f"exact_matches = {audit['exact_matches']}",
        f"unexpected_content_keys = {audit['unexpected_content_keys']}",
        f"task_source_key_mismatches = {audit['task_source_key_mismatches']}",
        f"payload_mismatch_rows = {audit['payload_mismatch_rows']}",
        f"planned_keys_not_yet_in_db = {audit['planned_keys_not_yet_in_db']}",
        "",
        "DB payload field-count distribution:",
        f"  < 19 fields = {audit['db_payload_field_count']['lt_19']}",
        f"  = 19 fields = {audit['db_payload_field_count']['eq_19']}",
        f"  > 19 fields = {audit['db_payload_field_count']['gt_19']}",
        "PLAN payload field-count distribution:",
        f"  < 19 fields = {audit['plan_payload_field_count']['lt_19']}",
        f"  = 19 fields = {audit['plan_payload_field_count']['eq_19']}",
        f"  > 19 fields = {audit['plan_payload_field_count']['gt_19']}",
        "",
        "FIELD_MISSING_IN_DB (plan has, DB missing) — 19 canonical fields:",
    ]
    for field in C_HEADERS:
        n = audit["field_missing_in_db_all"].get(field, 0)
        lines.append(f"  {field} = {n}")
    lines.append("")
    lines.append("FIELD_EXTRA_IN_DB (fields DB has beyond the 19 canonical set):")
    if audit["field_extra_in_db"]:
        for field, n in sorted(audit["field_extra_in_db"].items()):
            lines.append(f"  {field!r} = {n}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("VALUE_DIFFERENT per canonical field:")
    for field in C_HEADERS:
        n = audit["value_different_all"].get(field, 0)
        lines.append(f"  {field} = {n}")
    lines.append("")
    lines.append("TYPE_DIFFERENT per canonical field:")
    for field in C_HEADERS:
        n = audit["type_different_all"].get(field, 0)
        lines.append(f"  {field} = {n}")
    lines.append("")
    lines.append("WRITE = 0")
    lines.append("STOP")
    print("\n".join(lines), flush=True)


def _fetch_scalar(cur, sql: str, params: tuple = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _fetch_rows(cur, sql: str, params: tuple = ()) -> list[dict]:
    import psycopg2.extras  # noqa: F401  (imported for RealDictCursor typing hint)

    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _snapshot_map(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        rows = _fetch_rows(
            cur,
            "SELECT id::text AS id, source_id FROM public.risk_snapshots",
        )
    return {r["source_id"]: r["id"] for r in rows}


def preflight(conn, plan: dict) -> dict:
    with conn.cursor() as cur:
        sources = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_sources")
        snapshots = _fetch_rows(
            cur,
            "SELECT source_id, source_sha256, status FROM public.risk_snapshots "
            "ORDER BY source_id",
        )
        nodes_by_source = {
            r["source_id"]: r["n"]
            for r in _fetch_rows(
                cur,
                "SELECT source_id, count(*) AS n FROM public.risk_source_nodes "
                "GROUP BY source_id",
            )
        }
        records = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
        memberships = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_snapshot_memberships"
        )
        canonical = _fetch_rows(
            cur,
            "SELECT status, count(*) AS n FROM public.risk_canonical_nodes "
            "GROUP BY status",
        )
        canonical_total = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_nodes"
        )
        mappings = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_source_mappings"
        )
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )
        accepted = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_accepted_snapshots"
        )

    canonical_by_status = {r["status"]: r["n"] for r in canonical}

    audit = {
        "risk_sources": sources,
        "snapshots": snapshots,
        "nodes_by_source": nodes_by_source,
        "records": records,
        "memberships": memberships,
        "canonical_total": canonical_total,
        "canonical_by_status": canonical_by_status,
        "mappings": mappings,
        "canonical_node_sectors": sectors,
        "accepted": accepted,
    }

    _guard_baseline(audit)
    _verify_existing_nodes(conn, plan)
    _verify_existing_records(conn, plan)

    return audit


def _guard_baseline(audit: dict) -> None:
    if audit["risk_sources"] != 3:
        raise SystemExit(f"WRONG_DB_OR_DRIFT risk_sources={audit['risk_sources']}")

    shas = {row["source_id"]: row["source_sha256"] for row in audit["snapshots"]}
    expected_shas = {
        SOURCE_CIC_W: A_SHA256,
        SOURCE_KOSHA: B_SHA256,
        SOURCE_KALIS: C_SHA256,
    }
    if shas != expected_shas:
        raise SystemExit(f"SNAPSHOT_SHA_DRIFT {shas}")
    if len(audit["snapshots"]) != 3:
        raise SystemExit(f"SNAPSHOT_COUNT_DRIFT {len(audit['snapshots'])}")

    nodes = audit["nodes_by_source"]
    if (
        nodes.get(SOURCE_CIC_W, 0) != 1722
        or nodes.get(SOURCE_KOSHA, 0) != B_NODES
        or nodes.get(SOURCE_KALIS, 0) != C_NODES
    ):
        raise SystemExit(f"NODE_DRIFT {nodes}")

    if audit["canonical_total"] != 1110:
        raise SystemExit(f"CANONICAL_TOTAL_DRIFT {audit['canonical_total']}")
    if audit["canonical_by_status"].get("DRAFT", 0) != 1110:
        raise SystemExit(f"CANONICAL_DRAFT_DRIFT {audit['canonical_by_status']}")
    if audit["canonical_by_status"].get("ACTIVE", 0) != 0:
        raise SystemExit(f"CANONICAL_ACTIVE_PRESENT {audit['canonical_by_status']}")

    if audit["mappings"] != 0:
        raise SystemExit(f"MAPPING_DRIFT {audit['mappings']}")
    if audit["canonical_node_sectors"] != 0:
        raise SystemExit(f"SECTOR_DRIFT {audit['canonical_node_sectors']}")

    if audit["records"] > EXPECTED_RECORDS:
        raise SystemExit(f"RECORD_OVERSHOOT {audit['records']}")
    if audit["memberships"] > EXPECTED_MEMBERSHIPS:
        raise SystemExit(f"MEMBERSHIP_OVERSHOOT {audit['memberships']}")


def _norm_parent(v: Any) -> str | None:
    if v is None:
        return None
    v = str(v)
    return v if v else None


def _verify_existing_nodes(conn, plan: dict) -> None:
    planned = {(n["source_id"], n["source_key"]): n for n in planned_nodes(plan)}
    with conn.cursor(name="risk02_nodes_scan") as cur:
        cur.itersize = 2000
        cur.execute(
            "SELECT source_id, source_key, content_hash, parent_source_key, "
            "node_type, depth FROM public.risk_source_nodes"
        )
        for row in cur:
            source_id, source_key, content_hash, parent, node_type, depth = row
            key = (source_id, source_key)
            p = planned.get(key)
            if p is None:
                raise SystemExit(f"UNEXPECTED_NODE {key}")
            if content_hash != p["content_hash"]:
                raise SystemExit(f"NODE_CONTENT_HASH_CONFLICT {key}")
            if node_type != p["node_type"]:
                raise SystemExit(f"NODE_TYPE_CONFLICT {key}")
            if depth != p["depth"]:
                raise SystemExit(f"NODE_DEPTH_CONFLICT {key}")
            if _norm_parent(parent) != _norm_parent(p["parent_source_key"]):
                raise SystemExit(f"NODE_PARENT_CONFLICT {key}")


def repair_execute(conn, plan: dict) -> dict:
    """W1 execute: transactional repair of the 30 rows from the dry-run manifest.

    Reads manifest, per row: SELECT ... FOR UPDATE; recomputes current SHA against
    manifest current_payload_sha256; if any drift → ROLLBACK and abort. Then
    UPDATE raw_payload + all 19 scalar projection columns + task_source_key from
    plan. After all 30 UPDATEs, verifies row count, hash recompute, task key, and
    projection consistency inside the same transaction. Commits only on full PASS.
    """
    from tools.risk02.identity import c_content_key

    if not REPAIR_DRYRUN_PATH.exists():
        raise SystemExit("REPAIR_DRYRUN_MANIFEST_MISSING run --repair-dry-run first")
    manifest = load_tsv(REPAIR_DRYRUN_PATH)
    if len(manifest) != 30:
        raise SystemExit(f"MANIFEST_ROW_COUNT_DRIFT {len(manifest)}")
    for row in manifest:
        if row["repair_eligible"] != "YES":
            raise SystemExit(
                f"MANIFEST_HAS_INELIGIBLE_ROW {row['content_key']} "
                f"reason={row['ineligibility_reason']}"
            )

    planned = {r["content_key"]: r for r in planned_records(plan)}
    for row in manifest:
        if row["content_key"] not in planned:
            raise SystemExit(f"MANIFEST_ROW_NOT_IN_PLAN {row['content_key']}")

    # psycopg2 default is autocommit=False; we rely on that and drive the whole
    # repair inside a single implicit transaction.
    concurrency_ok = 0
    updated = 0
    verified = 0

    try:
        # Preflight-lite inside the same transaction: overall row count stability.
        with conn.cursor() as cur:
            pre_count = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
        if pre_count != 8010:
            raise SystemExit(f"PRE_REPAIR_COUNT_DRIFT expected=8010 got={pre_count}")

        # PASS 1: SELECT ... FOR UPDATE per row → verify current SHA → UPDATE.
        for row in manifest:
            content_key = row["content_key"]
            expected_sha = row["current_payload_sha256"]
            p = planned[content_key]
            plan_payload = p["raw_payload"]
            plan_task_key = p["task_source_key"]

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_payload FROM public.risk_records "
                    "WHERE source_id = %s AND content_key = %s FOR UPDATE",
                    (SOURCE_KALIS, content_key),
                )
                got = cur.fetchone()
            if got is None:
                raise SystemExit(f"ROW_MISSING {content_key}")
            current_payload = got[0] if isinstance(got[0], dict) else json.loads(got[0])
            current_sha = _canonical_payload_sha(current_payload)
            if current_sha != expected_sha:
                raise SystemExit(f"CONCURRENT_CHANGE {content_key}")
            concurrency_ok += 1

            params: dict[str, Any] = {
                "content_key": content_key,
                "source_id": SOURCE_KALIS,
                "raw_payload": json.dumps(
                    {h: plan_payload[h] for h in C_HEADERS},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "task_source_key": plan_task_key,
            }
            for canonical, col in PROJECTION_MAP:
                params[col] = plan_payload.get(canonical, "")

            set_clauses = [
                "raw_payload = %(raw_payload)s::jsonb",
                "task_source_key = %(task_source_key)s",
            ]
            for _, col in PROJECTION_MAP:
                set_clauses.append(f"{col} = %({col})s")

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.risk_records SET "
                    + ", ".join(set_clauses)
                    + " WHERE source_id = %(source_id)s "
                    + "AND content_key = %(content_key)s",
                    params,
                )
                if cur.rowcount != 1:
                    raise SystemExit(
                        f"UPDATE_ROWCOUNT_DRIFT {content_key} rows={cur.rowcount}"
                    )
            updated += 1

        # PASS 2: In-transaction verification.
        with conn.cursor() as cur:
            post_count = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
        if post_count != 8010:
            raise SystemExit(f"POST_REPAIR_COUNT_DRIFT expected=8010 got={post_count}")

        content_keys = tuple(r["content_key"] for r in manifest)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_key, task_source_key, raw_payload, "
                + ", ".join(col for _, col in PROJECTION_MAP)
                + " FROM public.risk_records "
                + "WHERE source_id = %s AND content_key = ANY(%s)",
                (SOURCE_KALIS, list(content_keys)),
            )
            col_names = [d[0] for d in cur.description]
            db_rows = {r[0]: dict(zip(col_names, r)) for r in cur.fetchall()}

        if len(db_rows) != 30:
            raise SystemExit(f"POST_REPAIR_ROW_MATCH_COUNT {len(db_rows)}")

        for content_key, db_row in db_rows.items():
            p = planned[content_key]
            plan_payload = p["raw_payload"]

            if db_row["task_source_key"] != p["task_source_key"]:
                raise SystemExit(f"POST_TASK_KEY_MISMATCH {content_key}")

            db_payload = (
                db_row["raw_payload"]
                if isinstance(db_row["raw_payload"], dict)
                else json.loads(db_row["raw_payload"])
            )
            db_vals = [db_payload.get(h, "") for h in C_HEADERS]
            if c_content_key(db_vals) != content_key:
                raise SystemExit(f"POST_HASH_MISMATCH {content_key}")

            for canonical, col in PROJECTION_MAP:
                expected = plan_payload.get(canonical, "") or ""
                actual = db_row.get(col) or ""
                if actual != expected:
                    raise SystemExit(f"POST_PROJECTION_MISMATCH {content_key} {col}")

            verified += 1

        conn.commit()
        return {
            "manifest_rows": len(manifest),
            "concurrency_ok": concurrency_ok,
            "updated": updated,
            "verified": verified,
            "records_before": pre_count,
            "records_after": post_count,
            "transaction": "COMMITTED",
        }
    except SystemExit:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise


def _canonical_payload_sha(payload: dict) -> str:
    """Deterministic sha for concurrency guard: canonical field order, ensure_ascii=False."""
    ordered = {h: payload.get(h) for h in C_HEADERS}
    return hashlib.sha256(
        json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def repair_dry_run(conn, plan: dict) -> dict:
    """Read-only dry-run manifest for the 30 mismatched KALIS records.

    Only SELECT. No UPDATE/INSERT/DELETE. Writes a sanitized TSV manifest with
    sha_prefixes + projection mismatch counts — no payload values.
    """
    from tools.risk02.identity import c_content_key

    planned = {r["content_key"]: r for r in planned_records(plan)}

    manifest_rows: list[dict] = []
    p1_count = 0
    p2_count = 0
    plan_recompute_match = 0
    db_recompute_mismatch = 0
    task_source_key_match = 0
    projection_mismatch_col_counts: dict[str, int] = {}
    concurrent_fingerprints_frozen = 0
    repair_eligible = 0

    scalar_cols = ", ".join(col for _, col in PROJECTION_MAP)

    # 8k rows with 22-scalar-cols is small enough for a client-side cursor.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content_key, task_source_key, raw_payload, "
            + scalar_cols
            + " FROM public.risk_records"
        )
        col_names = [d[0] for d in cur.description]
        rows_iter = cur.fetchall()
        for raw in rows_iter:
            row = dict(zip(col_names, raw))
            content_key = row["content_key"]
            db_task_key = row["task_source_key"]
            db_payload = row["raw_payload"]
            if not isinstance(db_payload, dict):
                db_payload = json.loads(db_payload)

            p = planned.get(content_key)
            if p is None:
                continue

            db_keys = set(db_payload.keys())
            missing_from_db = set(C_HEADERS) - db_keys
            extra_in_db = db_keys - set(C_HEADERS)
            plan_payload = p["raw_payload"]

            payload_field_diffs = 0
            for h in C_HEADERS:
                if h not in db_payload or db_payload[h] != plan_payload[h]:
                    payload_field_diffs += 1
            if missing_from_db or extra_in_db:
                # P1 style: keys drifted (encoding) or any extra keys.
                payload_mismatch = True
                population = "P1"
            else:
                payload_mismatch = payload_field_diffs > 0
                population = "P2" if payload_mismatch else "OK"

            if not payload_mismatch:
                continue  # Only manifest the 30 broken rows.

            if population == "P1":
                p1_count += 1
            else:
                p2_count += 1

            # projection comparison
            projection_mismatch_columns: list[str] = []
            for canonical, col in PROJECTION_MAP:
                planned_val = plan_payload.get(canonical)
                db_val = row.get(col)
                if (db_val or None) != (planned_val or None):
                    projection_mismatch_columns.append(col)
                    projection_mismatch_col_counts[col] = (
                        projection_mismatch_col_counts.get(col, 0) + 1
                    )

            planned_content_recompute = c_content_key(
                [plan_payload[h] for h in C_HEADERS]
            )
            plan_recompute_ok = planned_content_recompute == content_key
            if plan_recompute_ok:
                plan_recompute_match += 1

            db_values_in_canonical_order = [
                "" if db_payload.get(h) is None else str(db_payload.get(h))
                for h in C_HEADERS
            ]
            try:
                db_recompute = c_content_key(db_values_in_canonical_order)
                db_recompute_status = (
                    "MATCH" if db_recompute == content_key else "MISMATCH"
                )
            except ValueError:
                db_recompute_status = "NOT_COMPUTABLE"

            if db_recompute_status == "MISMATCH":
                db_recompute_mismatch += 1

            tsk_match = db_task_key == p["task_source_key"]
            if tsk_match:
                task_source_key_match += 1

            current_sha = _canonical_payload_sha(db_payload)
            planned_sha = _canonical_payload_sha(plan_payload)
            concurrent_fingerprints_frozen += 1

            eligible = (
                plan_recompute_ok
                and db_recompute_status == "MISMATCH"
                and tsk_match
                and payload_mismatch
            )
            ineligibility_reason = ""
            if not eligible:
                reasons = []
                if not plan_recompute_ok:
                    reasons.append("plan_recompute_not_match")
                if db_recompute_status != "MISMATCH":
                    reasons.append(f"db_recompute_{db_recompute_status.lower()}")
                if not tsk_match:
                    reasons.append("task_source_key_mismatch")
                ineligibility_reason = "|".join(reasons)
            else:
                repair_eligible += 1

            manifest_rows.append(
                {
                    "content_key": content_key,
                    "mismatch_population": population,
                    "changed_payload_field_count": str(payload_field_diffs),
                    "projection_mismatch_count": str(len(projection_mismatch_columns)),
                    "projection_mismatch_columns": ",".join(
                        sorted(projection_mismatch_columns)
                    ),
                    "current_payload_sha256": current_sha,
                    "planned_payload_sha256": planned_sha,
                    "planned_content_key_recompute": "MATCH" if plan_recompute_ok else "MISMATCH",
                    "db_payload_recompute": db_recompute_status,
                    "task_source_key_match": "YES" if tsk_match else "NO",
                    "repair_eligible": "YES" if eligible else "NO",
                    "ineligibility_reason": ineligibility_reason,
                }
            )

    manifest_rows.sort(key=lambda r: r["content_key"])
    write_tsv(manifest_rows, REPAIR_DRYRUN_PATH, REPAIR_DRYRUN_FIELDS)

    projection_rows_any_mismatch = sum(
        1 for r in manifest_rows if int(r["projection_mismatch_count"]) > 0
    )

    return {
        "repair_candidates": len(manifest_rows),
        "P1": p1_count,
        "P2": p2_count,
        "plan_key_recompute_match": plan_recompute_match,
        "db_payload_recompute_mismatch": db_recompute_mismatch,
        "task_source_key_match": task_source_key_match,
        "projection_mismatch_rows": projection_rows_any_mismatch,
        "projection_mismatch_columns": projection_mismatch_col_counts,
        "repair_eligible": repair_eligible,
        "concurrent_fingerprints_frozen": concurrent_fingerprints_frozen,
        "manifest_path": str(REPAIR_DRYRUN_PATH),
    }


def diagnose_mismatch_samples(conn, plan: dict) -> dict:
    """Read-only sanitized diagnosis of one P1 sample + one P2 sample.

    No raw values, no full content_keys except the two deterministic samples,
    no field values leak to output.
    """
    from tools.risk02.identity import c_content_key

    planned = {r["content_key"]: r for r in planned_records(plan)}

    p1_keys: list[str] = []
    p2_keys: list[str] = []

    with conn.cursor(name="risk02_diagnose_scan") as cur:
        cur.itersize = 2000
        cur.execute(
            "SELECT content_key, task_source_key, raw_payload FROM public.risk_records"
        )
        for content_key, _tsk, db_payload in cur:
            p = planned.get(content_key)
            if p is None:
                continue
            db_obj = db_payload if isinstance(db_payload, dict) else json.loads(db_payload)
            db_keys = set(db_obj.keys())
            missing = set(C_HEADERS) - db_keys
            extra = db_keys - set(C_HEADERS)
            if missing or extra:
                p1_keys.append(content_key)
            else:
                if any(db_obj[h] != p["raw_payload"][h] for h in C_HEADERS):
                    p2_keys.append(content_key)

    p1_keys.sort()
    p2_keys.sort()
    p1_sample = p1_keys[0] if p1_keys else None
    p2_sample = p2_keys[0] if p2_keys else None

    with conn.cursor() as cur:
        p1_row = _fetch_record(cur, p1_sample) if p1_sample else None
        p2_row = _fetch_record(cur, p2_sample) if p2_sample else None

    return {
        "population_counts": {"P1": len(p1_keys), "P2": len(p2_keys)},
        "p1_sample_key": p1_sample,
        "p2_sample_key": p2_sample,
        "p1": _diagnose_p1(p1_row, planned) if p1_row else None,
        "p2": _diagnose_p2(p2_row, planned) if p2_row else None,
    }


def _fetch_record(cur, content_key: str) -> dict | None:
    cur.execute(
        "SELECT content_key, task_source_key, raw_payload FROM public.risk_records "
        "WHERE content_key = %s",
        (content_key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    payload = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return {
        "content_key": row[0],
        "task_source_key": row[1],
        "raw_payload": payload,
    }


def _decode_unicode_escape(s: str) -> str | None:
    """Best-effort one-layer unicode-escape decode. Returns None on failure."""
    try:
        return bytes(s, "ascii").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return None


def _diagnose_p1(row: dict, planned: dict) -> dict:
    from tools.risk02.identity import c_content_key

    db_payload = row["raw_payload"]
    stored_key = row["content_key"]
    p = planned[stored_key]

    literal_escaped_key_count = 0
    decoded_matches_canonical = 0
    value_matches_after_decode = 0

    canonical_to_db_key: dict[str, str] = {}
    for db_key in db_payload.keys():
        if not isinstance(db_key, str):
            continue
        if "\\u" not in db_key:
            continue
        literal_escaped_key_count += 1
        decoded = _decode_unicode_escape(db_key)
        if decoded is None:
            continue
        if decoded in C_HEADERS:
            decoded_matches_canonical += 1
            canonical_to_db_key[decoded] = db_key

    for canonical in C_HEADERS:
        db_key = canonical_to_db_key.get(canonical)
        if db_key is None:
            continue
        if db_payload[db_key] == p["raw_payload"][canonical]:
            value_matches_after_decode += 1

    plan_recompute = c_content_key([p["raw_payload"][h] for h in C_HEADERS])
    plan_recompute_match = plan_recompute == stored_key

    db_decoded_recompute_status = "NOT_COMPUTABLE"
    if len(canonical_to_db_key) == 19:
        db_decoded_values = [db_payload[canonical_to_db_key[h]] for h in C_HEADERS]
        db_decoded_recompute = c_content_key(db_decoded_values)
        db_decoded_recompute_status = (
            "MATCH" if db_decoded_recompute == stored_key else "MISMATCH"
        )

    db_raw_recompute_status = "NOT_COMPUTABLE"
    if all(h in db_payload for h in C_HEADERS):
        db_raw_values = [db_payload[h] for h in C_HEADERS]
        db_raw_recompute_status = (
            "MATCH" if c_content_key(db_raw_values) == stored_key else "MISMATCH"
        )

    if (
        literal_escaped_key_count == 19
        and decoded_matches_canonical == 19
        and value_matches_after_decode == 19
        and plan_recompute_match
        and db_decoded_recompute_status == "MATCH"
    ):
        root_cause = "POST_IDENTITY_KEY_SERIALIZATION_ONLY"
    elif (
        literal_escaped_key_count == 19
        and decoded_matches_canonical == 19
        and value_matches_after_decode < 19
    ):
        root_cause = "KEY_AND_VALUE_CORRUPTION"
    else:
        root_cause = "UNCLASSIFIED_P1"

    return {
        "literal_escaped_key_count": literal_escaped_key_count,
        "decoded_keys_matching_canonical": decoded_matches_canonical,
        "values_matching_after_key_decode": value_matches_after_decode,
        "plan_content_key_recompute": "MATCH" if plan_recompute_match else "MISMATCH",
        "db_raw_key_recompute": db_raw_recompute_status,
        "db_decoded_key_recompute": db_decoded_recompute_status,
        "root_cause": root_cause,
    }


def _diagnose_p2(row: dict, planned: dict) -> dict:
    import unicodedata
    from tools.risk02.identity import c_content_key

    db_payload = row["raw_payload"]
    stored_key = row["content_key"]
    p = planned[stored_key]

    diffs: list[dict] = []
    for canonical in C_HEADERS:
        db_v = db_payload.get(canonical)
        pl_v = p["raw_payload"].get(canonical)
        if db_v == pl_v:
            continue
        db_s = "" if db_v is None else str(db_v)
        pl_s = "" if pl_v is None else str(pl_v)
        db_hash = hashlib.sha256(db_s.encode("utf-8")).hexdigest()[:12]
        pl_hash = hashlib.sha256(pl_s.encode("utf-8")).hexdigest()[:12]
        diffs.append(
            {
                "field": canonical,
                "plan_length": len(pl_s),
                "db_length": len(db_s),
                "plan_sha_prefix": pl_hash,
                "db_sha_prefix": db_hash,
                "exact_equal": db_s == pl_s,
                "strip_equal": db_s.strip() == pl_s.strip(),
                "nfc_equal": unicodedata.normalize("NFC", db_s)
                == unicodedata.normalize("NFC", pl_s),
                "nfkc_equal": unicodedata.normalize("NFKC", db_s)
                == unicodedata.normalize("NFKC", pl_s),
                "newline_normalized_equal": db_s.replace("\r\n", "\n")
                == pl_s.replace("\r\n", "\n"),
                "whitespace_collapsed_equal": " ".join(db_s.split())
                == " ".join(pl_s.split()),
                "plan_leading_ws": len(pl_s) - len(pl_s.lstrip()),
                "db_leading_ws": len(db_s) - len(db_s.lstrip()),
                "plan_trailing_ws": len(pl_s) - len(pl_s.rstrip()),
                "db_trailing_ws": len(db_s) - len(db_s.rstrip()),
                "plan_contains_tab": "\t" in pl_s,
                "db_contains_tab": "\t" in db_s,
                "plan_contains_newline": ("\n" in pl_s) or ("\r" in pl_s),
                "db_contains_newline": ("\n" in db_s) or ("\r" in db_s),
                "plan_contains_nbsp": " " in pl_s,
                "db_contains_nbsp": " " in db_s,
                "plan_contains_zero_width": any(
                    c in pl_s for c in ("​", "‌", "‍", "﻿")
                ),
                "db_contains_zero_width": any(
                    c in db_s for c in ("​", "‌", "‍", "﻿")
                ),
                "plan_contains_backslash_u": "\\u" in pl_s,
                "db_contains_backslash_u": "\\u" in db_s,
                "plan_contains_control": any(
                    ord(c) < 32 and c not in ("\t", "\n", "\r") for c in pl_s
                ),
                "db_contains_control": any(
                    ord(c) < 32 and c not in ("\t", "\n", "\r") for c in db_s
                ),
            }
        )

    plan_recompute = c_content_key([p["raw_payload"][h] for h in C_HEADERS])
    plan_recompute_match = plan_recompute == stored_key

    db_recompute = c_content_key(
        ["" if db_payload.get(h) is None else str(db_payload.get(h)) for h in C_HEADERS]
    )
    db_recompute_match = db_recompute == stored_key

    # Aggregate normalization results across differing fields
    def _all(fld):
        return all(d[fld] for d in diffs) if diffs else True

    normalization_summary = {
        "exact_equal_all_fields": _all("exact_equal"),
        "strip_equal_all_fields": _all("strip_equal"),
        "nfc_equal_all_fields": _all("nfc_equal"),
        "nfkc_equal_all_fields": _all("nfkc_equal"),
        "newline_normalized_all_fields": _all("newline_normalized_equal"),
        "whitespace_collapsed_all_fields": _all("whitespace_collapsed_equal"),
    }

    if normalization_summary["nfc_equal_all_fields"] or normalization_summary[
        "nfkc_equal_all_fields"
    ]:
        root_cause = "UNICODE_NORMALIZATION_DRIFT"
    elif normalization_summary["strip_equal_all_fields"] or normalization_summary[
        "whitespace_collapsed_all_fields"
    ]:
        root_cause = "WHITESPACE_DRIFT"
    elif not plan_recompute_match:
        root_cause = "PLAN_KEY_INCONSISTENT_WITH_STORED_KEY"
    elif db_recompute_match:
        root_cause = "DB_PAYLOAD_STILL_HASHES_TO_STORED_KEY"
    else:
        root_cause = "POST_IDENTITY_PAYLOAD_MUTATION"

    return {
        "differing_field_count": len(diffs),
        "plan_content_key_recompute": "MATCH" if plan_recompute_match else "MISMATCH",
        "db_payload_recompute": "MATCH" if db_recompute_match else "MISMATCH",
        "normalization_summary": normalization_summary,
        "per_field": diffs,
        "root_cause": root_cause,
    }


def audit_mismatch(conn, plan: dict) -> dict:
    """Read-only field-level mismatch scope audit.

    Compares every production risk_records row against the frozen local plan.
    Emits only aggregate counts — no content_key lists, no raw_payload values.
    """
    planned = {r["content_key"]: r for r in planned_records(plan)}
    total_planned = len(planned)

    production_total = 0
    exact_matches = 0
    unexpected_content_keys = 0
    task_source_key_mismatches = 0
    payload_mismatch_rows = 0

    field_count_dist = {"lt_19": 0, "eq_19": 0, "gt_19": 0}
    plan_field_count_dist = {"lt_19": 0, "eq_19": 0, "gt_19": 0}

    field_missing_in_db: dict[str, int] = {h: 0 for h in C_HEADERS}
    field_extra_in_db: dict[str, int] = {}
    value_different: dict[str, int] = {h: 0 for h in C_HEADERS}
    type_different: dict[str, int] = {h: 0 for h in C_HEADERS}

    seen_planned_keys: set[str] = set()

    with conn.cursor(name="risk02_audit_scan") as cur:
        cur.itersize = 2000
        cur.execute(
            "SELECT content_key, task_source_key, raw_payload FROM public.risk_records"
        )
        for content_key, db_task_key, db_payload in cur:
            production_total += 1

            p = planned.get(content_key)
            if p is None:
                unexpected_content_keys += 1
                continue
            seen_planned_keys.add(content_key)

            db_obj = db_payload if isinstance(db_payload, dict) else json.loads(db_payload)
            plan_obj = p["raw_payload"]

            _tally_field_count(db_obj, field_count_dist)
            _tally_field_count(plan_obj, plan_field_count_dist)

            row_task_mismatch = db_task_key != p["task_source_key"]
            if row_task_mismatch:
                task_source_key_mismatches += 1

            row_payload_mismatch = False
            for field in C_HEADERS:
                in_db = field in db_obj
                in_plan = field in plan_obj
                if in_plan and not in_db:
                    field_missing_in_db[field] += 1
                    row_payload_mismatch = True
                elif in_db and in_plan:
                    dv, pv = db_obj[field], plan_obj[field]
                    if type(dv) is not type(pv):
                        type_different[field] += 1
                        row_payload_mismatch = True
                    elif dv != pv:
                        value_different[field] += 1
                        row_payload_mismatch = True
            for field in db_obj.keys():
                if field not in C_HEADERS and field not in plan_obj:
                    field_extra_in_db[field] = field_extra_in_db.get(field, 0) + 1
                    row_payload_mismatch = True
                elif field not in C_HEADERS and field in plan_obj:
                    # Extra field appears in both (schema drift); treat as extra
                    field_extra_in_db[field] = field_extra_in_db.get(field, 0) + 1
                    row_payload_mismatch = True

            if row_payload_mismatch:
                payload_mismatch_rows += 1
            if not row_payload_mismatch and not row_task_mismatch:
                exact_matches += 1

    missing_planned_keys = total_planned - len(seen_planned_keys)

    return {
        "planned_total": total_planned,
        "production_total": production_total,
        "checked": production_total,
        "exact_matches": exact_matches,
        "unexpected_content_keys": unexpected_content_keys,
        "task_source_key_mismatches": task_source_key_mismatches,
        "payload_mismatch_rows": payload_mismatch_rows,
        "planned_keys_not_yet_in_db": missing_planned_keys,
        "db_payload_field_count": field_count_dist,
        "plan_payload_field_count": plan_field_count_dist,
        "field_missing_in_db": {k: v for k, v in field_missing_in_db.items() if v},
        "field_extra_in_db": field_extra_in_db,
        "value_different": {k: v for k, v in value_different.items() if v},
        "type_different": {k: v for k, v in type_different.items() if v},
        "field_missing_in_db_all": field_missing_in_db,
        "value_different_all": value_different,
        "type_different_all": type_different,
    }


def _tally_field_count(payload: dict, bucket: dict) -> None:
    n = len(payload)
    if n < 19:
        bucket["lt_19"] += 1
    elif n == 19:
        bucket["eq_19"] += 1
    else:
        bucket["gt_19"] += 1


def _verify_existing_records(conn, plan: dict) -> None:
    planned = {r["content_key"]: r for r in planned_records(plan)}
    with conn.cursor(name="risk02_records_scan") as cur:
        cur.itersize = 2000
        cur.execute(
            "SELECT content_key, task_source_key, raw_payload FROM public.risk_records"
        )
        for row in cur:
            content_key, task_source_key, raw_payload = row
            p = planned.get(content_key)
            if p is None:
                raise SystemExit(f"UNEXPECTED_CONTENT_KEY {content_key}")
            if task_source_key != p["task_source_key"]:
                raise SystemExit(f"RECORD_TASK_MISMATCH {content_key}")
            observed = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
            if observed != p["raw_payload"]:
                raise SystemExit(f"RECORD_PAYLOAD_MISMATCH {content_key}")


def ingest_records(conn, plan: dict) -> None:
    records = planned_records(plan)
    total = len(records)
    if total != EXPECTED_RECORDS:
        raise SystemExit(f"PLAN_RECORD_COUNT_DRIFT {total}")
    processed = 0
    batches_since_commit = 0
    for chunk in _chunks(records, RECORD_BATCH):
        sql = records_insert_sql(chunk)
        with conn.cursor() as cur:
            cur.execute(sql)
        processed += len(chunk)
        batches_since_commit += 1
        if batches_since_commit >= COMMIT_EVERY_N_BATCHES:
            conn.commit()
            batches_since_commit = 0
            _emit(f"records {processed}/{total}")
    conn.commit()
    _emit(f"records {processed}/{total} done")


def ingest_memberships(conn, plan: dict, snapshot_by_source: dict[str, str]) -> None:
    memberships = planned_memberships(plan)
    total = len(memberships)
    if total != EXPECTED_MEMBERSHIPS:
        raise SystemExit(f"PLAN_MEMBERSHIP_COUNT_DRIFT {total}")

    by_source: dict[str, list[dict]] = {
        SOURCE_CIC_W: [],
        SOURCE_KOSHA: [],
        SOURCE_KALIS: [],
    }
    for m in memberships:
        by_source[m["source_id"]].append(m)

    processed = 0
    batches_since_commit = 0
    for source_id in (SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS):
        rows = by_source[source_id]
        snap = snapshot_by_source[source_id]
        for chunk in _chunks(rows, MEMBERSHIP_BATCH):
            sql = memberships_insert_sql(snap, source_id, chunk)
            with conn.cursor() as cur:
                cur.execute(sql)
            processed += len(chunk)
            batches_since_commit += 1
            if batches_since_commit >= COMMIT_EVERY_N_BATCHES:
                conn.commit()
                batches_since_commit = 0
                _emit(f"memberships {processed}/{total}")
        conn.commit()
    conn.commit()
    _emit(f"memberships {processed}/{total} done")


def _post_record_gate(conn) -> None:
    with conn.cursor() as cur:
        n = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
        dup = _fetch_scalar(
            cur,
            "SELECT count(*) FROM (SELECT source_id, content_key, count(*) c "
            "FROM public.risk_records GROUP BY 1, 2 HAVING count(*) > 1) x",
        )
        orphan = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_records r LEFT JOIN public.risk_source_nodes n "
            "ON n.source_id = r.source_id AND n.source_key = r.task_source_key "
            "WHERE n.source_id IS NULL",
        )
    if n != EXPECTED_RECORDS:
        raise SystemExit(f"RECORD_GATE_FAIL count={n}")
    if dup:
        raise SystemExit(f"RECORD_GATE_FAIL duplicate={dup}")
    if orphan:
        raise SystemExit(f"RECORD_GATE_FAIL orphan={orphan}")


def _post_membership_gate(conn) -> None:
    with conn.cursor() as cur:
        n = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_snapshot_memberships")
        node_orphan = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_snapshot_memberships m "
            "LEFT JOIN public.risk_source_nodes sn "
            "ON sn.source_id = m.source_id AND sn.source_key = m.member_key "
            "WHERE m.member_kind = 'NODE' AND sn.source_id IS NULL",
        )
        record_orphan = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_snapshot_memberships m "
            "LEFT JOIN public.risk_records r "
            "ON r.source_id = m.source_id AND r.content_key = m.member_key "
            "WHERE m.member_kind = 'RECORD' AND r.source_id IS NULL",
        )
    if n != EXPECTED_MEMBERSHIPS:
        raise SystemExit(f"MEMBERSHIP_GATE_FAIL count={n}")
    if node_orphan:
        raise SystemExit(f"MEMBERSHIP_GATE_FAIL node_orphan={node_orphan}")
    if record_orphan:
        raise SystemExit(f"MEMBERSHIP_GATE_FAIL record_orphan={record_orphan}")


def _transition(conn, from_status: str, to_status: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.risk_snapshots SET status = %s "
            "WHERE status = %s AND source_id IN (%s, %s, %s) "
            "RETURNING id::text, source_id",
            (to_status, from_status, SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS),
        )
        rows = [{"id": r[0], "source_id": r[1]} for r in cur.fetchall()]
    return rows


def _pre_transition_audit(conn) -> dict:
    """Full invariance gate: counts, orphans, canonical, mapping, sector, occurrence."""
    audit = verify_final(conn)
    _assert_invariants(audit, require_accepted=False)
    return audit


def _run_transitions(conn) -> None:
    accepted_now = _snapshots_by_status(conn, "ACCEPTED")
    if accepted_now == {SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS}:
        _emit("snapshots already ACCEPTED — nothing to do")
        return

    _pre_transition_audit(conn)

    staged = _snapshots_by_status(conn, "STAGED")
    validated = _snapshots_by_status(conn, "VALIDATED")

    if staged == {SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS} and not validated:
        with conn:
            rows = _transition(conn, "STAGED", "VALIDATED")
        if len(rows) != 3:
            raise SystemExit(f"STAGED_TO_VALIDATED_COUNT {len(rows)}")
        _emit(f"STAGED→VALIDATED {len(rows)}")
    elif not staged and validated == {SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS}:
        _emit("snapshots already VALIDATED — skipping STAGED transition")
    else:
        raise SystemExit(
            f"UNEXPECTED_TRANSITION_STATE staged={sorted(staged)} "
            f"validated={sorted(validated)} accepted={sorted(accepted_now)}"
        )

    # Re-audit in VALIDATED state.
    _pre_transition_audit(conn)
    validated_after = _snapshots_by_status(conn, "VALIDATED")
    if validated_after != {SOURCE_CIC_W, SOURCE_KOSHA, SOURCE_KALIS}:
        raise SystemExit(f"VALIDATED_STATE_INCOMPLETE {sorted(validated_after)}")

    with conn:
        rows = _transition(conn, "VALIDATED", "ACCEPTED")
    if len(rows) != 3:
        raise SystemExit(f"VALIDATED_TO_ACCEPTED_COUNT {len(rows)}")
    _emit(f"VALIDATED→ACCEPTED {len(rows)}")

    # Final accepted-view check.
    with conn.cursor() as cur:
        accepted_view = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_accepted_snapshots")
    if accepted_view != 3:
        raise SystemExit(f"POST_ACCEPTED_VIEW_COUNT {accepted_view}")


def _snapshots_by_status(conn, status: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id FROM public.risk_snapshots WHERE status = %s",
            (status,),
        )
        return {r[0] for r in cur.fetchall()}


def _verify_kosha_identity_hold(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT metadata->>'identity_status' FROM public.risk_snapshots "
            "WHERE source_id = %s",
            (SOURCE_KOSHA,),
        )
        row = cur.fetchone()
    status = row[0] if row else None
    if status != "HOLD":
        raise SystemExit(f"KOSHA_IDENTITY_STATUS_DRIFT expected=HOLD got={status!r}")


def _full_row_validation(conn, plan: dict) -> tuple[int, int]:
    """Walk all risk_source_nodes + risk_records against plan. Returns (nodes, records) counts."""
    _verify_existing_nodes(conn, plan)
    _verify_existing_records(conn, plan)
    with conn.cursor() as cur:
        n = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_nodes")
        r = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
    return n, r


def verify_final(conn) -> dict:
    with conn.cursor() as cur:
        nodes = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_nodes")
        records = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_records")
        memberships = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_snapshot_memberships"
        )
        node_orphan = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_snapshot_memberships m "
            "LEFT JOIN public.risk_source_nodes sn "
            "ON sn.source_id = m.source_id AND sn.source_key = m.member_key "
            "WHERE m.member_kind = 'NODE' AND sn.source_id IS NULL",
        )
        record_orphan = _fetch_scalar(
            cur,
            "SELECT count(*) FROM public.risk_snapshot_memberships m "
            "LEFT JOIN public.risk_records r "
            "ON r.source_id = m.source_id AND r.content_key = m.member_key "
            "WHERE m.member_kind = 'RECORD' AND r.source_id IS NULL",
        )
        accepted = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_accepted_snapshots")
        mappings = _fetch_scalar(cur, "SELECT count(*) FROM public.risk_source_mappings")
        sectors = _fetch_scalar(
            cur, "SELECT count(*) FROM public.risk_canonical_node_sectors"
        )
        canonical_by_status = {
            r["status"]: r["n"]
            for r in _fetch_rows(
                cur,
                "SELECT status, count(*) AS n FROM public.risk_canonical_nodes "
                "GROUP BY status",
            )
        }
        breakdown = _fetch_rows(
            cur,
            "SELECT source_id, member_kind, count(*) AS n, "
            "sum(occurrence_count) AS occ "
            "FROM public.risk_snapshot_memberships GROUP BY 1, 2 ORDER BY 1, 2",
        )
        kosha_detail = _fetch_rows(
            cur,
            "SELECT count(*) AS n, sum(m.occurrence_count) AS occ, "
            "sum(CASE WHEN m.occurrence_count = 3 THEN 1 ELSE 0 END) AS triples "
            "FROM public.risk_snapshot_memberships m "
            "JOIN public.risk_source_nodes n "
            "ON n.source_id = m.source_id AND n.source_key = m.member_key "
            "WHERE m.member_kind = 'NODE' AND m.source_id = %s "
            "AND n.node_type = 'DETAIL_PROCESS'",
            (SOURCE_KOSHA,),
        )
    return {
        "nodes": nodes,
        "records": records,
        "memberships": memberships,
        "node_orphan": node_orphan,
        "record_orphan": record_orphan,
        "accepted": accepted,
        "mappings": mappings,
        "canonical_node_sectors": sectors,
        "canonical_by_status": canonical_by_status,
        "breakdown": breakdown,
        "kosha_detail_process": kosha_detail[0] if kosha_detail else None,
    }


def _assert_invariants(audit: dict, require_accepted: bool = True) -> None:
    if audit["nodes"] != EXPECTED_NODES:
        raise SystemExit(f"FINAL_NODE_DRIFT {audit['nodes']}")
    if audit["records"] != EXPECTED_RECORDS:
        raise SystemExit(f"FINAL_RECORD_DRIFT {audit['records']}")
    if audit["memberships"] != EXPECTED_MEMBERSHIPS:
        raise SystemExit(f"FINAL_MEMBERSHIP_DRIFT {audit['memberships']}")
    if audit["node_orphan"] or audit["record_orphan"]:
        raise SystemExit(f"FINAL_ORPHAN {audit}")
    if require_accepted and audit["accepted"] != 3:
        raise SystemExit(f"FINAL_ACCEPTED_DRIFT {audit['accepted']}")
    if audit["mappings"] != 0:
        raise SystemExit(f"FINAL_MAPPING_DRIFT {audit['mappings']}")
    if audit["canonical_node_sectors"] != 0:
        raise SystemExit(f"FINAL_SECTOR_DRIFT {audit['canonical_node_sectors']}")
    if (
        audit["canonical_by_status"].get("DRAFT", 0) != 1110
        or audit["canonical_by_status"].get("ACTIVE", 0) != 0
    ):
        raise SystemExit(f"FINAL_CANONICAL_DRIFT {audit['canonical_by_status']}")
    kd = audit["kosha_detail_process"]
    if not kd or kd["occ"] != KOSHA_LEAF_OCCURRENCE_SUM or kd["triples"] != 3:
        raise SystemExit(f"KOSHA_DETAIL_PROCESS_DRIFT {kd}")
    breakdown_expected = {
        (SOURCE_CIC_W, "NODE"): (1722, 1722),
        (SOURCE_KOSHA, "NODE"): (B_NODES, KOSHA_NODE_OCCURRENCE_SUM_TOTAL),
        (SOURCE_KALIS, "NODE"): (C_NODES, C_NODES),
        (SOURCE_KALIS, "RECORD"): (EXPECTED_RECORDS, KALIS_RECORD_OCCURRENCE_SUM),
    }
    breakdown_seen = {
        (r["source_id"], r["member_kind"]): (r["n"], r["occ"])
        for r in audit["breakdown"]
    }
    if breakdown_seen != breakdown_expected:
        raise SystemExit(f"BREAKDOWN_DRIFT expected={breakdown_expected} got={breakdown_seen}")


def _assert_final(audit: dict) -> None:
    _assert_invariants(audit, require_accepted=True)


def write_final_receipt(plan: dict, snapshot_by_source: dict[str, str]) -> str:
    rows = [
        {
            "source_id": SOURCE_CIC_W,
            "snapshot_id": snapshot_by_source[SOURCE_CIC_W],
            "snapshot_status": "ACCEPTED",
            "source_sha256": A_SHA256,
            "node_count": "1722",
            "record_count": "0",
            "membership_count": "1722",
            "occurrence_sum": "1722",
            "validation_status": "PASS",
        },
        {
            "source_id": SOURCE_KOSHA,
            "snapshot_id": snapshot_by_source[SOURCE_KOSHA],
            "snapshot_status": "ACCEPTED",
            "source_sha256": B_SHA256,
            "node_count": str(B_NODES),
            "record_count": "0",
            "membership_count": str(B_NODES),
            "occurrence_sum": str(KOSHA_NODE_OCCURRENCE_SUM_TOTAL),
            "validation_status": "PASS",
        },
        {
            "source_id": SOURCE_KALIS,
            "snapshot_id": snapshot_by_source[SOURCE_KALIS],
            "snapshot_status": "ACCEPTED",
            "source_sha256": C_SHA256,
            "node_count": str(C_NODES),
            "record_count": str(EXPECTED_RECORDS),
            "membership_count": str(C_NODES + EXPECTED_RECORDS),
            "occurrence_sum": str(KALIS_RECORD_OCCURRENCE_SUM),
            "validation_status": "PASS",
        },
    ]
    write_tsv(rows, RECEIPT_PATH, RECEIPT_FIELDS)
    sha = receipt_sha(load_tsv(RECEIPT_PATH))
    extra = {
        "production_execution": "EXECUTED",
        "verdict": "SOURCE_CORE_INGESTED / EVIDENCE_READY",
        "accepted": "3",
        "nodes": str(EXPECTED_NODES),
        "records": str(EXPECTED_RECORDS),
        "memberships": str(EXPECTED_MEMBERSHIPS),
        "receipt_sha": sha,
    }
    report = render_report(plan, extra) + _repair_evidence_block()
    REPORT_PATH.write_text(report, encoding="utf-8")
    return sha


def _repair_evidence_block() -> str:
    return f"""

---

## Repair Evidence (RISK-02 W1)

```text
partial ingest anomaly           = 30 rows in initial 8010 (Cursor MCP path)
repair                           = 30 targeted rows in one transaction
authority                        = frozen local plan
RISK02 DETERMINISM SHA           = {FROZEN_DETERMINISM_SHA}
manifest                         = {REPAIR_DRYRUN_PATH}
concurrency guard                = 30 / 30 PASS
post-repair full exact scan      = {EXPECTED_RECORDS} / {EXPECTED_RECORDS} PASS
KOSHA identity_status            = HOLD / preserved through ACCEPTED
KOSHA DETAIL_PROCESS occurrence  = {KOSHA_LEAF_OCCURRENCE_SUM}
KOSHA all-node occurrence sum    = {KOSHA_NODE_OCCURRENCE_SUM_TOTAL}
KALIS record occurrence sum      = {KALIS_RECORD_OCCURRENCE_SUM}
```
"""


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-RISK-02-INGEST-001-R1 local executor"
    )
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--audit-mismatch",
        action="store_true",
        help="Read-only field-level mismatch scope audit. No writes, no values.",
    )
    parser.add_argument(
        "--diagnose-mismatch-samples",
        action="store_true",
        help="Read-only sanitized root-cause diagnosis on 1 P1 + 1 P2 sample.",
    )
    parser.add_argument(
        "--repair-dry-run",
        action="store_true",
        help="Read-only repair manifest for the 30 mismatched rows. No writes.",
    )
    parser.add_argument(
        "--repair-execute",
        action="store_true",
        help=(
            "W1: transactional UPDATE of the 30 rows named in the dry-run manifest. "
            "SHA concurrency guard per row; verifies in-transaction before commit."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not any(
        [
            args.preflight,
            args.resume,
            args.verify,
            args.audit_mismatch,
            args.diagnose_mismatch_samples,
            args.repair_dry_run,
            args.repair_execute,
        ]
    ):
        parser.print_help()
        return 2

    plan = two_run_plan()
    if plan["determinism_sha"] != FROZEN_DETERMINISM_SHA:
        raise SystemExit(f"DETERMINISM_SHA_DRIFT {plan['determinism_sha']}")

    conn = _connect()
    try:
        if args.audit_mismatch:
            audit = audit_mismatch(conn, plan)
            _emit_audit(audit)
            return 0

        if args.diagnose_mismatch_samples:
            result = diagnose_mismatch_samples(conn, plan)
            _emit_diagnose(result)
            return 0

        if args.repair_dry_run:
            result = repair_dry_run(conn, plan)
            _emit_repair_dryrun(result)
            return 0

        if args.repair_execute:
            result = repair_execute(conn, plan)
            _emit_repair_execute(result)
            return 0

        if args.preflight or args.resume:
            audit = preflight(conn, plan)
            _emit(
                "preflight "
                + json.dumps(
                    {
                        "records": audit["records"],
                        "memberships": audit["memberships"],
                        "accepted": audit["accepted"],
                        "mappings": audit["mappings"],
                        "canonical_by_status": audit["canonical_by_status"],
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )

        if args.resume:
            ingest_records(conn, plan)
            _post_record_gate(conn)
            snap = _snapshot_map(conn)
            ingest_memberships(conn, plan, snap)
            _run_transitions(conn)

        if args.verify:
            full_nodes, full_records = _full_row_validation(conn, plan)
            audit = verify_final(conn)
            _assert_final(audit)
            _verify_kosha_identity_hold(conn)
            snap = _snapshot_map(conn)
            sha = write_final_receipt(plan, snap)
            _emit(
                "verify "
                + json.dumps(
                    {
                        "full_record_scan": f"{full_records}/{EXPECTED_RECORDS}",
                        "full_node_scan": f"{full_nodes}/{EXPECTED_NODES}",
                        "nodes": audit["nodes"],
                        "records": audit["records"],
                        "memberships": audit["memberships"],
                        "accepted": audit["accepted"],
                        "kosha_detail_process": audit["kosha_detail_process"],
                        "kosha_identity_status": "HOLD",
                        "receipt_sha": sha,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
