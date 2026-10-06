"""WP-1A Control Plane Foundation — T01~T17."""
from __future__ import annotations

import pytest

from services.public_data_sync.adapters import AdapterRegistry, SourceAdapter, adapter_registry
from services.public_data_sync.contracts import (
    RunContext,
    RunResult,
    RunStatus,
    SourceKind,
    SourceMode,
    SourceSpec,
    TriggerKind,
    _sanitize,
)
from services.public_data_sync.errors import (
    AdapterNotRegisteredError,
    PreflightError,
    SourceNotFoundError,
)
from services.public_data_sync.registry import SourceRegistry, registry
from services.public_data_sync.runner import run_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(**kwargs) -> SourceSpec:
    defaults = dict(
        source_id="TEST_SOURCE",
        display_name="Test Source",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="POOL_A",
        rate_limit_group="GROUP_A",
        consumer_tags=("tag1",),
        auto_refresh_candidate=True,
    )
    defaults.update(kwargs)
    return SourceSpec(**defaults)


class _OkAdapter(SourceAdapter):
    def __init__(self, source_id: str, rows: int = 5) -> None:
        self._source_id = source_id
        self._rows = rows

    @property
    def source_id(self) -> str:
        return self._source_id

    def execute(self, ctx: RunContext) -> RunResult:
        return RunResult(source_id=self._source_id, status=RunStatus.SUCCESS, rows_affected=self._rows)


class _PreflightFailAdapter(SourceAdapter):
    def __init__(self, source_id: str) -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    def preflight(self, ctx: RunContext) -> None:
        raise PreflightError("missing credential")

    def execute(self, ctx: RunContext) -> RunResult:  # pragma: no cover
        return RunResult(source_id=self._source_id, status=RunStatus.SUCCESS)


class _ExecuteRaisesAdapter(SourceAdapter):
    def __init__(self, source_id: str) -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    def execute(self, ctx: RunContext) -> RunResult:
        raise RuntimeError("network down")


class _WrongIdAdapter(SourceAdapter):
    def __init__(self, source_id: str) -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    def execute(self, ctx: RunContext) -> RunResult:
        return RunResult(source_id="WRONG_ID", status=RunStatus.SUCCESS)


# ---------------------------------------------------------------------------
# T01 — SourceSpec is frozen (immutable)
# ---------------------------------------------------------------------------

def test_t01_source_spec_frozen():
    spec = _make_spec()
    with pytest.raises((AttributeError, TypeError)):
        spec.source_id = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T02 — SourceSpec consumer_tags is tuple (hashable)
# ---------------------------------------------------------------------------

def test_t02_consumer_tags_tuple():
    spec = _make_spec(consumer_tags=("a", "b"))
    assert isinstance(spec.consumer_tags, tuple)
    hash(spec)  # must not raise


# ---------------------------------------------------------------------------
# T03 — credential_pool and rate_limit_group are independent fields
# ---------------------------------------------------------------------------

def test_t03_credential_pool_and_rate_limit_group_independent():
    spec = _make_spec(credential_pool="POOL_X", rate_limit_group="GROUP_Y")
    assert spec.credential_pool == "POOL_X"
    assert spec.rate_limit_group == "GROUP_Y"
    assert spec.credential_pool != spec.rate_limit_group


# ---------------------------------------------------------------------------
# T04 — RunResult secret sanitization strips keys matching pattern
# ---------------------------------------------------------------------------

def test_t04_run_result_sanitizes_secrets():
    result = RunResult(
        source_id="S",
        status=RunStatus.SUCCESS,
        detail={
            "serviceKey": "REAL_KEY",
            "apikey": "REAL_KEY2",
            "service_key": "REAL_KEY3",
            "Authorization": "Bearer abc",
            "secret": "shh",
            "token": "tok",
            "password": "pw",
            "credential": "cred",
            "safe_field": "visible",
        },
    )
    assert result.detail["serviceKey"] == "***"
    assert result.detail["apikey"] == "***"
    assert result.detail["service_key"] == "***"
    assert result.detail["Authorization"] == "***"
    assert result.detail["secret"] == "***"
    assert result.detail["token"] == "***"
    assert result.detail["password"] == "***"
    assert result.detail["credential"] == "***"
    assert result.detail["safe_field"] == "visible"


# ---------------------------------------------------------------------------
# T05 — RunResult sanitization does not alter non-secret fields
# ---------------------------------------------------------------------------

def test_t05_run_result_non_secret_unchanged():
    result = RunResult(
        source_id="S",
        status=RunStatus.SUCCESS,
        detail={"rows": 42, "source": "KOSHA", "url": "https://example.com"},
    )
    assert result.detail["rows"] == 42
    assert result.detail["source"] == "KOSHA"
    assert result.detail["url"] == "https://example.com"


# ---------------------------------------------------------------------------
# T06 — SourceRegistry.get raises SourceNotFoundError for unknown id
# ---------------------------------------------------------------------------

def test_t06_source_registry_unknown_raises():
    reg = SourceRegistry()
    with pytest.raises(SourceNotFoundError) as exc_info:
        reg.get("DOES_NOT_EXIST")
    assert exc_info.value.source_id == "DOES_NOT_EXIST"


# ---------------------------------------------------------------------------
# T07 — SourceRegistry contains exactly 12 persisted sources
# ---------------------------------------------------------------------------

def test_t07_registry_has_12_sources():
    reg = SourceRegistry()
    assert len(reg.list_all()) == 12


# ---------------------------------------------------------------------------
# T08 — S07 and S08 have auto_refresh_candidate=False
# ---------------------------------------------------------------------------

def test_t08_s07_s08_auto_refresh_false():
    reg = SourceRegistry()
    s07 = reg.get("KOSHA_CONSTRUCTION_SAFETY_LIGHT")
    s08 = reg.get("KOSHA_RISK_ASSESSMENT")
    assert s07.auto_refresh_candidate is False
    assert s08.auto_refresh_candidate is False


# ---------------------------------------------------------------------------
# T09 — KECO has distinct credential_pool and rate_limit_group
# ---------------------------------------------------------------------------

def test_t09_keco_dedicated_credential_pool():
    reg = SourceRegistry()
    keco = reg.get("KECO_CHEMICAL")
    assert keco.credential_pool == "KECO_DEDICATED"
    assert keco.rate_limit_group == "KECO"
    assert keco.sync_mode == SourceMode.TARGET_REFRESH
    assert keco.source_kind == SourceKind.REST


# ---------------------------------------------------------------------------
# T10 — PRECEDENT source_kind is EDGE
# ---------------------------------------------------------------------------

def test_t10_precedent_source_kind_edge():
    reg = SourceRegistry()
    precedent = reg.get("PRECEDENT_COLLECT")
    assert precedent.source_kind == SourceKind.EDGE


# ---------------------------------------------------------------------------
# T11 — list_auto_refresh_candidates excludes S07 and S08
# ---------------------------------------------------------------------------

def test_t11_auto_refresh_candidates_exclude_s07_s08():
    reg = SourceRegistry()
    candidates = reg.list_auto_refresh_candidates()
    ids = {s.source_id for s in candidates}
    assert "KOSHA_CONSTRUCTION_SAFETY_LIGHT" not in ids
    assert "KOSHA_RISK_ASSESSMENT" not in ids
    assert len(candidates) == 10


# ---------------------------------------------------------------------------
# T12 — AdapterRegistry.get raises AdapterNotRegisteredError for missing adapter
# ---------------------------------------------------------------------------

def test_t12_adapter_registry_missing_raises():
    reg = AdapterRegistry()
    with pytest.raises(AdapterNotRegisteredError) as exc_info:
        reg.get("NO_ADAPTER_HERE")
    assert exc_info.value.source_id == "NO_ADAPTER_HERE"


# ---------------------------------------------------------------------------
# T13 — AdapterRegistry.register and get round-trip
# ---------------------------------------------------------------------------

def test_t13_adapter_registry_register_and_get():
    reg = AdapterRegistry()
    adapter = _OkAdapter("MY_SOURCE")
    reg.register(adapter)
    retrieved = reg.get("MY_SOURCE")
    assert retrieved is adapter


# ---------------------------------------------------------------------------
# T14 — run_source raises SourceNotFoundError for unknown source_id
# ---------------------------------------------------------------------------

def test_t14_run_source_unknown_source_raises(monkeypatch):
    with pytest.raises(SourceNotFoundError):
        run_source("TOTALLY_UNKNOWN_XYZ")


# ---------------------------------------------------------------------------
# T15 — run_source raises AdapterNotRegisteredError when no adapter registered
# ---------------------------------------------------------------------------

def test_t15_run_source_no_adapter_raises(monkeypatch):
    # registry has KOSHA_ACCIDENT_CASES but no adapter is registered for it
    # Use a fresh adapter registry with no entries
    import services.public_data_sync.runner as runner_module
    import services.public_data_sync.adapters as adapters_module

    fresh_reg = AdapterRegistry()
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    with pytest.raises(AdapterNotRegisteredError):
        run_source("KOSHA_ACCIDENT_CASES")


# ---------------------------------------------------------------------------
# T16 — run_source returns FAILED when preflight raises PreflightError
# ---------------------------------------------------------------------------

def test_t16_run_source_preflight_fail_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    fresh_reg = AdapterRegistry()
    fresh_reg.register(_PreflightFailAdapter("KOSHA_ACCIDENT_CASES"))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.source_id == "KOSHA_ACCIDENT_CASES"
    assert "preflight" in (result.error or "")


# ---------------------------------------------------------------------------
# T17 — run_source returns FAILED when adapter.execute raises unexpectedly
# ---------------------------------------------------------------------------

def test_t17_run_source_execute_raises_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    fresh_reg = AdapterRegistry()
    fresh_reg.register(_ExecuteRaisesAdapter("KOSHA_ACCIDENT_CASES"))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.source_id == "KOSHA_ACCIDENT_CASES"
    assert "execute raised" in (result.error or "")


# ---------------------------------------------------------------------------
# Bonus: source_id mismatch in RunResult → FAILED
# ---------------------------------------------------------------------------

def test_run_source_source_id_mismatch_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    fresh_reg = AdapterRegistry()
    fresh_reg.register(_WrongIdAdapter("KOSHA_ACCIDENT_CASES"))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert "mismatch" in (result.error or "")


# ---------------------------------------------------------------------------
# Bonus: successful run returns SUCCESS with rows_affected
# ---------------------------------------------------------------------------

def test_run_source_success(monkeypatch):
    import services.public_data_sync.runner as runner_module

    fresh_reg = AdapterRegistry()
    fresh_reg.register(_OkAdapter("KOSHA_ACCIDENT_CASES", rows=99))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.SUCCESS
    assert result.rows_affected == 99
    assert result.source_id == "KOSHA_ACCIDENT_CASES"
