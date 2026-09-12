"""Explicit CORE22 construction predicates — copy only, never derive.

WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001
WO-SM-CORE22-CONSTRUCTION-PREDICATE-SERVER-FAIL-CLOSED-001

sector / construction_type / construction_type_code / order_type /
has_subcontractor / subcon_workers 로부터 추론하지 않는다.
missing != false. False is a stored value.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from fastapi import HTTPException

from services.legal_rules import normalize_sector_db

EXPLICIT_CONSTRUCTION_PREDICATES = (
    "is_construction",
    "is_relationship_contractor",
    "is_civil_construction",
)

ERROR_CODE = "CONSTRUCTION_EXPLICIT_PREDICATE_REQUIRED"
_CHILD_PREDICATES = (
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


def stored_explicit_predicate_body(input_data: Any) -> Any:
    """Restore collector-compatible body from persisted input_data.

    Uses input_data top-level explicit bools, then raw_structured_input.form_data.
    Does not read sector / construction_type / order_type / has_subcontractor.
    """
    data = input_data if isinstance(input_data, dict) else {}
    rsi = data.get("raw_structured_input")
    if not isinstance(rsi, dict):
        rsi = {}
    fd = rsi.get("form_data")
    if not isinstance(fd, dict):
        fd = {}
    kwargs: Dict[str, Any] = {"form_data": fd}
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        val = data.get(name)
        kwargs[name] = val if isinstance(val, bool) else None
    return SimpleNamespace(**kwargs)


def missing_explicit_construction_predicates(body: Any, sector: Any) -> List[str]:
    """Return missing exact-name fields. Empty list = gate PASS.

    Non-CONSTRUCTION sectors are not gated. False is answered. None/missing is not.
    Strings/numbers are not explicit bools (same as collect).
    """
    if normalize_sector_db(str(sector or "")) != "CONSTRUCTION":
        return []
    facts = collect_explicit_construction_predicates(body)
    if "is_construction" not in facts:
        return ["is_construction"]
    if facts["is_construction"] is False:
        return []
    missing: List[str] = []
    for name in _CHILD_PREDICATES:
        if name not in facts:
            missing.append(name)
    return missing


def validate_explicit_construction_predicates(body: Any, sector: Any) -> None:
    missing = missing_explicit_construction_predicates(body, sector)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"code": ERROR_CODE, "missing_fields": missing},
        )
