"""EXT-037 동기화 오케스트레이터 — 페이지네이션 + 체크포인트 + STAGING/COMPLETED 스냅샷 패턴.

GAP-B: start_page_no + on_page_complete 콜백으로 체크포인트 기반 Resume 지원.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from services.ext037_chemical_safety.contract import (
    MAX_PAGES_SAFETY_CAP,
    REQUEST_BUDGET_DEFAULT,
    REQUEST_BUDGET_ENV,
)
from services.ext037_chemical_safety.parse import Ext037Item, Ext037ParseError, parse_page
from services.public_data_sync.budget import RequestBudget, RequestBudgetExceeded
from services.public_data_sync.errors import PageFencedError, PageSaveError

logger = logging.getLogger(__name__)


class SyncStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    ABORTED_TOTAL_CHANGED = "ABORTED_TOTAL_CHANGED"


@dataclass
class SyncResult:
    status: SyncStatus
    fetched: int
    items: list[Ext037Item] = field(default_factory=list)
    pages_fetched: int = 0
    budget_used: int = 0
    error_code: str | None = None
    error_message: str | None = None


def _make_budget(override: int | None = None) -> RequestBudget:
    import os
    if override is not None:
        return RequestBudget(limit=override)
    raw = (os.getenv(REQUEST_BUDGET_ENV) or "").strip()
    try:
        limit = int(raw) if raw else REQUEST_BUDGET_DEFAULT
    except ValueError:
        limit = REQUEST_BUDGET_DEFAULT
    return RequestBudget(limit=limit)


def collect_all(
    *,
    num_of_rows: int | None = None,
    request_budget: int | None = None,
    dry_run: bool = False,
    page_delay_seconds: float = 0.5,
    timeout_seconds: int = 60,
    start_page_no: int = 1,
    on_page_complete: Callable[[int, list[Ext037Item], int, int | None], None] | None = None,
    expected_total_count: int | None = None,
    initial_items_count: int = 0,
) -> SyncResult:
    """전체 EXT-037 데이터 수집.

    start_page_no > 1이면 해당 페이지부터 시작 (Resume).
    on_page_complete(page_no, page_items, total_collected, total_count_from_api):
      page_items는 이 페이지 항목만. 콜백이 DB 저장 후 체크포인트를 갱신해야 한다.
    expected_total_count: Resume 시 API totalCount 변경 감지용.
    initial_items_count: Resume 시 기존 DB 항목 수.
    """
    if dry_run:
        request_budget = 10
    budget = _make_budget(request_budget)

    from services.ext037_chemical_safety.client import fetch_page, RateLimitError as _RateLimitError
    items: list[Ext037Item] = []
    pages_fetched = 0

    page_no = max(1, start_page_no)
    first_page = True
    seen_api_total: int | None = None

    while page_no <= MAX_PAGES_SAFETY_CAP:
        try:
            budget.consume_or_raise()
        except RequestBudgetExceeded:
            logger.warning("ext037 budget exhausted page_no=%d used=%d", page_no, budget.used)
            return SyncResult(
                status=SyncStatus.PARTIAL,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="BUDGET_EXHAUSTED",
            )

        try:
            raw = fetch_page(page_no, num_of_rows=num_of_rows, timeout=timeout_seconds)
        except _RateLimitError:
            # REPAIR-B: HTTP 429 → PARTIAL/RATE_LIMITED — preserve STAGING for resume
            logger.warning("ext037 rate limited page_no=%d", page_no)
            return SyncResult(
                status=SyncStatus.PARTIAL,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="RATE_LIMITED",
                error_message="HTTP 429 rate limit",
            )
        except Exception as exc:
            logger.error("ext037 fetch_page failed page_no=%d %s", page_no, type(exc).__name__)
            return SyncResult(
                status=SyncStatus.FAILED,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="HTTP_ERROR",
                error_message=type(exc).__name__,
            )

        try:
            page = parse_page(raw)
        except Ext037ParseError as exc:
            logger.error("ext037 parse_page failed page_no=%d %s", page_no, exc)
            return SyncResult(
                status=SyncStatus.FAILED,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="PARSE_ERROR",
                error_message=str(exc)[:200],
            )

        # REPAIR-B: API codes 22 (per-second limit) / 23 (daily limit) → PARTIAL/RATE_LIMITED
        if page.result_code in ("22", "23"):
            logger.warning(
                "ext037 API rate limit code page_no=%d result_code=%s",
                page_no, page.result_code,
            )
            return SyncResult(
                status=SyncStatus.PARTIAL,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="RATE_LIMITED",
                error_message=f"API rate limit: resultCode={page.result_code}",
            )

        if page.result_code is not None and page.result_code != "00":
            logger.error(
                "ext037 API error response page_no=%d result_code=%s result_msg=%s",
                page_no, page.result_code, page.result_msg,
            )
            return SyncResult(
                status=SyncStatus.FAILED,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="API_ERROR_CODE",
                error_message=f"resultCode={page.result_code}",
            )

        if first_page and expected_total_count is not None and page.total_count is not None:
            if page.total_count != expected_total_count:
                logger.warning(
                    "ext037 totalCount changed during resume: expected=%d current=%d — aborting",
                    expected_total_count, page.total_count,
                )
                return SyncResult(
                    status=SyncStatus.ABORTED_TOTAL_CHANGED,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="TOTAL_COUNT_CHANGED",
                    error_message=f"expected={expected_total_count} current={page.total_count}",
                )
        first_page = False

        if page.total_count is not None:
            if seen_api_total is None:
                seen_api_total = page.total_count
            elif page.total_count != seen_api_total:
                logger.warning(
                    "ext037 totalCount changed mid-collection page_no=%d first=%d current=%d — aborting",
                    page_no, seen_api_total, page.total_count,
                )
                return SyncResult(
                    status=SyncStatus.ABORTED_TOTAL_CHANGED,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="TOTAL_COUNT_CHANGED",
                    error_message=f"first={seen_api_total} current={page.total_count}",
                )

        pages_fetched += 1
        items.extend(page.items)

        logger.info(
            "ext037 page=%d items_this_page=%d total_so_far=%d total_count=%s",
            page_no, len(page.items), len(items), page.total_count,
        )

        if on_page_complete is not None:
            try:
                on_page_complete(page_no, page.items, len(items), page.total_count)
            except PageFencedError as exc:
                logger.warning("ext037 fencing detected page_no=%d: %s", page_no, exc)
                return SyncResult(
                    status=SyncStatus.FAILED,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="FENCED",
                    error_message=str(exc)[:200],
                )
            except PageSaveError as exc:
                logger.warning("ext037 page save error page_no=%d: %s", page_no, exc)
                return SyncResult(
                    status=SyncStatus.FAILED,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="SAVE_ERROR",
                    error_message=str(exc)[:200],
                )
            except Exception as exc:
                logger.error("ext037 callback error page_no=%d: %s", page_no, type(exc).__name__)
                return SyncResult(
                    status=SyncStatus.FAILED,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="CALLBACK_ERROR",
                    error_message=type(exc).__name__,
                )

        if not page.items:
            if page.total_count is not None and (initial_items_count + len(items)) < page.total_count:
                logger.warning(
                    "ext037 premature empty page page_no=%d in_session=%d total_db=%d api_total=%d",
                    page_no, len(items), initial_items_count + len(items), page.total_count,
                )
                return SyncResult(
                    status=SyncStatus.PARTIAL,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="PREMATURE_EMPTY_PAGE",
                )
            break

        if page.total_count is not None and (initial_items_count + len(items)) >= page.total_count:
            break

        if dry_run:
            break

        page_no += 1
        if page_delay_seconds > 0 and page_no <= MAX_PAGES_SAFETY_CAP:
            time.sleep(page_delay_seconds)

    if page_no > MAX_PAGES_SAFETY_CAP:
        logger.warning("ext037 safety cap reached page_no=%d", page_no)
        return SyncResult(
            status=SyncStatus.PARTIAL,
            fetched=len(items),
            items=items,
            pages_fetched=pages_fetched,
            budget_used=budget.used,
            error_code="SAFETY_CAP",
        )

    return SyncResult(
        status=SyncStatus.COMPLETED,
        fetched=len(items),
        items=items,
        pages_fetched=pages_fetched,
        budget_used=budget.used,
    )
