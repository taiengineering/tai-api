"""Translation Context — 번역에 필요한 컨텍스트 정보."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranslationContext:
    """이벤트 번역 시 참조하는 컨텍스트."""

    event_type: str
    flow_key: str | None = None
    severity: str = "INFO"
    domain: str | None = None
    count: int | None = None
    window_minutes: int | None = None
    trace_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> TranslationContext:
        """Runtime event dict → TranslationContext."""
        return cls(
            event_type=event.get("event_type", "unknown"),
            flow_key=event.get("flow_key"),
            severity=event.get("severity", "INFO"),
            domain=event.get("domain"),
            count=event.get("count"),
            window_minutes=event.get("window_minutes"),
            trace_id=event.get("trace_id"),
            extra={k: v for k, v in event.items()
                   if k not in {"event_type", "flow_key", "severity",
                                "domain", "count", "window_minutes", "trace_id"}},
        )
