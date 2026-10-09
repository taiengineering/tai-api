"""Generic HTTP request budget — physical attempt counter with hard limit.

Decoupled from any specific data source. consume_or_raise() should be called
immediately before each physical HTTP attempt (including retries).
"""
from __future__ import annotations

from dataclasses import dataclass, field


class RequestBudgetExceeded(Exception):
    def __init__(self, used: int, limit: int) -> None:
        super().__init__(f"request budget exhausted: used={used} limit={limit}")
        self.used = used
        self.limit = limit


@dataclass
class RequestBudget:
    """Hard budget on physical HTTP attempts. 1 attempt = 1 unit, regardless of HTTP status."""

    limit: int
    used: int = field(default=0)

    def consume_or_raise(self, n: int = 1) -> None:
        """Raise RequestBudgetExceeded before the attempt if it would exceed limit."""
        if self.used + n > self.limit:
            raise RequestBudgetExceeded(self.used, self.limit)
        self.used += n

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit
