from __future__ import annotations

import json
import re
from typing import Any, List, Optional

VALID_CONDITION_CODES = {
    "building_area",
    "worker_count",
    "electric_capacity",
    "gas_capacity_kg",
    "gas_capacity_m3",
    "boiler_capacity_kw",
    "elevator_count",
    "is_hazardous_material",
    "annual_energy_toe",
    "construction_amount",
    "floor_count",
    "is_factory_registered",
    "employee_count",
    "contract_amount",
    "has_chemical_substance",
    "is_multi_use",
    "contractor_count",
    "has_high_pressure_gas",
    "transformer_capacity_kva",
    "has_boiler",
    "electrical_capacity_kw",
    "boiler_capacity_th",
    "hospital_beds",
    "student_count",
}


def _extract_json_payload(raw: str) -> Any:
    cleaned = re.sub(r"```json\s*", "", raw.strip())
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m_arr = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if m_arr:
            try:
                return json.loads(m_arr.group())
            except Exception:
                pass
        m_obj = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m_obj:
            try:
                return json.loads(m_obj.group())
            except Exception:
                pass
    return None


_SUBMIT_ORG_CODES = {"kosha", "local_gov", "moel", "me", "kgs", "mlit", "nfa", "kesco"}


def _normalize_submit_org_code(code: Any) -> Optional[str]:
    value = str(code or "").strip().lower()
    if value in _SUBMIT_ORG_CODES:
        return value
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "y", "yes"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _is_valid_uuid(val: Any) -> bool:
    return bool(val and _UUID_RE.match(str(val)))


_VARCHAR_30_FIELDS = frozenset([
    "condition_code", "condition_operator_code", "cycle_unit_std",
    "inspection_cycle_unit_code", "executor_type_code",
    "appointment_target_code", "submit_org_code",
])


def sanitize_master_patch(patch: dict) -> dict:
    """master_building_legal_rules UPDATE 전 타입 안전 검증.
    - updated_by/created_by: UUID 아니면 제거
    - condition_value: numeric 변환 실패 시 제거
    - varchar(30) 초과 시 truncate
    """
    for uuid_field in ("updated_by", "created_by"):
        if uuid_field in patch:
            if not _is_valid_uuid(patch[uuid_field]):
                patch.pop(uuid_field)

    if "condition_value" in patch and patch["condition_value"] is not None:
        try:
            patch["condition_value"] = float(patch["condition_value"])
        except (ValueError, TypeError):
            patch.pop("condition_value")

    for f in _VARCHAR_30_FIELDS:
        if f in patch and patch[f] is not None and len(str(patch[f])) > 30:
            patch[f] = str(patch[f])[:30]

    return patch


def _validate_rule_row(row: dict) -> List[str]:
    errors: List[str] = []
    cond_code = row.get("condition_code")
    cond_op = row.get("condition_operator_code")
    cond_val = row.get("condition_value")
    if cond_code:
        if cond_code not in VALID_CONDITION_CODES:
            errors.append("invalid_condition_code")
        if _is_blank(cond_op) or cond_val is None:
            errors.append("condition_incomplete")

    if _to_bool(row.get("inspection_required")):
        if _is_blank(row.get("inspection_cycle_value")) or _is_blank(row.get("inspection_cycle_unit_code")):
            errors.append("missing_inspection_cycle")

    if _to_bool(row.get("report_required")) and _is_blank(row.get("report_method_code")):
        errors.append("missing_report_method")

    if _to_bool(row.get("appointment_required")) and _is_blank(row.get("appointment_qualification_code")):
        errors.append("missing_qualification")

    if row.get("penalty_summary") and _is_blank(row.get("penalty_value")):
        errors.append("missing_penalty_value")

    if _is_blank(row.get("obligation_summary")):
        errors.append("missing_obligation_summary")

    return errors
