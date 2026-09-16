"""Merge projected work facts into diagnosis source facts.

Explicit request keys are never silently overwritten.
Disagreeing values become source-level conflict evidence, not LEG Runtime rules.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from services.work_source.projector import project_work_rows


class WorkSourceMergeConflict(ValueError):
    def __init__(self, conflicts: List[Dict[str, Any]]):
        super().__init__("WORK_SOURCE_CONFLICT")
        self.conflicts = conflicts


def merge_projected_into_facts(
    explicit: Mapping[str, Any],
    work_rows: Optional[Iterable[Mapping[str, Any]]] = None,
    projected: Optional[Mapping[str, bool]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return (merged_facts, conflicts).

    - projected key absent from explicit → insert
    - same value already present → keep
    - different value already present → conflict, keep explicit, do not overwrite
    """
    merged: Dict[str, Any] = dict(explicit or {})
    facts = dict(projected) if projected is not None else project_work_rows(work_rows)
    conflicts: List[Dict[str, Any]] = []
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
                "reason": "WORK_SOURCE_CONFLICT: explicit diagnosis input kept; projected work fact not applied",
            }
        )
    return merged, conflicts


def merge_or_raise(
    explicit: Mapping[str, Any],
    work_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    projected: Optional[Mapping[str, bool]] = None,
) -> Dict[str, Any]:
    merged, conflicts = merge_projected_into_facts(
        explicit, work_rows=work_rows, projected=projected
    )
    if conflicts:
        raise WorkSourceMergeConflict(conflicts)
    return merged
