"""Delta Enrichment — snapshot에 delta/evolution 정보 추가."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.situation_evolution import compute_situation_evolution

def apply_delta_enrichment(snapshot: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    evolution = compute_situation_evolution(previous, snapshot)
    snapshot["previous_snapshot_id"] = previous.get("id") if previous else None
    snapshot["delta_type"] = evolution.get("delta_type", "new")
    snapshot["lifecycle_transition"] = evolution.get("lifecycle_transition")
    snapshot["risk_direction"] = evolution.get("risk_direction", "stable")
    snapshot["change_summary"] = evolution.get("change_summary", "")
    return snapshot
