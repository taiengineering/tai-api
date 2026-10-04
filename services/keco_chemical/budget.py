"""KECO Request Budget — 물리적 HTTP 시도 기준 예산 관리.

consume_or_raise() 는 client._get() 내부에서 HTTP GET 시도 직전에 호출된다.
timeout retry 포함 물리적 시도 1회 = 1 unit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from services.keco_chemical.contract import DEFAULT_REQUEST_BUDGET, REQUEST_BUDGET_ENV


class RequestBudgetExceeded(Exception):
    def __init__(self, used: int, limit: int):
        super().__init__(f"KECO request budget exhausted: used={used} limit={limit}")
        self.used = used
        self.limit = limit


@dataclass
class RequestBudget:
    """KECO 물리적 HTTP 시도 hard budget.

    consume_or_raise() 가 HTTP 시도 직전에 호출된다.
    성공/실패/timeout 무관하게 1시도 = 1 unit.
    """
    limit: int
    used: int = 0

    def consume_or_raise(self, n: int = 1) -> None:
        """HTTP 시도 직전 호출. 초과 시 RequestBudgetExceeded."""
        if self.used + n > self.limit:
            raise RequestBudgetExceeded(self.used, self.limit)
        self.used += n

    def consume(self, n: int = 1) -> None:
        """예외 없이 증가. 하위 호환 유지 전용."""
        self.used += n

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def check_available(self) -> bool:
        return not self.exhausted

    @classmethod
    def from_env(cls) -> "RequestBudget":
        raw = (os.getenv(REQUEST_BUDGET_ENV) or "").strip()
        try:
            limit = int(raw) if raw else DEFAULT_REQUEST_BUDGET
        except ValueError:
            limit = DEFAULT_REQUEST_BUDGET
        return cls(limit=limit)
