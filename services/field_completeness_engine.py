"""field_completeness_engine.py — Field-level Completeness (PHASE D)

field 단위 completeness 계산.
"""
import json
from typing import Optional


def evaluate_field_completeness(field: dict) -> dict:
    """single field의 completeness 평가"""
    value = field.get("value")
    required = field.get("required_level", "OPTIONAL")
    field_type = field.get("field_type", "text")
    validation = field.get("validation_rule")

    # NULL/empty 검사
    is_empty = value is None or (isinstance(value, str) and not value.strip())

    if is_empty:
        if required == "MANDATORY":
            return {"status": "FAIL", "reason": "mandatory_field_empty"}
        elif required == "RECOMMENDED":
            return {"status": "WARNING", "reason": "recommended_field_empty"}
        else:
            return {"status": "PASS", "reason": "optional_field_empty"}

    # validation rule 검사
    if validation:
        rules = validation if isinstance(validation, dict) else json.loads(validation)
        rule_list = rules.get("rules", [])

        for r in rule_list:
            if r == "numeric":
                try:
                    float(value)
                except (ValueError, TypeError):
                    return {"status": "FAIL", "reason": "invalid_numeric_value"}
            elif r == "non_empty":
                if is_empty:
                    return {"status": "FAIL", "reason": "non_empty_validation_fail"}
            elif r == "signature_required":
                if is_empty:
                    return {"status": "FAIL", "reason": "signature_missing"}
            elif r == "evidence_required":
                if is_empty:
                    return {"status": "FAIL", "reason": "evidence_missing"}

    return {"status": "PASS", "reason": "field_valid"}


def calculate_document_completeness(sections: list) -> dict:
    """문서 전체 completeness 계산"""
    total = mandatory = recommended = optional = 0
    mandatory_pass = recommended_pass = 0
    fails = []
    warnings = []

    for section in sections:
        for field in section.get("fields", []):
            if not field.get("visible", True):
                continue  # 조건부로 숨겨진 필드 제외

            comp = evaluate_field_completeness(field)
            field["completeness"] = comp
            total += 1

            req = field.get("required_level", "OPTIONAL")
            if req == "MANDATORY":
                mandatory += 1
                if comp["status"] == "PASS":
                    mandatory_pass += 1
                else:
                    fails.append({"field": field.get("field_code"), "reason": comp["reason"]})
            elif req == "RECOMMENDED":
                recommended += 1
                if comp["status"] == "PASS":
                    recommended_pass += 1
                else:
                    warnings.append({"field": field.get("field_code"), "reason": comp["reason"]})
            else:
                optional += 1

    mandatory_pct = (mandatory_pass / mandatory * 100) if mandatory > 0 else 100
    recommended_pct = (recommended_pass / recommended * 100) if recommended > 0 else 100
    creatable = mandatory_pct == 100

    return {
        "total_fields": total,
        "mandatory": {"total": mandatory, "pass": mandatory_pass, "pct": round(mandatory_pct, 1)},
        "recommended": {"total": recommended, "pass": recommended_pass, "pct": round(recommended_pct, 1)},
        "optional_count": optional,
        "creatable": creatable,
        "fails": fails[:20],
        "warnings": warnings[:20],
    }
