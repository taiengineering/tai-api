"""Classify asset-level storage failures as HOLD vs whole-run STOP.

Asset-local deterministic problems HOLD and continue.
Infrastructure, integrity, security, and unknown codes STOP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

REVIEW_REASON = "SOURCE_ASSET_REVIEW_REQUIRED"
REVIEW_SUBREASONS = frozenset({
    "PDF_MAGIC_MISMATCH",
    "HTML_NOT_BINARY",
    "JSON_NOT_BINARY",
    "TEXT_NOT_BINARY",
    "LICENSE_CHANGED_REVIEW_REQUIRED",
    "SOURCE_MEDSEQ_MISMATCH",
})
CONTENT_STREAK_SUBREASONS = frozenset({
    "PDF_MAGIC_MISMATCH",
    "HTML_NOT_BINARY",
    "JSON_NOT_BINARY",
    "TEXT_NOT_BINARY",
})
SYSTEMIC_STOP = "SYSTEMIC_SOURCE_RESPONSE_ANOMALY"
STREAK_LIMIT = 3

EXISTING_HOLD_REASONS = frozenset({
    "SOURCE_ASSET_FILENAME_MISMATCH",
    "SOURCE_ASSET_ZERO_MATCH",
    "SOURCE_ASSET_MULTI_MATCH",
    "SOURCE_ASSET_OVERSIZE_POLICY",
    "SOURCE_BINARY_UNAVAILABLE",
})

STOP_CODES = frozenset({
    "R2_ACCESS_BLOCKED",
    "R2_HEAD_AUTH",
    "QUOTA_BLOCKED",
    "ACCESS_BLOCKED",
    "TRANSIENT_UPSTREAM_FAILURE",
    "READBACK_MISMATCH",
    "R2_OBJECT_CONFLICT",
    "VERSION_OBJECT_MISSING",
    "VERSION_READBACK_MISMATCH",
    "CURRENT_NOT_UNIQUE",
    "ASSET_ID_REQUIRED",
    "HISTORICAL_STORAGE_FORBIDDEN",
    "PENDING_NO_PROGRESS",
    "MEMORY_STORE_FORBIDDEN",
    "MEMORY_HOLD_STORE_FORBIDDEN",
    "HOST_NOT_ALLOWED",
    "REDIRECT_HOST_BLOCKED",
    "SCHEME_NOT_ALLOWED",
    "EMPTY_BODY",
    "SOURCE_ASSET_RESOLUTION_BLOCKED",
})


@dataclass
class FailureDecision:
    action: str
    reason: str
    subreason: str | None = None
    evidence: dict = field(default_factory=dict)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_asset_failure(
    code: str | None,
    *,
    item: dict | None = None,
    http_status=None,
    body_bytes_read=None,
    declared_content_length=None,
    source_med_seq=None,
) -> FailureDecision:
    """HOLD only for explicit allowlists. Everything else STOP."""
    item = item or {}
    code = str(code or "")
    evidence = {
        "subreason": code or None,
        "http_status": http_status,
        "body_bytes_read": body_bytes_read,
        "declared_content_length": declared_content_length,
        "file_name": item.get("file_name"),
        "file_size": item.get("file_size"),
        "source_med_seq": source_med_seq or item.get("source_med_seq"),
        "observed_at": _utc(),
    }
    if code in REVIEW_SUBREASONS:
        return FailureDecision("HOLD", REVIEW_REASON, code, evidence)
    if code in EXISTING_HOLD_REASONS:
        return FailureDecision("HOLD", code, None, evidence)
    stop_reason = code if code in STOP_CODES else (code or "UNKNOWN_STORAGE_FAILURE")
    if code in STOP_CODES and code != "EMPTY_BODY":
        return FailureDecision("STOP", stop_reason, code if code != stop_reason else None, evidence)
    if code == "EMPTY_BODY":
        return FailureDecision("STOP", "BINARY_INTEGRITY_BLOCKED", "EMPTY_BODY", evidence)
    if code == "BINARY_INTEGRITY_BLOCKED":
        return FailureDecision("STOP", "BINARY_INTEGRITY_BLOCKED", None, evidence)
    return FailureDecision("STOP", stop_reason if stop_reason else "UNKNOWN_STORAGE_FAILURE", code or None, evidence)


class ContentAnomalyGuard:
    """In-process fuse: 3 consecutive same content-response failures → STOP."""

    def __init__(self, limit: int = STREAK_LIMIT):
        self.limit = limit
        self.subreason = None
        self.count = 0

    def reset(self) -> None:
        self.subreason = None
        self.count = 0

    def note(self, *, status: str | None, subreason: str | None) -> str | None:
        if status != "HOLD" or subreason not in CONTENT_STREAK_SUBREASONS:
            self.reset()
            return None
        if subreason == self.subreason:
            self.count += 1
        else:
            self.subreason = subreason
            self.count = 1
        if self.count >= self.limit:
            return SYSTEMIC_STOP
        return None
