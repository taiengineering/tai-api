"""Unit tests — services.free_result_additional_information (WO-FREE-RESULT-ADDITIONAL-INFORMATION-001).

full_result 형태는 GATE-0 실측 기준. DB/network 불필요.
PATCH-1(B): malformed obligation guard.
"""
import importlib

mod = importlib.import_module("services.free_result_additional_information")
project = mod.project_additional_information


def _fr(contract=None, obligations=None):
    fr = {}
    if contract is not None:
        fr["contract"] = contract
    if obligations is not None:
        fr["obligations_raw"] = obligations
    return fr


def test_input_gaps_counts():  # BE-T1
    fr = _fr(contract={
        "missing_fields": ["a", "b", "c"],
        "unknown_fields": ["x"],
        "invalid_fields": [],
    })
    out = project(fr)
    assert out["input_gaps"] == {"missing_count": 3, "unknown_count": 1, "invalid_count": 0}


def test_no_raw_arrays_or_field_codes_in_output():  # BE-T2
    fr = _fr(contract={"missing_fields": ["secret_code_1", "secret_code_2"]})
    out = project(fr)
    import json
    blob = json.dumps(out, ensure_ascii=False)
    assert "secret_code_1" not in blob and "secret_code_2" not in blob
    assert out["input_gaps"]["missing_count"] == 2


def test_obligation_affected_nonempty_only():  # BE-T3 / BE-T4
    obligations = [
        {"enrichment": {"missing_fields": ["f1"]}},           # affected
        {"enrichment": {"missing_fields": []}},               # not affected
        {"enrichment": {"missing_fields": ["f2", "f3"]}},     # affected
        {"enrichment": {}},                                    # not affected (키 없음)
        {"enrichment": {"missing_fields": None}},             # not affected (null)
    ]
    out = project(_fr(obligations=obligations))
    assert out["obligation_gaps"]["affected_count"] == 2


def test_coverage_true_false_null_separation():  # BE-T5
    obligations = [
        {"enrichment": {"usable_for_evaluation": True}},
        {"enrichment": {"usable_for_evaluation": True}},
        {"enrichment": {"usable_for_evaluation": False}},
        {"enrichment": {"usable_for_evaluation": None}},
        {"enrichment": {}},  # 키 없음
    ]
    out = project(_fr(obligations=obligations))
    assert out["coverage"] == {"evaluable_count": 2, "not_evaluable_count": 1, "unknown_count": 2}


def test_coverage_string_not_coerced():  # BE-T6
    obligations = [
        {"enrichment": {"usable_for_evaluation": "true"}},   # 문자열 → unknown (추론 금지)
        {"enrichment": {"usable_for_evaluation": "false"}},  # 문자열 → unknown
        {"enrichment": {"usable_for_evaluation": 1}},        # 정수 → unknown
    ]
    out = project(_fr(obligations=obligations))
    assert out["coverage"]["evaluable_count"] == 0
    assert out["coverage"]["not_evaluable_count"] == 0
    assert out["coverage"]["unknown_count"] == 3


def test_legacy_no_contract_fail_closed():  # BE-T7
    out = project(_fr(obligations=[{"enrichment": {"usable_for_evaluation": True}}]))
    assert out["input_gaps"] == {"missing_count": 0, "unknown_count": 0, "invalid_count": 0}
    assert out["coverage"]["evaluable_count"] == 1  # obligation 계층은 정상


def test_no_obligations_fail_closed():  # BE-T8
    out = project(_fr(contract={"missing_fields": ["a"]}))
    assert out["input_gaps"]["missing_count"] == 1
    assert out["obligation_gaps"] == {"affected_count": 0}
    assert out["coverage"] == {"evaluable_count": 0, "not_evaluable_count": 0, "unknown_count": 0}


def test_malformed_obligation_items_skipped():  # BE-T9 (PATCH-1 B)
    out = project(_fr(obligations=[None, "bad", 123]))
    assert out["obligation_gaps"]["affected_count"] == 0
    assert out["coverage"] == {"evaluable_count": 0, "not_evaluable_count": 0, "unknown_count": 0}


def test_enrichment_null_is_unknown():  # BE-T10 (PATCH-1 B)
    out = project(_fr(obligations=[{"enrichment": None}]))
    assert out["coverage"] == {"evaluable_count": 0, "not_evaluable_count": 0, "unknown_count": 1}
    assert out["obligation_gaps"]["affected_count"] == 0


def test_enrichment_malformed_nondict_skipped():  # BE-T11 (PATCH-1 B)
    out = project(_fr(obligations=[{"enrichment": "broken"}, {"enrichment": []}, {"enrichment": 7}]))
    assert out["coverage"] == {"evaluable_count": 0, "not_evaluable_count": 0, "unknown_count": 0}
    assert out["obligation_gaps"]["affected_count"] == 0


def test_mixed_valid_and_malformed():
    obligations = [
        {"enrichment": {"missing_fields": ["f"], "usable_for_evaluation": True}},  # affected + evaluable
        None,                                                                       # skip
        {"enrichment": "broken"},                                                   # skip
        {"enrichment": None},                                                       # unknown
        {"enrichment": {"usable_for_evaluation": False}},                           # not_evaluable
    ]
    out = project(_fr(obligations=obligations))
    assert out["obligation_gaps"]["affected_count"] == 1
    assert out["coverage"] == {"evaluable_count": 1, "not_evaluable_count": 1, "unknown_count": 1}


def test_malformed_full_result_fail_closed():
    for bad in [None, [], "x", 123, {"contract": "x", "obligations_raw": "y"}]:
        out = project(bad)
        assert out["input_gaps"] == {"missing_count": 0, "unknown_count": 0, "invalid_count": 0}
        assert out["obligation_gaps"]["affected_count"] == 0
        assert out["coverage"]["unknown_count"] == 0


def test_output_shape_is_counts_only():
    out = project(_fr(contract={"missing_fields": ["a"]},
                      obligations=[{"enrichment": {"missing_fields": ["f"], "usable_for_evaluation": True}}]))
    assert set(out.keys()) == {"input_gaps", "obligation_gaps", "coverage"}
    assert set(out["input_gaps"].keys()) == {"missing_count", "unknown_count", "invalid_count"}
    assert set(out["obligation_gaps"].keys()) == {"affected_count"}
    assert set(out["coverage"].keys()) == {"evaluable_count", "not_evaluable_count", "unknown_count"}
    for block in out.values():
        for v in block.values():
            assert isinstance(v, int)
