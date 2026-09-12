"""WO-SM-CORE22-CONSTRUCTION-PREDICATE-SERVER-FAIL-CLOSED-001

CONSTRUCTION Runtime must not start without explicit bool facts.
missing != false. False is answered. Raw facts do not satisfy the gate.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from schemas.diagnosis_integrated import DiagnosisRunBody
from services import diagnosis_integrated_svc as svc
from services.canonical.explicit_construction_predicates import (
    ERROR_CODE,
    collect_explicit_construction_predicates,
    missing_explicit_construction_predicates,
    stored_explicit_predicate_body,
    validate_explicit_construction_predicates,
)

CODE = ERROR_CODE


class _R:
    def __init__(self, data):
        self.data = data


class _RecTable:
    def __init__(self, name, store):
        self._n = name
        self._store = store
        self._pending = None

    def select(self, *a, **k):
        self._store["reads"].append(self._n)
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def insert(self, row):
        self._store["inserts"].setdefault(self._n, []).append(row)
        self._pending = row
        return self

    def update(self, row):
        self._store["updates"].setdefault(self._n, []).append(row)
        return self

    def execute(self):
        if self._n == "diagnosis_auth_log":
            if self._pending is None and not self._store["updates"].get(self._n):
                return _R(
                    [
                        {
                            "id": "a1",
                            "ci_hash": "ci",
                            "name": "n",
                            "phone": "p",
                            "free_count": 0,
                            "free_limit": 3,
                            "status": "ACTIVE",
                            "linked_user_id": None,
                        }
                    ]
                )
            return _R([{"id": "a1"}])
        if self._n == "diagnosis_disclaimer_log":
            if self._pending is not None:
                return _R([{**self._pending, "id": "disc-auto"}])
            return _R([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._n == "anonymous_diagnosis_results":
            if self._pending is not None:
                return _R([{**self._pending, "id": "r1"}])
            existing = self._store.get("existing_result")
            return _R([existing] if existing else [])
        if self._n == "diagnosis_purchases":
            return _R([{"id": "p1"}])
        return _R([])


class _SB:
    def __init__(self, existing_result=None):
        self.store = {"inserts": {}, "updates": {}, "reads": [], "existing_result": existing_result}

    def table(self, n):
        return _RecTable(n, self.store)


def _run_kw(**over):
    kw = dict(
        auto_tier_func=lambda *a, **k: "CONSTRUCTION_FREE",
        build_partial_func=lambda f: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={"CONSTRUCTION_X": 100, "PAID2": 149000, "PAID3": 249000},
        free_tier_codes={"CONSTRUCTION_FREE", "INDUSTRY_FREE", "BUILDING_FREE"},
        engine_version="t",
        current_user=None,
    )
    kw.update(over)
    return kw


def _assert_422(exc, missing):
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["code"] == CODE
    assert detail["missing_fields"] == missing


def test_T1_construction_missing_is_construction():
    body = DiagnosisRunBody(sector="CONSTRUCTION")
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == ["is_construction"]
    with pytest.raises(HTTPException) as ei:
        validate_explicit_construction_predicates(body, "CONSTRUCTION")
    _assert_422(ei, ["is_construction"])


def test_T2_true_children_missing():
    body = DiagnosisRunBody(sector="CONSTRUCTION", is_construction=True)
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == [
        "is_relationship_contractor",
        "is_civil_construction",
    ]


def test_T3_true_false_false_pass():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_relationship_contractor=False,
        is_civil_construction=False,
    )
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == []
    validate_explicit_construction_predicates(body, "CONSTRUCTION")


def test_T4_false_children_absent_pass():
    body = DiagnosisRunBody(sector="CONSTRUCTION", is_construction=False)
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == []
    collected = collect_explicit_construction_predicates(body)
    assert collected == {"is_construction": False}
    assert "is_relationship_contractor" not in collected
    assert "is_civil_construction" not in collected


def test_T5_form_data_true_false_false_pass():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        form_data={
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
        },
    )
    assert body.is_construction is None
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == []


def test_T6_form_data_string_not_explicit_bool():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        form_data={"is_construction": "true", "is_relationship_contractor": "false"},
    )
    assert collect_explicit_construction_predicates(body) == {}
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == ["is_construction"]


def test_T7_raw_facts_do_not_satisfy_gate():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        construction_type="토목",
        form_data={
            "construction_type_code": "CIVIL",
            "order_type": "하도급",
            "has_subcontractor": True,
            "subcon_workers": 20,
        },
    )
    assert collect_explicit_construction_predicates(body) == {}
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == ["is_construction"]


def test_T8_building_no_predicates_pass():
    body = DiagnosisRunBody(sector="BUILDING")
    assert missing_explicit_construction_predicates(body, "BUILDING") == []


def test_T9_industrial_no_predicates_pass():
    for sector in ("INDUSTRIAL", "INDUSTRY", "MANUFACTURING"):
        body = DiagnosisRunBody(sector=sector)
        assert missing_explicit_construction_predicates(body, sector) == []


def test_T10_top_level_false_form_data_true_preserved():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_relationship_contractor=False,
        form_data={"is_relationship_contractor": True, "is_construction": True},
    )
    collected = collect_explicit_construction_predicates(body)
    assert collected["is_relationship_contractor"] is False
    assert collected["is_construction"] is True
    # child false is answered; civil still missing because is_construction true
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == [
        "is_civil_construction"
    ]
    body2 = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=False,
        form_data={"is_construction": True},
    )
    assert collect_explicit_construction_predicates(body2)["is_construction"] is False
    assert missing_explicit_construction_predicates(body2, "CONSTRUCTION") == []


def test_one_child_missing_is_deterministic():
    rel_only = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_relationship_contractor=False,
    )
    assert missing_explicit_construction_predicates(rel_only, "CONSTRUCTION") == [
        "is_civil_construction"
    ]
    civil_only = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_civil_construction=False,
    )
    assert missing_explicit_construction_predicates(civil_only, "CONSTRUCTION") == [
        "is_relationship_contractor"
    ]


def test_numeric_and_yes_no_not_accepted():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        form_data={"is_construction": 1, "is_relationship_contractor": "예"},
    )
    assert collect_explicit_construction_predicates(body) == {}
    assert missing_explicit_construction_predicates(body, "CONSTRUCTION") == ["is_construction"]


def _capture_run(body, **over):
    sb = _SB()
    calls = {"step1": 0}
    disc_calls = {"n": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}

    orig = svc._ensure_disclaimer_for_paid_entry

    def _disc(sb_, auth_row):
        disc_calls["n"] += 1
        return orig(sb_, auth_row)

    svc._ensure_disclaimer_for_paid_entry = _disc
    try:
        out = svc.run_diagnosis(sb, body, run_step1_func=r1, **_run_kw(**over))
    finally:
        svc._ensure_disclaimer_for_paid_entry = orig
    return out, sb, calls, disc_calls


def test_run_T1_side_effects_zero_before_disclaimer():
    body = DiagnosisRunBody(sector="CONSTRUCTION", auth_token="t", payment_ref="oid1")
    sb = _SB()
    calls = {"step1": 0}
    disc_calls = {"n": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {}}

    orig = svc._ensure_disclaimer_for_paid_entry

    def _disc(sb_, auth_row):
        disc_calls["n"] += 1
        return orig(sb_, auth_row)

    svc._ensure_disclaimer_for_paid_entry = _disc
    try:
        with pytest.raises(HTTPException) as ei:
            svc.run_diagnosis(sb, body, run_step1_func=r1, **_run_kw())
    finally:
        svc._ensure_disclaimer_for_paid_entry = orig
    _assert_422(ei, ["is_construction"])
    assert calls["step1"] == 0
    assert disc_calls["n"] == 0
    assert sb.store["inserts"].get("anonymous_diagnosis_results", []) == []
    assert sb.store["inserts"].get("diagnosis_disclaimer_log", []) == []
    assert sb.store["inserts"].get("diagnosis_purchases", []) == []
    assert sb.store["updates"].get("diagnosis_auth_log", []) == []
    assert "diagnosis_auth_log" in sb.store["reads"]


def test_run_T2_true_children_missing_422():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        auth_token="t",
        disclaimer_log_id="disc1",
        is_construction=True,
        payment_ref="oid1",
    )
    with pytest.raises(HTTPException) as ei:
        _capture_run(body)
    _assert_422(ei, ["is_relationship_contractor", "is_civil_construction"])


def test_run_T3_true_false_false_reaches_engine():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        auth_token="t",
        disclaimer_log_id="disc1",
        is_construction=True,
        is_relationship_contractor=False,
        is_civil_construction=False,
    )
    _out, sb, calls, disc = _capture_run(body)
    assert calls["step1"] == 1
    assert disc["n"] == 0
    assert sb.store["inserts"].get("anonymous_diagnosis_results")


def test_run_T4_false_without_children_reaches_engine():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        auth_token="t",
        disclaimer_log_id="disc1",
        is_construction=False,
    )
    _out, _sb, calls, _disc = _capture_run(body)
    assert calls["step1"] == 1


def test_run_T7_raw_bypass_422():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        auth_token="t",
        payment_ref="oid1",
        construction_type="토목",
        form_data={
            "construction_type_code": "CIVIL",
            "order_type": "하도급",
            "has_subcontractor": True,
            "subcon_workers": 20,
        },
    )
    with pytest.raises(HTTPException) as ei:
        _capture_run(body)
    _assert_422(ei, ["is_construction"])


def test_run_T8_building_no_predicates_engine():
    body = DiagnosisRunBody(
        sector="BUILDING",
        auth_token="t",
        disclaimer_log_id="disc1",
        worker_count=10,
        appendix3_item_no=1,
    )
    _out, _sb, calls, _disc = _capture_run(
        body, auto_tier_func=lambda *a, **k: "BUILDING_FREE"
    )
    assert calls["step1"] == 1


def test_run_T9_industrial_no_predicates_engine():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        auth_token="t",
        disclaimer_log_id="disc1",
        worker_count=10,
        appendix3_item_no=28,
    )
    _out, _sb, calls, _disc = _capture_run(
        body, auto_tier_func=lambda *a, **k: "INDUSTRY_FREE"
    )
    assert calls["step1"] == 1


def test_auth_401_precedes_predicate_422():
    body = DiagnosisRunBody(sector="CONSTRUCTION")
    with pytest.raises(HTTPException) as ei:
        svc.run_diagnosis(_SB(), body, run_step1_func=lambda *a, **k: {"status": "success", "data": {}}, **_run_kw())
    assert ei.value.status_code == 401


def test_stored_body_uses_input_data_then_form_data():
    stored = {
        "sector": "CONSTRUCTION",
        "is_construction": True,
        "is_relationship_contractor": False,
        "raw_structured_input": {
            "form_data": {
                "is_construction": False,
                "is_relationship_contractor": True,
                "is_civil_construction": False,
            }
        },
    }
    body = stored_explicit_predicate_body(stored)
    collected = collect_explicit_construction_predicates(body)
    assert collected["is_construction"] is True
    assert collected["is_relationship_contractor"] is False
    assert collected["is_civil_construction"] is False


def test_stored_body_form_data_only():
    stored = {
        "sector": "CONSTRUCTION",
        "raw_structured_input": {
            "form_data": {
                "is_construction": True,
                "is_relationship_contractor": False,
                "is_civil_construction": False,
            }
        },
    }
    assert missing_explicit_construction_predicates(
        stored_explicit_predicate_body(stored), "CONSTRUCTION"
    ) == []


def test_upgrade_construction_missing_facts_no_write():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "CONSTRUCTION",
            "raw_structured_input": {
                "form_data": {
                    "construction_type": "토목",
                    "order_type": "하도급",
                    "has_subcontractor": True,
                }
            },
        },
    }
    sb = _SB(existing_result=existing)
    calls = {"step1": 0, "purchase": 0, "bind": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {}}

    orig_p = svc._save_diagnosis_purchase
    orig_b = svc._bind_linked_user_id
    svc._save_diagnosis_purchase = lambda *a, **k: calls.__setitem__("purchase", calls["purchase"] + 1)
    svc._bind_linked_user_id = lambda *a, **k: calls.__setitem__("bind", calls["bind"] + 1)
    up = SimpleNamespace(
        auth_token="t",
        public_token="PT",
        target_tier_code="PAID3",
        payment_ref="PR2",
        invoice_requested=False,
        invoice_biz_no=None,
        invoice_email=None,
    )
    try:
        with pytest.raises(HTTPException) as ei:
            svc.upgrade_diagnosis(
                sb,
                up,
                run_step1_func=r1,
                build_partial_func=lambda x: {},
                paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
                current_user={"id": "U1", "ci_hash": "ci"},
                now_func=lambda: "2026-01-01T00:00:00Z",
            )
    finally:
        svc._save_diagnosis_purchase = orig_p
        svc._bind_linked_user_id = orig_b
    _assert_422(ei, ["is_construction"])
    assert calls["step1"] == 0
    assert calls["purchase"] == 0
    assert calls["bind"] == 0
    assert sb.store["updates"].get("anonymous_diagnosis_results", []) == []
    assert sb.store["inserts"].get("diagnosis_purchases", []) == []


def test_upgrade_construction_true_false_false_reaches_engine():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "CONSTRUCTION",
            "workers": 10,
            "contract_amount_eok": 50,
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
            "raw_structured_input": {"form_data": {"is_construction": True}},
        },
    }
    sb = _SB(existing_result=existing)
    calls = {"step1": 0}
    orig_p = svc._save_diagnosis_purchase
    orig_b = svc._bind_linked_user_id
    svc._save_diagnosis_purchase = lambda *a, **k: None
    svc._bind_linked_user_id = lambda *a, **k: None

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {"applicable_count": 0}}

    up = SimpleNamespace(
        auth_token="t",
        public_token="PT",
        target_tier_code="PAID3",
        payment_ref="PR2",
        invoice_requested=False,
        invoice_biz_no=None,
        invoice_email=None,
    )
    try:
        svc.upgrade_diagnosis(
            sb,
            up,
            run_step1_func=r1,
            build_partial_func=lambda x: {},
            paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
            current_user={"id": "U1", "ci_hash": "ci"},
            now_func=lambda: "2026-01-01T00:00:00Z",
        )
    finally:
        svc._save_diagnosis_purchase = orig_p
        svc._bind_linked_user_id = orig_b
    assert calls["step1"] == 1


def test_upgrade_building_no_predicates_still_runs():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "BUILDING",
            "workers": 10,
            "floor_area": 400,
            "appendix3_item_no": 1,
        },
    }
    sb = _SB(existing_result=existing)
    calls = {"step1": 0}
    orig_p = svc._save_diagnosis_purchase
    orig_b = svc._bind_linked_user_id
    svc._save_diagnosis_purchase = lambda *a, **k: None
    svc._bind_linked_user_id = lambda *a, **k: None

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {"applicable_count": 0}}

    up = SimpleNamespace(
        auth_token="t",
        public_token="PT",
        target_tier_code="PAID3",
        payment_ref="PR2",
        invoice_requested=False,
        invoice_biz_no=None,
        invoice_email=None,
    )
    try:
        svc.upgrade_diagnosis(
            sb,
            up,
            run_step1_func=r1,
            build_partial_func=lambda x: {},
            paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
            current_user={"id": "U1", "ci_hash": "ci"},
            now_func=lambda: "2026-01-01T00:00:00Z",
        )
    finally:
        svc._save_diagnosis_purchase = orig_p
        svc._bind_linked_user_id = orig_b
    assert calls["step1"] == 1
