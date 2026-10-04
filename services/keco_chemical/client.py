"""KECO 15149420 공식 API HTTP client. kr_get 사용. serviceKey 절대 노출 금지."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from services.kr_public_api import kr_get
from services.keco_chemical.contract import (
    ALLOWED_SEARCH_GUBUN,
    BASE_URL,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_NUM_OF_ROWS,
    DEFAULT_PAGE_NO,
    DEFAULT_TIMEOUT_SECONDS,
    ERROR_AUTH,
    ERROR_RATE_LIMIT,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    ERROR_UPSTREAM,
    ERROR_VALIDATION,
    NON_RETRY_CODES,
    OPERATION,
    RATE_LIMIT_DAILY_CODES,
    RATE_LIMIT_SECOND_CODES,
    RETRY_CODES,
    RETURN_TYPE_JSON,
    SERVICE_KEY_ENV,
    SUCCESS_RESULT_CODES,
)
from services.keco_chemical.parse import (
    KecoParseError,
    KecoResultError,
    KecoSearchResponse,
    parse_keco_response,
)

logger = logging.getLogger(__name__)

GetFn = Callable[..., tuple[int, str]]


class KecoChemicalClientError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class KecoNoServiceKeyError(KecoChemicalClientError):
    def __init__(self):
        super().__init__("SERVICE_KEY_MISSING", "KECO_API_SERVICE_KEY is not set or empty")


class KecoTransportError(KecoChemicalClientError):
    def __init__(self, http_status: int, snippet: str):
        super().__init__("TRANSPORT", f"HTTP {http_status}: {snippet}")
        self.http_status = http_status
        self.snippet = snippet


def redact_key(text: str, key: str) -> str:
    """serviceKey를 [REDACTED]로 치환. 로깅·에러메시지 전용."""
    if not text:
        return text
    out = text
    if key:
        out = out.replace(key, "[REDACTED]")
    return re.sub(r"serviceKey=[^&\s\"']+", "serviceKey=[REDACTED]", out)


def _get_service_key() -> str:
    """KECO_API_SERVICE_KEY 환경변수에서만 읽기. 다른 키 fallback 금지."""
    for name in SERVICE_KEY_ENV:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _classify_error_code(code: str) -> str:
    """GW/기관 에러 코드 → error classification 레이블."""
    if code in {"91", "93"}:
        return ERROR_AUTH
    if code in {"95", "97"}:
        return ERROR_VALIDATION
    if code in RATE_LIMIT_DAILY_CODES | RATE_LIMIT_SECOND_CODES:
        return ERROR_RATE_LIMIT
    if code in {"10", "12"}:
        return ERROR_UPSTREAM
    if code in {"20", "30", "31"}:
        return ERROR_UPSTREAM
    if code in {"200"}:
        return ERROR_UPSTREAM
    return ERROR_UNKNOWN


@dataclass
class KecoChemicalClient:
    """KECO 15149420 API client. serviceKey는 환경변수에서만 읽음."""
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    get_fn: GetFn = field(default=kr_get)
    _service_key: Optional[str] = field(default=None, repr=False)

    def _key(self) -> str:
        """키 획득 — 없으면 KecoNoServiceKeyError."""
        key = (self._service_key or _get_service_key()).strip()
        if not key:
            raise KecoNoServiceKeyError()
        return key

    def _get(self, params: dict[str, str]) -> tuple[int, str, str]:
        """HTTP GET 실행. (http_status, response_text, key) 반환."""
        key = self._key()
        query = dict(params)
        query["serviceKey"] = key
        url = f"{BASE_URL}/{OPERATION}"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                status, text = self.get_fn(url, params=query, timeout=self.timeout_seconds)
            except Exception as exc:
                last_exc = exc
                err_str = redact_key(str(exc), key)
                if "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    if attempt >= self.max_attempts:
                        raise KecoChemicalClientError(ERROR_TIMEOUT, err_str) from exc
                else:
                    if attempt >= self.max_attempts:
                        raise KecoTransportError(0, err_str) from exc
                continue

            snippet = redact_key((text or "")[:240], key)
            if status >= 500 and attempt < self.max_attempts:
                last_exc = KecoTransportError(status, snippet)
                continue
            if status != 200:
                raise KecoTransportError(status, snippet)
            return status, text, key

        raise last_exc or KecoTransportError(0, "exhausted retries")

    def search(
        self,
        search_gubun: str,
        search_nm: str,
        page_no: int = DEFAULT_PAGE_NO,
        num_of_rows: int = DEFAULT_NUM_OF_ROWS,
        return_type: str = RETURN_TYPE_JSON,
    ) -> KecoSearchResponse:
        """KECO chemSbstnList 검색.

        Args:
            search_gubun: "1"=영문명, "2"=CAS번호, "3"=고유번호 (국문명 없음)
            search_nm: 검색어
            page_no: 페이지번호 (default 1)
            num_of_rows: 페이지당 결과 수 (default 10)
            return_type: "JSON" 또는 "XML"

        Raises:
            ValueError: searchGubun이 ALLOWED_SEARCH_GUBUN에 없을 때
            KecoNoServiceKeyError: 키 미설정
            KecoChemicalClientError: API 에러
        """
        if search_gubun not in ALLOWED_SEARCH_GUBUN:
            raise ValueError(
                f"searchGubun '{search_gubun}'은 허용되지 않습니다. "
                f"허용값: {sorted(ALLOWED_SEARCH_GUBUN)} (국문명 코드 없음)"
            )
        if page_no < 1:
            raise KecoChemicalClientError(ERROR_VALIDATION, "pageNo must be >= 1")
        if num_of_rows < 1:
            raise KecoChemicalClientError(ERROR_VALIDATION, "numOfRows must be >= 1")

        params = {
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
            "searchGubun": search_gubun,
            "searchNm": search_nm,
            "returnType": return_type,
        }

        logger.debug(
            "KECO search: searchGubun=%s searchNm=%s pageNo=%s numOfRows=%s serviceKey=[REDACTED]",
            search_gubun, search_nm, page_no, num_of_rows,
        )

        _, text, key = self._get(params)

        try:
            parsed = parse_keco_response(text)
        except KecoParseError as exc:
            raise KecoChemicalClientError(exc.code, redact_key(exc.message, key)) from exc

        if parsed.result_code and parsed.result_code not in SUCCESS_RESULT_CODES:
            err_class = _classify_error_code(parsed.result_code)
            msg = redact_key(parsed.result_msg or parsed.result_code, key)
            if err_class == ERROR_RATE_LIMIT:
                raise KecoChemicalClientError(ERROR_RATE_LIMIT, msg)
            raise KecoChemicalClientError(err_class, msg)

        return parsed
