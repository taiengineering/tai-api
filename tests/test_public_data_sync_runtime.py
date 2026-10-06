"""WP-1B Runtime Foundation — P01~P15.

SQL tests (S01~S18) require local Supabase DB.
LOCAL_DB_UNAVAILABLE = True in this environment.
"""
from __future__ import annotations

import json
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
from services.public_data_sync.errors import AdapterNotRegisteredError, SourceNotFoundError
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
# P14 — fenced completion (complete_run returns False) does not raise
# ---------------------------------------------------------------------------

def test_p14_fenced_completion_does_not_raise(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = _spec()
    sb = _fake_sb(complete_data=False)  # complete returns False (fenced)
    store = PublicDataRuntimeStore(supabase_client=sb)

    reg = AdapterRegistry()
    reg.register(_OkAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", reg)

    # Should NOT raise even if fenced
    result = execute_due_source(_SOURCE_ID, store=store, trigger=TriggerKind.MANUAL)
    assert result is not None  # result is still returned


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
# SQL tests placeholder
# ---------------------------------------------------------------------------

def test_sql_local_db_unavailable():
    """S01~S18 require local Supabase. Skipped: LOCAL_DB_UNAVAILABLE."""
    pytest.skip("LOCAL_DB_UNAVAILABLE — SQL tests require local Supabase instance")
