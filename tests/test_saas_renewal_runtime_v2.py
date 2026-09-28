"""TAI Safe Pricing V2 — Renewal Runtime Branch Wiring Tests (R01-R45).

검증 범위:
  R01-R07   classify_renewal_runtime_route (pure function)
  R08-R12   _validate_v2_payment_guards (via apply_saas_v2_renewal_runtime)
  R13-R21   V2 first apply: contract validation guards
  R22-R27   V2 first apply: temporal / build / apply path
  R28-R35   V2 replay path
  R36-R39   Race recovery + double extension invariants
  R40-R45   payment_post_process routing wiring

DB/네트워크 없음 — 순수 unit tests.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from services.saas_renewal_runtime_v2 import (
    SaasV2RenewalRuntimeError,
    apply_saas_v2_renewal_runtime,
    classify_renewal_runtime_route,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_PID = str(uuid.uuid4())
_CID = str(uuid.uuid4())
_QID = str(uuid.uuid4())
_UID = str(uuid.uuid4())
_CO  = str(uuid.uuid4())


def _pay(**overrides) -> dict:
    base = {
        "id":           _PID,
        "payment_type": "RENEWAL",
        "product_type": "SAAS",
        "status_code":  "PAID",
        "plan_code":    None,
        "contract_id":  _CID,
        "quote_id":     _QID,
        "company_id":   _CO,
        "user_id":      _UID,
        "paid_at":      "2026-09-28T12:00:00+09:00",
    }
    base.update(overrides)
    return base


def _sb_noop() -> MagicMock:
    """Supabase mock: all CV queries return empty (used for guard tests)."""
    sb = MagicMock()
    # _lookup_target_cv always returns []
    _chain(sb, "saas_contract_commercial_versions").execute.return_value.data = []
    return sb


def _chain(sb: MagicMock, table: str) -> MagicMock:
    return sb.table(table).select.return_value.eq.return_value


# ── R01-R07: classify_renewal_runtime_route ───────────────────────────────────

class TestClassifyRoute:
    def test_r01_v2(self):
        assert classify_renewal_runtime_route(_pay()) == "V2"

    def test_r02_legacy_construction(self):
        assert classify_renewal_runtime_route(_pay(product_type="SAAS_CONSTRUCTION")) == "LEGACY"

    def test_r03_legacy_industry(self):
        assert classify_renewal_runtime_route(_pay(product_type="SAAS_INDUSTRY")) == "LEGACY"

    def test_r04_legacy_facility(self):
        assert classify_renewal_runtime_route(_pay(product_type="SAAS_FACILITY")) == "LEGACY"

    def test_r05_legacy_building(self):
        assert classify_renewal_runtime_route(_pay(product_type="SAAS_BUILDING")) == "LEGACY"

    def test_r06_invalid_unknown_product(self):
        assert classify_renewal_runtime_route(_pay(product_type="UNKNOWN_PRODUCT")) == "INVALID"

    def test_r07_not_renewal(self):
        assert classify_renewal_runtime_route(_pay(payment_type="NEW_CONTRACT")) == "NOT_RENEWAL"


# ── R08-R12: _validate_v2_payment_guards ──────────────────────────────────────

class TestValidateGuards:
    """Guards fire before any DB query — _sb_noop() is never reached."""

    def _run(self, pay: dict) -> None:
        with patch("services.saas_renewal_runtime_v2._lookup_target_cv", return_value=None):
            with patch("services.saas_renewal_runtime_v2._run_first_apply") as m:
                m.return_value = {"status": "APPLIED"}
                apply_saas_v2_renewal_runtime(MagicMock(), pay)

    def test_r08_status_code_invalid(self):
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            self._run(_pay(status_code="PENDING"))
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"

    def test_r09_plan_code_not_null(self):
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            self._run(_pay(plan_code="PLAN_A"))
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"

    def test_r10_contract_id_missing(self):
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            self._run(_pay(contract_id=None))
        assert exc.value.code == "V2_RUNTIME_CONTRACT_NOT_FOUND"

    def test_r11_quote_id_missing(self):
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            self._run(_pay(quote_id=None))
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"

    def test_r12_paid_at_missing(self):
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            self._run(_pay(paid_at=None))
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"


# ── R13-R21: V2 first apply — contract validation ─────────────────────────────

def _make_sb_first_apply(
    *,
    target_rows=None,
    contract_rows=None,
    cv_rows=None,
) -> MagicMock:
    """Supabase mock for first apply path with configurable returns."""
    sb = MagicMock()
    target_rows = target_rows or []
    contract_rows = contract_rows if contract_rows is not None else []
    cv_rows = cv_rows or []

    def table_side(name):
        t = MagicMock()
        if name == "saas_contract_commercial_versions":
            def eq_side(field, val):
                e = MagicMock()
                if field == "renewal_payment_id":
                    e.execute.return_value = MagicMock(data=target_rows)
                else:
                    e.execute.return_value = MagicMock(data=cv_rows)
                return e
            t.select.return_value.eq = eq_side
        elif name == "contracts":
            ct = MagicMock()
            ct.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=contract_rows)
            return ct
        return t

    sb.table.side_effect = table_side
    return sb


def _contract(**overrides) -> dict:
    base = {
        "id":           _CID,
        "company_id":   _CO,
        "status_code":  "ACTIVE",
        "service_type": "SAAS",
        "end_date":     "2026-12-01",
    }
    base.update(overrides)
    return base


_SAMPLE_CV = {
    "id": str(uuid.uuid4()),
    "contract_id": _CID,
    "version_no": 1,
    "effective_from": "2026-01-01T00:00:00+09:00",
    "superseded_at": None,
}

_EFFECTIVE_AT = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)


class TestFirstApplyContractValidation:
    """R13-R21: First apply path — contract-level guards."""

    def _run_with_contract(self, contract_data):
        """Run first apply with given contract; mocks all downstream calls."""
        sb = _make_sb_first_apply(
            contract_rows=[contract_data],
            cv_rows=[_SAMPLE_CV],
        )
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.saas_renewal_runtime_v2._build_and_apply",
                           return_value={"status": "APPLIED"}) as m_build:
                    result = apply_saas_v2_renewal_runtime(sb, _pay())
        return result

    def test_r13_happy_path_applied(self):
        result = self._run_with_contract(_contract())
        assert result["status"] == "APPLIED"

    def test_r14_contract_not_found(self):
        sb = _make_sb_first_apply(contract_rows=[])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_CONTRACT_NOT_FOUND"

    def test_r15_company_mismatch(self):
        sb = _make_sb_first_apply(
            contract_rows=[_contract(company_id=str(uuid.uuid4()))],
            cv_rows=[_SAMPLE_CV],
        )
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_CONTRACT_MISMATCH"

    def test_r16_contract_not_active(self):
        sb = _make_sb_first_apply(
            contract_rows=[_contract(status_code="EXPIRED")],
            cv_rows=[_SAMPLE_CV],
        )
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_CONTRACT_NOT_ACTIVE"

    def test_r17_service_type_not_saas(self):
        sb = _make_sb_first_apply(
            contract_rows=[_contract(service_type="CONSTRUCTION")],
            cv_rows=[_SAMPLE_CV],
        )
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_CONTRACT_NOT_SAAS"

    def test_r18_end_date_null(self):
        sb = _make_sb_first_apply(
            contract_rows=[_contract(end_date=None)],
            cv_rows=[_SAMPLE_CV],
        )
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_END_DATE_REQUIRED"

    def test_r19_paid_at_naive_no_tz(self):
        sb = _make_sb_first_apply(
            contract_rows=[_contract()],
            cv_rows=[_SAMPLE_CV],
        )
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay(paid_at="2026-09-28T12:00:00"))
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"

    def test_r20_temporal_current_not_found(self):
        from services.saas_commercial_version_time_v2 import TemporalVersionError
        sb = _make_sb_first_apply(
            contract_rows=[_contract()],
            cv_rows=[_SAMPLE_CV],
        )
        err = TemporalVersionError("TEMPORAL_CURRENT_NOT_FOUND", "not found")
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   side_effect=err):
            with pytest.raises(SaasV2RenewalRuntimeError) as exc:
                apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TEMPORAL_CURRENT_NOT_FOUND"

    def test_r21_temporal_current_ambiguous(self):
        from services.saas_commercial_version_time_v2 import TemporalVersionError
        sb = _make_sb_first_apply(
            contract_rows=[_contract()],
            cv_rows=[_SAMPLE_CV],
        )
        err = TemporalVersionError("TEMPORAL_CURRENT_AMBIGUOUS", "ambiguous")
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   side_effect=err):
            with pytest.raises(SaasV2RenewalRuntimeError) as exc:
                apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TEMPORAL_CURRENT_AMBIGUOUS"


# ── R22-R27: First apply — build/apply path ───────────────────────────────────

class TestFirstApplyBuildApply:
    def _full_mock_sb(self) -> MagicMock:
        return _make_sb_first_apply(
            contract_rows=[_contract()],
            cv_rows=[_SAMPLE_CV],
        )

    def test_r22_uses_contract_end_date_as_boundary(self):
        """contract_end_date_to_effective_at_v2 is called with contract.end_date."""
        sb = self._full_mock_sb()
        captured_effective_at = []

        def fake_build_apply(_, _pay, source_cv, requested_effective_at):
            captured_effective_at.append(requested_effective_at)
            return {"status": "APPLIED"}

        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT) as m_eff:
                with patch("services.saas_renewal_runtime_v2._build_and_apply",
                           side_effect=fake_build_apply):
                    apply_saas_v2_renewal_runtime(sb, _pay())
        m_eff.assert_called_once_with("2026-12-01")
        assert captured_effective_at[0] == _EFFECTIVE_AT

    def test_r23_quote_not_found_raises(self):
        sb = self._full_mock_sb()
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.member_quote_svc.get_member_quote", return_value=None):
                    with patch("services.saas_renewal_v2_adapter.build_saas_v2_renewal_apply_plan"):
                        with patch("services.saas_renewal_atomic_apply_v2.apply_saas_v2_renewal_plan_atomic"):
                            with pytest.raises(SaasV2RenewalRuntimeError) as exc:
                                apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_PAYMENT_INVALID"
        assert "quote" in exc.value.message.lower()

    def test_r24_adapter_error_propagates(self):
        from services.saas_renewal_v2_adapter import SaasRenewalV2AdapterError
        sb = self._full_mock_sb()
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.member_quote_svc.get_member_quote",
                           return_value={"id": _QID}):
                    with patch("services.saas_renewal_v2_adapter.build_saas_v2_renewal_apply_plan",
                               side_effect=SaasRenewalV2AdapterError("PLAN_ERROR", "fail")):
                        with pytest.raises(SaasRenewalV2AdapterError):
                            apply_saas_v2_renewal_runtime(sb, _pay())

    def test_r25_atomic_error_propagates(self):
        from services.saas_renewal_atomic_apply_v2 import SaasV2RenewalAtomicApplyError
        sb = self._full_mock_sb()
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.member_quote_svc.get_member_quote",
                           return_value={"id": _QID}):
                    with patch("services.saas_renewal_v2_adapter.build_saas_v2_renewal_apply_plan",
                               return_value=MagicMock()):
                        with patch("services.saas_renewal_atomic_apply_v2.apply_saas_v2_renewal_plan_atomic",
                                   side_effect=SaasV2RenewalAtomicApplyError("RPC_ERR", "fail")):
                            with pytest.raises(SaasV2RenewalAtomicApplyError):
                                apply_saas_v2_renewal_runtime(sb, _pay())

    def test_r26_already_applied_returned_as_is(self):
        sb = self._full_mock_sb()
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.saas_renewal_runtime_v2._build_and_apply",
                           return_value={"status": "ALREADY_APPLIED"}):
                    result = apply_saas_v2_renewal_runtime(sb, _pay())
        assert result["status"] == "ALREADY_APPLIED"

    def test_r27_applied_returned(self):
        sb = self._full_mock_sb()
        with patch("services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
                   return_value=_SAMPLE_CV):
            with patch("services.saas_commercial_version_time_v2.contract_end_date_to_effective_at_v2",
                       return_value=_EFFECTIVE_AT):
                with patch("services.saas_renewal_runtime_v2._build_and_apply",
                           return_value={"status": "APPLIED"}):
                    result = apply_saas_v2_renewal_runtime(sb, _pay())
        assert result["status"] == "APPLIED"


# ── R28-R35: V2 replay path ────────────────────────────────────────────────────

_TARGET_CV_V2 = {
    "id":                  str(uuid.uuid4()),
    "contract_id":         _CID,
    "version_no":          2,
    "effective_from":      "2026-12-01T00:00:00+09:00",
    "renewal_payment_id":  _PID,
    "superseded_at":       None,
}

_SOURCE_CV_V1 = {
    "id":             str(uuid.uuid4()),
    "contract_id":    _CID,
    "version_no":     1,
    "effective_from": "2026-01-01T00:00:00+09:00",
    "superseded_at":  "2026-12-01T00:00:00+09:00",
}


def _make_sb_replay(
    *,
    target_rows=None,
    source_rows=None,
) -> MagicMock:
    sb = MagicMock()
    target_rows = target_rows if target_rows is not None else [_TARGET_CV_V2]
    source_rows = source_rows if source_rows is not None else [_SOURCE_CV_V1]

    def table_side(name):
        t = MagicMock()
        if name == "saas_contract_commercial_versions":
            call_seq = [0]

            def eq_field_side(field, val):
                e = MagicMock()
                if field == "renewal_payment_id":
                    e.execute.return_value = MagicMock(data=target_rows)
                elif field == "contract_id":
                    # next .eq("version_no", ...) chained
                    def eq_version_side(f2, v2):
                        e2 = MagicMock()
                        e2.limit.return_value = MagicMock(
                            execute=MagicMock(return_value=MagicMock(data=source_rows))
                        )
                        return e2
                    e.eq = eq_version_side
                return e

            t.select.return_value.eq = eq_field_side
        return t

    sb.table.side_effect = table_side
    return sb


class TestReplayPath:
    def test_r28_replay_uses_effective_from_boundary(self):
        """Replay path uses target.effective_from — NOT contract.end_date."""
        sb = _make_sb_replay()
        captured = []

        def fake_build_apply(_, _pay, source_cv, requested_effective_at):
            captured.append(requested_effective_at)
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_renewal_runtime_v2._build_and_apply",
                   side_effect=fake_build_apply):
            result = apply_saas_v2_renewal_runtime(sb, _pay())

        assert result["status"] == "ALREADY_APPLIED"
        assert len(captured) == 1
        # Must be derived from target effective_from (2026-12-01T00:00:00+09:00)
        # NOT from contract.end_date (contract was never queried in replay path)
        eff = captured[0]
        assert eff.year == 2026 and eff.month == 12 and eff.day == 1

    def test_r29_target_contract_mismatch(self):
        sb = _make_sb_replay(target_rows=[{**_TARGET_CV_V2, "contract_id": str(uuid.uuid4())}])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_CONTRACT_MISMATCH"

    def test_r30_target_version_no_too_low(self):
        sb = _make_sb_replay(target_rows=[{**_TARGET_CV_V2, "version_no": 1}])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_VERSION_INVALID"

    def test_r31_target_version_no_not_int(self):
        sb = _make_sb_replay(target_rows=[{**_TARGET_CV_V2, "version_no": "two"}])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_VERSION_INVALID"

    def test_r32_source_cv_not_found(self):
        sb = _make_sb_replay(source_rows=[])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_SOURCE_NOT_FOUND"

    def test_r33_multiple_target_cvs_raises_ambiguous(self):
        sb = _make_sb_replay(target_rows=[_TARGET_CV_V2, _TARGET_CV_V2])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_AMBIGUOUS"

    def test_r34_effective_from_unparseable(self):
        sb = _make_sb_replay(target_rows=[{**_TARGET_CV_V2, "effective_from": "NOT_A_DATE"}])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_VERSION_INVALID"

    def test_r35_replay_never_queries_contracts_table(self):
        """When target CV is found, contract table is never queried."""
        sb = _make_sb_replay()
        with patch("services.saas_renewal_runtime_v2._build_and_apply",
                   return_value={"status": "ALREADY_APPLIED"}):
            apply_saas_v2_renewal_runtime(sb, _pay())
        # contracts table must not have been accessed
        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", "Replay path must not query contracts table"


# ── R36-R39: Race recovery + double extension invariants ──────────────────────

class TestRaceRecoveryAndInvariants:
    def test_r36_race_recovery_uses_replay_when_target_appears(self):
        """If first apply raises and target is found on re-check, replay is used."""
        call_seq = {"n": 0}

        def lookup_side(_sb, _pid):
            call_seq["n"] += 1
            if call_seq["n"] == 1:
                return None
            return _TARGET_CV_V2

        with patch("services.saas_renewal_runtime_v2._lookup_target_cv",
                   side_effect=lookup_side):
            with patch("services.saas_renewal_runtime_v2._validate_v2_payment_guards"):
                with patch("services.saas_renewal_runtime_v2._run_first_apply",
                           side_effect=RuntimeError("concurrent write")):
                    with patch("services.saas_renewal_runtime_v2._run_replay",
                               return_value={"status": "ALREADY_APPLIED"}) as m_replay:
                        result = apply_saas_v2_renewal_runtime(MagicMock(), _pay())

        assert result["status"] == "ALREADY_APPLIED"
        m_replay.assert_called_once()

    def test_r37_race_recovery_reraises_when_no_target(self):
        """If first apply raises and no target on re-check, original error propagates."""
        with patch("services.saas_renewal_runtime_v2._lookup_target_cv", return_value=None):
            with patch("services.saas_renewal_runtime_v2._validate_v2_payment_guards"):
                with patch("services.saas_renewal_runtime_v2._run_first_apply",
                           side_effect=RuntimeError("permanent failure")):
                    with pytest.raises(RuntimeError, match="permanent failure"):
                        apply_saas_v2_renewal_runtime(MagicMock(), _pay())

    def _make_ppp_sb(self, pay: dict) -> MagicMock:
        """Supabase mock for on_payment_success_sync: returns pay on payments query."""
        sb = MagicMock()
        # payments fetch: any chained call returns [pay]
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [pay]
        return sb

    def _run_on_payment_success(self, pay: dict, **extra_patches):
        import services.payment_post_process as ppp
        sb = self._make_ppp_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.payment_post_process.send_payment_notification") as m_notif:
                        with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                            with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                                       return_value={"status": "APPLIED"}) as m_v2:
                                # Apply any extra patches via context managers
                                for target, value in extra_patches.items():
                                    pass
                                ppp.on_payment_success_sync(pay["id"])
        return m_v2, m_ext, m_notif

    def test_r38_v2_route_never_calls_extend_contract_for_renewal(self):
        """V2 payment MUST NOT call _extend_contract_for_renewal (double extension proof)."""
        import services.payment_post_process as ppp

        pay = {
            "id":             _PID,
            "payment_type":   "RENEWAL",
            "product_type":   "SAAS",
            "status_code":    "PAID",
            "plan_code":      None,
            "contract_id":    _CID,
            "quote_id":       _QID,
            "company_id":     _CO,
            "user_id":        _UID,
            "paid_at":        "2026-09-28T12:00:00+09:00",
        }
        sb = self._make_ppp_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.payment_post_process.send_payment_notification"):
                        with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                            with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                                       return_value={"status": "APPLIED"}):
                                ppp.on_payment_success_sync(pay["id"])
        m_ext.assert_not_called()

    def test_r39_legacy_route_never_calls_apply_v2_renewal_runtime(self):
        """LEGACY renewal MUST NOT call apply_saas_v2_renewal_runtime."""
        import services.payment_post_process as ppp

        pay = {
            "id":             _PID,
            "payment_type":   "RENEWAL",
            "product_type":   "SAAS_INDUSTRY",
            "status_code":    "PAID",
            "plan_code":      "INDUSTRY_PRO",
            "contract_id":    _CID,
            "quote_id":       None,
            "company_id":     _CO,
            "user_id":        _UID,
            "paid_at":        "2026-09-28T12:00:00+09:00",
        }
        sb = self._make_ppp_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.payment_post_process.send_payment_notification"):
                        with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime") as m_v2:
                            with patch.object(ppp, "_extend_contract_for_renewal"):
                                ppp.on_payment_success_sync(pay["id"])
        m_v2.assert_not_called()


# ── R40-R45: payment_post_process routing wiring ─────────────────────────────

class TestPaymentPostProcessRouting:
    """R40-R45 verify the PPP routing table without touching real DB."""

    def _base_pay(self, **kw) -> dict:
        base = {
            "id":             _PID,
            "payment_type":   "RENEWAL",
            "product_type":   "SAAS",
            "status_code":    "PAID",
            "plan_code":      None,
            "contract_id":    _CID,
            "quote_id":       _QID,
            "company_id":     _CO,
            "user_id":        _UID,
            "paid_at":        "2026-09-28T12:00:00+09:00",
        }
        base.update(kw)
        return base

    def _make_sb(self, pay: dict) -> MagicMock:
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [pay]
        return sb

    def _run(self, pay: dict, v2_side=None):
        import services.payment_post_process as ppp
        v2_side = v2_side or {"status": "APPLIED"}
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.payment_post_process.send_payment_notification") as m_notif:
                        with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                            with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                                       return_value=v2_side if isinstance(v2_side, dict) else None,
                                       side_effect=v2_side if not isinstance(v2_side, dict) else None) as m_v2:
                                ppp.on_payment_success_sync(pay["id"])
        return m_v2, m_ext, m_notif

    def test_r40_v2_route_calls_apply_v2(self):
        m_v2, m_ext, _ = self._run(self._base_pay())
        m_v2.assert_called_once()
        m_ext.assert_not_called()

    def test_r41_legacy_route_calls_extend(self):
        pay = self._base_pay(product_type="SAAS_CONSTRUCTION", plan_code="INDUSTRY_PRO")
        m_v2, m_ext, _ = self._run(pay)
        m_v2.assert_not_called()
        m_ext.assert_called_once()

    def test_r42_invalid_route_no_notification(self):
        pay = self._base_pay(product_type="COMPLETELY_UNKNOWN")
        m_v2, m_ext, m_notif = self._run(pay)
        m_v2.assert_not_called()
        m_ext.assert_not_called()
        m_notif.assert_not_called()

    def test_r43_v2_applied_sends_notification(self):
        _, _, m_notif = self._run(self._base_pay(), v2_side={"status": "APPLIED"})
        m_notif.assert_called_once()

    def test_r44_legacy_sends_notification(self):
        pay = self._base_pay(product_type="SAAS_BUILDING", plan_code="BUILDING_PRO")
        _, _, m_notif = self._run(pay)
        m_notif.assert_called_once()

    def test_r45_v2_runtime_error_propagates_no_legacy_fallback(self):
        """SaasV2RenewalRuntimeError must propagate; legacy fallback is forbidden."""
        import services.payment_post_process as ppp

        pay = self._base_pay()
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                               side_effect=SaasV2RenewalRuntimeError("V2_RUNTIME_CONTRACT_NOT_ACTIVE")):
                        with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                            with pytest.raises(SaasV2RenewalRuntimeError):
                                ppp.on_payment_success_sync(pay["id"])
        m_ext.assert_not_called()


# ── R46-R49: RENEWAL cannot fall into new contract writer ─────────────────────

class TestRenewalCannotCreateNewContract:
    """Broken renewal inputs must not reach _create_contract_from_payment."""

    def _make_sb(self, pay: dict) -> MagicMock:
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [pay]
        return sb

    def _base_pay(self, **kw) -> dict:
        base = {
            "id":             _PID,
            "payment_type":   "RENEWAL",
            "product_type":   "SAAS",
            "status_code":    "PAID",
            "plan_code":      None,
            "contract_id":    None,
            "quote_id":       _QID,
            "company_id":     _CO,
            "user_id":        _UID,
            "paid_at":        "2026-09-28T12:00:00+09:00",
        }
        base.update(kw)
        return base

    def test_r46_v2_renewal_null_contract_id_reaches_runtime_not_new_contract(self):
        """V2 Renewal with contract_id=None → runtime invoked, new contract writer = 0."""
        import services.payment_post_process as ppp

        pay = self._base_pay(contract_id=None)
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                               side_effect=SaasV2RenewalRuntimeError("V2_RUNTIME_CONTRACT_NOT_FOUND")) as m_v2:
                        with patch.object(ppp, "_create_contract_from_payment") as m_new:
                            with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                                with patch.object(ppp, "send_payment_notification") as m_notif:
                                    with pytest.raises(SaasV2RenewalRuntimeError):
                                        ppp.on_payment_success_sync(pay["id"])
        m_v2.assert_called_once()
        m_new.assert_not_called()
        m_ext.assert_not_called()
        m_notif.assert_not_called()

    def test_r47_legacy_renewal_null_contract_id_fails_closed(self):
        """Legacy Renewal with contract_id=None → all writers = 0."""
        import services.payment_post_process as ppp

        pay = self._base_pay(product_type="SAAS_INDUSTRY", plan_code="INDUSTRY_PRO", contract_id=None)
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                        with patch.object(ppp, "_create_contract_from_payment") as m_new:
                            with patch.object(ppp, "send_payment_notification") as m_notif:
                                ppp.on_payment_success_sync(pay["id"])
        m_ext.assert_not_called()
        m_new.assert_not_called()
        m_notif.assert_not_called()

    def test_r48_invalid_renewal_null_contract_id_fails_closed(self):
        """INVALID Renewal with contract_id=None → all writers = 0."""
        import services.payment_post_process as ppp

        pay = self._base_pay(product_type="COMPLETELY_UNKNOWN", contract_id=None)
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch.object(ppp, "_extend_contract_for_renewal") as m_ext:
                        with patch.object(ppp, "_create_contract_from_payment") as m_new:
                            with patch.object(ppp, "send_payment_notification") as m_notif:
                                ppp.on_payment_success_sync(pay["id"])
        m_ext.assert_not_called()
        m_new.assert_not_called()
        m_notif.assert_not_called()

    def test_r49_any_renewal_never_reaches_new_contract_writer(self):
        """SAAS RENEWAL failure must not fall into _create_contract_from_payment."""
        import services.payment_post_process as ppp

        pay = self._base_pay(contract_id=None)
        sb = self._make_sb(pay)
        with patch("services.payment_post_process.get_supabase", return_value=sb):
            with patch("services.payment_post_process._bootstrap_buyer_company_admin"):
                with patch("services.payment_post_process._fire_automation"):
                    with patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
                               side_effect=SaasV2RenewalRuntimeError("V2_RUNTIME_CONTRACT_NOT_FOUND")):
                        with patch.object(ppp, "_create_contract_from_payment") as m_new:
                            with pytest.raises(SaasV2RenewalRuntimeError):
                                ppp.on_payment_success_sync(pay["id"])
        m_new.assert_not_called()


# ── R50-R52: payment_svc V2 card success atomic boundary ─────────────────────

class TestCardSuccessAtomicBoundary:
    """R50-R52: V2 Renewal card success must not execute direct contract.update."""

    def _payment(self, **kw) -> MagicMock:
        base = {
            "id":             _PID,
            "payment_type":   "RENEWAL",
            "product_type":   "SAAS",
            "contract_id":    _CID,
            "period_months":  None,
        }
        base.update(kw)
        return base

    def _run_card_success(self, payment: dict, post_process_side=None):
        from services.payment_svc import process_card_success
        sb = MagicMock()
        sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("services.payment_svc.get_supabase", return_value=sb):
            with patch("services.payment_svc.now_iso", return_value="2026-09-28T12:00:00+09:00"):
                with patch("services.payment_svc.service_status_after_card_pay", return_value="ACTIVE"):
                    with patch("services.payment_svc.calc_expired_at", return_value=None):
                        with patch("services.tax_invoice_request_svc.canonical_payment_instrument", return_value="CARD"):
                            with patch("services.payment_post_process.on_payment_success_sync",
                                       side_effect=post_process_side) as m_ppp:
                                process_card_success(
                                    payment,
                                    auth_result={"applNum": "12345", "tid": "TID"},
                                    paymethod="Card",
                                    order_id="oid",
                                    goodname="test",
                                    price="100000",
                                    with_redirect_qs=False,
                                )
        return sb

    def test_r50_v2_renewal_success_no_direct_contract_update(self):
        """V2 Renewal card success: contracts.update(is_active) call = 0."""
        payment = self._payment()
        sb = self._run_card_success(payment)

        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", \
                f"contracts table was accessed in V2 Renewal card success: {c}"

    def test_r51_v2_renewal_post_process_failure_no_direct_contract_update(self):
        """V2 Renewal card success + on_payment_success_sync raises: contracts.update = 0."""
        payment = self._payment()
        sb = self._run_card_success(
            payment,
            post_process_side=Exception("post-process failed"),
        )

        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", \
                f"contracts table was accessed after V2 post-process failure: {c}"

    def test_r52_legacy_card_success_contract_update_maintained(self):
        """Legacy (non-V2 Renewal) card success: contracts.update(is_active) still fires."""
        payment = self._payment(payment_type="NEW_CONTRACT", product_type="SAAS_INDUSTRY",
                                plan_code="INDUSTRY_PRO")
        sb = self._run_card_success(payment)

        contracts_calls = [c for c in sb.table.call_args_list if c.args[0] == "contracts"]
        assert len(contracts_calls) >= 1, "Legacy card success must update contracts.is_active"


# ── R53: Naive effective_from rejected ────────────────────────────────────────

class TestNaiveEffectiveFromRejected:
    def test_r53_naive_target_effective_from_raises(self):
        """Naive target.effective_from → V2_RUNTIME_TARGET_VERSION_INVALID (fail closed)."""
        target_cv_naive = {
            **_TARGET_CV_V2,
            "effective_from": "2026-12-01T00:00:00",  # no tz offset
        }
        sb = _make_sb_replay(target_rows=[target_cv_naive])
        with pytest.raises(SaasV2RenewalRuntimeError) as exc:
            apply_saas_v2_renewal_runtime(sb, _pay())
        assert exc.value.code == "V2_RUNTIME_TARGET_VERSION_INVALID"
        assert "timezone-aware" in exc.value.message


# ── R54-R57: INICIS noti partial projection boundary ─────────────────────────

class TestNotiPartialProjectionBoundary:
    """R54-R57: /inicis/noti payment_type absence must not allow direct contract write."""

    def _run_card_success_with_payment(self, payment: dict, post_process_side=None):
        from services.payment_svc import process_card_success
        sb = MagicMock()
        with patch("services.payment_svc.get_supabase", return_value=sb):
            with patch("services.payment_svc.now_iso", return_value="2026-09-28T12:00:00+09:00"):
                with patch("services.payment_svc.service_status_after_card_pay", return_value="ACTIVE"):
                    with patch("services.payment_svc.calc_expired_at", return_value=None):
                        with patch("services.tax_invoice_request_svc.canonical_payment_instrument",
                                   return_value="CARD"):
                            with patch("services.payment_post_process.on_payment_success_sync",
                                       side_effect=post_process_side):
                                process_card_success(
                                    payment,
                                    auth_result={"applNum": "12345", "tid": "TID"},
                                    paymethod="Card",
                                    order_id="oid",
                                    goodname="test",
                                    price="100000",
                                    with_redirect_qs=False,
                                )
        return sb

    def test_r54_noti_projection_with_payment_type_v2_no_direct_write(self):
        """Correct noti projection (payment_type included) → V2 Renewal: contracts write = 0."""
        payment = {
            "id":             _PID,
            "status_code":    "SUCCESS",
            "contract_id":    _CID,
            "product_type":   "SAAS",
            "payment_type":   "RENEWAL",
            "period_months":  None,
        }
        sb = self._run_card_success_with_payment(payment)
        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", \
                f"contracts table accessed in V2 noti path: {c}"

    def test_r55_partial_caller_saas_payment_type_absent_success_no_direct_write(self):
        """SAAS + contract_id + payment_type key ABSENT, post-process OK → contracts write = 0."""
        payment = {
            "id":             _PID,
            "status_code":    "SUCCESS",
            "contract_id":    _CID,
            "product_type":   "SAAS",
            # payment_type intentionally absent
            "period_months":  None,
        }
        sb = self._run_card_success_with_payment(payment)
        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", \
                f"contracts table accessed with missing payment_type (SAAS): {c}"

    def test_r56_partial_caller_saas_payment_type_absent_failure_no_direct_write(self):
        """SAAS + payment_type absent + post-process raises → contracts write = 0."""
        payment = {
            "id":             _PID,
            "status_code":    "SUCCESS",
            "contract_id":    _CID,
            "product_type":   "SAAS",
            "period_months":  None,
        }
        sb = self._run_card_success_with_payment(
            payment, post_process_side=Exception("atomic failed")
        )
        for c in sb.table.call_args_list:
            assert c.args[0] != "contracts", \
                f"contracts table accessed after V2 failure with missing payment_type: {c}"

    def test_r57_partial_caller_legacy_saas_type_absent_contract_update_maintained(self):
        """SAAS_INDUSTRY + payment_type absent → legacy contracts.is_active update maintained."""
        payment = {
            "id":             _PID,
            "status_code":    "SUCCESS",
            "contract_id":    _CID,
            "product_type":   "SAAS_INDUSTRY",
            # payment_type absent — legacy product, must still activate
            "period_months":  None,
        }
        sb = self._run_card_success_with_payment(payment)
        contracts_calls = [c for c in sb.table.call_args_list if c.args[0] == "contracts"]
        assert len(contracts_calls) >= 1, \
            "Legacy SAAS_INDUSTRY must still update contracts.is_active even without payment_type"


# ── R58: Static projection assertion ─────────────────────────────────────────

class TestNotiProjectionStatic:
    def test_r58_noti_select_includes_payment_type(self):
        """routers/payment.py /inicis/noti SELECT must include payment_type."""
        import pathlib
        router_src = (
            pathlib.Path(__file__).parent.parent / "routers" / "payment.py"
        ).read_text()
        # Find the inicis_noti SELECT block
        noti_idx = router_src.find("inicis_noti")
        assert noti_idx != -1
        noti_block = router_src[noti_idx: noti_idx + 800]
        assert "payment_type" in noti_block, (
            "/inicis/noti SELECT projection must include payment_type"
        )
