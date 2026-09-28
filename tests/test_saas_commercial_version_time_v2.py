"""TAI Safe Commercial Version Temporal Semantics V2 — T01-T15 + CF/CO/RN tests.

검증 범위:
  T01-T07   is_commercial_version_effective_at_v2 boundary / open-ended
  T08-T10   select_effective_commercial_version_v2 selector
  T11-T13   Naive datetime fail-closed
  T14-T15   contract_end_date_to_effective_at_v2 KST boundary
  CF-T1-T4  Commercial Fit temporal migration
  CO-T1-T2  Change Order temporal migration
  RN-T1-T5  Renewal Adapter temporal migration (prepare side)

DB/네트워크 없음 — 순수 unit tests.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.saas_commercial_version_time_v2 import (  # noqa: E402
    TemporalVersionError,
    contract_end_date_to_effective_at_v2,
    find_future_commercial_versions_v2,
    is_commercial_version_effective_at_v2,
    select_effective_commercial_version_v2,
)

# ── Shared time anchors ───────────────────────────────────────────────────────

_JAN = datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)   # boundary
_MAR = datetime(2027, 3, 31, 23, 59, 59, tzinfo=timezone.utc)  # before boundary
_APR = datetime(2027, 4, 1, 0, 0, 0, tzinfo=timezone.utc)   # new effective (== boundary)


# ── CV factories ──────────────────────────────────────────────────────────────

def _cv(effective_from, superseded_at=None):
    """Minimal dict-style CV row."""
    return {"effective_from": effective_from, "superseded_at": superseded_at}


def _cv_str(eff_str, sup_str=None):
    """CV with ISO string fields (as returned from DB)."""
    return {"effective_from": eff_str, "superseded_at": sup_str}


@dataclass
class _ModelCV:
    """Pydantic-model-like CV (uses attribute access)."""
    effective_from: datetime
    superseded_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# T01-T07: is_commercial_version_effective_at_v2
# ─────────────────────────────────────────────────────────────────────────────

def test_T01_before_effective_returns_false():
    """as_of < effective_from → False."""
    cv = _cv(effective_from=_APR)
    as_of = _MAR
    assert is_commercial_version_effective_at_v2(cv, as_of) is False


def test_T02_exactly_at_effective_returns_true():
    """as_of == effective_from → True (start of interval)."""
    cv = _cv(effective_from=_APR)
    assert is_commercial_version_effective_at_v2(cv, _APR) is True


def test_T03_after_effective_before_superseded_returns_true():
    """effective_from < as_of < superseded_at → True."""
    sup = _APR + timedelta(days=90)
    cv = _cv(effective_from=_APR, superseded_at=sup)
    as_of = _APR + timedelta(days=30)
    assert is_commercial_version_effective_at_v2(cv, as_of) is True


def test_T04_exactly_at_superseded_returns_false():
    """as_of == superseded_at → False (end of half-open interval)."""
    sup = _APR + timedelta(days=90)
    cv = _cv(effective_from=_APR, superseded_at=sup)
    assert is_commercial_version_effective_at_v2(cv, sup) is False


def test_T05_after_superseded_returns_false():
    """as_of > superseded_at → False."""
    sup = _APR
    cv = _cv(effective_from=_JAN, superseded_at=sup)
    as_of = _APR + timedelta(seconds=1)
    assert is_commercial_version_effective_at_v2(cv, as_of) is False


def test_T06_open_ended_current_returns_true():
    """superseded_at=None (open-ended) → True when as_of >= effective_from."""
    cv = _cv(effective_from=_JAN, superseded_at=None)
    as_of = _APR
    assert is_commercial_version_effective_at_v2(cv, as_of) is True


def test_T07_future_open_ended_before_effective_returns_false():
    """effective_from in the future, superseded_at=None, as_of < effective_from → False."""
    future = _APR + timedelta(days=365)
    cv = _cv(effective_from=future, superseded_at=None)
    as_of = _APR
    assert is_commercial_version_effective_at_v2(cv, as_of) is False


# ─────────────────────────────────────────────────────────────────────────────
# T08-T10: select_effective_commercial_version_v2
# ─────────────────────────────────────────────────────────────────────────────

def test_T08_selector_exactly_one_returns_it():
    """effective CV 1개 → 반환."""
    cv = _cv(effective_from=_JAN)
    result = select_effective_commercial_version_v2([cv], _APR)
    assert result is cv


def test_T09_selector_zero_raises_not_found():
    """effective CV 0개 → TEMPORAL_CURRENT_NOT_FOUND."""
    future_cv = _cv(effective_from=_APR + timedelta(days=30))
    with pytest.raises(TemporalVersionError) as exc:
        select_effective_commercial_version_v2([future_cv], _APR)
    assert exc.value.code == "TEMPORAL_CURRENT_NOT_FOUND"


def test_T10_selector_two_effective_raises_ambiguous():
    """effective CV 2개 이상 → TEMPORAL_CURRENT_AMBIGUOUS."""
    cv1 = _cv(effective_from=_JAN)           # open-ended
    cv2 = _cv(effective_from=_JAN + timedelta(days=10))  # also open-ended
    with pytest.raises(TemporalVersionError) as exc:
        select_effective_commercial_version_v2([cv1, cv2], _APR)
    assert exc.value.code == "TEMPORAL_CURRENT_AMBIGUOUS"


# ─────────────────────────────────────────────────────────────────────────────
# T11-T13: Naive datetime fail-closed
# ─────────────────────────────────────────────────────────────────────────────

def test_T11_naive_as_of_raises():
    """as_of naive → TEMPORAL_NAIVE_DATETIME."""
    cv = _cv(effective_from=_JAN)
    naive = datetime(2027, 4, 1, 0, 0, 0)
    with pytest.raises(TemporalVersionError) as exc:
        is_commercial_version_effective_at_v2(cv, naive)
    assert exc.value.code == "TEMPORAL_NAIVE_DATETIME"


def test_T12_naive_effective_from_raises():
    """effective_from naive → TEMPORAL_NAIVE_DATETIME."""
    cv_naive = {"effective_from": datetime(2027, 1, 1, 0, 0, 0), "superseded_at": None}
    with pytest.raises(TemporalVersionError) as exc:
        is_commercial_version_effective_at_v2(cv_naive, _APR)
    assert exc.value.code == "TEMPORAL_NAIVE_DATETIME"


def test_T13_naive_superseded_at_raises():
    """superseded_at naive → TEMPORAL_NAIVE_DATETIME."""
    cv_naive = {"effective_from": _JAN, "superseded_at": datetime(2027, 4, 1, 0, 0, 0)}
    with pytest.raises(TemporalVersionError) as exc:
        is_commercial_version_effective_at_v2(cv_naive, _MAR)
    assert exc.value.code == "TEMPORAL_NAIVE_DATETIME"


# ─────────────────────────────────────────────────────────────────────────────
# T14-T15: contract_end_date_to_effective_at_v2 KST boundary
# ─────────────────────────────────────────────────────────────────────────────

def test_T14_kst_end_date_conversion_exact():
    """2027-01-01 DATE → 2027-01-01T00:00:00+09:00 (KST)."""
    import zoneinfo
    result = contract_end_date_to_effective_at_v2(date(2027, 1, 1))
    assert result.year == 2027
    assert result.month == 1
    assert result.day == 1
    assert result.hour == 0
    assert result.minute == 0
    assert result.second == 0
    # UTC offset = +09:00
    seoul_tz = zoneinfo.ZoneInfo("Asia/Seoul")
    assert result.tzinfo is not None
    assert result.utcoffset().total_seconds() == 9 * 3600


def test_T15_utc_kst_same_instant():
    """KST 2027-01-01 00:00 == UTC 2026-12-31 15:00."""
    import zoneinfo
    kst_dt = contract_end_date_to_effective_at_v2(date(2027, 1, 1))
    utc_dt = kst_dt.astimezone(timezone.utc)
    assert utc_dt.year == 2026
    assert utc_dt.month == 12
    assert utc_dt.day == 31
    assert utc_dt.hour == 15
    assert utc_dt.minute == 0


# ─────────────────────────────────────────────────────────────────────────────
# CF-T1 to CF-T4: Commercial Fit temporal migration
# ─────────────────────────────────────────────────────────────────────────────
# Owner Policy: [effective_from, superseded_at)
# CF-T1: future superseded old CV before boundary → still effective (PASS)
# CF-T2: old CV exactly at boundary → NOT effective
# CF-T3: new CV effective_from > as_of → NOT effective (before new kicks in)
# CF-T4: new CV effective_from == as_of → effective

def test_CF_T1_future_superseded_cv_before_boundary_is_effective():
    """superseded_at = boundary, as_of < boundary → old CV still effective."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    as_of = _MAR  # before boundary
    assert is_commercial_version_effective_at_v2(old_cv, as_of) is True


def test_CF_T2_old_cv_exactly_at_boundary_not_effective():
    """as_of == superseded_at (boundary) → old CV NOT effective."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    assert is_commercial_version_effective_at_v2(old_cv, boundary) is False


def test_CF_T3_new_cv_before_effective_from_not_effective():
    """new CV effective_from = boundary, as_of < boundary → NOT effective."""
    boundary = _APR
    new_cv = _cv(effective_from=boundary, superseded_at=None)
    as_of = _MAR  # before boundary
    assert is_commercial_version_effective_at_v2(new_cv, as_of) is False


def test_CF_T4_new_cv_exactly_at_effective_from_is_effective():
    """new CV effective_from = boundary, as_of == boundary → effective."""
    boundary = _APR
    new_cv = _cv(effective_from=boundary, superseded_at=None)
    assert is_commercial_version_effective_at_v2(new_cv, boundary) is True


def test_CF_T5_no_overlap_at_boundary():
    """경계 시점에서 old/new 동시 effective = 절대 없음."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    new_cv = _cv(effective_from=boundary, superseded_at=None)
    effective_at_boundary = [
        cv for cv in [old_cv, new_cv]
        if is_commercial_version_effective_at_v2(cv, boundary)
    ]
    assert len(effective_at_boundary) == 1
    assert effective_at_boundary[0] is new_cv


# ─────────────────────────────────────────────────────────────────────────────
# CO-T1 to CO-T2: Change Order temporal migration
# ─────────────────────────────────────────────────────────────────────────────

def test_CO_T1_future_superseded_cv_requested_before_boundary_usable():
    """old CV: superseded_at = future, requested_effective_at < superseded_at → usable."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    requested = _MAR  # before boundary
    assert is_commercial_version_effective_at_v2(old_cv, requested) is True


def test_CO_T2_requested_exactly_boundary_old_cv_not_effective():
    """old CV: superseded_at = boundary, requested == boundary → NOT effective."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    assert is_commercial_version_effective_at_v2(old_cv, boundary) is False


# ─────────────────────────────────────────────────────────────────────────────
# RN-T1 to RN-T5: Renewal Adapter temporal (pure selector tests)
# ─────────────────────────────────────────────────────────────────────────────

def test_RN_T1_temporal_old_selected_before_boundary():
    """as_of < boundary → old CV (superseded_at=boundary) selected."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    as_of = _MAR
    result = select_effective_commercial_version_v2([old_cv], as_of)
    assert result is old_cv


def test_RN_T2_future_cv_not_selected_before_boundary():
    """as_of < future_cv.effective_from → future CV not selected → NOT_FOUND."""
    boundary = _APR
    future_cv = _cv(effective_from=boundary, superseded_at=None)
    as_of = _MAR
    with pytest.raises(TemporalVersionError) as exc:
        select_effective_commercial_version_v2([future_cv], as_of)
    assert exc.value.code == "TEMPORAL_CURRENT_NOT_FOUND"


def test_RN_T3_future_version_detected():
    """find_future_commercial_versions_v2 finds future-scheduled CVs."""
    boundary = _APR
    old_cv = _cv(effective_from=_JAN, superseded_at=boundary)
    future_cv = _cv(effective_from=boundary, superseded_at=None)
    as_of = _MAR

    future_found = find_future_commercial_versions_v2([old_cv, future_cv], as_of)
    assert len(future_found) == 1
    assert future_found[0] is future_cv


def test_RN_T4_ambiguous_temporal_rows_raises():
    """두 CV 모두 as_of에 effective → TEMPORAL_CURRENT_AMBIGUOUS (fail-closed)."""
    cv1 = _cv(effective_from=_JAN, superseded_at=None)
    cv2 = _cv(effective_from=_JAN + timedelta(hours=1), superseded_at=None)
    with pytest.raises(TemporalVersionError) as exc:
        select_effective_commercial_version_v2([cv1, cv2], _APR)
    assert exc.value.code == "TEMPORAL_CURRENT_AMBIGUOUS"


def test_RN_T5_naive_as_of_raises_on_find_future():
    """find_future_commercial_versions_v2: naive as_of → TEMPORAL_NAIVE_DATETIME."""
    naive_as_of = datetime(2027, 3, 31, 0, 0, 0)
    with pytest.raises(TemporalVersionError) as exc:
        find_future_commercial_versions_v2([], naive_as_of)
    assert exc.value.code == "TEMPORAL_NAIVE_DATETIME"


# ─────────────────────────────────────────────────────────────────────────────
# Model CV compatibility (attribute access)
# ─────────────────────────────────────────────────────────────────────────────

def test_model_cv_attribute_access():
    """Pydantic-model-like object (attribute access) works correctly."""
    model_cv = _ModelCV(effective_from=_JAN, superseded_at=None)
    assert is_commercial_version_effective_at_v2(model_cv, _APR) is True


def test_string_fields_parsed_correctly():
    """ISO string fields from DB are parsed correctly."""
    cv = _cv_str(
        eff_str="2027-01-01T00:00:00+00:00",
        sup_str=None,
    )
    as_of = datetime(2027, 4, 1, tzinfo=timezone.utc)
    assert is_commercial_version_effective_at_v2(cv, as_of) is True
