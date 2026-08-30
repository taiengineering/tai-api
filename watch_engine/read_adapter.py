"""Common Event read adapter (§19) — logical view over legacy + v1 rows.

Pure, read-only projection. NEVER writes. NEVER fabricates a legacy row into a
precise v1 event. Consumers that only need legacy fields (bridge/integrity/
snapshot) keep reading them directly; this adapter is optional sugar for a
unified logical shape.

Mapping rules (§19):
    logical_event_name  = physical event_name if present
                          else a clearly-marked legacy synthesized label
    logical_recorded_at = created_at
    logical_display_time = occurred_at if present else created_at
    actor (canonical)   = actor_kind/actor_ref if present else LEGACY / UNKNOWN
"""

from __future__ import annotations

from typing import Any, Optional


def _synth_legacy_event_name(flow_key: Optional[str], event_type: Optional[str]) -> str:
    """Best-effort human label for a legacy row. Deliberately prefixed with
    'LEGACY:' so it can never be mistaken for an authoritative v1 event_name."""
    parts = [p for p in (flow_key, event_type) if p]
    raw = "_".join(str(p) for p in parts) if parts else "EVENT"
    return "LEGACY:" + raw


def logical_event(row: dict[str, Any]) -> dict[str, Any]:
    """Project a business_event row (dict) into a logical Common Event shape.

    Accepts both legacy rows (no canonical columns) and v1 rows. Does not
    require canonical fields to be present.
    """
    physical_name = row.get("event_name")
    is_v1 = row.get("event_version") is not None
    return {
        "is_contract_v1": is_v1,
        "logical_event_name": physical_name
        if physical_name
        else _synth_legacy_event_name(row.get("flow_key"), row.get("event_type")),
        "logical_recorded_at": row.get("created_at"),
        "logical_display_time": row.get("occurred_at") or row.get("created_at"),
        "logical_actor_kind": row.get("actor_kind") or "LEGACY",
        "logical_actor_ref": row.get("actor_ref") or "UNKNOWN",
        # Legacy fields remain first-class and untouched.
        "legacy_event_type": row.get("event_type"),
        "legacy_result": row.get("result"),
        "outcome": row.get("outcome"),
        "namespace": row.get("tenant_id"),
        "service": row.get("service_key"),
        "environment": row.get("environment"),
        "trace_id": row.get("trace_id"),
    }
