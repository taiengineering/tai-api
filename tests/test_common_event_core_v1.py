"""§90 Common Event Contract v1 — test suite (T1–T20).

Covers the forward contract on business_event:
  * legacy rows remain valid and untouched,
  * v1 rows require a complete, non-placeholder canonical core,
  * lossless outcome mapping only (no fabrication),
  * fail-safe / non-blocking emit preserved,
  * legacy reader compatibility via the read adapter.

The emitter's Supabase client and trace context are stubbed so tests never
touch the network or the database.
"""

import pytest

import watch_engine.emitter as emitter_mod
from watch_engine.emitter import emit_event
from watch_engine.validation import validate_contract_v1
from watch_engine.types import EventPayload
from watch_engine import read_adapter, canonical


# ─── Test doubles ───

class _FakeTable:
    def __init__(self, sink):
        self._sink = sink

    def insert(self, row):
        if self._sink.get("raise_on_insert"):
            raise RuntimeError("db down")
        self._sink["row"] = row
        return self

    def execute(self):
        return {"data": []}


class _FakeSupabase:
    def __init__(self, sink):
        self._sink = sink

    def table(self, name):
        self._sink["table"] = name
        return _FakeTable(self._sink)


@pytest.fixture
def sink(monkeypatch):
    s = {}
    monkeypatch.setattr(emitter_mod, "_get_supabase", lambda: _FakeSupabase(s))
    # Avoid ambient contextvar trace leaking into tests.
    monkeypatch.setattr(emitter_mod, "get_current_trace", lambda: None)
    return s


_REAL = dict(
    step_key="submit", step_order=1, event_type="submit",
    service_key="safe", tenant_id="acme", environment="production",
    flow_key="inspection", trace_id="t-123",
)


def _emit(sink, **kw):
    params = dict(_REAL)
    params.update(kw)
    ok = emit_event(**params)
    return ok, sink.get("row")


def _v1_payload(**overrides):
    base = dict(
        tenant_id="acme", environment="production", service_key="safe",
        flow_key="inspection", step_key="submit", step_order=1,
        trace_id="t-123", event_type="submit", result="success",
        event_name="INSPECTION_SUBMITTED", event_version=1,
        occurred_at="2026-01-01T00:00:00+00:00",
        actor_kind="USER", actor_ref="user:abc", outcome=None,
    )
    base.update(overrides)
    return EventPayload(**base)


# ─── T1–T2: shape acceptance ───

def test_t1_legacy_row_accepted(sink):
    ok, row = _emit(sink)
    assert ok is True
    assert "event_version" not in row
    assert row["event_type"] == "submit"
    assert row["result"] == "success"


def test_t2_v1_complete_accepted(sink):
    ok, row = _emit(
        sink, event_name="INSPECTION_SUBMITTED",
        actor_kind="USER", actor_ref="user:abc",
    )
    assert ok is True
    assert row["event_version"] == 1
    assert row["event_name"] == "INSPECTION_SUBMITTED"
    assert row["actor_kind"] == "USER"
    assert row["actor_ref"] == "user:abc"
    assert row["occurred_at"]  # server-derived


# ─── T3–T9: v1 rejection (application mirror of be_contract_v1_chk) ───

def test_t3_v1_missing_event_name_rejected():
    ok, _ = validate_contract_v1(_v1_payload(event_name=None))
    assert ok is False


def test_t4_v1_missing_occurred_at_rejected():
    ok, _ = validate_contract_v1(_v1_payload(occurred_at=None))
    assert ok is False


def test_t5_v1_missing_actor_kind_rejected():
    ok, _ = validate_contract_v1(_v1_payload(actor_kind=None))
    assert ok is False


def test_t6_v1_missing_actor_ref_rejected():
    ok, _ = validate_contract_v1(_v1_payload(actor_ref=None))
    assert ok is False


def test_t7_invalid_actor_kind_rejected():
    ok, _ = validate_contract_v1(_v1_payload(actor_kind="ROBOT"))
    assert ok is False


def test_t8_invalid_outcome_rejected():
    ok, _ = validate_contract_v1(_v1_payload(outcome="MAYBE"))
    assert ok is False


def test_t9_invalid_event_name_rejected():
    # lowercase, single-segment, leading/trailing/double underscore, spaces
    for bad in ("inspection_submitted", "INSPECTION", "_X_Y", "X_Y_", "X__Y", "X Y"):
        assert canonical.is_valid_event_name(bad) is False
    assert validate_contract_v1(_v1_payload(event_name="inspection"))[0] is False


# ─── T10: legacy fields preserved on a v1 row (dual-schema-in-one-row) ───

def test_t10_legacy_fields_preserved_on_v1(sink):
    _, row = _emit(
        sink, event_name="INSPECTION_SUBMITTED",
        actor_kind="USER", actor_ref="user:abc",
    )
    assert row["event_type"] == "submit"
    assert row["result"] == "success"
    assert row["tenant_id"] == "acme"
    assert row["service_key"] == "safe"


# ─── T11–T15: outcome mapping (lossless only) ───

def test_t11_success_maps_success():
    assert canonical.map_outcome("success") == "SUCCESS"


def test_t12_failure_maps_failure():
    assert canonical.map_outcome("failure") == "FAILURE"


def test_t13_skipped_maps_skipped():
    assert canonical.map_outcome("skipped") == "SKIPPED"


def test_t14_timeout_does_not_fabricate_outcome():
    assert canonical.map_outcome("timeout") is None


def test_t15_pending_does_not_fabricate_outcome():
    assert canonical.map_outcome("pending") is None


# ─── T16–T17: fail-safe / non-blocking ───

def test_t16_emit_db_failure_non_blocking(sink):
    sink["raise_on_insert"] = True
    ok = emit_event(**_REAL)  # must not raise
    assert ok is False


def test_t17_canonical_validation_failure_non_blocking(sink):
    # invalid event_name → must not raise, records as legacy, returns True
    ok, row = _emit(
        sink, event_name="bad name", actor_kind="USER", actor_ref="user:abc",
    )
    assert ok is True
    assert "event_version" not in row


# ─── T18: legacy reader compatibility ───

def test_t18_legacy_reader_remains_compatible():
    legacy_row = dict(
        flow_key="inspection", event_type="submit", result="success",
        created_at="2026-01-01T00:00:00+00:00", tenant_id="acme",
        service_key="safe", environment="mock", trace_id="t-1",
    )
    lv = read_adapter.logical_event(legacy_row)
    assert lv["is_contract_v1"] is False
    assert lv["logical_event_name"].startswith("LEGACY:")
    assert lv["logical_actor_kind"] == "LEGACY"
    assert lv["logical_actor_ref"] == "UNKNOWN"
    assert lv["logical_display_time"] == "2026-01-01T00:00:00+00:00"
    assert lv["legacy_event_type"] == "submit"

    v1_row = dict(
        event_name="INSPECTION_SUBMITTED", event_version=1,
        occurred_at="2026-02-02T00:00:00+00:00", actor_kind="USER",
        actor_ref="user:abc", created_at="2026-02-02T00:00:01+00:00",
        flow_key="inspection", event_type="submit", result="success",
        outcome="SUCCESS",
    )
    lp = read_adapter.logical_event(v1_row)
    assert lp["is_contract_v1"] is True
    assert lp["logical_event_name"] == "INSPECTION_SUBMITTED"
    assert lp["logical_display_time"] == "2026-02-02T00:00:00+00:00"


# ─── T19: mock/prod environment preserved verbatim ───

def test_t19_environment_value_preserved(sink):
    _, row = _emit(sink, environment="mock")
    assert row["environment"] == "mock"
    sink.clear()
    _, row = _emit(sink, environment="production")
    assert row["environment"] == "production"


# ─── T20: placeholder trace cannot become v1 ───

def test_t20_placeholder_trace_cannot_become_v1(sink):
    ok, row = _emit(
        sink, trace_id="no_trace", event_name="X_Y",
        actor_kind="SYSTEM", actor_ref="system:sched",
    )
    assert ok is True
    assert "event_version" not in row
    # canonical builder also refuses at the source
    core, errs = canonical.build_contract_core(
        event_name="X_Y", actor_kind="SYSTEM", actor_ref="system:sched",
        trace_id="no_trace", service_key="safe", tenant_id="acme",
        environment="mock",
    )
    assert core is None
    assert any("trace_id" in e for e in errs)
