"""EXT-132 동기화 오케스트레이터 — 페이지네이션 + 체크포인트 + STAGING/COMPLETED 스냅샷 패턴.

GAP-B: start_page_no + on_page_complete 콜백으로 체크포인트 기반 Resume 지원.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from services.ext132_hazardous_material.contract import (
    MAX_PAGES_SAFETY_CAP,
    REQUEST_BUDGET_DEFAULT,
    REQUEST_BUDGET_ENV,
)
from services.ext132_hazardous_material.parse import Ext132Item, Ext132ParseError, parse_page
from services.public_data_sync.budget import RequestBudget, RequestBudgetExceeded
from services.public_data_sync.errors import PageFencedError, PageSaveError

logger = logging.getLogger(__name__)

# PATCH-C: EXT-132 정상 resultCode — "0"(JSON 실측) + "00"(XML 문서 기준)
_EXT132_OK_CODES: frozenset[str] = frozenset({"0", "00"})
# TRACK-A: API 속도제한 코드 — PARTIAL/RATE_LIMITED (STAGING 보존)
_EXT132_RATE_LIMIT_CODES: frozenset[str] = frozenset({"22", "23"})


class SyncStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"         # budget exhausted or safety cap hit
    FAILED = "FAILED"
    ABORTED_TOTAL_CHANGED = "ABORTED_TOTAL_CHANGED"  # GAP-B: totalCount changed during resume


@dataclass
class SyncResult:
    status: SyncStatus
    fetched: int
    items: list[Ext132Item] = field(default_factory=list)
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
    # GAP-B: resume/checkpoint parameters
    start_page_no: int = 1,
    on_page_complete: Callable[[int, list[Ext132Item], int, int | None], None] | None = None,
    expected_total_count: int | None = None,
    # PATCH-003-02: resume 시 DB에 이미 저장된 항목 수 (빈 페이지 조기 종료 검증용)
    initial_items_count: int = 0,
) -> SyncResult:
    """전체 EXT-132 데이터 수집.

    GAP-A: dry_run은 adapter에서 이미 차단됨. 이 함수에서 dry_run=True이면
           1페이지 수집 후 종료 (HTTP 제한만, DB 저장은 adapter 책임).
    GAP-B: start_page_no > 1이면 해당 페이지부터 시작 (Resume).
           on_page_complete(page_no, page_items, total_collected, total_count_from_api):
             R3-02: page_items는 이 페이지 항목만. 콜백이 DB 저장 후 체크포인트를 갱신해야 한다.
           expected_total_count: Resume 시 API totalCount 변경 감지용.
    initial_items_count: Resume 시 기존 DB 항목 수. 빈 페이지 조기 종료 감지에 사용.
    Returns SyncResult — 예외를 raise하지 않는다.
    페이지 크기(num_of_rows) 최대값 UNVERIFIED: 보수적 기본값 사용.
    """
    if dry_run:
        request_budget = 10
    budget = _make_budget(request_budget)

    from services.ext132_hazardous_material.client import fetch_page, RateLimitError
    items: list[Ext132Item] = []
    pages_fetched = 0

    page_no = max(1, start_page_no)
    first_page = True
    seen_api_total: int | None = None  # REPAIR-B: mid-collection totalCount consistency guard

    while page_no <= MAX_PAGES_SAFETY_CAP:
        try:
            budget.consume_or_raise()
        except RequestBudgetExceeded:
            logger.warning("ext132 budget exhausted page_no=%d used=%d", page_no, budget.used)
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
        except RateLimitError:
            logger.warning("ext132 rate limit page_no=%d — PARTIAL/RATE_LIMITED", page_no)
            return SyncResult(
                status=SyncStatus.PARTIAL,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="RATE_LIMITED",
            )
        except Exception as exc:
            logger.error("ext132 fetch_page failed page_no=%d %s", page_no, type(exc).__name__)
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
        except Ext132ParseError as exc:
            logger.error("ext132 parse_page failed page_no=%d %s", page_no, exc)
            return SyncResult(
                status=SyncStatus.FAILED,
                fetched=len(items),
                items=items,
                pages_fetched=pages_fetched,
                budget_used=budget.used,
                error_code="PARSE_ERROR",
                error_message=str(exc)[:200],
            )

        # PATCH-002-05 / PATCH-C: EXT-132 정상 코드 = "0" 또는 "00"
        if page.result_code is not None and page.result_code not in _EXT132_OK_CODES:
            if page.result_code in _EXT132_RATE_LIMIT_CODES:
                logger.warning(
                    "ext132 API rate limit code page_no=%d result_code=%s — PARTIAL/RATE_LIMITED",
                    page_no, page.result_code,
                )
                return SyncResult(
                    status=SyncStatus.PARTIAL,
                    fetched=len(items),
                    items=items,
                    pages_fetched=pages_fetched,
                    budget_used=budget.used,
                    error_code="RATE_LIMITED",
                    error_message=f"resultCode={page.result_code}",
                )
            logger.error(
                "ext132 API error response page_no=%d result_code=%s result_msg=%s",
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

        # GAP-B: totalCount change detection during resume
        if first_page and expected_total_count is not None and page.total_count is not None:
            if page.total_count != expected_total_count:
                logger.warning(
                    "ext132 totalCount changed during resume: expected=%d current=%d — aborting",
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

        # REPAIR-B: mid-collection totalCount consistency — detect changes after page 1
        if page.total_count is not None:
            if seen_api_total is None:
                seen_api_total = page.total_count
            elif page.total_count != seen_api_total:
                logger.warning(
                    "ext132 totalCount changed mid-collection page_no=%d first=%d current=%d — aborting",
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
            "ext132 page=%d items_this_page=%d total_so_far=%d total_count=%s",
            page_no, len(page.items), len(items), page.total_count,
        )

        # GAP-B/R3-02: callback receives page items so adapter can save BEFORE checkpoint
        if on_page_complete is not None:
            try:
                on_page_complete(page_no, page.items, len(items), page.total_count)
            except PageFencedError as exc:
                # PATCH-03: fencing must stop collection immediately
                logger.warning("ext132 fencing detected page_no=%d: %s", page_no, exc)
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
                # PATCH-002-03: page save failure stops collection
                logger.warning("ext132 page save error page_no=%d: %s", page_no, exc)
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
                # REPAIR-B: unknown callback errors are fatal — silent pass was swallowing data loss
                logger.error("ext132 callback error page_no=%d: %s", page_no, type(exc).__name__)
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
            # PATCH-003-02: 조기 빈 페이지 감지 — totalCount 미달 시 PARTIAL 반환 (수집 불완전)
            if page.total_count is not None and (initial_items_count + len(items)) < page.total_count:
                logger.warning(
                    "ext132 premature empty page page_no=%d in_session=%d total_db=%d api_total=%d",
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
        logger.warning("ext132 safety cap reached page_no=%d", page_no)
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
