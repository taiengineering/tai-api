"""WO-LFR-OBJ-S02-L1-ART68-INITIAL-FACT-IMPLEMENT-001 PATCH-C
Pydantic strict int >= 0 contract for same_site_contracted_construction_work_count.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.legal_engine import SafeConstructionConsumerInput


_COUNT = "same_site_contracted_construction_work_count"


def _make(**kwargs):
    return SafeConstructionConsumerInput(**kwargs)


# ── Accept cases ─────────────────────────────────────────────────────────────

def test_count_0_accepted():
    m = _make(**{_COUNT: 0})
    assert getattr(m, _COUNT) == 0


def test_count_2_accepted():
    m = _make(**{_COUNT: 2})
    assert getattr(m, _COUNT) == 2


def test_count_none_accepted():
    """None = UNKNOWN (not provided); distinct from 0."""
    m = _make(**{_COUNT: None})
    assert getattr(m, _COUNT) is None


# ── Reject cases ──────────────────────────────────────────────────────────────

def test_count_string_rejected():
    """'2' (str) → ValidationError."""
    with pytest.raises(ValidationError):
        _make(**{_COUNT: "2"})


def test_count_float_rejected():
    """2.0 (float) → ValidationError."""
    with pytest.raises(ValidationError):
        _make(**{_COUNT: 2.0})


def test_count_float_frac_rejected():
    """2.9 (float) → ValidationError (truncation forbidden)."""
    with pytest.raises(ValidationError):
        _make(**{_COUNT: 2.9})


def test_count_bool_rejected():
    """True (bool) → ValidationError."""
    with pytest.raises(ValidationError):
        _make(**{_COUNT: True})


def test_count_negative_rejected():
    """-1 (int, negative) → ValidationError."""
    with pytest.raises(ValidationError):
        _make(**{_COUNT: -1})


# ── Co-existence: other 4-fact booleans unaffected ───────────────────────────

def test_four_fact_coexistence():
    """4-fact 전체 동시 입력 — strict count + boolean 3개 모두 수락."""
    m = _make(**{
        "contracts_construction_work_at_site": True,
        "leads_and_manages_construction_execution": False,
        "recontracts_received_construction_work": False,
        _COUNT: 2,
    })
    assert m.contracts_construction_work_at_site is True
    assert m.leads_and_manages_construction_execution is False
    assert m.recontracts_received_construction_work is False
    assert getattr(m, _COUNT) == 2
