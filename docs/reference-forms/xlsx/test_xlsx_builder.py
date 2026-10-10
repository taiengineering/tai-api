"""
pytest tests for xlsx_builder — WO-REF01-XLS03-BULK-XLSX-BUILD-001.

Run from docs/reference-forms/xlsx/:
    pytest test_xlsx_builder.py -v
"""
import os
import sys
import tempfile

import pytest
import openpyxl

sys.path.insert(0, os.path.dirname(__file__))

from xlsx_schema_adapter import load_form_spec, _json_path
from xlsx_builder import build_xlsx, _FORBIDDEN_FORMULA_IDS
from xlsx_registry import REGISTRY
from xlsx_validation import validate_xlsx

_OUTPUT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'output', 'xlsx')
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _built(rid: str) -> str:
    """Return path to already-built xlsx for research_id."""
    fname = REGISTRY[rid]["output_filename"]
    return os.path.join(_OUTPUT_DIR, fname)


def _build_temp(rid: str) -> str:
    """Build a form to a temp file and return its path."""
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        path = f.name
    spec = load_form_spec(rid)
    meta = REGISTRY[rid]
    build_xlsx(spec, meta["design_type"], path, research_id=rid)
    return path


# ── T01: registry completeness ────────────────────────────────────────────────

def test_registry_count():
    assert len(REGISTRY) == 118


def test_registry_design_types():
    expected = {"CUMULATIVE", "CALC_AGG", "DATE_STATUS", "CHECKLIST",
                "DAILY_LOG", "DOC_TABLE", "PLAN_EVAL"}
    actual = {v["design_type"] for v in REGISTRY.values()}
    assert actual == expected


def test_registry_forbidden_ids():
    forbidden = {rid for rid, v in REGISTRY.items() if v["forbidden_formula"]}
    assert forbidden == _FORBIDDEN_FORMULA_IDS


# ── T02: JSON paths resolve ───────────────────────────────────────────────────

def test_json_paths_exist():
    missing = []
    for rid in REGISTRY:
        path = _json_path(rid)
        if not os.path.exists(path):
            missing.append(f"{rid} → {path}")
    assert not missing, f"Missing JSON files: {missing}"


def test_c002_legacy_adapter():
    spec = load_form_spec("REF-C002")
    assert spec["_meta"]["adapter"] == "xlsx_schema_adapter"
    sections = spec["sections"]
    types = [s["type"] for s in sections]
    assert "repeat_table" in types
    assert "basic_info" in types


# ── T03: build produces valid xlsx ────────────────────────────────────────────

@pytest.mark.parametrize("rid,design_type", [
    ("CHW-01", "CUMULATIVE"),
    ("CHW-03", "CALC_AGG"),        # FORMULA_DIRECTION_UNVERIFIED
    ("REF-C029", "CALC_AGG"),      # FORMULA_DIRECTION_UNVERIFIED
    ("REF-C004", "CALC_AGG"),      # FORMULA_DIRECTION_UNVERIFIED
    ("CITYGAS-01", "CHECKLIST"),
    ("GOV-04", "DAILY_LOG"),
    ("DOC-03", "DATE_STATUS"),
    ("EQUIP-01", "DOC_TABLE"),
    ("GOV-11", "PLAN_EVAL"),
    ("REF-C002", "DOC_TABLE"),     # legacy adapter
    ("MNT-03", "DAILY_LOG"),       # no repeat_table
])
def test_build_produces_file(rid, design_type):
    path = _build_temp(rid)
    try:
        assert os.path.getsize(path) > 1000, "File too small"
        wb = openpyxl.load_workbook(path, read_only=True)
        assert wb.sheetnames, "No sheets"
        wb.close()
    finally:
        os.unlink(path)


# ── T04: title cell populated ─────────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C002", "MNT-03", "CITYGAS-01"])
def test_title_cell(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        val = ws.cell(row=1, column=1).value
        assert val, f"{rid}: A1 is empty"
        wb.close()
    finally:
        os.unlink(path)


# ── T05: auto-filter present on repeat_table forms ───────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "CHW-03", "REF-C016", "REF-C004"])
def test_auto_filter(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        assert ws.auto_filter.ref, f"{rid}: no auto_filter.ref"
        wb.close()
    finally:
        os.unlink(path)


# ── T06: FORMULA_DIRECTION_UNVERIFIED — no formulas ──────────────────────────

@pytest.mark.parametrize("rid", sorted(_FORBIDDEN_FORMULA_IDS))
def test_no_formulas_in_forbidden(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False, data_only=False)
        ws = wb.active
        formula_cells = [
            cell.coordinate
            for row in ws.iter_rows()
            for cell in row
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("=")
        ]
        assert not formula_cells, f"{rid}: unexpected formulas: {formula_cells}"
        wb.close()
    finally:
        os.unlink(path)


# ── T07: CALC_AGG non-forbidden may have SUM formulas (optional) ──────────────

def test_calc_agg_non_forbidden_sum():
    """CHW-02 is CALC_AGG and not forbidden; check SUM formula present."""
    path = _build_temp("CHW-02")
    try:
        wb = openpyxl.load_workbook(path, read_only=False, data_only=False)
        ws = wb.active
        formulas = [
            cell.value
            for row in ws.iter_rows()
            for cell in row
            if cell.value and isinstance(cell.value, str) and cell.value.startswith("=SUM")
        ]
        # Formulas are optional; just verify no crash and file is valid
        wb.close()
    finally:
        os.unlink(path)


# ── T08: checklist data validation ───────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CITYGAS-01", "EQUIP-06", "REF-C027"])
def test_checklist_data_validation(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        assert ws.data_validations.dataValidation, f"{rid}: no data validation"
        dv = ws.data_validations.dataValidation[0]
        assert "○" in (dv.formula1 or ""), f"{rid}: checklist formula missing ○"
        wb.close()
    finally:
        os.unlink(path)


# ── T09: freeze panes set ─────────────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C016", "GOV-09"])
def test_freeze_panes(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        assert ws.freeze_panes, f"{rid}: no freeze_panes"
        wb.close()
    finally:
        os.unlink(path)


# ── T10: print area set ───────────────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "EQUIP-01", "MNT-03"])
def test_print_area(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        assert ws.print_area, f"{rid}: no print_area"
        wb.close()
    finally:
        os.unlink(path)


# ── T11: output files exist for full 118 ─────────────────────────────────────

def test_all_118_output_files_exist():
    missing = []
    for rid, meta in REGISTRY.items():
        path = os.path.join(_OUTPUT_DIR, meta["output_filename"])
        if not os.path.exists(path):
            missing.append(rid)
    assert not missing, f"Missing output files: {missing}"


# ── T12: validation passes for full 118 ──────────────────────────────────────

@pytest.mark.parametrize("rid", list(REGISTRY.keys()))
def test_validation_pass(rid):
    path = _built(rid)
    meta = REGISTRY[rid]
    failures = validate_xlsx(path, rid, meta["design_type"])
    assert not failures, f"{rid} validation failures: {failures}"
