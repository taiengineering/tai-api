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
) -> ProbeResult:
    """Controlled probe — CAS search → name search → no-result.

    환경에 KECO_API_SERVICE_KEY 없으면 BLOCKED_NO_KEY 반환.
    max_calls는 하드코딩 PROBE_MAX_CALLS(3)이 상한.
    """
    if not _has_service_key():
        logger.info("KECO probe: BLOCKED_NO_KEY — KECO_API_SERVICE_KEY not set")
        return ProbeResult(status=PROBE_BLOCKED_NO_KEY)

    effective_max = min(max_calls, PROBE_MAX_CALLS)
    probe_targets = [
        (SEARCH_CAS, "7664-41-7"),          # 암모니아 CAS
        (SEARCH_ENGLISH_NAME, "Ammonia"),   # 영문명
        (SEARCH_CAS, "NORESULT-00000000"),  # 결과 없음 케이스
    ][:effective_max]

    calls: list[ProbeCall] = []
    for search_gubun, search_nm in probe_targets:
        try:
            from services.keco_chemical.client import KecoNoServiceKeyError
            response = client.search(
                search_gubun=search_gubun,
                search_nm=search_nm,
                page_no=1,
                num_of_rows=3,
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
