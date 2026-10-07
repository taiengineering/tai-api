"""WP-1D Wave1 — KOSHA incremental + Holiday adapter tests.

W1-01~W1-02: _get_last_collected canonical target
W1-03~W1-07: KoshaAPI strict transport
W1-08~W1-10: KoshaIncrementalAdapter (accident_cases)
W1-11~W1-13: KoshaIncrementalAdapter (construction_accidents)
W1-14~W1-16: HolidayAdapter
W1-17~W1-19: registry DAILY policy
W1-20~W1-22: runner integration (builtin lookup)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.public_data_sync.adapters import AdapterRegistry, register_builtin_adapters
from services.public_data_sync.adapters.holiday import HolidayAdapter
from services.public_data_sync.adapters.kosha_incremental import KoshaIncrementalAdapter
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus, TriggerKind
from services.public_data_sync.errors import AdapterNotRegisteredError, PreflightError
from services.public_data_sync.registry import registry


def _ctx(source_id: str = "KOSHA_ACCIDENT_CASES") -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id=source_id,
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# W1-01/02 — canonical log target
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_01_hyphen_accident_maps_to_underscore():
    from routers.kosha_collect import _canonical_log_target
    assert _canonical_log_target("accident-cases") == "accident_cases"


def test_w1_02_hyphen_construction_maps_to_underscore():
    from routers.kosha_collect import _canonical_log_target
    assert _canonical_log_target("construction-accidents") == "construction_accidents"


def test_w1_02b_underscore_passthrough():
    from routers.kosha_collect import _canonical_log_target
    assert _canonical_log_target("accident_cases") == "accident_cases"
    assert _canonical_log_target("construction_accidents") == "construction_accidents"


def test_w1_02c_get_last_collected_uses_canonical(monkeypatch):
    """_get_last_collected('accident-cases') queries with 'accident_cases'."""
    from routers.kosha_collect import _get_last_collected, INIT_DATE

    queried_targets = []

    class _FakeSB:
        def table(self, name):
            return self

        def select(self, *a):
            return self

        def eq(self, col, val):
            if col == "target":
                queried_targets.append(val)
            return self

        def order(self, *a, **kw):
            return self

        def limit(self, *a):
            return self

        def execute(self):
            m = MagicMock()
            m.data = [{"collected_at": "2026-05-01T00:00:00"}]
            return m

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _FakeSB())
    result = _get_last_collected("accident-cases")
    assert result == "2026-05-01"
    assert "accident_cases" in queried_targets
    assert "accident-cases" not in queried_targets


# ─────────────────────────────────────────────────────────────────────────────
# W1-03 — strict=True, network error raises KoshaFetchError
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_03_strict_network_error_raises():
    from routers.kosha_collect import KoshaAPI, KoshaFetchError

    async def _run():
        with patch("routers.kosha_collect.kr_get", side_effect=TimeoutError("timeout")):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                await KoshaAPI.get("some/path", {}, strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "KOSHA_FETCH_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# W1-04 — strict=True, HTTP 500 raises
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_04_strict_http_500_raises():
    from routers.kosha_collect import KoshaAPI, KoshaFetchError

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(500, "server error")):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                await KoshaAPI.get("some/path", {}, strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "KOSHA_HTTP_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# W1-05 — strict=True, resultCode != "00" raises
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_05_strict_result_code_error():
    from routers.kosha_collect import KoshaAPI, KoshaFetchError
    import json

    body = json.dumps({"header": {"resultCode": "99", "resultMsg": "SERVICE_ERROR"}, "body": {"items": [], "totalCount": 0}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, body)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                await KoshaAPI.get("some/path", {}, strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "KOSHA_RESULT_CODE"


# ─────────────────────────────────────────────────────────────────────────────
# W1-06 — strict path, first page empty → SOURCE_EMPTY_UNEXPECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_06_strict_empty_first_page_accident_cases():
    from routers.kosha_collect import KoshaFetchError, _collect_accident_cases
    import json

    empty_resp = json.dumps({"body": {"items": [], "totalCount": 0}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, empty_resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_accident_cases(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


def test_w1_06b_strict_empty_first_page_construction_accidents():
    from routers.kosha_collect import KoshaFetchError, _collect_construction_accidents
    import json

    empty_resp = json.dumps({"body": {"items": [], "totalCount": 0}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, empty_resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_construction_accidents(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


# ─────────────────────────────────────────────────────────────────────────────
# W1-07 — strict=False, network failure → empty dict (backward compat)
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_07_non_strict_network_failure_returns_empty():
    from routers.kosha_collect import KoshaAPI

    async def _run():
        with patch("routers.kosha_collect.kr_get", side_effect=TimeoutError("timeout")):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                return await KoshaAPI.get("some/path", {}, strict=False)

    result = asyncio.run(_run())
    assert result == {"body": {"items": [], "totalCount": 0}}


# ─────────────────────────────────────────────────────────────────────────────
# W1-08~10 — KoshaIncrementalAdapter (accident_cases)
# ─────────────────────────────────────────────────────────────────────────────

def _make_accident_adapter(collect_fn, since_fn=None) -> KoshaIncrementalAdapter:
    return KoshaIncrementalAdapter(
        adapter_key="kosha_accident_cases",
        collect_fn=collect_fn,
        log_target="accident_cases",
        get_since_fn=since_fn,
    )


def test_w1_08_accident_adapter_success():
    async def _collect(**kw):
        return {"upserted": 5, "since": "2026-05-01", "target": "accident_cases"}

    adapter = _make_accident_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx())
    assert result.status == RunStatus.SUCCESS
    assert result.created == 5
    assert result.change_detected is True


def test_w1_09_accident_adapter_no_change():
    async def _collect(**kw):
        return {"upserted": 0, "since": "2026-05-01", "target": "accident_cases"}

    adapter = _make_accident_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx())
    assert result.status == RunStatus.NO_CHANGE
    assert result.change_detected is False


def test_w1_10_accident_adapter_strict_failure():
    from routers.kosha_collect import KoshaFetchError

    async def _collect(**kw):
        raise KoshaFetchError("SOURCE_EMPTY_UNEXPECTED")

    adapter = _make_accident_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx())
    assert result.status == RunStatus.FAILED
    assert result.error_code == "SOURCE_EMPTY_UNEXPECTED"


# ─────────────────────────────────────────────────────────────────────────────
# W1-11~13 — KoshaIncrementalAdapter (construction_accidents)
# ─────────────────────────────────────────────────────────────────────────────

def _make_construction_adapter(collect_fn, since_fn=None) -> KoshaIncrementalAdapter:
    return KoshaIncrementalAdapter(
        adapter_key="kosha_construction_accidents",
        collect_fn=collect_fn,
        log_target="construction_accidents",
        get_since_fn=since_fn,
    )


def test_w1_11_construction_adapter_success():
    async def _collect(**kw):
        return {"upserted": 3, "since": "2026-05-01", "target": "construction_accidents"}

    adapter = _make_construction_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx("KOSHA_CONSTRUCTION_ACCIDENTS"))
    assert result.status == RunStatus.SUCCESS
    assert result.created == 3


def test_w1_12_construction_adapter_no_change():
    async def _collect(**kw):
        return {"upserted": 0, "since": "2026-05-01"}

    adapter = _make_construction_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx("KOSHA_CONSTRUCTION_ACCIDENTS"))
    assert result.status == RunStatus.NO_CHANGE


def test_w1_13_construction_adapter_failure():
    from routers.kosha_collect import KoshaFetchError

    async def _collect(**kw):
        raise KoshaFetchError("KOSHA_HTTP_ERROR")

    adapter = _make_construction_adapter(_collect)
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx("KOSHA_CONSTRUCTION_ACCIDENTS"))
    assert result.status == RunStatus.FAILED
    assert result.error_code == "KOSHA_HTTP_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# W1-14~16 — HolidayAdapter
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_14_holiday_preflight_error_missing_key():
    adapter = HolidayAdapter()
    with patch.dict(os.environ, {}, clear=True):
        if "DATA_GO_KR_SERVICE_KEY" in os.environ:
            del os.environ["DATA_GO_KR_SERVICE_KEY"]
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx("HOLIDAY"))


def test_w1_15_holiday_sync_success():
    sync_result = {
        "results": [
            {"year": 2026, "fetched": 15, "deleted": 14, "inserted": 15},
            {"year": 2027, "fetched": 12, "deleted": 0, "inserted": 12},
        ]
    }

    def _sync():
        return sync_result

    adapter = HolidayAdapter(sync_fn=_sync)
    result = adapter.run(_ctx("HOLIDAY"))
    assert result.status == RunStatus.SUCCESS
    assert result.created == 27
    assert result.fetched == 27


def test_w1_16_holiday_sync_exception_returns_failed():
    def _sync():
        raise RuntimeError("API 403")

    adapter = HolidayAdapter(sync_fn=_sync)
    result = adapter.run(_ctx("HOLIDAY"))
    assert result.status == RunStatus.FAILED
    assert result.error_code == "HOLIDAY_SYNC_FAILED"
    assert result.error_message == "RuntimeError"


# ─────────────────────────────────────────────────────────────────────────────
# W1-17~19 — Registry DAILY policy
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_17_guide_refresh_policy_daily():
    spec = registry.get("KOSHA_GUIDE")
    assert spec.refresh_policy == "DAILY"


def test_w1_18_safety_material_refresh_policy_daily():
    spec = registry.get("KOSHA_SAFETY_MATERIAL")
    assert spec.refresh_policy == "DAILY"


def test_w1_18b_accident_cases_refresh_policy_daily():
    spec = registry.get("KOSHA_ACCIDENT_CASES")
    assert spec.refresh_policy == "DAILY"


def test_w1_18c_construction_accidents_refresh_policy_daily():
    spec = registry.get("KOSHA_CONSTRUCTION_ACCIDENTS")
    assert spec.refresh_policy == "DAILY"


def test_w1_19_holiday_refresh_policy_daily():
    spec = registry.get("HOLIDAY")
    assert spec.refresh_policy == "DAILY"


# ─────────────────────────────────────────────────────────────────────────────
# W1-20~22 — Runner integration (builtin lookup)
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_20_builtin_registry_has_5_adapters():
    reg = AdapterRegistry()
    from services.public_data_sync.adapters.kosha_guide import KoshaGuideAdapter
    from services.public_data_sync.adapters.kosha_safety_material import KoshaSafetyMaterialAdapter
    from services.public_data_sync.adapters.holiday import HolidayAdapter
    from services.public_data_sync.adapters.kosha_incremental import KoshaIncrementalAdapter

    async def _noop(**kw):
        return {"upserted": 0}

    reg.register(KoshaSafetyMaterialAdapter())
    reg.register(KoshaGuideAdapter())
    reg.register(HolidayAdapter())
    reg.register(KoshaIncrementalAdapter("kosha_accident_cases", _noop, "accident_cases"))
    reg.register(KoshaIncrementalAdapter("kosha_construction_accidents", _noop, "construction_accidents"))

    keys = reg.registered_keys()
    assert "kosha_safety_material" in keys
    assert "kosha_guide" in keys
    assert "holiday" in keys
    assert "kosha_accident_cases" in keys
    assert "kosha_construction_accidents" in keys
    assert len(keys) == 5


def test_w1_21_run_source_accident_cases_adapter_lookup():
    """run_source('KOSHA_ACCIDENT_CASES') finds adapter when registered in adapter_registry."""
    from services.public_data_sync.runner import run_source

    async def _noop(**kw):
        return {"upserted": 0}

    test_reg = AdapterRegistry()
    test_reg.register(
        KoshaIncrementalAdapter("kosha_accident_cases", _noop, "accident_cases")
    )

    with patch("services.public_data_sync.runner.adapter_registry", test_reg):
        with patch("services.public_data_sync.runner.register_builtin_adapters"):
            with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
                result = run_source("KOSHA_ACCIDENT_CASES")
    assert result is not None
    assert result.status in (RunStatus.SUCCESS, RunStatus.NO_CHANGE, RunStatus.FAILED)


def test_w1_22_run_source_holiday_adapter_lookup():
    """run_source('HOLIDAY') finds HolidayAdapter when registered."""
    from services.public_data_sync.runner import run_source

    def _noop_sync():
        return {"results": [{"fetched": 10, "inserted": 10}]}

    test_reg = AdapterRegistry()
    test_reg.register(HolidayAdapter(sync_fn=_noop_sync))

    with patch("services.public_data_sync.runner.adapter_registry", test_reg):
        with patch("services.public_data_sync.runner.register_builtin_adapters"):
            with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
                result = run_source("HOLIDAY")
    assert result is not None
    assert result.status == RunStatus.SUCCESS


# ─────────────────────────────────────────────────────────────────────────────
# W1-P01~P09 — PATCH-FAIL-CLOSED-001
# ─────────────────────────────────────────────────────────────────────────────

def test_w1_p01_items_empty_total_nonzero_raises():
    """items=[] but totalCount=2802 on first page → SOURCE_EMPTY_UNEXPECTED (OR guard)."""
    from routers.kosha_collect import KoshaFetchError, _collect_accident_cases
    import json

    resp = json.dumps({"body": {"items": [], "totalCount": 2802}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_accident_cases(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


def test_w1_p02_items_nonempty_total_zero_raises():
    """items=[...] but totalCount=0 on first page → SOURCE_EMPTY_UNEXPECTED (OR guard)."""
    from routers.kosha_collect import KoshaFetchError, _collect_accident_cases
    import json

    item = {"boardNo": "1", "title": "test", "regDt": "20260101", "content": "x"}
    resp = json.dumps({"body": {"items": [item], "totalCount": 0}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_accident_cases(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


def test_w1_p03_construction_items_empty_total_nonzero_raises():
    """Construction: items=[] but totalCount>0 → SOURCE_EMPTY_UNEXPECTED."""
    from routers.kosha_collect import KoshaFetchError, _collect_construction_accidents
    import json

    resp = json.dumps({"body": {"items": [], "totalCount": 1039}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_construction_accidents(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


def test_w1_p04_construction_items_nonempty_total_zero_raises():
    """Construction: items=[...] but totalCount=0 → SOURCE_EMPTY_UNEXPECTED."""
    from routers.kosha_collect import KoshaFetchError, _collect_construction_accidents
    import json

    item = {"seq": "1", "dsstrDt": "20260101"}
    resp = json.dumps({"body": {"items": [item], "totalCount": 0}})

    async def _run():
        with patch("routers.kosha_collect.kr_get", return_value=(200, resp)):
            with patch("routers.kosha_collect._get_service_key", return_value="key"):
                with patch("routers.kosha_collect.get_supabase"):
                    await _collect_construction_accidents(strict=True)

    with pytest.raises(KoshaFetchError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == "SOURCE_EMPTY_UNEXPECTED"


def test_w1_p05_get_last_collected_db_success_row_found(monkeypatch):
    """DB success with row → returns date string."""
    from routers.kosha_collect import _get_last_collected

    class _FakeSB:
        def table(self, name): return self
        def select(self, *a): return self
        def eq(self, *a): return self
        def order(self, *a, **kw): return self
        def limit(self, *a): return self
        def execute(self):
            m = MagicMock()
            m.data = [{"collected_at": "2026-09-15T12:00:00"}]
            return m

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _FakeSB())
    result = _get_last_collected("accident_cases", strict=True)
    assert result == "2026-09-15"


def test_w1_p06_get_last_collected_db_success_no_rows(monkeypatch):
    """DB success but no rows (bootstrap) → returns INIT_DATE even in strict mode."""
    from routers.kosha_collect import _get_last_collected, INIT_DATE

    class _FakeSB:
        def table(self, name): return self
        def select(self, *a): return self
        def eq(self, *a): return self
        def order(self, *a, **kw): return self
        def limit(self, *a): return self
        def execute(self):
            m = MagicMock()
            m.data = []
            return m

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _FakeSB())
    result = _get_last_collected("accident_cases", strict=True)
    assert result == INIT_DATE


def test_w1_p07_get_last_collected_db_raises_strict_true(monkeypatch):
    """DB raises in strict=True → KoshaFetchError(KOSHA_CURSOR_LOOKUP_ERROR)."""
    from routers.kosha_collect import _get_last_collected, KoshaFetchError

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: (_ for _ in ()).throw(RuntimeError("connection refused")))

    with pytest.raises(KoshaFetchError) as exc_info:
        _get_last_collected("accident_cases", strict=True)
    assert exc_info.value.code == "KOSHA_CURSOR_LOOKUP_ERROR"


def test_w1_p08_get_last_collected_db_raises_strict_false(monkeypatch):
    """DB raises in strict=False → returns INIT_DATE (legacy fallback preserved)."""
    from routers.kosha_collect import _get_last_collected, INIT_DATE

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: (_ for _ in ()).throw(RuntimeError("connection refused")))

    result = _get_last_collected("accident_cases", strict=False)
    assert result == INIT_DATE


def test_w1_p09_adapter_cursor_lookup_failure_returns_failed():
    """KoshaIncrementalAdapter: get_since_fn raises KoshaFetchError → RunStatus.FAILED."""
    from routers.kosha_collect import KoshaFetchError

    def _failing_since(target):
        raise KoshaFetchError("KOSHA_CURSOR_LOOKUP_ERROR")

    async def _collect(**kw):
        return {"upserted": 5}

    adapter = KoshaIncrementalAdapter(
        adapter_key="kosha_accident_cases",
        collect_fn=_collect,
        log_target="accident_cases",
        get_since_fn=_failing_since,
    )
    with patch.dict(os.environ, {"DATA_GO_KR_SERVICE_KEY": "key"}):
        result = adapter.run(_ctx())
    assert result.status == RunStatus.FAILED
    assert result.error_code == "KOSHA_CURSOR_LOOKUP_ERROR"
