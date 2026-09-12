"""WO-SM-CORE22-AP01-05-APPENDIX3-SERVER-FAIL-CLOSED-001

BUILDING / INDUSTRIAL Runtime must not start without explicit Appendix3 source.
missing ≠ false. False is answered. KSIC / internal leaves cannot satisfy the gate.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from schemas.diagnosis_integrated import DiagnosisRunBody
from services import diagnosis_integrated_svc as svc
from services.canonical.explicit_appendix3_classification import (
    APPENDIX3_INTERNAL_LEAVES,
    ERROR_ITEM_CONFLICT,
    ERROR_ITEM_TYPE,
    ERROR_REQUIRED,
    Appendix3SourceError,
    missing_explicit_appendix3_fields,
    project_explicit_appendix3_classification,
    stored_appendix3_body,
    validate_explicit_appendix3_classification,
)
from services.legal_rules import normalize_sector_db

CODE = ERROR_REQUIRED


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
                auth = dict(self._store.get("auth") or {})
                return _R(
                    [
                        {
                            "id": "a1",
                            "ci_hash": "ci",
                            "name": "n",
                            "phone": "p",
                            "free_count": auth.get("free_count", 0),
                            "free_limit": auth.get("free_limit", 3),
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
    def __init__(self, existing_result=None, auth=None):
        self.store = {
            "inserts": {},
            "updates": {},
            "reads": [],
            "existing_result": existing_result,
            "auth": auth or {},
        }

    def table(self, n):
        return _RecTable(n, self.store)


def _run_kw(**over):
    kw = dict(
        auto_tier_func=lambda *a, **k: "BUILDING_FREE",
        build_partial_func=lambda f: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={"BUILDING_PAID": 99000, "PAID2": 149000, "PAID3": 249000},
        free_tier_codes={"CONSTRUCTION_FREE", "INDUSTRY_FREE", "BUILDING_FREE"},
        engine_version="t",
        current_user=None,
    )
    kw.update(over)
    return kw


def _assert_required(exc, missing):
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["code"] == CODE
    assert detail["missing_fields"] == missing


def _assert_existing_code(exc, code):
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == code


def test_F1_building_missing_item():
    body = DiagnosisRunBody(sector="BUILDING")
    assert missing_explicit_appendix3_fields(body, "BUILDING") == ["appendix3_item_no"]
    with pytest.raises(HTTPException) as ei:
        validate_explicit_appendix3_classification(body, "BUILDING")
    _assert_required(ei, ["appendix3_item_no"])


def test_F2_industrial_missing_item():
    body = DiagnosisRunBody(sector="INDUSTRIAL")
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == ["appendix3_item_no"]
    with pytest.raises(HTTPException) as ei:
        validate_explicit_appendix3_classification(body, "INDUSTRIAL")
    _assert_required(ei, ["appendix3_item_no"])


def test_F3_industry_alias_normalizes_to_industrial():
    assert normalize_sector_db("INDUSTRY") == "INDUSTRIAL"
    body = DiagnosisRunBody(sector="INDUSTRY")
    assert missing_explicit_appendix3_fields(body, "INDUSTRY") == ["appendix3_item_no"]


def test_F4_manufacturing_alias_normalizes_to_industrial():
    assert normalize_sector_db("MANUFACTURING") == "INDUSTRIAL"
    body = DiagnosisRunBody(sector="MANUFACTURING")
    assert missing_explicit_appendix3_fields(body, "MANUFACTURING") == ["appendix3_item_no"]


def test_F5_building_item_1_pass():
    body = DiagnosisRunBody(sector="BUILDING", appendix3_item_no=1)
    assert missing_explicit_appendix3_fields(body, "BUILDING") == []
    validate_explicit_appendix3_classification(body, "BUILDING")


def test_F6_industrial_item_28_pass():
    body = DiagnosisRunBody(sector="INDUSTRIAL", appendix3_item_no=28)
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == []
    validate_explicit_appendix3_classification(body, "INDUSTRIAL")


def test_F7_building_item37_subtype_missing():
    body = DiagnosisRunBody(sector="BUILDING", appendix3_item_no=37)
    assert missing_explicit_appendix3_fields(body, "BUILDING") == [
        "is_real_estate_management"
    ]
    with pytest.raises(HTTPException) as ei:
        validate_explicit_appendix3_classification(body, "BUILDING")
    _assert_required(ei, ["is_real_estate_management"])


def test_F8_item37_subtype_false_pass():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=37,
        is_real_estate_management=False,
    )
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == []
    validate_explicit_appendix3_classification(body, "INDUSTRIAL")


def test_F9_item37_subtype_true_pass():
    body = DiagnosisRunBody(
        sector="BUILDING",
        appendix3_item_no=37,
        is_real_estate_management=True,
    )
    assert missing_explicit_appendix3_fields(body, "BUILDING") == []
    validate_explicit_appendix3_classification(body, "BUILDING")


def test_F10_item40_subtype_absent_pass():
    body = DiagnosisRunBody(sector="INDUSTRIAL", appendix3_item_no=40)
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == []
    validate_explicit_appendix3_classification(body, "INDUSTRIAL")


def test_F11_item49_completeness_pass_no_is_construction():
    body = DiagnosisRunBody(sector="INDUSTRIAL", appendix3_item_no=49)
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == []
    validate_explicit_appendix3_classification(body, "INDUSTRIAL")
    proj = project_explicit_appendix3_classification(49)
    assert "is_construction" not in proj


def test_F12_construction_missing_appendix3_noop():
    body = DiagnosisRunBody(sector="CONSTRUCTION")
    assert missing_explicit_appendix3_fields(body, "CONSTRUCTION") == []
    validate_explicit_appendix3_classification(body, "CONSTRUCTION")


def test_F13_special_facility_missing_noop():
    for sector in ("SPECIAL", "SPECIAL_FACILITY"):
        body = DiagnosisRunBody(sector=sector)
        assert missing_explicit_appendix3_fields(body, sector) == []
        validate_explicit_appendix3_classification(body, sector)


def test_F14_raw_ksic_only_cannot_satisfy():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        ksic_major="C",
        form_data={"ksic_code": "10", "ksic_list": ["C"], "industry_type": "제조업"},
    )
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == ["appendix3_item_no"]


def test_F15_raw_internal_leaf_only_cannot_satisfy():
    body = DiagnosisRunBody(
        sector="BUILDING",
        form_data={name: True for name in APPENDIX3_INTERNAL_LEAVES},
    )
    assert missing_explicit_appendix3_fields(body, "BUILDING") == ["appendix3_item_no"]


def test_F16_form_data_appendix3_item_no_exact_int():
    body = DiagnosisRunBody(
        sector="BUILDING",
        form_data={"appendix3_item_no": 28},
    )
    assert body.appendix3_item_no is None
    assert missing_explicit_appendix3_fields(body, "BUILDING") == []
    validate_explicit_appendix3_classification(body, "BUILDING")


def test_F17_top_level_form_data_conflict():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        form_data={"appendix3_item_no": 37},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        missing_explicit_appendix3_fields(body, "INDUSTRIAL")
    assert ei.value.code == ERROR_ITEM_CONFLICT
    with pytest.raises(HTTPException) as http_ei:
        validate_explicit_appendix3_classification(body, "INDUSTRIAL")
    _assert_existing_code(http_ei, ERROR_ITEM_CONFLICT)


def test_F18_string_37_type_failure():
    with pytest.raises(ValidationError):
        DiagnosisRunBody.model_validate(
            {"sector": "INDUSTRIAL", "appendix3_item_no": "37"}
        )
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        form_data={"appendix3_item_no": "37"},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        missing_explicit_appendix3_fields(body, "INDUSTRIAL")
    assert ei.value.code == ERROR_ITEM_TYPE
    with pytest.raises(HTTPException) as http_ei:
        validate_explicit_appendix3_classification(body, "INDUSTRIAL")
    _assert_existing_code(http_ei, ERROR_ITEM_TYPE)


def test_F19_float_37_0_type_failure():
    with pytest.raises(ValidationError):
        DiagnosisRunBody.model_validate(
            {"sector": "INDUSTRIAL", "appendix3_item_no": 37.0}
        )
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        form_data={"appendix3_item_no": 37.0},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        missing_explicit_appendix3_fields(body, "INDUSTRIAL")
    assert ei.value.code == ERROR_ITEM_TYPE


def test_F20_true_as_item_type_failure():
    with pytest.raises(ValidationError):
        DiagnosisRunBody.model_validate(
            {"sector": "INDUSTRIAL", "appendix3_item_no": True}
        )
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        form_data={"appendix3_item_no": True},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        missing_explicit_appendix3_fields(body, "INDUSTRIAL")
    assert ei.value.code == ERROR_ITEM_TYPE


def test_item28_plus_subtype_false_completeness_pass():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        is_real_estate_management=False,
    )
    assert missing_explicit_appendix3_fields(body, "INDUSTRIAL") == []
    validate_explicit_appendix3_classification(body, "INDUSTRIAL")
    proj = project_explicit_appendix3_classification(28, False)
    assert "is_real_estate_management" not in proj


def test_run_missing_item_auth_read_only_no_side_effects():
    body = DiagnosisRunBody(
        sector="BUILDING",
        auth_token="t",
        payment_ref="oid1",
    )
    sb = _SB(auth={"free_count": 747, "free_limit": 747})
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
    _assert_required(ei, ["appendix3_item_no"])
    assert calls["step1"] == 0
    assert disc_calls["n"] == 0
    assert sb.store["inserts"].get("anonymous_diagnosis_results", []) == []
    assert sb.store["inserts"].get("diagnosis_disclaimer_log", []) == []
    assert sb.store["inserts"].get("diagnosis_purchases", []) == []
    assert sb.store["updates"].get("diagnosis_auth_log", []) == []
    assert "diagnosis_auth_log" in sb.store["reads"]


def test_run_item37_subtype_missing_no_side_effects():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        auth_token="t",
        payment_ref="oid1",
        appendix3_item_no=37,
    )
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
            svc.run_diagnosis(
                sb,
                body,
                run_step1_func=r1,
                **_run_kw(auto_tier_func=lambda *a, **k: "INDUSTRY_FREE"),
            )
    finally:
        svc._ensure_disclaimer_for_paid_entry = orig
    _assert_required(ei, ["is_real_estate_management"])
    assert calls["step1"] == 0
    assert disc_calls["n"] == 0
    assert sb.store["inserts"].get("anonymous_diagnosis_results", []) == []
    assert sb.store["inserts"].get("diagnosis_disclaimer_log", []) == []
    assert sb.store["updates"].get("diagnosis_auth_log", []) == []


def test_run_missing_item_422_before_quota_402():
    body = DiagnosisRunBody(
        sector="BUILDING",
        auth_token="t",
        disclaimer_log_id="disc1",
    )
    sb = _SB(auth={"free_count": 747, "free_limit": 747})
    calls = {"step1": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {}}

    with pytest.raises(HTTPException) as ei:
        svc.run_diagnosis(sb, body, run_step1_func=r1, **_run_kw())
    assert ei.value.status_code == 422
    _assert_required(ei, ["appendix3_item_no"])
    assert calls["step1"] == 0
    assert sb.store["updates"].get("diagnosis_auth_log", []) == []


def test_run_ksic_spoof_still_422_item():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        auth_token="t",
        payment_ref="oid1",
        ksic_major="C",
        form_data={
            "is_appendix3_1_27": True,
            "ksic_code": "10",
            "industry_type": "제조업",
        },
    )
    with pytest.raises(HTTPException) as ei:
        svc.run_diagnosis(
            _SB(),
            body,
            run_step1_func=lambda *a, **k: {"status": "success", "data": {}},
            **_run_kw(auto_tier_func=lambda *a, **k: "INDUSTRY_FREE"),
        )
    _assert_required(ei, ["appendix3_item_no"])


def test_run_item28_reaches_engine():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        auth_token="t",
        disclaimer_log_id="disc1",
        appendix3_item_no=28,
        worker_count=10,
    )
    sb = _SB()
    calls = {"step1": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {"applicable_count": 0}}

    svc.run_diagnosis(
        sb,
        body,
        run_step1_func=r1,
        **_run_kw(auto_tier_func=lambda *a, **k: "INDUSTRY_FREE"),
    )
    assert calls["step1"] == 1


def _upgrade(existing):
    sb = _SB(existing_result=existing)
    calls = {"step1": 0, "purchase": 0, "bind": 0}

    def r1(*a, **k):
        calls["step1"] += 1
        return {"status": "success", "data": {"applicable_count": 0}}

    orig_p = svc._save_diagnosis_purchase
    orig_b = svc._bind_linked_user_id
    svc._save_diagnosis_purchase = lambda *a, **k: calls.__setitem__(
        "purchase", calls["purchase"] + 1
    )
    svc._bind_linked_user_id = lambda *a, **k: calls.__setitem__(
        "bind", calls["bind"] + 1
    )
    up = SimpleNamespace(
        auth_token="t",
        public_token="PT",
        target_tier_code="PAID3",
        payment_ref="PR2",
        invoice_requested=False,
        invoice_biz_no=None,
        invoice_email=None,
    )
    out = None
    exc = None
    try:
        out = svc.upgrade_diagnosis(
            sb,
            up,
            run_step1_func=r1,
            build_partial_func=lambda x: {},
            paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
            current_user={"id": "U1", "ci_hash": "ci"},
            now_func=lambda: "2026-01-01T00:00:00Z",
        )
    except HTTPException as e:
        exc = e
    finally:
        svc._save_diagnosis_purchase = orig_p
        svc._bind_linked_user_id = orig_b
    return out, sb, calls, exc


def test_U1_stored_building_no_item():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {"sector": "BUILDING", "workers": 10, "floor_area": 400},
    }
    _out, sb, calls, exc = _upgrade(existing)
    assert exc is not None
    wrapper = SimpleNamespace(value=exc)
    _assert_required(wrapper, ["appendix3_item_no"])
    assert calls["step1"] == 0
    assert calls["purchase"] == 0
    assert calls["bind"] == 0
    assert sb.store["updates"].get("anonymous_diagnosis_results", []) == []
    assert sb.store["inserts"].get("diagnosis_purchases", []) == []


def test_U2_stored_industrial_item37_no_subtype():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {"sector": "INDUSTRIAL", "appendix3_item_no": 37, "workers": 10},
    }
    _out, sb, calls, exc = _upgrade(existing)
    assert exc is not None
    _assert_required(SimpleNamespace(value=exc), ["is_real_estate_management"])
    assert calls["step1"] == 0
    assert calls["purchase"] == 0
    assert sb.store["updates"].get("anonymous_diagnosis_results", []) == []


def test_U3_stored_item28_pass():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "INDUSTRIAL",
            "appendix3_item_no": 28,
            "workers": 10,
            "floor_area": 400,
        },
    }
    _out, _sb, calls, exc = _upgrade(existing)
    assert exc is None
    assert calls["step1"] == 1
    assert calls["purchase"] == 1


def test_U4_stored_item37_false_pass():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "BUILDING",
            "appendix3_item_no": 37,
            "is_real_estate_management": False,
            "workers": 10,
            "floor_area": 400,
        },
    }
    _out, _sb, calls, exc = _upgrade(existing)
    assert exc is None
    assert calls["step1"] == 1


def test_U5_stored_item37_true_pass():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "INDUSTRIAL",
            "appendix3_item_no": 37,
            "is_real_estate_management": True,
            "workers": 10,
            "floor_area": 400,
        },
    }
    _out, _sb, calls, exc = _upgrade(existing)
    assert exc is None
    assert calls["step1"] == 1


def test_U6_stored_raw_ksic_only_fail():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "INDUSTRIAL",
            "ksic_major": "C",
            "raw_structured_input": {"form_data": {"ksic_code": "10"}},
        },
    }
    _out, sb, calls, exc = _upgrade(existing)
    assert exc is not None
    _assert_required(SimpleNamespace(value=exc), ["appendix3_item_no"])
    assert calls["purchase"] == 0


def test_U7_stored_projected_leaves_only_fail():
    existing = {
        "id": "R1",
        "ci_hash": "ci",
        "tier_code": "PAID2",
        "paid_amount": 149000,
        "status": "ACTIVE",
        "input_data": {
            "sector": "BUILDING",
            "is_appendix3_1_27": True,
            "raw_structured_input": {
                "form_data": {name: True for name in APPENDIX3_INTERNAL_LEAVES}
            },
        },
    }
    _out, sb, calls, exc = _upgrade(existing)
    assert exc is not None
    _assert_required(SimpleNamespace(value=exc), ["appendix3_item_no"])
    assert calls["purchase"] == 0


def test_stored_form_data_item_satisfies_upgrade():
    stored = {
        "sector": "BUILDING",
        "raw_structured_input": {"form_data": {"appendix3_item_no": 1}},
    }
    assert missing_explicit_appendix3_fields(
        stored_appendix3_body(stored), "BUILDING"
    ) == []
