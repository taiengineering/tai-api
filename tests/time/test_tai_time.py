"""TAI time contract unit tests. FixedClock only — OS clock is not a fixture."""
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest

from services.time.api_primitives import serialize_api_datetime, validate_business_datetime
from services.time.legacy_naive_utc_adapter import (
    aware_to_legacy_naive_utc,
    legacy_naive_utc_to_aware,
)
from services.time.tai_time import (
    TAI_TIMEZONE,
    FixedClock,
    business_today,
    now_kst,
    parse_business_datetime,
    parse_external_datetime,
    serialize_business_datetime,
    to_kst,
    to_external_utc,
    serialize_external_utc,
)

KST = ZoneInfo("Asia/Seoul")


def _clk(y, m, d, hh, mm, ss=0):
    return FixedClock(datetime(y, m, d, hh, mm, ss, tzinfo=KST))


def test_now_kst_aware_asia_seoul():
    dt = now_kst(_clk(2026, 8, 31, 23, 59))
    assert dt.tzinfo is not None
    assert dt.tzinfo == TAI_TIMEZONE
    assert dt.year == 2026 and dt.month == 8 and dt.day == 31
    assert dt.hour == 23 and dt.minute == 59


def test_business_today_kst_midnight_boundary():
    assert business_today(_clk(2026, 8, 31, 23, 59)) == date(2026, 8, 31)
    assert business_today(_clk(2026, 9, 1, 0, 0)) == date(2026, 9, 1)
    assert business_today(_clk(2026, 9, 1, 0, 1)) == date(2026, 9, 1)


def test_business_today_sunday_to_monday():
    # 2026-08-30 = Sunday, 2026-08-31 = Monday
    assert datetime(2026, 8, 30).weekday() == 6
    assert datetime(2026, 8, 31).weekday() == 0
    assert business_today(_clk(2026, 8, 30, 23, 59)) == date(2026, 8, 30)
    assert business_today(_clk(2026, 8, 31, 0, 0)) == date(2026, 8, 31)


def test_business_today_month_end():
    assert business_today(_clk(2026, 8, 31, 23, 59)) == date(2026, 8, 31)
    assert business_today(_clk(2026, 9, 1, 0, 0)) == date(2026, 9, 1)


def test_business_today_year_end():
    assert business_today(_clk(2026, 12, 31, 23, 59)) == date(2026, 12, 31)
    assert business_today(_clk(2027, 1, 1, 0, 0)) == date(2027, 1, 1)


def test_to_kst_aware_utc_same_instant_plus09():
    utc = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
    k = to_kst(utc)
    assert k.tzinfo == TAI_TIMEZONE
    assert k == datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    assert k.utcoffset().total_seconds() == 9 * 3600
    assert k.isoformat().endswith("+09:00")


def test_to_kst_naive_raises():
    with pytest.raises(ValueError, match="aware"):
        to_kst(datetime(2026, 8, 31, 12, 0))


def test_fixed_clock_rejects_naive():
    with pytest.raises(ValueError, match="aware"):
        FixedClock(datetime(2026, 8, 31, 12, 0))


def test_serialize_plus09():
    utc = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
    s = serialize_business_datetime(utc)
    assert "+09:00" in s
    assert s.startswith("2026-09-01T00:00:00")
    assert serialize_api_datetime(utc) == s


def test_serialize_naive_raises():
    with pytest.raises(ValueError):
        serialize_business_datetime(datetime(2026, 8, 31, 12, 0))


def test_parse_business_naive_reject():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_business_datetime("2026-08-31T12:00:00")
    with pytest.raises(ValueError):
        validate_business_datetime("2026-08-31T12:00:00")


def test_date_only_not_a_datetime():
    with pytest.raises(ValueError):
        parse_business_datetime("2026-08-31")
    assert date.fromisoformat("2026-08-31") == date(2026, 8, 31)


def test_parse_business_plus09():
    dt = parse_business_datetime("2026-09-01T00:00:00+09:00")
    assert dt.tzinfo == TAI_TIMEZONE
    assert dt == datetime(2026, 9, 1, 0, 0, tzinfo=KST)


def test_external_naive_requires_source_timezone():
    with pytest.raises(ValueError, match="source_timezone"):
        parse_external_datetime("2026-08-31T15:00:00")


def test_external_naive_with_source_timezone_exact_instant():
    dt = parse_external_datetime("2026-08-31T15:00:00", source_timezone="UTC")
    assert dt == datetime(2026, 9, 1, 0, 0, tzinfo=KST)


def test_legacy_roundtrip():
    aware = datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    naive = aware_to_legacy_naive_utc(aware)
    assert naive.tzinfo is None
    assert naive == datetime(2026, 8, 31, 15, 0)
    back = legacy_naive_utc_to_aware(naive)
    assert back == aware.astimezone(timezone.utc)
    assert to_kst(back) == aware


def test_to_external_utc_same_instant():
    kst = datetime(2026, 9, 1, 0, 0, tzinfo=KST)
    utc = to_external_utc(kst)
    assert utc == datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
    s = serialize_external_utc(kst)
    assert s.startswith("2026-08-31T15:00:00")
    assert s.endswith("+00:00")


def test_otp_expiry_absolute_comparison_not_string_replace():
    """auth/OTP expiry must compare instants, not KST/UTC digit strings."""
    issued = now_kst(_clk(2026, 9, 1, 0, 0))
    expires = issued + timedelta(minutes=10)
    assert now_kst(_clk(2026, 9, 1, 0, 9, 59)) <= expires
    assert not (now_kst(_clk(2026, 9, 1, 0, 10, 1)) <= expires)
    stored = serialize_external_utc(expires)
    parsed = parse_external_datetime(stored)
    assert now_kst(_clk(2026, 9, 1, 0, 9)) <= parsed
    assert parsed == expires
    # stored UTC iso is not a naive digit-string substitute of KST wall
    assert not stored.startswith("2026-09-01T00:10")
    assert stored.startswith("2026-08-31T15:10")
