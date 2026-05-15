"""Browser Synthetic Runner — Playwright 시나리오 실행기.

Fail-safe: Playwright 미설치 시 skip, 예외 시 서비스 영향 없음.
"""

import asyncio
import logging
import time
from datetime import datetime

logger = logging.getLogger("watch_engine.browser_synthetic.runner")


def _generate_run_id() -> str:
    return f"browser_synth_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def run_browser_synthetic(scenarios: list[str] = None) -> dict:
    """Sync wrapper for async browser synthetic execution."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run_async(scenarios))
        loop.close()
        return result
    except Exception as e:
        logger.error("Browser synthetic runner failed: %s", e)
        return {"scenario_run_id": None, "total": 0, "passed": 0, "failed": 0, "errors": 1, "results": [{"error": str(e)[:200]}]}


async def _run_async(scenarios: list[str] = None) -> dict:
    run_id = _generate_run_id()
    stats = {"scenario_run_id": run_id, "results": [], "total": 0, "passed": 0, "failed": 0, "errors": 0}

    available = _get_scenarios()
    to_run = scenarios or list(available.keys())

    for name in to_run:
        fn = available.get(name)
        if not fn:
            logger.warning("Unknown browser scenario: %s", name)
            continue

        stats["total"] += 1
        t0 = time.time()
        try:
            result = await fn(run_id=run_id)
            result["duration_ms"] = int((time.time() - t0) * 1000)
            stats["results"].append(result)
            if result.get("status") == "passed":
                stats["passed"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["errors"] += 1
            stats["results"].append({"scenario": name, "status": "error", "error": str(e)[:200], "duration_ms": int((time.time() - t0) * 1000)})
            logger.error("Browser scenario %s error: %s", name, e)

    return stats


def _get_scenarios() -> dict:
    scenarios = {}
    try:
        from watch_engine.browser_synthetic.scenarios.login_browser import run_login_browser
        scenarios["login_browser"] = run_login_browser
    except ImportError as e:
        logger.error("Failed to load login_browser: %s", e)
    try:
        from watch_engine.browser_synthetic.scenarios.process_registration_browser import run_process_registration_browser
        scenarios["process_registration_browser"] = run_process_registration_browser
    except ImportError as e:
        logger.error("Failed to load process_registration_browser: %s", e)
    return scenarios
