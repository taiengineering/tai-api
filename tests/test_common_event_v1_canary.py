"""§91 A-NARROW — mock workflow.completed Common Event v1 canary (C1–C22).

Only (environment == "mock" AND original event_type == "workflow.completed")
is promoted to v1 via the single §90 canonical source. Everything else stays
legacy. A failed canonical request records nothing (no legacy downgrade).
"""

import pytest

from watch_engine.runtime_bus import event_store as store_mod
from watch_engine.runtime_bus.event_store import store_business_event, store_integrity_event
from watch_engine.runtime_bus.runtime_context import RuntimeContext, make_context
from watch_engine import canonical

AWARE = "2026-08-30T07:00:00+00:00"


class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, sink, name):
        self._sink = sink
        self._name = name

    def insert(self, row):
        if self._sink.get("raise_on_insert"):
            raise RuntimeError("db down")
        self._sink.setdefault("inserts", []).append((self._name, row))
        self._sink["row"] = row
        return self

    def execute(self):
        return _Resp([{"id": "evt_1"}])


class _FakeSB:
    def __init__(self, sink):
        self._sink = sink

    def table(self, name):
        self._sink["table"] = name
        return _FakeTable(self._sink, name)


def _ctx(environment="mock", actor_id="synthetic_normal_user", tenant_id="acme"):
    return make_context(runtime="workflow", tenant_id=tenant_id,
                        actor_id=actor_id, environment=environment)


def _evt(event_type="workflow.completed", trace_id="syn_acme_abc12345",
         occurred_at=AWARE, flow_key="login"):
    e = {"event_type": event_type, "flow_key": flow_key, "trace_id": trace_id,
         "severity": "INFO", "tenant_id": "acme", "environment": "mock"}
    if occurred_at is not None:
        e["occurred_at"] = occurred_at
    return e


def _run(ctx, evt, raise_on_insert=False):
    sink = {}
    if raise_on_insert:
        sink["raise_on_insert"] = True
    sb = _FakeSB(sink)
    eid = store_business_event(sb, ctx, evt)
    return eid, sink


# ─── C1–C11: canary happy path ───

def test_c1_mock_workflow_completed_v1_insert():
    eid, sink = _run(_ctx(), _evt())
    assert eid == "evt_1"
    assert sink["row"].get("event_version") == 1


def test_c2_event_version_1():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["event_version"] == 1


def test_c3_event_name_workflow_completed():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["event_name"] == "WORKFLOW_COMPLETED"


def test_c4_legacy_event_type_completed_preserved():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["event_type"] == "completed"


def test_c5_legacy_result_success_preserved():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["result"] == "success"


def test_c6_outcome_success():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["outcome"] == "SUCCESS"


def test_c7_environment_mock():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["environment"] == "mock"


def test_c8_real_syn_trace_preserved():
    _, sink = _run(_ctx(), _evt(trace_id="syn_acme_abc12345"))
    assert sink["row"]["trace_id"] == "syn_acme_abc12345"


def test_c9_actor_kind_system():
    _, sink = _run(_ctx(), _evt())
    assert sink["row"]["actor_kind"] == "SYSTEM"


def test_c10_actor_ref_from_ctx_actor_id():
    _, sink = _run(_ctx(actor_id="synthetic_normal_user"), _evt())
    assert sink["row"]["actor_ref"] == "system:synthetic_normal_user"


def test_c11_occurred_at_tz_aware():
    _, sink = _run(_ctx(), _evt(occurred_at=AWARE))
    assert canonical.is_tz_aware_datetime(sink["row"]["occurred_at"]) is True


# ─── C12–C15: v1-or-nothing (no legacy downgrade) ───

def test_c12_missing_actor_id_no_insert():
    eid, sink = _run(_ctx(actor_id=None), _evt())
    assert eid is None
    assert "row" not in sink  # nothing inserted


def test_c13_placeholder_trace_no_insert():
    eid, sink = _run(_ctx(), _evt(trace_id="no_trace"))
    assert eid is None
    assert "row" not in sink


def test_c14_naive_occurred_at_no_insert():
    eid, sink = _run(_ctx(), _evt(occurred_at="2026-08-30T07:00:00"))  # naive
    assert eid is None
    assert "row" not in sink


def test_c15_canonical_invalid_no_legacy_downgrade():
    # invalid (missing actor_id) must NOT fall back to a legacy row
    eid, sink = _run(_ctx(actor_id=None), _evt())
    assert eid is None
    assert sink.get("inserts") is None


# ─── C16–C19: everything else stays legacy ───

def test_c16_workflow_started_legacy_unchanged():
    _, sink = _run(_ctx(), _evt(event_type="workflow.started", occurred_at=None))
    assert "event_version" not in sink["row"]
    assert sink["row"]["event_type"] == "started"


def test_c17_step_completed_legacy_unchanged():
    # maps to event_type "completed" but is NOT the canary (original != workflow.completed)
    _, sink = _run(_ctx(), _evt(event_type="step.completed", occurred_at=None))
    assert sink["row"]["event_type"] == "completed"
    assert "event_version" not in sink["row"]


def test_c18_workflow_failed_legacy_unchanged():
    _, sink = _run(_ctx(), _evt(event_type="workflow.failed", occurred_at=None))
    assert "event_version" not in sink["row"]
    assert sink["row"]["result"] == "failure"


def test_c19_production_workflow_completed_legacy_unchanged():
    _, sink = _run(_ctx(environment="production"), _evt())
    assert "event_version" not in sink["row"]
    assert sink["row"]["event_type"] == "completed"


# ─── C20–C21: fail-safe / integrity path ───

def test_c20_runtime_bus_failure_no_exception():
    eid, sink = _run(_ctx(), _evt(), raise_on_insert=True)  # must not raise
    assert eid is None


def test_c21_integrity_path_unchanged():
    sink = {}
    sb = _FakeSB(sink)
    ctx = _ctx()
    eid = store_integrity_event(sb, ctx, {
        "event_type": "incident.created", "flow_key": "x",
        "trace_id": "syn_acme_1", "severity": "WARNING",
    })
    assert eid == "evt_1"
    assert sink["table"] == "engine_integrity_event"
    assert "event_version" not in sink["row"]


# C22 (production producer files delta 0) is a repo-diff assertion, evidenced
# in the STEP A report (changed files = event_store.py, orchestrator.py, tests).
