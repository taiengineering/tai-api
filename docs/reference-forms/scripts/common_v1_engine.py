#!/usr/bin/env python3
"""
TAI 서식 공통 렌더러 엔진 — common-v1
WO-058 Phase C-01
"""
import json, os, sys
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

# ─── Font ─────────────────────────────────────────────────────────
FONT_TTC_DEFAULT = (
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
    "7a0b5c0f3c1d41c4c52a33343496c9c65ad52c50.asset/AssetData/NanumGothic.ttc"
)
FONT_TTC = os.environ.get("NANUM_GOTHIC_TTC", FONT_TTC_DEFAULT)

def register_fonts():
    if not os.path.exists(FONT_TTC):
        raise FileNotFoundError(f"NanumGothic.ttc not found: {FONT_TTC}\n"
                                "Set NANUM_GOTHIC_TTC env var or download from https://github.com/naver/nanumfont")
    pdfmetrics.registerFont(TTFont('NG',     FONT_TTC, subfontIndex=0))
    pdfmetrics.registerFont(TTFont('NGBold', FONT_TTC, subfontIndex=1))
    from reportlab.lib.fonts import addMapping
    addMapping('NG', 0, 0, 'NG')
    addMapping('NG', 1, 0, 'NGBold')

# Register NG/NGBold font family mapping so Paragraph objects can be instantiated
# without the TTC file (needed for structural/assembler tests that don't render PDFs).
from reportlab.lib.fonts import addMapping as _addMapping
_addMapping('NG',     0, 0, 'NG')
_addMapping('NG',     1, 0, 'NGBold')
_addMapping('NGBold', 0, 0, 'NGBold')

# ─── Colors ───────────────────────────────────────────────────────
C_BLACK     = colors.HexColor('#000000')
C_HEADER_BG = colors.HexColor('#E8E8E8')
C_ALT_BG    = colors.HexColor('#F5F5F5')
C_GRAY_TEXT = colors.HexColor('#505050')

# ─── Layout constants ─────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN    = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN   # 170mm
CELL_PAD  = 3 * mm
ROW_H_INFO = 7  * mm
ROW_H_SIGN = 15 * mm

# ─── Paragraph styles ─────────────────────────────────────────────
def _mk(name, *, font='NG', size=10, leading=14, color=C_BLACK, align=TA_LEFT):
    return ParagraphStyle(name=name, fontName=font, fontSize=size,
                          leading=leading, textColor=color, alignment=align,
                          spaceBefore=0, spaceAfter=0)

S_TITLE  = _mk('cv1_title', font='NGBold', size=16, leading=20, align=TA_CENTER)
S_HDR    = _mk('cv1_hdr',   font='NGBold', size=10, leading=13, align=TA_CENTER)
S_BODY   = _mk('cv1_body',                 size=10, leading=14)
S_BODY_C = _mk('cv1_bc',                   size=10, leading=14, align=TA_CENTER)
S_BODY_R = _mk('cv1_br',                   size=10, leading=14)
S_LBL    = _mk('cv1_lbl',   font='NGBold', size=10, leading=14)
S_SMALL  = _mk('cv1_sm',                   size=8,  leading=12, color=C_GRAY_TEXT)

def P(text, s=None):
    return Paragraph(text or '', s or S_BODY)

# ─── Table style helpers ──────────────────────────────────────────
_BASE = [
    ('FONTNAME',      (0,0),(-1,-1),'NG'),
    ('FONTSIZE',      (0,0),(-1,-1),10),
    ('TOPPADDING',    (0,0),(-1,-1),CELL_PAD),
    ('BOTTOMPADDING', (0,0),(-1,-1),CELL_PAD),
    ('LEFTPADDING',   (0,0),(-1,-1),CELL_PAD),
    ('RIGHTPADDING',  (0,0),(-1,-1),CELL_PAD),
    ('GRID',          (0,0),(-1,-1),0.5,C_BLACK),
    ('VALIGN',        (0,0),(-1,-1),'MIDDLE'),
]

def ts(*extra):
    return TableStyle(list(_BASE) + list(extra))

# ─── NumberedCanvas ───────────────────────────────────────────────
class NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self.setProducer('TAI Document Pipeline v1')
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(n)
            pdfcanvas.Canvas.showPage(self)
        try:
            self._doc.setProducer('TAI Document Pipeline v1')
            self._doc.setCreator('TAI')
        except AttributeError:
            pass
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, total):
        self.saveState()
        self.setFont('NG', 8)
        self.setFillColor(C_GRAY_TEXT)
        self.drawCentredString(PAGE_W / 2, 10 * mm, f"{self._pageNumber} / {total}")
        self.restoreState()

# ─── Schema validator ─────────────────────────────────────────────
SUPPORTED_TYPES = {'approval', 'basic_info', 'labeled_grid', 'freeform_area', 'repeat_table'}

_REQUIRED = {
    'approval':      ['type','total_width_mm','fields'],
    'basic_info':    ['type','fields'],
    'labeled_grid':  ['type','rows'],
    'freeform_area': ['type','label','min_height_mm'],
    'repeat_table':  ['type','columns','default_row_count'],
}

def validate(fields):
    doc = fields.get('document')
    if not doc:
        raise ValueError("Missing 'document' key")
    for attr in ('title','doc_id','creator'):
        if not doc.get(attr):
            raise ValueError(f"document.{attr} is required")

    sections = fields.get('sections')
    if sections is None:
        raise ValueError("Missing 'sections' key")
    if not isinstance(sections, list):
        raise ValueError("'sections' must be a list")

    for i, s in enumerate(sections):
        t = s.get('type')
        if t not in SUPPORTED_TYPES:
            raise ValueError(f"sections[{i}]: unsupported block type {t!r}")
        for attr in _REQUIRED[t]:
            if attr not in s:
                raise ValueError(f"sections[{i}] ({t}): missing required attr {attr!r}")
        if t == 'approval':
            if not isinstance(s['fields'], list) or len(s['fields']) < 1:
                raise ValueError(f"sections[{i}] approval: fields must have >= 1 entry")
        if t == 'labeled_grid':
            for ri, row in enumerate(s['rows']):
                if len(row) != 2:
                    raise ValueError(f"sections[{i}] labeled_grid rows[{ri}]: must have exactly 2 cells, got {len(row)}")
        if t == 'repeat_table':
            total_mm = sum(c.get('width_mm', 0) for c in s['columns'])
            if abs(total_mm - 170) > 0.5:
                raise ValueError(f"sections[{i}] repeat_table: column widths sum to {total_mm}mm, expected 170mm")
    return True

# ─── Section builders ─────────────────────────────────────────────

def build_title(fields):
    return Table(
        [[P(fields['document']['title'], S_TITLE)]],
        colWidths=[CONTENT_W],
        style=ts(('FONTNAME',(0,0),(-1,-1),'NGBold')),
    )

def build_approval(section):
    appr  = section['fields']
    n     = len(appr)
    tot_w = section['total_width_mm'] * mm
    cell_w = tot_w / n
    title_w = CONTENT_W - tot_w
    hdr_h = section.get('min_header_height_mm', 7) * mm
    sign_h = section.get('min_sign_height_mm', 15) * mm

    inner = Table(
        [[P(f['label'], S_HDR) for f in appr], ['' for _ in appr]],
        colWidths=[cell_w] * n,
        rowHeights=[hdr_h, sign_h],
        style=ts(
            ('FONTNAME',  (0,0),(-1,0),'NGBold'),
            ('BACKGROUND',(0,0),(-1,0),C_HEADER_BG),
            ('LINEWIDTH', (0,0),(-1,-1),0.75),
        ),
    )
    return Table(
        [['', inner]],
        colWidths=[title_w, tot_w],
        style=TableStyle([
            ('TOPPADDING',   (0,0),(-1,-1),0),
            ('BOTTOMPADDING',(0,0),(-1,-1),0),
            ('LEFTPADDING',  (0,0),(-1,-1),0),
            ('RIGHTPADDING', (0,0),(-1,-1),0),
            ('LINEWIDTH',    (0,0),(-1,-1),0),
        ]),
    )

def build_basic_info(section):
    flds = section['fields']
    half = CONTENT_W / 2
    rows = []
    for i in range(0, len(flds), 2):
        left  = flds[i]   if i     < len(flds) else None
        right = flds[i+1] if i+1 < len(flds) else None
        rows.append([
            P(f"{left['label']}: ____________________________")  if left  else '',
            P(f"{right['label']}: ____________________________") if right else '',
        ])
    return Table(rows, colWidths=[half, half],
                 rowHeights=[ROW_H_INFO]*len(rows), style=ts())

def build_labeled_grid(section):
    label     = section.get('section_label')
    rows_data = section['rows']
    row_h     = section.get('row_height_mm', 7) * mm
    half      = CONTENT_W / 2

    tbl_rows   = []
    style_cmds = list(_BASE)

    if label:
        tbl_rows.append([P(label, S_HDR), ''])
        style_cmds += [
            ('SPAN',       (0,0),(1,0)),
            ('BACKGROUND', (0,0),(1,0),C_HEADER_BG),
            ('FONTNAME',   (0,0),(1,0),'NGBold'),
            ('ALIGN',      (0,0),(1,0),'CENTER'),
        ]

    data_start = 1 if label else 0
    for row in rows_data:
        tbl_rows.append([P(f"{cell['label']}: ", S_LBL) for cell in row])

    for r in range(data_start, len(tbl_rows)):
        style_cmds += [
            ('BACKGROUND',(0,r),(-1,r),C_ALT_BG),
            ('FONTNAME',  (0,r),(-1,r),'NGBold'),
        ]

    row_heights = ([7*mm] if label else []) + [row_h]*len(rows_data)
    return Table(tbl_rows, colWidths=[half, half],
                 rowHeights=row_heights, style=TableStyle(style_cmds))

def build_freeform_area(section):
    min_h = section['min_height_mm'] * mm
    return Table(
        [[P(section['label'], S_HDR)], ['']],
        colWidths=[CONTENT_W],
        rowHeights=[7*mm, min_h],
        style=ts(
            ('FONTNAME',  (0,0),(-1,0),'NGBold'),
            ('BACKGROUND',(0,0),(-1,0),C_HEADER_BG),
            ('BACKGROUND',(0,1),(-1,1),C_ALT_BG),
        ),
    )

def build_repeat_table(section, ex_rows=None):
    cols    = section['columns']
    n_def   = section['default_row_count']
    col_w   = [c['width_mm']*mm for c in cols]
    align_m = {'left':S_BODY,'center':S_BODY_C,'right':S_BODY_R}

    header = [P(c['label'], S_HDR) for c in cols]
    data   = list(ex_rows) if ex_rows else []
    while len(data) < n_def:
        data.append(['']*len(cols))

    rows = [header]
    for ri, rd in enumerate(data):
        rows.append([P(str(rd[i] or ''), align_m.get(cols[i].get('align','left'), S_BODY))
                     for i in range(len(cols))])

    cmds = list(_BASE) + [
        ('FONTNAME',  (0,0),(-1,0),'NGBold'),
        ('BACKGROUND',(0,0),(-1,0),C_HEADER_BG),
        ('ALIGN',     (0,0),(-1,0),'CENTER'),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            cmds.append(('BACKGROUND',(0,i),(-1,i),C_ALT_BG))

    ROW_H_PLAN = 14 * mm
    tbl = Table(rows, colWidths=col_w, style=TableStyle(cmds),
                repeatRows=1, minRowHeights=[0]+[ROW_H_PLAN]*len(data))
    return [tbl]

# ─── Common assembler ──────────────────────────────────────────────

def assemble(fields, ex_rows=None):
    story = [build_title(fields), Spacer(1, 1*mm)]
    for s in fields.get('sections', []):
        t = s['type']
        if   t == 'approval':      story.append(build_approval(s))
        elif t == 'basic_info':    story.append(build_basic_info(s))
        elif t == 'labeled_grid':  story.append(build_labeled_grid(s))
        elif t == 'freeform_area': story.append(build_freeform_area(s))
        elif t == 'repeat_table':  story += build_repeat_table(s, ex_rows)
        else:
            raise ValueError(f"Unsupported block type: {t!r}")
        story.append(Spacer(1, 1*mm))
    return story

# ─── Document generator ───────────────────────────────────────────

def generate(fields_path, out_path, ex_rows=None):
    with open(fields_path, encoding='utf-8') as f:
        fields = json.load(f)
    validate(fields)
    meta = fields['document']
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=meta['title'], author=meta.get('creator','TAI'),
        subject=meta.get('subject',''),
    )
    doc.build(assemble(fields, ex_rows), canvasmaker=NumberedCanvas)
    kb = os.path.getsize(out_path)/1024
    print(f"  PDF → {out_path}  ({kb:.0f} KB)")
