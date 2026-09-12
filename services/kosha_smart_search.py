"""KOSHA Smart Search provider adapter — WAVE 2 public discovery.

Official source (data.go.kr OpenAPI, dataset 15123696, probed 2026-09-13):
  host path = apis.data.go.kr/B552468/srch + /smartSearch
  required query = serviceKey, pageNo, numOfRows, searchValue, category

This module is a discovery provider, not a Knowledge SoT.
No DB writes. No legal applicability scoring.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import xml.etree.ElementTree as ET
from typing import Any, Optional

from services.kr_public_api import kr_get

logger = logging.getLogger("kosha_smart_search")

DATASET_ID = "15123696"
DATASET_NAME = "한국산업안전보건공단_안전보건법령 스마트검색"
OFFICIAL_HOST_PATH = "apis.data.go.kr/B552468/srch"
SOURCE_HOST = "https://apis.data.go.kr/B552468"
SOURCE_PATH = "srch/smartSearch"
PROVIDER = "KOSHA"
MATCH_TYPE = "SOURCE_SEARCH"
DEFAULT_CATEGORY = "0"  # 전체
MAX_Q_LENGTH = 100
MIN_PAGE = 1
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 50
REQUEST_TIMEOUT_SECONDS = 15
SUCCESS_RESULT_CODES = frozenset({"00", "0", "000", "03"})
RATE_LIMIT_RESULT_CODES = frozenset({"22"})
TIMEOUT_RESULT_CODES = frozenset({"05"})
CONTEXT_PARAM_BLOCKLIST = frozenset({
    "company",
    "factory",
    "user_id",
    "diagnosis",
    "equipment",
    "process",
    "task",
    "keyword",
})

_ITEM_PASSTHROUGH = (
    ("doc_id", "external_id"),
    ("title", "title"),
    ("content", "summary"),
    ("category", "category"),
)


class SmartSearchQueryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class KoshaTransportError(Exception):
    def __init__(self, http_status: int, snippet: str):
        super().__init__(f"KOSHA HTTP {http_status}")
        self.http_status = http_status
        self.snippet = snippet


def get_service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or os.getenv("BUILDING_API_KEY", "")
    )


def normalize_query(q: Optional[str], page: int, page_size: int) -> tuple[str, int, int]:
    query = (q or "").strip()
    if not query:
        raise SmartSearchQueryError("QUERY_EMPTY", "q must be a non-empty string")
    if len(query) > MAX_Q_LENGTH:
        raise SmartSearchQueryError("QUERY_TOO_LONG", f"q must be <= {MAX_Q_LENGTH} characters")
    if not isinstance(page, int) or page < MIN_PAGE:
        raise SmartSearchQueryError("PAGE_INVALID", "page must be >= 1")
    if not isinstance(page_size, int) or page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE:
        raise SmartSearchQueryError(
            "PAGE_SIZE_INVALID",
            f"page_size must be {MIN_PAGE_SIZE}..{MAX_PAGE_SIZE}",
        )
    return query, page, page_size


def build_kosha_params(search_value: str, page: int, page_size: int, service_key: str) -> dict[str, str]:
    return {
        "serviceKey": service_key,
        "pageNo": str(page),
        "numOfRows": str(page_size),
        "searchValue": search_value,
        "category": DEFAULT_CATEGORY,
        "returnType": "json",
    }


def _redact(text: str, secret: str) -> str:
    if not text or not secret:
        return text
    return text.replace(secret, "[REDACTED]")


def _clean_text(value: Any, secret: str) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = _redact(value.strip(), secret)
    return text or None


def _parse_xml_response(text: str) -> dict[str, Any]:
    root = ET.fromstring(text)
    result_code = root.findtext(".//resultCode") or "00"
    result_msg = root.findtext(".//resultMsg") or ""
    total_count = root.findtext(".//totalCount")
    page_no = root.findtext(".//pageNo")
    num_of_rows = root.findtext(".//numOfRows")
    items = []
    for items_el in root.findall(".//items"):
        for item_el in items_el:
            item = {child.tag: child.text or "" for child in item_el}
            if item:
                items.append(item)
    return {
        "header": {"resultCode": result_code, "resultMsg": result_msg},
        "body": {
            "items": items,
            "totalCount": int(total_count) if total_count else 0,
            "pageNo": int(page_no) if page_no else 1,
            "numOfRows": int(num_of_rows) if num_of_rows else 10,
        },
    }


def parse_kosha_payload(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = _parse_xml_response(text)
        except Exception as exc:
            raise ValueError("schema_error") from exc
    if not isinstance(data, dict):
        raise ValueError("schema_error")
    if isinstance(data.get("response"), dict):
        data = data["response"]
    if not isinstance(data, dict):
        raise ValueError("schema_error")
    return data


def _unwrap_items(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        raise ValueError("schema_error")
    node = body.get("items")
    if node is None:
        return []
    if isinstance(node, list):
        raw_items = node
    elif isinstance(node, dict):
        inner = node.get("item", [])
        if inner is None or inner == "":
            raw_items = []
        elif isinstance(inner, list):
            raw_items = inner
        elif isinstance(inner, dict):
            raw_items = [inner]
        else:
            raise ValueError("schema_error")
    else:
        raise ValueError("schema_error")
    items = []
    for row in raw_items:
        if row is None:
            continue
        if not isinstance(row, dict):
            raise ValueError("schema_error")
        items.append(row)
    return items


def _parse_total(body: dict[str, Any]) -> Optional[int]:
    raw = body.get("totalCount")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def normalize_item(raw: dict[str, Any], secret: str) -> dict[str, Any]:
    item = {
        "external_id": None,
        "title": None,
        "summary": None,
        "source_name": PROVIDER,
        "source_url": None,
        "original_url": None,
        "published_at": None,
        "category": None,
        "source_type": None,
        "match_type": MATCH_TYPE,
    }
    for src_key, dest_key in _ITEM_PASSTHROUGH:
        item[dest_key] = _clean_text(raw.get(src_key), secret)
    return item


def _unavailable(
    *,
    query: str,
    page: int,
    page_size: int,
    provider_error: str,
    secret: str,
    http_status: Optional[int] = None,
    result_code: Optional[str] = None,
) -> dict[str, Any]:
    logger.warning(
        "kosha smart search unavailable provider_error=%s http=%s result_code=%s",
        provider_error,
        http_status,
        result_code,
    )
    return {
        "status": "unavailable",
        "provider": PROVIDER,
        "query": _redact(query, secret),
        "page": page,
        "page_size": page_size,
        "total": 0,
        "items": [],
        "provider_error": provider_error,
    }


def _ok(
    *,
    query: str,
    page: int,
    page_size: int,
    total: Optional[int],
    items: list[dict[str, Any]],
    secret: str,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": PROVIDER,
        "query": _redact(query, secret),
        "page": page,
        "page_size": page_size,
        "total": total if total is not None else 0,
        "items": items,
    }


def _is_timeout(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return "timeout" in name or "timeout" in msg or "timed out" in msg


async def fetch_smart_search_raw(
    search_value: str,
    page_no: int,
    num_of_rows: int,
) -> dict[str, Any]:
    """Return the parsed KOSHA payload. Transport failures raise KoshaTransportError.

    Used by legacy GET /kosha/law-search so the outer {status:success,data:...} shape stays.
    """
    secret = get_service_key()
    params = build_kosha_params(search_value, page_no, num_of_rows, secret)
    url = f"{SOURCE_HOST}/{SOURCE_PATH}"
    try:
        status, text = await asyncio.to_thread(
            kr_get, url, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except Exception as exc:
        if _is_timeout(exc):
            raise KoshaTransportError(504, "timeout") from exc
        raise KoshaTransportError(502, "network") from exc
    if status >= 400:
        snippet = _redact((text or "")[:200], secret)
        raise KoshaTransportError(status, snippet)
    try:
        return parse_kosha_payload(text or "")
    except ValueError:
        return {"parse_error": "schema_error"}


def _classify_result_code(result_code: str) -> str:
    code = (result_code or "").strip()
    if code in SUCCESS_RESULT_CODES:
        return "ok"
    if code in RATE_LIMIT_RESULT_CODES:
        return "rate_limited"
    if code in TIMEOUT_RESULT_CODES:
        return "timeout"
    return "upstream_error"


async def search_kosha_public(
    q: Optional[str],
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    query, page, page_size = normalize_query(q, page, page_size)
    secret = get_service_key()
    params = build_kosha_params(query, page, page_size, secret)
    for blocked in CONTEXT_PARAM_BLOCKLIST:
        params.pop(blocked, None)
    url = f"{SOURCE_HOST}/{SOURCE_PATH}"
    try:
        status, text = await asyncio.to_thread(
            kr_get, url, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except Exception as exc:
        code = "timeout" if _is_timeout(exc) else "network_error"
        return _unavailable(
            query=query,
            page=page,
            page_size=page_size,
            provider_error=code,
            secret=secret,
        )
    if status == 429:
        return _unavailable(
            query=query,
            page=page,
            page_size=page_size,
            provider_error="rate_limited",
            secret=secret,
            http_status=status,
        )
    if status >= 400:
        return _unavailable(
            query=query,
            page=page,
            page_size=page_size,
            provider_error="upstream_http",
            secret=secret,
            http_status=status,
        )
    try:
        payload = parse_kosha_payload(text or "")
        header = payload.get("header")
        body = payload.get("body")
        if not isinstance(header, dict) or not isinstance(body, dict):
            raise ValueError("schema_error")
        result_code = str(header.get("resultCode") or "")
        classified = _classify_result_code(result_code)
        if classified != "ok":
            return _unavailable(
                query=query,
                page=page,
                page_size=page_size,
                provider_error=classified,
                secret=secret,
                http_status=status,
                result_code=result_code,
            )
        raw_items = _unwrap_items(body)
        items = [normalize_item(row, secret) for row in raw_items]
        return _ok(
            query=query,
            page=page,
            page_size=page_size,
            total=_parse_total(body),
            items=items,
            secret=secret,
        )
    except ValueError:
        return _unavailable(
            query=query,
            page=page,
            page_size=page_size,
            provider_error="schema_error",
            secret=secret,
            http_status=status,
        )


def response_contains_secret(payload: Any, secret: str) -> bool:
    if not secret:
        return False
    return secret in json.dumps(payload, ensure_ascii=False)
