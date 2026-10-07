"""CSI accident portal discovery — finds the latest official CSV artifact from
data.go.kr dataset 15108262 without browser, login, or full-file download.

Two HTTP requests are made:
  1. METADATA_URL (fileData.json)  → alternateName, dateModified, dataset identity
  2. DATASET_URL  (fileData.do)    → JSON-LD distribution contentUrl → attachment ID

Callers must provide http_get for testing (default uses urllib with bounded retry).
Change detection is the caller's responsibility: pass all three of
(known_attachment_id, known_file_detail_sn, known_effective_date) as non-None for
NO_CHANGE/NEW_ARTIFACT; omit all (or pass all=None) for DISCOVERED;
any partial supply → FAILED/COMPARISON_INPUT_INCOMPLETE.
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
    DATASET_ID,
    DATASET_NAME,
    DATASET_URL,
    DOWNLOAD_PATH,
    METADATA_URL,
)

_USER_AGENT = "tai-api-csi-discovery/1.0"
_TIMEOUT = 30
_MAX_ATTEMPTS = 3

# CSV is the required format; text/csv is a normalized alias
_ALLOWED_CSV_FORMATS: frozenset[str] = frozenset({"CSV", "TEXT/CSV"})

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


# ─── Validation helpers ───────────────────────────────────────────────────────

_EXPECTED_DATASET_PATH = f"/data/{DATASET_ID}/fileData.do"


def _validate_dataset_url(url: str) -> None:
    """Strict path-level fence: scheme+host+path must match dataset 15108262."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in ALLOWED_DOWNLOAD_HOSTS
        or parsed.path != _EXPECTED_DATASET_PATH
    ):
        raise DiscoveryError(
            "DATASET_ID_MISMATCH",
            f"metadata url {url!r} does not match dataset {DATASET_ID!r} identity",
        )


def _validate_dataset_name(name: str) -> None:
    if name.strip() != DATASET_NAME:
        raise DiscoveryError(
            "DATASET_NAME_MISMATCH",
            f"metadata name {name!r} does not match expected {DATASET_NAME!r}",
        )


def _parse_effective_date(alternate_name: str) -> str:
    m = re.search(r"_(\d{8})$", alternate_name)
    if not m:
        raise DiscoveryError(
            "EFFECTIVE_DATE_UNRESOLVED",
            f"cannot extract YYYYMMDD from alternateName: {alternate_name!r}",
        )
    d = m.group(1)
    try:
        datetime.strptime(d, "%Y%m%d")
    except ValueError:
        raise DiscoveryError(
            "EFFECTIVE_DATE_UNRESOLVED",
            f"date token {d!r} is not a valid calendar date",
        )
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _validate_download_url(url: str) -> None:
    """Strict scheme + host + path fence for download URLs."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise DiscoveryError(
            "UNTRUSTED_DOWNLOAD_HOST",
            f"scheme {parsed.scheme!r} not allowed (https only)",
        )
    if parsed.netloc not in ALLOWED_DOWNLOAD_HOSTS:
        raise DiscoveryError(
            "UNTRUSTED_DOWNLOAD_HOST",
            f"download host {parsed.netloc!r} not in allowlist",
        )
    if parsed.path != DOWNLOAD_PATH:
        raise DiscoveryError(
            "UNTRUSTED_DOWNLOAD_HOST",
            f"download path {parsed.path!r} not allowed (expected {DOWNLOAD_PATH!r})",
        )


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


def _collect_csv_content_urls(json_ld_blocks: list[dict]) -> list[str]:
    """Return contentUrl values from distributions whose encodingFormat is CSV only.

    Distributions with a missing, blank, or non-CSV encodingFormat are silently
    skipped. This is fail-closed: unknown formats are never treated as CSV.
    """
    urls: list[str] = []
    for block in json_ld_blocks:
        for dist in block.get("distribution", []):
            if not isinstance(dist, dict):
                continue
            fmt = (dist.get("encodingFormat") or "").strip().upper()
            if fmt not in _ALLOWED_CSV_FORMATS:
                continue
            url = (dist.get("contentUrl") or "").strip()
            if url:
                urls.append(url)
    return urls


def _parse_attachment(url: str) -> tuple[str, str]:
    """Return (atchFileId, fileDetailSn); both are required — no fallback."""
    params = parse_qs(urlparse(url).query)
    attachment_id = (params.get("atchFileId") or [None])[0]
    file_detail_sn = (params.get("fileDetailSn") or [None])[0]
    if not attachment_id:
        raise DiscoveryError(
            "DISCOVERY_PARSE_ERROR",
            "atchFileId missing from distribution contentUrl",
        )
    if file_detail_sn is None:
        raise DiscoveryError(
            "DISCOVERY_PARSE_ERROR",
            "fileDetailSn missing from distribution contentUrl",
        )
    return attachment_id, file_detail_sn


def parse_download_identity(url: str) -> tuple[str, str]:
    """Public: extract (attachment_id, file_detail_sn) from a data.go.kr download URL."""
    return _parse_attachment(url)


# ─── Public API ───────────────────────────────────────────────────────────────

def discover_latest_artifact(
    *,
    http_get: Optional[HttpGetFn] = None,
    known_attachment_id: Optional[str] = None,
    known_file_detail_sn: Optional[str] = None,
    known_effective_date: Optional[str] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> DiscoveryResult:
    """Discover the latest official CSI accident CSV artifact on data.go.kr.

    Change detection contract (all three fields required for comparison):
      all None       → DISCOVERED   (discovery only, no comparison)
      all non-None   → NO_CHANGE or NEW_ARTIFACT
      partial        → FAILED / COMPARISON_INPUT_INCOMPLETE
    """
    get = http_get or _default_http_get

    try:
        # now_fn is inside the boundary so failures are caught as DISCOVERY_UNEXPECTED
        now = (now_fn or (lambda: datetime.now(timezone.utc)))()
        discovered_at = now.isoformat()

        # ── Step 1: metadata JSON ────────────────────────────────────────────
        try:
            meta_bytes = get(METADATA_URL)
        except (HTTPError, URLError, OSError) as exc:
            raise DiscoveryError(
                "DISCOVERY_HTTP_ERROR",
                f"metadata fetch failed: {type(exc).__name__}",
            ) from exc

        try:
            meta = json.loads(meta_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DiscoveryError(
                "DISCOVERY_PARSE_ERROR",
                f"metadata JSON parse failed: {type(exc).__name__}",
            ) from exc

        _validate_dataset_url(meta.get("url", ""))
        _validate_dataset_name(meta.get("name", ""))

        alternate_name: str = meta.get("alternateName", "")
        portal_modified_at: str = meta.get("dateModified", "")
        effective_date = _parse_effective_date(alternate_name)

        # ── Step 2: HTML page → JSON-LD → CSV distribution contentUrls ──────
        try:
            page_bytes = get(DATASET_URL)
        except (HTTPError, URLError, OSError) as exc:
            raise DiscoveryError(
                "DISCOVERY_HTTP_ERROR",
                f"page fetch failed: {type(exc).__name__}",
            ) from exc

        try:
            html = page_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise DiscoveryError(
                "DISCOVERY_PARSE_ERROR",
                f"page decode failed: {type(exc).__name__}",
            ) from exc

        json_ld_blocks = _extract_json_ld_blocks(html)
        csv_urls = _collect_csv_content_urls(json_ld_blocks)

        if not csv_urls:
            raise DiscoveryError(
                "NO_ARTIFACT",
                "no CSV distribution contentUrl found in JSON-LD on page",
            )

        for url in csv_urls:
            _validate_download_url(url)

        # Dedupe by (attachment_id, file_detail_sn); distinct pairs = ambiguous
        seen: dict[tuple[str, str], str] = {}
        for url in csv_urls:
            att_id, fdsn = _parse_attachment(url)
            key = (att_id, fdsn)
            if key not in seen:
                seen[key] = url

        if len(seen) > 1:
            raise DiscoveryError(
                "AMBIGUOUS_LATEST_ARTIFACT",
                f"multiple distinct CSV attachments found: {sorted(seen.keys())}",
            )

        download_url = next(iter(seen.values()))
        attachment_id, file_detail_sn = _parse_attachment(download_url)

        artifact = CsiArtifactDescriptor(
            dataset_id=DATASET_ID,
            dataset_name=DATASET_NAME,
            effective_date=effective_date,
            alternate_name=alternate_name,
            download_url=download_url,
            attachment_id=attachment_id,
            file_detail_sn=file_detail_sn,
            portal_modified_at=portal_modified_at,
            discovered_at=discovered_at,
            source_page_url=DATASET_URL,
        )

        # ── Change detection (all three fields required) ─────────────────────
        known_fields = (known_attachment_id, known_file_detail_sn, known_effective_date)
        none_count = sum(1 for f in known_fields if f is None)

        if none_count == 3:
            return DiscoveryResult(status="DISCOVERED", artifact=artifact)

        if none_count > 0:
            raise DiscoveryError(
                "COMPARISON_INPUT_INCOMPLETE",
                "known_attachment_id, known_file_detail_sn, and known_effective_date must all be provided",
            )

        if (
            attachment_id == known_attachment_id
            and file_detail_sn == known_file_detail_sn
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
    except Exception as exc:
        return DiscoveryResult(
            status="FAILED",
            error_code="DISCOVERY_UNEXPECTED",
            error_message=type(exc).__name__,
        )


__all__ = [
    "CsiArtifactDescriptor",
    "DiscoveryError",
    "DiscoveryResult",
    "discover_latest_artifact",
    "parse_download_identity",
]
