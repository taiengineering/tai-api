"""
XLSX builder for TAI reference forms — WO-REF01-XLS03-BULK-XLSX-BUILD-001.
CORRECTION-003 (WO-REF01-XLS03-FUNCTIONAL-QA-REPAIR-003):
  FIX-A: Checklist ○/× validation applied only to result-type columns
  FIX-B: repeat_table rendered as Excel Table (auto-expand on row add)
  FIX-C: SUM formulas removed entirely
  FIX-D: Sections rendered in JSON definition order; all sections preserved
  FIX-E: Document metadata properties added
"""
from __future__ import annotations

import os
import re
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

# ── colour palette ────────────────────────────────────────────────────────────
_C_TITLE_BG  = "1F3864"
_C_TITLE_FG  = "FFFFFF"
_C_HDR_BG    = "2F5496"
_C_HDR_FG    = "FFFFFF"
_C_LABEL_BG  = "D9D9D9"
_C_SECT_BG   = "F2F2F2"
_C_NOTE_BG   = "FFF2CC"   # FORMULA_DIRECTION_UNVERIFIED note row
_C_TEXT_BG   = "FAFAFA"
_C_INPUT     = "DCE6F1"
_C_WHITE     = "FFFFFF"

# FIX-A: ○/× validation applies only to columns whose label ENDS with these
_RESULT_SUFFIX = re.compile(
    r"(결과|여부|유무|확인)\s*(\(입력\))?\s*$", re.IGNORECASE
)

# FORMULA_DIRECTION_UNVERIFIED — no computed formulas allowed
_FORBIDDEN_FORMULA_IDS = {"CHW-03", "REF-C029", "REF-C004"}

# ── style helpers ─────────────────────────────────────────────────────────────

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _font(bold=False, color="000000", size=10, italic=False) -> Font:
    return Font(bold=bold, color=color, size=size, italic=italic,
                name="맑은 고딕")


def _border() -> Border:
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


def _align(h="center", v="center", wrap=True) -> Alignment:
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def _set_cell(ws, row, col, value, *, bold=False, fg=None, bg=None,
              size=10, italic=False, h="center", v="center", wrap=True,
              border=True):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = _font(bold=bold, color=fg or "000000", size=size, italic=italic)
    if bg:
        cell.fill = _fill(bg)
    cell.alignment = _align(h=h, v=v, wrap=wrap)
    if border:
        cell.border = _border()
    return cell


def _merge(ws, r1, c1, r2, c2, value="", **kw):
    ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    _set_cell(ws, r1, c1, value, **kw)


def _mm_to_chars(mm: float) -> float:
    return max(4.0, min(mm * 0.45, 40.0))


def _field_label(f: Any) -> str:
    return f.get("label", "") if isinstance(f, dict) else str(f)


def _safe_sheet_name(name: str) -> str:
    return re.sub(r"[/\\?*\[\]:]", "_", name)[:31]


def _safe_table_name(research_id: str, idx: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", research_id)
    return f"T_{base}_{idx}"


# ── main entry point ──────────────────────────────────────────────────────────

def build_xlsx(
    form_spec: dict,
    design_type: str,
    output_path: str,
    research_id: str = "",
) -> None:
    """Build one .xlsx from a normalized form_spec (common-v1 or adapted)."""
    forbidden = research_id.upper() in _FORBIDDEN_FORMULA_IDS

    doc = form_spec.get("document", {})
    title = doc.get("title", research_id)
    orientation = doc.get("page", {}).get("orientation", "portrait")
    sections = form_spec.get("sections", [])

    # First repeat_table determines sheet column count
    repeat_table_first = next(
        (s for s in sections if s["type"] == "repeat_table"), None
    )
    n_data_cols = (
        len(repeat_table_first["columns"]) if repeat_table_first else 4
    )
    n_cols = max(n_data_cols, 4)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _safe_sheet_name(title)

    # FIX-E: document metadata
    wb.properties.title = title
    wb.properties.description = (
        f"TAI-FORM | {research_id} | INTERNAL_POC_ONLY | "
        f"LEGAL_REVIEW_PENDING | RIGHTS_UNVERIFIED | GPT_REVIEW_REQUIRED"
    )
    wb.properties.creator = "TAI"
    wb.properties.keywords = "LEGAL_REVIEW_PENDING RIGHTS_UNVERIFIED"

    row = 1

    # ── Title row ─────────────────────────────────────────────────────────────
    _merge(ws, row, 1, row, n_cols, title,
           bold=True, fg=_C_TITLE_FG, bg=_C_TITLE_BG, size=12, h="center")
    ws.row_dimensions[row].height = 24
    row += 1

    # FORMULA_DIRECTION_UNVERIFIED: insert warning row
    if forbidden:
        _merge(ws, row, 1, row, n_cols,
               "【수동 입력 전용】 계산 방향 미검증 — 수식 자동 생성 금지 (FORMULA_DIRECTION_UNVERIFIED)",
               bold=False, fg="CC0000", bg=_C_NOTE_BG, size=9, h="left", italic=True)
        ws.row_dimensions[row].height = 14
        row += 1

    # ── Sections in JSON definition order (FIX-D) ────────────────────────────
    freeze_row = None
    table_idx = 0

    for section in sections:
        stype = section.get("type", "")

        if stype == "basic_info":
            row = _render_basic_info(ws, section, row, n_cols)

        elif stype == "labeled_grid":
            row = _render_labeled_grid(ws, section, row, n_cols)

        elif stype == "freeform_area":
            row = _render_freeform(ws, section, row, n_cols)

        elif stype == "text_flow":
            row = _render_text_flow(ws, section, row, n_cols)

        elif stype == "approval":
            row = _render_approval(ws, section, row, n_cols)

        elif stype == "repeat_table":
            table_idx += 1
            cols = section.get("columns", [])
            n_sec_cols = min(len(cols), n_cols)
            header_row, data_start, data_end = _render_repeat_table_header(
                ws, section, row, n_sec_cols, design_type, forbidden
            )
            # Add Excel Table (FIX-B)
            tname = _safe_table_name(research_id or "form", table_idx)
            tref = (
                f"A{header_row}:{get_column_letter(n_sec_cols)}{data_end}"
            )
            tbl = Table(displayName=tname, ref=tref)
            tbl.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            ws.add_table(tbl)

            # FIX-A: CHECKLIST — validate only result-type columns
            if design_type == "CHECKLIST":
                _apply_checklist_validation(
                    ws, section, data_start, data_end, n_sec_cols
                )

            if freeze_row is None:
                freeze_row = data_start

            row = data_end + 1

    # ── Freeze panes ─────────────────────────────────────────────────────────
    if freeze_row:
        ws.freeze_panes = ws.cell(row=freeze_row, column=1)

    # ── Print settings (FIX-2: print area = actual content range) ────────────
    ws.page_setup.orientation = (
        "landscape" if orientation == "landscape" else "portrait"
    )
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    # Print area covers actual written rows; user-added rows beyond the
    # pre-allocated table range require manual print-area extension in Excel.
    ws.print_area = f"A1:{get_column_letter(n_cols)}{row - 1}"

    # ── Column widths ─────────────────────────────────────────────────────────
    if repeat_table_first:
        for ci, col_def in enumerate(repeat_table_first["columns"], start=1):
            if ci <= n_cols:
                ws.column_dimensions[get_column_letter(ci)].width = (
                    _mm_to_chars(col_def.get("width_mm", 20))
                )
        for ci in range(n_data_cols + 1, n_cols + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 10
    else:
        for ci in range(1, n_cols + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 14

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)


# ── section renderers ─────────────────────────────────────────────────────────

def _render_basic_info(ws, section: dict, row: int, n_cols: int) -> int:
    fields = section.get("fields", [])
    half = max(n_cols // 2, 2)
    i = 0
    while i < len(fields):
        f1 = fields[i]
        f2 = fields[i + 1] if i + 1 < len(fields) else None
        ws.row_dimensions[row].height = 16
        _set_cell(ws, row, 1, _field_label(f1), bold=True, bg=_C_LABEL_BG)
        if f2:
            _merge(ws, row, 2, row, half, "", bg=_C_INPUT, h="left")
            _set_cell(ws, row, half + 1, _field_label(f2), bold=True, bg=_C_LABEL_BG)
            _merge(ws, row, half + 2, row, n_cols, "", bg=_C_INPUT, h="left")
        else:
            _merge(ws, row, 2, row, n_cols, "", bg=_C_INPUT, h="left")
        row += 1
        i += 2
    return row


def _render_labeled_grid(ws, section: dict, row: int, n_cols: int) -> int:
    label = section.get("section_label", "")
    rows_def = section.get("rows", [])
    half = max(n_cols // 2, 2)
    if label:
        _merge(ws, row, 1, row, n_cols, label,
               bold=True, bg=_C_SECT_BG, h="left")
        ws.row_dimensions[row].height = 14
        row += 1
    for row_def in rows_def:
        h = max(section.get("row_height_mm", 9) * 2.1, 14)
        ws.row_dimensions[row].height = h
        if len(row_def) >= 2:
            _set_cell(ws, row, 1, row_def[0].get("label", ""),
                      bold=True, bg=_C_LABEL_BG)
            _merge(ws, row, 2, row, half, "", bg=_C_INPUT, h="left")
            _set_cell(ws, row, half + 1, row_def[1].get("label", ""),
                      bold=True, bg=_C_LABEL_BG)
            _merge(ws, row, half + 2, row, n_cols, "", bg=_C_INPUT, h="left")
        elif len(row_def) == 1:
            _set_cell(ws, row, 1, row_def[0].get("label", ""),
                      bold=True, bg=_C_LABEL_BG)
            _merge(ws, row, 2, row, n_cols, "", bg=_C_INPUT, h="left")
        row += 1
    return row


def _render_freeform(ws, section: dict, row: int, n_cols: int) -> int:
    label = section.get("label", "")
    min_h_mm = section.get("min_height_mm", 20)
    n_rows = max(2, int(min_h_mm / 6))
    _merge(ws, row, 1, row, n_cols, label, bold=True, bg=_C_SECT_BG, h="left")
    ws.row_dimensions[row].height = 14
    row += 1
    _merge(ws, row, 1, row + n_rows - 1, n_cols, "", bg=_C_INPUT, h="left", v="top")
    for r in range(row, row + n_rows):
        ws.row_dimensions[r].height = 14
    row += n_rows
    return row


def _render_text_flow(ws, section: dict, row: int, n_cols: int) -> int:
    for para in section.get("paragraphs", []):
        text = para.get("text", "")
        _merge(ws, row, 1, row, n_cols, text,
               italic=True, bg=_C_TEXT_BG, h="left", size=8)
        ws.row_dimensions[row].height = 28
        row += 1
    return row


def _render_approval(ws, section: dict, row: int, n_cols: int) -> int:
    fields = section.get("fields", [])
    if not fields:
        return row
    # Render section-level label if present (FIX-D)
    sec_label = section.get("label", "")
    if sec_label:
        _merge(ws, row, 1, row, n_cols, sec_label, bold=True, bg=_C_SECT_BG, h="left")
        ws.row_dimensions[row].height = 14
        row += 1
    n = len(fields)
    per = n_cols // n
    ws.row_dimensions[row].height = 14
    ws.row_dimensions[row + 1].height = 28
    for i, f in enumerate(fields):
        c1 = i * per + 1
        c2 = c1 + per - 1 if i < n - 1 else n_cols
        _merge(ws, row, c1, row, c2, _field_label(f), bold=True, bg=_C_LABEL_BG)
        _merge(ws, row + 1, c1, row + 1, c2, "", bg=_C_WHITE)
    return row + 2


def _render_repeat_table_header(
    ws, section: dict, row: int, n_sec_cols: int,
    design_type: str, forbidden: bool,
) -> tuple[int, int, int]:
    """
    Render repeat_table header + pre-allocated data rows.
    Returns (header_row, data_start, data_end).
    FIX-B: data allocation = max(default_row_count * 4, 60).
    """
    columns = section.get("columns", [])
    default_rows = section.get("default_row_count", 10)
    # FIX-B: allocate more rows for expansion
    n_alloc = max(default_rows * 4, 60)

    header_row = row
    for ci, col in enumerate(columns[:n_sec_cols], start=1):
        _set_cell(ws, row, ci, col.get("label", ""),
                  bold=True, fg=_C_HDR_FG, bg=_C_HDR_BG, h="center")
    ws.row_dimensions[row].height = 18
    row += 1

    data_start = row
    data_end = row + n_alloc - 1

    # Pre-fill rows with light background (table style will overlay striping)
    for r in range(data_start, data_end + 1):
        ws.row_dimensions[r].height = 16
        for ci in range(1, n_sec_cols + 1):
            _set_cell(ws, r, ci, "", bg=_C_INPUT)

    return header_row, data_start, data_end


def _apply_checklist_validation(
    ws, section: dict, data_start: int, data_end: int, n_sec_cols: int
) -> None:
    """
    FIX-A: apply ○/× validation ONLY to columns whose label ends with
    결과/여부/유무/확인 (optionally followed by (입력)).
    """
    columns = section.get("columns", [])
    dv = DataValidation(
        type="list",
        formula1='"○,×,"',
        allow_blank=True,
        showDropDown=False,
    )
    ws.add_data_validation(dv)
    applied = 0
    for ci, col in enumerate(columns[:n_sec_cols], start=1):
        label = col.get("label", "")
        if _RESULT_SUFFIX.search(label):
            col_letter = get_column_letter(ci)
            dv.add(f"{col_letter}{data_start}:{col_letter}{data_end}")
            applied += 1
    return applied
