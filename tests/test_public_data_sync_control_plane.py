"""WP-1A PATCH — Control Plane Foundation T01~T35 + census regression."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

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
    _sanitize_value,
    _redact_string,
)
from services.public_data_sync.errors import (
    AdapterNotRegisteredError,
    PreflightError,
    SourceNotFoundError,
)
from services.public_data_sync.registry import SourceRegistry, registry
from services.public_data_sync.runner import run_source

_EXPECTED_SOURCE_IDS = {
    "KOSHA_SAFETY_MATERIAL",
    "KOSHA_GUIDE",
    "KOSHA_MSDS",
    "KECO_15149420",
    "KOSHA_ACCIDENT_CASES",
    "KOSHA_CONSTRUCTION_ACCIDENTS",
    "KOSHA_CONSTRUCTION_SAFETY_LIGHT",
    "KOSHA_RISK_ASSESSMENT",
    "CSI_ACCIDENT",
    "KCSC",
    "INDUSTRIAL_ACCIDENT_PRECEDENT",
    "HOLIDAY",
}


# ---------------------------------------------------------------------------
# Fake adapters
# ---------------------------------------------------------------------------

class _OkAdapter(SourceAdapter):
    def __init__(self, adapter_key: str, rows: int = 5) -> None:
        self._adapter_key = adapter_key
        self._rows = rows

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        now = datetime.now(timezone.utc)
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.SUCCESS,
            started_at=ctx.started_at,
            finished_at=now,
            fetched=self._rows,
            created=self._rows,
        )


class _NoChangeAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        now = datetime.now(timezone.utc)
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.NO_CHANGE,
            started_at=ctx.started_at,
            finished_at=now,
        )


class _PartialAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        now = datetime.now(timezone.utc)
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            status=RunStatus.PARTIAL,
            started_at=ctx.started_at,
            finished_at=now,
            fetched=10,
            created=7,
            failed=3,
        )


class _PreflightFailAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def preflight(self, ctx: RunContext) -> None:
        raise PreflightError("missing credential")

    def run(self, ctx: RunContext) -> RunResult:  # pragma: no cover
        raise AssertionError("run must not be called after preflight failure")


class _RunRaisesAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        raise RuntimeError("network down")


class _WrongSourceIdAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        now = datetime.now(timezone.utc)
        return RunResult(
            run_id=ctx.run_id,
            source_id="WRONG_SOURCE_ID",
            status=RunStatus.SUCCESS,
            started_at=ctx.started_at,
            finished_at=now,
        )


class _WrongRunIdAdapter(SourceAdapter):
    def __init__(self, adapter_key: str) -> None:
        self._adapter_key = adapter_key

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        now = datetime.now(timezone.utc)
        return RunResult(
            run_id="WRONG-RUN-ID-00000000",
            source_id=ctx.source_id,
            status=RunStatus.SUCCESS,
            started_at=ctx.started_at,
            finished_at=now,
        )


def _make_runner_registry(adapter: SourceAdapter) -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(adapter)
    return reg


# ---------------------------------------------------------------------------
# T01 — SourceMode exact values
# ---------------------------------------------------------------------------

def test_t01_source_mode_exact():
    expected = {
        "FULL_SNAPSHOT", "INCREMENTAL", "ENUMERATE_HYDRATE", "TARGET_REFRESH",
        "FILE_SNAPSHOT", "LIVE_PROXY", "LIVE_CONTEXT", "LOOKUP",
        "LOOKUP_PERSIST_ON_ACTION", "DISCOVERY",
    }
    assert {m.value for m in SourceMode} == expected


# ---------------------------------------------------------------------------
# T02 — SourceKind exact values
# ---------------------------------------------------------------------------

def test_t02_source_kind_exact():
    assert {k.value for k in SourceKind} == {"API", "FILE", "EDGE", "INTERNAL"}


# ---------------------------------------------------------------------------
# T03 — TriggerKind exact values
# ---------------------------------------------------------------------------

def test_t03_trigger_kind_exact():
    assert {t.value for t in TriggerKind} == {"SCHEDULED", "MANUAL", "RETRY"}


# ---------------------------------------------------------------------------
# T04 — RunStatus exact values
# ---------------------------------------------------------------------------

def test_t04_run_status_exact():
    assert {s.value for s in RunStatus} == {"SUCCESS", "NO_CHANGE", "PARTIAL", "FAILED", "SKIPPED"}


# ---------------------------------------------------------------------------
# T05 — SourceSpec is frozen (immutable)
# ---------------------------------------------------------------------------

def test_t05_source_spec_frozen():
    spec = registry.get("HOLIDAY")
    with pytest.raises((AttributeError, TypeError)):
        spec.source_id = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T06 — SourceSpec contract fields present
# ---------------------------------------------------------------------------

def test_t06_source_spec_required_fields():
    spec = registry.get("HOLIDAY")
    for attr in (
        "source_id", "provider", "dataset_id", "source_kind", "sync_mode",
        "adapter_key", "credential_pool", "rate_limit_group", "refresh_policy",
        "max_concurrency", "max_requests_per_run", "max_run_seconds",
        "persisted", "auto_refresh_candidate", "consumer_tags",
    ):
        assert hasattr(spec, attr), f"missing field: {attr}"


# ---------------------------------------------------------------------------
# T07 — credential_pool and rate_limit_group are independent
# ---------------------------------------------------------------------------

def test_t07_credential_pool_rate_limit_group_independent():
    keco = registry.get("KECO_15149420")
    assert keco.credential_pool == "DATA_GO_KR"
    assert keco.rate_limit_group == "KECO"
    assert keco.credential_pool != keco.rate_limit_group


# ---------------------------------------------------------------------------
# T08 — Registry contains exactly the 12 approved source IDs
# ---------------------------------------------------------------------------

def test_t08_registry_exact_12_source_ids():
    reg = SourceRegistry()
    actual = {s.source_id for s in reg.list_all()}
    assert actual == _EXPECTED_SOURCE_IDS
    assert len(reg.list_all()) == 12


# ---------------------------------------------------------------------------
# T09 — LEGAL_TEXT_SYNC absent
# ---------------------------------------------------------------------------

def test_t09_legal_text_sync_absent():
    reg = SourceRegistry()
    ids = {s.source_id for s in reg.list_all()}
    assert "LEGAL_TEXT_SYNC" not in ids
    with pytest.raises(SourceNotFoundError):
        reg.get("LEGAL_TEXT_SYNC")


# ---------------------------------------------------------------------------
# T10 — KSIC_SYNC absent
# ---------------------------------------------------------------------------

def test_t10_ksic_sync_absent():
    reg = SourceRegistry()
    ids = {s.source_id for s in reg.list_all()}
    assert "KSIC_SYNC" not in ids
    with pytest.raises(SourceNotFoundError):
        reg.get("KSIC_SYNC")


# ---------------------------------------------------------------------------
# T11 — KOSHA_GUIDE present
# ---------------------------------------------------------------------------

def test_t11_kosha_guide_present():
    spec = registry.get("KOSHA_GUIDE")
    assert spec.sync_mode == SourceMode.FULL_SNAPSHOT
    assert spec.source_kind == SourceKind.API
    assert spec.auto_refresh_candidate is True


# ---------------------------------------------------------------------------
# T12 — KOSHA_CONSTRUCTION_ACCIDENTS present
# ---------------------------------------------------------------------------

def test_t12_kosha_construction_accidents_present():
    spec = registry.get("KOSHA_CONSTRUCTION_ACCIDENTS")
    assert spec.sync_mode == SourceMode.INCREMENTAL
    assert spec.source_kind == SourceKind.API
    assert spec.auto_refresh_candidate is True


# ---------------------------------------------------------------------------
# T13 — CSI_ACCIDENT is FILE / FILE_SNAPSHOT
# ---------------------------------------------------------------------------

def test_t13_csi_accident_file_snapshot():
    spec = registry.get("CSI_ACCIDENT")
    assert spec.sync_mode == SourceMode.FILE_SNAPSHOT
    assert spec.source_kind == SourceKind.FILE


# ---------------------------------------------------------------------------
# T14 — KOSHA_ACCIDENT_CASES is INCREMENTAL
# ---------------------------------------------------------------------------

def test_t14_kosha_accident_cases_incremental():
    spec = registry.get("KOSHA_ACCIDENT_CASES")
    assert spec.sync_mode == SourceMode.INCREMENTAL
    assert spec.source_kind == SourceKind.API


# ---------------------------------------------------------------------------
# T15 — KOSHA_RISK_ASSESSMENT is INCREMENTAL + auto_refresh_candidate=False
# ---------------------------------------------------------------------------

def test_t15_kosha_risk_assessment_incremental_candidate_false():
    spec = registry.get("KOSHA_RISK_ASSESSMENT")
    assert spec.sync_mode == SourceMode.INCREMENTAL
    assert spec.auto_refresh_candidate is False


# ---------------------------------------------------------------------------
# T16 — KOSHA_CONSTRUCTION_SAFETY_LIGHT auto_refresh_candidate=False
# ---------------------------------------------------------------------------

def test_t16_s07_candidate_false():
    spec = registry.get("KOSHA_CONSTRUCTION_SAFETY_LIGHT")
    assert spec.auto_refresh_candidate is False


# ---------------------------------------------------------------------------
# T17 — KECO_15149420 TARGET_REFRESH + DATA_GO_KR shared pool
# ---------------------------------------------------------------------------

def test_t17_keco_target_refresh():
    spec = registry.get("KECO_15149420")
    assert spec.sync_mode == SourceMode.TARGET_REFRESH
    assert spec.credential_pool == "DATA_GO_KR"
    assert spec.rate_limit_group == "KECO"
    assert spec.source_kind == SourceKind.API


# ---------------------------------------------------------------------------
# T18 — INDUSTRIAL_ACCIDENT_PRECEDENT is EDGE
# ---------------------------------------------------------------------------

def test_t18_industrial_accident_precedent_edge():
    spec = registry.get("INDUSTRIAL_ACCIDENT_PRECEDENT")
    assert spec.source_kind == SourceKind.EDGE
    assert spec.sync_mode == SourceMode.INCREMENTAL


# ---------------------------------------------------------------------------
# T19 — AdapterRegistry instances are isolated (no shared module global)
# ---------------------------------------------------------------------------

def test_t19_adapter_registry_instances_isolated():
    reg_a = AdapterRegistry()
    reg_b = AdapterRegistry()
    reg_a.register(_OkAdapter("key_a"))
    assert "key_a" in reg_a.registered_keys()
    with pytest.raises(AdapterNotRegisteredError):
        reg_b.get("key_a")


# ---------------------------------------------------------------------------
# T20 — adapter_key lookup separation (SourceSpec.adapter_key ≠ source_id path)
# ---------------------------------------------------------------------------

def test_t20_adapter_key_lookup_separation(monkeypatch):
    import services.public_data_sync.runner as runner_module

    # KOSHA_GUIDE has adapter_key="kosha_guide", not "KOSHA_GUIDE"
    spec = registry.get("KOSHA_GUIDE")
    assert spec.adapter_key == "kosha_guide"
    assert spec.adapter_key != spec.source_id

    fresh_reg = _make_runner_registry(_OkAdapter("kosha_guide", rows=3))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_GUIDE")
    assert result.status == RunStatus.SUCCESS
    assert result.fetched == 3


# ---------------------------------------------------------------------------
# T21 — missing adapter raises AdapterNotRegisteredError (fail-closed)
# ---------------------------------------------------------------------------

def test_t21_missing_adapter_raises(monkeypatch):
    import services.public_data_sync.runner as runner_module

    monkeypatch.setattr(runner_module, "adapter_registry", AdapterRegistry())
    with pytest.raises(AdapterNotRegisteredError):
        run_source("HOLIDAY")


# ---------------------------------------------------------------------------
# T22 — preflight failure → FAILED RunResult
# ---------------------------------------------------------------------------

def test_t22_preflight_failure_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_PreflightFailAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.error_code == "PREFLIGHT_ERROR"
    assert result.source_id == "KOSHA_ACCIDENT_CASES"


# ---------------------------------------------------------------------------
# T23 — adapter.run raises exception → FAILED RunResult
# ---------------------------------------------------------------------------

def test_t23_adapter_run_exception_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_RunRaisesAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.error_code == "EXECUTE_EXCEPTION"


# ---------------------------------------------------------------------------
# T24 — run_id mismatch → FAILED
# ---------------------------------------------------------------------------

def test_t24_run_id_mismatch_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_WrongRunIdAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.error_code == "RUN_ID_MISMATCH"


# ---------------------------------------------------------------------------
# T25 — source_id mismatch → FAILED
# ---------------------------------------------------------------------------

def test_t25_source_id_mismatch_returns_failed(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_WrongSourceIdAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.FAILED
    assert result.error_code == "SOURCE_ID_MISMATCH"


# ---------------------------------------------------------------------------
# T26 — NO_CHANGE status preserved through runner
# ---------------------------------------------------------------------------

def test_t26_no_change_preserved(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_NoChangeAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.NO_CHANGE


# ---------------------------------------------------------------------------
# T27 — PARTIAL status preserved through runner
# ---------------------------------------------------------------------------

def test_t27_partial_preserved(monkeypatch):
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    fresh_reg = _make_runner_registry(_PartialAdapter(spec.adapter_key))
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    result = run_source("KOSHA_ACCIDENT_CASES")
    assert result.status == RunStatus.PARTIAL
    assert result.created == 7
    assert result.failed == 3


# ---------------------------------------------------------------------------
# T28 — nested dict/list/tuple secret sanitization
# ---------------------------------------------------------------------------

def test_t28_nested_secret_sanitization():
    result = RunResult(
        run_id="r1",
        source_id="S",
        status=RunStatus.SUCCESS,
        details={
            "top_key": "safe",
            "serviceKey": "REAL_TOP_KEY",
            "nested": {
                "token": "SECRET_TOKEN",
                "safe_field": "visible",
            },
            "list_data": [
                {"password": "LIST_PW"},
                "plain_string",
                42,
            ],
            "tuple_field": ({"secret": "TUPLE_SECRET"}, "safe_elem"),
        },
    )
    assert result.details["serviceKey"] == "***"
    assert result.details["top_key"] == "safe"
    assert result.details["nested"]["token"] == "***"
    assert result.details["nested"]["safe_field"] == "visible"
    assert result.details["list_data"][0]["password"] == "***"
    assert result.details["list_data"][1] == "plain_string"
    assert result.details["list_data"][2] == 42
    assert result.details["tuple_field"][0]["secret"] == "***"
    assert result.details["tuple_field"][1] == "safe_elem"


# ---------------------------------------------------------------------------
# T29 — error_message secret sanitization
# ---------------------------------------------------------------------------

def test_t29_error_message_sanitization():
    result = RunResult(
        run_id="r1",
        source_id="S",
        status=RunStatus.FAILED,
        error_message="request failed: serviceKey=REALKEY123 status=404",
    )
    assert "REALKEY123" not in result.error_message
    assert "serviceKey=***" in result.error_message


# ---------------------------------------------------------------------------
# T30 — existing census regression
# ---------------------------------------------------------------------------

def test_t30_census_regression():
    from services.public_data_sync.census import (
        CensusDiff,
        CensusError,
        diff_identity_maps,
        validate_identity_census,
    )

    ids = validate_identity_census(["A", "B", "C"], total_count=3)
    assert ids == ("A", "B", "C")

    diff = diff_identity_maps(
        previous={"A": "v1", "B": "v1"},
        current={"A": "v2", "C": "v1"},
    )
    assert diff.new == ("C",)
    assert diff.changed == ("A",)
    assert diff.removed == ("B",)
    assert diff.unchanged == ()
    assert set(diff.hydration_identities) == {"A", "C"}

    with pytest.raises(CensusError) as exc_info:
        validate_identity_census(["A", "A"], total_count=2)
    assert exc_info.value.code == "DUPLICATE_IDENTITY"


# ---------------------------------------------------------------------------
# Bonus — run_source unknown source raises SourceNotFoundError
# ---------------------------------------------------------------------------

def test_run_source_unknown_source_raises():
    with pytest.raises(SourceNotFoundError):
        run_source("TOTALLY_UNKNOWN_XYZ_9999")


# ===========================================================================
# T31~T35 — Secret logging / sanitizer PATCH
# ===========================================================================


class _SecretPreflightAdapter(SourceAdapter):
    def __init__(self, adapter_key: str, secret_msg: str) -> None:
        self._adapter_key = adapter_key
        self._secret_msg = secret_msg

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def preflight(self, ctx: RunContext) -> None:
        raise PreflightError(self._secret_msg)

    def run(self, ctx: RunContext) -> RunResult:  # pragma: no cover
        raise AssertionError("run must not be called after preflight failure")


class _SecretRunAdapter(SourceAdapter):
    def __init__(self, adapter_key: str, exc: Exception) -> None:
        self._adapter_key = adapter_key
        self._exc = exc

    @property
    def adapter_key(self) -> str:
        return self._adapter_key

    def run(self, ctx: RunContext) -> RunResult:
        raise self._exc


# ---------------------------------------------------------------------------
# T31 — preflight exception: secret absent from logs AND RunResult
# ---------------------------------------------------------------------------

def test_t31_preflight_exception_log_secret_absence(monkeypatch, caplog):
    import logging
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    secret_val = "TOP_SECRET_123"
    fresh_reg = _make_runner_registry(
        _SecretPreflightAdapter(spec.adapter_key, f"serviceKey={secret_val}")
    )
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    with caplog.at_level(logging.DEBUG):
        result = run_source("KOSHA_ACCIDENT_CASES")

    assert secret_val not in caplog.text, "secret leaked into log"
    assert result.error_message is not None
    assert secret_val not in result.error_message, "secret leaked into error_message"


# ---------------------------------------------------------------------------
# T32 — adapter.run exception: Bearer token absent from logs AND RunResult
# ---------------------------------------------------------------------------

def test_t32_adapter_run_exception_bearer_log_absence(monkeypatch, caplog):
    import logging
    import services.public_data_sync.runner as runner_module

    spec = registry.get("KOSHA_ACCIDENT_CASES")
    bearer_token = "REAL_BEARER_TOKEN_456"
    fresh_reg = _make_runner_registry(
        _SecretRunAdapter(
            spec.adapter_key,
            RuntimeError(f"HTTP 401 Authorization: Bearer {bearer_token}"),
        )
    )
    monkeypatch.setattr(runner_module, "adapter_registry", fresh_reg)

    with caplog.at_level(logging.DEBUG):
        result = run_source("KOSHA_ACCIDENT_CASES")

    assert bearer_token not in caplog.text, "Bearer token leaked into log"
    assert result.error_message is not None
    assert bearer_token not in result.error_message, "Bearer token leaked into error_message"


# ---------------------------------------------------------------------------
# T33 — Authorization Bearer redactor
# ---------------------------------------------------------------------------

def test_t33_authorization_bearer_redaction():
    token = "REAL_TOKEN_789"
    original = f"Authorization: Bearer {token}"
    redacted = _redact_string(original)
    assert token not in redacted, "Bearer token not redacted"
    assert f"Bearer {token}" not in redacted, "Bearer + token not redacted"
    assert "Authorization:" in redacted, "Authorization key should remain"


# ---------------------------------------------------------------------------
# T34 — Authorization Basic redactor
# ---------------------------------------------------------------------------

def test_t34_authorization_basic_redaction():
    credential = "ABCDEF123456"
    original = f"Authorization: Basic {credential}"
    redacted = _redact_string(original)
    assert credential not in redacted, "Basic credential not redacted"
    assert "Authorization:" in redacted, "Authorization key should remain"


# ---------------------------------------------------------------------------
# T35 — existing secret key patterns regression
# ---------------------------------------------------------------------------

def test_t35_existing_secret_regression():
    cases = [
        ("serviceKey=SKEY123", "SKEY123"),
        ("apikey=AKEY456", "AKEY456"),
        ("service_key=SKVAL", "SKVAL"),
        ("token=TOKVAL", "TOKVAL"),
        ("password=PWVAL", "PWVAL"),
        ("secret=SECVAL", "SECVAL"),
        ("credential=CREDVAL", "CREDVAL"),
    ]
    for original, secret_val in cases:
        redacted = _redact_string(original)
        assert secret_val not in redacted, f"secret not redacted in: {original!r}"

    # nested dict/list/tuple via RunResult
    result = RunResult(
        run_id="r1",
        source_id="S",
        status=RunStatus.SUCCESS,
        details={
            "serviceKey": "TOP",
            "nested": {"token": "NESTED_TOK"},
            "list": [{"password": "LIST_PW"}],
            "tup": ({"secret": "TUP_SEC"},),
        },
    )
    assert result.details["serviceKey"] == "***"
    assert result.details["nested"]["token"] == "***"
    assert result.details["list"][0]["password"] == "***"
    assert result.details["tup"][0]["secret"] == "***"
