"""§93 STEP A — anonymous diagnosis DIAGNOSIS_COMPLETED Common Event v1 (A1–A8 + freeze)."""
import ast
import pathlib

CANON = {"event_name", "actor_kind", "actor_ref"}
SRC = (pathlib.Path(__file__).resolve().parents[1] / "routers" / "anonymous_diagnosis.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _calls(fnname, callee):
    fn = _fn(fnname)
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == callee]


def _kw(call):
    out = {}
    for k in call.keywords:
        out[k.arg] = k.value.value if isinstance(k.value, ast.Constant) else ast.dump(k.value)
    return out


def _emit_calls():
    return _calls("_create_anonymous_diagnosis_impl", "emit_event")


def _canonical_calls():
    return [c for c in _emit_calls() if CANON <= {k.arg for k in c.keywords}]


def test_a1_exactly_one_canonical():
    assert len(_canonical_calls()) == 1

def test_a2_canonical_step_key_result_save():
    assert _kw(_canonical_calls()[0]).get("step_key") == "result_save"

def test_a3_canonical_result_success():
    assert _kw(_canonical_calls()[0]).get("result") == "success"

def test_a4_canonical_event_type_save():
    assert _kw(_canonical_calls()[0]).get("event_type") == "save"

def test_a2b_event_name():
    assert _kw(_canonical_calls()[0]).get("event_name") == "DIAGNOSIS_COMPLETED"

def test_a5_actor_kind_external():
    assert _kw(_canonical_calls()[0]).get("actor_kind") == "EXTERNAL"

def test_a6_actor_ref_external_anonymous():
    assert _kw(_canonical_calls()[0]).get("actor_ref") == "external:anonymous"

def test_a7_no_canonical_failure_result_save():
    for c in _canonical_calls():
        kw = _kw(c)
        assert not (kw.get("step_key") == "result_save" and kw.get("result") == "failure")

def test_a8_no_other_canonical():
    for c in _canonical_calls():
        kw = _kw(c)
        assert kw.get("step_key") == "result_save" and kw.get("result") == "success"

def test_legacy_freeze_other_steps():
    legacy_steps = {"submit_diagnosis", "rule_evaluate", "result_generate", "error"}
    for c in _emit_calls():
        kw = _kw(c)
        if kw.get("step_key") in legacy_steps:
            assert not (CANON <= {k.arg for k in c.keywords}), f"{kw.get('step_key')} must stay legacy"

def test_no_caller_overrides():
    kwset = {k.arg for k in _canonical_calls()[0].keywords}
    for forbidden in ("event_version", "occurred_at", "outcome", "trace", "trace_id",
                      "tenant_id", "service_key", "environment"):
        assert forbidden not in kwset

def test_create_trace_unchanged():
    ct = _calls("_create_anonymous_diagnosis_impl", "create_trace")
    assert len(ct) == 1
    kw = _kw(ct[0])
    assert kw.get("flow_key") == "law_diagnosis"
    assert kw.get("tenant_id") == "anonymous"
    assert kw.get("actor_type") == "user"
