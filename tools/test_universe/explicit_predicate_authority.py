"""Owner-approved E2E companion authority for CORE22 construction predicates.

WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001

This is OWNER_APPROVED_E2E_FIXTURE_FACT, not a production derivation rule.
Does not read sector / construction_type / construction_type_code / order_type
/ subcon_workers to compute booleans.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

PREDICATE_NAMES = (
    "is_construction",
    "is_relationship_contractor",
    "is_civil_construction",
)

AUTHORITY_MISSING = "E2E_FIXTURE_AUTHORITY_MISSING"
DEFAULT_AUTHORITY_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "canonical"
    / "test-universe"
    / "core22_explicit_predicate_authority_v1.json"
)


class FixtureAuthorityError(RuntimeError):
    """Fail closed before HTTP. Message is a deterministic code."""


def _fail(code: str = AUTHORITY_MISSING) -> None:
    raise FixtureAuthorityError(code)


def load_authority_document(path: str | Path | None = None) -> dict:
    loc = Path(path) if path is not None else DEFAULT_AUTHORITY_PATH
    if not loc.is_file():
        _fail()
    try:
        data = json.loads(loc.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail()
    if not isinstance(data, dict):
        _fail()
    return data


def build_authority_index(document: Mapping[str, Any]) -> Dict[str, Dict[str, bool]]:
    if document.get("status") != "APPROVED":
        _fail()
    if document.get("authority_type") != "OWNER_APPROVED_E2E_FIXTURE_FACT":
        _fail()
    rows = document.get("profiles")
    if not isinstance(rows, list) or len(rows) != 27:
        _fail()
    index: Dict[str, Dict[str, bool]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            _fail()
        pid = row.get("profile_id")
        if not isinstance(pid, str) or not pid or pid in index:
            _fail()
        facts: Dict[str, bool] = {}
        for name in PREDICATE_NAMES:
            if name not in row:
                _fail()
            val = row[name]
            if type(val) is not bool:
                _fail()
            facts[name] = val
        index[pid] = facts
    if len(index) != 27:
        _fail()
    return index


def load_approved_authority_index(path: str | Path | None = None) -> Dict[str, Dict[str, bool]]:
    return build_authority_index(load_authority_document(path))


def require_construction_facts(
    profile_id: str,
    authority_index: Optional[Mapping[str, Mapping[str, bool]]],
) -> Dict[str, bool]:
    if not profile_id or authority_index is None:
        _fail()
    row = authority_index.get(profile_id)
    if not isinstance(row, Mapping):
        _fail()
    facts: Dict[str, bool] = {}
    for name in PREDICATE_NAMES:
        if name not in row:
            _fail()
        val = row[name]
        if type(val) is not bool:
            _fail()
        facts[name] = val
    return facts
