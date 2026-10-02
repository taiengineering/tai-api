"""CST process + work source projector — Owner-approved mappings (SEM-P0-01A-R4 + BLK-009).

Pure projector: no DB reads.  Callers provide work_type_code lists read from
kcsc_process_master (process projection) or kcsc_work_master (work projection);
each function emits boolean LEG input fields.

Frozen registry: modifications require SEM semantic review + Owner approval.
"""
from __future__ import annotations

# Owner-approved source→target mappings.
# Key = (source_table, work_type_code); value = LEG input field name.
# MAP-01: CONFINED_SPACE → performs_confined_space_work  (SEM-P0-01A-R4, 2026-10-01)
# MAP-02: TEMP_ELECTRIC  → performs_electrical_work       (SEM-P0-01A-R4, 2026-10-01)
# BLK-008: EXCAVATION    → has_excavation                 (WO-BLK008, 2026-10-02)
# BLK-009: BLASTING      → has_blasting                   (WO-BLK009C, 2026-10-02)
_APPROVED_PROCESS_MAPPINGS_V1: dict[tuple[str, str], str] = {
    ("kcsc_process_master", "CONFINED_SPACE"): "performs_confined_space_work",
    ("kcsc_process_master", "TEMP_ELECTRIC"):  "performs_electrical_work",
    ("kcsc_process_master", "EXCAVATION"):     "has_excavation",
    ("kcsc_work_master",    "BLASTING"):       "has_blasting",
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


def project_cst_work_codes(work_type_codes: list[str]) -> dict[str, bool]:
    """Return TRUE LEG fields for the given kcsc_work_master work_type_codes.

    Absent mapping → field omitted (never synthesizes False).
    Duplicate codes are idempotent — later occurrence does not change the True.
    """
    out: dict[str, bool] = {}
    for code in (work_type_codes or []):
        if code is None:
            continue
        field = _APPROVED_PROCESS_MAPPINGS_V1.get(("kcsc_work_master", code))
        if field is not None:
            out[field] = True
    return out
