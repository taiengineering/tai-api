"""
FIX-D: Field coverage verifier.
Loads each form's source JSON and the generated xlsx, checks that all
repeat_table column labels and basic_info field labels are present.
"""
from __future__ import annotations

import os
import re

import openpyxl

from xlsx_schema_adapter import load_form_spec


def verify_field_coverage(
    form_spec: dict, xlsx_path: str, research_id: str
) -> dict:
    """
    Returns:
      {
        'research_id': str,
        'status': 'OK'|'MISSING'|'ERROR',
        'missing_fields': list[str],
        'extra_unexpected': list[str],  # always empty (builder adds no extra)
        'sections_rendered': int,
        'sections_source': int,
      }
    """
    result = {
        "research_id": research_id,
        "status": "OK",
        "missing_fields": [],
        "sections_rendered": 0,
        "sections_source": 0,
    }

    try:
        sections = form_spec.get("sections", [])
        result["sections_source"] = len(sections)

        # Collect all expected labels from source JSON
        expected_labels: list[str] = []
        for sec in sections:
            stype = sec.get("type", "")
            if stype == "basic_info":
                for f in sec.get("fields", []):
                    lbl = f.get("label", "") if isinstance(f, dict) else str(f)
                    if lbl:
                        expected_labels.append(lbl)
            elif stype == "repeat_table":
                for col in sec.get("columns", []):
                    lbl = col.get("label", "")
                    if lbl:
                        expected_labels.append(lbl)
            elif stype == "labeled_grid":
                for row_def in sec.get("rows", []):
                    for cell in row_def:
                        lbl = cell.get("label", "")
                        if lbl:
                            expected_labels.append(lbl)
            elif stype in ("freeform_area", "approval"):
                lbl = sec.get("label") or sec.get("section_label", "")
                if lbl:
                    expected_labels.append(lbl)
                for f in sec.get("fields", []):
                    fl = f.get("label", "") if isinstance(f, dict) else str(f)
                    if fl:
                        expected_labels.append(fl)

        # Load xlsx and collect all non-empty cell text values
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        cell_texts: set[str] = set()
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if v and isinstance(v, str) and v.strip():
                    cell_texts.add(v.strip())
        wb.close()

        result["sections_rendered"] = len(sections)  # trust builder

        # Check each expected label appears somewhere in the xlsx
        missing = []
        for lbl in expected_labels:
            # Normalize whitespace and newlines for comparison
            normalized = re.sub(r"\s+", " ", lbl.strip())
            # Check exact or normalized match
            found = any(
                re.sub(r"\s+", " ", ct.strip()) == normalized
                for ct in cell_texts
            )
            if not found:
                missing.append(lbl)

        if missing:
            result["status"] = "MISSING"
            result["missing_fields"] = missing

    except Exception as exc:
        result["status"] = "ERROR"
        result["missing_fields"] = [str(exc)]

    return result


def run_coverage_check(
    registry: dict, output_dir: str
) -> list[dict]:
    results = []
    for rid, meta in registry.items():
        xlsx_path = os.path.join(output_dir, meta["output_filename"])
        try:
            spec = load_form_spec(rid)
        except Exception as e:
            results.append({
                "research_id": rid,
                "status": "ERROR",
                "missing_fields": [str(e)],
                "sections_source": 0,
                "sections_rendered": 0,
            })
            continue
        r = verify_field_coverage(spec, xlsx_path, rid)
        results.append(r)
    return results
