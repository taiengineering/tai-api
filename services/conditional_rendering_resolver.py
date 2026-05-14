"""conditional_rendering_resolver.py — Conditional Rendering (PHASE C)

조건부 section/field 활성화. deterministic 연산만.
절대 금지: AI 조건 해석
"""
import json
from typing import Any, Optional


def evaluate_condition(rule: dict, context: dict) -> bool:
    """conditional_rule 평가. deterministic operators only."""
    if not rule:
        return True  # 조건 없으면 항상 표시

    field = rule.get("condition") or rule.get("field")
    operator = rule.get("operator", "=")
    expected = rule.get("value")

    if not field:
        return True

    actual = context.get(field)

    # NULL 처리
    if actual is None:
        if operator == "EXISTS":
            return False
        return False  # 데이터 없으면 조건 미충족

    try:
        if operator == "=":
            return actual == expected
        elif operator == "!=":
            return actual != expected
        elif operator == ">":
            return float(actual) > float(expected)
        elif operator == ">=":
            return float(actual) >= float(expected)
        elif operator == "<":
            return float(actual) < float(expected)
        elif operator == "<=":
            return float(actual) <= float(expected)
        elif operator == "IN":
            if isinstance(expected, list):
                return actual in expected
            return str(actual) in str(expected)
        elif operator == "EXISTS":
            return actual is not None
        else:
            return True  # 알 수 없는 연산자 → 표시 (안전 쪽)
    except (ValueError, TypeError):
        return False


def _rule_unmet_description(rule: dict, context: dict) -> str:
    field = rule.get("condition") or rule.get("field")
    op = rule.get("operator", "=")
    expected = rule.get("value")
    actual = context.get(field) if field else None
    return (
        f"conditional_rule not satisfied: {field!r} {op} {expected!r} "
        f"(context[{field!r}]={actual!r})"
    )


def resolve_conditional_fields(fields: list, context: dict) -> list:
    """필드 목록에서 조건부 필드를 필터링"""
    result = []
    for f in fields:
        rule_str = f.get("conditional_rule")
        if rule_str:
            try:
                rule = rule_str if isinstance(rule_str, dict) else json.loads(rule_str)
            except (json.JSONDecodeError, TypeError):
                f["visible"] = True
                f["condition_evaluated"] = False
                f["conditional_reason"] = "invalid_conditional_rule_json"
                result.append(f)
                continue
            visible = evaluate_condition(rule, context)
            f["visible"] = visible
            f["condition_evaluated"] = True
            f["condition_result"] = visible
            if not visible:
                f["conditional_reason"] = _rule_unmet_description(rule, context)
            else:
                f.pop("conditional_reason", None)
        else:
            f["visible"] = True
            f["condition_evaluated"] = False
            f.pop("conditional_reason", None)
        result.append(f)
    return result
