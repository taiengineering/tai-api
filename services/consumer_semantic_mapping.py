"""Consumer Input → Semantic Mapping Layer (WO-IMPL-001).

Purpose
-------
Supply Consumer Input to the engine's FIELD_MAP binding_fields WITHOUT
changing Consumer Input, FIELD_MAP, or the engine core.

This module is a *standalone, pure resolver*. It does not import from or
mutate the engine. It mirrors FIELD_MAP READ-ONLY for traceability. When
wired in-repo, replace `_FIELD_MAP_MIRROR` with a read-only import:

    from services.facility_applicability_eval import FIELD_MAP

Scope (per SD-003 / WO-IMPL-001)
--------------------------------
- DIRECT axes implemented: employee_count, area_size, power_capacity
- SCOPE axes implemented:  facility_type, process_type
- Other 6 axes: NOT fabricated. Resolver returns an explicit non-delivery
  status that matches SD-003 (AMBIGUOUS_BLOCKED / NEEDS_JOIN / NO_INPUT /
  MISSING). No new Mapping Rule is invented.

Nothing here modifies: evaluate_draft_for_facility, FIELD_MAP, draft_slot,
Compiler, Runtime Core, obligation_adapter, Legal DB, Semantic DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# --- READ-ONLY mirror of services/facility_applicability_eval.py::FIELD_MAP ---
# Source of truth stays in the engine. Mirrored only so this layer can run
# standalone in tests. In-repo: import FIELD_MAP instead of mirroring.
_FIELD_MAP_MIRROR: Dict[str, Tuple[Optional[str], str]] = {
    "employee_count":      ("employee_count",          "DIRECT"),
    "area_size":           ("building_area",            "DIRECT"),
    "power_capacity":      ("electrical_capacity_kw",   "DIRECT"),
    "voltage_level":       ("transformer_capacity_kva", "AMBIGUOUS"),
    "storage_capacity":    ("gas_capacity_m3",          "AMBIGUOUS"),
    "equipment_type":      (None,                       "EQUIPMENT_JOIN"),
    "facility_type":       ("site_type",                "AMBIGUOUS"),
    "process_type":        ("ksic_code",                "AMBIGUOUS"),
    "monetary_value":      ("construction_amount",      "AMBIGUOUS"),
    "concentration_level": (None,                       "MISSING"),
    "distance_value":      (None,                       "MISSING"),
}


# --- SD-003 Mapping Rules (declarative; no new rule invented) -----------------
# kind: how the input reaches the binding_field
#   DIRECT   = pass through numeric value
#   SCOPE    = existence only (engine ignores quality for IF_SCOPE)
#   DERIVED  = unit/scale conversion needed (defined but engine-blocked)
#   LOOKUP   = needs join, no facility column
#   NONE     = no consumer input available
@dataclass(frozen=True)
class MappingRule:
    binding_field: str
    source_input: Optional[str]
    kind: str
    note: str = ""


_RULES: Dict[str, MappingRule] = {
    # DIRECT (implemented)
    "employee_count": MappingRule("employee_count", "worker_count", "DIRECT", "int passthrough"),
    "area_size":      MappingRule("area_size", "total_floor_area", "DIRECT", "m2 passthrough"),
    "power_capacity": MappingRule("power_capacity", "electric_capacity", "DIRECT", "kW passthrough"),
    # SCOPE (implemented, existence only)
    "facility_type":  MappingRule("facility_type", "building_use_type", "SCOPE", "presence -> POSSIBLE_CANDIDATE"),
    "process_type":   MappingRule("process_type", "ksic_major", "SCOPE", "KSIC presence -> POSSIBLE_CANDIDATE"),
    # DERIVED (rule defined by SD-003; engine quality=AMBIGUOUS blocks result)
    "storage_capacity": MappingRule("storage_capacity", "gas_capacity_m3", "DERIVED", "ton/L/kg<->m3, density-dependent"),
    "monetary_value":   MappingRule("monetary_value", "project_amount", "DERIVED", "eok/manwon -> won scale"),
    # LOOKUP (no fac_col; join required)
    "equipment_type": MappingRule("equipment_type", "equipment_list", "LOOKUP", "fac_col None; equipment join required"),
    # NONE (no consumer input)
    "voltage_level":       MappingRule("voltage_level", None, "NONE", "no voltage input; kVA is a different quantity"),
    "concentration_level": MappingRule("concentration_level", None, "NONE", "no input, no fac_col"),
    "distance_value":      MappingRule("distance_value", None, "NONE", "no input, no fac_col"),
}


@dataclass
class Resolution:
    """One binding_field resolution outcome (traceable)."""
    binding_field: str
    source_input: Optional[str]
    rule_kind: str
    input_value: Any = None
    resolved_value: Any = None
    fac_col: Optional[str] = None
    quality: str = ""
    engine_reachable: bool = False
    status: str = ""            # DELIVERED / AMBIGUOUS_BLOCKED / NEEDS_JOIN / NO_INPUT / MISSING
    detail: str = ""


# statuses
DELIVERED = "DELIVERED"                     # value reaches fac_col; engine compares / scope-checks
DELIVERED_AMBIGUOUS = "DELIVERED_AMBIGUOUS" # value reaches fac_col; engine returns AMBIGUOUS (quality tag)
NEEDS_JOIN = "NEEDS_JOIN"                   # fac_col None; equipment join required
NO_INPUT = "NO_INPUT"                       # fac_col exists but no valid consumer input
MISSING = "MISSING"                         # fac_col None and no input


def _eok_to_won(v: Any) -> Any:
    """억원 -> 원 scale normalization (input-side, allowed by SD-003)."""
    try:
        return float(v) * 1e8
    except (TypeError, ValueError):
        return None


def _resolve_one(binding_field: str, consumer_input: Dict[str, Any]) -> Resolution:
    rule = _RULES[binding_field]
    fac_col, quality = _FIELD_MAP_MIRROR[binding_field]
    r = Resolution(
        binding_field=binding_field,
        source_input=rule.source_input,
        rule_kind=rule.kind,
        fac_col=fac_col,
        quality=quality,
        detail=rule.note,
    )

    # No consumer input available
    if rule.kind == "NONE":
        r.status = MISSING if fac_col is None else NO_INPUT
        r.engine_reachable = False
        return r

    # No facility column -> engine reads facility[fac_col] which is absent
    if fac_col is None:
        r.status = NEEDS_JOIN if rule.kind == "LOOKUP" else MISSING
        r.engine_reachable = False
        return r

    r.input_value = consumer_input.get(rule.source_input)

    # DIRECT numeric: value passthrough, engine will compare
    if rule.kind == "DIRECT":
        r.resolved_value = r.input_value
        r.engine_reachable = r.input_value is not None
        r.status = DELIVERED if r.engine_reachable else NO_INPUT
        return r

    # SCOPE: existence only; engine ignores quality for IF_SCOPE
    if rule.kind == "SCOPE":
        present = r.input_value is not None and r.input_value != ""
        r.resolved_value = r.input_value if present else None
        r.engine_reachable = present
        r.status = DELIVERED if present else NO_INPUT
        return r

    # DERIVED: deliver the value into facility[fac_col] with input-side
    # normalization. The value DOES reach the engine; the engine then returns
    # AMBIGUOUS because FIELD_MAP quality==AMBIGUOUS (engine-core limitation,
    # out of this WO's scope). Withholding would REGRESS engine behavior.
    if rule.kind == "DERIVED":
        if r.input_value is None:
            r.status = NO_INPUT
            r.engine_reachable = False
            return r
        if binding_field == "monetary_value":
            r.resolved_value = _eok_to_won(r.input_value)   # 억원 -> 원
        else:  # storage_capacity: fac_col is m3, input already m3 -> passthrough
            r.resolved_value = r.input_value
        r.engine_reachable = True
        r.status = DELIVERED_AMBIGUOUS
        return r

    r.status = MISSING
    return r


def resolve(consumer_input: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Resolution]]:
    """Resolve consumer input into binding_field values + a full trace.

    Returns
    -------
    binding_field_values : dict
        {binding_field: resolved_value} for engine-reachable axes only.
    trace : list[Resolution]
        Per-binding_field record for human traceability / logging.
    """
    trace: List[Resolution] = [
        _resolve_one(bf, consumer_input) for bf in _FIELD_MAP_MIRROR
    ]
    binding_field_values = {
        r.binding_field: r.resolved_value for r in trace if r.engine_reachable
    }
    return binding_field_values, trace


def facility_view(consumer_input: Dict[str, Any]) -> Dict[str, Any]:
    """Engine-compatible view: {fac_col: value} for reachable axes.

    The engine reads facility[fac_col]; this is the shape it actually consumes.
    Wiring this into the live path is a separate approval (IMPL-002+).
    """
    _, trace = resolve(consumer_input)
    return {r.fac_col: r.resolved_value for r in trace if r.engine_reachable and r.fac_col}


def format_log(trace: List[Resolution]) -> str:
    """Human-readable log: Input -> Semantic Rule -> Output -> Engine 전달."""
    lines = []
    for r in trace:
        lines.append(
            f"[{r.binding_field:19}] in={r.source_input or '-':17} "
            f"({r.input_value!r:>10}) --{r.rule_kind:7}--> "
            f"fac_col={r.fac_col or '-':22} val={r.resolved_value!r:>10} "
            f"reachable={str(r.engine_reachable):5} status={r.status}"
        )
    return "\n".join(lines)
