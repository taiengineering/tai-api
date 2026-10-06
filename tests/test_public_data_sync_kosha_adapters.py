"""WP-1C-A — KOSHA adapter tests.

A01~A10: common (registry / register_builtin_adapters)
S01~S18: KoshaSafetyMaterialAdapter
G01~G13: KoshaGuideAdapter

No real API calls. No production DB writes. All adapters use DI stubs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from services.public_data_sync.adapters import (
    AdapterRegistry,
    SourceAdapter,
    adapter_registry,
    register_builtin_adapters,
)
from services.public_data_sync.adapters.kosha_guide import KoshaGuideAdapter
from services.public_data_sync.adapters.kosha_safety_material import KoshaSafetyMaterialAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus, TriggerKind
from services.public_data_sync.errors import PreflightError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_SM = "KOSHA_SAFETY_MATERIAL"
_SOURCE_GD = "KOSHA_GUIDE"


def _ctx(source_id: str = _SOURCE_SM, dry_run: bool = False) -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id=source_id,
        trigger=TriggerKind.MANUAL,
        dry_run=dry_run,
        started_at=datetime.now(timezone.utc),
    )


def _sm_adapter(daily_fn=None, dry_run_fn=None) -> KoshaSafetyMaterialAdapter:
    return KoshaSafetyMaterialAdapter(daily_fn=daily_fn, dry_run_fn=dry_run_fn)


def _guide_adapter(sync_fn=None) -> KoshaGuideAdapter:
    return KoshaGuideAdapter(sync_fn=sync_fn)


@dataclass
class _GuideSyncResult:
    status: str
    declared: int = 0
    fetched: int = 0
    unique: int = 0
    hold_count: int = 0
    membership: int = 0
    snapshot_hash: str | None = None
    snapshot_id: str | None = None
    catalog_upserted: int = 0
    business_dml: int = 0
    failure_reason: str | None = None


def _sm_report(final_status: str, snapshot_result: str | None = None, failure_code: str | None = None) -> tuple[dict, int]:
    return {
        "final_status": final_status,
        "snapshot_result": snapshot_result,
        "failure_code": failure_code,
    }, (0 if final_status == "SUCCESS" else 1)


async def _async_sm_report(*args, **kwargs) -> tuple[dict, int]:
    return _sm_report(*args, **kwargs)


# ---------------------------------------------------------------------------
# A — common / registry
# ---------------------------------------------------------------------------

class TestCommon:
    def setup_method(self):
        # Reset adapter_registry to blank state before each common test
        # by clearing its internal dict directly (tests only, not production)
        adapter_registry._adapters.clear()

    def teardown_method(self):
        adapter_registry._adapters.clear()

    def test_a01_register_builtin_registers_both(self):
        register_builtin_adapters()
        keys = adapter_registry.registered_keys()
        assert "kosha_safety_material" in keys
        assert "kosha_guide" in keys

    def test_a02_register_builtin_idempotent(self):
        register_builtin_adapters()
        register_builtin_adapters()
        keys = adapter_registry.registered_keys()
        assert keys.count("kosha_safety_material") == 1
        assert keys.count("kosha_guide") == 1

    def test_a03_register_builtin_does_not_contaminate_fresh_registry(self):
        fresh = AdapterRegistry()
        register_builtin_adapters()
        # fresh must still be empty
        assert fresh.registered_keys() == []

    def test_a04_get_kosha_safety_material_returns_correct_adapter(self):
        register_builtin_adapters()
        adapter = adapter_registry.get("kosha_safety_material")
        assert isinstance(adapter, KoshaSafetyMaterialAdapter)

    def test_a05_get_kosha_guide_returns_correct_adapter(self):
        register_builtin_adapters()
        adapter = adapter_registry.get("kosha_guide")
        assert isinstance(adapter, KoshaGuideAdapter)

    def test_a06_both_adapters_are_source_adapter_subclasses(self):
        assert issubclass(KoshaSafetyMaterialAdapter, SourceAdapter)
        assert issubclass(KoshaGuideAdapter, SourceAdapter)

    def test_a07_sm_adapter_key(self):
        assert KoshaSafetyMaterialAdapter().adapter_key == "kosha_safety_material"

    def test_a08_guide_adapter_key(self):
        assert KoshaGuideAdapter().adapter_key == "kosha_guide"

    def test_a09_sm_adapter_accepts_di_daily_fn(self):
        async def stub():
            return _sm_report("SUCCESS", "COMPLETED")
        adapter = KoshaSafetyMaterialAdapter(daily_fn=stub)
        assert adapter._daily_fn is stub

    def test_a10_guide_adapter_accepts_di_sync_fn(self):
        def stub(**kwargs):
            return _GuideSyncResult(status="COMPLETED")
        adapter = KoshaGuideAdapter(sync_fn=stub)
        assert adapter._sync_fn is stub


# ---------------------------------------------------------------------------
# S — KoshaSafetyMaterialAdapter
# ---------------------------------------------------------------------------

class TestKoshaSafetyMaterial:
    def test_s01_preflight_passes_with_key(self):
        adapter = _sm_adapter()
        ctx = _ctx()
        with patch("services.kosha_safety_material_sync.kosha_service_key", return_value="k"):
            adapter.preflight(ctx)  # must not raise

    def test_s02_preflight_raises_preflight_error_when_key_empty(self):
        adapter = _sm_adapter()
        ctx = _ctx()
        with patch("services.kosha_safety_material_sync.kosha_service_key", return_value=""):
            with pytest.raises(PreflightError):
                adapter.preflight(ctx)

    def test_s03_run_dry_run_returns_skipped(self):
        async def dry_stub():
            return {"status": "DRY_RUN", "dry_run": True}

        adapter = _sm_adapter(dry_run_fn=dry_stub)
        ctx = _ctx(dry_run=True)
        result = adapter.run(ctx)
        assert result.status == RunStatus.SKIPPED

    def test_s04_run_success_completed_returns_success(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.SUCCESS

    def test_s05_run_success_snapshot_no_change_returns_no_change(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "SNAPSHOT_NO_CHANGE")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.NO_CHANGE

    def test_s06_run_network_preflight_fail_returns_failed(self):
        async def daily_stub():
            return _sm_report("NETWORK_PREFLIGHT_FAIL", failure_code="AUTH")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s07_run_snapshot_failed_returns_failed(self):
        async def daily_stub():
            return _sm_report("SNAPSHOT_FAILED", failure_code="FETCH_ERROR")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s08_run_no_completed_snapshot_returns_failed(self):
        async def daily_stub():
            return _sm_report("NO_COMPLETED_SNAPSHOT")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s09_run_detail_stop_returns_failed(self):
        async def daily_stub():
            return _sm_report("DETAIL_STOP", failure_code="SNAPSHOT_INVALID")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s10_run_storage_stop_returns_failed(self):
        async def daily_stub():
            return _sm_report("STORAGE_STOP", failure_code="R2_MUTATION_FORBIDDEN")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s11_run_consistency_fail_returns_failed(self):
        async def daily_stub():
            return _sm_report("CONSISTENCY_FAIL", failure_code="STATS_SNAPSHOT_MISMATCH")

        adapter = _sm_adapter(daily_fn=daily_stub)
        result = adapter.run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s12_run_result_has_correct_run_id_and_source_id(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED")

        ctx = _ctx()
        result = _sm_adapter(daily_fn=daily_stub).run(ctx)
        assert result.run_id == ctx.run_id
        assert result.source_id == ctx.source_id

    def test_s13_run_report_in_details_no_service_key(self):
        async def daily_stub():
            report, code = _sm_report("SUCCESS", "COMPLETED")
            report["service_key"] = "should-be-redacted"
            return report, code

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        # RunResult.__post_init__ sanitizes details — service_key must be redacted
        assert result.details.get("service_key") == "***"

    def test_s14_async_bridge_loop_present_returns_failed(self):
        adapter = _sm_adapter()

        async def _inner():
            return adapter.run(_ctx())

        result = asyncio.run(_inner())
        assert result.status == RunStatus.FAILED
        assert result.error_code == "ASYNC_CONTEXT_UNSUPPORTED"

    def test_s15_failure_code_propagated_to_error_code(self):
        async def daily_stub():
            return _sm_report("NETWORK_PREFLIGHT_FAIL", failure_code="AUTH")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.error_code == "AUTH"

    def test_s16_final_status_propagated_to_error_message_on_fail(self):
        async def daily_stub():
            return _sm_report("CONSISTENCY_FAIL")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.error_message == "CONSISTENCY_FAIL"

    def test_s17_dry_run_report_in_details(self):
        async def dry_stub():
            return {"status": "DRY_RUN", "catalog_inserts_planned": 5}

        result = _sm_adapter(dry_run_fn=dry_stub).run(_ctx(dry_run=True))
        assert result.status == RunStatus.SKIPPED
        assert result.details.get("catalog_inserts_planned") == 5

    def test_s18_daily_fn_exception_returns_failed(self):
        async def daily_stub():
            raise RuntimeError("upstream exploded")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED
        assert result.error_code == "DAILY_FN_EXCEPTION"
        assert "RuntimeError" in (result.error_message or "")


# ---------------------------------------------------------------------------
# G — KoshaGuideAdapter
# ---------------------------------------------------------------------------

class TestKoshaGuide:
    def test_g01_preflight_passes_with_key(self):
        adapter = _guide_adapter()
        ctx = _ctx(_SOURCE_GD)
        with patch("services.kosha_safety_material_sync.kosha_service_key", return_value="k"):
            adapter.preflight(ctx)  # must not raise

    def test_g02_preflight_raises_preflight_error_when_key_empty(self):
        adapter = _guide_adapter()
        ctx = _ctx(_SOURCE_GD)
        with patch("services.kosha_safety_material_sync.kosha_service_key", return_value=""):
            with pytest.raises(PreflightError):
                adapter.preflight(ctx)

    def test_g03_completed_maps_to_success(self):
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED", catalog_upserted=10)

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.SUCCESS

    def test_g04_snapshot_no_change_maps_to_no_change(self):
        def stub(**kw):
            return _GuideSyncResult(status="SNAPSHOT_NO_CHANGE")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.NO_CHANGE

    def test_g05_dry_run_maps_to_skipped(self):
        def stub(**kw):
            return _GuideSyncResult(status="DRY_RUN")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD, dry_run=True))
        assert result.status == RunStatus.SKIPPED

    def test_g06_reject_maps_to_failed(self):
        def stub(**kw):
            return _GuideSyncResult(status="REJECT", failure_reason="MEMBERSHIP_WRITE")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED

    def test_g07_failed_maps_to_failed(self):
        def stub(**kw):
            return _GuideSyncResult(status="FAILED", failure_reason="network error")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED

    def test_g08_unknown_status_returns_failed_with_unknown_domain_status(self):
        def stub(**kw):
            return _GuideSyncResult(status="TOTALLY_NEW_STATUS")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED
        assert result.error_code == "UNKNOWN_DOMAIN_STATUS"

    def test_g09_validated_intermediate_state_returns_failed(self):
        def stub(**kw):
            return _GuideSyncResult(status="VALIDATED")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED

    def test_g10_result_has_correct_run_id_and_source_id(self):
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED")

        ctx = _ctx(_SOURCE_GD)
        result = _guide_adapter(sync_fn=stub).run(ctx)
        assert result.run_id == ctx.run_id
        assert result.source_id == ctx.source_id

    def test_g11_catalog_upserted_not_in_created_field(self):
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED", catalog_upserted=42)

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.created == 0
        assert result.details.get("catalog_upserted") == 42

    def test_g12_failure_reason_propagated_to_error_message(self):
        def stub(**kw):
            return _GuideSyncResult(status="REJECT", failure_reason="MEMBERSHIP_MISMATCH")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.error_message == "MEMBERSHIP_MISMATCH"

    def test_g13_sync_fn_exception_returns_failed(self):
        def stub(**kw):
            raise ConnectionError("KOSHA unreachable")

        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED
        assert result.error_code == "SYNC_FN_EXCEPTION"
        assert "ConnectionError" in (result.error_message or "")
