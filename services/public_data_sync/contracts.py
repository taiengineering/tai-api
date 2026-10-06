"""Control Plane contracts — enums, frozen specs, run context/result."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


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
    REST = "REST"
    FILE = "FILE"
    EDGE = "EDGE"
    DB = "DB"


class TriggerKind(str, Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    EVENT = "EVENT"


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


_SECRET_PATTERN = re.compile(
    r"(servicekey|apikey|service_key|authorization|secret|token|password|credential)",
    re.IGNORECASE,
)


def _sanitize(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        k: "***" if _SECRET_PATTERN.search(k) else _sanitize(v)
        for k, v in value.items()
    }


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    display_name: str
    sync_mode: SourceMode
    source_kind: SourceKind
    credential_pool: str
    rate_limit_group: str
    consumer_tags: tuple[str, ...]
    auto_refresh_candidate: bool = True
    notes: str = ""


@dataclass
class RunContext:
    source_id: str
    trigger: TriggerKind
    params: dict[str, Any] = field(default_factory=dict)
    triggered_at: datetime | None = None


@dataclass
class RunResult:
    source_id: str
    status: RunStatus
    rows_affected: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        self.detail = _sanitize(self.detail)
