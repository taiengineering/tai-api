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
    RuntimeHeartbeatError,
    SourceNotFoundError,
)
from services.public_data_sync.heartbeat import HeartbeatSupervisor
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
    """Infrastructure exceptions must not expose raw message (potential secrets) anywhere."""
    import logging
    import traceback
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    secret_value = "SUPER_SECRET_123"

    # --- claim path ---
    sb_claim = _fake_sb()
    store_claim = PublicDataRuntimeStore(supabase_client=sb_claim)

    def _raise_claim(*args, **kwargs):
        raise RuntimeError(f"Authorization: Bearer {secret_value}")

    store_claim.claim_run = _raise_claim

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    exc_claim = None
    with caplog.at_level(logging.ERROR, logger="services.public_data_sync.runtime"):
        with pytest.raises(RuntimeClaimError) as exc_info:
            execute_due_source(_SOURCE_ID, store=store_claim, trigger=TriggerKind.MANUAL)
        exc_claim = exc_info.value

    for record in caplog.records:
        assert secret_value not in record.getMessage(), \
            f"Claim secret in log: {record.getMessage()!r}"
    assert secret_value not in str(exc_claim), \
        "Claim secret in RuntimeClaimError message"
    tb_str = "".join(traceback.format_exception(type(exc_claim), exc_claim, exc_claim.__traceback__))
    assert secret_value not in tb_str, \
        "Claim secret in traceback (raw exc chain not suppressed)"

    caplog.clear()

    # --- complete path ---
    sb_complete = _fake_sb()
    store_complete = PublicDataRuntimeStore(supabase_client=sb_complete)

    def _raise_complete(*args, **kwargs):
        raise RuntimeError(f"Authorization: Bearer {secret_value}")

    store_complete.complete_run = _raise_complete

    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    exc_complete = None
    with caplog.at_level(logging.ERROR, logger="services.public_data_sync.runtime"):
        with pytest.raises(RuntimeCompletionError) as exc_info:
            execute_due_source(_SOURCE_ID, store=store_complete, trigger=TriggerKind.MANUAL)
        exc_complete = exc_info.value

    for record in caplog.records:
        assert secret_value not in record.getMessage(), \
            f"Complete secret in log: {record.getMessage()!r}"
    assert secret_value not in str(exc_complete), \
        "Complete secret in RuntimeCompletionError message"
    tb_str = "".join(traceback.format_exception(type(exc_complete), exc_complete, exc_complete.__traceback__))
    assert secret_value not in tb_str, \
        "Complete secret in traceback (raw exc chain not suppressed)"


# ---------------------------------------------------------------------------
# P28~P34 — Normal claim rejections (allowlist) → None
# P35~P39 — Invariant/unexpected claim rejections → RuntimeClaimError
# ---------------------------------------------------------------------------

def test_p28_to_p34_normal_claim_rejections_return_none(monkeypatch):
    """All allowlisted business rejection reasons must return None without raising."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    normal_reasons = [
        "DISABLED",               # P28
        "NOT_DUE",                # P29
        "RETRY_NOT_BEFORE",       # P30
        "SOURCE_BUSY",            # P31
        "CREDENTIAL_BUSY",        # P32
        "RATE_LIMIT_BUSY",        # P33
        "SOURCE_LIMIT_UNSUPPORTED",  # P34
    ]
    for reason in normal_reasons:
        sb = _fake_sb(claim_data={"claimed": False, "run_id": str(uuid4()), "reason": reason})
        store = PublicDataRuntimeStore(supabase_client=sb)

        reg = AdapterRegistry()
        reg.register(_OkAdapter(spec.adapter_key))
        monkeypatch.setattr(runner_module, "adapter_registry", reg)

        result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
        assert result is None, f"Normal reason {reason!r} must return None, not raise"


def test_p35_to_p39_invariant_claim_rejections_raise(monkeypatch):
    """DB invariant violations and unknown reasons must raise RuntimeClaimError with reason."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    invariant_reasons = [
        "UNKNOWN_SOURCE_RUNTIME",  # P35 — Registry/DB seed mismatch
        "RUN_ID_CONFLICT",         # P36 — UUID collision in sync_runs PK
        "UNIQUE_CONFLICT",         # P37 — Unexpected DB invariant violation
        "DEADLOCK_RETRY",          # P38 — Deadlock; no retry engine in this WP
        "SOME_FUTURE_REASON",      # P39 — Unknown reason not yet in allowlist
    ]
    for reason in invariant_reasons:
        sb = _fake_sb(claim_data={"claimed": False, "run_id": str(uuid4()), "reason": reason})
        store = PublicDataRuntimeStore(supabase_client=sb)

        reg = AdapterRegistry()
        reg.register(_OkAdapter(spec.adapter_key))
        monkeypatch.setattr(runner_module, "adapter_registry", reg)

        with pytest.raises(RuntimeClaimError) as exc_info:
            execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
        assert exc_info.value.reason == reason, \
            f"RuntimeClaimError.reason must carry the DB contract code: {reason!r}"


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
# M23~M28 — Migration static tests for heartbeat lease guard migration
# ---------------------------------------------------------------------------

_HEARTBEAT_GUARD_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "supabase", "migrations",
    "20261006180546_public_data_heartbeat_lease_guard.sql",
)


@pytest.fixture(scope="module")
def heartbeat_guard_sql():
    with open(_HEARTBEAT_GUARD_MIGRATION_PATH) as f:
        return f.read()


def _guard_fn_body(sql: str) -> str:
    block = sql[sql.index("fn_public_data_heartbeat_run"):]
    return block[: block.index("$fn$;")]


def test_m23_guard_migration_file_exists():
    assert os.path.exists(_HEARTBEAT_GUARD_MIGRATION_PATH), \
        "heartbeat guard migration file must exist"


def test_m24_guard_migration_contains_create_or_replace(heartbeat_guard_sql):
    assert "CREATE OR REPLACE FUNCTION public.fn_public_data_heartbeat_run" in heartbeat_guard_sql


def test_m25_guard_migration_lease_until_is_not_null(heartbeat_guard_sql):
    body = _guard_fn_body(heartbeat_guard_sql)
    assert "lease_until" in body and "IS NOT NULL" in body, \
        "heartbeat guard must check lease_until IS NOT NULL"


def test_m26_guard_migration_lease_until_gt_p_now(heartbeat_guard_sql):
    body = _guard_fn_body(heartbeat_guard_sql)
    assert "lease_until" in body and "> p_now" in body, \
        "heartbeat guard must check lease_until > p_now"


def test_m27_guard_migration_security_invoker(heartbeat_guard_sql):
    body = _guard_fn_body(heartbeat_guard_sql)
    assert "SECURITY INVOKER" in body


def test_m28_guard_migration_service_role_grant(heartbeat_guard_sql):
    assert "TO service_role" in heartbeat_guard_sql


# ---------------------------------------------------------------------------
# H01~H11 — HeartbeatSupervisor and orchestrator heartbeat integration tests
# ---------------------------------------------------------------------------

def _make_supervisor(
    *,
    heartbeat_fn=None,
    lease_seconds: int = 30,
    interval: int = 1,
) -> HeartbeatSupervisor:
    """Build a HeartbeatSupervisor with a stub store factory."""
    calls = []

    class _StubStore:
        def heartbeat(self, run_id, *, lease_seconds=900):
            return heartbeat_fn(run_id) if heartbeat_fn else True

    return HeartbeatSupervisor(
        run_id=str(uuid4()),
        source_id="KOSHA_ACCIDENT_CASES",
        store_factory=_StubStore,
        lease_seconds=lease_seconds,
        heartbeat_interval_seconds=interval,
    )


def test_h01_supervisor_starts_daemon_thread():
    sv = _make_supervisor(interval=60)
    sv.start()
    assert sv._thread is not None
    assert sv._thread.daemon is True
    sv.stop()


def test_h02_supervisor_sends_heartbeat():
    import time
    beat_count = []

    def _hb(run_id):
        beat_count.append(1)
        return True

    sv = _make_supervisor(heartbeat_fn=_hb, lease_seconds=3, interval=1)
    sv.start()
    time.sleep(2.5)
    sv.stop()
    assert len(beat_count) >= 1, "supervisor must call heartbeat at least once"


def test_h03_supervisor_stops_cleanly():
    import time
    sv = _make_supervisor(interval=60)
    sv.start()
    sv.stop(timeout=2.0)
    assert not sv._thread.is_alive(), "thread must stop after stop() called"


def test_h04_heartbeat_false_sets_lease_lost():
    import time

    def _hb(run_id):
        return False

    sv = _make_supervisor(heartbeat_fn=_hb, lease_seconds=3, interval=1)
    sv.start()
    time.sleep(2.0)
    sv.stop()
    assert sv.failed_reason == "LEASE_LOST"


def test_h05_heartbeat_exception_sets_infra_error():
    import time

    def _hb(run_id):
        raise RuntimeError("DB connection lost")

    sv = _make_supervisor(heartbeat_fn=_hb, lease_seconds=3, interval=1)
    sv.start()
    time.sleep(2.0)
    sv.stop()
    assert sv.failed_reason == "HEARTBEAT_INFRA_ERROR"


def test_h06_successful_heartbeat_failed_reason_none():
    import time

    def _hb(run_id):
        return True

    sv = _make_supervisor(heartbeat_fn=_hb, lease_seconds=3, interval=1)
    sv.start()
    time.sleep(0.5)
    sv.stop()
    assert sv.failed_reason is None


def test_h07_interval_bounded_to_one_third_lease():
    sv = HeartbeatSupervisor(
        run_id=str(uuid4()),
        source_id="X",
        store_factory=object,
        lease_seconds=30,
        heartbeat_interval_seconds=300,
    )
    assert sv._interval == 10, f"expected 30//3=10, got {sv._interval}"

    sv2 = HeartbeatSupervisor(
        run_id=str(uuid4()),
        source_id="X",
        store_factory=object,
        lease_seconds=30,
        heartbeat_interval_seconds=5,
    )
    assert sv2._interval == 5, f"configured interval 5 < lease//3=10, should use 5"

    sv3 = HeartbeatSupervisor(
        run_id=str(uuid4()),
        source_id="X",
        store_factory=object,
        lease_seconds=2,
        heartbeat_interval_seconds=300,
    )
    assert sv3._interval == 1, f"min bound must be 1, got {sv3._interval}"


def test_h08_lease_lost_heartbeat_raises_runtime_fenced_error(monkeypatch):
    """execute_due_source: LEASE_LOST heartbeat → RuntimeFencedError, complete_run skipped."""
    import services.public_data_sync.runner as runner_module
    import services.public_data_sync.runtime as runtime_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    complete_called = []
    original_complete = store.complete_run
    def _spy_complete(*args, **kwargs):
        complete_called.append(True)
        return original_complete(*args, **kwargs)
    store.complete_run = _spy_complete

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    fake_sv = MagicMock()
    fake_sv.failed_reason = "LEASE_LOST"

    with patch("services.public_data_sync.runtime.HeartbeatSupervisor", return_value=fake_sv):
        with pytest.raises(RuntimeFencedError):
            execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    assert complete_called == [], "complete_run must not be called when LEASE_LOST"


def test_h09_heartbeat_infra_error_raises_runtime_heartbeat_error(monkeypatch):
    """execute_due_source: HEARTBEAT_INFRA_ERROR → RuntimeHeartbeatError, complete_run skipped."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    complete_called = []
    original_complete = store.complete_run
    def _spy_complete(*args, **kwargs):
        complete_called.append(True)
        return original_complete(*args, **kwargs)
    store.complete_run = _spy_complete

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    fake_sv = MagicMock()
    fake_sv.failed_reason = "HEARTBEAT_INFRA_ERROR"

    with patch("services.public_data_sync.runtime.HeartbeatSupervisor", return_value=fake_sv):
        with pytest.raises(RuntimeHeartbeatError) as exc_info:
            execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    assert exc_info.value.reason == "HEARTBEAT_INFRA_ERROR"
    assert complete_called == [], "complete_run must not be called when HEARTBEAT_INFRA_ERROR"


def test_h10_no_heartbeat_failure_complete_run_called(monkeypatch):
    """execute_due_source: no heartbeat failure → complete_run is called normally."""
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    fake_sv = MagicMock()
    fake_sv.failed_reason = None

    with patch("services.public_data_sync.runtime.HeartbeatSupervisor", return_value=fake_sv):
        result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    assert result is not None
    assert result.status == RunStatus.SUCCESS
    complete_calls = [c for c in sb.rpc.call_args_list
                      if c.args[0] == "fn_public_data_complete_run"]
    assert len(complete_calls) == 1


def test_h11_orchestrator_exception_message_no_raw_text(monkeypatch):
    """runtime.py ORCHESTRATOR_EXCEPTION path must not expose raw exception message."""
    spec = _spec()
    sb = _fake_sb()
    store = PublicDataRuntimeStore(supabase_client=sb)

    secret = "Authorization: Bearer secret_token_xyz"

    fake_sv = MagicMock()
    fake_sv.failed_reason = None

    with patch("services.public_data_sync.runtime.HeartbeatSupervisor", return_value=fake_sv):
        with patch(
            "services.public_data_sync.runner.run_source",
            side_effect=RuntimeError(secret),
        ):
            result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)

    assert result is not None
    assert result.status == RunStatus.FAILED
    assert result.error_code == "ORCHESTRATOR_EXCEPTION"
    assert secret not in (result.error_message or ""), \
        "raw exception message must not appear in error_message"
    assert result.error_message == "RuntimeError"


# ---------------------------------------------------------------------------
# SQL tests placeholder
# ---------------------------------------------------------------------------

def test_sql_local_db_unavailable():
    """S01~S18 require local Supabase. Skipped: LOCAL_DB_UNAVAILABLE."""
    pytest.skip("LOCAL_DB_UNAVAILABLE — SQL tests require local Supabase instance")
