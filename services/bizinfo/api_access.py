"""OBJ-BZI-001 — Bizinfo API Access.

WO-TAI-BIZINFO-OBJ-001-API-ACCESS-001.
No DB, no storage, no routing. Pure read operation.

Fetches one page of raw items from 기업마당 (bizinfo.go.kr) and returns
them in a SourceBatch without modification.  API keys are never written
to returned data, error messages, or logs.

get_fn is injected for testability.  Production default is kr_get from
services.kr_public_api (curl_cffi + proxy for Korean public APIs).
Tests must always inject a mock — do NOT call real API in tests.

Error codes (SourceBatch.error_code):
  None             — success
  KEY_MISSING      — BIZINFO_API_KEY / BIZINFO_EVENT_API_KEY env var absent
  SIZE_LIMIT       — size < 1 or size > MAX_PAGE_SIZE
  TIMEOUT          — network timeout
  HTTP_ERROR       — non-200 HTTP status (not auth-related)
  INVALID_RESPONSE — non-JSON or unexpected top-level type
  AUTH_FAIL        — HTTP 401 or auth error marker in response body
  EMPTY            — API returned no items for the requested page
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROGRAM_API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
_EVENT_API_URL   = "https://www.bizinfo.go.kr/uss/rss/bizinfoEventApi.do"

_ENV_KEY_PROGRAM = "BIZINFO_API_KEY"
_ENV_KEY_EVENT   = "BIZINFO_EVENT_API_KEY"

_MAX_PAGE_SIZE    = 100
_TIMEOUT_SECONDS  = 25
# Post-download guard only — kr_get (curl_cffi) cannot cap download size
# pre-receipt.  5 MB is generous for a single paginated page.
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# Auth error key name that 기업마당 API uses when the service key is invalid.
# Presence of this key in the response body signals AUTH_FAIL regardless of
# HTTP status code.
_AUTH_ERROR_KEY = "returnAuthMsg"

# ---------------------------------------------------------------------------
# Public error codes
# ---------------------------------------------------------------------------

ERR_KEY_MISSING      = "KEY_MISSING"
ERR_SIZE_LIMIT       = "SIZE_LIMIT"
ERR_TIMEOUT          = "TIMEOUT"
ERR_HTTP_ERROR       = "HTTP_ERROR"
ERR_INVALID_RESPONSE = "INVALID_RESPONSE"
ERR_AUTH_FAIL        = "AUTH_FAIL"
ERR_EMPTY            = "EMPTY"

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceBatch:
    """Result of fetch_source_batch().

    error_code is None on success.  items is an empty tuple on any error
    or when the API returns no results for the requested page.
    total_count is 0 on error; on EMPTY it reflects the API total if
    the response provided one.
    """
    source_kind:  Literal["PROGRAM", "EVENT"]
    provider:     Literal["BIZINFO_PROGRAM", "BIZINFO_EVENT"]
    items:        tuple[dict, ...]
    retrieved_at: datetime
    page:         int
    size:         int
    total_count:  int
    error_code:   Optional[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _provider(source_kind: str) -> Literal["BIZINFO_PROGRAM", "BIZINFO_EVENT"]:
    return "BIZINFO_PROGRAM" if source_kind == "PROGRAM" else "BIZINFO_EVENT"


def _api_url(source_kind: str) -> str:
    return _PROGRAM_API_URL if source_kind == "PROGRAM" else _EVENT_API_URL


def _env_key_name(source_kind: str) -> str:
    return _ENV_KEY_PROGRAM if source_kind == "PROGRAM" else _ENV_KEY_EVENT


def _error_batch(
    source_kind: Literal["PROGRAM", "EVENT"],
    retrieved_at: datetime,
    page: int,
    size: int,
    error_code: str,
) -> SourceBatch:
    return SourceBatch(
        source_kind=source_kind,
        provider=_provider(source_kind),
        items=(),
        retrieved_at=retrieved_at,
        page=page,
        size=size,
        total_count=0,
        error_code=error_code,
    )


def _has_auth_error(data: dict) -> bool:
    """Return True if the parsed response body indicates an auth failure.

    기업마당 API returns HTTP 200 with a JSON body containing
    'returnAuthMsg' when the service key is invalid.
    """
    if _AUTH_ERROR_KEY in data:
        return True
    for v in data.values():
        if isinstance(v, str) and "SERVICE_KEY_IS_NOT_REGISTERED" in v:
            return True
    return False


def _extract_items(data: dict) -> tuple[tuple[dict, ...], int]:
    """Extract items tuple and total_count from a parsed API response dict.

    기업마당 wraps results in {"jsonArray": {"item": [...], "totCnt": "N"}}.
    When only one item exists the API may return item as a dict rather than
    a one-element list — both forms are normalised to a tuple of dicts.
    Falls back to "totalCount" key when "totCnt" is absent.
    """
    array_candidate = data.get("jsonArray")
    if isinstance(array_candidate, dict):
        array = array_candidate
    elif array_candidate is None:
        array = data
    else:
        return (), 0

    raw_items = array.get("item")

    if raw_items is None:
        return (), 0

    if isinstance(raw_items, dict):
        items: tuple[dict, ...] = (raw_items,)
    elif isinstance(raw_items, list):
        items = tuple(i for i in raw_items if isinstance(i, dict))
    else:
        items = ()

    total_key = "totCnt" if "totCnt" in array else "totalCount"
    try:
        total = int(array.get(total_key, 0))
    except (ValueError, TypeError):
        total = len(items)

    return items, total


def _is_timeout_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg  = str(exc).lower()
    return "timeout" in name or "timed out" in msg


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def fetch_source_batch(
    source_kind: Literal["PROGRAM", "EVENT"],
    page: int = 1,
    size: int = 10,
    *,
    get_fn: Optional[Callable] = None,
) -> SourceBatch:
    """Fetch one page of raw items from 기업마당 API.

    source_kind:  "PROGRAM" (지원사업) or "EVENT" (행사).
    page:         1-based page number.
    size:         Items per page.  Must be between 1 and MAX_PAGE_SIZE (100).
    get_fn:       callable(url, *, params, timeout) → (status:int, text:str).
                  Defaults to kr_get.  Always inject a mock in tests — never
                  call real API endpoints in test/CI environments.

    API keys are read from environment variables only and are never included
    in returned SourceBatch fields or error messages.

    The original record is never modified.
    """
    retrieved_at = datetime.now(tz=timezone.utc)

    if size < 1 or size > _MAX_PAGE_SIZE:
        return _error_batch(source_kind, retrieved_at, page, size, ERR_SIZE_LIMIT)

    env_key_name = _env_key_name(source_kind)
    api_key = os.environ.get(env_key_name, "").strip()
    if not api_key:
        return _error_batch(source_kind, retrieved_at, page, size, ERR_KEY_MISSING)

    if get_fn is None:
        from services.kr_public_api import kr_get
        get_fn = kr_get

    url = _api_url(source_kind)
    params = {
        "crtfcKey":  api_key,
        "dataType":  "json",
        "pageIndex": str(page),
        "pageUnit":  str(size),
    }

    try:
        status_code, text = get_fn(url, params=params, timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        code = ERR_TIMEOUT if _is_timeout_error(exc) else ERR_HTTP_ERROR
        return _error_batch(source_kind, retrieved_at, page, size, code)

    if len(text.encode("utf-8", errors="replace")) > _MAX_RESPONSE_BYTES:
        return _error_batch(source_kind, retrieved_at, page, size, ERR_INVALID_RESPONSE)

    if status_code == 401:
        return _error_batch(source_kind, retrieved_at, page, size, ERR_AUTH_FAIL)
    if status_code != 200:
        return _error_batch(source_kind, retrieved_at, page, size, ERR_HTTP_ERROR)

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _error_batch(source_kind, retrieved_at, page, size, ERR_INVALID_RESPONSE)

    if not isinstance(data, dict):
        return _error_batch(source_kind, retrieved_at, page, size, ERR_INVALID_RESPONSE)

    if _has_auth_error(data):
        return _error_batch(source_kind, retrieved_at, page, size, ERR_AUTH_FAIL)

    items, total_count = _extract_items(data)

    if not items:
        return SourceBatch(
            source_kind=source_kind,
            provider=_provider(source_kind),
            items=(),
            retrieved_at=retrieved_at,
            page=page,
            size=size,
            total_count=total_count,
            error_code=ERR_EMPTY,
        )

    return SourceBatch(
        source_kind=source_kind,
        provider=_provider(source_kind),
        items=items[:size],
        retrieved_at=retrieved_at,
        page=page,
        size=size,
        total_count=total_count,
        error_code=None,
    )
