"""WP-1C-A — KOSHA adapter tests (PATCH-001).

A01~A13: common (registry / register_builtin_adapters / runner bootstrap)
S01~S28: KoshaSafetyMaterialAdapter
G01~G20: KoshaGuideAdapter
C01~C03: composition / CLI SoT

No real API calls. No production DB writes. All adapters use DI stubs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
from services.public_data_sync.runner import run_source

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


def _sm_report(
    final_status: str,
    snapshot_result: str | None = None,
    failure_code: str | None = None,
    *,
    snapshot_membership: int = 0,
    catalog_new: int = 0,
    snapshot_id: str | None = None,
    snapshot_hash: str | None = None,
    detail_new: int = 0,
    storage_completed: int = 0,
    new_hold_count: int = 0,
) -> tuple[dict, int]:
    return {
        "final_status": final_status,
        "snapshot_result": snapshot_result,
        "failure_code": failure_code,
        "snapshot_membership": snapshot_membership,
        "catalog_new": catalog_new,
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "detail_new": detail_new,
        "storage_completed": storage_completed,
        "new_hold_count": new_hold_count,
    }, (0 if final_status == "SUCCESS" else 1)


def _fake_sm_run(ctx: RunContext) -> RunResult:
    """Return a valid SKIPPED RunResult using ctx IDs (used for runner bootstrap tests)."""
    return RunResult(
        run_id=ctx.run_id,
        source_id=ctx.source_id,
        status=RunStatus.SKIPPED,
        started_at=ctx.started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _fake_gd_run(ctx: RunContext) -> RunResult:
    return RunResult(
        run_id=ctx.run_id,
        source_id=ctx.source_id,
        status=RunStatus.SKIPPED,
        started_at=ctx.started_at,
        finished_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# A — common / registry / runner bootstrap
# ---------------------------------------------------------------------------

class TestCommon:
    def setup_method(self):
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

    def test_a11_runner_auto_bootstraps_builtins(self):
        """run_source() must call register_builtin_adapters() before adapter lookup."""
        adapter_registry._adapters.clear()
        assert "kosha_guide" not in adapter_registry.registered_keys()

        with patch.object(KoshaGuideAdapter, "run", _fake_gd_run):
            with patch.object(KoshaGuideAdapter, "preflight", lambda *_: None):
                run_source("KOSHA_GUIDE")

        assert "kosha_guide" in adapter_registry.registered_keys()
        assert "kosha_safety_material" in adapter_registry.registered_keys()

    def test_a12_run_source_resolves_kosha_sm_without_manual_bootstrap(self):
        """Caller never calls register_builtin_adapters() — run_source still works."""
        adapter_registry._adapters.clear()

        with patch.object(KoshaSafetyMaterialAdapter, "run", _fake_sm_run):
            with patch.object(KoshaSafetyMaterialAdapter, "preflight", lambda *_: None):
                result = run_source("KOSHA_SAFETY_MATERIAL")

        assert result is not None
        assert result.status != RunStatus.FAILED or result.error_code != "ADAPTER_NOT_REGISTERED"

    def test_a13_repeated_run_source_does_not_duplicate_registry(self):
        """Multiple run_source() calls must not create duplicate registry entries."""
        adapter_registry._adapters.clear()

        with patch.object(KoshaGuideAdapter, "run", _fake_gd_run):
            with patch.object(KoshaGuideAdapter, "preflight", lambda *_: None):
                run_source("KOSHA_GUIDE")
                run_source("KOSHA_GUIDE")

        assert adapter_registry.registered_keys().count("kosha_guide") == 1
        assert adapter_registry.registered_keys().count("kosha_safety_material") == 1


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

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.SUCCESS

    def test_s05_run_success_snapshot_no_change_all_zero_returns_no_change(self):
        """SNAPSHOT_NO_CHANGE with zero writes → NO_CHANGE."""
        async def daily_stub():
            return _sm_report(
                "SUCCESS", "SNAPSHOT_NO_CHANGE",
                detail_new=0, storage_completed=0, new_hold_count=0,
            )

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.NO_CHANGE

    def test_s06_run_network_preflight_fail_returns_failed(self):
        async def daily_stub():
            return _sm_report("NETWORK_PREFLIGHT_FAIL", failure_code="AUTH")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s07_run_snapshot_failed_returns_failed(self):
        async def daily_stub():
            return _sm_report("SNAPSHOT_FAILED", failure_code="FETCH_ERROR")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s08_run_no_completed_snapshot_returns_failed(self):
        async def daily_stub():
            return _sm_report("NO_COMPLETED_SNAPSHOT")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s09_run_detail_stop_returns_failed(self):
        async def daily_stub():
            return _sm_report("DETAIL_STOP", failure_code="SNAPSHOT_INVALID")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s10_run_storage_stop_returns_failed(self):
        async def daily_stub():
            return _sm_report("STORAGE_STOP", failure_code="R2_MUTATION_FORBIDDEN")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s11_run_consistency_fail_returns_failed(self):
        async def daily_stub():
            return _sm_report("CONSISTENCY_FAIL", failure_code="STATS_SNAPSHOT_MISMATCH")

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.FAILED

    def test_s12_run_result_has_correct_run_id_and_source_id(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED")

        ctx = _ctx()
        result = _sm_adapter(daily_fn=daily_stub).run(ctx)
        assert result.run_id == ctx.run_id
        assert result.source_id == ctx.source_id

    def test_s13_allowlist_prevents_service_key_from_leaking(self):
        """service_key is not in the allowlist — it must not appear in details at all."""
        async def daily_stub():
            report, code = _sm_report("SUCCESS", "COMPLETED")
            report["service_key"] = "should-be-excluded"
            return report, code

        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert "service_key" not in result.details

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

    # ------------------------------------------------------------------
    # S19-S23 — NO_CHANGE semantic
    # ------------------------------------------------------------------

    def test_s19_no_change_requires_all_three_counters_zero(self):
        """SNAPSHOT_NO_CHANGE + all counters zero → NO_CHANGE, change_detected=False."""
        async def daily_stub():
            return _sm_report(
                "SUCCESS", "SNAPSHOT_NO_CHANGE",
                detail_new=0, storage_completed=0, new_hold_count=0,
            )
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.NO_CHANGE
        assert result.change_detected is False

    def test_s20_snapshot_no_change_but_detail_new_positive_returns_success(self):
        """SNAPSHOT_NO_CHANGE + detail_new > 0 → SUCCESS, change_detected=True."""
        async def daily_stub():
            return _sm_report(
                "SUCCESS", "SNAPSHOT_NO_CHANGE",
                detail_new=5, storage_completed=0, new_hold_count=0,
            )
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.SUCCESS
        assert result.change_detected is True

    def test_s21_snapshot_no_change_but_storage_completed_positive_returns_success(self):
        """SNAPSHOT_NO_CHANGE + storage_completed > 0 → SUCCESS, change_detected=True."""
        async def daily_stub():
            return _sm_report(
                "SUCCESS", "SNAPSHOT_NO_CHANGE",
                detail_new=0, storage_completed=3, new_hold_count=0,
            )
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.SUCCESS
        assert result.change_detected is True

    def test_s22_snapshot_no_change_but_new_hold_count_positive_returns_success(self):
        """SNAPSHOT_NO_CHANGE + new_hold_count > 0 → SUCCESS, change_detected=True."""
        async def daily_stub():
            return _sm_report(
                "SUCCESS", "SNAPSHOT_NO_CHANGE",
                detail_new=0, storage_completed=0, new_hold_count=1,
            )
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.SUCCESS
        assert result.change_detected is True

    def test_s23_completed_returns_success_with_change_detected(self):
        """snapshot_result=COMPLETED → SUCCESS, change_detected=True."""
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED")
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.status == RunStatus.SUCCESS
        assert result.change_detected is True

    # ------------------------------------------------------------------
    # S24-S27 — RunResult evidence mapping
    # ------------------------------------------------------------------

    def test_s24_snapshot_membership_mapped_to_fetched(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED", snapshot_membership=42)
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.fetched == 42

    def test_s25_catalog_new_mapped_to_created(self):
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED", catalog_new=7)
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.created == 7

    def test_s26_snapshot_id_mapped_to_source_version(self):
        sid = str(uuid4())
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED", snapshot_id=sid)
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.source_version == sid

    def test_s27_snapshot_hash_mapped_to_content_hash(self):
        h = "abc123"
        async def daily_stub():
            return _sm_report("SUCCESS", "COMPLETED", snapshot_hash=h)
        result = _sm_adapter(daily_fn=daily_stub).run(_ctx())
        assert result.content_hash == h

    # ------------------------------------------------------------------
    # S28 — secret-safe exception
    # ------------------------------------------------------------------

    def test_s28_daily_fn_exception_with_secret_does_not_leak(self):
        SECRET = "Authorization: Bearer SUPER_SECRET_123"

        async def leaky_stub():
            raise RuntimeError(SECRET)

        result = _sm_adapter(daily_fn=leaky_stub).run(_ctx())
        assert result.status == RunStatus.FAILED
        assert "SUPER_SECRET_123" not in (result.error_message or "")
        assert "SUPER_SECRET_123" not in str(result.details)


# ---------------------------------------------------------------------------
# G — KoshaGuideAdapter
# ---------------------------------------------------------------------------

class TestKoshaGuide:
    def test_g01_preflight_passes_with_key(self):
        adapter = _guide_adapter()
        ctx = _ctx(_SOURCE_GD)
        with patch("services.kosha_safety_material_sync.kosha_service_key", return_value="k"):
            adapter.preflight(ctx)

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

    def test_g12_failure_uses_stable_domain_code_not_raw_failure_reason(self):
        """error_message must be domain_status (stable code), not raw failure_reason text."""
        def stub(**kw):
            return _GuideSyncResult(status="REJECT", failure_reason="MEMBERSHIP_MISMATCH")
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.error_message == "REJECT"

    def test_g13_sync_fn_exception_returns_domain_execution_error(self):
        def stub(**kw):
            raise ConnectionError("KOSHA unreachable")
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED
        assert result.error_code == "DOMAIN_EXECUTION_ERROR"
        assert result.error_message == "ConnectionError"

    # ------------------------------------------------------------------
    # G14-G16 — RunResult evidence mapping
    # ------------------------------------------------------------------

    def test_g14_fetched_mapped_from_sync_result(self):
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED", fetched=55)
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.fetched == 55

    def test_g15_snapshot_id_mapped_to_source_version(self):
        sid = str(uuid4())
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED", snapshot_id=sid)
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.source_version == sid

    def test_g16_snapshot_hash_mapped_to_content_hash(self):
        h = "hashval123"
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED", snapshot_hash=h)
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.content_hash == h

    # ------------------------------------------------------------------
    # G17-G19 — change_detected semantics
    # ------------------------------------------------------------------

    def test_g17_completed_sets_change_detected_true(self):
        def stub(**kw):
            return _GuideSyncResult(status="COMPLETED")
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.change_detected is True

    def test_g18_snapshot_no_change_sets_change_detected_false(self):
        def stub(**kw):
            return _GuideSyncResult(status="SNAPSHOT_NO_CHANGE")
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD))
        assert result.change_detected is False

    def test_g19_dry_run_sets_change_detected_false(self):
        def stub(**kw):
            return _GuideSyncResult(status="DRY_RUN")
        result = _guide_adapter(sync_fn=stub).run(_ctx(_SOURCE_GD, dry_run=True))
        assert result.change_detected is False

    # ------------------------------------------------------------------
    # G20 — secret-safe exception
    # ------------------------------------------------------------------

    def test_g20_sync_fn_exception_with_secret_does_not_leak(self):
        SECRET = "Authorization: Bearer SUPER_SECRET_123"

        def leaky_stub(**kw):
            raise RuntimeError(SECRET)

        result = _guide_adapter(sync_fn=leaky_stub).run(_ctx(_SOURCE_GD))
        assert result.status == RunStatus.FAILED
        assert "SUPER_SECRET_123" not in (result.error_message or "")
        assert "SUPER_SECRET_123" not in str(result.details)


# ---------------------------------------------------------------------------
# C — composition / CLI SoT
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "kosha_safety_material_daily_sync.py"
_PRODUCTION_DAILY_PATH = (
    Path(__file__).parents[1]
    / "services" / "kosha_safety_materials" / "production_daily.py"
)


class TestComposition:
    def _script_text(self) -> str:
        return _SCRIPT_PATH.read_text()

    def test_c01_cli_uses_production_daily_helper(self):
        """The CLI must import from production_daily (not duplicate the assembly)."""
        text = self._script_text()
        assert "production_daily" in text

    def test_c02_production_assembly_removed_from_cli(self):
        """_production_sync and _production_storage must not exist in CLI anymore."""
        text = self._script_text()
        assert "_production_sync" not in text
        assert "_production_storage" not in text

    def test_c03_lock_behavior_preserved_in_cli(self):
        """The lock mechanism must still be in the CLI script."""
        text = self._script_text()
        assert "try_acquire_lock" in text
        assert "release_lock" in text
        assert "SKIPPED_LOCKED" in text
