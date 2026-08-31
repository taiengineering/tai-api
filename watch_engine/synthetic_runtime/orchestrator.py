"""Orchestrator — Synthetic Tick 실행.

매 tick마다:
1. 20개 tenant 순회
2. Persona 기반 workflow 실행 여부 결정
3. Scenario 선택 + 실행
4. Chaos 주입
5. emit_runtime_event 경유 저장

중요: Workflow Runtime은 severity=INFO만 설정 가능.
WARNING/CRITICAL은 Control Bridge가 projection.
"""

import random
import logging
import uuid
from datetime import datetime, timezone
from services.time import now_kst

logger = logging.getLogger("watch_engine.synthetic_runtime.orchestrator")


def run_synthetic_tick(sb=None) -> dict:
    """1회 synthetic tick 실행."""
    from watch_engine.synthetic_runtime.personas import TENANT_PERSONAS, PERSONAS
    from watch_engine.synthetic_runtime.scenarios import SCENARIOS
    from watch_engine.synthetic_runtime.chaos_engine import inject_chaos
    from watch_engine.runtime_bus import emit_runtime_event, make_context

    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()

    now = now_kst()
    hour = now.hour
    stats = {"tenants": 0, "workflows": 0, "events": 0, "chaos": 0, "abandoned": 0, "failed": 0, "blocked": 0}

    scenario_keys = list(SCENARIOS.keys())

    for tenant_id, persona_key in TENANT_PERSONAS.items():
        persona = PERSONAS.get(persona_key)
        if not persona:
            continue

        stats["tenants"] += 1

        # 근무시간 체크
        wh = persona["working_hours"]
        if wh[0] < wh[1]:
            if not (wh[0] <= hour < wh[1]):
                continue
        else:  # 야간 (22~6)
            if not (hour >= wh[0] or hour < wh[1]):
                continue

        # workflow 빈도 기반 실행 여부
        freq = persona["workflow_freq"]
        if random.random() > freq * 0.3:
            continue

        # burst 체크
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

            # workflow.started (INFO — 사실 기록)
            r = emit_runtime_event(ctx, {
                "event_type": "workflow.started",
                "flow_key": scenario["flow_key"],
                "trace_id": trace_id,
                "severity": "INFO",
                "tenant_id": tenant_id,
                "environment": "mock",
            }, sb=sb)
            if r.accepted:
                stats["events"] += 1
            else:
                stats["blocked"] += 1

            # 중도 포기 체크
            if random.random() < persona["abandon_rate"]:
                r = emit_runtime_event(ctx, {
                    "event_type": "workflow.blocked",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                    "description": "[SYNTHETIC] user abandoned flow",
                }, sb=sb)
                stats["abandoned"] += 1
                stats["events"] += 1 if r.accepted else 0
                continue

            # Step 실행
            flow_failed = False
            for step in scenario["steps"]:
                step_fail = random.random() < (step["fail_rate"] + persona["retry_rate"])
                step_timeout = random.random() < persona["timeout_rate"]

                if step_timeout:
                    r = emit_runtime_event(ctx, {
                        "event_type": "workflow.timeout",
                        "flow_key": scenario["flow_key"],
                        "step_key": step["step_key"],
                        "step_order": step["order"],
                        "trace_id": trace_id,
                        "severity": "INFO",
                        "tenant_id": tenant_id,
                        "environment": "mock",
                    }, sb=sb)
                    stats["events"] += 1 if r.accepted else 0
                    flow_failed = True
                    break

                if step_fail:
                    r = emit_runtime_event(ctx, {
                        "event_type": "step.failed",
                        "flow_key": scenario["flow_key"],
                        "step_key": step["step_key"],
                        "step_order": step["order"],
                        "trace_id": trace_id,
                        "severity": "INFO",
                        "tenant_id": tenant_id,
                        "environment": "mock",
                    }, sb=sb)
                    stats["events"] += 1 if r.accepted else 0
                    stats["failed"] += 1
                    flow_failed = True
                    break

                # step 성공
                r = emit_runtime_event(ctx, {
                    "event_type": "step.completed",
                    "flow_key": scenario["flow_key"],
                    "step_key": step["step_key"],
                    "step_order": step["order"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
                stats["events"] += 1 if r.accepted else 0

            # Chaos injection (Control Runtime 컨텍스트 — WARNING/CRITICAL 가능)
            chaos = inject_chaos(tenant_id, scenario["flow_key"],
                                 chaos_probability=persona["degradation_sensitivity"])
            if chaos:
                ctrl_ctx = make_context("control", tenant_id=tenant_id, environment="mock")
                r = emit_runtime_event(ctrl_ctx, {
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
                stats["events"] += 1 if r.accepted else 0

            # workflow 결과 (INFO — Control Bridge가 severity projection)
            if flow_failed:
                r = emit_runtime_event(ctx, {
                    "event_type": "workflow.failed",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
            else:
                r = emit_runtime_event(ctx, {
                    "event_type": "workflow.completed",
                    "flow_key": scenario["flow_key"],
                    "trace_id": trace_id,
                    "severity": "INFO",
                    "tenant_id": tenant_id,
                    "environment": "mock",
                }, sb=sb)
            stats["events"] += 1 if r.accepted else 0
            stats["workflows"] += 1

    logger.info("[SYNTHETIC] tick: %s", stats)
    return stats
