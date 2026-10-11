'use strict';
/**
 * TAI REF-C012 안전작업 허가서 DOCX 생성기 — WO-058 Phase C-01
 * Entry point only — assembly and rendering via common_v1_engine.cjs.
 * Usage: node gen_c012_docx.cjs [blank|all]
 */
const fs     = require('fs');
const path   = require('path');
const engine = require('./common_v1_engine.cjs');

async function main() {
    const fieldsPath = path.join(__dirname, 'c012_fields.json');
    const outDir     = path.join(__dirname, '..', 'output');
    fs.mkdirSync(outDir, { recursive: true });

    const mode = process.argv[2] || 'blank';
    if (mode === 'blank' || mode === 'all') {
        await engine.generate(fieldsPath, path.join(outDir, 'TAI-FORM-C012-blank.docx'));
    }
    console.log('Done (DOCX).');
}

main().catch(err => { console.error(err); process.exit(1); });
