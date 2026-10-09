'use strict';
/**
 * C002 공통 엔진 DOCX 생성 진입점 — WO-058 Phase C-03
 * Usage: node gen_c002_docx_common.cjs <input_v1.json> <output.docx> [extra_row_count]
 *
 * input_v1.json: common-v1 형식 JSON (c002_v1_adapter.py 출력 또는 any form)
 * extra_row_count: repeat_table에 추가할 빈 행 수 (기본 0; 다중페이지 테스트용)
 */
const fs     = require('fs');
const path   = require('path');
const engine = require('./common_v1_engine.cjs');

async function main() {
    const args       = process.argv.slice(2);
    const inputPath  = args[0];
    const outputPath = args[1];
    const extraRows  = parseInt(args[2] || '0', 10);

    if (!inputPath || !outputPath) {
        process.stderr.write(
            'Usage: node gen_c002_docx_common.cjs <input_v1.json> <output.docx> [extra_row_count]\n'
        );
        process.exit(1);
    }

    let exRows = null;
    if (extraRows > 0) {
        const fields = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
        const rt     = (fields.sections || []).find(s => s.type === 'repeat_table');
        const nCols  = rt && rt.columns ? rt.columns.length : 6;
        exRows = Array.from({ length: extraRows }, () => Array(nCols).fill(''));
    }

    await engine.generate(inputPath, outputPath, exRows);
    console.log('Done (DOCX).');
}

main().catch(err => { console.error(err.message || err); process.exit(1); });
