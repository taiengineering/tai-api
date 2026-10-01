"""CST process source projector — Owner-approved process mappings (SEM-P0-01A-R4).

Pure projector: no DB reads.  Caller provides work_type_code list read from
kcsc_process_master; this function emits boolean LEG input fields.

Frozen registry: modifications require SEM semantic review + Owner approval.
BLK-009 (has_blasting) is NOT in this registry until its LEG target-side
repair object is resolved.
"""
from __future__ import annotations

# Owner-approved source→target mappings.
# Key = (source_table, work_type_code); value = LEG input field name.
# MAP-01: CONFINED_SPACE → performs_confined_space_work  (SEM-P0-01A-R4, 2026-10-01)
# MAP-02: TEMP_ELECTRIC  → performs_electrical_work       (SEM-P0-01A-R4, 2026-10-01)
# BLK-008: EXCAVATION    → has_excavation                 (WO-BLK008, 2026-10-02)
_APPROVED_PROCESS_MAPPINGS_V1: dict[tuple[str, str], str] = {
    ("kcsc_process_master", "CONFINED_SPACE"): "performs_confined_space_work",
    ("kcsc_process_master", "TEMP_ELECTRIC"):  "performs_electrical_work",
    ("kcsc_process_master", "EXCAVATION"):     "has_excavation",
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
