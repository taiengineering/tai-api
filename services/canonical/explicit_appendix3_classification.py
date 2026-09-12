"""Explicit Appendix3 item → Published AP01~05 Runtime Leaf projection.

WO-SM-CORE22-AP01-05-EXPLICIT-APPENDIX3-INPUT-CONTRACT-001
WO-SM-CORE22-AP01-05-APPENDIX3-SERVER-FAIL-CLOSED-001

Canonical source is the user-selected 별표 3 호 (`appendix3_item_no`).
The four group booleans are representation expansion of that one legal fact,
not a new inference and not a user-supplied Runtime authority.

BUILDING / INDUSTRIAL (after normalize_sector_db) require explicit source
before disclaimer / quota / Runtime. CONSTRUCTION and SPECIAL_FACILITY are
not gated here.

NOT: KSIC mapping, sector mapping, industry_type, building_use_type.
NOT: item 49 → is_construction, item ≤48 → is_construction=false.
missing ≠ false. KSIC / internal leaves cannot satisfy the completeness gate.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fastapi import HTTPException

from services.legal_rules import normalize_sector_db

APPENDIX3_LAW_VERSION_ID = "1fa1f5af-3575-461d-8d8c-4389d0e128d8"
APPENDIX3_APPENDIX_NO = "별표 3"
APPENDIX3_LAW_ID = "5562eb48-01d9-4d53-9a8a-1018e79b34c0"

APPENDIX3_ITEM_MIN = 1
APPENDIX3_ITEM_MAX = 49

# Internal Runtime Leaves. Client must never supply these as authority.
APPENDIX3_INTERNAL_LEAVES = (
    "is_appendix3_1_27",
    "is_appendix3_28_48",
    "is_appendix3_item_37",
    "is_appendix3_item_40",
)

# Published AP01~05 exact names. Injected by server projection only.
APPENDIX3_RUNTIME_LEAVES = APPENDIX3_INTERNAL_LEAVES + ("is_real_estate_management",)

SOURCE_ITEM_FIELD = "appendix3_item_no"
SOURCE_SUBTYPE_FIELD = "is_real_estate_management"

ERROR_ITEM_TYPE = "APPENDIX3_ITEM_NO_TYPE"
ERROR_ITEM_RANGE = "APPENDIX3_ITEM_NO_RANGE"
ERROR_ITEM_CONFLICT = "APPENDIX3_ITEM_NO_CONFLICT"
ERROR_SUBTYPE_TYPE = "APPENDIX3_SUBTYPE_TYPE"
ERROR_SUBTYPE_CONFLICT = "APPENDIX3_SUBTYPE_CONFLICT"
ERROR_REQUIRED = "APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED"

# Completeness gate scope only. Not a legal-item inference from sector.
GATED_NORMALIZED_SECTORS = frozenset({"BUILDING", "INDUSTRIAL"})


class Appendix3SourceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_strict_int(value: Any) -> bool:
    """JSON integer only. bool is a subclass of int in Python — reject it."""
    return type(value) is int


def is_strict_bool(value: Any) -> bool:
    return type(value) is bool


def strip_internal_projected_leaves(data: Any) -> Any:
    """Remove internal projected leaves in-place. Does not invent replacements."""
    if not isinstance(data, dict):
        return data
    for key in APPENDIX3_INTERNAL_LEAVES:
        data.pop(key, None)
    return data


def _strict_item_no(value: Any, *, present: bool) -> Optional[int]:
    if value is None:
        return None
    if not is_strict_int(value):
        raise Appendix3SourceError(
            ERROR_ITEM_TYPE,
            "appendix3_item_no must be a JSON integer 1..49 (no string/float/bool)",
        )
    if not APPENDIX3_ITEM_MIN <= value <= APPENDIX3_ITEM_MAX:
        raise Appendix3SourceError(
            ERROR_ITEM_RANGE,
            "appendix3_item_no must be in 1..49",
        )
    return value


def _strict_subtype(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if not is_strict_bool(value):
        raise Appendix3SourceError(
            ERROR_SUBTYPE_TYPE,
            "is_real_estate_management must be a JSON boolean",
        )
    return value


def _read_pair(container: Mapping[str, Any], name: str) -> Tuple[bool, Any]:
    if name not in container:
        return False, None
    return True, container.get(name)


def collect_explicit_appendix3_source(body: Any) -> Dict[str, Any]:
    """Collect explicit Appendix3 source. Top-level wins over form_data.

    Both present and unequal → FAIL (no silent override).
    Invalid types FAIL. Missing item is omitted here; completeness is
    missing_explicit_appendix3_fields / validate_explicit_appendix3_classification.
    Item 37 + missing subtype is incomplete: subtype key omitted, no invented false.
    Item != 37: subtype is not authority (omitted, not synthesized false).
    """
    fd = getattr(body, "form_data", None) or {}
    if not isinstance(fd, dict):
        fd = {}

    top_item = getattr(body, SOURCE_ITEM_FIELD, None)
    top_item_present = top_item is not None
    fd_item_present, fd_item = _read_pair(fd, SOURCE_ITEM_FIELD)
    if fd_item is None:
        fd_item_present = False

    item: Optional[int] = None
    if top_item_present and fd_item_present:
        a = _strict_item_no(top_item, present=True)
        b = _strict_item_no(fd_item, present=True)
        if a != b:
            raise Appendix3SourceError(
                ERROR_ITEM_CONFLICT,
                "appendix3_item_no top-level and form_data conflict",
            )
        item = a
    elif top_item_present:
        item = _strict_item_no(top_item, present=True)
    elif fd_item_present:
        item = _strict_item_no(fd_item, present=True)

    top_sub = getattr(body, SOURCE_SUBTYPE_FIELD, None)
    top_sub_present = top_sub is not None
    fd_sub_present, fd_sub = _read_pair(fd, SOURCE_SUBTYPE_FIELD)
    if fd_sub is None:
        fd_sub_present = False

    subtype: Optional[bool] = None
    if top_sub_present and fd_sub_present:
        a = _strict_subtype(top_sub)
        b = _strict_subtype(fd_sub)
        if a != b:
            raise Appendix3SourceError(
                ERROR_SUBTYPE_CONFLICT,
                "is_real_estate_management top-level and form_data conflict",
            )
        subtype = a
    elif top_sub_present:
        subtype = _strict_subtype(top_sub)
    elif fd_sub_present:
        subtype = _strict_subtype(fd_sub)

    out: Dict[str, Any] = {}
    if item is None:
        return out
    out[SOURCE_ITEM_FIELD] = item
    if item == 37 and subtype is not None:
        out[SOURCE_SUBTYPE_FIELD] = subtype
    return out


def collect_explicit_appendix3_source_http(body: Any) -> Dict[str, Any]:
    try:
        return collect_explicit_appendix3_source(body)
    except Appendix3SourceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc


def missing_explicit_appendix3_fields(body: Any, sector: Any) -> List[str]:
    """Return missing explicit Appendix3 source fields. Empty = completeness PASS.

    Gated only after normalize_sector_db ∈ {BUILDING, INDUSTRIAL}.
    INDUSTRY / MANUFACTURING normalize to INDUSTRIAL and are gated.
    CONSTRUCTION / SPECIAL_FACILITY are no-op.

    KSIC / sector / internal leaves never satisfy this gate.
    False is answered. missing ≠ false.
    Type / range / conflict still raise Appendix3SourceError (existing codes).
    """
    if normalize_sector_db(str(sector or "")) not in GATED_NORMALIZED_SECTORS:
        return []
    source = collect_explicit_appendix3_source(body)
    if SOURCE_ITEM_FIELD not in source:
        return [SOURCE_ITEM_FIELD]
    if source[SOURCE_ITEM_FIELD] == 37 and SOURCE_SUBTYPE_FIELD not in source:
        return [SOURCE_SUBTYPE_FIELD]
    return []


def validate_explicit_appendix3_classification(body: Any, sector: Any) -> None:
    try:
        missing = missing_explicit_appendix3_fields(body, sector)
    except Appendix3SourceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"code": ERROR_REQUIRED, "missing_fields": missing},
        )


def project_explicit_appendix3_classification(
    appendix3_item_no: Optional[int],
    is_real_estate_management: Optional[bool] = None,
) -> Dict[str, Any]:
    """Expand one explicit 호 into Published Runtime Leaf representation.

    No KSIC/sector lookup. Does not set is_construction.
    Item != 37: subtype is absent (not false).
    Item == 37 and subtype missing: four group bools present, subtype absent.
    """
    if appendix3_item_no is None:
        return {}
    if not is_strict_int(appendix3_item_no):
        raise Appendix3SourceError(
            ERROR_ITEM_TYPE,
            "appendix3_item_no must be a JSON integer 1..49 (no string/float/bool)",
        )
    if not APPENDIX3_ITEM_MIN <= appendix3_item_no <= APPENDIX3_ITEM_MAX:
        raise Appendix3SourceError(
            ERROR_ITEM_RANGE,
            "appendix3_item_no must be in 1..49",
        )

    item = appendix3_item_no
    if 1 <= item <= 27:
        out = {
            "is_appendix3_1_27": True,
            "is_appendix3_28_48": False,
            "is_appendix3_item_37": False,
            "is_appendix3_item_40": False,
        }
    elif 28 <= item <= 48:
        out = {
            "is_appendix3_1_27": False,
            "is_appendix3_28_48": True,
            "is_appendix3_item_37": item == 37,
            "is_appendix3_item_40": item == 40,
        }
    else:
        # item == 49. Representation of "not 1~48". is_construction is out of scope.
        out = {
            "is_appendix3_1_27": False,
            "is_appendix3_28_48": False,
            "is_appendix3_item_37": False,
            "is_appendix3_item_40": False,
        }

    if item == 37:
        if is_real_estate_management is None:
            return out
        if not is_strict_bool(is_real_estate_management):
            raise Appendix3SourceError(
                ERROR_SUBTYPE_TYPE,
                "is_real_estate_management must be a JSON boolean",
            )
        out["is_real_estate_management"] = is_real_estate_management
    return out


def prepare_available_and_projection(
    body: Any, available: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """FIRST SAFE INSERTION POINT helper.

    1. Collect explicit source from body (top-level / form_data).
    2. Strip internal projected leaves and subtype from external available.
    3. Return (persistable source, server projection).

    Caller must run canonical_applicability(available) AFTER this strip,
    skip APPENDIX3_RUNTIME_LEAVES, then inp.update(projection).
    """
    source = collect_explicit_appendix3_source_http(body)
    if isinstance(available, dict):
        strip_internal_projected_leaves(available)
        available.pop(SOURCE_SUBTYPE_FIELD, None)
    projection = project_explicit_appendix3_classification(
        source.get(SOURCE_ITEM_FIELD),
        source.get(SOURCE_SUBTYPE_FIELD),
    )
    return source, projection


def persist_explicit_appendix3_source(source: Mapping[str, Any]) -> Dict[str, Any]:
    """User-answered source + server law-version metadata. No projected leaves."""
    if SOURCE_ITEM_FIELD not in source:
        return {}
    out: Dict[str, Any] = {
        SOURCE_ITEM_FIELD: source[SOURCE_ITEM_FIELD],
        "appendix3_law_version_id": APPENDIX3_LAW_VERSION_ID,
    }
    if source.get(SOURCE_ITEM_FIELD) == 37 and SOURCE_SUBTYPE_FIELD in source:
        out[SOURCE_SUBTYPE_FIELD] = source[SOURCE_SUBTYPE_FIELD]
    return out


def sanitize_form_data_for_persist(
    form_data: Any, source: Mapping[str, Any]
) -> Any:
    if not isinstance(form_data, dict):
        return form_data
    fd = dict(form_data)
    strip_internal_projected_leaves(fd)
    item = source.get(SOURCE_ITEM_FIELD)
    if item != 37:
        fd.pop(SOURCE_SUBTYPE_FIELD, None)
    if item is not None:
        fd[SOURCE_ITEM_FIELD] = item
        if item == 37 and SOURCE_SUBTYPE_FIELD in source:
            fd[SOURCE_SUBTYPE_FIELD] = source[SOURCE_SUBTYPE_FIELD]
    return fd


def stored_appendix3_body(input_data: Any) -> Any:
    data = input_data if isinstance(input_data, dict) else {}
    rsi = data.get("raw_structured_input")
    if not isinstance(rsi, dict):
        rsi = {}
    fd = rsi.get("form_data")
    if not isinstance(fd, dict):
        fd = {}
    item = data.get(SOURCE_ITEM_FIELD)
    subtype = data.get(SOURCE_SUBTYPE_FIELD)
    return SimpleNamespace(
        appendix3_item_no=item if is_strict_int(item) else None,
        is_real_estate_management=subtype if is_strict_bool(subtype) else None,
        form_data=fd,
    )


def merge_projection_after_canonical(
    inp: Dict[str, Any],
    canonical: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> Dict[str, Any]:
    """Copy canonical facts except internal Appendix3 leaves, then inject projection."""
    for code, val in canonical.items():
        if code in APPENDIX3_RUNTIME_LEAVES:
            continue
        inp.setdefault(code, val)
    inp.update(projection)
    return inp
