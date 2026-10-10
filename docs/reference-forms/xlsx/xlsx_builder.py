"""
XLSX builder for TAI reference forms — WO-REF01-XLS03-BULK-XLSX-BUILD-001.
Converts common-v1 JSON (or adapted legacy) to a structured .xlsx file.
"""
from __future__ import annotations

import os
import re
from typing import Any

import openpyxl
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# ── colour palette ────────────────────────────────────────────────────────────
_C_TITLE_BG    = "1F3864"
_C_TITLE_FG    = "FFFFFF"
_C_HDR_BG      = "2F5496"
_C_HDR_FG      = "FFFFFF"
_C_LABEL_BG    = "D9D9D9"
_C_SECT_BG     = "F2F2F2"
_C_INPUT       = "DCE6F1"   # input cell
_C_CALC        = "FFF2CC"   # formula / calculated cell
_C_NOFORMULA   = "FFCCCC"   # FORMULA_DIRECTION_UNVERIFIED
_C_CHECKLIST   = "E2EFDA"   # checklist data cell
_C_TEXT_BG     = "FAFAFA"
_C_WHITE       = "FFFFFF"

# FORMULA_DIRECTION_UNVERIFIED forms — no auto-calc in any column
_FORBIDDEN_FORMULA_IDS = {"CHW-03", "REF-C029", "REF-C004"}

# Columns where a SUM formula is reasonable (label keywords)
_NUMERIC_KEYWORDS = re.compile(
    r"(수량|건수|인원|점수|횟수|시간|금액|예산|달성률|비용|비율)", re.IGNORECASE
)

# ── style helpers ─────────────────────────────────────────────────────────────

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _font(bold=False, color="000000", size=10, italic=False) -> Font:
    return Font(bold=bold, color=color, size=size, italic=italic,
                name="맑은 고딕")


def _border(style="thin") -> Border:
    s = Side(style=style)
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
    ws.merge_cells(
        start_row=r1, start_column=c1, end_row=r2, end_column=c2
    )
    _set_cell(ws, r1, c1, value, **kw)


# ── width conversion ──────────────────────────────────────────────────────────

def _mm_to_chars(mm: float) -> float:
    """Approximate: 1 Excel char ≈ 2mm (Calibri 11pt ≈ 7px, ~2.5mm)."""
    val = max(4.0, mm * 0.45)
    return min(val, 40.0)


# ── main entry point ──────────────────────────────────────────────────────────

def build_xlsx(
    form_spec: dict,
    design_type: str,
    output_path: str,
    research_id: str = "",
) -> None:
    """
    Build one .xlsx file from a normalized form_spec.
    design_type: CUMULATIVE|CALC_AGG|DATE_STATUS|CHECKLIST|DAILY_LOG|DOC_TABLE|PLAN_EVAL
    """
    forbidden = research_id.upper() in _FORBIDDEN_FORMULA_IDS

    doc = form_spec.get("document", {})
    title = doc.get("title", research_id)
    orientation = doc.get("page", {}).get("orientation", "portrait")
    sections = form_spec.get("sections", [])

    # Separate sections by type for easy access
    basic_info = next((s for s in sections if s["type"] == "basic_info"), None)
    repeat_tables = [s for s in sections if s["type"] == "repeat_table"]
    freeform_areas = [s for s in sections if s["type"] == "freeform_area"]
    approval_sec = next((s for s in sections if s["type"] == "approval"), None)
    text_flows = [s for s in sections if s["type"] == "text_flow"]
    labeled_grids = [s for s in sections if s["type"] == "labeled_grid"]

    repeat_table = repeat_tables[0] if repeat_tables else None

    # Determine sheet width (number of columns)
    n_data_cols = len(repeat_table["columns"]) if repeat_table else 4
    n_cols = max(n_data_cols, 4)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _safe_sheet_name(title)

    # Track current row
    row = 1

    # ── 1. Title row ──────────────────────────────────────────────────────────
    _merge(ws, row, 1, row, n_cols, title,
           bold=True, fg=_C_TITLE_FG, bg=_C_TITLE_BG, size=12, h="center")
    ws.row_dimensions[row].height = 24
    row += 1

    # ── 2. Approval section (if before basic_info) ────────────────────────────
    # C002 puts approval first; check order in sections list
    appr_idx = next((i for i, s in enumerate(sections)
                     if s["type"] == "approval"), None)
    bi_idx = next((i for i, s in enumerate(sections)
                   if s["type"] == "basic_info"), None)
    if approval_sec and appr_idx is not None and (
        bi_idx is None or appr_idx < bi_idx
    ):
        row = _render_approval(ws, approval_sec, row, n_cols)

    # ── 3. Basic info section ─────────────────────────────────────────────────
    if basic_info:
        row = _render_basic_info(ws, basic_info, row, n_cols)

    # ── 4. Labeled grid sections (before repeat_table) ────────────────────────
    rt_idx = next((i for i, s in enumerate(sections)
                   if s["type"] == "repeat_table"), None)
    for lg in labeled_grids:
        lg_idx = sections.index(lg)
        if rt_idx is None or lg_idx < rt_idx:
            row = _render_labeled_grid(ws, lg, row, n_cols)

    # ── 5. Freeform areas (before repeat_table) ───────────────────────────────
    for fa in freeform_areas:
        fa_idx = sections.index(fa)
        if rt_idx is None or fa_idx < rt_idx:
            row = _render_freeform(ws, fa, row, n_cols)

    # ── 6. Repeat table ───────────────────────────────────────────────────────
    freeze_row = None
    sum_row = None
    if repeat_table:
        header_row, data_start, data_end = _render_repeat_table(
            ws, repeat_table, row, n_cols, n_data_cols,
            design_type, forbidden
        )
        freeze_row = data_start
        sum_row = data_end + 1 if not forbidden and design_type == "CALC_AGG" else None
        row = data_end + 1

        # SUM row for CALC_AGG (non-forbidden)
        if sum_row and not forbidden:
            row = _render_sum_row(
                ws, repeat_table, sum_row, n_data_cols, data_start, data_end
            )

        # Checklist data validation
        if design_type == "CHECKLIST":
            _apply_checklist_validation(ws, repeat_table, data_start, data_end, n_data_cols)

    # ── 7. Labeled grid sections (after repeat_table) ─────────────────────────
    for lg in labeled_grids:
        lg_idx = sections.index(lg)
        if rt_idx is not None and lg_idx > rt_idx:
            row = _render_labeled_grid(ws, lg, row, n_cols)

    # ── 8. Freeform areas (after repeat_table) ────────────────────────────────
    for fa in freeform_areas:
        fa_idx = sections.index(fa)
        if rt_idx is None or fa_idx > rt_idx:
            row = _render_freeform(ws, fa, row, n_cols)

    # ── 9. Text flows ─────────────────────────────────────────────────────────
    for tf in text_flows:
        row = _render_text_flow(ws, tf, row, n_cols)

    # ── 10. Approval (if after repeat_table or only section) ─────────────────
    if approval_sec and (appr_idx is None or (bi_idx is not None and appr_idx > bi_idx)):
        row = _render_approval(ws, approval_sec, row, n_cols)

    # ── Column widths ─────────────────────────────────────────────────────────
    if repeat_table:
        for ci, col_def in enumerate(repeat_table["columns"], start=1):
            if ci <= n_cols:
                w = _mm_to_chars(col_def.get("width_mm", 20))
                ws.column_dimensions[get_column_letter(ci)].width = w
        # Extra cols (if n_cols > n_data_cols) use default
        for ci in range(n_data_cols + 1, n_cols + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 10
    else:
        # Default widths for non-repeat forms
        for ci in range(1, n_cols + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 14

    # ── Freeze panes ─────────────────────────────────────────────────────────
    if freeze_row:
        ws.freeze_panes = ws.cell(row=freeze_row, column=1)

    # ── Print settings ────────────────────────────────────────────────────────
    ws.page_setup.orientation = (
        "landscape" if orientation == "landscape" else "portrait"
    )
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:{get_column_letter(n_cols)}{row - 1}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)


# ── section renderers ─────────────────────────────────────────────────────────

def _render_basic_info(ws, section: dict, row: int, n_cols: int) -> int:
    fields = section.get("fields", [])
    # Pair fields 2 per row: [label | value | label | value]
    half = max(n_cols // 2, 2)
    i = 0
    while i < len(fields):
        f1 = fields[i]
        f2 = fields[i + 1] if i + 1 < len(fields) else None
        ws.row_dimensions[row].height = 16

        # left label
        _set_cell(ws, row, 1, _field_label(f1), bold=True, bg=_C_LABEL_BG)
        # left value (span to halfway if no right field)
        if f2:
            _merge(ws, row, 2, row, half, "", bg=_C_INPUT, h="left")
            # right label
            _set_cell(ws, row, half + 1, _field_label(f2), bold=True, bg=_C_LABEL_BG)
            # right value
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
        ws.row_dimensions[row].height = max(
            section.get("row_height_mm", 9) * 2.1, 14
        )
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
    # Divide n_cols evenly among approval fields
    n = len(fields)
    per = n_cols // n
    rest = n_cols - per * n

    ws.row_dimensions[row].height = 14
    ws.row_dimensions[row + 1].height = 28

    for i, f in enumerate(fields):
        c1 = i * per + 1 + (0 if i < rest else rest - (rest - i) if i < rest else 0)
        # simpler even split
        c1 = i * (n_cols // n) + 1
        c2 = c1 + (n_cols // n) - 1
        if i == n - 1:
            c2 = n_cols
        label = _field_label(f)
        _merge(ws, row, c1, row, c2, label, bold=True, bg=_C_LABEL_BG)
        _merge(ws, row + 1, c1, row + 1, c2, "", bg=_C_WHITE)
    row += 2
    return row


def _render_repeat_table(
    ws, section: dict, row: int, n_cols: int, n_data_cols: int,
    design_type: str, forbidden: bool
) -> tuple[int, int, int]:
    """Renders repeat_table. Returns (header_row, data_start_row, data_end_row)."""
    columns = section.get("columns", [])
    default_rows = section.get("default_row_count", 10)
    header_row = row

    # Header row
    for ci, col in enumerate(columns, start=1):
        _set_cell(ws, row, ci, col.get("label", ""),
                  bold=True, fg=_C_HDR_FG, bg=_C_HDR_BG, h="center")
    # If n_cols > n_data_cols, fill remaining header cells
    for ci in range(n_data_cols + 1, n_cols + 1):
        _set_cell(ws, row, ci, "", bold=True, fg=_C_HDR_FG, bg=_C_HDR_BG)
    ws.row_dimensions[row].height = 18
    row += 1

    data_start = row
    data_end = row + default_rows - 1

    cell_bg = _pick_cell_bg(design_type, forbidden)
    for r in range(data_start, data_end + 1):
        ws.row_dimensions[r].height = 16
        for ci in range(1, n_data_cols + 1):
            _set_cell(ws, r, ci, "", bg=cell_bg)
        for ci in range(n_data_cols + 1, n_cols + 1):
            _set_cell(ws, r, ci, "", bg=cell_bg)

    # Auto-filter on header row
    ws.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(n_data_cols)}{data_end}"
    )

    row = data_end + 1
    return header_row, data_start, data_end


def _render_sum_row(
    ws, section: dict, row: int, n_data_cols: int,
    data_start: int, data_end: int
) -> int:
    columns = section.get("columns", [])
    _set_cell(ws, row, 1, "합계", bold=True, bg=_C_SECT_BG)
    if n_data_cols > 1:
        for ci, col in enumerate(columns[1:], start=2):
            if ci > n_data_cols:
                break
            label = col.get("label", "")
            if _NUMERIC_KEYWORDS.search(label):
                col_letter = get_column_letter(ci)
                formula = f"=SUM({col_letter}{data_start}:{col_letter}{data_end})"
                _set_cell(ws, row, ci, formula, bg=_C_CALC)
            else:
                _set_cell(ws, row, ci, "", bg=_C_SECT_BG)
    ws.row_dimensions[row].height = 16
    return row + 1


def _apply_checklist_validation(
    ws, section: dict, data_start: int, data_end: int, n_data_cols: int
):
    dv = DataValidation(
        type="list",
        formula1='"○,×,"',
        allow_blank=True,
        showDropDown=False,
    )
    ws.add_data_validation(dv)
    for ci in range(1, n_data_cols + 1):
        col_letter = get_column_letter(ci)
        dv.add(f"{col_letter}{data_start}:{col_letter}{data_end}")


# ── helper utilities ──────────────────────────────────────────────────────────

def _field_label(f: Any) -> str:
    if isinstance(f, dict):
        return f.get("label", "")
    return str(f)


def _pick_cell_bg(design_type: str, forbidden: bool) -> str:
    if forbidden:
        return _C_NOFORMULA
    if design_type == "CHECKLIST":
        return _C_CHECKLIST
    if design_type == "CALC_AGG":
        return _C_CALC
    return _C_INPUT


def _safe_sheet_name(name: str) -> str:
    # Excel sheet names: max 31 chars, no special chars
    safe = re.sub(r"[/\\?*\[\]:]", "_", name)
    return safe[:31]
