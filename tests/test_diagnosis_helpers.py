from services import diagnosis_helpers as h
from services.diagnosis_helpers import SOURCE_DIAGNOSIS, _build_standard_output


def test_now_iso_has_utc_offset():
    now = h._now()
    assert "T" in now
    assert now.endswith("+00:00")


def test_sha256_snapshot():
    assert h._sha256("tai") == "f4ddd195cab04430d4595e18bd75fd48df4a0dfb3a7a28c6b2fcf3582762d49d"


def test_auto_tier_snapshot():
    assert h._auto_tier("BUILDING", floor_area=4999) == "BUILDING_V2"
    assert h._auto_tier("BUILDING", floor_area=5000) == "BUILDING_LARGE_V2"
    assert h._auto_tier("CONSTRUCTION", contract_amount_eok=49) == "CONSTRUCTION"
    assert h._auto_tier("CONSTRUCTION", contract_amount_eok=50) == "CONSTRUCTION_PREMIUM"
    assert h._auto_tier("INDUSTRIAL", user_tier="INDUSTRY_STANDARD") == "INDUSTRY_STANDARD"


def test_build_partial_truncates_lists():
    full = {
        "risk_level": "HIGH",
        "summary": {"total": 10},
        "applicable_count": 10,
        "sector": "BUILDING",
        "key_obligations": [f"k{i}" for i in range(10)],
        "law_badges": [f"l{i}" for i in range(30)],
    }
    part = h._build_partial(full)
    assert len(part["key_obligations"]) == 6
    assert len(part["law_badges"]) == 18
    assert part["key_obligations"][0]["source"] == SOURCE_DIAGNOSIS


def test_build_standard_output_unifies_anonymous_and_integrated_fields():
    full = {
        "risk_level": "MEDIUM",
        "summary": {"total": 244},
        "applicable_count": 244,
        "sector": "BUILDING",
        "evaluated_at": "2026-06-08T00:00:00+00:00",
        "engine_version": "v3.0-compiler-core-anonymous",
        "key_obligations": [
            {"title": "안전관리자 선임", "law_name": "산업안전보건법", "source": SOURCE_DIAGNOSIS},
            "점검 실시",
        ],
        "rules_table": [
            {"rule_id": "r1", "law_name": "산업안전보건법", "obligation_summary": "선임"},
            {"rule_id": "r2", "law_name": "화재예방법", "obligation_summary": "점검"},
        ],
        "law_badges": ["산업안전보건법", "화재예방법"],
        "appointment_required": [{"rule_id": "r1", "law_name": "산업안전보건법"}],
        "construction_summary": {"tip": "건설 요약"},
    }
    out = _build_standard_output(full)
    assert out["evaluated_at"] == "2026-06-08T00:00:00+00:00"
    assert out["engine_version"] == "v3.0-compiler-core-anonymous"
    assert out["rules_preview"] == out["rules_table"]
    assert len(out["rules_table"]) == 2
    assert all(r.get("source") == SOURCE_DIAGNOSIS for r in out["rules_table"])
    assert out["key_obligations"][0]["title"] == "안전관리자 선임"
    assert out["key_obligations"][1]["title"] == "점검 실시"
    assert all(k.get("source") == SOURCE_DIAGNOSIS for k in out["key_obligations"])
    assert out["appointment_required"][0]["source"] == SOURCE_DIAGNOSIS
    assert out["construction_summary"] == {"tip": "건설 요약"}
    assert out["message"]


def test_build_partial_equals_build_standard_output():
    full = {"sector": "BUILDING", "applicable_count": 5, "key_obligations": ["a"]}
    assert h._build_partial(full) == _build_standard_output(full)
