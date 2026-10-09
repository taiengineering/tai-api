"""tests/test_leg_run_diagnosis_pending.py
WO-LFR-DUAL-CONSUMER-FINAL-GATE-003

Unit tests for diagnosis_pending in /diagnosis/run-leg response.

DP-LEG-1  paid + review_required non-empty → diagnosis_pending=True
DP-LEG-2  paid + review_required=[]        → diagnosis_pending=False
DP-LEG-3  paid + review_required absent    → diagnosis_pending=False
DP-LEG-4  free                             → diagnosis_pending absent
DP-LEG-5  paid + review_required non-list  → diagnosis_pending=False (safe)
"""
from __future__ import annotations

import asyncio
import pytest


_ABSENT = object()


def _make_run_diagnosis_result(*, is_free: bool, review_required=_ABSENT):
    _rr_default = _ABSENT

    def _fake(*args, **kwargs):
        full: dict = {"leg_status": "OK", "applicable_count": 3}
        if review_required is not _rr_default:
            full["review_required"] = review_required
        return {
            "public_token": "pt-x",
            "diagnosis_id": "d-x",
            "tier_code": "T1",
            "is_free": is_free,
            "expires_at": None,
            "free_remaining_after": None,
            "result": full,
        }
    return _fake


@pytest.fixture()
def leg_env(monkeypatch):
    import routers.diagnosis_integrated_leg as dl
    monkeypatch.setattr(dl, "LEG_PIPELINE_ENABLED", True)
    monkeypatch.setattr(dl, "is_enabled", lambda: True)
    monkeypatch.setattr(dl, "get_supabase", lambda: object())
    return dl


def _body():
    from types import SimpleNamespace
    return SimpleNamespace(form_data={"sector": "IND"})


# ── DP-LEG-1: paid + review_required non-empty → diagnosis_pending=True ──────

def test_dp_leg_1_paid_nonempty_rr_pending_true(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(
        dl.diagnosis_integrated_svc, "run_diagnosis",
        _make_run_diagnosis_result(is_free=False,
                                   review_required=[{"atom_id": "A1", "reason": "UNKNOWN"}]),
    )
    resp = asyncio.run(dl._run_leg_impl(_body(), current_user=None))
    assert resp["diagnosis_pending"] is True


# ── DP-LEG-2: paid + review_required=[] → diagnosis_pending=False ────────────

def test_dp_leg_2_paid_empty_rr_pending_false(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(
        dl.diagnosis_integrated_svc, "run_diagnosis",
        _make_run_diagnosis_result(is_free=False, review_required=[]),
    )
    resp = asyncio.run(dl._run_leg_impl(_body(), current_user=None))
    assert resp["diagnosis_pending"] is False


# ── DP-LEG-3: paid + review_required absent → diagnosis_pending=False ────────

def test_dp_leg_3_paid_rr_absent_pending_false(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(
        dl.diagnosis_integrated_svc, "run_diagnosis",
        _make_run_diagnosis_result(is_free=False),
    )
    resp = asyncio.run(dl._run_leg_impl(_body(), current_user=None))
    assert resp["diagnosis_pending"] is False


# ── DP-LEG-4: free → diagnosis_pending absent ────────────────────────────────

def test_dp_leg_4_free_no_pending_key(leg_env, monkeypatch):
    """Free response must NOT contain diagnosis_pending (free contract unchanged)."""
    dl = leg_env
    monkeypatch.setattr(
        dl.diagnosis_integrated_svc, "run_diagnosis",
        _make_run_diagnosis_result(
            is_free=True,
            review_required=[{"atom_id": "A1", "reason": "UNKNOWN"}],
        ),
    )
    resp = asyncio.run(dl._run_leg_impl(_body(), current_user=None))
    assert "diagnosis_pending" not in resp, "free response must not include diagnosis_pending"


# ── DP-LEG-5: paid + review_required=None (non-list) → diagnosis_pending=False

def test_dp_leg_5_paid_rr_none_pending_false(leg_env, monkeypatch):
    dl = leg_env
    monkeypatch.setattr(
        dl.diagnosis_integrated_svc, "run_diagnosis",
        _make_run_diagnosis_result(is_free=False, review_required=None),
    )
    resp = asyncio.run(dl._run_leg_impl(_body(), current_user=None))
    assert resp["diagnosis_pending"] is False
