"""Chaos Engine — \ud655\ub960 \uae30\ubc18 \uc7a5\uc560 \uc8fc\uc785."""

import random
import logging
from typing import Optional

logger = logging.getLogger("watch_engine.synthetic_runtime.chaos")

CHAOS_TYPES = {
    "timeout":           {"weight": 20, "severity": "WARNING",  "event": "workflow.timeout"},
    "slow_response":     {"weight": 15, "severity": "INFO",     "event": "step.failed"},
    "malformed_payload": {"weight": 5,  "severity": "WARNING",  "event": "step.failed"},
    "duplicate_event":   {"weight": 8,  "severity": "INFO",     "event": "workflow.retried"},
    "retry_storm":       {"weight": 5,  "severity": "WARNING",  "event": "workflow.retried"},
    "selector_not_found":{"weight": 10, "severity": "WARNING",  "event": "watch.integrity_detected"},
    "schema_mismatch":   {"weight": 12, "severity": "WARNING",  "event": "watch.integrity_detected"},
    "partial_failure":   {"weight": 10, "severity": "WARNING",  "event": "step.failed"},
    "stale_state":       {"weight": 8,  "severity": "INFO",     "event": "step.failed"},
    "workflow_blockage": {"weight": 7,  "severity": "CRITICAL", "event": "workflow.blocked"},
}


def inject_chaos(
    tenant_id: str,
    flow_key: str,
    chaos_probability: float = 0.15,
) -> Optional[dict]:
    """\ud655\ub960 \uae30\ubc18 chaos \uc8fc\uc785. None\uc774\uba74 \uc815\uc0c1."""
    if random.random() > chaos_probability:
        return None

    types = list(CHAOS_TYPES.keys())
    weights = [CHAOS_TYPES[t]["weight"] for t in types]
    chosen = random.choices(types, weights=weights, k=1)[0]
    info = CHAOS_TYPES[chosen]

    logger.debug("[CHAOS] %s tenant=%s flow=%s", chosen, tenant_id, flow_key)

    return {
        "chaos_type": chosen,
        "event_type": info["event"],
        "severity": info["severity"],
        "description": f"[CHAOS] {chosen} on {flow_key}",
    }
