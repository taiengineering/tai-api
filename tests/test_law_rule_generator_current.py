"""law_rule_generator 분리 작업 STEP 0 — 현재 동작 스냅샷 (DEV_RULES_SERVICE_LAYER)."""
from __future__ import annotations

import json
import os

os.environ.setdefault("INTERNAL_API_SECRET", "test-law-rule-generator-secret")


def test_router_module_imports():
    from routers import law_rule_generator as lrg

    assert lrg.router.prefix == "/law-rule-generator"


def test_excluded_sectors_contains_special_facility():
    from routers.law_rule_generator import EXCLUDED_SECTORS

    assert "SPECIAL_FACILITY" in EXCLUDED_SECTORS


def test_submit_org_labels_has_expected_keys():
    from routers.law_rule_generator import SUBMIT_ORG_LABELS

    assert "nfa" in SUBMIT_ORG_LABELS
    assert "kosha" in SUBMIT_ORG_LABELS


def test_build_draft_row_service_contract():
    from services.rule_gen_builders import _build_draft_row

    rule = {
        "draft_rule_id": "TEST-001-BLD",
        "obligation_type": "INSPECT",
        "sector": "BUILDING",
        "condition_code": "worker_count",
        "condition_operator": "gte",
        "condition_value": "10",
        "obligation_summary": "요약",
        "penalty_summary": None,
        "appointment_target": None,
        "diagnosis_stage": 1,
        "ai_confidence": 80,
        "ai_reasoning": "test",
        "ai_flags": [],
    }
    row = _build_draft_row("산업안전보건법", "제1조", "article-uuid", "본문" * 10, rule)
    assert row["law_name"] == "산업안전보건법"
    assert row["status"] == "PENDING"
    assert row["draft_rule_id"] == "TEST-001-BLD"
    assert row["article_text"].startswith("본문")


def test_user_prompt_template_formats():
    from routers.law_rule_generator import FEW_SHOT_RULE, USER_PROMPT_TEMPLATE

    out = USER_PROMPT_TEMPLATE.format(
        law_name="L",
        article_text="T",
        full_context="C",
        few_shot=json.dumps(FEW_SHOT_RULE, ensure_ascii=False),
    )
    assert "L" in out and "T" in out and "C" in out


def test_validate_rule_row_invalid_condition_from_helpers():
    from services.rule_gen_helpers import _validate_rule_row

    errs = _validate_rule_row(
        {
            "condition_code": "not_a_valid_condition",
            "condition_operator_code": "gte",
            "condition_value": 1,
            "obligation_summary": "ok",
        }
    )
    assert "invalid_condition_code" in errs
