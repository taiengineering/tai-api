"""Consumer Input Canonicalization (WO-ENG-002).

Multiple consumer input paths (anonymous input_data, public_request
facility_data / process_data / equipment_data) use different field names for
the same thing. This front layer maps them into ONE CanonicalConsumerInput so
the Axis Value Builder sees a single input schema.

STRICT SCOPE — alias only:
- No new meaning. No unit/scale conversion (that stays in the builder).
- No domain inference. No legal judgment. No Object creation.
- Only picks a value from the first present alias, in priority order.

Unchanged: FIELD_MAP, Axis Value Builder, Semantic Mapping, Engine, Runtime.
The builder is fed canonicalize(raw) and otherwise runs as committed.
"""

from __future__ import annotations

from typing import Any, Dict, List

# canonical_key -> [source aliases in priority order]
# Sources are the REAL field names observed in:
#   anonymous_diagnosis_results.input_data
#   public_diagnosis_requests.facility_data / process_data / equipment_data
ALIASES: Dict[str, List[str]] = {
    "worker_count":     ["worker_count", "workers"],
    "direct_workers":   ["direct_workers"],
    "subcon_workers":   ["subcon_workers"],
    "total_floor_area": ["total_floor_area", "floor_area"],
    "electric_capacity": ["electric_capacity", "electric_kw"],
    "building_use_type": ["building_use_type", "building_use"],
    "ksic_major":       ["ksic_major", "ksic_code"],
    "project_amount":   ["project_amount", "contract_eok", "contract_amount_eok"],
    "gas_capacity_m3":  ["gas_capacity_m3"],
    "gas_capacity_kg":  ["gas_capacity_kg"],
    "voltage_level":    ["voltage_level"],
    "equipment_list":   ["equipment_list", "equipment_data"],
    "process_list":     ["process_list", "process_data"],
}

# every source key that participates in an alias group
_ALIAS_SOURCES = {s for sources in ALIASES.values() for s in sources}


def canonicalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw consumer input (any path) into CanonicalConsumerInput.

    - For each canonical key, take the value of the first present alias.
    - Every alias source in a resolved group is consumed (not re-emitted).
    - Non-alias keys (e.g. has_* flags, sector) pass through unchanged so the
      builder's flag augmentation still works.
    Value is copied verbatim — no transformation of meaning.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    consumed: set = set()
    for canon, sources in ALIASES.items():
        for s in sources:
            if s in raw and raw[s] is not None:
                out[canon] = raw[s]
                consumed.update(sources)   # fold sibling aliases too
                break
    for k, v in raw.items():
        if k not in _ALIAS_SOURCES and k not in out:
            out[k] = v
    return out


def alias_table() -> List[Dict[str, str]]:
    """Deliverable: Alias Mapping Table as rows."""
    return [
        {"canonical": c, "aliases": " <- ".join(srcs)}
        for c, srcs in ALIASES.items()
    ]


# CanonicalConsumerInput schema (documentation): the set of canonical keys the
# builder consumes. Values are passed verbatim; types follow the builder's
# expectations (numeric coercion happens inside the builder).
CANONICAL_SCHEMA: List[str] = list(ALIASES.keys())
