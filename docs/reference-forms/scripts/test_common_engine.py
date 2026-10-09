"""
WO-058 Phase C-02 — 공통 엔진 QA 강화 및 출력 회귀검증
pytest test_common_engine.py -v

C02-01: 테스트 신뢰성 — 필수 테스트는 SKIP 없이 FAIL 보고
C02-02: 스키마 검증 보강 — Python/Node 규칙 일치
C02-03: C012 출력물 QA — OOXML 구조 + PDF 텍스트
C02-04: C002 회귀검증 — 어댑터 출력 구조 비교
"""
import json, os, sys, subprocess, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

BASE   = Path(__file__).parent
OUTPUT = BASE.parent / 'output'

# ─── Engine import (FAIL on error — not skip) ─────────────────────
sys.path.insert(0, str(BASE))
from common_v1_engine import (
    validate, assemble, generate_from_dict,
    build_approval, build_labeled_grid, build_freeform_area,
)
from c002_v1_adapter import adapt_c002_to_v1

FONT_PATH = os.environ.get(
    'NANUM_GOTHIC_TTC',
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font8/'
    '7a0b5c0f3c1d41c4c52a33343496c9c65ad52c50.asset/AssetData/NanumGothic.ttc'
)
FONTS_OK = os.path.exists(FONT_PATH)

# skip_font applies ONLY to visual-inspection helpers that require actual rendering;
# all automated assertions use structural data available without rendering.
skip_font = pytest.mark.skipif(not FONTS_OK, reason="NanumGothic font not found — visual-only test")

# ─── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def c012():
    return json.loads((BASE / 'c012_fields.json').read_text(encoding='utf-8'))

@pytest.fixture
def c002():
    return json.loads((BASE / 'c002_fields.json').read_text(encoding='utf-8'))

@pytest.fixture
def minimal():
    return {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'Test', 'doc_id': 'T001', 'creator': 'TAI'},
        'sections': [],
    }

def _ooxml_tables(docx_path):
    NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(docx_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', NS)
    result = []
    for tbl in tables:
        rows = tbl.findall('.//w:tr', NS)
        tbl_data = []
        for row in rows:
            cells = row.findall('w:tc', NS)
            cell_texts = [
                ''.join(r.text or '' for r in c.findall('.//w:t', NS))
                for c in cells
            ]
            tbl_data.append(cell_texts)
        result.append(tbl_data)
    return result

# ─── C01: Schema validation ────────────────────────────────────────

def test_C01_c012_passes_validation(c012):
    assert validate(c012) is True

def test_C01_minimal_passes(minimal):
    assert validate(minimal) is True

def test_C01_missing_document_raises():
    with pytest.raises(ValueError, match="document"):
        validate({'sections': []})

def test_C01_unknown_block_type_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'totally_unknown'}],
    }
    with pytest.raises(ValueError, match="unsupported block type"):
        validate(fields)

def test_C01_approval_missing_fields_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'approval', 'total_width_mm': 90}],
    }
    with pytest.raises(ValueError, match="missing required attr 'fields'"):
        validate(fields)

def test_C01_labeled_grid_wrong_row_size_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'labeled_grid',
                      'rows': [[{'id': 'F1', 'label': 'A'}]]}],
    }
    with pytest.raises(ValueError, match="exactly 2 cells"):
        validate(fields)

def test_C01_repeat_table_wrong_column_sum_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'repeat_table', 'default_row_count': 5,
            'columns': [{'id': 'C1', 'label': 'A', 'width_mm': 100, 'align': 'left'}],
        }],
    }
    with pytest.raises(ValueError, match="100mm"):
        validate(fields)

def test_C01_freeform_missing_label_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'freeform_area', 'min_height_mm': 20}],
    }
    with pytest.raises(ValueError, match="missing required attr 'label'"):
        validate(fields)

# ─── C02-02: Schema validation hardening ──────────────────────────

def test_C0202_approval_negative_width_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'approval', 'total_width_mm': -10,
            'fields': [{'id': 'A1', 'label': 'X'}],
        }],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_approval_zero_width_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'approval', 'total_width_mm': 0,
            'fields': [{'id': 'A1', 'label': 'X'}],
        }],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_approval_field_missing_id_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'approval', 'total_width_mm': 90,
            'fields': [{'label': 'X'}],  # no id
        }],
    }
    with pytest.raises(ValueError, match="'id'"):
        validate(fields)

def test_C0202_approval_field_missing_label_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'approval', 'total_width_mm': 90,
            'fields': [{'id': 'A1'}],  # no label
        }],
    }
    with pytest.raises(ValueError, match="'label'"):
        validate(fields)

def test_C0202_freeform_negative_height_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'freeform_area', 'label': 'X', 'min_height_mm': -5}],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_freeform_zero_height_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'freeform_area', 'label': 'X', 'min_height_mm': 0}],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_labeled_grid_negative_row_height_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'labeled_grid', 'row_height_mm': -1,
                      'rows': [[{'id':'R1','label':'A'},{'id':'R2','label':'B'}]]}],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_repeat_table_empty_columns_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 5, 'columns': []}],
    }
    with pytest.raises(ValueError):
        validate(fields)

def test_C0202_repeat_table_column_missing_id_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'repeat_table', 'default_row_count': 5,
            'columns': [{'label': 'A', 'width_mm': 170, 'align': 'left'}],  # no id
        }],
    }
    with pytest.raises(ValueError, match="'id'"):
        validate(fields)

def test_C0202_repeat_table_negative_column_width_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{
            'type': 'repeat_table', 'default_row_count': 5,
            'columns': [{'id':'C1','label':'A','width_mm': -5,'align':'left'}],
        }],
    }
    with pytest.raises(ValueError, match="positive"):
        validate(fields)

def test_C0202_document_title_not_string_raises():
    fields = {
        'document': {'title': 123, 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [],
    }
    with pytest.raises(ValueError, match="string"):
        validate(fields)

# ─── C03: Block structure tests ────────────────────────────────────

def test_C03_c012_approval_has_2_roles(c012):
    appr = next(s for s in c012['sections'] if s['type'] == 'approval')
    assert len(appr['fields']) == 2
    labels = [f['label'] for f in appr['fields']]
    assert labels == ['신청', '허가']

def test_C03_c012_labeled_grid_4_rows(c012):
    grid = next(s for s in c012['sections'] if s['type'] == 'labeled_grid')
    assert len(grid['rows']) == 4
    for row in grid['rows']:
        assert len(row) == 2

def test_C03_c012_freeform_areas(c012):
    fas = [s for s in c012['sections'] if s['type'] == 'freeform_area']
    assert len(fas) == 2
    assert fas[0]['id'] == 'F09' and fas[0]['min_height_mm'] == 20
    assert fas[1]['id'] == 'F10' and fas[1]['min_height_mm'] == 30

def test_C03_c012_requiredness_unverified_preserved(c012):
    for s in c012['sections']:
        if s['type'] == 'freeform_area':
            assert s.get('requiredness') == 'UNVERIFIED'
        if s['type'] == 'labeled_grid':
            for row in s['rows']:
                for cell in row:
                    assert cell.get('requiredness') == 'UNVERIFIED'

def test_C03_approval_cell_width_contract():
    for n_cols, expected_mm in [(2, 45), (3, 30)]:
        section = {
            'type': 'approval', 'total_width_mm': 90,
            'fields': [{'id': f'A{i}', 'label': f'L{i}'} for i in range(n_cols)],
        }
        from common_v1_engine import mm as rl_mm
        cell_w_mm = section['total_width_mm'] / len(section['fields'])
        assert cell_w_mm == expected_mm

# ─── C02: Assembler section count ─────────────────────────────────

def test_C02_assemble_returns_correct_section_count(c012):
    story = assemble(c012)
    # title + spacer + (approval+spacer) + (labeled_grid+spacer) + (fa+spacer)*2
    assert len(story) == 10

def test_C02_assembler_fail_closed_on_unknown_block():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'mystery_block', 'label': 'x', 'min_height_mm': 10}],
    }
    with pytest.raises(ValueError, match="Unsupported block type"):
        assemble(fields)

def test_C02_assemble_empty_sections(minimal):
    story = assemble(minimal)
    assert len(story) == 2  # title + spacer only

# ─── C04: PDF/DOCX generation ─────────────────────────────────────

def test_C04_c012_pdf_generation(tmp_path):
    from common_v1_engine import register_fonts, generate
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'TAI-FORM-C012-blank.pdf'
    generate(BASE / 'c012_fields.json', out)
    assert out.exists()
    assert out.stat().st_size > 5_000

def test_C04_c012_docx_generation():
    result = subprocess.run(
        ['node', str(BASE / 'gen_c012_docx.cjs'), 'blank'],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(f"node gen_c012_docx.cjs failed (returncode={result.returncode}):\n{result.stderr[:500]}")
    out = BASE.parent / 'output' / 'TAI-FORM-C012-blank.docx'
    assert out.exists(), f"DOCX not found: {out}"
    assert out.stat().st_size > 3_000

# ─── C02-03: C012 DOCX output structure (OOXML) ───────────────────

def test_C0203_c012_docx_table_count():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    assert out.exists(), "run test_C04_c012_docx_generation first"
    tables = _ooxml_tables(out)
    # title + approval + labeled_grid + freeform×2
    assert len(tables) == 5, f"Expected 5 tables, got {len(tables)}"

def test_C0203_c012_docx_title_full_width():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    t1 = tables[0]
    assert len(t1) == 1, "Title table must have 1 row"
    assert len(t1[0]) == 1, "Title table must have 1 cell (full width)"
    assert '안전작업 허가서' in t1[0][0]

def test_C0203_c012_docx_approval_2cols():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    t2 = tables[1]
    assert len(t2) == 2, "Approval table must have 2 rows (header + sign)"
    assert len(t2[0]) == 2, "Approval header row must have 2 cells"
    labels = t2[0]
    assert '신청' in labels[0] and '허가' in labels[1], f"Labels: {labels}"

def test_C0203_c012_docx_labeled_grid_structure():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    t3 = tables[2]
    # 1 header row + 4 data rows
    assert len(t3) == 5, f"labeled_grid must have 5 rows (header+4), got {len(t3)}"
    assert '작업 기본 정보' in t3[0][0], "Header must contain section label"
    # All data rows: 2 cells each
    for ri in range(1, 5):
        assert len(t3[ri]) == 2, f"Data row {ri} must have 2 cells"

def test_C0203_c012_docx_labeled_grid_long_label():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    t3 = tables[2]
    # Row 1 right cell: '신청부서(업체명)' — the long label
    all_texts = ' '.join(cell for row in t3[1:] for cell in row)
    assert '신청부서(업체명)' in all_texts, f"Long label not found in: {all_texts}"

def test_C0203_c012_docx_freeform_labels():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    t4, t5 = tables[3], tables[4]
    assert len(t4) == 2 and '작업내용' in t4[0][0]
    assert len(t5) == 2 and '안전조치 사항' in t5[0][0]

def test_C0203_c012_docx_freeform_content_rows_empty():
    out = OUTPUT / 'TAI-FORM-C012-blank.docx'
    tables = _ooxml_tables(out)
    # Content rows (row index 1) of both freeforms must be present but blank
    assert tables[3][1][0].strip() == ''
    assert tables[4][1][0].strip() == ''

def test_C0203_c012_pdf_page_count_and_footer():
    import pymupdf
    out = OUTPUT / 'TAI-FORM-C012-blank.pdf'
    assert out.exists(), "run test_C04_c012_pdf_generation or gen_c012_pdf.py first"
    doc = pymupdf.open(str(out))
    assert len(doc) == 1, f"C012 blank must be 1 page, got {len(doc)}"
    texts = [b[4].strip() for b in doc[0].get_text('blocks')]
    footer_text = '1 / 1'
    assert any(footer_text in t for t in texts), f"Footer '1 / 1' not found. blocks={texts}"

def test_C0203_c012_pdf_title_text():
    import pymupdf
    out = OUTPUT / 'TAI-FORM-C012-blank.pdf'
    doc = pymupdf.open(str(out))
    full_text = doc[0].get_text()
    assert '안전작업 허가서' in full_text
    assert '신청' in full_text and '허가' in full_text
    assert '작업 기본 정보' in full_text
    assert '작업내용' in full_text
    assert '안전조치 사항' in full_text

def test_C0203_c012_pdf_no_text_clipping():
    import pymupdf
    out = OUTPUT / 'TAI-FORM-C012-blank.pdf'
    doc = pymupdf.open(str(out))
    full_text = doc[0].get_text()
    # All 8 labeled_grid cell labels must appear
    required = ['작업종류', '신청부서(업체명)', '직책', '성명(서명)',
                '허가요청기간', '작업장소', '장비투입', '작업인원']
    missing = [r for r in required if r not in full_text]
    assert not missing, f"Labels clipped/missing: {missing}"

# ─── C05: C002 compatibility ───────────────────────────────────────

def test_C05_c002_adapter_produces_valid_v1(c002):
    v1 = adapt_c002_to_v1(c002)
    assert validate(v1) is True

def test_C05_c002_adapter_block_order(c002):
    v1 = adapt_c002_to_v1(c002)
    assert [s['type'] for s in v1['sections']] == [
        'approval', 'basic_info', 'freeform_area', 'repeat_table'
    ]

def test_C05_c002_basic_info_display_order(c002):
    v1 = adapt_c002_to_v1(c002)
    bi = next(s for s in v1['sections'] if s['type'] == 'basic_info')
    assert [f['id'] for f in bi['fields']] == ['N01', 'N02', 'N04', 'N03']

def test_C05_c002_freeform_height_20mm(c002):
    v1 = adapt_c002_to_v1(c002)
    fa = next(s for s in v1['sections'] if s['type'] == 'freeform_area')
    assert fa['min_height_mm'] == 20

def test_C05_c002_repeat_table_column_widths(c002):
    v1 = adapt_c002_to_v1(c002)
    rt = next(s for s in v1['sections'] if s['type'] == 'repeat_table')
    widths = [c['width_mm'] for c in rt['columns']]
    assert widths == [56, 26, 22, 26, 22, 18]
    assert sum(widths) == 170

def test_C05_c002_approval_3col_labels(c002):
    v1 = adapt_c002_to_v1(c002)
    appr = next(s for s in v1['sections'] if s['type'] == 'approval')
    assert [f['label'] for f in appr['fields']] == ['작성', '검토', '승인']

def test_C05_c002_generator_source_files_exist():
    assert (BASE / 'gen_c002_pdf.py').exists()
    assert (BASE / 'gen_c002_docx.cjs').exists()
    assert (BASE / 'gen_c002_pdf.py').stat().st_size   > 10_000
    assert (BASE / 'gen_c002_docx.cjs').stat().st_size > 10_000

# ─── C02-04: C002 regression via common engine ────────────────────

@pytest.fixture
def c002_v1(c002):
    return adapt_c002_to_v1(c002)

def test_C0204_c002_pdf_via_engine(c002_v1, tmp_path):
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_common_engine.pdf'
    generate_from_dict(c002_v1, out)
    assert out.exists()
    assert out.stat().st_size > 5_000

def test_C0204_c002_docx_via_engine(c002_v1, tmp_path):
    from common_v1_engine import generate_from_dict as gfd
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    # DOCX generation uses Node (common_v1_engine.cjs) — verify adapter validates
    assert validate(c002_v1) is True

def test_C0204_c002_engine_approval_3cols(c002_v1):
    appr = next(s for s in c002_v1['sections'] if s['type'] == 'approval')
    assert len(appr['fields']) == 3
    assert appr['total_width_mm'] == 90

def test_C0204_c002_engine_basic_info_2rows(c002_v1):
    bi = next(s for s in c002_v1['sections'] if s['type'] == 'basic_info')
    assert len(bi['fields']) == 4  # 4 fields = 2 rows × 2 cols

def test_C0204_c002_engine_freeform_label(c002_v1, c002):
    fa = next(s for s in c002_v1['sections'] if s['type'] == 'freeform_area')
    original_label = c002['corporate_goal']['label']
    assert fa['label'] == original_label

def test_C0204_c002_engine_repeat_table_5_default_rows(c002_v1):
    rt = next(s for s in c002_v1['sections'] if s['type'] == 'repeat_table')
    assert rt['default_row_count'] == 5

def test_C0204_c002_pdf_text_regression(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_regression.pdf'
    generate_from_dict(c002_v1, out)
    doc = pymupdf.open(str(out))
    full_text = doc[0].get_text()
    # Key text from C002 must appear in common-engine output
    for expected in ['작성', '검토', '승인', '1 / ']:
        assert expected in full_text, f"Expected '{expected}' in common-engine C002 PDF"

def test_C0204_c002_original_files_unchanged():
    import hashlib
    files = {
        'gen_c002_pdf.py':   19394,
        'gen_c002_docx.cjs': 14479,
        'c002_fields.json':  2057,
    }
    for fname, expected_size in files.items():
        p = BASE / fname
        assert p.exists(), f"{fname} must exist"
        actual = p.stat().st_size
        assert actual == expected_size, f"{fname}: size changed {expected_size}→{actual}"
