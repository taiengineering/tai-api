"""tests/test_paid_result_public_projection_v1.py — WO-STEP8A B1~B14 + REV-1 B15~B21

대상:
  services/paid_result_public_projection_svc.py
  routers/diagnosis_result_web.py  genuine-paid additive premium_result_v1

실 Supabase / LEG Runtime 미호출.
"""
from __future__ import annotations

import copy
import json

import routers.diagnosis_result_web as rw
from services.paid_result_public_projection_svc import (
    FINDING_FACTS_ALLOWLIST,
    F13_TRIGGER_WHITELIST,
    build_public_premium_result_v1,
)
from tests.test_paid_result_delivery_wiring_v1 import (
    install,
    leg_obligation,
    source_item,
    stored_rec,
)


PREMIUM = "premium_result_v1"

FORBIDDEN_KEYS = {
    "source_index",
    "atom_id",
    "source_atom_ids",
    "semantic_clause_id",
    "source_part_id",
    "source_sha256",
    "__source_index",
    "paid_result_materials_v1",
    "paid_result_evidence_v1",
    "paid_result_source_text_v1",
    "law_article_id",
    "law_version_id",
    "article_no_sort",
    "enforcement_date",
    "match_rule",
    "match_field",
    "source_table",
    "resolution",
    "unresolved",
    "provenance",
    "reason",
    "what",
    "triggered_by",
    "mapped_field",
    "missing_fields",
    "decision_inputs",
    "finding_id",
    "finding_type",
    "related_obligation_refs",
}

RAW_INPUT_FIELD_CODES = (
    "has_unmapped_thing",
    "mapped_field",
    "worker_count",
    "total_floor_area",
)


def _keys(value, acc=None):
    if acc is None:
        acc = set()
    if isinstance(value, dict):
        acc.update(value.keys())
        for child in value.values():
            _keys(child, acc)
    elif isinstance(value, list):
        for child in value:
            _keys(child, acc)
    return acc


def _paid(monkeypatch, rec=None, items=None):
    rec = rec or stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    items = items if items is not None else [source_item(0, "a0", "원문A")]
    install(monkeypatch, rec, product_items=items)
    return rw.get_paid_result_web("tok-1")


def test_B1_genuine_paid_premium_exists(monkeypatch):
    data = _paid(monkeypatch)["data"]
    assert PREMIUM in data
    assert isinstance(data[PREMIUM], dict)
    assert data[PREMIUM]["version"] == 1


def test_B2_free_route_and_free_tier_premium_absent(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    assert PREMIUM not in rw.get_diagnosis_result_web("tok-1")["data"]

    rec_free = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    install(monkeypatch, rec_free, product_items=[source_item(0, "a0", "원문A")])
    assert PREMIUM not in rw.get_paid_result_web("tok-1")["data"]


def test_B3_raw_legacy_premium_absent(monkeypatch):
    monkeypatch.setattr(rw, "enrich_rules_with_candidate_slots", lambda *a, **k: None)
    rules_table = [{
        "law_name": "L", "law_article": "1", "obligation_type": "INSPECT",
        "obligation_summary": "레거시", "description": "레거시", "rule_id": "r1",
    }]
    rec = stored_rec(
        [leg_obligation("a0", "무시")], tier="BUILDING_V2", rules_table=rules_table
    )
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문")])
    data = rw.get_paid_result_web("tok-1")["data"]
    assert calls["n"] == 0
    assert PREMIUM not in data


def test_B4_forbidden_keys_recursive_zero():
    projected = build_public_premium_result_v1(_sample_product())
    found = _keys(projected) & FORBIDDEN_KEYS
    assert found == set(), found


def test_B5_duty_what_recursive_absent():
    projected = build_public_premium_result_v1(_sample_product())
    blob = json.dumps(projected, ensure_ascii=False)
    assert '"what"' not in blob
    for duty in (ob["duty"] for ob in projected["materials"]["obligations"]):
        assert "what" not in duty


def test_B6_source_index_name_recursive_absent():
    projected = build_public_premium_result_v1(_sample_product())
    assert "source_index" not in _keys(projected)
    blob = json.dumps(projected, ensure_ascii=False)
    assert '"source_index"' not in blob


def test_B7_ref_equals_source_index_exact():
    product = _sample_product()
    src_refs = [
        ob["identity"]["source_index"]
        for ob in product["paid_result_materials_v1"]["normalized_obligations"]
    ]
    out_refs = [
        ob["ref"]
        for ob in build_public_premium_result_v1(product)["materials"]["obligations"]
    ]
    assert out_refs == src_refs


def test_B8_duplicate_canonical_same_ref_preserved():
    product = _sample_product()
    product["paid_result_source_text_v1"]["items"] = [
        _src_item(0, "원문A"),
        _src_item(0, "원문A-again"),
    ]
    sources = build_public_premium_result_v1(product)["canonical_sources"]
    assert sources == [
        {"ref": 0, "text": "원문A"},
        {"ref": 0, "text": "원문A-again"},
    ]


def test_B9_non_exact_not_projected():
    product = _sample_product()
    product["paid_result_source_text_v1"]["items"] = [
        _src_item(0, "원문A"),
        _src_item(1, None, status="SOURCE_MISMATCH"),
        _src_item(2, "", status="EXACT"),
        {"obligation_ref": 3, "resolution_status": "UNRESOLVED", "text": "x"},
    ]
    sources = build_public_premium_result_v1(product)["canonical_sources"]
    assert sources == [{"ref": 0, "text": "원문A"}]


def test_B10_finding_facts_per_id_allowlist_exact():
    projected = build_public_premium_result_v1(_sample_product())
    findings = projected["materials"]["diagnosis_findings"]["findings"]
    by_id = {f["id"]: f for f in findings}
    for finding_id, allow in FINDING_FACTS_ALLOWLIST.items():
        assert set(by_id[finding_id]["facts"]) == set(allow), finding_id
        assert "provenance" not in by_id[finding_id]
        assert by_id[finding_id]["type"]


def test_B11_unsafe_f13_trigger_removed():
    product = _sample_product()
    findings = product["paid_result_materials_v1"]["diagnosis_findings"]["findings"]
    f13 = next(f for f in findings if f["finding_id"] == "F13")
    f13["facts"] = {
        "trigger_count": 3,
        "triggers": ["has_excavation", "has_unmapped_thing", "has_chemical"],
    }
    out = build_public_premium_result_v1(product)
    facts = next(
        f["facts"] for f in out["materials"]["diagnosis_findings"]["findings"]
        if f["id"] == "F13"
    )
    assert facts["triggers"] == ["has_excavation"]
    assert "trigger_count" not in facts
    assert "has_unmapped_thing" not in json.dumps(out, ensure_ascii=False)
    assert "has_chemical" not in json.dumps(out, ensure_ascii=False)
    for item in facts["triggers"]:
        assert item in F13_TRIGGER_WHITELIST


def test_B12_raw_input_field_code_absent():
    product = _sample_product()
    findings = product["paid_result_materials_v1"]["diagnosis_findings"]["findings"]
    f13 = next(f for f in findings if f["finding_id"] == "F13")
    f13["facts"]["triggers"] = ["has_excavation", "has_unmapped_thing"]
    projected = build_public_premium_result_v1(product)
    blob = json.dumps(projected, ensure_ascii=False)
    for code in RAW_INPUT_FIELD_CODES:
        assert code not in blob, code
    assert "triggered_by" not in _keys(projected)
    assert "mapped_field" not in _keys(projected)
    assert "missing_fields" not in _keys(projected)


def test_B13_assembler_called_exactly_once(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    data = rw.get_paid_result_web("tok-1")["data"]
    assert calls["n"] == 1
    assert PREMIUM in data


def test_B14_legacy_response_fields_unchanged(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    data = rw.get_paid_result_web("tok-1")["data"]
    legacy = {k: v for k, v in data.items() if k != PREMIUM}
    expected = {
        "public_token", "tier_code", "is_free", "sector", "sector_label",
        "company_name", "risk_level", "risk_reason", "applicable_count",
        "engine_version", "summary", "obligation_counts", "warnings",
        "rules_table", "appointment_required", "inspection_required",
        "law_badges", "key_obligations", "inspection_schedule", "law_groups",
        "free_obligations", "free_obligation_count", "input_data",
        "recommended_plan", "pdf_url",
    }
    assert expected <= set(legacy)
    row = data["rules_table"][0]
    assert row["obligation_summary"] == "점검"
    assert data["is_free"] is False
    assert data["public_token"] == "tok-1"


PRESENTATION_F13_KEYS = (
    "worker_count",
    "total_floor_area",
    "contract_amount_eok",
    "sector",
    "construction_type",
    "building_use_type",
    "has_excavation",
    "has_hazardous_material",
)


def _finding_by_id(projected, finding_id):
    return next(
        f for f in projected["materials"]["diagnosis_findings"]["findings"]
        if f["id"] == finding_id
    )


def test_B15_f13_whitelist_is_presentation_frozen_eight():
    assert F13_TRIGGER_WHITELIST == PRESENTATION_F13_KEYS
    assert len(F13_TRIGGER_WHITELIST) == 8
    for removed in (
        "has_asbestos", "has_chemical", "has_crane",
        "has_elevator", "has_scaffold", "has_subcontractor",
    ):
        assert removed not in F13_TRIGGER_WHITELIST


def test_B16_f13_trigger_count_absent_public():
    projected = build_public_premium_result_v1(_sample_product())
    facts = _finding_by_id(projected, "F13")["facts"]
    assert "trigger_count" not in facts
    assert "trigger_count" not in _keys(projected)


def test_B17_f03_obligation_count_absent():
    facts = _finding_by_id(build_public_premium_result_v1(_sample_product()), "F03")["facts"]
    assert "obligation_count" not in facts
    assert set(facts) == {"max_obligation_count", "actors"}


def test_B18_f03_actors_count_absent():
    facts = _finding_by_id(build_public_premium_result_v1(_sample_product()), "F03")["facts"]
    assert facts["actors"]
    for row in facts["actors"]:
        assert set(row) == {"actor"}
        assert "count" not in row


def test_B19_f08_laws_count_absent():
    facts = _finding_by_id(build_public_premium_result_v1(_sample_product()), "F08")["facts"]
    assert facts["laws"]
    for row in facts["laws"]:
        assert set(row) == {"law_name"}
        assert "count" not in row


def test_B20_f09_articles_count_absent():
    facts = _finding_by_id(build_public_premium_result_v1(_sample_product()), "F09")["facts"]
    assert facts["articles"]
    for row in facts["articles"]:
        assert set(row) == {"law_name", "law_article"}
        assert "count" not in row


def test_B21_nested_unknown_key_injection_not_exposed():
    product = _sample_product()
    findings = product["paid_result_materials_v1"]["diagnosis_findings"]["findings"]
    by_id = {f["finding_id"]: f for f in findings}
    by_id["F03"]["facts"]["actors"] = [{
        "actor": "사업주", "count": 2, "secret_nested": "LEAK_F03",
    }]
    by_id["F08"]["facts"]["laws"] = [{
        "law_name": "산업안전보건법", "count": 9, "secret_nested": "LEAK_F08",
    }]
    by_id["F09"]["facts"]["articles"] = [{
        "law_name": "산업안전보건법", "law_article": "38",
        "count": 1, "secret_nested": "LEAK_F09",
    }]
    projected = build_public_premium_result_v1(product)
    blob = json.dumps(projected, ensure_ascii=False)
    assert "secret_nested" not in _keys(projected)
    assert '"secret_nested"' not in blob
    for leak in ("LEAK_F03", "LEAK_F08", "LEAK_F09"):
        assert leak not in blob, leak
    out = {f["id"]: f["facts"] for f in projected["materials"]["diagnosis_findings"]["findings"]}
    assert out["F03"]["actors"] == [{"actor": "사업주"}]
    assert out["F08"]["laws"] == [{"law_name": "산업안전보건법"}]
    assert out["F09"]["articles"] == [{"law_name": "산업안전보건법", "law_article": "38"}]


def test_projection_does_not_mutate_product():
    product = _sample_product()
    before = copy.deepcopy(product)
    build_public_premium_result_v1(product)
    assert product == before


def _src_item(ref, text, *, status="EXACT"):
    return {
        "obligation_ref": ref,
        "atom_id": "a%s" % ref,
        "source_atom_ids": ["a%s" % ref],
        "semantic_clause_id": "sc",
        "source_part_id": "sp",
        "law_name": "법",
        "law_article": "1",
        "text": text,
        "source_sha256": "h",
        "resolution_status": status,
    }


def _finding(finding_id, finding_type, facts, *, eligible=True):
    return {
        "finding_id": finding_id,
        "finding_type": finding_type,
        "eligible": eligible,
        "facts": facts,
        "provenance": {
            "source_materials": ["overview"],
            "source_fields": ["x"],
            "derivation_rule": "COUNT_DISTINCT_V1",
        },
    }


def _sample_product():
    findings = []
    for finding_id, keys in FINDING_FACTS_ALLOWLIST.items():
        facts = {key: ([] if key in ("triggers", "actors", "laws", "articles") else 1) for key in keys}
        if finding_id == "F03":
            facts = {
                "obligation_count": 99,
                "max_obligation_count": 2,
                "actors": [{"actor": "사업주", "count": 2, "secret_nested": "LEAK_F03"}],
            }
        elif finding_id == "F08":
            facts = {
                "obligation_count": 2,
                "laws": [{"law_name": "산업안전보건법", "count": 2, "secret_nested": "LEAK_F08"}],
            }
        elif finding_id == "F09":
            facts = {
                "obligation_count": 1,
                "articles": [{
                    "law_name": "산업안전보건법",
                    "law_article": "38",
                    "count": 1,
                    "secret_nested": "LEAK_F09",
                }],
            }
        elif finding_id == "F13":
            facts = {
                "trigger_count": 2,
                "triggers": ["has_excavation", "has_unmapped_thing"],
            }
        findings.append(_finding(finding_id, "TYPE_%s" % finding_id, facts))
    return {
        "contract_version": 1,
        "diagnosis": {
            "result_id": "row-1",
            "public_token": "tok-1",
            "diagnosed_at": "2026-08-11T01:25:02+00:00",
        },
        "diagnosis_profile": {
            "profile_version": 1,
            "company_name": "샘플",
            "sector": "BUILDING",
            "workers": 10,
            "floor_area": 100,
            "contract_amount_eok": None,
            "site_kind": "SECRET",
            "construction_type": None,
            "building_use_type": None,
            "address": "서울",
            "has_excavation": True,
            "has_hazardous_material": False,
            "available_facts": ["company_name", "has_excavation"],
        },
        "paid_result_materials_v1": {
            "meta": {
                "material_version": 1,
                "normalizer_version": 2,
                "obligation_source": "full_result.obligations_raw",
            },
            "normalized_obligations": [
                {
                    "identity": {
                        "source_index": 7,
                        "atom_id": "a7",
                        "source_atom_ids": ["a7"],
                    },
                    "legal": {
                        "law_name": "산업안전보건법",
                        "law_article": "38",
                        "evidence": "근거",
                    },
                    "classification": {
                        "content_type": "OBLIGATION",
                        "obligation_type": "INSPECT",
                    },
                    "duty": {
                        "what": "점검을 해야 한다",
                        "who": "사업주",
                        "recipient": None,
                        "where": None,
                        "how": None,
                    },
                    "applicability": {
                        "condition": "굴착하는 경우",
                        "triggered_by": ["has_excavation", "has_unmapped_thing"],
                    },
                    "verification": {"check_result": "VERIFIED"},
                    "timing": {
                        "when": "상시",
                        "inspection_cycle": None,
                        "raw_cycle": "상시",
                        "conflict": False,
                    },
                }
            ],
            "overview": {
                "total_obligation_count": 1,
                "distinct_law_count": 1,
                "unspecified_law_obligation_count": 0,
                "obligation_type_counts": {"INSPECT": 1},
                "content_type_counts": {"OBLIGATION": 1},
                "verification_counts": {"VERIFIED": 1},
            },
            "duty_vs_prohibition": {
                "OBLIGATION": {"count": 1, "obligation_refs": [7]},
                "PROHIBITION": {"count": 0, "obligation_refs": []},
                "UNKNOWN": {"count": 0, "obligation_refs": []},
            },
            "compliance_profile": {"periodic_count": 0},
            "law_portfolio": [{
                "law_name": "산업안전보건법",
                "obligation_count": 1,
                "article_count": 1,
                "unspecified_article_obligation_count": 0,
                "obligation_refs": [7],
            }],
            "legal_actor_map": [
                {"actor": "사업주", "count": 1, "obligation_refs": [7]},
            ],
            "article_bundles": [{
                "law_name": "산업안전보건법",
                "law_article": "38",
                "count": 1,
                "obligation_refs": [7],
            }],
            "timing_character_summary": {
                "counts": {"CONTINUOUS": 1, "UNKNOWN": 0},
                "obligation_refs": {"CONTINUOUS": [7]},
            },
            "information_gaps": {
                "diagnosis_input_gaps": {
                    "missing_fields": ["worker_count"],
                    "unknown_fields": [],
                    "invalid_fields": [],
                },
                "obligation_information_gaps": {
                    "fields": [{"field": "when", "count": 1, "obligation_refs": [7]}],
                    "obligation_count_with_gaps": 1,
                },
            },
            "coverage_summary": {
                "obligation_evaluation_coverage": {
                    "source": "internal",
                    "total": 1,
                    "evaluable_count": 1,
                    "not_evaluable_count": 0,
                    "unknown_count": 0,
                }
            },
            "diagnosis_findings": {"version": 1, "findings": findings},
        },
        "paid_result_evidence_v1": {
            "resolution": {"rule": "EXACT_EVIDENCE_SUBSTRING_V1"},
            "unresolved": [],
            "articles": [{
                "law_name": "산업안전보건법",
                "article_no": 38,
                "article_sub_no": None,
                "article_no_sort": "0038-000",
                "article_title": "제목",
                "article_text": "원문",
                "enforcement_date": "2025-09-01",
                "related_obligation_refs": [7],
                "provenance": {
                    "source_table": "public.law_article",
                    "law_article_id": "a-1",
                    "law_version_id": "v-1",
                    "match_rule": "WHITESPACE_NORMALIZED_EXACT_SUBSTRING_V1",
                    "match_field": "x",
                },
            }],
        },
        "paid_result_source_text_v1": {
            "version": 1,
            "items": [_src_item(7, "원문A")],
            "unresolved": [],
        },
    }
