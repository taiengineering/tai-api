"""KECO Live probe 유틸리티. max_calls=3 하드 상한 (bulk collection 금지)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from services.keco_chemical.contract import (
    PROBE_MAX_CALLS,
    SEARCH_CAS,
    SEARCH_ENGLISH_NAME,
    SERVICE_KEY_ENV,
)

logger = logging.getLogger(__name__)

PROBE_OK = "OK"
PROBE_BLOCKED_NO_KEY = "BLOCKED_NO_KEY"
PROBE_FAILED = "FAILED"

PROBE_NORESULT_SENTINEL = "TAI-PROBE-NORESULT-001"


@dataclass
class ProbeCall:
    search_gubun: str
    search_nm: str
    status_code: Optional[int]
    total_count: Optional[str]
    item_count: int
    error: Optional[str]


@dataclass
class ProbeResult:
    status: str
    calls: list[ProbeCall] = field(default_factory=list)
    error: Optional[str] = None


def _has_service_key() -> bool:
    for name in SERVICE_KEY_ENV:
        if (os.getenv(name) or "").strip():
            return True
    return False


def run_probe(
    client,
    store=None,
    max_calls: int = PROBE_MAX_CALLS,
    budget=None,
) -> ProbeResult:
    """Controlled probe — CAS 검색 → 영문명 검색 → 0건 sentinel.

    budget: RequestBudget 전달 시 attempt_hook으로 physical 시도 차감.
            전달 안 하면 hook 없이 실행 (기존 동작).
    max_calls는 하드코딩 PROBE_MAX_CALLS(3)이 상한.
    """
    if not _has_service_key():
        logger.info("KECO probe: BLOCKED_NO_KEY — KECO_API_SERVICE_KEY not set")
        return ProbeResult(status=PROBE_BLOCKED_NO_KEY)

    effective_max = min(max_calls, PROBE_MAX_CALLS)
    probe_targets = [
        (SEARCH_CAS, "7664-41-7"),
        (SEARCH_ENGLISH_NAME, "Ammonia"),
        (SEARCH_ENGLISH_NAME, PROBE_NORESULT_SENTINEL),
    ][:effective_max]

    calls: list[ProbeCall] = []
    for search_gubun, search_nm in probe_targets:
        attempt_hook = budget.consume_or_raise if budget is not None else None
        try:
            from services.keco_chemical.client import KecoNoServiceKeyError
            response = client.search(
                search_gubun=search_gubun,
                search_nm=search_nm,
                page_no=1,
                num_of_rows=3,
                attempt_hook=attempt_hook,
            )
            call = ProbeCall(
                search_gubun=search_gubun,
                search_nm=search_nm,
                status_code=200,
                total_count=response.total_count,
                item_count=len(response.items),
                error=None,
            )
        except KecoNoServiceKeyError:
            return ProbeResult(status=PROBE_BLOCKED_NO_KEY)
        except Exception as exc:
            call = ProbeCall(
                search_gubun=search_gubun,
                search_nm=search_nm,
                status_code=None,
                total_count=None,
                item_count=0,
                error=str(exc),
            )
        calls.append(call)

    errors = [c for c in calls if c.error is not None]
    status = PROBE_FAILED if errors else PROBE_OK
    return ProbeResult(status=status, calls=calls)


def run_preflight_probe() -> None:
    """collect.py --mode preflight 진입점.

    physical HTTP attempts <= PROBE_MAX_CALLS (3) hard cap.
    RequestBudget(limit=3)을 budget hook으로 주입 — timeout retry 포함.
    """
    from services.keco_chemical.client import KecoChemicalClient
    from services.keco_chemical.budget import RequestBudget

    client = KecoChemicalClient()
    budget = RequestBudget(limit=PROBE_MAX_CALLS)

    result = run_probe(client, budget=budget)

    if result.status == PROBE_BLOCKED_NO_KEY:
        logger.warning("[PREFLIGHT] BLOCKED_NO_KEY — KECO_API_SERVICE_KEY not set")
        raise RuntimeError("KECO_API_SERVICE_KEY not set — cannot run preflight")

    for c in result.calls:
        if c.error:
            logger.error("[PREFLIGHT] FAIL: %s %s → %s", c.search_gubun, c.search_nm, c.error)
        else:
            logger.info(
                "[PREFLIGHT] OK: %s %s → totalCount=%s items=%d",
                c.search_gubun, c.search_nm, c.total_count, c.item_count,
            )

    if result.status == PROBE_FAILED:
        errors = [c.error for c in result.calls if c.error]
        raise RuntimeError(f"Preflight probe FAILED: {errors}")

    logger.info("[PREFLIGHT] PASS — %d calls OK, budget_used=%d/%d", len(result.calls), budget.used, budget.limit)
