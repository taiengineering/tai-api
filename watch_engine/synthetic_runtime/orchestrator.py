"""Orchestrator — Synthetic Tick \uc2e4\ud589.

\ub9e4 tick\ub9c8\ub2e4:
1. 20\uac1c tenant \uc21c\ud68c
2. Persona \uae30\ubc18 workflow \uc2e4\ud589 \uc5ec\ubd80 \uacb0\uc815
3. Scenario \uc120\ud0dd + \uc2e4\ud589
4. Chaos \uc8fc\uc785
5. emit_runtime_event \uacbd\uc720 \uc800\uc7a5
"""

import random
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("watch_engine.synthetic_runtime.orchestrator")


def run_synthetic_tick(sb=None) -> dict:
    """1\ud68c synthetic tick \uc2e4\ud589."""
    from watch_engine.synthetic_runtime.personas import TENANT_PERSONAS, PERSONAS
    from watch_engine.synthetic_runtime.scenarios import SCENARIOS
    from watch_engine.synthetic_runtime.chaos_engine import inject_chaos
    from watch_engine.runtime_bus import emit_runtime_event, make_context

    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()

    now = datetime.now(timezone.utc)
    hour = now.hour
    stats = {"tenants": 0, "workflows": 0, "events": 0, "chaos": 0, "abandoned": 0, "failed": 0}

    scenario_keys = list(SCENARIOS.keys())

    for tenant_id, persona_key in TENANT_PERSONAS.items():
        persona = PERSONAS.get(persona_key)
        if not persona:
            continue

        stats["tenants"] += 1

        # \uadfc\ubb34\uc2dc\uac04 \uccb4\ud06c
        wh = persona["working_hours"]
        if wh[0] < wh[1]:
            if not (wh[0] <= hour < wh[1]):
                continue
        else:  # \uc57c\uac04 (22~6)
            if not (hour >= wh[0] or hour < wh[1]):
                continue

        # workflow \ube48\ub3c4 \uae30\ubc18 \uc2e4\ud589 \uc5ec\ubd80
        freq = persona["workflow_freq"]
        if random.random() > freq * 0.3:  # tick\ub2f9 30% * freq \ud655\ub960
            continue

        # burst \uccb4\ud06c
        run_count = 1
        if random.random() < persona["burst_rate"]:
            run_count = random.randint(3, 8)

        for _ in range(run_count):
            scenario_key = random.choice(scenario_keys)
            scenario = SCENARIOS[scenario_key]
            trace_id = f"syn_{tenant_id}_{uuid.uuid4().hex[:8]}"

            ctx = make_context(
                runtime="workflow",
                tenant_id=tenant_id,
                actor_id=f"synthetic_{persona_key}",
                environment="mock",
            )

            # workflow.started
            emit_runtime_event(ctx, {
                "event_type": "workflow.started",
                "flow_key": scenario["flow_key"],
                "trace_id": trace_id,
                "severity": "INFO",
                "tenant_id": tenant_id,
                "environment": "mock",
            }, sb=sb)
            stats["events"] += 1

            # \uc911\ub3c4 \ud3ec\uae30 \uccb4\ud06c
            if random.random() < persona["abandon_rate"]:
                emit_runtime_event(ctx, {
                    "event_type": "workflow.blocked",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "WARNING",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                    "description": "[SYNTHETIC] user abandoned flow",
                }, sb=sb)
                stats["abandoned"] += 1
                stats["events"] += 1
                continue

            # Step \uc2e4\ud589
            flow_failed = False
            for step in scenario["steps"]:
                step_fail = random.random() < (step["fail_rate"] + persona["retry_rate"])
                step_timeout = random.random() < persona["timeout_rate"]

                if step_timeout:
                    emit_runtime_event(ctx, {
                        "event_type": "workflow.timeout",
                        "flow_key": scenario["flow_key"],
                        "step_key": step["step_key"],
                        "step_order": step["order"],
                        "trace_id": trace_id,
                        "severity": "WARNING",
                        "tenant_id": tenant_id,
                        "environment": "mock",
                    }, sb=sb)
                    stats["events"] += 1
                    flow_failed = True
                    break

                if step_fail:
                    emit_runtime_event(ctx, {
                        "event_type": "step.failed",
                        "flow_key": scenario["flow_key"],
                        "step_key": step["step_key"],
                        "step_order": step["order"],
                        "trace_id": trace_id,
                        "severity": "WARNING",
                        "tenant_id": tenant_id,
                        "environment": "mock",
                    }, sb=sb)
                    stats["events"] += 1
                    stats["failed"] += 1
                    flow_failed = True
                    break

                # step \uc131\uacf5
                emit_runtime_event(ctx, {
                    "event_type": "step.completed",
                    "flow_key": scenario["flow_key"],
                    "step_key": step["step_key"],
                    "step_order": step["order"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
                stats["events"] += 1

            # Chaos injection
            chaos = inject_chaos(tenant_id, scenario["flow_key"],
                                 chaos_probability=persona["degradation_sensitivity"])
            if chaos:
                ctrl_ctx = make_context("control", tenant_id=tenant_id, environment="mock")
                emit_runtime_event(ctrl_ctx, {
                    "event_type": chaos["event_type"],
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": chaos["severity"],
                    "tenant_id": tenant_id,
                    "environment": "mock",
                    "description": chaos["description"],
                    "payload": {"chaos_type": chaos["chaos_type"]},
                }, sb=sb)
                stats["chaos"] += 1
                stats["events"] += 1

            # workflow \uacb0\uacfc
            if flow_failed:
                emit_runtime_event(ctx, {
                    "event_type": "workflow.failed",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "WARNING",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
            else:
                emit_runtime_event(ctx, {
                    "event_type": "workflow.completed",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
            stats["events"] += 1
            stats["workflows"] += 1

    logger.info("[SYNTHETIC] tick: %s", stats)
    return stats
