"""CST process source projector — Owner-approved process mappings (SEM-P0-01A-R4).

Pure projector: no DB reads.  Caller provides work_type_code list read from
kcsc_process_master; this function emits boolean LEG input fields.

Frozen registry: modifications require SEM semantic review + Owner approval.
BLK-008 (has_excavation) and BLK-009 (has_blasting) are NOT in this registry
until their LEG target-side repair objects are resolved.
"""
from __future__ import annotations

# Owner-approved source→target mappings frozen at SEM-P0-01A-R4 (2026-10-01).
# Key = (source_table, work_type_code); value = LEG input field name.
# MAP-01: CONFINED_SPACE → performs_confined_space_work
# MAP-02: TEMP_ELECTRIC  → performs_electrical_work
_APPROVED_PROCESS_MAPPINGS_V1: dict[tuple[str, str], str] = {
    ("kcsc_process_master", "CONFINED_SPACE"): "performs_confined_space_work",
    ("kcsc_process_master", "TEMP_ELECTRIC"): "performs_electrical_work",
}


def project_cst_process_codes(work_type_codes: list[str]) -> dict[str, bool]:
    """Return TRUE LEG fields for the given kcsc_process_master work_type_codes.

    Absent mapping → field omitted (never synthesizes False).
    Duplicate codes are idempotent — later occurrence does not change the True.
    """
    out: dict[str, bool] = {}
    for code in (work_type_codes or []):
        if code is None:
            continue
        field = _APPROVED_PROCESS_MAPPINGS_V1.get(("kcsc_process_master", code))
        if field is not None:
            out[field] = True
    return out
