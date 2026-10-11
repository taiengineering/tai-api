'use strict';
/**
 * WO-057B 후보 생성기 — Google Docs 호환성 테스트 전용 (프로덕션 아님)
 * Usage: node gen_c002_docx_candidate.cjs [A|B|all]
 * Candidate A: 제목-결재란 사이에 분리 단락 삽입
 * Candidate B: 결재란을 중첩 없는 독립 90mm 오른쪽 정렬 테이블로 교체
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

const mm = convertMillimetersToTwip;

const CONTENT_W   = mm(170);
const PAGE_MARGIN = mm(20);
const APPROVAL_W  = mm(90);
const TITLE_W     = CONTENT_W - APPROVAL_W;
const APPR_CELL_W = Math.round(APPROVAL_W / 3);
const COL_W = [56, 26, 22, 26, 22, 18].map(mm);
const ROW_H_INFO = mm(7);
const ROW_H_PLAN = mm(14);
const ROW_H_SIGN = mm(15);
const ROW_H_GOAL = mm(20);
const CELL_MARGIN = { top: mm(3), bottom: mm(3), left: mm(3), right: mm(3) };
const HEADER_BG = 'E8E8E8';
const ALT_BG    = 'F5F5F5';
const GRAY_TEXT = '505050';

function border(pt = 4) {
    const s = { style: BorderStyle.SINGLE, size: pt, color: '000000' };
    return { top: s, bottom: s, left: s, right: s };
}
function noBorder() {
    const s = { style: BorderStyle.NONE, size: 0, color: 'auto' };
    return { top: s, bottom: s, left: s, right: s };
}
function shading(fill) { return { fill, type: ShadingType.CLEAR, color: 'auto' }; }
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

// ─── Candidate A approval: same nested structure, no change ──────────────────
function buildApprovalA(fields) {
    const apprF = fields.approval.fields;
    const innerRows = [
        new TableRow({
            height: { value: mm(7), rule: HeightRule.ATLEAST },
            children: apprF.map(f => hdrCell(f.label, APPR_CELL_W, 6)),
        }),
        new TableRow({
            height: { value: ROW_H_SIGN, rule: HeightRule.ATLEAST },
            children: apprF.map(() => new TableCell({
                width: { size: APPR_CELL_W, type: WidthType.DXA },
                borders: border(6),
                margins: CELL_MARGIN,
                children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
            })),
        }),
    ];
    const innerApproval = new Table({
        width: { size: APPROVAL_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: innerRows,
    });
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [new TableRow({
            children: [
                new TableCell({
                    width: { size: TITLE_W, type: WidthType.DXA },
                    borders: noBorder(),
                    margins: { top: 0, bottom: 0, left: 0, right: 0 },
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                }),
                new TableCell({
                    width: { size: APPROVAL_W, type: WidthType.DXA },
                    borders: noBorder(),
                    margins: { top: 0, bottom: 0, left: 0, right: 0 },
                    children: [innerApproval],
                }),
            ],
        })],
    });
}

// ─── Candidate B approval: independent 90mm table, right-aligned (no nesting) ─
function buildApprovalB(fields) {
    const apprF = fields.approval.fields;
    return new Table({
        width: { size: APPROVAL_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        alignment: AlignmentType.RIGHT,
        rows: [
            new TableRow({
                height: { value: mm(7), rule: HeightRule.ATLEAST },
                children: apprF.map(f => hdrCell(f.label, APPR_CELL_W, 6)),
            }),
            new TableRow({
                height: { value: ROW_H_SIGN, rule: HeightRule.ATLEAST },
                children: apprF.map(() => new TableCell({
                    width: { size: APPR_CELL_W, type: WidthType.DXA },
                    borders: border(6),
                    margins: CELL_MARGIN,
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                })),
            }),
        ],
    });
}

function buildBasicInfo(fields) {
    const bi = {};
    fields.basic_info.fields.forEach(f => { bi[f.id] = f; });
    const half = Math.round(CONTENT_W / 2);
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [
            new TableRow({ height: { value: ROW_H_INFO, rule: HeightRule.ATLEAST }, children: [ bodyCell(`${bi.N01.label}: `, half), bodyCell(`${bi.N02.label}:      년     월     일`, half) ] }),
            new TableRow({ height: { value: ROW_H_INFO, rule: HeightRule.ATLEAST }, children: [ bodyCell(`${bi.N04.label}:      년`, half), bodyCell(`${bi.N03.label}: `, half) ] }),
        ],
    });
}
function buildCorporateGoal(fields) {
    const cg = fields.corporate_goal;
    return new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [
            new TableRow({ height: { value: mm(7), rule: HeightRule.ATLEAST }, children: [hdrCell(cg.label, CONTENT_W)] }),
            new TableRow({ height: { value: ROW_H_GOAL, rule: HeightRule.ATLEAST }, children: [new TableCell({ width: { size: CONTENT_W, type: WidthType.DXA }, borders: border(4), shading: shading(ALT_BG), margins: CELL_MARGIN, children: [new Paragraph({ children: [new TextRun({ text: '' })] })] })] }),
        ],
    });
}
function buildPlanTable(fields) {
    const cols = fields.plan_table.columns;
    const n    = fields.plan_table.default_row_count;
    const alignMap = { left: AlignmentType.LEFT, center: AlignmentType.CENTER, right: AlignmentType.RIGHT };
    const rows = [];
    rows.push(new TableRow({ tableHeader: true, height: { value: mm(8), rule: HeightRule.ATLEAST }, children: cols.map((c, i) => hdrCell(c.label, COL_W[i])) }));
    for (let ri = 0; ri < n; ri++) {
        const isAlt = (ri + 1) % 2 === 0;
        rows.push(new TableRow({ height: { value: ROW_H_PLAN, rule: HeightRule.ATLEAST }, children: cols.map((c, i) => bodyCell('', COL_W[i], { bg: isAlt ? ALT_BG : 'ffffff', align: alignMap[c.align] || AlignmentType.LEFT })) }));
    }
    return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, rows });
}
function buildFooter() {
    return new Footer({ children: [new Paragraph({ children: [
        new TextRun({ children: [PageNumber.CURRENT], font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
        new TextRun({ text: ' / ', font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
    ], alignment: AlignmentType.CENTER })], });
}

function spacer0() {
    // Zero-height separator paragraph — prevents Google Docs table merge
    return new Paragraph({ children: [new TextRun({ text: '' })], spacing: { before: 0, after: 0 } });
}

async function main() {
    const fields  = JSON.parse(fs.readFileSync(path.join(__dirname, 'c002_fields.json'), 'utf8'));
    const outDir  = path.join(__dirname, '..', 'output');
    const mode    = process.argv[2] || 'all';

    function buildDocA(f) {
        function sp() { return new Paragraph({ children: [new TextRun({ text: '' })], spacing: { before: 80, after: 80 } }); }
        return new Document({
            creator: f.document.creator, description: f.document.subject, title: f.document.title, lastModifiedBy: f.document.producer,
            sections: [{ properties: { page: { size: { width: mm(210), height: mm(297) }, margin: { top: PAGE_MARGIN, bottom: PAGE_MARGIN, left: PAGE_MARGIN, right: PAGE_MARGIN } } }, footers: { default: buildFooter() },
            children: [
                buildTitle(f),
                spacer0(),            // ← Candidate A: 분리 단락 삽입
                buildApprovalA(f),
                sp(), buildBasicInfo(f), sp(), buildCorporateGoal(f), sp(), buildPlanTable(f),
                new Paragraph({ children: [new TextRun({ text: f.plan_table.extra_rows_note || '', font: 'NanumGothic', size: 16, color: GRAY_TEXT })], spacing: { before: 60 } }),
            ]}],
        });
    }

    function buildDocB(f) {
        function sp() { return new Paragraph({ children: [new TextRun({ text: '' })], spacing: { before: 80, after: 80 } }); }
        return new Document({
            creator: f.document.creator, description: f.document.subject, title: f.document.title, lastModifiedBy: f.document.producer,
            sections: [{ properties: { page: { size: { width: mm(210), height: mm(297) }, margin: { top: PAGE_MARGIN, bottom: PAGE_MARGIN, left: PAGE_MARGIN, right: PAGE_MARGIN } } }, footers: { default: buildFooter() },
            children: [
                buildTitle(f),
                spacer0(),            // ← Candidate B도 분리 단락 + 중첩 없는 테이블
                buildApprovalB(f),
                sp(), buildBasicInfo(f), sp(), buildCorporateGoal(f), sp(), buildPlanTable(f),
                new Paragraph({ children: [new TextRun({ text: f.plan_table.extra_rows_note || '', font: 'NanumGothic', size: 16, color: GRAY_TEXT })], spacing: { before: 60 } }),
            ]}],
        });
    }

    if (mode === 'A' || mode === 'all') {
        const buf = await Packer.toBuffer(buildDocA(fields));
        const dest = path.join(outDir, 'TAI-FORM-C002-blank-CandidateA.docx');
        fs.writeFileSync(dest, buf);
        console.log(`  CandidateA → ${dest}  (${(buf.length/1024).toFixed(1)} KB)`);
    }
    if (mode === 'B' || mode === 'all') {
        const buf = await Packer.toBuffer(buildDocB(fields));
        const dest = path.join(outDir, 'TAI-FORM-C002-blank-CandidateB.docx');
        fs.writeFileSync(dest, buf);
        console.log(`  CandidateB → ${dest}  (${(buf.length/1024).toFixed(1)} KB)`);
    }
    console.log('Done.');
}
main().catch(err => { console.error(err); process.exit(1); });
