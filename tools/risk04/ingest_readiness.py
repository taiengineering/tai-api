"""Source ingest dry-run readiness. Production write = 0."""
from __future__ import annotations

import json
from pathlib import Path

from tools.risk02.contract import C_SHA256
from tools.risk02.identity import sha256_parts
from tools.risk03.contract import B_IDENTITY, B_LEAF_OCCURRENCE_SUM, B_PATH_IDENTITIES
from tools.risk04.contract import (
    CANONICAL_INGEST_ORDER,
    REQUIRED_TABLES,
    SOURCE_INGEST_ORDER,
)

RISK02_SQL = Path("supabase/migrations/20260915_risk_source_catalog.sql")
RISK03_SQL = Path("supabase/migrations/20260916_risk_canonical_mapping.sql")


def migration_order_ok() -> bool:
    return RISK02_SQL.name < RISK03_SQL.name and RISK02_SQL.exists() and RISK03_SQL.exists()


def schema_tables_present() -> dict[str, bool]:
    text = RISK02_SQL.read_text(encoding="utf-8") + RISK03_SQL.read_text(encoding="utf-8")
    return {table: f"public.{table}" in text for table in REQUIRED_TABLES}


def source_ingest_readiness(source_plan: dict) -> dict:
    integrity = source_plan["integrity"]
    a = source_plan["A"]
    b = source_plan["B"]
    c = source_plan["C"]
    orphan = (
        integrity["A_orphan_parent"]
        + integrity["B_orphan_parent"]
        + integrity["C_orphan_task_link"]
        + integrity["snapshot_membership_orphan"]
    )
    occurrence_ok = (
        b["leaf_occurrence_sum"] == B_LEAF_OCCURRENCE_SUM
        and b["path_identities"] == B_PATH_IDENTITIES
        and b["identity"] == B_IDENTITY
        and c["occurrence_sum"] == c["raw_rows"]
        and c["sha256"] == C_SHA256
    )
    if orphan != 0 or not occurrence_ok:
        status = "NOT_READY"
    elif b["identity"] == "HOLD":
        status = "READY_WITH_HOLD"
    else:
        status = "READY"
    return {
        "status": status,
        "source_ingest_order": list(SOURCE_INGEST_ORDER),
        "canonical_ingest_order": list(CANONICAL_INGEST_ORDER),
        "canonical_ingest": "NOT AUTHORIZED",
        "mapping_ingest": "NOT AUTHORIZED",
        "migration_apply": 0,
        "source_node_orphan": integrity["A_orphan_parent"] + integrity["B_orphan_parent"],
        "snapshot_orphan": integrity["snapshot_membership_orphan"],
        "membership_orphan": integrity["snapshot_membership_orphan"],
        "C_task_orphan": integrity["C_orphan_task_link"],
        "A_nodes": a["nodes"],
        "B_raw_rows": b["rows"],
        "B_path_identities": b["path_identities"],
        "B_leaf_occurrence_sum": b["leaf_occurrence_sum"],
        "B_identity": b["identity"],
        "C_raw_rows": c["raw_rows"],
        "C_unique_content": c["unique_content"],
        "C_membership_rows": c["membership_rows"],
        "C_occurrence_sum": c["occurrence_sum"],
        "C_sha256": c["sha256"],
        "metadata_drift": c.get("metadata_drift"),
        "tables": schema_tables_present(),
        "migration_order_ok": migration_order_ok(),
        "db_write": 0,
    }


def readiness_sha(payload: dict) -> str:
    slim = {k: v for k, v in payload.items() if k != "tables"}
    slim["tables"] = payload["tables"]
    return sha256_parts(json.dumps(slim, ensure_ascii=False, sort_keys=True))
