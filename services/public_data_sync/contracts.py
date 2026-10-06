"""Control Plane contracts — enums, frozen specs, run context/result."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceMode(str, Enum):
    FULL_SNAPSHOT = "FULL_SNAPSHOT"
    INCREMENTAL = "INCREMENTAL"
    ENUMERATE_HYDRATE = "ENUMERATE_HYDRATE"
    TARGET_REFRESH = "TARGET_REFRESH"
    FILE_SNAPSHOT = "FILE_SNAPSHOT"
    LIVE_PROXY = "LIVE_PROXY"
    LIVE_CONTEXT = "LIVE_CONTEXT"
    LOOKUP = "LOOKUP"
    LOOKUP_PERSIST_ON_ACTION = "LOOKUP_PERSIST_ON_ACTION"
    DISCOVERY = "DISCOVERY"


class SourceKind(str, Enum):
    API = "API"
    FILE = "FILE"
    EDGE = "EDGE"
    INTERNAL = "INTERNAL"


class TriggerKind(str, Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    RETRY = "RETRY"


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_CHANGE = "NO_CHANGE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# Secret sanitization
# ---------------------------------------------------------------------------

_SECRET_KEY = re.compile(
    r"(servicekey|apikey|service_key|authorization|secret|token|password|credential)",
    re.IGNORECASE,
)

# Authorization headers can carry multi-word values (e.g. "Bearer TOKEN", "Basic ABC").
# Capture everything to end of line so no credential bytes leak.
_INLINE_SECRET_AUTH = re.compile(
    r"(authorization\s*[=:]\s*)([^\n]+)",
    re.IGNORECASE,
)

# All other secret keys carry single-word values — stop at whitespace/punctuation.
_INLINE_SECRET_KEY = re.compile(
    r"((?:servicekey|apikey|service_key|secret|token|password|credential)\s*[=:]\s*)([^\s,&'\"]+)",
    re.IGNORECASE,
)


def _redact_string(s: str) -> str:
    s = _INLINE_SECRET_AUTH.sub(r"\1***", s)
    s = _INLINE_SECRET_KEY.sub(r"\1***", s)
    return s


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "***" if _SECRET_KEY.search(str(k)) else _sanitize_value(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(x) for x in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(x) for x in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


# ---------------------------------------------------------------------------
# SourceSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    provider: str
    dataset_id: str
    source_kind: SourceKind
    sync_mode: SourceMode
    adapter_key: str
    credential_pool: str
    rate_limit_group: str
    refresh_policy: str
    max_concurrency: int = 1
    max_requests_per_run: int | None = None
    max_run_seconds: int = 3600
    persisted: bool = True
    auto_refresh_candidate: bool = True
    consumer_tags: tuple[str, ...] = ()
    display_name: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    run_id: str
    source_id: str
    trigger: TriggerKind
    dry_run: bool = False
    started_at: datetime | None = None
    request_budget: int | None = None
    deadline: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    run_id: str
    source_id: str
    status: RunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    fetched: int = 0
    created: int = 0
    changed: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: int = 0
    source_version: str | None = None
    content_hash: str | None = None
    change_detected: bool = False
    error_code: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.details = _sanitize_value(self.details)
        if self.error_message is not None:
            self.error_message = _redact_string(self.error_message)
