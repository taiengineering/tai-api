"""Explicit CORE22 construction predicates — copy only, never derive.

WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001
WO-SM-CORE22-CONSTRUCTION-PREDICATE-SERVER-FAIL-CLOSED-001
WO-LFR-OBJ-S01-P1-001

sector / construction_type / construction_type_code / order_type /
has_subcontractor / subcon_workers 로부터 추론하지 않는다.
missing != false. False is a stored value.

S01 gate change (WO-LFR-OBJ-S01-P1-001):
  OLD: CONSTRUCTION → is_construction required (user explicit boolean)
  NEW: CONSTRUCTION → appendix3_item_no==49 → child predicates required
  is_construction: still collected for legacy compat; no longer the parent gate.
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
    WO-LFR-OBJ-S01-P1-001: also exposes appendix3_item_no for child gate.
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
    item = data.get("appendix3_item_no")
    kwargs["appendix3_item_no"] = item if type(item) is int else None
    return SimpleNamespace(**kwargs)


def missing_explicit_construction_predicates(body: Any, sector: Any) -> List[str]:
    """Return missing child predicate fields. Empty list = gate PASS.

    Non-CONSTRUCTION sectors are not gated.
    CONSTRUCTION + appendix3_item_no==49: is_relationship_contractor and
    is_civil_construction are required (S01 child predicates).
    is_construction is no longer the parent gate — appendix3_item_no is.

    WO-LFR-OBJ-S01-P1-001: item_no absent handled by appendix3 completeness gate.
    """
    if normalize_sector_db(str(sector or "")) != "CONSTRUCTION":
        return []
    item_no = getattr(body, "appendix3_item_no", None)
    if item_no is None:
        fd = getattr(body, "form_data", None) or {}
        if isinstance(fd, dict):
            item_no = fd.get("appendix3_item_no")
    if type(item_no) is not int or item_no != 49:
        # item absent or non-49: children not gated here
        return []
    facts = collect_explicit_construction_predicates(body)
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
