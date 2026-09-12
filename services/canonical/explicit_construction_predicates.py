"""Explicit CORE22 construction predicates — copy only, never derive.

WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001.

sector / construction_type / construction_type_code / order_type /
has_subcontractor / subcon_workers 로부터 추론하지 않는다.
missing != false. False is a stored value.
"""
from __future__ import annotations

from typing import Any, Dict

EXPLICIT_CONSTRUCTION_PREDICATES = (
    "is_construction",
    "is_relationship_contractor",
    "is_civil_construction",
)


def collect_explicit_construction_predicates(body: Any) -> Dict[str, bool]:
    """Return only user/DB-supplied bool facts. Skip None. Do not invent False."""
    fd = getattr(body, "form_data", None) or {}
    if not isinstance(fd, dict):
        fd = {}
    out: Dict[str, bool] = {}
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        val = getattr(body, name, None)
        if val is None:
            val = fd.get(name)
        if isinstance(val, bool):
            out[name] = val
    return out
