"""Synthetic Runner — 업무 흐름 heartbeat.

실제 API를 호출하여 핵심 업무 흐름이 끝까지 성공하는지 확인.
사용자보다 먼저 이상을 발견하는 것이 목표.

Fail-safe: 절대 서비스 영향 없음.
"""

import logging
import os
import time
from datetime import datetime
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.synthetic.runner")


def _generate_run_id(prefix: str = "synthetic") -> str:
    """Generate scenario_run_id: synthetic_YYYYMMDD_HHMMSS"""
    ts = now_kst().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}"


def run_synthetic(
    scenarios: Optional[list[str]] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Run synthetic scenarios.

    Args:
        scenarios: List of scenario names to run. None = all.
        base_url: API base URL. Defaults to env INTERNAL_API_URL.

    Returns:
        {"scenario_run_id": str, "results": [...], "total": int,
         "passed": int, "failed": int, "errors": int}
    """
    run_id = _generate_run_id()
    url = base_url or os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")

    stats = {
        "scenario_run_id": run_id,
        "results": [],
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
    }

    # Available scenarios
    available = _get_available_scenarios()
    to_run = scenarios or list(available.keys())

    for name in to_run:
        scenario_fn = available.get(name)
        if not scenario_fn:
            logger.warning("Unknown scenario: %s", name)
            continue

        stats["total"] += 1
        t0 = time.time()

        try:
            result = scenario_fn(run_id=run_id, base_url=url)
            elapsed_ms = int((time.time() - t0) * 1000)

            result["duration_ms"] = elapsed_ms
            stats["results"].append(result)

            if result.get("status") == "passed":
                stats["passed"] += 1
            else:
                stats["failed"] += 1

        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            stats["errors"] += 1
            stats["results"].append({
                "scenario": name,
                "status": "error",
                "error": str(e),
                "duration_ms": elapsed_ms,
            })
            logger.error("Synthetic %s error: %s", name, e)

    logger.info(
        "Synthetic run %s: %d total, %d passed, %d failed, %d errors",
        run_id, stats["total"], stats["passed"],
        stats["failed"], stats["errors"],
    )
    return stats


def _get_available_scenarios() -> dict:
    """Load available scenarios (lazy import)."""
    scenarios = {}
    try:
        from watch_engine.synthetic.scenarios.login import run_login_scenario
        scenarios["login"] = run_login_scenario
    except ImportError as e:
        logger.error("Failed to load login scenario: %s", e)

    try:
        from watch_engine.synthetic.scenarios.process_registration import run_process_registration_scenario
        scenarios["process_registration"] = run_process_registration_scenario
    except ImportError as e:
        logger.error("Failed to load process_registration scenario: %s", e)

    return scenarios
