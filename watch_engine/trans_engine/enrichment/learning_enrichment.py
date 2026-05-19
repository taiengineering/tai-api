"""Learning Enrichment."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.operational_memory import build_operational_memory

async def apply_learning_enrichment(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        situation_id = snapshot.get("situation_id", "")
        memory = await build_operational_memory(situation_id)
        snapshot["learned_effectiveness"] = memory.get("learned_effectiveness")
        snapshot["recurrence_risk"] = memory.get("recurrence_risk", "low")
        snapshot["operational_memory_notes"] = " ".join(memory.get("memory_notes", []))
        if memory.get("outcomes"):
            outcomes = memory["outcomes"]
            snapshot["last_response_outcome"] = max(outcomes, key=outcomes.get) if outcomes else None
    except Exception:
        pass
    return snapshot
