"""
pytest test suite — WO-REF01-XLS03-BULK-XLSX-BUILD-001 CORRECTION-003.
Run: pytest test_xlsx_builder.py -v

Coverage:
  T01-T03: Registry, JSON paths, basic build
  T04-T05: Title, metadata
  T06-T08: Excel Table (FIX-B)
  T09-T11: Checklist validation correct columns (FIX-A)
  T12-T13: No formulas in forbidden forms (FIX-C)
  T14-T15: No SUM formulas in any form (FIX-C)
  T16-T17: Section order / all sections rendered (FIX-D)
  T18:     Field coverage 118/118 (FIX-D)
  T19:     Full validation pass 118/118
"""
import os
import re
import sys
import tempfile

import pytest
import openpyxl

sys.path.insert(0, os.path.dirname(__file__))

from xlsx_builder import build_xlsx, _FORBIDDEN_FORMULA_IDS, _RESULT_SUFFIX
from xlsx_field_coverage import run_coverage_check, verify_field_coverage
from xlsx_registry import REGISTRY
from xlsx_schema_adapter import load_form_spec, _json_path
from xlsx_validation import validate_xlsx

_OUTPUT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'output', 'xlsx')
)


def _built(rid: str) -> str:
    return os.path.join(_OUTPUT_DIR, REGISTRY[rid]["output_filename"])


def _build_temp(rid: str) -> str:
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        path = f.name
    spec = load_form_spec(rid)
    meta = REGISTRY[rid]
    build_xlsx(spec, meta["design_type"], path, research_id=rid)
    return path


# ── T01: registry ─────────────────────────────────────────────────────────────

def test_registry_count():
    assert len(REGISTRY) == 118


def test_registry_design_types():
    expected = {
        "CUMULATIVE", "CALC_AGG", "DATE_STATUS", "CHECKLIST",
        "DAILY_LOG", "DOC_TABLE", "PLAN_EVAL",
    }
    assert {v["design_type"] for v in REGISTRY.values()} == expected


def test_registry_forbidden_ids():
    assert {k for k, v in REGISTRY.items() if v["forbidden_formula"]} == _FORBIDDEN_FORMULA_IDS


# ── T02: JSON paths ────────────────────────────────────────────────────────────

def test_json_paths_exist():
    missing = [rid for rid in REGISTRY if not os.path.exists(_json_path(rid))]
    assert not missing, f"Missing JSON: {missing}"


def test_c002_legacy_adapter():
    spec = load_form_spec("REF-C002")
    assert spec["_meta"]["adapter"] == "xlsx_schema_adapter"
    types = [s["type"] for s in spec["sections"]]
    assert "repeat_table" in types
    assert "basic_info" in types


# ── T03: basic build ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("rid", [
    "CHW-01", "CHW-03", "CITYGAS-01", "GOV-04", "DOC-03",
    "EQUIP-01", "GOV-11", "REF-C002", "MNT-03", "REF-C016",
    "REF-C029", "REF-C004",
])
def test_build_produces_valid_file(rid):
    path = _build_temp(rid)
    try:
        assert os.path.getsize(path) > 1000
        wb = openpyxl.load_workbook(path, read_only=True)
        assert wb.sheetnames
        wb.close()
    finally:
        os.unlink(path)


# ── T04: title cell ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C002", "MNT-03", "CITYGAS-01"])
def test_title_cell_non_empty(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        assert wb.active.cell(row=1, column=1).value
        wb.close()
    finally:
        os.unlink(path)


# ── T05: FIX-E document metadata ─────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C002", "CHW-03"])
def test_document_metadata(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path)
        assert wb.properties.title, "title not set"
        assert "INTERNAL_POC_ONLY" in (wb.properties.description or "")
        assert "LEGAL_REVIEW_PENDING" in (wb.properties.description or "")
        wb.close()
    finally:
        os.unlink(path)


# ── T06: FIX-B Excel Table present ───────────────────────────────────────────

@pytest.mark.parametrize("rid", [
    "CHW-01", "CHW-03", "CITYGAS-01", "REF-C016", "GOV-09",
])
def test_excel_table_present(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        assert ws._tables, f"{rid}: no Excel Table"
        wb.close()
    finally:
        os.unlink(path)


# ── T07: FIX-B table covers expanded rows ────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C016"])
def test_table_row_count_exceeds_default(rid):
    import json
    spec = load_form_spec(rid)
    default_rows = next(
        (s["default_row_count"] for s in spec["sections"]
         if s["type"] == "repeat_table"),
        10,
    )
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        tables = list(ws._tables.values())
        assert tables
        tbl = tables[0]
        # Table ref end row should be ≥ header + max(default*4, 60)
        ref = tbl.ref  # e.g. "A3:G63"
        end_row = int(re.search(r":.*?(\d+)$", ref).group(1))
        min_expected = max(default_rows * 4, 60) + 3  # header row + title + ...
        assert end_row >= min_expected, (
            f"{rid}: table end row {end_row} < {min_expected}"
        )
        wb.close()
    finally:
        os.unlink(path)


# ── T08: FIX-B freeze panes set ───────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "REF-C016", "GOV-09"])
def test_freeze_panes(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        assert wb.active.freeze_panes, f"{rid}: no freeze_panes"
        wb.close()
    finally:
        os.unlink(path)


# ── T09: FIX-A checklist only result columns ──────────────────────────────────

def test_citygas01_only_result_col_validated():
    """CITYGAS-01: 점검결과(입력) col C only, not 번호/점검항목/이상내용."""
    path = _build_temp("CITYGAS-01")
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        dvs = ws.data_validations.dataValidation
        assert dvs, "No data validation"
        sqref_str = str(dvs[0].sqref)
        # Only column C should be validated
        assert "C" in sqref_str
        assert "A" not in sqref_str, "Column A (번호) should not be validated"
        assert "B" not in sqref_str, "Column B (점검항목) should not be validated"
        assert "D" not in sqref_str, "Column D (이상내용) should not be validated"
        wb.close()
    finally:
        os.unlink(path)


def test_ref_c067_only_confirmation_col_validated():
    """REF-C067: 점검 결과(양호/불량/해당없음) should NOT get ○/×; 확인 should."""
    path = _build_temp("REF-C067")
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        dvs = ws.data_validations.dataValidation
        # Column C is "점검 결과(양호/불량/해당없음)" — must NOT be validated
        sqref_str = str(dvs[0].sqref) if dvs else ""
        assert "C" not in sqref_str, (
            "점검 결과(양호/불량/해당없음) should not get ○/× validation"
        )
        wb.close()
    finally:
        os.unlink(path)


def test_pra_22_09_correct_cols_validated():
    """PRA-22-09: 조치 필요 여부 + 인계 확인 (cols E, F) get ○/×."""
    path = _build_temp("PRA-22-09")
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        dvs = ws.data_validations.dataValidation
        assert dvs, "No data validation"
        sqref_str = str(dvs[0].sqref)
        assert "E" in sqref_str, "E (조치 필요 여부) should be validated"
        assert "F" in sqref_str, "F (인계 확인) should be validated"
        assert "A" not in sqref_str
        assert "B" not in sqref_str
        wb.close()
    finally:
        os.unlink(path)


# ── T10: FIX-A result suffix regex ───────────────────────────────────────────

@pytest.mark.parametrize("label,should_match", [
    ("점검결과(입력)", True),
    ("점검 결과(입력)", True),
    ("확인 결과(입력)", True),
    ("이수 여부(입력)", True),
    ("라벨 유무(입력)", True),
    ("격리 확인(입력)", True),
    ("인계 확인", True),
    ("점검 결과(양호/불량/해당없음)", False),  # explicit values, not ○/×
    ("이상내용", False),
    ("조치 내용(입력)", False),
    ("번호", False),
    ("점검항목", False),
    ("법령 근거(입력)", False),
    ("개선 사항(입력)", False),
    ("시정 이력(입력)", False),
    ("미이수 사유(입력)", False),
])
def test_result_suffix_regex(label, should_match):
    result = bool(_RESULT_SUFFIX.search(label))
    assert result == should_match, f"'{label}': expected {should_match}, got {result}"


# ── T11: FIX-A non-checklist forms have no data validation ────────────────────

@pytest.mark.parametrize("rid", ["CHW-01", "GOV-04", "DOC-03", "EQUIP-01"])
def test_non_checklist_no_dv(rid):
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False)
        ws = wb.active
        # Non-checklist forms should not have ○/× validation
        for dv in ws.data_validations.dataValidation:
            assert "○" not in (dv.formula1 or ""), (
                f"{rid}: unexpected ○/× validation"
            )
        wb.close()
    finally:
        os.unlink(path)


# ── T12: FIX-C no SUM formulas in FORMULA_DIRECTION_UNVERIFIED ───────────────

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
            if cell.value and isinstance(cell.value, str)
            and cell.value.startswith("=")
        ]
        assert not formula_cells, f"{rid}: formulas found: {formula_cells}"
        wb.close()
    finally:
        os.unlink(path)


# ── T13: FIX-C no SUM in any form ────────────────────────────────────────────

@pytest.mark.parametrize("rid", ["CHW-02", "P-20", "P-26", "REF-C016", "GOV-10"])
def test_no_sum_formulas(rid):
    """FIX-C: SUM formulas removed from all forms."""
    path = _build_temp(rid)
    try:
        wb = openpyxl.load_workbook(path, read_only=False, data_only=False)
        ws = wb.active
        sum_cells = [
            cell.coordinate
            for row in ws.iter_rows()
            for cell in row
            if cell.value and isinstance(cell.value, str)
            and cell.value.upper().startswith("=SUM")
        ]
        assert not sum_cells, f"{rid}: SUM formulas found: {sum_cells}"
        wb.close()
    finally:
        os.unlink(path)


# ── T14: FIX-D sections rendered in order ─────────────────────────────────────

def test_ref_c016_approval_label_rendered():
    """REF-C016 approval section has label '연간 교육계획' — must appear in xlsx."""
    path = _build_temp("REF-C016")
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        texts = {
            c.value for row in ws.iter_rows()
            for c in row if c.value
        }
        assert "연간 교육계획" in texts, "approval section label missing"
        wb.close()
    finally:
        os.unlink(path)


def test_mnt03_no_table_but_builds():
    """MNT-03 has no repeat_table; must build without error."""
    path = _build_temp("MNT-03")
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        assert wb.sheetnames
        assert wb.active.cell(row=1, column=1).value
        wb.close()
    finally:
        os.unlink(path)


def test_p25_all_freeform_sections_rendered():
    """P-25 has 3 freeform_area sections — all labels must appear in xlsx."""
    spec = load_form_spec("P-25")
    freeform_labels = [
        s["label"] for s in spec["sections"]
        if s["type"] == "freeform_area" and s.get("label")
    ]
    assert freeform_labels, "P-25 should have freeform sections with labels"
    path = _build_temp("P-25")
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        texts = {c.value for row in ws.iter_rows() for c in row if c.value}
        for lbl in freeform_labels:
            assert lbl in texts, f"freeform label '{lbl}' missing from P-25"
        wb.close()
    finally:
        os.unlink(path)


# ── T15: FIX-D field coverage 118/118 ────────────────────────────────────────

def test_field_coverage_all_118():
    results = run_coverage_check(REGISTRY, _OUTPUT_DIR)
    missing = [r for r in results if r["status"] != "OK"]
    assert not missing, (
        f"Field coverage failures: "
        + ", ".join(f"{r['research_id']}:{r['missing_fields'][:2]}" for r in missing[:5])
    )


# ── T16: output files exist for all 118 ──────────────────────────────────────

def test_all_118_output_files_exist():
    missing = [
        rid for rid, meta in REGISTRY.items()
        if not os.path.exists(os.path.join(_OUTPUT_DIR, meta["output_filename"]))
    ]
    assert not missing, f"Missing output files: {missing}"


# ── T17: full validation 118/118 ─────────────────────────────────────────────

@pytest.mark.parametrize("rid", list(REGISTRY.keys()))
def test_validation_pass(rid):
    path = _built(rid)
    meta = REGISTRY[rid]
    failures = validate_xlsx(path, rid, meta["design_type"])
    assert not failures, f"{rid}: {failures}"
