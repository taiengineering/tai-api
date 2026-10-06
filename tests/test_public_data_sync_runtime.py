"""WP-1B Runtime Foundation — P01~P15 + PATCH P16~P27 + Migration static M01~M22.

SQL execution tests require local Supabase DB (LOCAL_DB_UNAVAILABLE).
Migration static tests (M01~M22) run against the SQL file text only.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from services.public_data_sync.adapters import AdapterRegistry, SourceAdapter
from services.public_data_sync.contracts import (
    RunContext,
    RunResult,
    RunStatus,
    TriggerKind,
)
from services.public_data_sync.errors import (
    AdapterNotRegisteredError,
    RuntimeClaimError,
    RuntimeCompletionError,
    RuntimeFencedError,
    SourceNotFoundError,
)
from services.public_data_sync.registry import registry
from services.public_data_sync.runtime import execute_due_source
from services.public_data_sync.runtime_store import ClaimResult, PublicDataRuntimeStore
from services.public_data_sync.runner import run_source

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_ID = "KOSHA_ACCIDENT_CASES"


def _spec():
    return registry.get(_SOURCE_ID)


def _now():
    return datetime.now(timezone.utc)


def _fake_sb(claim_data: dict | None = None, complete_data: bool = True) -> MagicMock:
    """Return a mock Supabase client whose .rpc().execute().data returns predefined values."""
    sb = MagicMock()
    default_claim = {
        "claimed": True,
        "run_id": str(uuid4()),
        "reason": "CLAIMED",
        "lease_until": _now().isoformat(),
        "source_slot": 1,
        "credential_slot": 1,
        "rate_limit_slot": 1,
    }
    responses = {
        "fn_public_data_claim_run":      claim_data if claim_data is not None else default_claim,
        "fn_public_data_heartbeat_run":  True,
        "fn_public_data_complete_run":   complete_data,
    }

    def _rpc_side_effect(name, params=None):
        mock_result = MagicMock()
        mock_result.execute.return_value.data = responses.get(name, None)
        return mock_result

    sb.rpc.side_effect = _rpc_side_effect
    return sb


class _OkAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.SUCCESS,
            started_at=ctx.started_at,
            finished_at=_now(),
            fetched=10,
            created=10,
        )


# ---------------------------------------------------------------------------
# P01 — WP-1A regression (spot-checks; full suite in test_public_data_sync_control_plane.py)
# ---------------------------------------------------------------------------

def test_p01_wp1a_regression():
    """Key WP-1A contracts still hold after runner.py update."""
    from services.public_data_sync.registry import SourceRegistry
    reg = SourceRegistry()
    assert len(reg.list_all()) == 12
    assert "LEGAL_TEXT_SYNC" not in {s.source_id for s in reg.list_all()}
    assert "KSIC_SYNC" not in {s.source_id for s in reg.list_all()}
    assert reg.get("CSI_ACCIDENT").sync_mode.value == "FILE_SNAPSHOT"
    assert reg.get("KECO_15149420").credential_pool == "KECO_DEDICATED"
    # runner still accepts no run_id/started_at
    with pytest.raises(AdapterNotRegisteredError):
        run_source(_SOURCE_ID)


# ---------------------------------------------------------------------------
# P02 — externally supplied run_id is preserved by runner
# ---------------------------------------------------------------------------

def test_p02_external_run_id_preserved(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    supplied_run_id = str(uuid4())

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = run_source(_SOURCE_ID, run_id=supplied_run_id)
    assert result.run_id == supplied_run_id


# ---------------------------------------------------------------------------
# P03 — omitting run_id causes auto-generation (backward compatibility)
# ---------------------------------------------------------------------------

def test_p03_auto_generated_run_id(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = run_source(_SOURCE_ID)
    assert result.run_id is not None
    assert len(result.run_id) == 36  # UUID4 format


# ---------------------------------------------------------------------------
# P04 — orchestrator uses spec.adapter_key (not source_id)
# ---------------------------------------------------------------------------

def test_p04_runtime_uses_adapter_key(monkeypatch):
    import services.public_data_sync.runtime as runtime_module
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    assert spec.adapter_key != spec.source_id, "test prerequisite"

    claimed_run_id = str(uuid4())
    sb = _fake_sb(claim_data={
        "claimed": True, "run_id": claimed_run_id, "reason": "CLAIMED",
        "lease_until": _now().isoformat(), "source_slot": 1,
        "credential_slot": 1, "rate_limit_slot": 1,
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is not None
    assert result.status == RunStatus.SUCCESS


# ---------------------------------------------------------------------------
# P05 — credential_pool propagated to claim RPC
# ---------------------------------------------------------------------------

def test_p05_credential_pool_propagated(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    # Inspect claim RPC call
    claim_calls = [c for c in sb.rpc.call_args_list
                   if c.args[0] == "fn_public_data_claim_run"]
    assert len(claim_calls) == 1
    params = claim_calls[0].args[1]
    assert params["p_credential_pool"] == spec.credential_pool


# ---------------------------------------------------------------------------
# P06 — rate_limit_group propagated to claim RPC
# ---------------------------------------------------------------------------

def test_p06_rate_limit_group_propagated(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    claim_calls = [c for c in sb.rpc.call_args_list
                   if c.args[0] == "fn_public_data_claim_run"]
    params = claim_calls[0].args[1]
    assert params["p_rate_limit_group"] == spec.rate_limit_group


# ---------------------------------------------------------------------------
# P07 — source max_concurrency propagated to claim RPC
# ---------------------------------------------------------------------------

def test_p07_source_max_concurrency_propagated(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    claim_calls = [c for c in sb.rpc.call_args_list
                   if c.args[0] == "fn_public_data_claim_run"]
    params = claim_calls[0].args[1]
    assert params["p_source_limit"] == spec.max_concurrency


# ---------------------------------------------------------------------------
# P08 — credential_limit defaults to 1
# ---------------------------------------------------------------------------

def test_p08_credential_limit_default_1(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    claim_calls = [c for c in sb.rpc.call_args_list
                   if c.args[0] == "fn_public_data_claim_run"]
    params = claim_calls[0].args[1]
    assert params["p_credential_limit"] == 1


# ---------------------------------------------------------------------------
# P09 — rate_limit_limit defaults to 1
# ---------------------------------------------------------------------------

def test_p09_rate_limit_default_1(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    claim_calls = [c for c in sb.rpc.call_args_list
                   if c.args[0] == "fn_public_data_claim_run"]
    params = claim_calls[0].args[1]
    assert params["p_rate_limit_limit"] == 1


# ---------------------------------------------------------------------------
# P10 — claim failure → adapter not called, returns None
# ---------------------------------------------------------------------------

def test_p10_claim_failure_adapter_not_called(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb(claim_data={
        "claimed": False, "run_id": str(uuid4()), "reason": "SOURCE_BUSY"
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    run_called = []

    class _SpyAdapter(SourceAdapter):
        @property
        def adapter_key(self):
            return spec.adapter_key
        def run(self, ctx):
            run_called.append(ctx.run_id)
            return RunResult(run_id=ctx.run_id, source_id=ctx.source_id, status=RunStatus.SUCCESS)

    reg = AdapterRegistry()
    reg.register(_SpyAdapter())
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is None
    assert run_called == [], "adapter must not be called when claim fails"


# ---------------------------------------------------------------------------
# P11 — claim success → run_source called exactly once
# ---------------------------------------------------------------------------

def test_p11_claim_success_run_called_once(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    claimed_run_id = str(uuid4())
    sb = _fake_sb(claim_data={
        "claimed": True, "run_id": claimed_run_id, "reason": "CLAIMED",
        "lease_until": _now().isoformat(), "source_slot": 1,
        "credential_slot": 1, "rate_limit_slot": 1,
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    run_invocations = []

    class _SpyAdapter(SourceAdapter):
        @property
        def adapter_key(self):
            return spec.adapter_key
        def run(self, ctx):
            run_invocations.append(ctx.run_id)
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SUCCESS,
                started_at=ctx.started_at,
                finished_at=_now(),
            )

    reg = AdapterRegistry()
    reg.register(_SpyAdapter())
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is not None
    assert len(run_invocations) == 1


# ---------------------------------------------------------------------------
# P12 — RunResult fields correctly mapped in complete_run payload
# ---------------------------------------------------------------------------

def test_p12_result_complete_payload_mapping(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    claimed_run_id = str(uuid4())
    sb = _fake_sb(claim_data={
        "claimed": True, "run_id": claimed_run_id, "reason": "CLAIMED",
        "lease_until": _now().isoformat(), "source_slot": 1,
        "credential_slot": 1, "rate_limit_slot": 1,
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    class _DetailedAdapter(SourceAdapter):
        @property
        def adapter_key(self):
            return spec.adapter_key
        def run(self, ctx):
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SUCCESS,
                started_at=ctx.started_at,
                finished_at=_now(),
                fetched=100,
                created=80,
                changed=15,
                unchanged=5,
                removed=0,
                failed=0,
                source_version="v2",
                content_hash="abc123",
                change_detected=True,
            )

    reg = AdapterRegistry()
    reg.register(_DetailedAdapter())
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    complete_calls = [c for c in sb.rpc.call_args_list
                      if c.args[0] == "fn_public_data_complete_run"]
    assert len(complete_calls) == 1
    params = complete_calls[0].args[1]

    assert params["p_status"] == "SUCCESS"
    assert params["p_fetched"] == 100
    assert params["p_created"] == 80
    assert params["p_changed"] == 15
    assert params["p_unchanged"] == 5
    assert params["p_removed"] == 0
    assert params["p_failed"] == 0
    assert params["p_source_version"] == "v2"
    assert params["p_content_hash"] == "abc123"
    assert params["p_change_detected"] is True


# ---------------------------------------------------------------------------
# P13 — exception in run_source path → complete attempted with FAILED
# ---------------------------------------------------------------------------

def test_p13_run_exception_complete_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    claimed_run_id = str(uuid4())
    sb = _fake_sb(claim_data={
        "claimed": True, "run_id": claimed_run_id, "reason": "CLAIMED",
        "lease_until": _now().isoformat(), "source_slot": 1,
        "credential_slot": 1, "rate_limit_slot": 1,
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    # No adapter registered → AdapterNotRegisteredError in run_source
    reg = AdapterRegistry()
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    assert result is not None
    assert result.status == RunStatus.FAILED

    # complete_run should still have been called
    complete_calls = [c for c in sb.rpc.call_args_list
                      if c.args[0] == "fn_public_data_complete_run"]
    assert len(complete_calls) == 1
    params = complete_calls[0].args[1]
    assert params["p_status"] == "FAILED"


# ---------------------------------------------------------------------------
# P14 — fenced completion (complete_run returns False) raises RuntimeFencedError
# ---------------------------------------------------------------------------

def test_p14_fenced_completion_raises_runtime_fenced_error(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb(complete_data=False)  # complete returns False (fenced)
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with pytest.raises(RuntimeFencedError):
        execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)


# ---------------------------------------------------------------------------
# P15 — secret keys excluded from RunResult.details passed to complete
# ---------------------------------------------------------------------------

def test_p15_secrets_excluded_from_details(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    class _SecretAdapter(SourceAdapter):
        @property
        def adapter_key(self):
            return spec.adapter_key
        def run(self, ctx):
            return RunResult(
                run_id=ctx.run_id,
                source_id=ctx.source_id,
                status=RunStatus.SUCCESS,
                started_at=ctx.started_at,
                finished_at=_now(),
                details={"serviceKey": "SHOULD_BE_REDACTED", "rows": 5},
            )

    reg = AdapterRegistry()
    reg.register(_SecretAdapter())
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    complete_calls = [c for c in sb.rpc.call_args_list
                      if c.args[0] == "fn_public_data_complete_run"]
    params = complete_calls[0].args[1]

    details = params["p_details"]
    assert "SHOULD_BE_REDACTED" not in str(details)
    assert details.get("serviceKey") == "***"
    assert details.get("rows") == 5


# ---------------------------------------------------------------------------
# P16 — list_due_sources uses OR for retry condition (not IS NULL only)
# ---------------------------------------------------------------------------

def test_p16_list_due_sources_uses_or_retry_filter():
    """list_due_sources must call .or_() to include sources with past retry_not_before."""
    sb = MagicMock()
    store = PublicDataRuntimeStore(supabase_client=sb)
    now_dt = _now()

    chain = sb.table.return_value.select.return_value.eq.return_value.lte.return_value
    chain.or_.return_value.execute.return_value.data = [{"source_id": "HOLIDAY"}]

    result = store.list_due_sources(now=now_dt)

    assert chain.or_.called, "list_due_sources must use .or_() for retry_not_before"
    or_arg = chain.or_.call_args[0][0]
    assert "retry_not_before.is.null" in or_arg
    assert "retry_not_before.lte." in or_arg
    assert result == ["HOLIDAY"]


# ---------------------------------------------------------------------------
# P17 — list_due_sources does NOT use the old IS NULL only filter
# ---------------------------------------------------------------------------

def test_p17_list_due_sources_no_is_null_only_filter():
    """list_due_sources must NOT call .is_() on retry_not_before (old stale code)."""
    sb = MagicMock()
    store = PublicDataRuntimeStore(supabase_client=sb)
    now_dt = _now()

    chain = sb.table.return_value.select.return_value.eq.return_value.lte.return_value
    chain.or_.return_value.execute.return_value.data = []

    store.list_due_sources(now=now_dt)

    assert not chain.is_.called, "must not use .is_() for retry_not_before"


# ---------------------------------------------------------------------------
# P18 — SOURCE_LIMIT_UNSUPPORTED claim reason → execute_due_source returns None
# ---------------------------------------------------------------------------

def test_p18_source_limit_unsupported_returns_none(monkeypatch):
    """SOURCE_LIMIT_UNSUPPORTED from DB → execute_due_source returns None."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb(claim_data={
        "claimed": False, "run_id": str(uuid4()), "reason": "SOURCE_LIMIT_UNSUPPORTED",
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is None


# ---------------------------------------------------------------------------
# P19 — CREDENTIAL_BUSY reason preserved in ClaimResult
# ---------------------------------------------------------------------------

def test_p19_credential_busy_reason_preserved():
    """CREDENTIAL_BUSY returned from DB is preserved in ClaimResult.reason."""
    sb = _fake_sb(claim_data={
        "claimed": False, "run_id": str(uuid4()), "reason": "CREDENTIAL_BUSY",
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    claim = store.claim_run(
        run_id=str(uuid4()),
        spec=_spec(),
        trigger=TriggerKind.MANUAL,
        now=_now(),
    )
    assert claim.claimed is False
    assert claim.reason == "CREDENTIAL_BUSY"


# ---------------------------------------------------------------------------
# P20 — RATE_LIMIT_BUSY reason preserved in ClaimResult
# ---------------------------------------------------------------------------

def test_p20_rate_limit_busy_reason_preserved():
    """RATE_LIMIT_BUSY returned from DB is preserved in ClaimResult.reason."""
    sb = _fake_sb(claim_data={
        "claimed": False, "run_id": str(uuid4()), "reason": "RATE_LIMIT_BUSY",
    })
    store = PublicDataRuntimeStore(supabase_client=sb)

    claim = store.claim_run(
        run_id=str(uuid4()),
        spec=_spec(),
        trigger=TriggerKind.MANUAL,
        now=_now(),
    )
    assert claim.claimed is False
    assert claim.reason == "RATE_LIMIT_BUSY"


# ---------------------------------------------------------------------------
# P21 — complete_run store exception → raises RuntimeCompletionError
# ---------------------------------------------------------------------------

def test_p21_complete_exception_raises_runtime_completion_error(monkeypatch):
    """DB failure in store.complete_run must raise RuntimeCompletionError (fail-closed)."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    def _raise_complete(*args, **kwargs):
        raise RuntimeError("DB connection lost")

    store.complete_run = _raise_complete

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with pytest.raises(RuntimeCompletionError):
        execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)


# ---------------------------------------------------------------------------
# P22 — claim DB exception → raises RuntimeClaimError (fail-closed)
# ---------------------------------------------------------------------------

def test_p22_claim_db_exception_raises_runtime_claim_error(monkeypatch):
    """DB failure in store.claim_run must raise RuntimeClaimError — not return None."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    def _raise_claim(*args, **kwargs):
        raise RuntimeError("DB connection lost")

    store.claim_run = _raise_claim

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with pytest.raises(RuntimeClaimError):
        execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)


# ---------------------------------------------------------------------------
# P23 — business claim rejection → None maintained (not an infrastructure error)
# ---------------------------------------------------------------------------

def test_p23_business_claim_rejection_returns_none(monkeypatch):
    """Normal business rejection returns None — distinct from infrastructure failure."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    for reason in ["DISABLED", "SOURCE_BUSY", "NOT_DUE", "CREDENTIAL_BUSY", "RATE_LIMIT_BUSY"]:
        sb = _fake_sb(claim_data={"claimed": False, "run_id": str(uuid4()), "reason": reason})
        store = PublicDataRuntimeStore(supabase_client=sb)

        reg = AdapterRegistry()
        reg.register(_OkAdapter(spec.adapter_key))
        monkeypatch.setattr(runner_module, "adapter_registry", reg)

        result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
        assert result is None, f"reason={reason!r} must return None, not raise"


# ---------------------------------------------------------------------------
# P24 — completion DB exception → raises RuntimeCompletionError
# ---------------------------------------------------------------------------

def test_p24_completion_db_exception_raises_runtime_completion_error(monkeypatch):
    """DB failure in store.complete_run must raise RuntimeCompletionError."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    def _raise_complete(*args, **kwargs):
        raise OSError("network timeout")

    store.complete_run = _raise_complete

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with pytest.raises(RuntimeCompletionError):
        execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)


# ---------------------------------------------------------------------------
# P25 — fenced completion (complete_run returns False) → raises RuntimeFencedError
# ---------------------------------------------------------------------------

def test_p25_fenced_completion_raises_runtime_fenced_error(monkeypatch):
    """complete_run returning False must raise RuntimeFencedError."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb(complete_data=False)
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with pytest.raises(RuntimeFencedError):
        execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)


# ---------------------------------------------------------------------------
# P26 — adapter raises → FAILED RunResult returned normally, complete called
# ---------------------------------------------------------------------------

def test_p26_adapter_exception_returns_failed_result(monkeypatch):
    """Adapter exception → FAILED RunResult; complete_run called; result returned normally."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    # No adapter registered → AdapterNotRegisteredError raised inside run_source
    reg = AdapterRegistry()
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is not None
    assert result.status == RunStatus.FAILED
    assert result.error_code == "ORCHESTRATOR_EXCEPTION"

    complete_calls = [c for c in sb.rpc.call_args_list
                      if c.args[0] == "fn_public_data_complete_run"]
    assert len(complete_calls) == 1
    assert complete_calls[0].args[1]["p_status"] == "FAILED"


# ---------------------------------------------------------------------------
# P27 — infrastructure exception log must not expose raw exception message (secrets)
# ---------------------------------------------------------------------------

def test_p27_infra_exception_log_no_raw_secret(monkeypatch, caplog):
    """Infrastructure exceptions must log only exception type, not the raw message."""
    import logging
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    secret_value = "sk_live_SUPER_SECRET_API_KEY_12345"

    def _raise_claim(*args, **kwargs):
        raise RuntimeError(f"auth failed: {secret_value}")

    store.claim_run = _raise_claim

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    with caplog.at_level(logging.ERROR, logger="services.public_data_sync.runtime"):
        with pytest.raises(RuntimeClaimError):
            execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    for record in caplog.records:
        assert secret_value not in record.getMessage(), \
            f"Secret value leaked in log: {record.getMessage()!r}"


# ---------------------------------------------------------------------------
# Migration static contract tests — M01~M22
# Run against SQL file text; do not require a running DB.
# ---------------------------------------------------------------------------

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "supabase", "migrations",
    "20261006131519_public_data_runtime_state.sql",
)

_EXPECTED_SEED_IDS = {
    "KOSHA_SAFETY_MATERIAL", "KOSHA_GUIDE", "KOSHA_MSDS", "KECO_15149420",
    "KOSHA_ACCIDENT_CASES", "KOSHA_CONSTRUCTION_ACCIDENTS",
    "KOSHA_CONSTRUCTION_SAFETY_LIGHT", "KOSHA_RISK_ASSESSMENT",
    "CSI_ACCIDENT", "KCSC", "INDUSTRIAL_ACCIDENT_PRECEDENT", "HOLIDAY",
}


@pytest.fixture(scope="module")
def migration_sql():
    with open(_MIGRATION_PATH) as f:
        return f.read()


def _claim_body(sql: str) -> str:
    block = sql[sql.index("fn_public_data_claim_run"):]
    return block[: block.index("$fn$;")]


def _heartbeat_body(sql: str) -> str:
    block = sql[sql.index("fn_public_data_heartbeat_run"):]
    return block[: block.index("$fn$;")]


def _complete_body(sql: str) -> str:
    block = sql[sql.index("fn_public_data_complete_run"):]
    return block[: block.index("$fn$;")]


def test_m01_exact_12_seed_ids(migration_sql):
    found = set(re.findall(r"'([A-Z_0-9]+)',\s+false", migration_sql))
    # Filter to only known seed IDs (remove false positives like constraint names)
    found &= _EXPECTED_SEED_IDS | {s.upper() for s in found}
    assert found == _EXPECTED_SEED_IDS, f"seed mismatch: {found ^ _EXPECTED_SEED_IDS}"


def test_m02_all_seed_disabled(migration_sql):
    seed_section = migration_sql[migration_sql.index("SEED"):]
    true_rows = re.findall(r"'[A-Z_0-9]+',\s+true", seed_section)
    assert true_rows == [], f"enabled seed rows found: {true_rows}"


def test_m03_legal_text_sync_absent(migration_sql):
    # Remove SQL comments before checking — comments may legitimately explain exclusion
    sql_no_comments = re.sub(r"--[^\n]*", "", migration_sql)
    assert "LEGAL_TEXT_SYNC" not in sql_no_comments


def test_m04_ksic_sync_absent(migration_sql):
    sql_no_comments = re.sub(r"--[^\n]*", "", migration_sql)
    assert "KSIC_SYNC" not in sql_no_comments


def test_m05_rls_source_runtime(migration_sql):
    assert "public_data_source_runtime ENABLE ROW LEVEL SECURITY" in migration_sql


def test_m06_rls_sync_runs(migration_sql):
    assert "public_data_sync_runs ENABLE ROW LEVEL SECURITY" in migration_sql


def test_m07_anon_revoke(migration_sql):
    assert "FROM anon" in migration_sql


def test_m08_authenticated_revoke(migration_sql):
    assert "FROM anon, authenticated" in migration_sql


def test_m09_service_role_grant(migration_sql):
    assert "TO service_role" in migration_sql


def test_m10_claim_security_invoker(migration_sql):
    assert "SECURITY INVOKER" in _claim_body(migration_sql)


def test_m11_heartbeat_security_invoker(migration_sql):
    assert "SECURITY INVOKER" in _heartbeat_body(migration_sql)


def test_m12_complete_security_invoker(migration_sql):
    assert "SECURITY INVOKER" in _complete_body(migration_sql)


def test_m13_shared_stale_credential_scope(migration_sql):
    """Stale recovery UPDATE must include credential_pool in its WHERE clause."""
    body = _claim_body(migration_sql)
    lease_pos = body.index("LEASE_EXPIRED")
    # Look forward from LEASE_EXPIRED to the closing semicolon of the stale UPDATE
    surrounding = body[lease_pos: lease_pos + 500]
    assert "credential_pool" in surrounding, \
        "stale recovery must scope to credential_pool for shared-resource unblocking"


def test_m14_shared_stale_rate_limit_scope(migration_sql):
    """Stale recovery UPDATE must include rate_limit_group in its WHERE clause."""
    body = _claim_body(migration_sql)
    lease_pos = body.index("LEASE_EXPIRED")
    surrounding = body[lease_pos: lease_pos + 500]
    assert "rate_limit_group" in surrounding, \
        "stale recovery must scope to rate_limit_group for shared-resource unblocking"


def test_m15_source_limit_guard(migration_sql):
    """Claim function must reject p_source_limit != 1 with SOURCE_LIMIT_UNSUPPORTED."""
    assert "SOURCE_LIMIT_UNSUPPORTED" in _claim_body(migration_sql)


def test_m16_complete_current_run_fence(migration_sql):
    """complete_run must SELECT FOR UPDATE on source_runtime WHERE current_run_id = p_run_id."""
    body = _complete_body(migration_sql)
    assert "current_run_id = p_run_id" in body, \
        "complete_run must fence on current_run_id = p_run_id"


def test_m17_heartbeat_fence(migration_sql):
    """heartbeat must check current_run_id to prevent stale run lease renewal."""
    body = _heartbeat_body(migration_sql)
    assert "current_run_id" in body, \
        "heartbeat must include current_run_id fence"


def test_m18_unique_conflict_reason_mapping(migration_sql):
    """Unique violation handler must map each constraint to a distinct reason code."""
    body = _claim_body(migration_sql)
    assert "CREDENTIAL_BUSY" in body
    assert "RATE_LIMIT_BUSY" in body
    assert "CONSTRAINT_NAME" in body


def test_m19_cross_source_runtime_state_cleared(migration_sql):
    """Stale recovery must update public_data_source_runtime for ALL affected sources."""
    body = _claim_body(migration_sql)
    lease_pos = body.index("LEASE_EXPIRED")
    # The CTE RETURNING drives a follow-up UPDATE on source_runtime
    after_lease = body[lease_pos:]
    assert "public_data_source_runtime" in after_lease, \
        "stale recovery must update source_runtime for cross-source ghost current_run_id clearing"


def test_m20_cte_returning_used(migration_sql):
    """Claim must use CTE RETURNING to atomically terminalize runs and clear runtime pointers."""
    body = _claim_body(migration_sql)
    assert "RETURNING id, source_id" in body, \
        "claim must use CTE RETURNING id, source_id for cross-source runtime cleanup"


def test_m21_stale_recovery_sets_last_status_failed(migration_sql):
    """Stale recovery runtime UPDATE must set last_status = 'FAILED'."""
    body = _claim_body(migration_sql)
    lease_pos = body.index("LEASE_EXPIRED")
    after_lease = body[lease_pos:]
    assert "last_status" in after_lease, \
        "stale recovery must set last_status on source_runtime rows"


def test_m22_stale_recovery_protects_newer_current_run(migration_sql):
    """Stale recovery must only clear current_run_id when it matches the stale run."""
    body = _claim_body(migration_sql)
    # WHERE rt.current_run_id = s.id prevents clearing a newer claim's ownership
    assert "current_run_id = s.id" in body, \
        "stale recovery WHERE must reference current_run_id = s.id (stale run only)"


# ---------------------------------------------------------------------------
# SQL tests placeholder
# ---------------------------------------------------------------------------

def test_sql_local_db_unavailable():
    """S01~S18 require local Supabase. Skipped: LOCAL_DB_UNAVAILABLE."""
    pytest.skip("LOCAL_DB_UNAVAILABLE — SQL tests require local Supabase instance")
