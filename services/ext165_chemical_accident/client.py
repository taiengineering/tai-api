"""EXT-165 HTTP client — 화학물질안전원 화학사고 API 호출."""
from __future__ import annotations

import os
from typing import Any

from services.ext165_chemical_accident.contract import (
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
    yyyy: str | None = None,
    timeout: int = 60,
) -> bytes:
    """Fetch a single XML page from the EXT-165 API.

    yyyy: optional year filter (e.g. "2024"). None = all years.
    num_of_rows: UNVERIFIED maximum — callers should pass conservatively.
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
    if yyyy is not None:
        params["yyyy"] = yyyy

    resp = kr_get(BASE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.content
