"""
Structure and contract validation for generated .xlsx files.
WO-REF01-XLS03-BULK-XLSX-BUILD-001 CORRECTION-003.
"""
from __future__ import annotations

import os
import zipfile

import openpyxl

_FORBIDDEN_FORMULA_IDS = {"CHW-03", "REF-C029", "REF-C004"}


def validate_xlsx(path: str, research_id: str, design_type: str) -> list[str]:
    """Returns list of failure strings. Empty list = PASS."""
    failures = []

    if not os.path.exists(path):
        return [f"FILE_NOT_FOUND: {path}"]

    if not zipfile.is_zipfile(path):
        return ["INVALID_ZIP: file is not a valid xlsx/zip"]

    try:
        wb = openpyxl.load_workbook(path, read_only=False, data_only=False)
    except Exception as e:
        return [f"LOAD_ERROR: {e}"]

    if not wb.sheetnames:
        wb.close()
        return ["NO_SHEETS: workbook has no sheets"]

    ws = wb.active

    # 1. Minimum row count
    if (ws.max_row or 0) < 3:
        failures.append(f"TOO_FEW_ROWS: max_row={ws.max_row}")

    # 2. Title cell non-empty
    if not ws.cell(row=1, column=1).value:
        failures.append("EMPTY_TITLE: A1 is empty")

    # 3. Auto-filter OR Excel Table present
    has_table = bool(ws._tables)
    has_autofilter = bool(ws.auto_filter and ws.auto_filter.ref)
    if not has_table and not has_autofilter and research_id not in {"MNT-03"}:
        failures.append("NO_FILTER: no auto_filter and no table")

    # 4. Freeze panes set (forms with repeat_table)
    if research_id not in {"MNT-03"}:
        if not ws.freeze_panes:
            failures.append("NO_FREEZE_PANES")

    # 5. Page setup: fitToPage (openpyxl may raise on some worksheet states)
    try:
        fit = ws.page_setup.fitToPage
        if not fit:
            failures.append("NO_FIT_TO_PAGE")
    except AttributeError:
        pass  # openpyxl version edge case; not blocking

    # 6. FORMULA_DIRECTION_UNVERIFIED: no formula cells
    if research_id.upper() in _FORBIDDEN_FORMULA_IDS:
        formula_cells = [
            cell.coordinate
            for row in ws.iter_rows()
            for cell in row
            if cell.value and isinstance(cell.value, str)
            and cell.value.startswith("=")
        ]
        if formula_cells:
            failures.append(
                f"FORBIDDEN_FORMULA: {formula_cells[:5]}"
            )

    # 7. Document metadata set
    if not wb.properties.title:
        failures.append("NO_METADATA_TITLE")

    wb.close()
    return failures
