"""WO025-F09-G3-I17 ART438 R2-B: T09 — leg_diagnosis_svc ART438_EVENT_UNCONFIRMED 안내문 분기 검증.

LEG engine이 reason_code="ART438_EVENT_UNCONFIRMED"를 반환할 때
leg_diagnosis_svc.py의 unconfirmed 변환이 올바른 reason 메시지를 부착하는지 검증.

T09-A: ART438_EVENT_UNCONFIRMED → 제438조 전용 안내문 반환
T09-B: MISSING_NUMERIC_INPUT → 기존 안내문 불변 (회귀)
T09-C: reason_code 없음(None) → MISSING_NUMERIC_INPUT 기본값 + 기존 안내문
T09-D: 두 reason_code 혼재 시 각각 올바른 메시지 분리
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clients import leg_runtime_client as leg_client
from services.leg_diagnosis_svc import run_leg_diagnosis

_ATOM_OUTREG = "7b22c5d4-657f-55cd-ae10-30b3cb90ad6f"
_ATOM_NUMERIC = "aaaa0000-0000-0000-0000-000000000001"

_MSG_ART438 = "제438조 제1항 각 호에 따른 상황 발생 및 작업중지 여부를 확인하지 못해 적용 여부를 확정할 수 없습니다."
_MSG_NUMERIC = "추가 수치 정보가 필요하여 적용 여부를 확정하지 못했습니다."

_ART438_REVIEW = {
    "atom_id": _ATOM_OUTREG,
    "source_atom_ids": [_ATOM_OUTREG],
    "law_name": "산업안전보건기준에 관한 규칙",
    "law_article": "제438조",
    "applicability": "REVIEW_REQUIRED",
    "reason_code": "ART438_EVENT_UNCONFIRMED",
    "missing_fields": [],
    "condition_desc": "is_managed_hazardous_substance AND (art438-sec1-event-out-of-scope)",
}

_NUMERIC_REVIEW = {
    "atom_id": _ATOM_NUMERIC,
    "source_atom_ids": [_ATOM_NUMERIC],
    "law_name": "산업안전보건기준에 관한 규칙",
    "law_article": "제49조",
    "applicability": "REVIEW_REQUIRED",
    "reason_code": "MISSING_NUMERIC_INPUT",
    "missing_fields": ["work_height_m"],
    "condition_desc": "work_height_m>=2.0",
}


class _Body:
    def __init__(self, sector="CONSTRUCTION", input=None):
        self.sector = sector
        self.input = input or {}


def _fake_eval_factory(*review_items):
    def fake_eval(facility, *, timeout=None, context=None):
        return {
            "status": "OK",
            "obligations": [],
            "obligation_count": 0,
            "trace_id": "wo025-i17-t09",
            "provenance": {"release_version": "t09"},
            "contract": {"valid": True},
            "review_required": list(review_items),
            "review_required_count": len(review_items),
        }
    return fake_eval


# ── T09-A: ART438_EVENT_UNCONFIRMED → 제438조 안내문 ─────────────────────────

def test_t09a_art438_event_unconfirmed_reason_message(monkeypatch):
    """T09-A: reason_code=ART438_EVENT_UNCONFIRMED → 제438조 전용 안내문."""
    monkeypatch.setattr(leg_client, "evaluate_rtm", _fake_eval_factory(_ART438_REVIEW))
    full = run_leg_diagnosis(_Body())

    assert full["unconfirmed_count"] == 1
    u = full["unconfirmed"][0]
    assert u["atom_id"] == _ATOM_OUTREG
    assert u["reason_code"] == "ART438_EVENT_UNCONFIRMED"
    assert u["reason"] == _MSG_ART438, (
        f"T09-A: ART438_EVENT_UNCONFIRMED reason 불일치: {u['reason']!r}"
    )
    # missing_fields=[] 보존
    assert u["missing_fields"] == []


# ── T09-B: MISSING_NUMERIC_INPUT → 기존 안내문 불변 ─────────────────────────

def test_t09b_missing_numeric_reason_unchanged(monkeypatch):
    """T09-B: reason_code=MISSING_NUMERIC_INPUT → 기존 안내문 불변 (회귀)."""
    monkeypatch.setattr(leg_client, "evaluate_rtm", _fake_eval_factory(_NUMERIC_REVIEW))
    full = run_leg_diagnosis(_Body())

    assert full["unconfirmed_count"] == 1
    u = full["unconfirmed"][0]
    assert u["reason_code"] == "MISSING_NUMERIC_INPUT"
    assert u["reason"] == _MSG_NUMERIC, (
        f"T09-B: MISSING_NUMERIC_INPUT reason 변경됨: {u['reason']!r}"
    )
    assert u["missing_fields"] == ["work_height_m"]


# ── T09-C: reason_code=None → MISSING_NUMERIC_INPUT 기본값 ──────────────────

def test_t09c_none_reason_code_defaults_to_missing_numeric(monkeypatch):
    """T09-C: reason_code=None → 기본값 MISSING_NUMERIC_INPUT + 기존 안내문."""
    no_code_review = {**_NUMERIC_REVIEW, "reason_code": None}
    monkeypatch.setattr(leg_client, "evaluate_rtm", _fake_eval_factory(no_code_review))
    full = run_leg_diagnosis(_Body())

    u = full["unconfirmed"][0]
    assert u["reason_code"] == "MISSING_NUMERIC_INPUT"
    assert u["reason"] == _MSG_NUMERIC


# ── T09-D: 두 reason_code 혼재 → 각각 올바른 메시지 ────────────────────────

def test_t09d_mixed_reason_codes(monkeypatch):
    """T09-D: ART438_EVENT_UNCONFIRMED + MISSING_NUMERIC_INPUT 혼재 → 각 메시지 정확."""
    monkeypatch.setattr(
        leg_client, "evaluate_rtm",
        _fake_eval_factory(_ART438_REVIEW, _NUMERIC_REVIEW)
    )
    full = run_leg_diagnosis(_Body())

    assert full["unconfirmed_count"] == 2
    by_code = {u["reason_code"]: u for u in full["unconfirmed"]}
    assert by_code["ART438_EVENT_UNCONFIRMED"]["reason"] == _MSG_ART438
    assert by_code["MISSING_NUMERIC_INPUT"]["reason"] == _MSG_NUMERIC
    # raw review_required 불변
    assert full["review_required_count"] == 2
