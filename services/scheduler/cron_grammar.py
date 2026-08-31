"""5-field cron grammar: weekday names only. Numeric DOW is a hard fail."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from services.time import TAI_TIMEZONE

DOW_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
_DOW_TOKEN = re.compile(r"^[a-zA-Z*]+$")
_NUMERIC_TOKEN = re.compile(r"^\d+$")


class CronGrammarError(ValueError):
    pass


def split_cron(expr: str) -> tuple[str, str, str, str, str]:
    parts = (expr or "").strip().split()
    if len(parts) != 5:
        raise CronGrammarError(f"cron must be 5 fields, got {len(parts)}: {expr!r}")
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def _dow_tokens(dow: str) -> list[str]:
    return [t for t in re.split(r"[,-/]", dow) if t]


def assert_named_weekday(expr: str) -> None:
    _min, _hour, _day, _month, dow = split_cron(expr)
    if dow == "*":
        return
    for tok in _dow_tokens(dow.lower()):
        if tok == "*":
            continue
        if _NUMERIC_TOKEN.match(tok):
            raise CronGrammarError(f"numeric weekday forbidden: {expr!r}")
        if tok not in DOW_NAMES:
            raise CronGrammarError(f"weekday must be sun..sat, got {tok!r} in {expr!r}")


def normalize_numeric_dow(expr: str) -> str:
    """Map a single trailing 0-6 dow digit to sun..sat. Other fields unchanged."""
    minute, hour, day, month, dow = split_cron(expr)
    mapping = {"0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri", "6": "sat", "7": "sun"}
    if dow in mapping:
        return f"{minute} {hour} {day} {month} {mapping[dow]}"
    return expr


def trigger_for(expr: str, tz: ZoneInfo | None = None) -> CronTrigger:
    assert_named_weekday(expr)
    return CronTrigger.from_crontab(expr, timezone=tz or TAI_TIMEZONE)


def next_fire_after(expr: str, instant: datetime, tz: ZoneInfo | None = None) -> datetime:
    """Next matching fire strictly after `instant` (KST timezone on the trigger)."""
    if instant.tzinfo is None:
        raise ValueError("next_fire_after requires aware datetime")
    trig = trigger_for(expr, tz)
    nxt = trig.get_next_fire_time(instant, instant + timedelta(microseconds=1))
    if nxt is None:
        raise CronGrammarError(f"no next fire for {expr!r} after {instant.isoformat()}")
    return nxt


def next_fire_at_or_after(expr: str, instant: datetime, tz: ZoneInfo | None = None) -> datetime:
    if instant.tzinfo is None:
        raise ValueError("next_fire_at_or_after requires aware datetime")
    trig = trigger_for(expr, tz)
    nxt = trig.get_next_fire_time(None, instant)
    if nxt is None:
        raise CronGrammarError(f"no next fire for {expr!r} at {instant.isoformat()}")
    return nxt
