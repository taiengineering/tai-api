from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import Protocol

TAI_TIMEZONE = ZoneInfo("Asia/Seoul")

class Clock(Protocol):
    def now(self) -> datetime: ...          # aware UTC instant

class SystemClock:
    def now(self) -> datetime: return datetime.now(timezone.utc)

class FixedClock:
    def __init__(self, instant: datetime):
        if instant.tzinfo is None:
            raise ValueError("FixedClock requires aware datetime")
        self._i = instant
    def now(self) -> datetime: return self._i

SYSTEM_CLOCK = SystemClock()

def now_kst(clock: Clock = SYSTEM_CLOCK) -> datetime:
    return clock.now().astimezone(TAI_TIMEZONE)         # aware, tz=Asia/Seoul

def business_today(clock: Clock = SYSTEM_CLOCK) -> date:
    return now_kst(clock).date()

def to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("to_kst requires aware datetime (no naive guessing)")
    return value.astimezone(TAI_TIMEZONE)

def parse_external_datetime(value: str, source_timezone: str | None = None) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        if not source_timezone:
            raise ValueError("naive external datetime requires explicit source_timezone")
        dt = dt.replace(tzinfo=ZoneInfo(source_timezone))
    return dt.astimezone(TAI_TIMEZONE)

def parse_business_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("business datetime must be timezone-aware (+09:00)")
    return dt.astimezone(TAI_TIMEZONE)

def serialize_business_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("serialize requires aware datetime")
    return value.astimezone(TAI_TIMEZONE).isoformat()   # +09:00

def to_external_utc(value: datetime) -> datetime:
    """Boundary helper: aware instant → UTC-aware datetime. Production code must not use timezone.utc."""
    if value.tzinfo is None:
        raise ValueError("to_external_utc requires aware datetime")
    return value.astimezone(timezone.utc)

def serialize_external_utc(value: datetime) -> str:
    """UTC ISO-8601 with +00:00 (Python isoformat). Instant-preserving external serialization."""
    return to_external_utc(value).isoformat()
