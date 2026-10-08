#!/usr/bin/env python3
"""
TAI REF-C002 PDF 생성기 — WO-054 시제품
Usage:
    python3 gen_c002_pdf.py [blank|example|all]

Font: NanumGothic.ttc (SIL OFL 1.1)
  - 기본 경로: macOS MobileAsset (로컬 전용, Git 미포함)
  - 환경 변수: NANUM_GOTHIC_TTC=/path/to/NanumGothic.ttc 로 재지정 가능
  - 공식 다운로드: https://github.com/naver/nanumfont
"""
import json, os, sys, hashlib
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

# ─── Font ─────────────────────────────────────────────────────────────────────

FONT_TTC_DEFAULT = (
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
    "7a0b5c0f3c1d41c4c52a33343496c9c65ad52c50.asset/AssetData/NanumGothic.ttc"
)
FONT_TTC = os.environ.get("NANUM_GOTHIC_TTC", FONT_TTC_DEFAULT)

def register_fonts():
    if not os.path.exists(FONT_TTC):
        print(f"ERROR: NanumGothic.ttc not found.\n  Path: {FONT_TTC}", file=sys.stderr)
        print("  Set NANUM_GOTHIC_TTC env var or download from https://github.com/naver/nanumfont",
              file=sys.stderr)
        sys.exit(1)
    pdfmetrics.registerFont(TTFont('NG',     FONT_TTC, subfontIndex=0))  # Regular
    pdfmetrics.registerFont(TTFont('NGBold', FONT_TTC, subfontIndex=1))  # Bold
    sha256 = hashlib.sha256(open(FONT_TTC, 'rb').read()).hexdigest()
    return sha256

# ─── Colors ───────────────────────────────────────────────────────────────────

C_BLACK      = colors.HexColor('#000000')
C_HEADER_BG  = colors.HexColor('#E8E8E8')
C_ALT_BG     = colors.HexColor('#F5F5F5')
C_GRAY_TEXT  = colors.HexColor('#505050')

# ─── Layout constants ─────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN   = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN       # 170mm

APPROVAL_W    = 90 * mm               # 결재란 총 너비
TITLE_W       = CONTENT_W - APPROVAL_W  # 80mm
APPR_CELL_W   = APPROVAL_W / 3          # 30mm per cell

COL_WIDTHS_MM = [56, 26, 22, 26, 22, 18]   # F05-F10 (PATCH-1: F08 담당부서 20→26mm)
COL_WIDTHS    = [w * mm for w in COL_WIDTHS_MM]

CELL_PAD   = 3 * mm
ROW_H_INFO = 8  * mm
ROW_H_PLAN = 14 * mm
ROW_H_SIGN = 15 * mm
ROW_H_GOAL = 22 * mm

# ─── Paragraph styles ─────────────────────────────────────────────────────────

def mk_style(name, *, font='NG', size=10, leading=14,
             color=C_BLACK, align=TA_LEFT):
    return ParagraphStyle(name=name, fontName=font, fontSize=size,
                          leading=leading, textColor=color, alignment=align,
                          spaceBefore=0, spaceAfter=0)

S_TITLE  = mk_style('title',  font='NGBold', size=16, leading=20, align=TA_CENTER)
S_HDR    = mk_style('hdr',    font='NGBold', size=10, leading=13, align=TA_CENTER)
S_BODY   = mk_style('body',                  size=10, leading=14, align=TA_LEFT)
S_BODY_C = mk_style('body_c',               size=10, leading=14, align=TA_CENTER)
S_BODY_R = mk_style('body_r',               size=10, leading=14, align=TA_RIGHT)
S_SMALL  = mk_style('small',               size=8,  leading=12, color=C_GRAY_TEXT)

def P(text, s=None):
    return Paragraph(text or '', s or S_BODY)

# ─── Table style helpers ───────────────────────────────────────────────────────

_BASE = [
    ('FONTNAME',      (0, 0), (-1, -1), 'NG'),
    ('FONTSIZE',      (0, 0), (-1, -1), 10),
    ('TOPPADDING',    (0, 0), (-1, -1), CELL_PAD),
    ('BOTTOMPADDING', (0, 0), (-1, -1), CELL_PAD),
    ('LEFTPADDING',   (0, 0), (-1, -1), CELL_PAD),
    ('RIGHTPADDING',  (0, 0), (-1, -1), CELL_PAD),
    ('GRID',          (0, 0), (-1, -1), 0.5, C_BLACK),
    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
]

def ts(*extra):
    return TableStyle(list(_BASE) + list(extra))

# ─── Section builders ─────────────────────────────────────────────────────────

def build_title(fields):
    return Table(
        [[P(fields['document']['title'], S_TITLE)]],
        colWidths=[CONTENT_W],
        style=ts(
            ('FONTNAME', (0, 0), (-1, -1), 'NGBold'),
        ),
    )

def build_approval(fields):
    appr = fields['approval']['fields']
    inner = Table(
        [[P(f['label'], S_HDR) for f in appr], ['', '', '']],
        colWidths=[APPR_CELL_W] * 3,
        rowHeights=[None, ROW_H_SIGN],
        style=ts(
            ('FONTNAME',    (0, 0), (-1, 0), 'NGBold'),
            ('BACKGROUND',  (0, 0), (-1, 0), C_HEADER_BG),
            ('LINEWIDTH',   (0, 0), (-1, -1), 0.75),
        ),
    )
    return Table(
        [['', inner]],
        colWidths=[TITLE_W, APPROVAL_W],
        style=TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('LINEWIDTH',     (0, 0), (-1, -1), 0),
        ]),
    )

def build_basic_info(fields):
    bi = {f['id']: f for f in fields['basic_info']['fields']}
    half = CONTENT_W / 2
    return Table(
        [
            [
                P(f"{bi['N01']['label']}: _________________________________"),
                P(f"{bi['N02']['label']}: ______년  ______월  ______일"),
            ],
            [
                P(f"{bi['N04']['label']}: ______년"),
                P(f"{bi['N03']['label']}: ___________________________"),
            ],
        ],
        colWidths=[half, half],
        rowHeights=[ROW_H_INFO, ROW_H_INFO],
        style=ts(),
    )

def build_corporate_goal(fields):
    cg = fields['corporate_goal']
    return Table(
        [[P(cg['label'], S_HDR)], ['']],
        colWidths=[CONTENT_W],
        rowHeights=[None, ROW_H_GOAL],
        style=ts(
            ('FONTNAME',   (0, 0), (-1, 0), 'NGBold'),
            ('BACKGROUND', (0, 0), (-1, 0), C_HEADER_BG),
            ('BACKGROUND', (0, 1), (-1, 1), C_ALT_BG),
        ),
    )

def build_plan_table(fields, example_rows=None):
    cols = fields['plan_table']['columns']
    n_default = fields['plan_table']['default_row_count']
    align_map = {'left': S_BODY, 'center': S_BODY_C, 'right': S_BODY_R}

    header = [P(c['label'], S_HDR) for c in cols]
    rows = [header]

    data_rows = list(example_rows) if example_rows else []
    while len(data_rows) < n_default:
        data_rows.append([''] * len(cols))

    for ri, row_data in enumerate(data_rows):
        row = [P(str(row_data[i] or ''), align_map.get(cols[i].get('align','left'), S_BODY))
               for i in range(len(cols))]
        rows.append(row)

    style_cmds = list(_BASE) + [
        ('FONTNAME',   (0, 0), (-1, 0), 'NGBold'),
        ('BACKGROUND', (0, 0), (-1, 0), C_HEADER_BG),
        ('ROWHEIGHT',  (0, 1), (-1, -1), ROW_H_PLAN),
        ('ALIGN',      (0, 0), (-1, 0), 'CENTER'),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), C_ALT_BG))

    return Table(
        rows,
        colWidths=COL_WIDTHS,
        style=TableStyle(style_cmds),
        repeatRows=1,
    )

# ─── Numbered Canvas (N / 전체 페이지) ────────────────────────────────────────

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
        # Override producer/creator set by ReportLab defaults
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

# ─── Main generator ───────────────────────────────────────────────────────────

def generate(fields_path, out_path, example_rows=None):
    with open(fields_path, encoding='utf-8') as f:
        fields = json.load(f)

    meta = fields['document']
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title=meta['title'],
        author=meta['creator'],
        subject=meta['subject'],
    )

    story = [
        build_title(fields),
        build_approval(fields),
        Spacer(1, 2 * mm),
        build_basic_info(fields),
        Spacer(1, 2 * mm),
        build_corporate_goal(fields),
        Spacer(1, 3 * mm),
        build_plan_table(fields, example_rows),
        Spacer(1, 2 * mm),
        P(fields['plan_table'].get('extra_rows_note', ''), S_SMALL),
    ]

    doc.build(story, canvasmaker=NumberedCanvas)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  PDF → {out_path}  ({size_kb:.0f} KB)")

# ─── Example data ─────────────────────────────────────────────────────────────

EXAMPLE_ROWS = [
    ["안전보건 교육 실시 (신규·정기)", "연 2회\n(3월·9월)", "이수율 100%",       "안전관리팀", "500", ""],
    ["위험성평가 연 1회 실시",          "2월",               "완료 100%",         "각 부서장",  "200", ""],
    ["추락·낙하 예방 설비 점검",        "분기 1회",          "점검 완료율 100%",  "시설팀",     "300", ""],
    ["화학물질 취급 관리 개선",          "상반기",            "누출 0건",           "환경안전팀", "150", ""],
    ["소방 훈련 및 비상대피 실시",       "연 2회",            "참여율 95% 이상",   "총무팀",     "100", ""],
    ["작업환경측정 실시",                "연 2회",            "기준치 이하 유지",  "안전관리팀", "400", ""],
    ["안전보호구 지급 및 관리",          "연간",              "지급률 100%",       "구매팀",     "250", ""],
    ["협력업체 안전 교육",               "분기 1회",          "참여율 90% 이상",   "안전관리팀",  "80", ""],
    ["사고 원인 분석 및 재발방지",       "사고 발생 시",      "재발 0건",           "각 부서장",  "50", ""],
    ["안전문화 캠페인 실시",             "연 4회",            "인지도 향상",        "인사팀",     "120", ""],
]

# 18행: 페이지 분할(QA-03 표 헤더 반복) 검증용
MULTIPAGE_ROWS = EXAMPLE_ROWS + [
    ["근골격계 부담작업 유해요인 조사", "격년",              "조사 완료",          "산업보건팀", "300", ""],
    ["밀폐공간 출입 안전 관리",          "작업 전",           "사고 0건",           "공사관리팀", "100", ""],
    ["신규 입사자 안전 교육",            "입사 즉시",         "이수율 100%",        "인사팀",      "80", ""],
    ["안전보건 예산 집행률 관리",        "분기별",            "집행률 90% 이상",    "경영지원팀", "0",   ""],
    ["도급 계약 안전조건 검토",          "계약 시",           "조건 반영 100%",     "구매팀",      "50", ""],
    ["PSM 정기 감사",                    "연 1회",            "지적 사항 0건",      "안전관리팀", "200", ""],
    ["이상 징후 신고 체계 운영",         "연간",              "신고율 증가",        "안전관리팀",  "30", ""],
    ["안전보건경영시스템 인증 유지",     "연 1회 갱신",       "인증 유지",          "안전관리팀", "500", ""],
]

if __name__ == '__main__':
    sha256 = register_fonts()
    print(f"NanumGothic.ttc  path : {FONT_TTC}")
    print(f"NanumGothic.ttc SHA256: {sha256}")

    base        = Path(__file__).parent
    fields_path = base / 'c002_fields.json'
    out_dir     = base.parent / 'output'
    out_dir.mkdir(exist_ok=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode in ('blank', 'all'):
        generate(fields_path, out_dir / 'TAI-FORM-C002-blank.pdf')
    if mode in ('example', 'all'):
        generate(fields_path, out_dir / 'TAI-FORM-C002-example.pdf', EXAMPLE_ROWS)
    if mode in ('multipage', 'all'):
        generate(fields_path, out_dir / 'TAI-FORM-C002-multipage.pdf', MULTIPAGE_ROWS)
    print("Done (PDF).")
