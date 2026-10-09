'use strict';
/**
 * TAI 서식 공통 렌더러 엔진 (DOCX) — common-v1
 * WO-058 Phase C-01 / WO-REF01-059-B2-L01 (landscape 지원)
 */
const fs   = require('fs');
const path = require('path');

const DOCX_DIR = path.resolve(__dirname, 'node_modules', 'docx');
const {
    Document, Packer, Paragraph, TextRun,
    Table, TableRow, TableCell,
    AlignmentType, WidthType, HeightRule, BorderStyle,
    TableLayoutType, ShadingType, VerticalAlign,
    Footer, PageNumber, PageOrientation,
    convertMillimetersToTwip,
} = require(DOCX_DIR);

const mm = convertMillimetersToTwip;

// ─── Layout constants (portrait defaults) ─────────────────────────
const CONTENT_W   = mm(170);   // portrait default — kept for backward compat
const PAGE_MARGIN = mm(20);
const ROW_H_INFO  = mm(7);
const ROW_H_SIGN  = mm(15);
const ROW_H_PLAN  = mm(14);
const CELL_MARGIN = { top: mm(3), bottom: mm(3), left: mm(3), right: mm(3) };
const HEADER_BG   = 'E8E8E8';
const ALT_BG      = 'F5F5F5';
const GRAY_TEXT   = '505050';

// ─── Layout context ───────────────────────────────────────────────

function layoutCtx(fields) {
    const pageCfg     = (fields.document || {}).page || {};
    const orientation = ('orientation' in pageCfg) ? pageCfg.orientation : 'portrait';
    if (orientation === 'landscape') {
        return {
            pageW: mm(297), pageH: mm(210),
            contentW: mm(257),
            orientation: PageOrientation.LANDSCAPE,
        };
    } else if (orientation === 'portrait') {
        return {
            pageW: mm(210), pageH: mm(297),
            contentW: CONTENT_W,
            orientation: PageOrientation.PORTRAIT,
        };
    } else {
        throw new Error(
            `document.page.orientation must be 'portrait' or 'landscape', got '${orientation}'`
        );
    }
}

// ─── Cell helpers ─────────────────────────────────────────────────
function border(pt = 4) {
    const s = { style: BorderStyle.SINGLE, size: pt, color: '000000' };
    return { top: s, bottom: s, left: s, right: s };
}
function shading(fill) {
    return { fill, type: ShadingType.CLEAR, color: 'auto' };
}
function hdrCell(text, widthTwips, bpt = 4) {
    const lines = text.split('\n');
    const runs  = [];
    lines.forEach((line, i) => {
        if (i > 0) runs.push(new TextRun({ break: 1 }));
        runs.push(new TextRun({ text: line, font: 'NanumGothic', bold: true, size: 20 }));
    });
    return new TableCell({
        width: { size: widthTwips, type: WidthType.DXA },
        borders: border(bpt), shading: shading(HEADER_BG),
        verticalAlign: VerticalAlign.CENTER, margins: CELL_MARGIN,
        children: [new Paragraph({ children: runs, alignment: AlignmentType.CENTER })],
    });
}
function bodyCell(text, widthTwips, { bg, align = AlignmentType.LEFT } = {}) {
    return new TableCell({
        width: { size: widthTwips, type: WidthType.DXA },
        borders: border(4), shading: shading(bg || 'ffffff'),
        verticalAlign: VerticalAlign.CENTER, margins: CELL_MARGIN,
        children: [new Paragraph({
            children: [new TextRun({ text: text || '', font: 'NanumGothic', size: 20 })],
            alignment: align,
        })],
    });
}
function labelCell(text, widthTwips) {
    return new TableCell({
        width: { size: widthTwips, type: WidthType.DXA },
        borders: border(4), shading: shading(ALT_BG),
        verticalAlign: VerticalAlign.CENTER, margins: CELL_MARGIN,
        children: [new Paragraph({
            children: [new TextRun({ text: `${text}: `, font: 'NanumGothic', bold: true, size: 20 })],
        })],
    });
}
function spacer()  { return new Paragraph({ children: [new TextRun({ text: '' })], spacing: { before: 80, after: 80 } }); }
function spacer0() { return new Paragraph({ children: [new TextRun({ text: '' })], spacing: { before: 0,  after: 0  } }); }
function buildFooter() {
    return new Footer({ children: [new Paragraph({
        children: [
            new TextRun({ children: [PageNumber.CURRENT],     font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
            new TextRun({ text: ' / ',                         font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'NanumGothic', size: 16, color: GRAY_TEXT }),
        ],
        alignment: AlignmentType.CENTER,
    })] });
}

// ─── Schema validator ─────────────────────────────────────────────
const SUPPORTED_TYPES = new Set(['approval','basic_info','labeled_grid','freeform_area','repeat_table']);
const REQUIRED_ATTRS  = {
    approval:      ['type','total_width_mm','fields'],
    basic_info:    ['type','fields'],
    labeled_grid:  ['type','rows'],
    freeform_area: ['type','label','min_height_mm'],
    repeat_table:  ['type','columns','default_row_count'],
};

function posCheck(val, label) {
    if (typeof val !== 'number' || val <= 0)
        throw new Error(`${label} must be a positive number, got ${JSON.stringify(val)}`);
}

function validate(fields) {
    const doc = fields.document;
    if (!doc) throw new Error("Missing 'document' key");
    for (const a of ['title', 'doc_id', 'creator']) {
        if (!doc[a]) throw new Error(`document.${a} is required`);
        if (typeof doc[a] !== 'string') throw new Error(`document.${a} must be a string`);
    }

    // Validate orientation if specified — fail-closed: only unspecified key defaults to 'portrait'
    const pageCfg     = (doc.page || {});
    const orientation = ('orientation' in pageCfg) ? pageCfg.orientation : 'portrait';
    if (typeof orientation !== 'string' || !['portrait', 'landscape'].includes(orientation))
        throw new Error(
            `document.page.orientation must be 'portrait' or 'landscape', got ${JSON.stringify(orientation)}`
        );
    const expectedContentW = orientation === 'landscape' ? 257 : 170;

    const sections = fields.sections;
    if (!Array.isArray(sections)) throw new Error("'sections' must be an array");

    sections.forEach((s, i) => {
        const t = s.type;
        if (!SUPPORTED_TYPES.has(t))
            throw new Error(`sections[${i}]: unsupported block type '${t}'`);
        for (const a of REQUIRED_ATTRS[t]) {
            if (!(a in s))
                throw new Error(`sections[${i}] (${t}): missing required attr '${a}'`);
        }

        if (t === 'approval') {
            if (!Array.isArray(s.fields) || s.fields.length < 1)
                throw new Error(`sections[${i}] approval: fields must have >= 1 entry`);
            posCheck(s.total_width_mm, `sections[${i}] approval.total_width_mm`);
            s.fields.forEach((f, fi) => {
                if (!f.id)    throw new Error(`sections[${i}] approval fields[${fi}]: missing required attr 'id'`);
                if (!f.label) throw new Error(`sections[${i}] approval fields[${fi}]: missing required attr 'label'`);
            });
        }
        if (t === 'labeled_grid') {
            s.rows.forEach((row, ri) => {
                if (row.length !== 2)
                    throw new Error(`sections[${i}] labeled_grid rows[${ri}]: must have exactly 2 cells`);
            });
            if ('row_height_mm' in s) posCheck(s.row_height_mm, `sections[${i}] labeled_grid.row_height_mm`);
        }
        if (t === 'freeform_area') {
            posCheck(s.min_height_mm, `sections[${i}] freeform_area.min_height_mm`);
        }
        if (t === 'repeat_table') {
            if (!s.columns.length)
                throw new Error(`sections[${i}] repeat_table: columns must not be empty`);
            s.columns.forEach((col, ci) => {
                posCheck(col.width_mm, `sections[${i}] repeat_table columns[${ci}].width_mm`);
                if (!col.id) throw new Error(`sections[${i}] repeat_table columns[${ci}]: missing required attr 'id'`);
            });
            const total = s.columns.reduce((acc, c) => acc + (c.width_mm || 0), 0);
            if (Math.abs(total - expectedContentW) > 0.5)
                throw new Error(
                    `sections[${i}] repeat_table: column widths sum to ${total}mm, expected ${expectedContentW}mm`
                );
            if ('min_row_height_mm' in s) posCheck(s.min_row_height_mm, `sections[${i}] repeat_table.min_row_height_mm`);
        }
    });
    return true;
}

// ─── Section builders ─────────────────────────────────────────────

function buildTitle(fields, contentW) {
    const cw = contentW || CONTENT_W;
    return new Table({
        width: { size: cw, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [new TableRow({
            height: { value: mm(14), rule: HeightRule.ATLEAST },
            children: [new TableCell({
                width: { size: cw, type: WidthType.DXA },
                borders: border(4), verticalAlign: VerticalAlign.CENTER,
                margins: { top: mm(4), bottom: mm(4), left: mm(4), right: mm(4) },
                children: [new Paragraph({
                    children: [new TextRun({ text: fields.document.title, font: 'NanumGothic', bold: true, size: 32 })],
                    alignment: AlignmentType.CENTER,
                })],
            })],
        })],
    });
}

function buildApproval(section, contentW) {
    const cw     = contentW || CONTENT_W;
    const apprF  = section.fields;
    const n      = apprF.length;
    const totW   = mm(section.total_width_mm);
    const cellW  = Math.round(totW / n);
    const hdrH   = mm(section.min_header_height_mm ?? 7);
    const signH  = mm(section.min_sign_height_mm  ?? 15);

    return new Table({
        width: { size: totW, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        alignment: AlignmentType.RIGHT,
        rows: [
            new TableRow({
                height: { value: hdrH, rule: HeightRule.ATLEAST },
                children: apprF.map(f => hdrCell(f.label, cellW, 6)),
            }),
            new TableRow({
                height: { value: signH, rule: HeightRule.ATLEAST },
                children: apprF.map(() => new TableCell({
                    width: { size: cellW, type: WidthType.DXA },
                    borders: border(6), margins: CELL_MARGIN,
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                })),
            }),
        ],
    });
}

function buildBasicInfo(section, contentW) {
    const cw   = contentW || CONTENT_W;
    const flds = section.fields;
    const half = Math.round(cw / 2);
    const rows = [];
    for (let i = 0; i < flds.length; i += 2) {
        const L = flds[i], R = flds[i + 1];
        rows.push(new TableRow({
            height: { value: ROW_H_INFO, rule: HeightRule.ATLEAST },
            children: [
                bodyCell(L ? `${L.label}: ` : '', half),
                bodyCell(R ? `${R.label}: ` : '', half),
            ],
        }));
    }
    return new Table({ width: { size: cw, type: WidthType.DXA }, layout: TableLayoutType.FIXED, rows });
}

function buildLabeledGrid(section, contentW) {
    const cw = contentW || CONTENT_W;
    const { section_label, rows: rowsData, row_height_mm = 7 } = section;
    const half   = Math.round(cw / 2);
    const rowH   = mm(row_height_mm);
    const tRows  = [];

    if (section_label) {
        tRows.push(new TableRow({
            height: { value: mm(7), rule: HeightRule.ATLEAST },
            children: [new TableCell({
                columnSpan: 2,
                width: { size: cw, type: WidthType.DXA },
                borders: border(4), shading: shading(HEADER_BG),
                verticalAlign: VerticalAlign.CENTER, margins: CELL_MARGIN,
                children: [new Paragraph({
                    children: [new TextRun({ text: section_label, font: 'NanumGothic', bold: true, size: 20 })],
                    alignment: AlignmentType.CENTER,
                })],
            })],
        }));
    }
    for (const row of rowsData) {
        tRows.push(new TableRow({
            height: { value: rowH, rule: HeightRule.ATLEAST },
            children: row.map(cell => labelCell(cell.label, half)),
        }));
    }
    return new Table({ width: { size: cw, type: WidthType.DXA }, layout: TableLayoutType.FIXED, rows: tRows });
}

function buildFreeformArea(section, contentW) {
    const cw   = contentW || CONTENT_W;
    const minH = mm(section.min_height_mm);
    return new Table({
        width: { size: cw, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        rows: [
            new TableRow({
                height: { value: mm(7), rule: HeightRule.ATLEAST },
                children: [hdrCell(section.label, cw)],
            }),
            new TableRow({
                height: { value: minH, rule: HeightRule.ATLEAST },
                children: [new TableCell({
                    width: { size: cw, type: WidthType.DXA },
                    borders: border(4), shading: shading(ALT_BG), margins: CELL_MARGIN,
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                })],
            }),
        ],
    });
}

function buildRepeatTable(section, exRows, contentW) {
    const cw    = contentW || CONTENT_W;
    const cols  = section.columns;
    const n     = section.default_row_count;
    const colW  = cols.map(c => mm(c.width_mm));
    const rowH  = mm(section.min_row_height_mm ?? 14);
    const alignM = { left: AlignmentType.LEFT, center: AlignmentType.CENTER, right: AlignmentType.RIGHT };
    const rows  = [];

    rows.push(new TableRow({
        tableHeader: true,
        height: { value: mm(8), rule: HeightRule.ATLEAST },
        children: cols.map((c, i) => hdrCell(c.label, colW[i])),
    }));

    const data = exRows ? [...exRows] : [];
    while (data.length < n) data.push(Array(cols.length).fill(''));
    data.forEach((rd, ri) => {
        const isAlt = (ri + 1) % 2 === 0;
        rows.push(new TableRow({
            height: { value: rowH, rule: HeightRule.ATLEAST },
            children: cols.map((c, i) => bodyCell(
                rd[i] || '', colW[i],
                { bg: isAlt ? ALT_BG : 'ffffff', align: alignM[c.align] || AlignmentType.LEFT }
            )),
        }));
    });
    // Table width = sum of column widths (from JSON, already correct for portrait/landscape)
    const tblW = colW.reduce((a, b) => a + b, 0);
    return new Table({ width: { size: tblW, type: WidthType.DXA }, layout: TableLayoutType.FIXED, rows });
}

// ─── Common assembler ──────────────────────────────────────────────

function assemble(fields, exRows, contentW) {
    const cw = contentW || CONTENT_W;
    const children = [buildTitle(fields, cw), spacer0()];
    for (const s of (fields.sections ?? [])) {
        switch (s.type) {
            case 'approval':      children.push(buildApproval(s, cw));            break;
            case 'basic_info':    children.push(buildBasicInfo(s, cw));           break;
            case 'labeled_grid':  children.push(buildLabeledGrid(s, cw));         break;
            case 'freeform_area': children.push(buildFreeformArea(s, cw));        break;
            case 'repeat_table':  children.push(buildRepeatTable(s, exRows, cw)); break;
            default: throw new Error(`Unsupported block type: ${s.type}`);
        }
        children.push(spacer());
    }
    return children;
}

// ─── Document generator ───────────────────────────────────────────

async function generate(fieldsPath, outPath, exRows) {
    const fields = JSON.parse(fs.readFileSync(fieldsPath, 'utf8'));
    validate(fields);
    const ctx  = layoutCtx(fields);
    const meta = fields.document;
    const doc  = new Document({
        creator: meta.creator, title: meta.title,
        description: meta.subject || '', lastModifiedBy: meta.producer || 'TAI Document Pipeline v1',
        sections: [{
            properties: { page: {
                size: {
                    width:       ctx.pageW,
                    height:      ctx.pageH,
                    orientation: ctx.orientation,
                },
                margin: { top: PAGE_MARGIN, bottom: PAGE_MARGIN, left: PAGE_MARGIN, right: PAGE_MARGIN },
            }},
            footers: { default: buildFooter() },
            children: assemble(fields, exRows, ctx.contentW),
        }],
    });
    const buf = await Packer.toBuffer(doc);
    fs.writeFileSync(outPath, buf);
    console.log(`  DOCX → ${outPath}  (${(buf.length/1024).toFixed(1)} KB)`);
}

module.exports = { validate, layoutCtx, buildTitle, buildApproval, buildBasicInfo,
    buildLabeledGrid, buildFreeformArea, buildRepeatTable,
    buildFooter, assemble, generate, spacer, spacer0,
    CONTENT_W, PAGE_MARGIN };
