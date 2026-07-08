"""FIELD_MAP Axis Value Builder (WO-ENG-001).

One builder per FIELD_MAP axis. Each builder does:

    consumer input  ->  normalize  ->  derive  ->  augment  ->  axis value

This is NOT a 1:1 resolver. Builders try multiple candidate input fields,
convert units/scale, combine fields, and (optionally) augment from injected
domain maps. They never invent domain mappings: augmentation maps are passed
in; when absent, augmentation is skipped and the primary value is used.

Constraints honored:
- FIELD_MAP 11 axes unchanged (fac_col/quality mirrored READ-ONLY).
- Engine philosophy unchanged: builders only produce values; whether the
  engine then compares or returns AMBIGUOUS is the engine's business.
- No Object/Compliance expansion. No live-path wiring.

For AMBIGUOUS-quality numeric axes (storage_capacity, monetary_value) the
builder produces a clean value, but the engine still returns AMBIGUOUS due to
the FIELD_MAP quality tag (engine-core, out of scope). engine_note records this.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Dict, List, Optional


# READ-ONLY mirror: axis -> (fac_col, quality). Source of truth = engine FIELD_MAP.
_FAC: Dict[str, tuple] = {
    "employee_count": ("employee_count", "DIRECT"),
    "area_size": ("building_area", "DIRECT"),
    "power_capacity": ("electrical_capacity_kw", "DIRECT"),
    "voltage_level": ("transformer_capacity_kva", "AMBIGUOUS"),
    "storage_capacity": ("gas_capacity_m3", "AMBIGUOUS"),
    "equipment_type": (None, "EQUIPMENT_JOIN"),
    "facility_type": ("site_type", "AMBIGUOUS"),
    "process_type": ("ksic_code", "AMBIGUOUS"),
    "monetary_value": ("construction_amount", "AMBIGUOUS"),
    "concentration_level": (None, "MISSING"),
    "distance_value": (None, "MISSING"),
}

# methods
DIRECT, FALLBACK, COMBINED, DERIVED, LOOKUP, GAP = (
    "DIRECT", "FALLBACK", "COMBINED", "DERIVED", "LOOKUP", "GAP")


@dataclass
class AxisValue:
    axis: str
    value: Any = None
    method: str = GAP
    sources_used: List[str] = dc_field(default_factory=list)
    fac_col: Optional[str] = None
    engine_note: str = ""      # COMPARE / SCOPE / AMBIGUOUS_QUALITY / NO_FAC_COL / GAP
    notes: str = ""

    def __post_init__(self) -> None:
        self.fac_col = _FAC[self.axis][0]


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _get_path(ci: Dict[str, Any], dotted: str) -> Any:
    cur: Any = ci
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _first_num(ci: Dict[str, Any], keys: List[str]):
    for k in keys:
        v = _num(_get_path(ci, k))
        if v is not None:
            return v, k
    return None, None


# --- numeric / DIRECT-compare axes ------------------------------------------
def build_employee_count(ci: Dict[str, Any]) -> AxisValue:
    direct = _num(ci.get("direct_workers"))
    subcon = _num(ci.get("subcon_workers"))
    if direct is not None or subcon is not None:
        used = [k for k in ("direct_workers", "subcon_workers") if ci.get(k) is not None]
        return AxisValue("employee_count", (direct or 0) + (subcon or 0), COMBINED,
                         used, engine_note="COMPARE", notes="direct+subcon")
    v, k = _first_num(ci, ["worker_count", "employee_count"])
    if v is not None:
        return AxisValue("employee_count", v, DIRECT if k == "employee_count" else FALLBACK,
                         [k], engine_note="COMPARE")
    return AxisValue("employee_count", None, GAP, [], engine_note="GAP", notes="no worker input")


def build_area_size(ci: Dict[str, Any]) -> AxisValue:
    v, k = _first_num(ci, ["total_floor_area", "floor_area", "building_register.total_floor_area"])
    if v is not None:
        return AxisValue("area_size", v, DIRECT if k == "total_floor_area" else FALLBACK,
                         [k], engine_note="COMPARE")
    return AxisValue("area_size", None, GAP, [], engine_note="GAP", notes="no area input")


def build_power_capacity(ci: Dict[str, Any]) -> AxisValue:
    v, k = _first_num(ci, ["electric_capacity", "electrical_capacity_kw"])
    if v is not None:
        return AxisValue("power_capacity", v, DIRECT if k == "electric_capacity" else FALLBACK,
                         [k], engine_note="COMPARE")
    return AxisValue("power_capacity", None, GAP, [], engine_note="GAP", notes="no power input")


# --- numeric / AMBIGUOUS-quality axes (value produced; engine still AMBIGUOUS)
def build_storage_capacity(ci: Dict[str, Any]) -> AxisValue:
    # target unit = m3 (fac_col gas_capacity_m3)
    m3 = _num(ci.get("gas_capacity_m3"))
    if m3 is not None:
        return AxisValue("storage_capacity", m3, DIRECT, ["gas_capacity_m3"],
                         engine_note="AMBIGUOUS_QUALITY", notes="m3 direct")
    kg = _num(ci.get("gas_capacity_kg"))
    density = _num(ci.get("gas_density_kg_m3"))
    if kg is not None and density:
        return AxisValue("storage_capacity", kg / density, DERIVED,
                         ["gas_capacity_kg", "gas_density_kg_m3"],
                         engine_note="AMBIGUOUS_QUALITY", notes="kg/density -> m3")
    if kg is not None:
        return AxisValue("storage_capacity", None, GAP, ["gas_capacity_kg"],
                         engine_note="GAP", notes="kg present but density unknown (cannot convert)")
    cap = _num(ci.get("capacity"))
    if cap is not None and ci.get("capacity_unit") in ("m3", "m³"):
        return AxisValue("storage_capacity", cap, DERIVED, ["capacity", "capacity_unit"],
                         engine_note="AMBIGUOUS_QUALITY", notes="capacity(m3)")
    # confirmed source (WO-ENG-003) fallback: water tank tonnage; water 1 t ~= 1 m3
    ton = _num(ci.get("water_tank_ton"))
    if ton is not None:
        return AxisValue("storage_capacity", ton, DERIVED, ["water_tank_ton"],
                         engine_note="AMBIGUOUS_QUALITY", notes="water_tank ton~=m3 (water medium)")
    return AxisValue("storage_capacity", None, GAP, [], engine_note="GAP", notes="no storage input")


def build_monetary_value(ci: Dict[str, Any]) -> AxisValue:
    # target unit = won (fac_col construction_amount)
    won = _num(ci.get("construction_amount"))
    if won is not None:
        return AxisValue("monetary_value", won, DIRECT, ["construction_amount"],
                         engine_note="AMBIGUOUS_QUALITY", notes="won direct")
    for k in ("contract_amount_eok", "project_amount"):  # eok -> won
        eok = _num(ci.get(k))
        if eok is not None:
            return AxisValue("monetary_value", eok * 1e8, DERIVED, [k],
                             engine_note="AMBIGUOUS_QUALITY", notes="eok*1e8 -> won")
    return AxisValue("monetary_value", None, GAP, [], engine_note="GAP", notes="no amount input")


# --- scope axes -------------------------------------------------------------
def build_facility_type(ci: Dict[str, Any],
                        fire_target_map: Optional[Dict[str, Any]] = None) -> AxisValue:
    code = ci.get("building_use_type") or ci.get("use_code")
    used = ["building_use_type"] if ci.get("building_use_type") else (
        ["use_code"] if ci.get("use_code") else [])
    if code is None:
        return AxisValue("facility_type", None, GAP, [], engine_note="GAP", notes="no use code")
    # augment: fire-target derivation (only if a verified map is injected)
    if fire_target_map is not None and code in fire_target_map:
        return AxisValue("facility_type", fire_target_map[code], LOOKUP, used + ["fire_target_map"],
                         engine_note="SCOPE", notes="fire-target derived")
    return AxisValue("facility_type", code, DIRECT if used and used[0] == "building_use_type" else FALLBACK,
                     used, engine_note="SCOPE", notes="use code passthrough")


def build_process_type(ci: Dict[str, Any],
                       process_map: Optional[Dict[str, Any]] = None) -> AxisValue:
    ksic = ci.get("ksic_major") or ci.get("ksic_code")
    used = ["ksic_major"] if ci.get("ksic_major") else (["ksic_code"] if ci.get("ksic_code") else [])
    augmented: List[Any] = []
    if process_map is not None:
        for p in (ci.get("process_list") or []):
            key = p.get("type") if isinstance(p, dict) else p
            if key in process_map:
                augmented.append(process_map[key])
    if ksic is None and not augmented:
        return AxisValue("process_type", None, GAP, [], engine_note="GAP", notes="no ksic/process")
    if augmented:
        vals = [ksic] + augmented if ksic else augmented
        return AxisValue("process_type", vals, LOOKUP, used + ["process_list", "process_map"],
                         engine_note="SCOPE", notes="ksic + augmented processes")
    return AxisValue("process_type", ksic, DIRECT if used and used[0] == "ksic_major" else FALLBACK,
                     used, engine_note="SCOPE", notes="ksic passthrough")


# --- equipment (no fac_col; produced for future join) -----------------------
# Default has_* -> equipment label map, grounded in diagnosis_input_fields
# (field_group 위험물/전기/수질환경 boolean equipment fields). Labels are the
# literal flag meaning, not invented domain codes. Override via flag_map arg;
# map to system_codes 설비유형 codes via code_map arg.
DEFAULT_EQUIPMENT_FLAG_MAP: Dict[str, str] = {
    "has_boiler": "boiler",
    "has_emergency_gen": "emergency_generator",
    "has_gas": "gas_facility",
    "has_high_pressure_gas": "high_pressure_gas",
    "has_hazmat_storage": "hazmat_storage",
    "has_water_tank": "water_tank",
}


def build_equipment_type(ci: Dict[str, Any],
                         flag_map: Optional[Dict[str, Any]] = None,
                         code_map: Optional[Dict[str, Any]] = None) -> AxisValue:
    if flag_map is None:
        flag_map = DEFAULT_EQUIPMENT_FLAG_MAP
    types: List[Any] = []
    used: List[str] = []
    # normalize: extract from equipment_list
    for e in (ci.get("equipment_list") or []):
        t = e.get("type") if isinstance(e, dict) else e
        if t is not None:
            types.append(t)
    if types:
        used.append("equipment_list")
    # augment: has_* flags -> equipment types (only with injected flag_map)
    if flag_map is not None:
        for flag, present in ci.items():
            if flag.startswith("has_") and present and flag in flag_map:
                types.append(flag_map[flag])
                if "has_flags" not in used:
                    used.append("has_flags")
    # augment: normalize labels -> system_codes 설비유형 codes (injected code_map)
    if code_map is not None and types:
        types = [code_map.get(t, t) for t in types]
        used.append("code_map")
    if not types:
        return AxisValue("equipment_type", None, GAP, [], engine_note="NO_FAC_COL",
                         notes="no equipment input")
    method = LOOKUP if (flag_map or code_map) else DIRECT
    return AxisValue("equipment_type", sorted(set(map(str, types))), method, used,
                     engine_note="NO_FAC_COL", notes="produced; engine has no fac_col (needs join)")


# --- collection-gap axes ----------------------------------------------------
def _gap(axis: str, note: str) -> AxisValue:
    return AxisValue(axis, None, GAP, [], engine_note="GAP", notes=note)


def build_voltage_level(ci: Dict[str, Any]) -> AxisValue:
    # Confirmed source (WO-ENG-003): transformer_capacity_kva is voltage_level's
    # FIELD_MAP source column. Priority: explicit voltage_level -> transformer kVA.
    v, k = _first_num(ci, ["voltage_level", "transformer_capacity_kva"])
    if v is not None:
        return AxisValue("voltage_level", v,
                         DIRECT if k == "voltage_level" else FALLBACK, [k],
                         engine_note="AMBIGUOUS_QUALITY",
                         notes="from transformer_capacity_kva" if k != "voltage_level" else "voltage supplied")
    return _gap("voltage_level", "no voltage_level / transformer_capacity_kva")


def build_concentration_level(ci: Dict[str, Any]) -> AxisValue:
    return _gap("concentration_level", "collection gap: no concentration input")


def build_distance_value(ci: Dict[str, Any]) -> AxisValue:
    return _gap("distance_value", "collection gap: no distance input")


# --- registry ---------------------------------------------------------------
BUILDERS: Dict[str, Callable[..., AxisValue]] = {
    "employee_count": build_employee_count,
    "area_size": build_area_size,
    "power_capacity": build_power_capacity,
    "storage_capacity": build_storage_capacity,
    "monetary_value": build_monetary_value,
    "facility_type": build_facility_type,
    "process_type": build_process_type,
    "equipment_type": build_equipment_type,
    "voltage_level": build_voltage_level,
    "concentration_level": build_concentration_level,
    "distance_value": build_distance_value,
}


def build_all(ci: Dict[str, Any], **maps: Any) -> Dict[str, AxisValue]:
    """Run every axis builder. `maps` may carry fire_target_map / process_map /
    flag_map / code_map for the augmentable axes; absent -> augmentation skipped."""
    out: Dict[str, AxisValue] = {}
    for axis, fn in BUILDERS.items():
        if axis == "facility_type":
            out[axis] = fn(ci, fire_target_map=maps.get("fire_target_map"))
        elif axis == "process_type":
            out[axis] = fn(ci, process_map=maps.get("process_map"))
        elif axis == "equipment_type":
            out[axis] = fn(ci, flag_map=maps.get("flag_map"), code_map=maps.get("code_map"))
        else:
            out[axis] = fn(ci)
    return out


def facility_view(ci: Dict[str, Any], **maps: Any) -> Dict[str, Any]:
    """{fac_col: value} for axes that produced a value AND have a fac_col."""
    return {
        av.fac_col: av.value
        for av in build_all(ci, **maps).values()
        if av.value is not None and av.fac_col
    }
