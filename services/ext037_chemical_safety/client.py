"""EXT-037 HTTP client — 화학안전원 화학물질안전정보 API 호출."""
from __future__ import annotations

import os
from typing import Any

from services.ext037_chemical_safety.contract import (
    BASE_URL,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_ENV,
)


def _service_key() -> str:
    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "")
    if not key:
        raise EnvironmentError("DATA_GO_KR_SERVICE_KEY not set")
    return key


def fetch_page(
    page_no: int,
    *,
    num_of_rows: int | None = None,
    timeout: int = 60,
) -> bytes:
    """Fetch a single XML page from the EXT-037 API.

    EXT-037은 연도 필터 없이 전체 수집만 지원 (G1 probe 확인).
    """
    from services.kr_public_api import kr_get

    size = num_of_rows or int(
        os.getenv(PAGE_SIZE_ENV, str(PAGE_SIZE_DEFAULT))
    )
    params: dict[str, Any] = {
        "serviceKey": _service_key(),
        "pageNo": page_no,
        "numOfRows": size,
        "type": "xml",
    }

    status_code, text = kr_get(BASE_URL, params=params, timeout=timeout)
    if status_code == 401:
        raise EnvironmentError("API authentication failed (HTTP 401) — check DATA_GO_KR_SERVICE_KEY")
    if status_code == 429:
        raise IOError("API rate limit exceeded (HTTP 429)")
    if status_code >= 400:
        raise IOError(f"API HTTP error {status_code}")
    return text.encode("utf-8")
