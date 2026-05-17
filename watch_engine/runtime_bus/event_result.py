"""Event Result — emit \uacb0\uacfc \ud45c\uc900."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EventResult:
    status: str  # accepted, accepted_with_warning, blocked, failed
    event_id: Optional[str] = None
    validation_status: str = "passed"  # passed, warning, blocked
    warnings: list = field(default_factory=list)
    blocked_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "event_id": self.event_id,
            "validation_status": self.validation_status,
            "warnings": self.warnings,
            "blocked_reason": self.blocked_reason,
            "error": self.error,
        }

    @property
    def accepted(self) -> bool:
        return self.status in ("accepted", "accepted_with_warning")
