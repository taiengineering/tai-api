"""Official KOSHA MSDS OpenAPI client. Search is candidate-only."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlencode

from services.kr_public_api import kr_get
from services.kosha_msds.contract import (
    ALLOWED_SEARCH_CND,
    ALLOWED_SECTIONS,
    BASE_URL,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_NUM_OF_ROWS,
    DEFAULT_TIMEOUT_SECONDS,
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    DETAIL_OPERATION_PREFIX,
    LIST_OPERATION,
    MAX_NUM_OF_ROWS,
    RATE_LIMIT_DAILY_CODES,
    RATE_LIMIT_SECOND_CODES,
    SECTION_MAX,
    SECTION_MIN,
    SERVICE_KEY_ENV,
    SUCCESS_RESULT_CODES,
)
from services.kosha_msds.identity import ListCandidate, candidate_from_list_item, normalize_chem_id
from services.kosha_msds.parse import (
    KoshaMsdsParseError,
    KoshaMsdsResultError,
    MsdsListResponse,
    MsdsSectionResponse,
    parse_list_xml,
    parse_section_xml,
)

GetFn = Callable[..., tuple[int, str]]


class KoshaMsdsClientError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class KoshaMsdsTransportError(KoshaMsdsClientError):
    def __init__(self, http_status: int, snippet: str):
        super().__init__("TRANSPORT", f"HTTP {http_status}")
        self.http_status = http_status
        self.snippet = snippet


def redact_secret(text: str, secret: str) -> str:
    if not text:
        return text
    out = text
    if secret:
        out = out.replace(secret, "[REDACTED]")
    return re.sub(r"serviceKey=[^&\s\"']+", "serviceKey=[REDACTED]", out)


def get_service_key() -> str:
    for name in SERVICE_KEY_ENV:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def section_no(value: int | str) -> int:
    if isinstance(value, str):
        raw = value.strip()
        if not raw.isdigit():
            raise KoshaMsdsClientError("SECTION_INVALID", f"section not allowed: {value}")
        value = int(raw)
    if value not in ALLOWED_SECTIONS:
        raise KoshaMsdsClientError(
            "SECTION_INVALID",
            f"section must be {SECTION_MIN}..{SECTION_MAX}",
        )
    return value


def section_token(value: int | str) -> str:
    return f"{section_no(value):02d}"


@dataclass(frozen=True)
class SearchResult:
    total_count: int
    page_no: int
    num_of_rows: int
    result_code: str
    result_msg: str
    candidates: list[ListCandidate]


@dataclass(frozen=True)
class SectionFetch:
    section_no: int
    result_code: str
    result_msg: str
    items: list[dict[str, Optional[str]]]
    status: str


@dataclass(frozen=True)
class FullDetail:
    chem_id: str
    sections: dict[str, SectionFetch]
    detail_status: str
    failed_sections: tuple[int, ...] = ()


@dataclass
class KoshaMsdsClient:
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    get_fn: GetFn = kr_get
    service_key: Optional[str] = None

    def _key(self) -> str:
        key = (self.service_key if self.service_key is not None else get_service_key()).strip()
        if not key:
            raise KoshaMsdsClientError("SERVICE_KEY_MISSING", "KOSHA MSDS serviceKey is not configured")
        return key

    def _get(self, operation: str, params: dict[str, str]) -> tuple[int, str, str]:
        key = self._key()
        query = dict(params)
        query["serviceKey"] = key
        url = f"{BASE_URL}/{operation}"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                status, text = self.get_fn(url, params=query, timeout=self.timeout_seconds)
            except Exception as exc:  # transport/timeout
                last_exc = exc
                if attempt >= self.max_attempts:
                    raise KoshaMsdsTransportError(0, redact_secret(str(exc), key)) from exc
                continue
            snippet = redact_secret((text or "")[:240], key)
            if status >= 500 and attempt < self.max_attempts:
                last_exc = KoshaMsdsTransportError(status, snippet)
                continue
            if status != 200:
                raise KoshaMsdsTransportError(status, snippet)
            return status, text, key
        raise last_exc or KoshaMsdsTransportError(0, "exhausted retries")

    def search(
        self,
        *,
        search_cnd: int,
        search_wrd: str,
        page_no: int = 1,
        num_of_rows: int = DEFAULT_NUM_OF_ROWS,
    ) -> SearchResult:
        if search_cnd not in ALLOWED_SEARCH_CND:
            raise KoshaMsdsClientError("SEARCH_CND_INVALID", "searchCnd must be 0..4")
        if page_no < 1:
            raise KoshaMsdsClientError("PAGE_INVALID", "pageNo must be >= 1")
        if num_of_rows < 1 or num_of_rows > MAX_NUM_OF_ROWS:
            raise KoshaMsdsClientError(
                "ROWS_INVALID",
                f"numOfRows must be 1..{MAX_NUM_OF_ROWS}",
            )
        _, text, key = self._get(
            LIST_OPERATION,
            {
                "searchCnd": str(search_cnd),
                "searchWrd": search_wrd,
                "pageNo": str(page_no),
                "numOfRows": str(num_of_rows),
            },
        )
        try:
            parsed = parse_list_xml(text, require_success=True)
        except KoshaMsdsResultError as exc:
            if exc.result_code in RATE_LIMIT_DAILY_CODES | RATE_LIMIT_SECOND_CODES:
                raise KoshaMsdsClientError("RATE_LIMIT", redact_secret(exc.result_msg, key)) from exc
            raise KoshaMsdsClientError("RESULT_CODE", redact_secret(exc.result_msg, key)) from exc
        candidates = [candidate_from_list_item(item) for item in parsed.items]
        return SearchResult(
            total_count=parsed.total_count,
            page_no=parsed.page_no,
            num_of_rows=parsed.num_of_rows,
            result_code=parsed.result_code,
            result_msg=parsed.result_msg,
            candidates=candidates,
        )

    def get_detail_section(self, chem_id: str, section: int | str) -> SectionFetch:
        cid = normalize_chem_id(chem_id)
        if not cid:
            raise KoshaMsdsClientError("CHEM_ID_REQUIRED", "detail fetch requires chemId")
        token = section_token(section)
        _, text, key = self._get(
            f"{DETAIL_OPERATION_PREFIX}{token}",
            {"chemId": cid},
        )
        try:
            parsed = parse_section_xml(text, require_success=True)
        except KoshaMsdsResultError as exc:
            raise KoshaMsdsClientError("RESULT_CODE", redact_secret(exc.result_msg, key)) from exc
        status = DETAIL_EMPTY_BUT_VALID if parsed.empty_but_valid else DETAIL_COMPLETE
        if parsed.result_code not in SUCCESS_RESULT_CODES:
            status = DETAIL_INCOMPLETE
        return SectionFetch(
            section_no=int(token),
            result_code=parsed.result_code,
            result_msg=parsed.result_msg,
            items=parsed.items,
            status=status,
        )

    def get_full_detail(self, chem_id: str) -> FullDetail:
        cid = normalize_chem_id(chem_id)
        if not cid:
            raise KoshaMsdsClientError("CHEM_ID_REQUIRED", "detail fetch requires chemId")
        sections: dict[str, SectionFetch] = {}
        failed: list[int] = []
        for n in ALLOWED_SECTIONS:
            try:
                fetched = self.get_detail_section(cid, n)
                sections[f"{n:02d}"] = fetched
                if fetched.result_code not in SUCCESS_RESULT_CODES:
                    failed.append(n)
            except (KoshaMsdsClientError, KoshaMsdsParseError, KoshaMsdsTransportError):
                failed.append(n)
        detail_status = DETAIL_COMPLETE if not failed and len(sections) == 16 else DETAIL_INCOMPLETE
        return FullDetail(
            chem_id=cid,
            sections=sections,
            detail_status=detail_status,
            failed_sections=tuple(failed),
        )


def masked_query(params: dict[str, str]) -> str:
    redacted = dict(params)
    if "serviceKey" in redacted:
        redacted["serviceKey"] = "[REDACTED]"
    return urlencode(redacted)
