from __future__ import annotations

import json
import re
from typing import Any, List, Optional

VALID_CONDITION_CODES = frozenset({
    "annual_energy_toe", "boiler_capacity_kw", "boiler_capacity_th", "building_area", "construction_amount",
    "contract_amount", "contractor_count", "electric_capacity", "electrical_capacity_kw", "elevator_count",
    "employee_count", "floor_count", "gas_capacity_kg", "gas_capacity_m3", "has_boiler", "has_chemical_substance",
    "has_high_pressure_gas", "hospital_beds", "is_factory_registered", "is_hazardous_material", "is_multi_use",
    "student_count", "transformer_capacity_kva", "worker_count",
})


def _extract_json_payload(raw: str) -> Any:
    cleaned = re.sub(r"```\s*", "", re.sub(r"```json\s*", "", raw.strip())).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        for pat in (r"\[.*\]", r"\{.*\}"):
            m = re.search(pat, cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
    return None


_SUBMIT_ORG_CODES = {"kosha", "local_gov", "moel", "me", "kgs", "mlit", "nfa", "kesco"}


def _normalize_submit_org_code(code: Any) -> Optional[str]:
    value = str(code or "").strip().lower()
    return value if value in _SUBMIT_ORG_CODES else None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "y", "yes"}
    return value != 0 if isinstance(value, (int, float)) else False


def _safe_float(value: Any) -> Optional[float]:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return None if value in (None, "") else int(float(value))
    except (TypeError, ValueError):
        return None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _is_valid_uuid(val: Any) -> bool:
    return bool(val and _UUID_RE.match(str(val)))


_VARCHAR_30_FIELDS = frozenset({
    "appointment_target_code", "condition_code", "condition_operator_code", "cycle_unit_std",
    "executor_type_code", "inspection_cycle_unit_code", "submit_org_code",
})
_NUMERIC_FIELDS = frozenset({
    "appointment_count_value", "condition_value", "equipment_condition_value",
    "inspection_cycle_value", "penalty_value",
})


def _coerce_numeric(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            m = re.search(r"-?\d+(?:\.\d+)?", value)
            if m:
                try:
                    return float(m.group())
                except ValueError:
                    return None
    return None


def sanitize_master_patch(patch: dict) -> dict:
    for uuid_field in ("updated_by", "created_by"):
        if uuid_field in patch and not _is_valid_uuid(patch[uuid_field]):
            patch.pop(uuid_field)
    for nf in _NUMERIC_FIELDS:
        if nf in patch and patch[nf] is not None:
            coerced = _coerce_numeric(patch[nf])
            if coerced is None:
                patch.pop(nf)
            else:
                patch[nf] = coerced
    for f in _VARCHAR_30_FIELDS:
        if f in patch and patch[f] is not None and len(str(patch[f])) > 30:
            patch[f] = str(patch[f])[:30]
    return patch


def _validate_rule_row(row: dict) -> List[str]:
    errors: List[str] = []
    cond_code, cond_op, cond_val = row.get("condition_code"), row.get("condition_operator_code"), row.get("condition_value")
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
