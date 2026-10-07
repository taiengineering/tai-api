"""CSI accident dynamic refresh — discover latest portal artifact, sync if new.

Flow:
  load latest COMPLETED snapshot
       ↓
  extract current artifact identity (effective_date, attachment_id, file_detail_sn)
       ↓
  discover_latest_artifact()
       ↓
  NO_CHANGE  → return immediately, full CSV download = 0, DML = 0
  FAILED     → return FAILED, full CSV download = 0, DML = 0
  NEW_ARTIFACT → download once, validate, _sync_csi_bytes()
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.request import Request, urlopen

from services.csi_accidents.contract import (
    ALLOWED_DOWNLOAD_HOSTS,
    APPLY_ENABLE_ENV,
    DATASET_ID,
    DOWNLOAD_PATH,
)
from services.csi_accidents.discovery import (
    DiscoveryError,
    discover_latest_artifact,
    parse_download_identity,
)
from services.csi_accidents.sync import (
    SyncResult,
    _sync_csi_bytes,
    file_sha256,
)
from services.csi_accidents.store import SupabaseCsiStore

_USER_AGENT = "tai-api-csi-refresh/1.0"
_DOWNLOAD_TIMEOUT = 300


class RefreshError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RefreshResult:
    status: str                              # NO_CHANGE / COMPLETED / FAILED
    discovery_status: str = ""
    effective_date: Optional[str] = None
    attachment_id: Optional[str] = None
    file_detail_sn: Optional[str] = None
    downloaded: bool = False
    bytes: int = 0
    sha256: Optional[str] = None
    filename: Optional[str] = None
    parsed_rows: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    snapshot_id: Optional[str] = None
    metadata_requests: int = 0
    full_csv_downloads: int = 0
    dml: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    details: dict = field(default_factory=dict)


# ─── Download helpers ──────────────────────────────────────────────────────────

def _validate_download_fence(url: str) -> None:
    """Re-validate download URL is still within the allowed fence."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RefreshError("CSI_DOWNLOAD_FENCE", f"scheme {parsed.scheme!r} not allowed")
    if parsed.netloc not in ALLOWED_DOWNLOAD_HOSTS:
        raise RefreshError("CSI_DOWNLOAD_FENCE", f"host {parsed.netloc!r} not in allowlist")
    if parsed.path != DOWNLOAD_PATH:
        raise RefreshError("CSI_DOWNLOAD_FENCE", f"path {parsed.path!r} not allowed")


def _extract_filename(headers: Any) -> Optional[str]:
    """Extract filename from Content-Disposition header.

    Handles RFC 5987 filename*= and plain filename= forms.
    Returns None if filename cannot be resolved.
    """
    cd = headers.get("Content-Disposition", "") if hasattr(headers, "get") else ""
    if not cd:
        return None

    # RFC 5987: filename*=charset''encoded
    m = re.search(r"filename\*\s*=\s*([^;]+)", cd, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        parts = raw.split("''", 1)
        if len(parts) == 2:
            charset, encoded = parts
            try:
                from urllib.parse import unquote
                decoded = unquote(encoded, encoding=charset.strip() or "utf-8")
                if decoded:
                    return decoded
            except Exception:
                pass

    # filename="value"
    m = re.search(r'filename\s*=\s*"([^"]*)"', cd, re.IGNORECASE)
    if m and m.group(1):
        return m.group(1)

    # filename=value (no quotes)
    m = re.search(r'filename\s*=\s*([^\s;]+)', cd, re.IGNORECASE)
    if m and m.group(1):
        return m.group(1)

    return None


def _download_artifact(
    url: str,
    *,
    http_download: Optional[Callable[[str], tuple[bytes, str]]] = None,
    timeout: int = _DOWNLOAD_TIMEOUT,
) -> tuple[bytes, str]:
    """Download CSV from url, return (data, filename).

    http_download is injectable for tests: callable(url) → (bytes, filename).
    Raises RefreshError if filename cannot be resolved.
    """
    _validate_download_fence(url)

    if http_download is not None:
        return http_download(url)

    req = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        filename = _extract_filename(resp.headers)

    if not filename:
        raise RefreshError(
            "CSI_FILENAME_UNRESOLVED",
            "Content-Disposition header missing or filename not parseable",
        )
    return data, filename


# ─── Public API ────────────────────────────────────────────────────────────────

def refresh_latest_csi_artifact(
    *,
    http_get=None,
    http_download: Optional[Callable[[str], tuple[bytes, str]]] = None,
    store: Any = None,
    now=None,
    uuid_fn=None,
) -> RefreshResult:
    """Discover the latest CSI artifact and sync it only if it has changed.

    Requires APPLY_ENABLE_ENV=1 and a valid store for DB writes.

    Returns:
      NO_CHANGE  — portal artifact matches current snapshot (zero downloads, zero DML)
      COMPLETED  — new artifact downloaded and synced
      FAILED     — any step failed (existing snapshot preserved)
    """
    if store is None:
        from db.supabase_client import get_supabase
        store = SupabaseCsiStore(get_supabase())

    # Step 1: Load current baseline
    latest = store.get_latest_completed() if hasattr(store, "get_latest_completed") else None
    if latest is None:
        return RefreshResult(
            status="FAILED",
            error_code="CSI_BASELINE_MISSING",
            error_message="no COMPLETED snapshot found; manual bootstrap required",
        )

    # Step 2: Extract current artifact identity from stored download_url
    stored_url = latest.get("download_url") or ""
    if not stored_url:
        return RefreshResult(
            status="FAILED",
            error_code="CSI_IDENTITY_PARSE_ERROR",
            error_message="latest COMPLETED snapshot has no download_url",
        )
    try:
        attachment_id, file_detail_sn = parse_download_identity(stored_url)
    except DiscoveryError as exc:
        return RefreshResult(
            status="FAILED",
            error_code="CSI_IDENTITY_PARSE_ERROR",
            error_message=type(exc).__name__,
        )

    known_effective_date: str = latest.get("effective_date") or ""

    # Step 3: Discover latest artifact (2 metadata requests)
    disc = discover_latest_artifact(
        http_get=http_get,
        known_attachment_id=attachment_id,
        known_file_detail_sn=file_detail_sn,
        known_effective_date=known_effective_date,
    )

    if disc.status == "FAILED":
        return RefreshResult(
            status="FAILED",
            discovery_status="FAILED",
            metadata_requests=2,
            error_code=disc.error_code,
            error_message=disc.error_message,
        )

    if disc.status == "NO_CHANGE":
        return RefreshResult(
            status="NO_CHANGE",
            discovery_status="NO_CHANGE",
            effective_date=disc.artifact.effective_date if disc.artifact else known_effective_date,
            attachment_id=attachment_id,
            file_detail_sn=file_detail_sn,
            downloaded=False,
            metadata_requests=2,
            full_csv_downloads=0,
            dml=0,
        )

    # Step 4: NEW_ARTIFACT — download once
    desc = disc.artifact
    assert desc is not None  # guaranteed when status == NEW_ARTIFACT

    try:
        data, filename = _download_artifact(desc.download_url, http_download=http_download)
    except RefreshError as exc:
        return RefreshResult(
            status="FAILED",
            discovery_status="NEW_ARTIFACT",
            metadata_requests=2,
            full_csv_downloads=0,
            error_code=exc.code,
            error_message=exc.message,
        )
    except Exception as exc:
        return RefreshResult(
            status="FAILED",
            discovery_status="NEW_ARTIFACT",
            metadata_requests=2,
            full_csv_downloads=0,
            error_code="CSI_DOWNLOAD_ERROR",
            error_message=type(exc).__name__,
        )

    sha = file_sha256(data)

    # Step 5: Dynamic sync — declared_rows=None → PARSED_FALLBACK
    sync_result: SyncResult = _sync_csi_bytes(
        data,
        filename,
        effective_date=desc.effective_date,
        download_url=desc.download_url,
        declared_rows=None,
        dry_run=False,
        store=store,
        now=now,
        uuid_fn=uuid_fn,
    )

    if sync_result.status in ("REJECT", "FAILED"):
        return RefreshResult(
            status="FAILED",
            discovery_status="NEW_ARTIFACT",
            effective_date=desc.effective_date,
            attachment_id=desc.attachment_id,
            file_detail_sn=desc.file_detail_sn,
            downloaded=True,
            bytes=len(data),
            sha256=sha,
            filename=filename,
            metadata_requests=2,
            full_csv_downloads=1,
            dml=sync_result.business_dml,
            error_code=sync_result.extra.get("error_code") or sync_result.status,
            error_message=sync_result.failure_reason,
        )

    return RefreshResult(
        status="COMPLETED",
        discovery_status="NEW_ARTIFACT",
        effective_date=desc.effective_date,
        attachment_id=desc.attachment_id,
        file_detail_sn=desc.file_detail_sn,
        downloaded=True,
        bytes=len(data),
        sha256=sha,
        filename=filename,
        parsed_rows=sync_result.parsed_rows,
        new=sync_result.new,
        changed=sync_result.changed,
        unchanged=sync_result.unchanged,
        snapshot_id=sync_result.snapshot_id,
        metadata_requests=2,
        full_csv_downloads=1,
        dml=sync_result.business_dml,
        details={
            "declared_rows_source": sync_result.extra.get("declared_rows_source"),
        },
    )


__all__ = [
    "RefreshError",
    "RefreshResult",
    "refresh_latest_csi_artifact",
]
