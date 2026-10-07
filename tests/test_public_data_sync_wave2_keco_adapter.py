"""WP-1D Wave2A — KecoChemicalAdapter tests (K2A-01 ~ K2A-16).

All tests use DI / monkeypatching — zero external API calls.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters
from services.public_data_sync.adapters.keco_chemical import KecoChemicalAdapter
from services.public_data_sync.contracts import RunContext, RunStatus, TriggerKind
from services.public_data_sync.errors import PreflightError
from services.public_data_sync.registry import registry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(source_id: str = "KECO_15149420") -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id=source_id,
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
    )


_GOOD_ENV = {
    "DATA_GO_KR_SERVICE_KEY": "key",
    "LEG_SUPABASE_URL": "https://leg.supabase.co",
    "LEG_SUPABASE_SERVICE_ROLE_KEY": "leg_key",
    "KECO_REQUEST_BUDGET": "9000",
    "KECO_REFRESH_BATCH_SIZE": "3000",
}


@dataclass
class FakeTargetResult:
    stop_batch: bool = False


@dataclass
class FakeDomainResult:
    run_id: str = "domain-run-001"
    run_type: str = "SCHEDULED_REFRESH"
    status: str = "COMPLETED"
    targets_selected: int = 50
    targets_processed: int = 50
    requests: int = 50
    new: int = 0
    changed: int = 0
    unchanged: int = 50
    empty: int = 0
    conflict: int = 0
    retry: int = 0
    failed: int = 0
    source_items: int = 50
    facts_inserted: int = 0
    budget_used: int = 50
    budget_remaining: int = 8950
    results: List[FakeTargetResult] = field(default_factory=list)


def _mock_domain(result: FakeDomainResult):
    return patch(
        "services.public_data_sync.adapters.keco_chemical.KecoChemicalAdapter.run",
        wraps=None,
    )


def _adapter_with_domain(domain_result: FakeDomainResult) -> KecoChemicalAdapter:
    adapter = KecoChemicalAdapter()

    def _patched_run(ctx):
        # Bypass imports — call _map directly with fake result
        return adapter._map(ctx, domain_result)

    adapter.run = _patched_run  # type: ignore[method-assign]
    return adapter


# ─────────────────────────────────────────────────────────────────────────────
# K2A-01 — missing KECO API credential
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_01_missing_keco_credential():
    adapter = KecoChemicalAdapter()
    # Both canonical and legacy must be absent to trigger PreflightError
    env = {k: v for k, v in _GOOD_ENV.items()
           if k not in ("DATA_GO_KR_SERVICE_KEY", "KECO_API_SERVICE_KEY")}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# K2A-02 — missing DB env vars
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_02a_missing_leg_supabase_url():
    adapter = KecoChemicalAdapter()
    env = {k: v for k, v in _GOOD_ENV.items() if k != "LEG_SUPABASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


def test_k2a_02b_missing_leg_service_role_key():
    adapter = KecoChemicalAdapter()
    env = {k: v for k, v in _GOOD_ENV.items() if k != "LEG_SUPABASE_SERVICE_ROLE_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# K2A-03 — missing capacity env vars
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_03a_missing_request_budget():
    adapter = KecoChemicalAdapter()
    env = {k: v for k, v in _GOOD_ENV.items() if k != "KECO_REQUEST_BUDGET"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


def test_k2a_03b_missing_refresh_batch_size():
    adapter = KecoChemicalAdapter()
    env = {k: v for k, v in _GOOD_ENV.items() if k != "KECO_REFRESH_BATCH_SIZE"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# K2A-04 — invalid capacity values
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("budget,batch", [
    ("0", "50"),       # budget <= 0
    ("-100", "50"),    # budget negative
    ("9000", "0"),     # batch <= 0
    ("9000", "-1"),    # batch negative
    ("50", "100"),     # batch > budget
    ("abc", "50"),     # non-integer budget
    ("9000", "xyz"),   # non-integer batch
])
def test_k2a_04_invalid_capacity(budget, batch):
    adapter = KecoChemicalAdapter()
    env = {**_GOOD_ENV, "KECO_REQUEST_BUDGET": budget, "KECO_REFRESH_BATCH_SIZE": batch}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# K2A-05 — domain locked → SKIPPED
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_05_domain_locked_returns_skipped():
    locked_result = FakeDomainResult(run_id="LOCKED", targets_selected=0)
    adapter = _adapter_with_domain(locked_result)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.SKIPPED
    assert result.details.get("domain_status") == "LOCKED"


# ─────────────────────────────────────────────────────────────────────────────
# K2A-06 — no due targets → NO_CHANGE
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_06_no_due_returns_no_change():
    no_due = FakeDomainResult(run_id="real-run-id", targets_selected=0)
    adapter = _adapter_with_domain(no_due)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.NO_CHANGE
    assert result.change_detected is False


# ─────────────────────────────────────────────────────────────────────────────
# K2A-07 — COMPLETED with changes → SUCCESS
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_07_completed_with_changes_returns_success():
    changed = FakeDomainResult(new=10, changed=5, unchanged=35, status="COMPLETED")
    adapter = _adapter_with_domain(changed)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.SUCCESS
    assert result.created == 10
    assert result.changed == 5
    assert result.change_detected is True


# ─────────────────────────────────────────────────────────────────────────────
# K2A-08 — COMPLETED no changes → NO_CHANGE
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_08_completed_no_changes_returns_no_change():
    unchanged = FakeDomainResult(new=0, changed=0, unchanged=50, status="COMPLETED")
    adapter = _adapter_with_domain(unchanged)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.NO_CHANGE
    assert result.change_detected is False


# ─────────────────────────────────────────────────────────────────────────────
# K2A-09 — failed target → PARTIAL / KECO_TARGET_ATTENTION_REQUIRED
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_09_failed_target_returns_partial():
    failed = FakeDomainResult(failed=2, new=5, status="COMPLETED")
    adapter = _adapter_with_domain(failed)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.PARTIAL
    assert result.error_code == "KECO_TARGET_ATTENTION_REQUIRED"
    assert result.failed == 2


# ─────────────────────────────────────────────────────────────────────────────
# K2A-10 — conflict target → PARTIAL / KECO_TARGET_ATTENTION_REQUIRED
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_10_conflict_target_returns_partial():
    conflict = FakeDomainResult(conflict=1, new=3, status="COMPLETED")
    adapter = _adapter_with_domain(conflict)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.PARTIAL
    assert result.error_code == "KECO_TARGET_ATTENTION_REQUIRED"
    assert result.failed == 1  # failed = failed + conflict


# ─────────────────────────────────────────────────────────────────────────────
# K2A-11 — retry required (non-budget) → PARTIAL / KECO_TARGET_RETRY_REQUIRED
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_11_retry_required_returns_partial():
    retry = FakeDomainResult(retry=3, status="COMPLETED", budget_remaining=1000)
    adapter = _adapter_with_domain(retry)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.PARTIAL
    assert result.error_code == "KECO_TARGET_RETRY_REQUIRED"


# ─────────────────────────────────────────────────────────────────────────────
# K2A-12 — bounded budget partial (budget_remaining=0) → SUCCESS
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_12_bounded_budget_partial_returns_success():
    bounded = FakeDomainResult(
        status="PARTIAL",
        budget_remaining=0,
        failed=0,
        conflict=0,
        retry=2,
        new=20,
        changed=10,
    )
    adapter = _adapter_with_domain(bounded)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.SUCCESS
    assert result.details.get("bounded_partial") is True


# ─────────────────────────────────────────────────────────────────────────────
# K2A-13 — stop_batch signal → SUCCESS (bounded)
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_13_stop_batch_partial_returns_success():
    stop = FakeDomainResult(
        status="PARTIAL",
        budget_remaining=500,  # not zero — but stop_batch=True
        failed=0,
        conflict=0,
        new=15,
        results=[FakeTargetResult(stop_batch=True)],
    )
    adapter = _adapter_with_domain(stop)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.SUCCESS
    assert result.details.get("bounded_partial") is True


# ─────────────────────────────────────────────────────────────────────────────
# K2A-14 — exception sanitization
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_14_exception_sanitizes_secret():
    adapter = KecoChemicalAdapter()

    def _raise(*a, **kw):
        raise RuntimeError("KECO_API_SERVICE_KEY=SUPER_SECRET_VALUE request failed")

    with patch.dict(os.environ, _GOOD_ENV, clear=True):
        with patch("services.public_data_sync.adapters.keco_chemical.KecoChemicalAdapter.run",
                   side_effect=_raise):
            # Test _fail output directly
            ctx = _ctx()
            result = adapter._fail(ctx, "KECO_REFRESH_EXCEPTION", "RuntimeError")
    assert result.status == RunStatus.FAILED
    assert result.error_code == "KECO_REFRESH_EXCEPTION"
    assert result.error_message == "RuntimeError"
    assert "SECRET" not in (result.error_message or "")

    # Also verify domain exception path via direct patching of lazy import
    adapter2 = KecoChemicalAdapter()
    with patch.dict(os.environ, _GOOD_ENV, clear=True):
        with patch("services.keco_chemical.client.KecoChemicalClient",
                   side_effect=RuntimeError("KECO_API_SERVICE_KEY=SUPER_SECRET")):
            result2 = adapter2.run(_ctx())
    assert result2.status == RunStatus.FAILED
    assert result2.error_code == "KECO_REFRESH_EXCEPTION"
    assert result2.error_message == "RuntimeError"
    assert "SUPER_SECRET" not in (result2.error_message or "")


# ─────────────────────────────────────────────────────────────────────────────
# K2A-15 — builtin lookup (run_source adapter not missing)
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_15_builtin_lookup_not_missing():
    from services.public_data_sync.errors import AdapterNotRegisteredError

    test_reg = AdapterRegistry()
    with patch("services.public_data_sync.adapters.adapter_registry", test_reg):
        register_builtin_adapters()

    keys = test_reg.registered_keys()
    assert "keco_chemical" in keys

    # Confirm it does not raise AdapterNotRegisteredError
    try:
        test_reg.get("keco_chemical")
        found = True
    except AdapterNotRegisteredError:
        found = False
    assert found is True


# ─────────────────────────────────────────────────────────────────────────────
# K2A-16 — registry checks
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_16_registry_refresh_policy_daily():
    spec = registry.get("KECO_15149420")
    assert spec.refresh_policy == "DAILY"


def test_k2a_16b_registry_max_run_seconds():
    spec = registry.get("KECO_15149420")
    assert spec.max_run_seconds == 7200


def test_k2a_16c_registry_sync_mode_and_pool():
    from services.public_data_sync.contracts import SourceMode
    spec = registry.get("KECO_15149420")
    assert spec.sync_mode == SourceMode.TARGET_REFRESH
    assert spec.credential_pool == "DATA_GO_KR"
    assert spec.rate_limit_group == "KECO"
    assert spec.auto_refresh_candidate is True


# ─────────────────────────────────────────────────────────────────────────────
# K2A extra — unknown domain status → FAILED
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_unknown_status_returns_failed():
    unknown = FakeDomainResult(status="WEIRD_STATUS")
    adapter = _adapter_with_domain(unknown)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.FAILED
    assert result.error_code == "KECO_UNKNOWN_DOMAIN_STATUS"


# ─────────────────────────────────────────────────────────────────────────────
# K2A extra — preflight passes with all required env vars
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_preflight_passes_with_valid_env():
    adapter = KecoChemicalAdapter()
    with patch.dict(os.environ, _GOOD_ENV, clear=True):
        adapter.preflight(_ctx())  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# K2A extra — failed > 0 takes priority over bounded partial
# ─────────────────────────────────────────────────────────────────────────────

def test_k2a_failed_priority_over_bounded_partial():
    """failed>0 takes priority even when budget_remaining=0."""
    mixed = FakeDomainResult(
        status="PARTIAL",
        budget_remaining=0,
        failed=1,
        conflict=0,
    )
    adapter = _adapter_with_domain(mixed)
    result = adapter.run(_ctx())
    assert result.status == RunStatus.PARTIAL
    assert result.error_code == "KECO_TARGET_ATTENTION_REQUIRED"
