"""Material Source → LEG canonical fact adapter (per-factory boolean presence).

WO-OBS009-CANONICAL-PSR-BATCH-001 / OPTION A (GPT decision).

Layer separation:
  Source contract   = classification triples
                      {material_key, classification_code, source_ref}
  Canonical contract = per-factory boolean presence facts

This module ONLY translates the source contract into the canonical contract.
It does not redesign the material source master, the projector contract,
the DB schema, admin, or legal classification authority.

Invariants:
  * missing != false (emit True only; omit absence)
  * no free-text expansion; classification_code is authority
  * one adapter path; no new family-specific evaluators
  * fail-closed on upstream read failure (propagate, do not convert to empty
    or to booleans-set-to-false)
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from services.material_source.projector import project_factory_material_rows
from services.material_source.registry import ALLOWED_CLASSIFICATION_CODES
from services.material_source.store import catalog_index


CLASSIFICATION_TO_CANONICAL: Dict[str, str] = {
    "MANAGED_HAZARDOUS_SUBSTANCE":         "is_managed_hazardous_substance",
    "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE": "is_permit_required_hazardous_substance",
    "SPECIAL_MANAGEMENT_SUBSTANCE":        "is_special_management_substance",
}

CANONICAL_FIELDS = frozenset(CLASSIFICATION_TO_CANONICAL.values())


def project_material_canonical_facts(
    classifications: Optional[Iterable[Mapping[str, Any]]],
) -> Dict[str, bool]:
    """Reduce projected classification triples to per-factory canonical booleans.

    Only emits True. A classification not present in the input is ABSENT
    (i.e., the key is omitted). This is the LEG "missing != false" contract.

    Unknown classification codes are ignored (authority is closed under
    ALLOWED_CLASSIFICATION_CODES; the adapter never invents booleans).
    """
    out: Dict[str, bool] = {}
    for item in classifications or ():
        code = item.get("classification_code")
        if not isinstance(code, str):
            continue
        if code not in ALLOWED_CLASSIFICATION_CODES:
            continue
        canonical = CLASSIFICATION_TO_CANONICAL.get(code)
        if canonical is None:
            continue
        out[canonical] = True
    return out


def project_material_canonical_facts_from_rows(
    rows: Optional[Iterable[Mapping[str, Any]]],
    *,
    authority_dir=None,
) -> Dict[str, bool]:
    """Convenience: load classifications via the existing projector then reduce.

    Upstream read failure (catalog load, etc.) propagates unchanged from
    project_factory_material_rows — the adapter must not convert failure
    into an empty-facts result nor into booleans-set-to-false.
    """
    projected = project_factory_material_rows(rows, authority_dir=authority_dir)
    return project_material_canonical_facts(projected.get("material_classifications"))


class MaterialCanonicalMergeConflict(ValueError):
    """Explicit diagnosis input disagrees with material-derived canonical fact.

    Mirrors WorkSourceMergeConflict shape; explicit input is kept and the
    canonical fact is NOT overwritten. The conflict record is surfaced
    as source-level evidence.
    """

    def __init__(self, conflicts):
        super().__init__("MATERIAL_CANONICAL_CONFLICT")
        self.conflicts = list(conflicts)


def merge_material_canonical_into_facts(
    explicit: Mapping[str, Any],
    classifications: Optional[Iterable[Mapping[str, Any]]] = None,
    projected: Optional[Mapping[str, bool]] = None,
):
    """Return (merged_facts, conflicts). Mirrors work_source/merge.py policy.

    Priority: explicit > projected. Same value = keep. Disagreement = conflict.
    Absent projected canonical fact is never injected as False.
    """
    merged: Dict[str, Any] = dict(explicit or {})
    facts = (
        dict(projected)
        if projected is not None
        else project_material_canonical_facts(classifications)
    )
    conflicts = []
    for key, val in facts.items():
        if key not in merged:
            merged[key] = val
            continue
        existing = merged[key]
        if existing == val:
            continue
        conflicts.append(
            {
                "field": key,
                "explicit": existing,
                "projected": val,
                "reason": (
                    "MATERIAL_CANONICAL_CONFLICT: explicit diagnosis input kept; "
                    "material-derived canonical fact not applied"
                ),
            }
        )
    return merged, conflicts


def merge_or_raise(
    explicit: Mapping[str, Any],
    classifications: Optional[Sequence[Mapping[str, Any]]] = None,
    projected: Optional[Mapping[str, bool]] = None,
) -> Dict[str, Any]:
    merged, conflicts = merge_material_canonical_into_facts(
        explicit, classifications=classifications, projected=projected
    )
    if conflicts:
        raise MaterialCanonicalMergeConflict(conflicts)
    return merged


# WO-A5-FC001-TRACK1-SOURCE-TRANSPORT-IMPLEMENT-001: FC-001 per-row synthesis.
# (synthetic_field, classification_code_filter, mode_code)
# classification_code_filter=None → any active row regardless of classification.
_FC001_ROW_SPEC: Tuple[Tuple[str, Optional[str], str], ...] = (
    ("fc001_managed_indoor_handling",       "MANAGED_HAZARDOUS_SUBSTANCE",         "INDOOR_HANDLING"),
    ("fc001_managed_manufacture_or_use",    "MANAGED_HAZARDOUS_SUBSTANCE",         "MANUFACTURE_OR_USE"),
    ("fc001_managed_storage_transport",     "MANAGED_HAZARDOUS_SUBSTANCE",         "STORAGE_TRANSPORT"),
    ("fc001_managed_tank_equipment_work",   "MANAGED_HAZARDOUS_SUBSTANCE",         "TANK_EQUIPMENT_WORK"),
    ("fc001_permit_manufacture_or_use",     "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE", "MANUFACTURE_OR_USE"),
    ("fc001_permit_storage_transport",      "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE", "STORAGE_TRANSPORT"),
)


def _fc001_row_state(
    qualifying: List[Mapping[str, Any]],
    target_mode: str,
) -> Optional[bool]:
    """True/False/None(omit→UNKNOWN) for one mode across qualifying rows.

    True   — at least one row has target_mode in handling_mode_codes.
    False  — qualifying rows exist and all have explicit modes that exclude target_mode.
    None   — qualifying rows exist but some have NULL handling_mode_codes (not yet entered).
    """
    if not qualifying:
        return None  # no qualifying rows → cannot confirm or deny (UNKNOWN)
    has_null = False
    for row in qualifying:
        hm = row.get("handling_mode_codes")
        if hm is None:
            has_null = True
        elif target_mode in hm:
            return True
    return None if has_null else False


def project_material_fc001_facts(
    rows: Optional[Iterable[Mapping[str, Any]]],
    *,
    authority_dir=None,
) -> Dict[str, Any]:
    """Per-row FC-001 HAZARDOUS_MATERIAL_HANDLING_MODE synthesis.

    Reads classification codes per row via material_master_key → catalog lookup,
    then checks handling_mode_codes for each (classification, mode) pair.
    Tri-state per pair: True/False in output, None = omit (LEG UNKNOWN).
    Only active rows are considered (is_active=True).
    """
    active_rows = [r for r in (rows or ()) if r.get("is_active") is True]
    if not active_rows:
        return {}

    idx = catalog_index(authority_dir)
    cls_by_key = idx["classifications_by_key"]

    row_cls: List[Set[str]] = []
    for row in active_rows:
        key = row.get("material_master_key")
        if isinstance(key, str) and key.strip():
            hits = cls_by_key.get(key) or []
            codes: Set[str] = {h["classification_code"] for h in hits if h.get("active") is not False}
        else:
            codes = set()
        row_cls.append(codes)

    out: Dict[str, Any] = {}
    for field, cls_filter, mode in _FC001_ROW_SPEC:
        if cls_filter is None:
            qualifying = active_rows
        else:
            qualifying = [r for r, codes in zip(active_rows, row_cls) if cls_filter in codes]
        state = _fc001_row_state(qualifying, mode)
        if state is True:
            out[field] = True
        elif state is False:
            out[field] = False
        # None → omit (UNKNOWN)
    return out
