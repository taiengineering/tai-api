'use strict';
/**
 * TAI REF-C002 DOCX 생성기 — WO-054 시제품
 * Usage: node gen_c002_docx.cjs [blank|example|all]
 */
const fs   = require('fs');
const path = require('path');

const DOCX_DIR = path.resolve(__dirname, 'node_modules', 'docx');
const {
    Document, Packer, Paragraph, TextRun,
    Table, TableRow, TableCell,
    AlignmentType, WidthType, HeightRule, BorderStyle,
    TableLayoutType, ShadingType, VerticalAlign,
    Footer, PageNumber,
    convertMillimetersToTwip,
} = require(DOCX_DIR);

const mm = convertMillimetersToTwip;  // 1mm = 56 twips

// ─── Layout constants ─────────────────────────────────────────────────────────

const CONTENT_W    = mm(170);
const PAGE_MARGIN  = mm(20);
const APPROVAL_W   = mm(90);
const TITLE_W      = CONTENT_W - APPROVAL_W;   // 80mm
const APPR_CELL_W  = Math.round(APPROVAL_W / 3); // 30mm

const COL_W = [56, 26, 22, 26, 22, 18].map(mm);  // F05-F10 (PATCH-1: F08 담당부서 20→26mm)

const ROW_H_INFO = mm(7);   // WO-056: PDF 기준 7mm 통일
const ROW_H_PLAN = mm(14);
const ROW_H_SIGN = mm(15);
const ROW_H_GOAL = mm(20);  // WO-056: PDF 기준 20mm 통일
const CELL_MARGIN = { top: mm(3), bottom: mm(3), left: mm(3), right: mm(3) };

const HEADER_BG = 'E8E8E8';
const ALT_BG    = 'F5F5F5';
const GRAY_TEXT = '505050';

// ─── Cell helpers ─────────────────────────────────────────────────────────────

function border(pt = 4) {
    const s = { style: BorderStyle.SINGLE, size: pt, color: '000000' };
    return { top: s, bottom: s, left: s, right: s };
}

function noBorder() {
    const s = { style: BorderStyle.NONE, size: 0, color: 'auto' };
    return { top: s, bottom: s, left: s, right: s };
}

function shading(fill) {
    return { fill, type: ShadingType.CLEAR, color: 'auto' };
}

function hdrCell(text, widthTwips, bpt = 4) {
    const lines = text.split('\n');
    const runs = [];
    lines.forEach((line, i) => {
        if (i > 0) runs.push(new TextRun({ break: 1 }));
        runs.push(new TextRun({ text: line, font: 'NanumGothic', bold: true, size: 20 }));
    });
    return new TableCell({
        width: { size: widthTwips, type: WidthType.DXA },
        borders: border(bpt),
        shading: shading(HEADER_BG),
        verticalAlign: VerticalAlign.CENTER,
        margins: CELL_MARGIN,
        children: [new Paragraph({ children: runs, alignment: AlignmentType.CENTER })],
    });
}

function bodyCell(text, widthTwips, { bg, align = AlignmentType.LEFT } = {}) {
    return new TableCell({
        width: { size: widthTwips, type: WidthType.DXA },
        borders: border(4),
        shading: shading(bg || 'ffffff'),
        verticalAlign: VerticalAlign.CENTER,
        margins: CELL_MARGIN,
        children: [new Paragraph({
            children: [new TextRun({ text: text || '', font: 'NanumGothic', size: 20 })],
            alignment: align,
        })],
    });
}

function emptyCell(widthTwips, { bg } = {}) {
    return bodyCell('', widthTwips, { bg });
}

// ─── Section: Title (전체 너비) ───────────────────────────────────────────────

function buildTitle(fields) {
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [new TableRow({
            height: { value: mm(14), rule: HeightRule.ATLEAST },
            children: [new TableCell({
                width: { size: CONTENT_W, type: WidthType.DXA },
                borders: border(4),
                verticalAlign: VerticalAlign.CENTER,
                margins: { top: mm(4), bottom: mm(4), left: mm(4), right: mm(4) },
                children: [new Paragraph({
                    children: [new TextRun({ text: fields.document.title, font: 'NanumGothic', bold: true, size: 32 })],
                    alignment: AlignmentType.CENTER,
                })],
            })],
        })],
    });
}

// ─── Section: Approval (제목 아래 우측, WO-057B Candidate B) ─────────────────
// 독립 90mm 우측 정렬 테이블 — 중첩 없음, noBorder 없음
// Google Docs 변환 시 제목 테이블과 병합되지 않도록 분리 단락과 함께 사용

function buildApproval(fields) {
    const apprF = fields.approval.fields;
    return new Table({
        width:     { size: APPROVAL_W, type: WidthType.DXA },
        layout:    TableLayoutType.FIXED,
        alignment: AlignmentType.RIGHT,
        rows: [
            new TableRow({
                height: { value: mm(7), rule: HeightRule.ATLEAST },
                children: apprF.map(f => hdrCell(f.label, APPR_CELL_W, 6)),
            }),
            new TableRow({
                height: { value: ROW_H_SIGN, rule: HeightRule.ATLEAST },
                children: apprF.map(() => new TableCell({
                    width:   { size: APPR_CELL_W, type: WidthType.DXA },
                    borders: border(6),
                    margins: CELL_MARGIN,
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                })),
            }),
        ],
    });
}

// ─── Section: Basic Info ──────────────────────────────────────────────────────

function buildBasicInfo(fields) {
    const bi = {};
    fields.basic_info.fields.forEach(f => { bi[f.id] = f; });
    const half = Math.round(CONTENT_W / 2);
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [
            new TableRow({
                height: { value: ROW_H_INFO, rule: HeightRule.ATLEAST },
                children: [
                    bodyCell(`${bi.N01.label}: `, half),
                    bodyCell(`${bi.N02.label}:      년     월     일`, half),
                ],
            }),
            new TableRow({
                height: { value: ROW_H_INFO, rule: HeightRule.ATLEAST },
                children: [
                    bodyCell(`${bi.N04.label}:      년`, half),
                    bodyCell(`${bi.N03.label}: `, half),
                ],
            }),
        ],
    });
}

// ─── Section: Corporate Goal ──────────────────────────────────────────────────

function buildCorporateGoal(fields) {
    const cg = fields.corporate_goal;
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [
            new TableRow({
                height: { value: mm(7), rule: HeightRule.ATLEAST },
                children: [hdrCell(cg.label, CONTENT_W)],
            }),
            new TableRow({
                height: { value: ROW_H_GOAL, rule: HeightRule.ATLEAST },
                children: [new TableCell({
                    width: { size: CONTENT_W, type: WidthType.DXA },
                    borders: border(4),
                    shading: shading(ALT_BG),
                    margins: CELL_MARGIN,
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                })],
            }),
        ],
    });
}

// ─── Section: Plan Table ──────────────────────────────────────────────────────

function buildPlanTable(fields, exRows) {
    const cols = fields.plan_table.columns;
    const n    = fields.plan_table.default_row_count;
    const alignMap = {
        left:   AlignmentType.LEFT,
        center: AlignmentType.CENTER,
        right:  AlignmentType.RIGHT,
    };

    const rows = [];

    rows.push(new TableRow({
        tableHeader: true,
        height: { value: mm(8), rule: HeightRule.ATLEAST },
        children: cols.map((c, i) => hdrCell(c.label, COL_W[i])),
    }));

    const data = exRows ? [...exRows] : [];
    while (data.length < n) data.push(Array(cols.length).fill(''));

    data.forEach((rowData, ri) => {
        const isAlt = (ri + 1) % 2 === 0;
        rows.push(new TableRow({
            height: { value: ROW_H_PLAN, rule: HeightRule.ATLEAST },
            children: cols.map((c, i) => bodyCell(
                rowData[i] || '',
                COL_W[i],
                { bg: isAlt ? ALT_BG : 'ffffff', align: alignMap[c.align] || AlignmentType.LEFT }
            )),
        }));
    });

    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows,
    });
}

// ─── Footer with page numbers ─────────────────────────────────────────────────

function buildFooter() {
    return new Footer({
        children: [new Paragraph({
            children: [
                new TextRun({ children: [PageNumber.CURRENT], font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
                new TextRun({ text: ' / ',                    font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
            ],
            alignment: AlignmentType.CENTER,
        })],
    });
}

// ─── Document assembler ───────────────────────────────────────────────────────

function buildDoc(fields, exRows) {
    const meta = fields.document;

    function spacer() {
        return new Paragraph({ children: [new TextRun({ text: '' })],
                               spacing: { before: 80, after: 80 } });
    }
    // 제목↔결재란 사이 분리 단락: Google Docs 테이블 병합 방지 (WO-057B)
    function spacer0() {
        return new Paragraph({ children: [new TextRun({ text: '' })],
                               spacing: { before: 0, after: 0 } });
    }

    return new Document({
        creator:        meta.creator,
        description:    meta.subject,
        title:          meta.title,
        lastModifiedBy: meta.producer,
        sections: [{
            properties: {
                page: {
                    size:   { width: mm(210), height: mm(297) },
                    margin: { top: PAGE_MARGIN, bottom: PAGE_MARGIN,
                              left: PAGE_MARGIN, right: PAGE_MARGIN },
                },
            },
            footers: { default: buildFooter() },
            children: [
                buildTitle(fields),
                spacer0(),
                buildApproval(fields),
                spacer(),
                buildBasicInfo(fields),
                spacer(),
                buildCorporateGoal(fields),
                spacer(),
                buildPlanTable(fields, exRows),
                new Paragraph({
                    children: [new TextRun({
                        text:  fields.plan_table.extra_rows_note || '',
                        font:  'NanumGothic',
                        size:  16,
                        color: GRAY_TEXT,
                    })],
                    spacing: { before: 60 },
                }),
            ],
        }],
    });
}

// ─── Example data ─────────────────────────────────────────────────────────────

const EXAMPLE_ROWS = [
    ["안전보건 교육 실시 (신규·정기)", "연 2회 (3월·9월)",  "이수율 100%",       "안전관리팀",  "500",  ""],
    ["위험성평가 연 1회 실시",          "2월",               "완료 100%",          "각 부서장",   "200",  ""],
    ["추락·낙하 예방 설비 점검",        "분기 1회",           "점검 완료율 100%", "시설팀",      "300",  ""],
    ["화학물질 취급 관리 개선",          "상반기",             "누출 0건",            "환경안전팀",  "150",  ""],
    ["소방 훈련 및 비상대피 실시",       "연 2회",             "참여율 95% 이상",   "총무팀",      "100",  ""],
    ["작업환경측정 실시",                "연 2회",             "기준치 이하 유지",  "안전관리팀",  "400",  ""],
    ["안전보호구 지급 및 관리",          "연간",               "지급률 100%",       "구매팀",      "250",  ""],
    ["협력업체 안전 교육",               "분기 1회",           "참여율 90% 이상",   "안전관리팀",   "80",  ""],
    ["사고 원인 분석 및 재발방지",       "사고 발생 시",        "재발 0건",            "각 부서장",    "50",  ""],
    ["안전문화 캠페인 실시",             "연 4회",             "인지도 향상",        "인사팀",      "120",  ""],
];

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
    const fieldsPath = path.join(__dirname, 'c002_fields.json');
    const fields     = JSON.parse(fs.readFileSync(fieldsPath, 'utf8'));
    const outDir     = path.join(__dirname, '..', 'output');
    fs.mkdirSync(outDir, { recursive: true });

    const mode = process.argv[2] || 'all';

    if (mode === 'blank' || mode === 'all') {
        const buf  = await Packer.toBuffer(buildDoc(fields, null));
        const dest = path.join(outDir, 'TAI-FORM-C002-blank.docx');
        fs.writeFileSync(dest, buf);
        console.log(`  DOCX → ${dest}  (${(buf.length/1024).toFixed(1)} KB)`);
    }

    if (mode === 'example' || mode === 'all') {
        const buf  = await Packer.toBuffer(buildDoc(fields, EXAMPLE_ROWS));
        const dest = path.join(outDir, 'TAI-FORM-C002-example.docx');
        fs.writeFileSync(dest, buf);
        console.log(`  DOCX → ${dest}  (${(buf.length/1024).toFixed(1)} KB)`);
    }

    console.log('Done (DOCX).');
}

main().catch(err => { console.error(err); process.exit(1); });
