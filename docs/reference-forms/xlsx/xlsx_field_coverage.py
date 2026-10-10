"""
FIX-D / FIX-3 / FIX-01: Field coverage verifier (v3 — individual section verification).

Key change from v2:
- sections_rendered counts individual section instances, not unique types
- Each section is verified independently, including duplicate-type sections
- text_flow paragraphs included
- Occurrence-count comparison for labels shared across sections
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import NamedTuple

import openpyxl

from xlsx_schema_adapter import load_form_spec


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _section_labels(sec: dict) -> list[str]:
    """Extract all expected text labels from a single section."""
    stype = sec.get("type", "")
    labels: list[str] = []

    if stype == "basic_info":
        for f in sec.get("fields", []):
            lbl = f.get("label", "") if isinstance(f, dict) else str(f)
            if lbl:
                labels.append(lbl)

    elif stype == "repeat_table":
        for col in sec.get("columns", []):
            lbl = col.get("label", "")
            if lbl:
                labels.append(lbl)

    elif stype == "labeled_grid":
        sec_lbl = sec.get("section_label", "")
        if sec_lbl:
            labels.append(sec_lbl)
        for row_def in sec.get("rows", []):
            for cell in row_def:
                lbl = cell.get("label", "")
                if lbl:
                    labels.append(lbl)

    elif stype == "freeform_area":
        lbl = sec.get("label") or sec.get("section_label", "")
        if lbl:
            labels.append(lbl)

    elif stype == "approval":
        sec_lbl = sec.get("label", "")
        if sec_lbl:
            labels.append(sec_lbl)
        for f in sec.get("fields", []):
            fl = f.get("label", "") if isinstance(f, dict) else str(f)
            if fl:
                labels.append(fl)

    elif stype == "text_flow":
        for para in sec.get("paragraphs", []):
            text = para.get("text", "")
            if text and text.strip():
                labels.append(text)

    return [_normalize(lbl) for lbl in labels if lbl.strip()]


def verify_field_coverage(
    form_spec: dict, xlsx_path: str, research_id: str
) -> dict:
    """
    Returns:
      {
        'research_id': str,
        'status': 'OK'|'MISSING'|'ERROR',
        'missing_fields': list[str],
        'count_mismatches': list[str],
        'sections_source': int,
        'sections_rendered': int,   # individual sections with all labels found
        'sections_missing': int,    # individual sections with ≥1 label missing
        'extra_unexpected': list[str],
      }
    """
    result = {
        "research_id": research_id,
        "status": "OK",
        "missing_fields": [],
        "count_mismatches": [],
        "sections_rendered": 0,
        "sections_missing": 0,
        "sections_source": 0,
        "extra_unexpected": [],
    }

    try:
        sections = form_spec.get("sections", [])
        result["sections_source"] = len(sections)

        if not sections:
            return result

        # Load xlsx cell texts
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        actual: Counter[str] = Counter()
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if v and isinstance(v, str) and v.strip():
                    actual[_normalize(v)] += 1
        wb.close()

        # Build overall expected counts across all sections (for count-mismatch check)
        all_expected: Counter[str] = Counter()
        for sec in sections:
            for lbl in _section_labels(sec):
                all_expected[lbl] += 1

        # Per-section verification
        sections_ok = 0
        sections_fail = 0
        all_missing: list[str] = []
        all_mismatches: list[str] = []

        # Track consumed occurrences to handle duplicates correctly
        consumed: Counter[str] = Counter()

        for sec_idx, sec in enumerate(sections):
            sec_labels = _section_labels(sec)
            if not sec_labels:
                # Sections with no labels (e.g. empty approval): count as rendered
                sections_ok += 1
                continue

            sec_missing: list[str] = []
            for lbl in sec_labels:
                consumed[lbl] += 1
                needed = consumed[lbl]
                if actual.get(lbl, 0) < needed:
                    sec_missing.append(lbl)

            if sec_missing:
                sections_fail += 1
                for lbl in sec_missing:
                    if lbl not in all_missing:
                        all_missing.append(lbl)
            else:
                sections_ok += 1

        # Overall count-mismatch check (across all sections)
        for lbl, exp_count in all_expected.items():
            found_count = actual.get(lbl, 0)
            if 0 < found_count < exp_count:
                all_mismatches.append(
                    f"{lbl} (expected>={exp_count}, found={found_count})"
                )

        result["sections_rendered"] = sections_ok
        result["sections_missing"] = sections_fail

        if all_missing:
            result["status"] = "MISSING"
            result["missing_fields"] = all_missing
        if all_mismatches:
            result["status"] = "MISSING"
            result["count_mismatches"] = all_mismatches

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
                "count_mismatches": [],
                "sections_source": 0,
                "sections_rendered": 0,
                "sections_missing": 0,
                "extra_unexpected": [],
            })
            continue
        r = verify_field_coverage(spec, xlsx_path, rid)
        results.append(r)
    return results
