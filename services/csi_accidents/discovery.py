"""CSI accident portal discovery — finds the latest official CSV artifact from
data.go.kr dataset 15108262 without browser, login, or full-file download.

Two HTTP requests are made:
  1. METADATA_URL (fileData.json)  → alternateName, dateModified, dataset identity
  2. DATASET_URL  (fileData.do)    → JSON-LD distribution contentUrl → attachment ID

Callers must provide http_get for testing (default uses urllib with bounded retry).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from services.csi_accidents.contract import (
    ALLOWED_DOWNLOAD_HOSTS,
    ATCH_FILE_ID,
    DATASET_EFFECTIVE_DATE,
    DATASET_ID,
    DATASET_URL,
    METADATA_URL,
)

_USER_AGENT = "tai-api-csi-discovery/1.0"
_TIMEOUT = 30
_MAX_ATTEMPTS = 3

HttpGetFn = Callable[[str], bytes]


class DiscoveryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CsiArtifactDescriptor:
    dataset_id: str
    dataset_name: str
    effective_date: str
    alternate_name: str
    download_url: str
    attachment_id: str
    file_detail_sn: str
    portal_modified_at: str
    discovered_at: str
    source_page_url: str
    filename: Optional[str] = None
    bytes: Optional[int] = None
    sha256: Optional[str] = None


@dataclass
class DiscoveryResult:
    status: str
    artifact: Optional[CsiArtifactDescriptor] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ─── HTTP ─────────────────────────────────────────────────────────────────────

def _default_http_get(url: str) -> bytes:
    last_exc: BaseException = RuntimeError("no attempts made")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            req = Request(url, headers={"User-Agent": _USER_AGENT})
            with urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read()
        except (HTTPError, URLError, OSError) as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                continue
    raise last_exc


# ─── Parsing helpers ──────────────────────────────────────────────────────────

def _parse_effective_date(alternate_name: str) -> str:
    m = re.search(r"_(\d{8})$", alternate_name)
    if not m:
        raise DiscoveryError(
            "EFFECTIVE_DATE_UNRESOLVED",
            f"cannot extract YYYYMMDD date from alternateName: {alternate_name!r}",
        )
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _extract_json_ld_blocks(html: str) -> list[dict]:
    blocks: list[dict] = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                blocks.append(obj)
        except (json.JSONDecodeError, ValueError):
            pass
    return blocks


def _collect_content_urls(json_ld_blocks: list[dict]) -> list[str]:
    urls: list[str] = []
    for block in json_ld_blocks:
        for dist in block.get("distribution", []):
            if isinstance(dist, dict):
                url = (dist.get("contentUrl") or "").strip()
                if url:
                    urls.append(url)
    return urls


def _validate_download_host(url: str) -> None:
    host = urlparse(url).netloc
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise DiscoveryError(
            "UNTRUSTED_DOWNLOAD_HOST",
            f"download host {host!r} not in allowlist {sorted(ALLOWED_DOWNLOAD_HOSTS)}",
        )


def _parse_attachment(url: str) -> tuple[str, str]:
    params = parse_qs(urlparse(url).query)
    attachment_id = (params.get("atchFileId") or [None])[0]
    file_detail_sn = (params.get("fileDetailSn") or ["1"])[0]
    if not attachment_id:
        raise DiscoveryError(
            "DISCOVERY_PARSE_ERROR",
            "atchFileId missing from distribution contentUrl",
        )
    return attachment_id, file_detail_sn


# ─── Public API ───────────────────────────────────────────────────────────────

def discover_latest_artifact(
    *,
    http_get: Optional[HttpGetFn] = None,
    known_attachment_id: Optional[str] = ATCH_FILE_ID,
    known_effective_date: Optional[str] = DATASET_EFFECTIVE_DATE,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> DiscoveryResult:
    """Discover the latest official CSI accident CSV artifact on data.go.kr.

    Returns NO_CHANGE when the discovered artifact matches known_attachment_id
    and known_effective_date. Returns NEW_ARTIFACT when either differs. Returns
    DISCOVERED when comparison data is not provided. Returns FAILED on any error.
    """
    get = http_get or _default_http_get
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    discovered_at = now.isoformat()

    try:
        # Step 1: metadata JSON → alternateName, dateModified, dataset identity
        try:
            meta_bytes = get(METADATA_URL)
        except (HTTPError, URLError, OSError) as exc:
            raise DiscoveryError(
                "DISCOVERY_HTTP_ERROR", f"metadata fetch failed: {type(exc).__name__}"
            ) from exc

        try:
            meta = json.loads(meta_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DiscoveryError(
                "DISCOVERY_PARSE_ERROR", f"metadata JSON parse failed: {type(exc).__name__}"
            ) from exc

        # Dataset identity fence
        dataset_url_in_meta: str = meta.get("url", "")
        if DATASET_ID not in dataset_url_in_meta:
            raise DiscoveryError(
                "DATASET_ID_MISMATCH",
                f"metadata url {dataset_url_in_meta!r} does not contain dataset_id={DATASET_ID!r}",
            )

        alternate_name: str = meta.get("alternateName", "")
        dataset_name: str = meta.get("name", "")
        portal_modified_at: str = meta.get("dateModified", "")
        effective_date = _parse_effective_date(alternate_name)

        # Step 2: HTML page → JSON-LD → distribution contentUrl
        try:
            page_bytes = get(DATASET_URL)
        except (HTTPError, URLError, OSError) as exc:
            raise DiscoveryError(
                "DISCOVERY_HTTP_ERROR", f"page fetch failed: {type(exc).__name__}"
            ) from exc

        try:
            html = page_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise DiscoveryError(
                "DISCOVERY_PARSE_ERROR", f"page decode failed: {type(exc).__name__}"
            ) from exc

        json_ld_blocks = _extract_json_ld_blocks(html)
        raw_urls = _collect_content_urls(json_ld_blocks)

        if not raw_urls:
            raise DiscoveryError(
                "NO_ARTIFACT",
                "no distribution contentUrl found in JSON-LD on page",
            )

        for url in raw_urls:
            _validate_download_host(url)

        # De-duplicate by attachment_id; multiple distinct IDs = ambiguous
        seen: dict[str, str] = {}  # attachment_id → url
        for url in raw_urls:
            att_id, _ = _parse_attachment(url)
            if att_id not in seen:
                seen[att_id] = url

        if len(seen) > 1:
            raise DiscoveryError(
                "AMBIGUOUS_LATEST_ARTIFACT",
                f"multiple distinct attachments found: {sorted(seen.keys())}",
            )

        download_url = next(iter(seen.values()))
        attachment_id, file_detail_sn = _parse_attachment(download_url)

        artifact = CsiArtifactDescriptor(
            dataset_id=DATASET_ID,
            dataset_name=dataset_name,
            effective_date=effective_date,
            alternate_name=alternate_name,
            download_url=download_url,
            attachment_id=attachment_id,
            file_detail_sn=file_detail_sn,
            portal_modified_at=portal_modified_at,
            discovered_at=discovered_at,
            source_page_url=DATASET_URL,
        )

        # Change detection
        if known_attachment_id is None or known_effective_date is None:
            return DiscoveryResult(status="DISCOVERED", artifact=artifact)

        if (
            attachment_id == known_attachment_id
            and effective_date == known_effective_date
        ):
            return DiscoveryResult(status="NO_CHANGE", artifact=artifact)

        return DiscoveryResult(status="NEW_ARTIFACT", artifact=artifact)

    except DiscoveryError as exc:
        return DiscoveryResult(
            status="FAILED",
            error_code=exc.code,
            error_message=exc.message,
        )


__all__ = [
    "CsiArtifactDescriptor",
    "DiscoveryError",
    "DiscoveryResult",
    "discover_latest_artifact",
]
