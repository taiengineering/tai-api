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

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from services.material_source.projector import project_factory_material_rows
from services.material_source.registry import ALLOWED_CLASSIFICATION_CODES


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
