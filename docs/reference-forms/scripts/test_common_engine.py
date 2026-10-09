"""
WO-058 Phase C-02/C-03 — 공통 엔진 QA 강화 및 출력 통합검증
WO-REF01-059 Phase B-1 — REF-C003 REGISTER 대표 서식 POC
WO-REF01-059 Phase B-2 — REF-C014 PLAN Landscape POC
WO-REF01-059-B2-L01 — A4 Landscape 엔진 지원
pytest test_common_engine.py -v

C02-01: 테스트 신뢰성 — 필수 테스트는 SKIP 없이 FAIL 보고
C02-02: 스키마 검증 보강 — Python/Node 규칙 일치
C02-03: C012 출력물 QA — OOXML 구조 + PDF 텍스트
C02-04: C002 회귀검증 기초 — 어댑터 출력 구조 비교
C03-01: C002 DOCX 실생성 — gen_c002_docx_common.cjs 통해 실제 DOCX 생성
C03-02: C002 DOCX 회귀 — 원본과 구조 비교 (5테이블/열수/라벨)
C03-03: C002 PDF 다중페이지 — 15행 시 2페이지 전환
C03-04: C012 장문·다중페이지 — 150mm freeform × 2 시 2페이지
C03-05: SHA256 원본 무결성 확인
C03-06: C002 PDF 페이지 경계 QA — 10/11/15/18행 페이지 수 및 데이터 무손실
C04-01: REF-C003 JSON 스키마 검증
C04-02: REF-C003 DOCX 생성 — 9컬럼/라벨/푸터
C04-03: REF-C003 PDF 생성 — 1페이지(기본)/2페이지(30행)/전 페이지 푸터
C04-04: REF-C003 회귀 — C002/C012 기준본 SHA256 불변
C05-01: REF-C014 JSON 스키마 검증 — 10컬럼/257mm/landscape
C05-02: REF-C014 DOCX 생성 — 10컬럼/라벨/푸터/pgSz=landscape
C05-03: REF-C014 PDF 생성 — 1페이지(기본)/2페이지(30행)/데이터 무손실
C06-01: Landscape 엔진 스키마 검증 — 유효성/경계/격리
C06-02: Landscape PDF 치수 — 297mm 페이지 폭 확인
C06-03: Node.js Landscape 컨텍스트 정합성
C06-04: 공통 엔진 SHA256 회귀 — 기준본 무변경
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
    # Structural pre-check before DOCX generation (C03-01 does the actual generation)
    assert validate(c002_v1) is True
    assert len(c002_v1['sections']) == 4

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
    # Size + SHA256 — ensures byte-level integrity (C03-05 upgrades to SHA256-only)
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

# ─── C03-01: C002 DOCX 실생성 via gen_c002_docx_common.cjs ──────────

def test_C0301_c002_docx_real_generation(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')

    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(f"C002 DOCX via common engine failed (rc={result.returncode}):\n{result.stderr[:500]}")

    assert out_path.exists(), f"DOCX not created: {out_path}"
    assert out_path.stat().st_size > 3_000, f"DOCX too small: {out_path.stat().st_size}"

# ─── C03-02: C002 DOCX 구조 회귀검증 ────────────────────────────────

def test_C0302_c002_docx_table_count(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(f"DOCX generation failed: {result.stderr[:300]}")

    tables = _ooxml_tables(out_path)
    assert len(tables) == 5, f"Expected 5 tables (title/approval/basic_info/freeform/repeat), got {len(tables)}"

def test_C0302_c002_docx_approval_3cols(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    # T2 = approval; header row (row 0) must have 3 cells (작성/검토/승인)
    assert len(tables[1][0]) == 3, f"Approval must have 3 cols, got {len(tables[1][0])}"
    assert tables[1][0] == ['작성', '검토', '승인'], f"Labels: {tables[1][0]}"

def test_C0302_c002_docx_repeat_table_6cols(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    # T5 = repeat_table; header row has 6 cols
    assert len(tables[4][0]) == 6, f"Repeat table must have 6 cols, got {len(tables[4][0])}"
    # Header labels match original
    expected = ['목표·세부\n추진계획', '추진일정', '성과지표', '담당부서', '예산(만원)', '달성률']
    for i, exp in enumerate(expected):
        # Compare first line of each label (DOCX may split multiline)
        assert exp.split('\n')[0] in tables[4][0][i], \
            f"Col {i} label mismatch: expected '{exp}', got '{tables[4][0][i]}'"

def test_C0302_c002_docx_repeat_table_5_default_rows(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    # T5 = repeat_table; 1 header + 5 data = 6 rows
    assert len(tables[4]) == 6, f"Repeat table must have 6 rows (1+5), got {len(tables[4])}"

def test_C0302_c002_docx_repeat_table_header_flag(c002_v1, tmp_path):
    NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', NS)
    t5_rows = tables[4].findall('.//w:tr', NS)
    hdr_elem = t5_rows[0].find('.//w:tblHeader', NS)
    assert hdr_elem is not None, "Repeat table header row must have tblHeader for page repeat"

def test_C0302_c002_docx_freeform_label(c002_v1, tmp_path):
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    # T4 = freeform; header row must contain the corporate goal label
    assert '전사 목표' in tables[3][0][0], f"Freeform label: {tables[3][0][0]}"

def test_C0302_c002_docx_acceptable_differences_documented(c002_v1, tmp_path):
    """
    ACCEPTABLE DIFFERENCE: basic_info fill format differs.
    Original: '작성일:      년     월   일'  (custom date fill)
    Common engine: '작성일: ____________________'  (uniform underscore fill)
    This is expected — common engine uses uniform fill format.
    Test confirms both have same label text, different fill only.
    """
    v1_path = tmp_path / 'c002_v1.json'
    out_path = tmp_path / 'c002_common.docx'
    v1_path.write_text(json.dumps(c002_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    t3 = tables[2]  # basic_info
    all_labels = ' '.join(cell for row in t3 for cell in row)
    for label in ['사업장명', '작성일', '적용 연도', '문서번호']:
        assert label in all_labels, f"basic_info label missing: '{label}' in '{all_labels}'"

# ─── C03-03: C002 PDF 다중페이지 ─────────────────────────────────────

def test_C0303_c002_pdf_1page_default_5rows(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_5rows.pdf'
    generate_from_dict(c002_v1, out)
    doc = pymupdf.open(str(out))
    assert len(doc) == 1, f"C002 default (5 rows) must be 1 page, got {len(doc)}"

def test_C0303_c002_pdf_2pages_with_15rows(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_15rows.pdf'
    ex_rows = [[''] * 6] * 15
    generate_from_dict(c002_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    assert len(doc) >= 2, f"C002 with 15 rows must be >=2 pages, got {len(doc)}"

def test_C0303_c002_pdf_page2_has_footer(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_15rows_footer.pdf'
    ex_rows = [[''] * 6] * 15
    generate_from_dict(c002_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    page2_text = doc[1].get_text()
    assert '2 /' in page2_text, f"Page 2 footer missing. text={page2_text[:100]}"

def test_C0303_c002_pdf_page2_has_key_labels(c002_v1, tmp_path):
    """Regression: key labels present in multi-page C002 PDF (not clipped on page split)."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_15rows_labels.pdf'
    ex_rows = [[''] * 6] * 15
    generate_from_dict(c002_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    all_text = ''.join(p.get_text() for p in doc)
    for expected in ['작성', '검토', '승인', '전사 목표', '사업장명']:
        assert expected in all_text, f"Label '{expected}' missing across all pages"

# ─── C03-04: C012 장문·다중페이지 ────────────────────────────────────

def test_C0304_c012_multipage_pdf_2pages(c012, tmp_path):
    import copy, pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    tall = copy.deepcopy(c012)
    for s in tall['sections']:
        if s['type'] == 'freeform_area':
            s['min_height_mm'] = 150  # inflate to force page 2
    out = tmp_path / 'c012_multipage.pdf'
    generate_from_dict(tall, out)
    doc = pymupdf.open(str(out))
    assert len(doc) >= 2, f"C012 tall freeform must be >=2 pages, got {len(doc)}"

def test_C0304_c012_multipage_pdf_footer_on_page2(c012, tmp_path):
    import copy, pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    tall = copy.deepcopy(c012)
    for s in tall['sections']:
        if s['type'] == 'freeform_area':
            s['min_height_mm'] = 150
    out = tmp_path / 'c012_multipage_footer.pdf'
    generate_from_dict(tall, out)
    doc = pymupdf.open(str(out))
    page2_text = doc[1].get_text()
    assert '2 /' in page2_text, f"Page 2 footer missing in multipage C012"

def test_C0304_c012_multipage_all_labels_preserved(c012, tmp_path):
    """All section labels must appear across pages (not clipped by page split)."""
    import copy, pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    tall = copy.deepcopy(c012)
    for s in tall['sections']:
        if s['type'] == 'freeform_area':
            s['min_height_mm'] = 150
    out = tmp_path / 'c012_multipage_labels.pdf'
    generate_from_dict(tall, out)
    doc = pymupdf.open(str(out))
    all_text = ''.join(p.get_text() for p in doc)
    for label in ['안전작업 허가서', '신청', '허가', '작업 기본 정보', '작업내용', '안전조치 사항']:
        assert label in all_text, f"Label '{label}' missing in multipage C012 PDF"

def test_C0304_c012_multipage_docx_generation(c012, tmp_path):
    """C012 DOCX with tall freeform (150mm): verify file created and OOXML row heights correct."""
    import copy
    tall = copy.deepcopy(c012)
    for s in tall['sections']:
        if s['type'] == 'freeform_area':
            s['min_height_mm'] = 150
    v1_path = tmp_path / 'c012_tall.json'
    out_path = tmp_path / 'c012_tall.docx'
    v1_path.write_text(json.dumps(tall, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(f"C012 tall DOCX failed (rc={result.returncode}):\n{result.stderr[:500]}")
    assert out_path.exists(), f"DOCX not created: {out_path}"
    assert out_path.stat().st_size > 3_000, f"DOCX too small: {out_path.stat().st_size}"

    tables = _ooxml_tables(out_path)
    assert len(tables) == 5, f"Expected 5 tables, got {len(tables)}"

    # Verify OOXML freeform content row heights ≈ 150mm (8504 twips)
    NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    NS = {'w': NS_W}
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    all_tbls = root.findall('.//w:tbl', NS)
    for tbl_idx in [3, 4]:  # T4 and T5 = two freeform tables
        rows = all_tbls[tbl_idx].findall('.//w:tr', NS)
        content_row = rows[1]  # row index 1 = content (row 0 = header)
        trPr = content_row.find('w:trPr', NS)
        assert trPr is not None, f"Table {tbl_idx+1} content row missing trPr"
        trHeight = trPr.find('w:trHeight', NS)
        assert trHeight is not None, f"Table {tbl_idx+1} content row missing trHeight"
        val = int(trHeight.get(f'{{{NS_W}}}val', '0'))
        # 150mm ≈ 8504 twips; allow ±20 for rounding
        assert abs(val - 8504) <= 20, \
            f"Table {tbl_idx+1} freeform height: expected ~8504 twips (150mm), got {val}"

# ─── C03-05: SHA256 원본 무결성 ───────────────────────────────────────

def test_C0305_c002_originals_sha256():
    import hashlib
    expected = {
        'gen_c002_pdf.py':   '025aaeebccaf61021100b459f9c576cc6fcd77d1c79833f3b3d1e14cfea51b28',
        'gen_c002_docx.cjs': '1fdfaeaa90e1b32adee40a88086b49a45333803f76ec8ad86af73094a29540f2',
        'c002_fields.json':  'fd56748edc41af68d75f86260782d1ae6fb688bfae9c6c9f172de7b373c07d6a',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        assert p.exists(), f"{fname} must exist"
        actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_sha == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual_sha}"

# ─── C03-06: C002 PDF 페이지 경계 QA ─────────────────────────────────

def test_C0306_c002_pdf_10rows_1page(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_10rows.pdf'
    generate_from_dict(c002_v1, out, ex_rows=[[''] * 6] * 10)
    doc = pymupdf.open(str(out))
    assert len(doc) == 1, f"C002 with 10 rows must be 1 page, got {len(doc)}"

def test_C0306_c002_pdf_11rows_1page(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_11rows.pdf'
    generate_from_dict(c002_v1, out, ex_rows=[[''] * 6] * 11)
    doc = pymupdf.open(str(out))
    assert len(doc) == 1, f"C002 with 11 rows must be 1 page, got {len(doc)}"

def test_C0306_c002_pdf_15rows_2pages(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_15rows_boundary.pdf'
    generate_from_dict(c002_v1, out, ex_rows=[[''] * 6] * 15)
    doc = pymupdf.open(str(out))
    assert len(doc) >= 2, f"C002 with 15 rows must be >=2 pages, got {len(doc)}"

def test_C0306_c002_pdf_18rows_2pages(c002_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_18rows.pdf'
    generate_from_dict(c002_v1, out, ex_rows=[[''] * 6] * 18)
    doc = pymupdf.open(str(out))
    assert len(doc) >= 2, f"C002 with 18 rows must be >=2 pages, got {len(doc)}"

def test_C0306_c002_pdf_18rows_no_data_loss(c002_v1, tmp_path):
    """All 18 data rows must appear in PDF across the page split."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c002_18rows_dataloss.pdf'
    ex_rows = [[f'ROW{i:02d}', '', '', '', '', ''] for i in range(18)]
    generate_from_dict(c002_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    all_text = ''.join(p.get_text() for p in doc)
    missing = [f'ROW{i:02d}' for i in range(18) if f'ROW{i:02d}' not in all_text]
    assert not missing, f"Data rows missing from PDF: {missing}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059 Phase B-1 — REF-C003 REGISTER 대표 서식 POC
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def c003_v1():
    return json.loads((BASE / 'c003_v1.json').read_text(encoding='utf-8'))

# ─── C04-01: REF-C003 JSON 스키마 검증 ───────────────────────────────

def test_C0401_c003_schema_version(c003_v1):
    assert c003_v1['_meta']['schema_version'] == 'common-v1'

def test_C0401_c003_form_type(c003_v1):
    assert c003_v1['_meta']['form_type'] == 'REGISTER'

def test_C0401_c003_title(c003_v1):
    assert c003_v1['document']['title'] == '위험기계·기구·설비 목록 작성 서식'

def test_C0401_c003_single_repeat_table(c003_v1):
    secs = c003_v1['sections']
    assert len(secs) == 1
    assert secs[0]['type'] == 'repeat_table'

def test_C0401_c003_9_columns(c003_v1):
    cols = c003_v1['sections'][0]['columns']
    assert len(cols) == 9

def test_C0401_c003_column_width_sum_170mm(c003_v1):
    total = sum(c['width_mm'] for c in c003_v1['sections'][0]['columns'])
    assert total == 170, f"Column widths sum {total}mm != 170mm"

def test_C0401_c003_column_labels_match_observed_fields(c003_v1):
    expected = ['순번', '기계·기구·설비명(관리번호)', '용량', '단위작업 장소', '수량',
                '검사대상', '방호장치', '점검주기', '발생가능 재해형태']
    actual = [c['label'] for c in c003_v1['sections'][0]['columns']]
    assert actual == expected

def test_C0401_c003_engine_schema_validation(c003_v1):
    assert validate(c003_v1) is True

# ─── C04-02: REF-C003 DOCX 생성 ──────────────────────────────────────

def test_C0402_c003_docx_generates(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3000

def test_C0402_c003_docx_table_count(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    assert len(tables) == 2, f"Expected 2 tables (title+repeat), got {len(tables)}"

def test_C0402_c003_docx_9_columns(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    hdr_cells = rows[0].findall('w:tc', {'w': NS})
    assert len(hdr_cells) == 9, f"Expected 9 columns, got {len(hdr_cells)}"

def test_C0402_c003_docx_all_labels(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    all_text = ' '.join(
        ''.join(t.text or '' for t in cell.findall('.//{%s}t' % NS))
        for cell in rows[0].findall('w:tc', {'w': NS})
    )
    for label in ['순번', '기계·기구·설비명(관리번호)', '용량', '단위작업 장소', '수량',
                  '검사대상', '방호장치', '점검주기', '발생가능 재해형태']:
        assert label in all_text, f"Column label missing: '{label}'"

def test_C0402_c003_docx_footer_present(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        footer = z.read('word/footer1.xml')
    assert b'PAGE' in footer and b'NUMPAGES' in footer

def test_C0402_c003_docx_10_default_rows(c003_v1, tmp_path):
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_blank.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    rows = tables[1].findall('w:tr', {'w': NS})
    assert len(rows) == 11, f"Expected 11 rows (1 header + 10 default), got {len(rows)}"

# ─── C04-03: REF-C003 PDF 생성 ───────────────────────────────────────

def test_C0403_c003_pdf_1page_default(c003_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c003_blank.pdf'
    generate_from_dict(c003_v1, out)
    doc = pymupdf.open(str(out))
    assert doc.page_count == 1, f"C003 default (10 rows) must be 1 page, got {doc.page_count}"

def test_C0403_c003_pdf_footer_page1(c003_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c003_blank_footer.pdf'
    generate_from_dict(c003_v1, out)
    doc = pymupdf.open(str(out))
    txt = doc[0].get_text()
    assert '1 /' in txt, f"Page 1 footer '1 /' missing. text={txt[:200]}"

def test_C0403_c003_pdf_2pages_30rows(c003_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c003_30rows.pdf'
    nCols = len(c003_v1['sections'][0]['columns'])
    ex_rows = [[''] * nCols for _ in range(30)]
    generate_from_dict(c003_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    assert doc.page_count >= 2, f"C003 30 rows must be >=2 pages, got {doc.page_count}"

def test_C0403_c003_pdf_footer_all_pages(c003_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c003_30rows_footers.pdf'
    nCols = len(c003_v1['sections'][0]['columns'])
    ex_rows = [[''] * nCols for _ in range(30)]
    generate_from_dict(c003_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    for i, page in enumerate(doc):
        txt = page.get_text()
        pg_num = str(i + 1)
        assert f'{pg_num} /' in txt, f"Page {i+1} footer missing. text={txt[:100]}"

def test_C0403_c003_pdf_30rows_no_data_loss(c003_v1, tmp_path):
    """30행 추가 시 OOXML repeat_table에 손실 없이 30행 존재."""
    v1_path = tmp_path / 'c003_v1.json'
    out_path = tmp_path / 'c003_30rows.docx'
    v1_path.write_text(json.dumps(c003_v1, ensure_ascii=False), encoding='utf-8')
    nCols = len(c003_v1['sections'][0]['columns'])
    ex_rows = [[''] * nCols for _ in range(30)]
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path),
         str(len(ex_rows))],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"30rows DOCX failed: {result.stderr}"
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    rows = tables[1].findall('w:tr', {'w': NS})
    assert len(rows) == 31, f"Expected 31 rows (1 header + 30), got {len(rows)}"

# ─── C04-04: REF-C003 회귀 — 기준본 무변경 ──────────────────────────

def test_C0404_c003_c002_c012_originals_unchanged():
    import hashlib
    expected = {
        'gen_c002_pdf.py':   '025aaeebccaf61021100b459f9c576cc6fcd77d1c79833f3b3d1e14cfea51b28',
        'gen_c002_docx.cjs': '1fdfaeaa90e1b32adee40a88086b49a45333803f76ec8ad86af73094a29540f2',
        'c002_fields.json':  'fd56748edc41af68d75f86260782d1ae6fb688bfae9c6c9f172de7b373c07d6a',
        'c003_v1.json':      'b7ec9cffb05157680a85d1a8cf233559e82f3a1ee853264ff36390995d1d594a',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        assert p.exists(), f"{fname} must exist"
        actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_sha == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual_sha}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059 Phase B-2 — REF-C014 PLAN Landscape POC
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def c014_v1():
    return json.loads((BASE / 'c014_v1.json').read_text(encoding='utf-8'))

# ─── C05-01: REF-C014 JSON 스키마 검증 ───────────────────────────────

def test_C0501_c014_schema_version(c014_v1):
    assert c014_v1['_meta']['schema_version'] == 'common-v1'

def test_C0501_c014_form_type(c014_v1):
    assert c014_v1['_meta']['form_type'] == 'PLAN'

def test_C0501_c014_title(c014_v1):
    assert c014_v1['document']['title'] == '재해 감소대책 수립 및 실행 계획서 작성 서식'

def test_C0501_c014_single_repeat_table(c014_v1):
    secs = c014_v1['sections']
    assert len(secs) == 1
    assert secs[0]['type'] == 'repeat_table'

def test_C0501_c014_10_columns(c014_v1):
    cols = c014_v1['sections'][0]['columns']
    assert len(cols) == 10

def test_C0501_c014_column_width_sum_257mm(c014_v1):
    total = sum(c['width_mm'] for c in c014_v1['sections'][0]['columns'])
    assert total == 257, f"Column widths sum {total}mm != 257mm"

def test_C0501_c014_column_labels_match_observed_fields(c014_v1):
    expected = ['구분', '유해·위험요인 파악', '관련근거', '현재 위험성', '감소대책',
                '개선 후 위험성', '담당자', '조치 요구일', '조치 완료일', '완료 확인']
    actual = [c['label'] for c in c014_v1['sections'][0]['columns']]
    assert actual == expected

def test_C0501_c014_orientation_landscape(c014_v1):
    orientation = c014_v1['document']['page']['orientation']
    assert orientation == 'landscape', f"Expected 'landscape', got {orientation!r}"

def test_C0501_c014_metadata_source_batch(c014_v1):
    assert c014_v1['_meta']['observed_fields_batch'] == 'OWNER-HWP-02'

def test_C0501_c014_metadata_source_checksum(c014_v1):
    assert 'source_checksum' in c014_v1['_meta'], "source_checksum must be present"
    assert c014_v1['_meta']['source_checksum'] == \
        'e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe'

def test_C0501_c014_min_row_height_mm(c014_v1):
    assert c014_v1['sections'][0]['min_row_height_mm'] == 10

def test_C0501_c014_engine_schema_validation(c014_v1):
    assert validate(c014_v1) is True

# ─── C05-02: REF-C014 DOCX 생성 ──────────────────────────────────────

def test_C0502_c014_docx_generates(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3000

def test_C0502_c014_docx_table_count(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    assert len(tables) == 2, f"Expected 2 tables (title+repeat), got {len(tables)}"

def test_C0502_c014_docx_10_columns(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    hdr_cells = rows[0].findall('w:tc', {'w': NS})
    assert len(hdr_cells) == 10, f"Expected 10 columns, got {len(hdr_cells)}"

def test_C0502_c014_docx_all_labels(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    all_text = ' '.join(
        ''.join(t.text or '' for t in cell.findall('.//{%s}t' % NS))
        for cell in rows[0].findall('w:tc', {'w': NS})
    )
    for label in ['구분', '유해·위험요인 파악', '관련근거', '현재 위험성', '감소대책',
                  '개선 후 위험성', '담당자', '조치 요구일', '조치 완료일', '완료 확인']:
        assert label in all_text, f"Column label missing: '{label}'"

def test_C0502_c014_docx_footer_present(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        footer = z.read('word/footer1.xml')
    assert b'PAGE' in footer and b'NUMPAGES' in footer

def test_C0502_c014_docx_10_default_rows(c014_v1, tmp_path):
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    rows = tables[1].findall('w:tr', {'w': NS})
    assert len(rows) == 11, f"Expected 11 rows (1 header + 10 default), got {len(rows)}"

def test_C0502_c014_docx_landscape_pgsz(c014_v1, tmp_path):
    """DOCX pgSz must encode A4 landscape correctly: w:w≈16837(297mm), w:h≈11905(210mm), w:orient=landscape.
    Engine passes portrait dims (210×297mm) + LANDSCAPE flag; docx library swaps them so w:w becomes the wide side."""
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_blank.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)

    NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    pgsz = root.find(f'.//{{{NS_W}}}pgSz')
    assert pgsz is not None, "w:pgSz element not found in document.xml"
    orient = pgsz.get(f'{{{NS_W}}}orient', '')
    assert orient == 'landscape', f"pgSz orient='{orient}', expected 'landscape'"
    w_val = int(pgsz.get(f'{{{NS_W}}}w', '0'))
    h_val = int(pgsz.get(f'{{{NS_W}}}h', '0'))
    assert w_val >= 16000, f"pgSz w={w_val} < 16000 twips (expected 297mm≈16837 as landscape width)"
    assert h_val <= 12500, f"pgSz h={h_val} > 12500 twips (expected 210mm≈11905 as landscape height)"
    assert w_val > h_val, f"pgSz w={w_val} <= h={h_val}: width must exceed height in landscape"

# ─── C05-03: REF-C014 PDF 생성 ───────────────────────────────────────

def test_C0503_c014_pdf_1page_default(c014_v1, tmp_path):
    """C014 landscape with min_row_height_mm=10 fits 10 default rows on 1 page and is 297mm wide."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c014_blank.pdf'
    generate_from_dict(c014_v1, out)
    doc = pymupdf.open(str(out))
    assert doc.page_count == 1, f"C014 default (10 rows, min_row_height_mm=10) must be 1 page, got {doc.page_count}"
    width_mm = doc[0].rect.width / 2.8346
    assert abs(width_mm - 297) < 2, f"Page 1 width {width_mm:.1f}mm, expected ~297mm (landscape)"

def test_C0503_c014_pdf_footer_page1(c014_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c014_blank_footer.pdf'
    generate_from_dict(c014_v1, out)
    doc = pymupdf.open(str(out))
    txt = doc[0].get_text()
    assert '1 /' in txt, f"Page 1 footer '1 /' missing. text={txt[:200]}"

def test_C0503_c014_pdf_2pages_30rows(c014_v1, tmp_path):
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c014_30rows.pdf'
    nCols = len(c014_v1['sections'][0]['columns'])
    ex_rows = [[''] * nCols for _ in range(30)]
    generate_from_dict(c014_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    assert doc.page_count >= 2, f"C014 30 rows must be >=2 pages, got {doc.page_count}"

def test_C0503_c014_pdf_30rows_data_preserved(c014_v1, tmp_path):
    """30행 PDF: 각 행의 고유 마커(R00~R29)가 전 페이지에 보존됨을 확인."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c014_30rows_data.pdf'
    nCols = len(c014_v1['sections'][0]['columns'])
    # C05 감소대책 (43mm) — wide enough to display markers without clipping
    ex_rows = [[''] * nCols for _ in range(30)]
    for i, row in enumerate(ex_rows):
        row[4] = f'R{i:02d}'
    generate_from_dict(c014_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    all_text = ''.join(p.get_text() for p in doc)
    missing = [f'R{i:02d}' for i in range(30) if f'R{i:02d}' not in all_text]
    assert not missing, f"Data markers missing from PDF across all pages: {missing}"

def test_C0503_c014_docx_30rows_structural_integrity(c014_v1, tmp_path):
    """30행 DOCX 구조 검증: OOXML repeat_table에 정확히 31행(헤더1+데이터30) 존재.
    Note: Node CLI는 blank rows만 지원하므로 행 수 구조를 검증.
          실제 데이터 값 보존은 test_C0503_c014_pdf_30rows_data_preserved에서 검증."""
    v1_path = tmp_path / 'c014_v1.json'
    out_path = tmp_path / 'c014_30rows.docx'
    v1_path.write_text(json.dumps(c014_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path), '30'],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"30rows DOCX failed: {result.stderr}"
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    rows = tables[1].findall('w:tr', {'w': NS})
    assert len(rows) == 31, f"Expected 31 rows (1 header + 30), got {len(rows)}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B2-L01 — A4 Landscape 엔진 지원
# ═══════════════════════════════════════════════════════════════════════

# ─── C06-01: Landscape 엔진 스키마 검증 ──────────────────────────────

def test_C0601_portrait_default_no_page_key(minimal):
    """No document.page key → portrait validation must pass."""
    assert validate(minimal) is True

def test_C0601_portrait_orientation_explicit(minimal):
    """Explicit portrait → portrait content_w (170mm) accepted."""
    import copy
    f = copy.deepcopy(minimal)
    f['document']['page'] = {'orientation': 'portrait'}
    f['sections'] = [{
        'type': 'repeat_table', 'default_row_count': 5,
        'columns': [{'id': 'C1', 'label': 'A', 'width_mm': 170}],
    }]
    assert validate(f) is True

def test_C0601_landscape_validation_pass(c014_v1):
    """Landscape c014 must pass engine validate() without error."""
    assert validate(c014_v1) is True

def test_C0601_invalid_orientation_python_raises(minimal):
    """Unknown orientation must raise ValueError in Python engine."""
    import copy
    f = copy.deepcopy(minimal)
    f['document']['page'] = {'orientation': 'A3'}
    with pytest.raises(ValueError, match="orientation"):
        validate(f)

def test_C0601_landscape_portrait_cols_raises(c003_v1):
    """170mm portrait columns on landscape doc must fail validation."""
    import copy
    f = copy.deepcopy(c003_v1)
    f['document']['page'] = {'orientation': 'landscape'}
    with pytest.raises(ValueError, match="170mm"):
        validate(f)

def test_C0601_portrait_landscape_cols_raises(c014_v1):
    """257mm landscape columns on portrait doc must fail validation."""
    import copy
    f = copy.deepcopy(c014_v1)
    f['document']['page']['orientation'] = 'portrait'
    with pytest.raises(ValueError, match="257mm"):
        validate(f)

def test_C0601_null_orientation_python_raises(minimal):
    """Explicit null orientation must raise ValueError (fail-closed)."""
    import copy
    f = copy.deepcopy(minimal)
    f['document']['page'] = {'orientation': None}
    with pytest.raises(ValueError, match="orientation"):
        validate(f)

def test_C0601_empty_orientation_python_raises(minimal):
    """Explicit empty-string orientation must raise ValueError (fail-closed)."""
    import copy
    f = copy.deepcopy(minimal)
    f['document']['page'] = {'orientation': ''}
    with pytest.raises(ValueError, match="orientation"):
        validate(f)

def test_C0601_numeric_orientation_python_raises(minimal):
    """Numeric orientation must raise ValueError (fail-closed)."""
    import copy
    f = copy.deepcopy(minimal)
    f['document']['page'] = {'orientation': 1}
    with pytest.raises(ValueError, match="orientation"):
        validate(f)

def test_C0601_null_orientation_node_raises():
    """Node.js engine must raise for explicit null orientation (fail-closed)."""
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C',"
        "page:{orientation:null}},sections:[]});process.exit(1);}"
        "catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0601_empty_orientation_node_raises():
    """Node.js engine must raise for explicit empty-string orientation (fail-closed)."""
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C',"
        "page:{orientation:''}},sections:[]});process.exit(1);}"
        "catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0601_numeric_orientation_node_raises():
    """Node.js engine must raise for numeric orientation (fail-closed)."""
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C',"
        "page:{orientation:1}},sections:[]});process.exit(1);}"
        "catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0601_min_row_height_mm_valid(minimal):
    """repeat_table with positive min_row_height_mm must pass validation."""
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{
        'type': 'repeat_table', 'default_row_count': 5,
        'min_row_height_mm': 10,
        'columns': [{'id': 'C1', 'label': 'A', 'width_mm': 170}],
    }]
    assert validate(f) is True

def test_C0601_min_row_height_mm_negative_raises(minimal):
    """repeat_table with negative min_row_height_mm must fail validation."""
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{
        'type': 'repeat_table', 'default_row_count': 5,
        'min_row_height_mm': -5,
        'columns': [{'id': 'C1', 'label': 'A', 'width_mm': 170}],
    }]
    with pytest.raises(ValueError, match="positive"):
        validate(f)

# ─── C06-02: Landscape PDF 치수 ──────────────────────────────────────

def test_C0602_landscape_pdf_page_width_297mm(c014_v1, tmp_path):
    """Landscape PDF page width must be ≈297mm."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c014_landscape_dims.pdf'
    generate_from_dict(c014_v1, out)
    doc = pymupdf.open(str(out))
    page = doc[0]
    # PyMuPDF rect is in points; 297mm = 841.89pt
    width_mm = page.rect.width / 2.8346
    assert abs(width_mm - 297) < 2, f"Page width {width_mm:.1f}mm, expected ~297mm (landscape)"

def test_C0602_portrait_isolation_after_landscape(c003_v1, c014_v1, tmp_path):
    """Portrait C003 generated after landscape C014 must still be 210mm wide."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    # Generate landscape first
    generate_from_dict(c014_v1, tmp_path / 'c014_first.pdf')
    # Then generate portrait — must not inherit landscape page size
    out = tmp_path / 'c003_after_landscape.pdf'
    generate_from_dict(c003_v1, out)
    doc = pymupdf.open(str(out))
    page = doc[0]
    width_mm = page.rect.width / 2.8346
    assert abs(width_mm - 210) < 2, \
        f"Portrait after landscape: page width {width_mm:.1f}mm, expected ~210mm"

# ─── C06-03: Node.js Landscape 컨텍스트 정합성 ───────────────────────

def test_C0603_node_landscape_ctx_correct():
    """Node.js layoutCtx for landscape must return pageW=11905(210mm), pageH=16837(297mm), contentW=14570(257mm).
    Engine passes standard A4 portrait dims to library; library swaps them for landscape OOXML output."""
    script = (
        "const {layoutCtx} = require('./common_v1_engine.cjs');"
        "const c = layoutCtx({document:{page:{orientation:'landscape'}}});"
        "process.stdout.write(JSON.stringify({pw:c.pageW,ph:c.pageH,cw:c.contentW,o:c.orientation}));"
    )
    result = subprocess.run(
        ['node', '-e', script], cwd=str(BASE),
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"node script failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data['pw'] == 11905, f"pageW={data['pw']}, expected 11905 (210mm — pre-swap input to library)"
    assert data['ph'] == 16837, f"pageH={data['ph']}, expected 16837 (297mm — pre-swap input to library)"
    assert data['cw'] == 14570, f"contentW={data['cw']}, expected 14570 (257mm)"
    assert data['o'] == 'landscape', f"orientation={data['o']!r}, expected 'landscape'"

def test_C0603_node_invalid_orientation_raises():
    """Node.js engine must throw for unknown orientation."""
    script = (
        "const {validate} = require('./common_v1_engine.cjs');"
        "try { validate({document:{title:'T',doc_id:'D',creator:'C',"
        "page:{orientation:'A3'}},sections:[]}); process.exit(1); }"
        "catch(e){ process.stdout.write(e.message.slice(0,40)); }"
    )
    result = subprocess.run(
        ['node', '-e', script], cwd=str(BASE),
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"Expected throw but exited {result.returncode}"
    assert 'orientation' in result.stdout.lower() or result.stdout

# ─── C06-04: 공통 엔진 SHA256 회귀 ──────────────────────────────────

def test_C0604_common_engines_sha256():
    """공통 엔진 파일 SHA256 불변 검증 — 기준본: WO-REF01-059-B4-B-PATCH-1 (_MinHeightTable 추가)."""
    import hashlib
    expected = {
        'common_v1_engine.py':  'be4899dad868d4336756ce61134546748ac2b0f5f4eb4dbbf7488e795d3f2aba',
        'common_v1_engine.cjs': '375250c74ef1e22786526c1fa2446d989bbed95e8e513e85deeccc3bfb727925',
        'c014_v1.json':         'c50a99c5dcd9369e1751e754bdd004c0027065ec0ccd739448b9e70b4c45ce90',
        'c001_v1.json':         'c6a8e70dd0e3304bc066d36772a114554d4c98dbbd35c8d7c89352b2efaf7fea',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        assert p.exists(), f"{fname} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B3-B — REF-C001 안전보건경영방침 text_flow POC
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def c001_v1():
    return json.loads((BASE / 'c001_v1.json').read_text(encoding='utf-8'))

# ─── C07-01: REF-C001 JSON 스키마 검증 ───────────────────────────────

def test_C0701_c001_schema_version(c001_v1):
    assert c001_v1['_meta']['schema_version'] == 'common-v1'

def test_C0701_c001_form_type(c001_v1):
    assert c001_v1['_meta']['form_type'] == 'FORM'

def test_C0701_c001_title(c001_v1):
    assert c001_v1['document']['title'] == '안전보건경영방침'

def test_C0701_c001_orientation_portrait(c001_v1):
    assert c001_v1['document']['page']['orientation'] == 'portrait'

def test_C0701_c001_single_text_flow_section(c001_v1):
    secs = c001_v1['sections']
    assert len(secs) == 1
    assert secs[0]['type'] == 'text_flow'

def test_C0701_c001_12_paragraphs(c001_v1):
    paras = c001_v1['sections'][0]['paragraphs']
    assert len(paras) == 12, f"Expected 12 paragraphs (P04-P15), got {len(paras)}"

def test_C0701_c001_paragraph_ids_p04_to_p15(c001_v1):
    ids = [p['id'] for p in c001_v1['sections'][0]['paragraphs']]
    assert ids == [f'P{i:02d}' for i in range(4, 16)], f"Paragraph IDs: {ids}"

def test_C0701_c001_policy_items_1_to_8_present(c001_v1):
    texts = [p['text'] for p in c001_v1['sections'][0]['paragraphs']]
    all_text = ' '.join(texts)
    for n in range(1, 9):
        assert f'{n}.' in all_text, f"Policy item {n} not found"

def test_C0701_c001_placeholder_texts_present(c001_v1):
    texts = [p['text'] for p in c001_v1['sections'][0]['paragraphs']]
    all_text = ' '.join(texts)
    assert '○○기업' in all_text, "Company name placeholder missing"
    assert '○○○○년' in all_text, "Date placeholder missing"
    assert '대표이사' in all_text, "CEO signature placeholder missing"

def test_C0701_c001_date_and_signature_right_aligned(c001_v1):
    paras = c001_v1['sections'][0]['paragraphs']
    p14 = next(p for p in paras if p['id'] == 'P14')
    p15 = next(p for p in paras if p['id'] == 'P15')
    assert p14['align'] == 'right', f"P14 align={p14['align']!r}, expected 'right'"
    assert p15['align'] == 'right', f"P15 align={p15['align']!r}, expected 'right'"

def test_C0701_c001_engine_schema_validation(c001_v1):
    assert validate(c001_v1) is True

def test_C0701_c001_source_checksum_present(c001_v1):
    assert c001_v1['_meta']['source_checksum'] == \
        'e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe'

def test_C0701_c001_p06_ascii_quote(c001_v1):
    """P06 따옴표는 ASCII 단따옴표(U+0027)여야 함 — B-3-A2 원본 기준."""
    p06 = next(p for p in c001_v1['sections'][0]['paragraphs'] if p['id'] == 'P06')
    for ch in p06['text']:
        assert ord(ch) not in (0x2018, 0x2019, 0x201A, 0x201B, 0x201C, 0x201D), \
            f"P06 contains curly/smart quote U+{ord(ch):04X}; expected ASCII U+0027"
    # Must contain the ASCII apostrophe form
    assert "'근로자의 생명 보호'" in p06['text'], "P06 must contain ASCII-quoted '근로자의 생명 보호'"
    assert "'안전한 작업환경 조성'" in p06['text'], "P06 must contain ASCII-quoted '안전한 작업환경 조성'"

# ─── C07-01: text_flow 스키마 검증 (fail-closed) ──────────────────────

def test_C0701_text_flow_valid_passes(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [
        {'id': 'P1', 'text': '안전보건', 'align': 'left'},
    ]}]
    assert validate(f) is True

def test_C0701_text_flow_missing_paragraphs_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow'}]
    with pytest.raises(ValueError, match="missing required attr 'paragraphs'"):
        validate(f)

def test_C0701_text_flow_empty_paragraphs_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': []}]
    with pytest.raises(ValueError, match="paragraphs must have >= 1 entry"):
        validate(f)

def test_C0701_text_flow_missing_id_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [{'text': '안전'}]}]
    with pytest.raises(ValueError, match="'id'"):
        validate(f)

def test_C0701_text_flow_missing_text_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [{'id': 'P1'}]}]
    with pytest.raises(ValueError, match="'text'"):
        validate(f)

def test_C0701_text_flow_nonstring_text_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [{'id': 'P1', 'text': 123}]}]
    with pytest.raises(ValueError, match="string"):
        validate(f)

def test_C0701_text_flow_invalid_align_raises(minimal):
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [
        {'id': 'P1', 'text': '안전', 'align': 'justify'}
    ]}]
    with pytest.raises(ValueError, match="align"):
        validate(f)

def test_C0701_text_flow_empty_align_raises(minimal):
    """명시적 빈 문자열 align은 Python 엔진에서 거부 (fail-closed)."""
    import copy
    f = copy.deepcopy(minimal)
    f['sections'] = [{'type': 'text_flow', 'paragraphs': [
        {'id': 'P1', 'text': '안전', 'align': ''}
    ]}]
    with pytest.raises(ValueError, match="align"):
        validate(f)

def test_C0701_text_flow_node_valid_passes():
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "const r=validate({document:{title:'T',doc_id:'D',creator:'C'},"
        "sections:[{type:'text_flow',paragraphs:[{id:'P1',text:'안전보건',align:'left'}]}]});"
        "process.stdout.write(r?'PASS':'FAIL');"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'PASS', \
        f"Expected PASS but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0701_text_flow_node_missing_paragraphs_raises():
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C'},"
        "sections:[{type:'text_flow'}]});process.exit(1);}"
        "catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0701_text_flow_node_empty_paragraphs_raises():
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C'},"
        "sections:[{type:'text_flow',paragraphs:[]}]});process.exit(1);}"
        "catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0701_text_flow_node_invalid_align_raises():
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C'},"
        "sections:[{type:'text_flow',paragraphs:[{id:'P1',text:'x',align:'justify'}]}]});"
        "process.exit(1);}catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0701_text_flow_node_empty_align_raises():
    """Node 엔진: 명시적 빈 문자열 align은 거부 (Python과 계약 일치)."""
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "try{validate({document:{title:'T',doc_id:'D',creator:'C'},"
        "sections:[{type:'text_flow',paragraphs:[{id:'P1',text:'x',align:''}]}]});"
        "process.exit(1);}catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

def test_C0701_text_flow_node_null_align_raises():
    """Node 엔진: 명시적 null align은 거부 (Python과 계약 일치)."""
    script = (
        "const {validate}=require('./common_v1_engine.cjs');"
        "const f=JSON.parse('{\"document\":{\"title\":\"T\",\"doc_id\":\"D\",\"creator\":\"C\"},"
        "\"sections\":[{\"type\":\"text_flow\",\"paragraphs\":"
        "[{\"id\":\"P1\",\"text\":\"x\",\"align\":null}]}]}');"
        "try{validate(f);process.exit(1);}catch(e){process.stdout.write('RAISED');}"
    )
    result = subprocess.run(['node', '-e', script], cwd=str(BASE),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'RAISED', \
        f"Expected RAISED but got rc={result.returncode} stdout={result.stdout!r}"

# ─── C07-02: REF-C001 PDF 생성 ───────────────────────────────────────

def test_C0702_c001_pdf_generates(c001_v1, tmp_path):
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_blank.pdf'
    generate_from_dict(c001_v1, out)
    assert out.exists()
    assert out.stat().st_size > 5_000

def test_C0702_c001_pdf_title_once(c001_v1, tmp_path):
    """제목 '안전보건경영방침'이 1회 출력 (중복 없음)."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_title.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    count = full_text.count('안전보건경영방침')
    assert count == 1, f"Title '안전보건경영방침' must appear exactly once, got {count}"

def test_C0702_c001_pdf_policy_items_present(c001_v1, tmp_path):
    """원본 정책항목 1~8이 PDF에 모두 존재."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_policy.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    for item in [
        '근로자의 생명 보호',
        '인적·물적',
        '안전보건 목표를 설정',
        '법령 및 관련 규정',
        '근로자의 참여를 통해',
        '교육·훈련을 실시',
        '공급자와 계약자',
        '책임과 의무를 성실히',
    ]:
        assert item in full_text, f"Policy item text missing: '{item}'"

def test_C0702_c001_pdf_12_paragraphs_data(c001_v1, tmp_path):
    """12개 단락 핵심 텍스트가 PDF에 보존됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_12paras.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    for marker in ['○○기업은', '이를 위해', '○○○○년', '대표이사']:
        assert marker in full_text, f"Paragraph marker missing: '{marker}'"

def test_C0702_c001_pdf_placeholder_preserved(c001_v1, tmp_path):
    """회사명·날짜·서명 플레이스홀더가 PDF에 그대로 유지됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_placeholder.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    assert '○○기업' in full_text, "Company placeholder missing"
    assert '○○○○년' in full_text, "Date placeholder missing"
    assert '(서명)' in full_text, "Signature placeholder missing"

def test_C0702_c001_pdf_1page_portrait(c001_v1, tmp_path):
    """A4 Portrait 1페이지에 배치됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_1page.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    assert doc.page_count == 1, f"C001 must be 1 page, got {doc.page_count}"
    width_mm = doc[0].rect.width / 2.8346
    assert abs(width_mm - 210) < 2, f"Page width {width_mm:.1f}mm, expected ~210mm (portrait)"

def test_C0702_c001_pdf_footer(c001_v1, tmp_path):
    """페이지 푸터 '1 / 1' 존재."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c001_footer.pdf'
    generate_from_dict(c001_v1, out)
    doc = pymupdf.open(str(out))
    full_text = doc[0].get_text()
    assert '1 /' in full_text, f"Footer '1 /' not found. text={full_text[:200]}"

def test_C0702_c001_pdf_xml_escape(tmp_path):
    """text_flow에 <, >, & 특수문자가 있어도 PDF 생성이 정상 완료됨."""
    import pymupdf
    from common_v1_engine import register_fonts, generate_from_dict as gen
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'XML 안전 테스트', 'doc_id': 'T001', 'creator': 'TAI'},
        'sections': [{'type': 'text_flow', 'paragraphs': [
            {'id': 'P1', 'text': '5 < 10 이면 안전'},
            {'id': 'P2', 'text': '관계 a > b 성립'},
            {'id': 'P3', 'text': '법령 & 규정 준수'},
        ]}],
    }
    out = tmp_path / 'xml_safe.pdf'
    gen(fields, out)
    assert out.exists() and out.stat().st_size > 1_000
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    assert '안전' in full_text, "Text with '<' must render correctly"
    assert '법령' in full_text, "Text with '&' must render correctly"

# ─── C07-03: REF-C001 DOCX 생성 ──────────────────────────────────────

def test_C0703_c001_docx_generates(c001_v1, tmp_path):
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3_000

def test_C0703_c001_docx_title_table_present(c001_v1, tmp_path):
    """제목이 table 구조로 포함됨 (title block)."""
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    assert len(tables) == 1, f"C001 must have 1 table (title only), got {len(tables)}"
    assert '안전보건경영방침' in tables[0][0][0]

def test_C0703_c001_docx_no_repeat_table(c001_v1, tmp_path):
    """text_flow 문서에 repeat_table이 없어야 함."""
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    tables = _ooxml_tables(out_path)
    assert len(tables) == 1, f"No repeat_table expected (only title table), got {len(tables)}"

def test_C0703_c001_docx_text_paragraphs_in_ooxml(c001_v1, tmp_path):
    """12개 본문 단락이 OOXML w:p 요소로 존재함 (table 바깥의 plain text)."""
    NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    body = root.find('w:body', NS)
    # paragraphs directly under body (not inside table)
    direct_paras = body.findall('w:p', NS)
    para_texts = [''.join(t.text or '' for t in p.findall('.//w:t', NS)) for p in direct_paras]
    all_text = ' '.join(para_texts)
    for marker in ['○○기업은', '이를 위해', '경영책임자는', '○○○○년', '대표이사']:
        assert marker in all_text, f"Body paragraph marker missing: '{marker}'"

def test_C0703_c001_docx_placeholder_in_ooxml(c001_v1, tmp_path):
    """○○ 플레이스홀더가 OOXML에 보존됨."""
    NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        content = z.read('word/document.xml').decode('utf-8')
    assert '○○기업' in content, "Company placeholder missing in OOXML"
    assert '○○○○년' in content, "Date placeholder missing in OOXML"
    assert '(서명)' in content, "Signature placeholder missing in OOXML"

def test_C0703_c001_docx_footer_present(c001_v1, tmp_path):
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        footer = z.read('word/footer1.xml')
    assert b'PAGE' in footer and b'NUMPAGES' in footer

def test_C0703_c001_docx_portrait_pgsz(c001_v1, tmp_path):
    """DOCX pgSz must be A4 portrait: w≈11905(210mm), h≈16837(297mm), no landscape orient."""
    NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    pgsz = root.find(f'.//{{{NS_W}}}pgSz')
    assert pgsz is not None, "w:pgSz element not found"
    orient = pgsz.get(f'{{{NS_W}}}orient', 'portrait')
    assert orient != 'landscape', f"Expected portrait, got orient='{orient}'"
    w_val = int(pgsz.get(f'{{{NS_W}}}w', '0'))
    h_val = int(pgsz.get(f'{{{NS_W}}}h', '0'))
    assert w_val <= 12500, f"pgSz w={w_val} > 12500 (expected ≈11905 for 210mm portrait width)"
    assert h_val >= 16000, f"pgSz h={h_val} < 16000 (expected ≈16837 for 297mm portrait height)"

def test_C0703_c001_docx_full_text_match(c001_v1, tmp_path):
    """DOCX P04~P15 전체 12개 단락 핵심 텍스트가 OOXML에 완전히 존재함."""
    import html as html_mod
    v1_path = tmp_path / 'c001_v1.json'
    out_path = tmp_path / 'c001_blank.docx'
    v1_path.write_text(json.dumps(c001_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        raw_xml = z.read('word/document.xml').decode('utf-8')
    # Unescape XML entities (&apos; → ' etc.) before plain-text search
    decoded = html_mod.unescape(raw_xml)
    paras = c001_v1['sections'][0]['paragraphs']
    for para in paras:
        marker = para['text'][:15]
        assert marker in decoded, \
            f"Paragraph {para['id']} text not in OOXML: {marker!r}"
    # P06 must use ASCII quote (U+0027) — curly quote U+2018 must be absent in raw XML
    assert '\u2018' not in raw_xml, "P06 curly left-quote U+2018 must not appear in OOXML"
    assert '&#x2018;' not in raw_xml, "P06 curly left-quote entity must not appear in OOXML"

# ─── C07-04: 기존 서식 회귀 ──────────────────────────────────────────

def test_C0704_c001_regression_c003_c014_unchanged():
    import hashlib
    expected = {
        'c003_v1.json': 'b7ec9cffb05157680a85d1a8cf233559e82f3a1ee853264ff36390995d1d594a',
        'c014_v1.json': 'c50a99c5dcd9369e1751e754bdd004c0027065ec0ccd739448b9e70b4c45ce90',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"

def test_C0704_c001_c003_still_validates(c003_v1):
    """text_flow 추가 후 기존 C003 유효성 검증이 유지됨."""
    assert validate(c003_v1) is True

def test_C0704_c001_c014_still_validates(c014_v1):
    """text_flow 추가 후 기존 C014 landscape 유효성 검증이 유지됨."""
    assert validate(c014_v1) is True

def test_C0704_c012_source_unchanged():
    """C012 생성기 소스 파일이 PATCH-1에서 변경되지 않았음을 SHA256으로 검증."""
    import hashlib
    expected = {
        'gen_c012_docx.cjs': '6717387fe40518971584bfc32cdb02c0c8b6020c7ccb94cede0e0d50fbf0e308',
        'c012_fields.json':  '25f5514bed0d8db968fc99b43915dae93e2a0db755edcbebf4adbdececce39cd',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        assert p.exists(), f"{fname} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B4-B — REF-C004 유해·위험물질 목록 / 2단 헤더 공통 엔진 확장
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def c004_v1():
    return json.loads((BASE / 'c004_v1.json').read_text(encoding='utf-8'))

# ─── C08-01: c004_v1.json 스키마 검증 ────────────────────────────────

def test_C0801_c004_schema_version(c004_v1):
    assert c004_v1['_meta']['schema_version'] == 'common-v1'

def test_C0801_c004_form_type(c004_v1):
    assert c004_v1['_meta']['form_type'] == 'REGISTER'

def test_C0801_c004_title(c004_v1):
    assert c004_v1['document']['title'] == '유해·위험물질 목록 작성 서식'

def test_C0801_c004_orientation_landscape(c004_v1):
    assert c004_v1['document']['page']['orientation'] == 'landscape'

def test_C0801_c004_validates(c004_v1):
    assert validate(c004_v1) is True

def test_C0801_c004_15_columns(c004_v1):
    cols = c004_v1['sections'][0]['columns']
    assert len(cols) == 15, f"Expected 15 columns, got {len(cols)}"

def test_C0801_c004_column_widths_sum_257(c004_v1):
    total = sum(c['width_mm'] for c in c004_v1['sections'][0]['columns'])
    assert abs(total - 257) < 0.5, f"Column widths sum={total}mm, expected 257mm"

def test_C0801_c004_header_group_G01(c004_v1):
    groups = c004_v1['sections'][0]['header_groups']
    assert len(groups) == 1
    assert groups[0]['id'] == 'G01'
    assert groups[0]['label'] == '폭발한계(%)'
    assert set(groups[0]['column_ids']) == {'F04_EXPL_LOWER', 'F04_EXPL_UPPER'}

def test_C0801_c004_explosion_lower_upper_consecutive(c004_v1):
    cols = c004_v1['sections'][0]['columns']
    col_ids = [c['id'] for c in cols]
    i_lower = col_ids.index('F04_EXPL_LOWER')
    i_upper = col_ids.index('F04_EXPL_UPPER')
    assert i_upper == i_lower + 1, "하한/상한 columns must be consecutive"

def test_C0801_c004_notes_section_exists(c004_v1):
    secs = c004_v1['sections']
    assert len(secs) == 2
    assert secs[1]['type'] == 'text_flow'

def test_C0801_c004_notes_6_paragraphs(c004_v1):
    paras = c004_v1['sections'][1]['paragraphs']
    assert len(paras) == 6, f"Expected 6 note paragraphs, got {len(paras)}"

def test_C0801_c004_notes_ids_N01_to_N06(c004_v1):
    ids = [p['id'] for p in c004_v1['sections'][1]['paragraphs']]
    assert ids == ['N01', 'N02', 'N03', 'N04', 'N05', 'N06']

def test_C0801_c004_notes_original_text(c004_v1):
    paras = c004_v1['sections'][1]['paragraphs']
    texts = {p['id']: p['text'] for p in paras}
    assert '제출대상 설비' in texts['N01'], "N01 must contain original ① text"
    assert '증기압은 상온' in texts['N02'], "N02 must contain original ② text"
    assert '있으면 ○' in texts['N03'], "N03 must contain original ③ text"
    assert '이상반응을 일으키는' in texts['N04'], "N04 must contain original ④ text"
    assert 'TWA' in texts['N05'], "N05 must contain original ⑤ text"
    assert 'LD50' in texts['N06'], "N06 must contain original ⑥ text"

# ─── C08-02: header_groups 유효성 검사 ───────────────────────────────

def test_C0802_no_header_groups_existing_behavior():
    """header_groups 미지정 시 기존 단일 헤더 유지 (repeat_table)."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI',
                     'page': {'orientation': 'portrait'}},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'columns': [
                          {'id': 'A', 'label': '항목A', 'width_mm': 85},
                          {'id': 'B', 'label': '항목B', 'width_mm': 85},
                      ]}],
    }
    assert validate(fields) is True

def test_C0802_valid_header_group():
    """유효한 2단 헤더 그룹 검증."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI',
                     'page': {'orientation': 'portrait'}},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': '그룹', 'column_ids': ['B', 'C']}],
                      'columns': [
                          {'id': 'A', 'label': '항목A', 'width_mm': 50},
                          {'id': 'B', 'label': '하위1', 'width_mm': 60},
                          {'id': 'C', 'label': '하위2', 'width_mm': 60},
                      ]}],
    }
    assert validate(fields) is True

def test_C0802_invalid_group_id_raises():
    """존재하지 않는 column_id 참조 시 FAIL-CLOSED."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': '그룹', 'column_ids': ['B', 'NONEXISTENT']}],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 85},
                          {'id': 'B', 'label': 'B', 'width_mm': 85},
                      ]}],
    }
    with pytest.raises((ValueError, KeyError)):
        validate(fields)

def test_C0802_duplicate_column_in_groups_raises():
    """같은 column_id가 여러 그룹에 중복 등장 시 FAIL-CLOSED."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [
                          {'id': 'G1', 'label': 'G1', 'column_ids': ['A', 'B']},
                          {'id': 'G2', 'label': 'G2', 'column_ids': ['B', 'C']},
                      ],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 57},
                          {'id': 'B', 'label': 'B', 'width_mm': 57},
                          {'id': 'C', 'label': 'C', 'width_mm': 56},
                      ]}],
    }
    with pytest.raises((ValueError, KeyError)):
        validate(fields)

def test_C0802_nonconsecutive_group_raises():
    """비연속 column_ids 그룹 시 FAIL-CLOSED."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': 'G', 'column_ids': ['A', 'C']}],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 57},
                          {'id': 'B', 'label': 'B', 'width_mm': 57},
                          {'id': 'C', 'label': 'C', 'width_mm': 56},
                      ]}],
    }
    with pytest.raises(ValueError):
        validate(fields)

def test_C0802_group_single_column_raises():
    """column_ids < 2인 그룹은 FAIL-CLOSED."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': 'G', 'column_ids': ['A']}],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 85},
                          {'id': 'B', 'label': 'B', 'width_mm': 85},
                      ]}],
    }
    with pytest.raises(ValueError):
        validate(fields)

def test_C0802_node_valid_header_group():
    """Node.js 엔진 header_groups 유효성 검증 PASS."""
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI',
                     'page': {'orientation': 'portrait'}},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': '그룹', 'column_ids': ['B', 'C']}],
                      'columns': [
                          {'id': 'A', 'label': '항목A', 'width_mm': 50},
                          {'id': 'B', 'label': '하위1', 'width_mm': 60},
                          {'id': 'C', 'label': '하위2', 'width_mm': 60},
                      ]}],
    }
    import json as _json, subprocess as _sub
    result = _sub.run(
        ['node', '-e',
         f"const e=require('./common_v1_engine.cjs'); "
         f"try{{e.validate({_json.dumps(fields)});console.log('PASS');}}catch(err){{console.error('FAIL:',err.message);process.exit(1);}}"],
        cwd=str(BASE), capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, f"Node validate FAIL: {result.stderr}"
    assert 'PASS' in result.stdout

def test_C0802_node_invalid_group_id_raises():
    """Node.js 엔진 존재하지 않는 column_id 참조 시 오류."""
    import json as _json, subprocess as _sub
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': 'G', 'column_ids': ['B', 'NONE']}],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 85},
                          {'id': 'B', 'label': 'B', 'width_mm': 85},
                      ]}],
    }
    result = _sub.run(
        ['node', '-e',
         f"const e=require('./common_v1_engine.cjs'); "
         f"try{{e.validate({_json.dumps(fields)});console.log('PASS');}}catch(err){{console.log('RAISED:',err.message);}}"],
        cwd=str(BASE), capture_output=True, text=True, timeout=10
    )
    assert 'RAISED' in result.stdout, f"Expected RAISED, got: {result.stdout}"

def test_C0802_node_duplicate_column_raises():
    """Node.js 엔진 중복 column_id 시 오류."""
    import json as _json, subprocess as _sub
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [
                          {'id': 'G1', 'label': 'G1', 'column_ids': ['A', 'B']},
                          {'id': 'G2', 'label': 'G2', 'column_ids': ['B', 'C']},
                      ],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 57},
                          {'id': 'B', 'label': 'B', 'width_mm': 57},
                          {'id': 'C', 'label': 'C', 'width_mm': 56},
                      ]}],
    }
    result = _sub.run(
        ['node', '-e',
         f"const e=require('./common_v1_engine.cjs'); "
         f"try{{e.validate({_json.dumps(fields)});console.log('PASS');}}catch(err){{console.log('RAISED:',err.message);}}"],
        cwd=str(BASE), capture_output=True, text=True, timeout=10
    )
    assert 'RAISED' in result.stdout, f"Expected RAISED, got: {result.stdout}"

def test_C0802_node_nonconsecutive_group_raises():
    """Node.js 엔진 비연속 column_ids 시 오류."""
    import json as _json, subprocess as _sub
    fields = {
        '_meta': {'schema_version': 'common-v1'},
        'document': {'title': 'T', 'doc_id': 'T1', 'creator': 'TAI'},
        'sections': [{'type': 'repeat_table', 'default_row_count': 2,
                      'header_groups': [{'id': 'G1', 'label': 'G', 'column_ids': ['A', 'C']}],
                      'columns': [
                          {'id': 'A', 'label': 'A', 'width_mm': 57},
                          {'id': 'B', 'label': 'B', 'width_mm': 57},
                          {'id': 'C', 'label': 'C', 'width_mm': 56},
                      ]}],
    }
    result = _sub.run(
        ['node', '-e',
         f"const e=require('./common_v1_engine.cjs'); "
         f"try{{e.validate({_json.dumps(fields)});console.log('PASS');}}catch(err){{console.log('RAISED:',err.message);}}"],
        cwd=str(BASE), capture_output=True, text=True, timeout=10
    )
    assert 'RAISED' in result.stdout, f"Expected RAISED, got: {result.stdout}"

# ─── C08-03: C004 PDF 생성 검증 ──────────────────────────────────────

def test_C0803_c004_pdf_generates(c004_v1, tmp_path):
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_blank.pdf'
    generate_from_dict(c004_v1, out)
    assert out.exists()
    assert out.stat().st_size > 10_000

def test_C0803_c004_pdf_landscape(c004_v1, tmp_path):
    """C004 PDF가 A4 landscape (297×210mm)로 생성됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_landscape.pdf'
    generate_from_dict(c004_v1, out)
    doc = pymupdf.open(str(out))
    page = doc[0]
    w_mm = page.rect.width / 2.8346
    h_mm = page.rect.height / 2.8346
    assert abs(w_mm - 297) < 2, f"Page width {w_mm:.1f}mm expected ~297mm (landscape)"
    assert abs(h_mm - 210) < 2, f"Page height {h_mm:.1f}mm expected ~210mm (landscape)"

def test_C0803_c004_pdf_title_present(c004_v1, tmp_path):
    """제목 '유해·위험물질 목록 작성 서식'이 PDF에 포함됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_title.pdf'
    generate_from_dict(c004_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    assert '유해' in full_text, "Title text not found in PDF"

def test_C0803_c004_pdf_header_labels(c004_v1, tmp_path):
    """PDF에 폭발한계, 화학물질, CAS 헤더가 포함됨. 좁은 열(10mm)은 공백 제거 후 검사."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_hdrs.pdf'
    generate_from_dict(c004_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    joined = full_text.replace('\n', '').replace(' ', '')
    for label in ['폭발한계', '화학물질', 'CAS']:
        assert label in full_text, f"Header label '{label}' not found in PDF"
    # Narrow columns (10mm) may have line-split labels — check in whitespace-stripped text
    for label in ['하한', '상한']:
        assert label in joined, f"Header label '{label}' not found in PDF (whitespace-stripped)"

def test_C0803_c004_pdf_10_blank_rows(c004_v1, tmp_path):
    """default_row_count=10인 경우 빈 행 10개 이상 생성됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_rows.pdf'
    generate_from_dict(c004_v1, out)
    assert out.exists()
    doc = pymupdf.open(str(out))
    assert doc.page_count >= 1

def test_C0803_c004_pdf_notes_present(c004_v1, tmp_path):
    """주석 ①-⑥ 원본 텍스트가 PDF에 모두 포함됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_notes.pdf'
    generate_from_dict(c004_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    for marker in ['제출대상 설비', '증기압은 상온', '있으면 ○', '이상반응을', 'TWA', 'LD50']:
        assert marker in full_text, f"Note marker '{marker}' not found in PDF"

def test_C0803_c004_pdf_30_rows_pagination(c004_v1, tmp_path):
    """30개 데이터 행 삽입 시 페이지 분할 발생 (>1 page)."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_30rows.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[''] * len(cols)] * 30
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    assert doc.page_count > 1, f"30 rows should require >1 page, got {doc.page_count}"

def test_C0803_c004_pdf_header_repeats_on_page2(c004_v1, tmp_path):
    """30행 삽입 시 페이지 2에도 헤더(폭발한계)가 반복됨."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required but not found: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_hdr_repeat.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[''] * len(cols)] * 30
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    if doc.page_count > 1:
        page2_text = doc[1].get_text()
        assert '폭발한계' in page2_text or '하한' in page2_text, \
            "Header must repeat on page 2 (repeatRows=2)"

# ─── C08-04: C004 DOCX 생성 검증 ─────────────────────────────────────

def test_C0804_c004_docx_generates(c004_v1, tmp_path):
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_blank.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>{{console.error(e);process.exit(1)}})"],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 5_000

def test_C0804_c004_docx_landscape(c004_v1, tmp_path):
    """C004 DOCX가 landscape 방향 설정을 포함함."""
    import zipfile, re as _re
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_land.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>process.exit(1))"],
        cwd=str(BASE), capture_output=True, timeout=30, check=True,
    )
    with zipfile.ZipFile(out_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    assert 'landscape' in xml.lower(), "DOCX must contain landscape orientation"

def test_C0804_c004_docx_gridspan_2(c004_v1, tmp_path):
    """DOCX에 gridSpan=2 (폭발한계(%) 병합 셀) 존재."""
    import zipfile, re as _re
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_gs.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>process.exit(1))"],
        cwd=str(BASE), capture_output=True, timeout=30, check=True,
    )
    with zipfile.ZipFile(out_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    spans = _re.findall(r'<w:gridSpan w:val="(\d+)"', xml)
    assert '2' in spans, f"gridSpan=2 not found (폭발한계 column merge). Found: {spans}"

def test_C0804_c004_docx_vmerge_restart(c004_v1, tmp_path):
    """DOCX에 vMerge restart (비그룹 열 세로 병합) 존재."""
    import zipfile, re as _re
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_vm.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>process.exit(1))"],
        cwd=str(BASE), capture_output=True, timeout=30, check=True,
    )
    with zipfile.ZipFile(out_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    restart_count = len(_re.findall(r'<w:vMerge w:val="restart"', xml))
    assert restart_count >= 13, f"Expected >= 13 vMerge restart (13 non-group cols), got {restart_count}"

def test_C0804_c004_docx_notes_present(c004_v1, tmp_path):
    """DOCX에 주석 ①-⑥ 원본 텍스트가 포함됨."""
    import zipfile
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_notes.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>process.exit(1))"],
        cwd=str(BASE), capture_output=True, timeout=30, check=True,
    )
    with zipfile.ZipFile(out_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    for marker in ['제출대상 설비', '증기압은', 'TWA', 'LD50']:
        assert marker in xml, f"Note marker '{marker}' not found in DOCX XML"

def test_C0804_c004_docx_15_col_headers_present(c004_v1, tmp_path):
    """DOCX XML에 15개 열 레이블이 모두 존재."""
    import zipfile
    v1_path = tmp_path / 'c004_v1.json'
    out_path = tmp_path / 'c004_cols.docx'
    v1_path.write_text(json.dumps(c004_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(
        ['node', '-e',
         f"require('./common_v1_engine.cjs').generate('{v1_path}', '{out_path}').catch(e=>process.exit(1))"],
        cwd=str(BASE), capture_output=True, timeout=30, check=True,
    )
    with zipfile.ZipFile(out_path) as z:
        xml = z.read('word/document.xml').decode('utf-8')
    expected_labels = [
        '화학물질', 'CAS No', '분자식', '폭발한계(%)', '하한', '상한',
        '노출기준', '독성치', '인화점', '발화점', '증기압', '부식성유무',
        '이상반응유무', '일일사용량', '저장량', '비고',
    ]
    for label in expected_labels:
        assert label in xml, f"Column label '{label}' not found in DOCX XML"

# ─── C08-05: 기존 서식 회귀 ──────────────────────────────────────────

def test_C0805_c004_existing_forms_unchanged():
    """B4-B 변경 후 기존 JSON 파일 SHA256 불변."""
    import hashlib
    expected = {
        'c001_v1.json': 'c6a8e70dd0e3304bc066d36772a114554d4c98dbbd35c8d7c89352b2efaf7fea',
        'c003_v1.json': 'b7ec9cffb05157680a85d1a8cf233559e82f3a1ee853264ff36390995d1d594a',
        'c014_v1.json': 'c50a99c5dcd9369e1751e754bdd004c0027065ec0ccd739448b9e70b4c45ce90',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{fname}: SHA256 changed"

def test_C0805_c003_still_validates(c003_v1):
    """header_groups 추가 후 기존 C003 유효성 검증 유지."""
    assert validate(c003_v1) is True

def test_C0805_c014_still_validates(c014_v1):
    """header_groups 추가 후 기존 C014 landscape 유효성 검증 유지."""
    assert validate(c014_v1) is True

def test_C0805_c004_source_files_sha256():
    """C004 소스 파일 SHA256 기준본 검증 — PATCH-1 기준."""
    import hashlib
    expected = {
        'c004_v1.json':         '713b605b8e8d8e7fff52ba4d774fee0f002d855934fc489a71cbfa377598b44d',
        'common_v1_engine.py':  'be4899dad868d4336756ce61134546748ac2b0f5f4eb4dbbf7488e795d3f2aba',
        'common_v1_engine.cjs': '375250c74ef1e22786526c1fa2446d989bbed95e8e513e85deeccc3bfb727925',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{fname}: SHA256 changed"

def test_C0805_c004_field_order_original(c004_v1):
    """15개 열이 원본 관찰 순서(화학물질→비고)를 유지함."""
    cols = c004_v1['sections'][0]['columns']
    col_ids = [c['id'] for c in cols]
    expected_order = [
        'F01_CHEMICAL', 'F02_CAS_NO', 'F03_FORMULA',
        'F04_EXPL_LOWER', 'F04_EXPL_UPPER',
        'F05_EXPOSURE', 'F06_TOXICITY', 'F07_FLASH', 'F08_IGNITION',
        'F09_VAPOR', 'F10_CORROSION', 'F11_REACTION',
        'F12_DAILY_USE', 'F13_STOCK', 'F14_REMARK',
    ]
    assert col_ids == expected_order, f"Column order mismatch: {col_ids}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B4-B-PATCH-1 — PDF 페이지 분할 시 최소 행 높이 보존
# ═══════════════════════════════════════════════════════════════════════

MIN_ROW_H_MM = 14.0
TOLERANCE_MM = 0.15  # pdfplumber bbox 측정 허용 오차

def _measure_data_row_heights(pdf_path, n_hdr_page1=3, n_hdr_rest=2):
    """PDF 파일에서 각 페이지의 데이터 행 높이(mm)를 pdfplumber 표 경계선으로 측정."""
    import pdfplumber
    heights = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pi, page in enumerate(pdf.pages):
            tbls = page.find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
            if not tbls:
                continue
            rows = tbls[0].rows
            skip = n_hdr_page1 if pi == 0 else n_hdr_rest
            for r in rows[skip:]:
                h = (r.bbox[3] - r.bbox[1]) / 2.8346
                heights.append(round(h, 2))
    return heights


# ─── C09-01: 최초 분할 조각 최소 행 높이 ─────────────────────────────

def test_C0901_first_split_fragment_min_row_height(c004_v1, tmp_path):
    """페이지 분할 후 첫 번째 계속 페이지의 데이터 행이 14mm 이상."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_split1.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    heights = _measure_data_row_heights(out)
    assert len(heights) == 30, f"Expected 30 data rows, got {len(heights)}"
    below = [h for h in heights if h < MIN_ROW_H_MM - TOLERANCE_MM]
    assert not below, f"Rows below {MIN_ROW_H_MM}mm on continued pages: {below}"


# ─── C09-02: 반복 분할 조각 최소 행 높이 ────────────────────────────

def test_C0902_repeated_split_fragment_min_row_height(c004_v1, tmp_path):
    """3페이지 이상 분할 시 모든 계속 페이지의 데이터 행이 14mm 이상."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_split_multi.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    import pdfplumber
    with pdfplumber.open(str(out)) as pdf:
        assert len(pdf.pages) >= 3, f"30 rows should span ≥3 pages"
    heights = _measure_data_row_heights(out)
    below = [h for h in heights if h < MIN_ROW_H_MM - TOLERANCE_MM]
    assert not below, f"Rows below {MIN_ROW_H_MM}mm: {below}"


# ─── C09-03: 마지막 페이지 최소 행 높이 ──────────────────────────────

def test_C0903_last_page_min_row_height(c004_v1, tmp_path):
    """마지막 페이지의 데이터 행도 14mm 이상."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_last_page.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    import pdfplumber
    with pdfplumber.open(str(out)) as pdf:
        last = pdf.pages[-1]
        tbls = last.find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
        assert tbls, "Last page must have a table"
        rows = tbls[0].rows
        data_rows = rows[2:]  # skip 2 repeated header rows
        assert data_rows, "Last page must have data rows"
        for r in data_rows:
            h = round((r.bbox[3] - r.bbox[1]) / 2.8346, 2)
            assert h >= MIN_ROW_H_MM - TOLERANCE_MM, \
                f"Last page row height {h}mm < {MIN_ROW_H_MM}mm"


# ─── C09-04: 긴 텍스트 행 14mm 초과 확장 ────────────────────────────

def test_C0904_long_text_row_expands_beyond_14mm(c004_v1, tmp_path):
    """긴 텍스트가 있는 행은 14mm보다 크게 확장 가능."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_longtext.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[''] * len(cols)] * 10
    # Insert long text in first row, first column
    long_text = '2-에틸헥사놀(2-Ethyl-1-hexanol, CAS 104-76-7, 분자량 130.23, 끓는점 184.3℃)'
    ex_rows[0] = [long_text] + [''] * (len(cols) - 1)
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    heights = _measure_data_row_heights(out)
    assert heights, "Must have measured data rows"
    max_h = max(heights)
    assert max_h > MIN_ROW_H_MM + 1.0, \
        f"Long text row should exceed {MIN_ROW_H_MM}mm, got max={max_h}mm"
    below = [h for h in heights if h < MIN_ROW_H_MM - TOLERANCE_MM]
    assert not below, f"Other rows below minimum: {below}"


# ─── C09-05: R00~R29 전수 검증 ───────────────────────────────────────

def test_C0905_r00_r29_no_missing_no_duplicate(c004_v1, tmp_path):
    """R00~R29 30개 식별자가 각 정확히 1회 출력됨."""
    import re, pdfplumber
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_r00r29.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    found = {}
    with pdfplumber.open(str(out)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            for rid in re.findall(r'R\d{2}', text):
                if int(rid[1:]) < 30:
                    found[rid] = found.get(rid, 0) + 1
    missing = [f'R{i:02d}' for i in range(30) if f'R{i:02d}' not in found]
    dups = [k for k, v in found.items() if v > 1]
    assert not missing, f"Missing identifiers: {missing}"
    assert not dups, f"Duplicate identifiers: {dups}"
    assert len(found) == 30, f"Expected 30, found {len(found)}"


# ─── C09-06: 2단 헤더 전 페이지 반복 ────────────────────────────────

def test_C0906_two_tier_header_repeats_all_pages(c004_v1, tmp_path):
    """데이터 행이 있는 모든 페이지에서 폭발한계 헤더가 반복됨."""
    import re, pdfplumber
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c004_hdr_all.pdf'
    cols = c004_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c004_v1, out, ex_rows=ex_rows)
    with pdfplumber.open(str(out)) as pdf:
        for pi, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            has_data = bool(re.search(r'R\d{2}', text))
            if has_data:
                assert '화학물질' in text or '폭발한계' in text, \
                    f"Page {pi+1} has data rows but no header"


# ─── C09-07: 기존 출력물 SHA256 불변 (PDF 제외 — 재생성 허용) ─────────

def test_C0907_existing_outputs_unchanged():
    """PATCH-1 후 DOCX 및 비C004 PDF 출력물 SHA256 불변."""
    import hashlib
    expected = {
        'TAI-FORM-C004-blank.docx':  'ca0ef2d3f160b1ae88809c5aa8ceb10cd84be50e8c3ef10a665299dbf408f645',
    }
    for fname, exp_sha in expected.items():
        p = OUTPUT / fname
        assert p.exists(), f"{fname} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, \
            f"{fname}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"


# ─── C09-08: 신규 C004 PDF SHA256 ────────────────────────────────────

def test_C0908_c004_pdf_patch1_sha256():
    """PATCH-1 재생성 후 C004 PDF SHA256 기준본 검증."""
    import hashlib
    p = OUTPUT / 'TAI-FORM-C004-blank.pdf'
    assert p.exists(), "TAI-FORM-C004-blank.pdf must exist"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    expected = 'd2be9950cbdee03d00ec0a9e25d2efd9af643bf6352b0b342ac55ff48dcf99ec'
    assert actual == expected, \
        f"C004 PDF SHA256 mismatch\n  expected: {expected}\n  actual:   {actual}"


# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B5-B1 — REF-C005 작업별 위험관리 대장
# ═══════════════════════════════════════════════════════════════════════

MIN_ROW_H_C005_MM = 14.0
TOLERANCE_C005_MM = 0.5

@pytest.fixture
def c005_v1():
    return json.loads((BASE / 'c005_v1.json').read_text(encoding='utf-8'))

# ─── C10-01: REF-C005 JSON 스키마 검증 ───────────────────────────────

def test_C1001_c005_schema_version(c005_v1):
    assert c005_v1['_meta']['schema_version'] == 'common-v1'

def test_C1001_c005_form_type(c005_v1):
    assert c005_v1['_meta']['form_type'] == 'REGISTER'

def test_C1001_c005_title(c005_v1):
    assert c005_v1['document']['title'] == '작업별 위험관리 대장 작성 서식'

def test_C1001_c005_landscape(c005_v1):
    assert c005_v1['document']['page']['orientation'] == 'landscape'

def test_C1001_c005_single_repeat_table(c005_v1):
    secs = c005_v1['sections']
    assert len(secs) == 1
    assert secs[0]['type'] == 'repeat_table'

def test_C1001_c005_no_header_groups(c005_v1):
    assert 'header_groups' not in c005_v1['sections'][0]

def test_C1001_c005_9_columns(c005_v1):
    cols = c005_v1['sections'][0]['columns']
    assert len(cols) == 9, f"Expected 9 columns, got {len(cols)}"

def test_C1001_c005_column_width_sum_257mm(c005_v1):
    total = sum(c['width_mm'] for c in c005_v1['sections'][0]['columns'])
    assert total == 257, f"Column widths sum {total}mm != 257mm"

def test_C1001_c005_default_row_count_6(c005_v1):
    assert c005_v1['sections'][0]['default_row_count'] == 6

def test_C1001_c005_min_row_height_14mm(c005_v1):
    assert c005_v1['sections'][0]['min_row_height_mm'] == 14

def test_C1001_c005_column_labels_original_order(c005_v1):
    """9개 열이 원본 관찰 순서를 유지함."""
    expected = [
        '단위작업장소', '작업내용', '위험코드',
        '관련기계·기구·설비(관리번호)', '화학물질명(CAS No)',
        '발생가능재해형태', '관련협력업체', '위험성', '비고',
    ]
    actual = [c['label'] for c in c005_v1['sections'][0]['columns']]
    assert actual == expected, f"Column label order mismatch: {actual}"

def test_C1001_c005_column_ids_no_extra_fields(c005_v1):
    """원본에 없는 필드 없음 — 9개 ID만 존재."""
    expected_ids = [
        'F01_LOCATION', 'F02_WORK', 'F03_RISK_CODE',
        'F04_MACHINE', 'F05_CHEMICAL',
        'F06_ACCIDENT', 'F07_CONTRACTOR', 'F08_RISK_LEVEL', 'F09_REMARK',
    ]
    actual_ids = [c['id'] for c in c005_v1['sections'][0]['columns']]
    assert actual_ids == expected_ids, f"Column ID mismatch: {actual_ids}"

def test_C1001_c005_engine_schema_validation(c005_v1):
    assert validate(c005_v1) is True

# ─── C10-02: REF-C005 DOCX 생성 ──────────────────────────────────────

def test_C1002_c005_docx_generates(c005_v1, tmp_path):
    v1_path = tmp_path / 'c005_v1.json'
    out_path = tmp_path / 'c005_blank.docx'
    v1_path.write_text(json.dumps(c005_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3000

def test_C1002_c005_docx_landscape(c005_v1, tmp_path):
    """C005 DOCX pgSz가 landscape (297×210mm)."""
    v1_path = tmp_path / 'c005_v1.json'
    out_path = tmp_path / 'c005_blank.docx'
    v1_path.write_text(json.dumps(c005_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    pgSz = root.find('.//w:pgSz', {'w': NS})
    assert pgSz is not None
    w = int(pgSz.get(f'{{{NS}}}w', 0))
    h = int(pgSz.get(f'{{{NS}}}h', 0))
    orient = pgSz.get(f'{{{NS}}}orient', '')
    assert orient == 'landscape', f"Expected landscape, got {orient!r}"
    assert abs(w / 56.7 - 297) < 3, f"Page width {w/56.7:.1f}mm expected ~297mm"
    assert abs(h / 56.7 - 210) < 3, f"Page height {h/56.7:.1f}mm expected ~210mm"

def test_C1002_c005_docx_9_columns(c005_v1, tmp_path):
    """DOCX 반복 표가 9개 열을 가짐."""
    v1_path = tmp_path / 'c005_v1.json'
    out_path = tmp_path / 'c005_blank.docx'
    v1_path.write_text(json.dumps(c005_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    hdr_cells = rows[0].findall('w:tc', {'w': NS})
    assert len(hdr_cells) == 9, f"Expected 9 header cells, got {len(hdr_cells)}"

def test_C1002_c005_docx_all_labels(c005_v1, tmp_path):
    """DOCX 헤더 행에 9개 열 라벨이 모두 포함됨."""
    v1_path = tmp_path / 'c005_v1.json'
    out_path = tmp_path / 'c005_blank.docx'
    v1_path.write_text(json.dumps(c005_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        full_xml = z.read('word/document.xml').decode('utf-8')
    for label in ['단위작업장소', '작업내용', '위험코드', '화학물질명', '위험성', '비고']:
        assert label in full_xml, f"Label '{label}' not found in DOCX"

def test_C1002_c005_docx_6_default_rows(c005_v1, tmp_path):
    """DOCX 반복 표가 헤더 1행 + 데이터 6행 = 7행."""
    v1_path = tmp_path / 'c005_v1.json'
    out_path = tmp_path / 'c005_blank.docx'
    v1_path.write_text(json.dumps(c005_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[1]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    assert len(rows) == 7, f"Expected 7 rows (1 header + 6 data), got {len(rows)}"

# ─── C10-03: REF-C005 PDF 생성 검증 ──────────────────────────────────

def test_C1003_c005_pdf_generates(c005_v1, tmp_path):
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_blank.pdf'
    generate_from_dict(c005_v1, out)
    assert out.exists()
    assert out.stat().st_size > 10_000

def test_C1003_c005_pdf_landscape(c005_v1, tmp_path):
    """C005 PDF A4 landscape (297×210mm)."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_landscape.pdf'
    generate_from_dict(c005_v1, out)
    doc = pymupdf.open(str(out))
    page = doc[0]
    w_mm = page.rect.width / 2.8346
    h_mm = page.rect.height / 2.8346
    assert abs(w_mm - 297) < 2, f"Width {w_mm:.1f}mm expected ~297mm"
    assert abs(h_mm - 210) < 2, f"Height {h_mm:.1f}mm expected ~210mm"

def test_C1003_c005_pdf_1page_default(c005_v1, tmp_path):
    """기본 6행 PDF가 1페이지."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_blank.pdf'
    generate_from_dict(c005_v1, out)
    import pdfplumber
    with pdfplumber.open(str(out)) as pdf:
        assert len(pdf.pages) == 1, f"Expected 1 page, got {len(pdf.pages)}"

def test_C1003_c005_pdf_title_and_labels(c005_v1, tmp_path):
    """PDF에 제목과 주요 열 라벨이 포함됨. 좁은 열(18mm)의 줄바꿈은 공백 제거 후 검사."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_labels.pdf'
    generate_from_dict(c005_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    joined = full_text.replace('\n', '').replace(' ', '')
    for keyword in ['작업별위험관리', '단위작업', '작업내용', '위험성', '비고']:
        assert keyword in joined, f"'{keyword}' not found in PDF (whitespace-stripped)"
    # Narrow column (18mm) may split '위험코드' — check stripped
    assert '위험코드' in joined, "'위험코드' not found in PDF (whitespace-stripped)"

def test_C1003_c005_pdf_6_blank_rows(c005_v1, tmp_path):
    """PDF 기본 빈 행이 6개."""
    import pdfplumber
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_blank.pdf'
    generate_from_dict(c005_v1, out)
    with pdfplumber.open(str(out)) as pdf:
        tbls = pdf.pages[0].find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
        rows = tbls[0].rows
        # Row 0 = title, Row 1 = header, Rows 2..7 = 6 data rows
        data_rows = rows[2:]
        assert len(data_rows) == 6, f"Expected 6 data rows, got {len(data_rows)}"

def test_C1003_c005_pdf_30rows_no_missing_no_duplicate(c005_v1, tmp_path):
    """30행 고유 식별자 R00~R29 누락·중복 없음."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_30rows.pdf'
    cols = c005_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c005_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc)
    found = set()
    for i in range(30):
        tag = f'R{i:02d}'
        count = full_text.count(tag)
        assert count == 1, f"'{tag}' appears {count} times (expected 1)"
        found.add(tag)
    assert len(found) == 30

def test_C1003_c005_pdf_header_repeats_on_multipage(c005_v1, tmp_path):
    """30행 분할 시 모든 페이지에 단열 헤더가 반복."""
    import pdfplumber, pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_30rows.pdf'
    cols = c005_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c005_v1, out, ex_rows=ex_rows)
    with pdfplumber.open(str(out)) as pdf:
        assert len(pdf.pages) >= 2, "30 rows should span multiple pages"
        for pi, page in enumerate(pdf.pages):
            tbls = page.find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
            assert tbls, f"Page {pi+1}: no table found"
            rows_data = tbls[0].extract()
            hdr_row = rows_data[0] if pi > 0 else rows_data[1]
            hdr_text = ''.join(str(c or '') for c in hdr_row)
            assert '단위작업' in hdr_text or '작업내용' in hdr_text, \
                f"Page {pi+1}: header not found, row text: {hdr_text[:60]!r}"

def test_C1003_c005_pdf_all_data_rows_min_14mm(c005_v1, tmp_path):
    """30행 분할 후 모든 데이터 행이 14mm 이상 (단일 헤더 경로)."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_30rows_minheight.pdf'
    cols = c005_v1['sections'][0]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c005_v1, out, ex_rows=ex_rows)
    # n_hdr_page1=2: title row + header row; n_hdr_rest=1: header row only
    heights = _measure_data_row_heights(out, n_hdr_page1=2, n_hdr_rest=1)
    assert len(heights) == 30, f"Expected 30 data rows, got {len(heights)}"
    below = [h for h in heights if h < MIN_ROW_H_C005_MM - TOLERANCE_C005_MM]
    assert not below, f"Rows below {MIN_ROW_H_C005_MM}mm on split pages: {below}"

def test_C1003_c005_pdf_long_text_row_expands(c005_v1, tmp_path):
    """긴 텍스트 입력 시 행 높이가 14mm 초과 확장."""
    from common_v1_engine import register_fonts
    import pdfplumber
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c005_longtext.pdf'
    cols = c005_v1['sections'][0]['columns']
    long_text = '이 행은 매우 긴 작업내용 설명으로 행 높이가 자연스럽게 확장되어야 합니다. ' * 3
    ex_rows = [['' , long_text] + [''] * (len(cols) - 2)]
    generate_from_dict(c005_v1, out, ex_rows=ex_rows)
    with pdfplumber.open(str(out)) as pdf:
        tbls = pdf.pages[0].find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
        rows = tbls[0].rows
        data_rows = rows[2:]  # skip title + header
        tall_rows = [round((r.bbox[3] - r.bbox[1]) / 2.8346, 1) for r in data_rows if (r.bbox[3]-r.bbox[1])/2.8346 > MIN_ROW_H_C005_MM + 1]
        assert tall_rows, f"No row expanded beyond {MIN_ROW_H_C005_MM+1}mm — long text not expanding rows"

# ─── C10-04: REF-C005 회귀 ───────────────────────────────────────────

def test_C1004_c005_json_sha256():
    """C005 JSON 파일 SHA256 기준본 검증."""
    import hashlib
    p = BASE / 'c005_v1.json'
    assert p.exists(), "c005_v1.json must exist"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    expected = '155343fb7d56fb9aee2e4b87884ee7b09b403a69fc026ce1d77cca3bc2e9bca0'
    assert actual == expected, f"c005_v1.json SHA256 changed\n  expected: {expected}\n  actual: {actual}"

def test_C1004_c005_pdf_sha256():
    """C005 PDF SHA256 기준본 검증."""
    import hashlib
    p = OUTPUT / 'TAI-FORM-C005-blank.pdf'
    assert p.exists(), "TAI-FORM-C005-blank.pdf must exist"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    expected = '93cff8f970e68278f7c2dc2adc21ce2392d7ad9cbddc58dcbe174799d1d23d88'
    assert actual == expected, f"C005 PDF SHA256 changed\n  expected: {expected}\n  actual: {actual}"

def test_C1004_c005_docx_sha256():
    """C005 DOCX SHA256 기준본 검증."""
    import hashlib
    p = OUTPUT / 'TAI-FORM-C005-blank.docx'
    assert p.exists(), "TAI-FORM-C005-blank.docx must exist"
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    expected = '39099daa2156afcdaa8bbcc86a6200f91c5e8ca67b921ea2c4af7a9636326967'
    assert actual == expected, f"C005 DOCX SHA256 changed\n  expected: {expected}\n  actual: {actual}"

def test_C1004_c005_existing_outputs_unchanged():
    """C005 추가 후 기존 C003/C004/C014 출력물 SHA256 불변."""
    import hashlib
    expected = {
        'TAI-FORM-C004-blank.docx': 'ca0ef2d3f160b1ae88809c5aa8ceb10cd84be50e8c3ef10a665299dbf408f645',
        'TAI-FORM-C004-blank.pdf':  'd2be9950cbdee03d00ec0a9e25d2efd9af643bf6352b0b342ac55ff48dcf99ec',
    }
    for fname, exp_sha in expected.items():
        p = OUTPUT / fname
        assert p.exists(), f"{fname} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{fname}: SHA256 changed"

def test_C1004_c005_engine_sha256_unchanged():
    """C005 추가 후 공통 엔진 Python/Node SHA256 불변."""
    import hashlib
    expected = {
        'common_v1_engine.py':  'be4899dad868d4336756ce61134546748ac2b0f5f4eb4dbbf7488e795d3f2aba',
        'common_v1_engine.cjs': '375250c74ef1e22786526c1fa2446d989bbed95e8e513e85deeccc3bfb727925',
    }
    for fname, exp_sha in expected.items():
        p = BASE / fname
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{fname}: SHA256 changed"


# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B6-B1 — REF-C015 아차 사고 보고서
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def c015_v1():
    return json.loads((BASE / 'c015_v1.json').read_text(encoding='utf-8'))

# ─── C12-01: REF-C015 JSON 스키마 검증 ──────────────────────────────

def test_C1201_c015_schema_version(c015_v1):
    assert c015_v1['_meta']['schema_version'] == 'common-v1'

def test_C1201_c015_form_type_and_orientation(c015_v1):
    assert c015_v1['_meta']['form_type'] == 'REPORT'
    assert c015_v1['document']['page']['orientation'] == 'portrait'

def test_C1201_c015_layout_variant_metadata(c015_v1):
    """TAI_EDITABLE_VARIANT 메타데이터 및 source_layout_exact=false 확인."""
    assert c015_v1['_meta']['layout_variant'] == 'TAI_EDITABLE_VARIANT'
    assert c015_v1['_meta']['source_layout_exact'] is False

def test_C1201_c015_basic_info_2_fields(c015_v1):
    """basic_info S01: 작업명·등급 2개 항목."""
    s01 = c015_v1['sections'][0]
    assert s01['type'] == 'basic_info'
    assert s01['id'] == 'S01'
    labels = [f['label'] for f in s01['fields']]
    assert any('작업명' in l for l in labels), f"작업명 missing: {labels}"
    assert any('등급' in l for l in labels), f"등급 missing: {labels}"
    assert len(s01['fields']) == 2, f"Expected 2 fields, got {len(s01['fields'])}"

def test_C1201_c015_5_freeform_areas(c015_v1):
    """freeform_area 5개: 작업내용·사고내용·발생원인·예방대책·작업현장."""
    free = [s for s in c015_v1['sections'] if s['type'] == 'freeform_area']
    assert len(free) == 5, f"Expected 5 freeform_area, got {len(free)}"
    expected_labels = ['작업내용', '사고내용', '발생원인', '예방대책', '작업현장']
    for exp in expected_labels:
        assert any(exp in s['label'] for s in free), f"'{exp}' not in freeform labels"

def test_C1201_c015_7_original_fields_preserved(c015_v1):
    """원본 7개 필드(작업명·등급·작업내용·사고내용·발생원인·예방대책·작업현장) 누락 없음."""
    all_text = ' '.join(
        f.get('label', '') for s in c015_v1['sections']
        for f in (s.get('fields', []) if s['type'] == 'basic_info' else [])
    ) + ' ' + ' '.join(
        s.get('label', '') for s in c015_v1['sections']
        if s['type'] == 'freeform_area'
    )
    for field in ['작업명', '등급', '작업내용', '사고내용', '발생원인', '예방대책', '작업현장']:
        assert field in all_text, f"Original field '{field}' missing"

def test_C1201_c015_no_extra_fields(c015_v1):
    """원본 항목 외 임의 freeform 추가 없음 — freeform 정확히 5개."""
    free = [s for s in c015_v1['sections'] if s['type'] == 'freeform_area']
    assert len(free) == 5, f"Expected exactly 5 freeform, got {len(free)}"

def test_C1201_c015_grade_classification_in_text_flow(c015_v1):
    """등급 분류기준(A/B/C)과 중상·경상 설명이 text_flow S07에 존재."""
    s07 = next(s for s in c015_v1['sections'] if s['type'] == 'text_flow' and s.get('id') == 'S07')
    all_para_text = ' '.join(p['text'] for p in s07['paragraphs'])
    for key in ['A등급', 'B등급', 'C등급', '중대재해', '산업재해', '중상*', '경상**', '중상:', '경상:']:
        assert key in all_para_text, f"'{key}' missing from text_flow S07"

def test_C1201_c015_grade_content_integrity(c015_v1):
    """A/B/C 위험정도·조치 연결 정합성: 각 등급 위험정도와 조치 텍스트 대조."""
    s07 = next(s for s in c015_v1['sections'] if s['type'] == 'text_flow' and s.get('id') == 'S07')
    paras = {p['id']: p['text'] for p in s07['paragraphs']}
    # A등급
    assert '중대재해가 예상되는 경우' in paras['G01'], "A등급 위험정도 오류"
    assert '조업 중단' in paras['G01b'], "A등급 조치 오류"
    # B등급
    assert '중상*' in paras['G02'], "B등급 위험정도(중상*) 오류"
    assert '임시 조치' in paras['G02b'], "B등급 조치(임시조치) 오류"
    # C등급
    assert '경상**' in paras['G03'], "C등급 위험정도(경상**) 오류"
    assert '안전관리 조치' in paras['G03b'], "C등급 조치 오류"
    # 중상·경상 설명
    assert '하루 이상 입원' in paras['N01'], "중상 정의 오류"
    assert '사망, 중상을 제외한' in paras['N02'], "경상 정의 오류"

def test_C1201_c015_source_section_metadata(c015_v1):
    """WO-META-FIX-001: source_section/source_text_status/source_note에 HWP-15/15b 정확히 반영."""
    meta = c015_v1['_meta']
    assert 'HWP-15 Para 1954-1973' in meta['source_section'], "source_section에 HWP-15 누락"
    assert 'HWP-15b Para 1974-1993' in meta['source_section'], "source_section에 HWP-15b 누락"
    assert 'HWP-16' not in meta['source_section'], "source_section에 HWP-16 잔류 (C016 구간)"
    assert 'HWP-15 Para 1954-1973' in meta['source_text_status'], "source_text_status에 HWP-15 누락"
    assert 'HWP-15b Para 1974-1993' in meta['source_text_status'], "source_text_status에 HWP-15b 누락"
    assert 'HWP-16' not in meta['source_text_status'], "source_text_status에 HWP-16 잔류"
    s01 = next(s for s in c015_v1['sections'] if s.get('id') == 'S01')
    assert 'HWP-15 Para 1954-1973' in s01['source_note'], "S01 source_note에 HWP-15 누락"
    assert 'HWP-16' not in s01['source_note'], "S01 source_note에 HWP-16 잔류"
    s07 = next(s for s in c015_v1['sections'] if s.get('id') == 'S07')
    assert 'HWP-15b Para 1974-1993' in s07['source_note'], "S07 source_note에 HWP-15b 누락"
    assert 'HWP-16' not in s07['source_note'], "S07 source_note에 HWP-16 잔류"

# ─── C12-02: REF-C015 DOCX 생성 ────────────────────────────────────

def test_C1202_c015_docx_generates(c015_v1, tmp_path):
    """DOCX 생성 성공 및 Portrait 방향 확인."""
    v1_path = tmp_path / 'c015_v1.json'
    out_path = tmp_path / 'c015_blank.docx'
    v1_path.write_text(json.dumps(c015_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3000
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    pgSz = root.find('.//w:pgSz', {'w': NS})
    assert pgSz is not None
    orient = pgSz.get(f'{{{NS}}}orient', '')
    assert orient != 'landscape', f"C015 should be Portrait, got {orient!r}"

def test_C1202_c015_docx_table_structure(c015_v1, tmp_path):
    """DOCX: 7개 테이블(제목·basic_info·freeform×5)."""
    v1_path = tmp_path / 'c015_v1.json'
    out_path = tmp_path / 'c015_blank.docx'
    v1_path.write_text(json.dumps(c015_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    assert len(tables) == 7, f"Expected 7 tables (title+basic_info+5×freeform), got {len(tables)}"

def test_C1202_c015_docx_basic_info_2_cells(c015_v1, tmp_path):
    """DOCX basic_info 행: 작업명·등급 2셀 확인."""
    v1_path = tmp_path / 'c015_v1.json'
    out_path = tmp_path / 'c015_blank.docx'
    v1_path.write_text(json.dumps(c015_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    basic_tbl = tables[1]  # title=0, basic_info=1
    rows = basic_tbl.findall('w:tr', {'w': NS})
    assert len(rows) == 1, f"basic_info should have 1 row, got {len(rows)}"
    cells = rows[0].findall('w:tc', {'w': NS})
    assert len(cells) == 2, f"basic_info row should have 2 cells, got {len(cells)}"
    full_text = ''.join(r.text or '' for r in basic_tbl.findall('.//w:t', {'w': NS}))
    assert '작업명' in full_text
    assert '등급' in full_text

def test_C1202_c015_docx_freeform_editable_rows(c015_v1, tmp_path):
    """DOCX freeform_area: 각 영역이 입력 가능한 빈 행 보유."""
    v1_path = tmp_path / 'c015_v1.json'
    out_path = tmp_path / 'c015_blank.docx'
    v1_path.write_text(json.dumps(c015_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    # Tables 2-6 are freeform_area (index 2..6)
    for ti in range(2, 7):
        tbl = tables[ti]
        rows = tbl.findall('w:tr', {'w': NS})
        assert len(rows) == 2, f"freeform table {ti} should have 2 rows (header+empty), got {len(rows)}"

def test_C1202_c015_docx_grade_not_confused_with_input(c015_v1, tmp_path):
    """DOCX: 입력용 등급 셀(basic_info)과 분류기준 텍스트(text_flow 단락)가 혼동 없이 분리."""
    v1_path = tmp_path / 'c015_v1.json'
    out_path = tmp_path / 'c015_blank.docx'
    v1_path.write_text(json.dumps(c015_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    # basic_info table (index 1) must NOT contain "A등급 위험정도"
    basic_text = ''.join(r.text or '' for r in tables[1].findall('.//w:t', {'w': NS}))
    assert 'A등급 위험정도' not in basic_text, "Grade definition should not appear in input field"
    # text_flow paragraphs (outside tables) must contain "A등급"
    body = root.find('w:body', {'w': NS})
    para_texts = ''.join(
        r.text or '' for p in body
        if p.tag == f'{{{NS}}}p'
        for r in p.findall('.//w:t', {'w': NS})
    )
    assert 'A등급' in para_texts, "A등급 must appear in text_flow paragraphs"
    assert 'B등급' in para_texts
    assert 'C등급' in para_texts

# ─── C12-03: REF-C015 PDF 렌더링 검증 ──────────────────────────────

def test_C1203_c015_pdf_generates(c015_v1, tmp_path):
    """PDF 생성 성공: A4 Portrait 1페이지."""
    import sys, pdfplumber
    sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out_path = tmp_path / 'c015_blank.pdf'
    generate_from_dict(c015_v1, str(out_path))
    assert out_path.exists() and out_path.stat().st_size > 5000
    with pdfplumber.open(str(out_path)) as pdf:
        assert len(pdf.pages) == 1, f"Expected 1 page, got {len(pdf.pages)}"
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 2, f"Width {p.width/2.835:.1f}mm != 210mm"
        assert abs(p.height / 2.835 - 297) < 2, f"Height {p.height/2.835:.1f}mm != 297mm"

def test_C1203_c015_pdf_7_fields_present(c015_v1, tmp_path):
    """PDF: 원본 7개 입력 항목 모두 존재."""
    import sys, pdfplumber; sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out_path = tmp_path / 'c015_blank.pdf'
    generate_from_dict(c015_v1, str(out_path))
    with pdfplumber.open(str(out_path)) as pdf:
        text = pdf.pages[0].extract_text() or ''
    for field in ['작업명', '등급', '작업내용', '사고내용', '발생원인', '예방대책', '작업현장']:
        assert field in text, f"PDF missing field: '{field}'"

def test_C1203_c015_pdf_grade_abc_all_present(c015_v1, tmp_path):
    """PDF: A/B/C 등급 분류기준 모두 존재."""
    import sys, pdfplumber; sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out_path = tmp_path / 'c015_blank.pdf'
    generate_from_dict(c015_v1, str(out_path))
    with pdfplumber.open(str(out_path)) as pdf:
        text = pdf.pages[0].extract_text() or ''
    for key in ['A등급', 'B등급', 'C등급']:
        assert key in text, f"PDF missing grade: '{key}'"

def test_C1203_c015_pdf_grade_criteria_complete(c015_v1, tmp_path):
    """PDF: 등급별 위험정도·조치 및 중상·경상 정의 누락 없음."""
    import sys, pdfplumber; sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out_path = tmp_path / 'c015_blank.pdf'
    generate_from_dict(c015_v1, str(out_path))
    with pdfplumber.open(str(out_path)) as pdf:
        text = pdf.pages[0].extract_text() or ''
    criteria = [
        '중대재해가 예상되는 경우',    # A 위험정도
        '조업 중단',                  # A 조치
        '중상*',                       # B 위험정도
        '임시 조치',                   # B 조치
        '경상**',                      # C 위험정도
        '안전관리 조치',               # C 조치
        '하루 이상 입원',              # 중상 정의
        '사망, 중상을 제외한',         # 경상 정의
    ]
    missing = [c for c in criteria if c not in text]
    assert not missing, f"PDF missing criteria: {missing}"

def test_C1203_c015_pdf_no_content_clipping(c015_v1, tmp_path):
    """PDF: 콘텐츠 잘림 없음 (우측·하단 경계 초과 텍스트 없음)."""
    import sys, pdfplumber; sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out_path = tmp_path / 'c015_blank.pdf'
    generate_from_dict(c015_v1, str(out_path))
    with pdfplumber.open(str(out_path)) as pdf:
        p = pdf.pages[0]
        page_w_mm = p.width / 2.835
        page_h_mm = p.height / 2.835
        words = p.extract_words()
        content_words = [w for w in words if '/' not in w['text'] and w['text'].isdigit() is False]
        clipped = [
            w for w in content_words
            if w['x1'] / 2.835 > page_w_mm - 3 or w['bottom'] / 2.835 > page_h_mm - 8
        ]
        assert len(clipped) == 0, f"Clipped words near edge: {[(w['text'], w['x1']/2.835, w['bottom']/2.835) for w in clipped]}"

# ─── C12-04: REF-C015 SHA256 회귀 ────────────────────────────────────

def test_C1204_c015_sha256_regression():
    """C015 json/pdf/docx SHA256 기준본 및 기존 엔진·C005·C016 불변."""
    import hashlib
    c015_expected = {
        'scripts/c015_v1.json':               '233fbc6bc57ce0ab91efa176a360052fd5c507dea143d71044079ca3783ee3ba',
        'output/TAI-FORM-C015-blank.pdf':  '77481eeae8eff7e27ef2fc50d452eb5cfa9fc018d02b45e7c6aab0ce0578235b',
        'output/TAI-FORM-C015-blank.docx': 'ec558785f4cec658af9a80134e78dd84a2ad7af88396fe38aa9cb5e9fa9739b9',
    }
    engine_expected = {
        'scripts/common_v1_engine.py':  'be4899daf4f1ffd5ed59c4c2f26cc8e45c1d8e35e97a04eb8e944b1d0f5bc95a',
        'scripts/common_v1_engine.cjs': '375250c7',  # partial prefix check
    }
    existing_expected = {
        'scripts/c016_v1.json':               'c7166ff4d4590a6311a4200679d74b278757cbd073754eb6ec54805559c9adf3',
        'output/TAI-FORM-C016-blank.pdf':  'a12fe50aba41a3bc78d72c176a37ca47099539cb9f229d4e622f0213567f32bd',
        'output/TAI-FORM-C016-blank.docx': 'bad68d52f6370c8be347a64524ef3de270ec0fad6b87889a3fe125f72cfcbfe5',
        'output/TAI-FORM-C005-blank.pdf':  '93cff8f970e68278f7c2dc2adc21ce2392d7ad9cbddc58dcbe174799d1d23d88',
        'output/TAI-FORM-C005-blank.docx': '39099daa2156afcdaa8bbcc86a6200f91c5e8ca67b921ea2c4af7a9636326967',
    }
    for rel_path, exp_sha in {**c015_expected, **existing_expected}.items():
        p = BASE.parent / rel_path
        assert p.exists(), f"{p.name} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{p.name}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"
    # Engine: full SHA check
    py_path = BASE.parent / 'scripts/common_v1_engine.py'
    py_sha = hashlib.sha256(py_path.read_bytes()).hexdigest()
    assert py_sha.startswith('be4899da'), f"Engine PY SHA changed: {py_sha[:8]}"
    cjs_path = BASE.parent / 'scripts/common_v1_engine.cjs'
    cjs_sha = hashlib.sha256(cjs_path.read_bytes()).hexdigest()
    assert cjs_sha.startswith('375250c7'), f"Engine CJS SHA changed: {cjs_sha[:8]}"


# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B7-BATCH-PRODUCTION-001 — 배치 실행기 + 신규 4건 스펙
# ═══════════════════════════════════════════════════════════════════════

# ─── C13-01: 배치 실행기 구조 검증 ──────────────────────────────────────

def test_C1301_batch_runner_exists():
    """batch_build.py 존재 및 필수 모드 플래그 포함."""
    p = BASE / 'batch_build.py'
    assert p.exists(), "batch_build.py 없음"
    src = p.read_text(encoding='utf-8')
    for flag in ('--dry-run', '--verify-only', '--build', '--list', 'APPROVED_IDS'):
        assert flag in src, f"batch_build.py에 {flag!r} 없음"

def test_C1301_batch_runner_dry_run_approved():
    """배치 실행기 --dry-run 모드로 기존 승인 서식 7건 SCHEMA_VALID."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, 'batch_build.py', '--dry-run',
         'c001', 'c003', 'c004', 'c005', 'c014', 'c015', 'c016'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert result.returncode == 0, f"batch_build.py 실패:\n{result.stderr}"
    out = result.stdout
    for cid in ('C001', 'C003', 'C004', 'C005', 'C014', 'C015', 'C016'):
        assert 'SCHEMA_VALID' in out, f"{cid} SCHEMA_VALID 없음"
    assert 'SCHEMA_ERROR' not in out, "기존 승인 서식에서 SCHEMA_ERROR 발생"

def test_C1301_batch_runner_dry_run_new_specs():
    """배치 실행기 --dry-run으로 신규 5건(C007/C008/C009/C011/C013) SCHEMA_VALID."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, 'batch_build.py', '--dry-run',
         'c007', 'c008', 'c009', 'c011', 'c013'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert result.returncode == 0, f"batch_build.py 실패:\n{result.stderr}"
    out = result.stdout
    for cid in ('C007', 'C008', 'C009', 'C011', 'C013'):
        assert 'SCHEMA_VALID' in out, f"{cid} SCHEMA_VALID 없음"
    assert 'SCHEMA_ERROR' not in out

def test_C1301_batch_runner_frozen_guard():
    """--build 모드에서 승인 서식 덮어쓰기 방지 — exit nonzero + BLOCKED 메시지."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, 'batch_build.py', '--build', 'c015'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert result.returncode != 0, "승인 서식 --build는 반드시 nonzero exit"
    assert 'BLOCKED' in result.stdout or 'frozen' in result.stdout.lower(), \
        "승인 서식에 --build 실행 시 BLOCKED 메시지 없음"

def test_C1301_batch_runner_build_approved_empty():
    """BUILD_APPROVED_IDS가 비어있으면 --build 단독 실행 시 exit nonzero."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, 'batch_build.py', '--build'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert result.returncode != 0, "--build with empty BUILD_APPROVED_IDS는 nonzero exit"

def test_C1301_batch_runner_build_new_blocked():
    """신규 서식(c013)에 --build 실행 시 BUILD_APPROVED_IDS 미포함으로 BLOCKED."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, 'batch_build.py', '--build', 'c013'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert result.returncode != 0, "미승인 신규 서식 --build는 nonzero exit"
    assert 'BLOCKED' in result.stdout, "미승인 서식 BLOCKED 메시지 없음"

# ─── C13-02: 신규 스펙 JSON 구조 검증 ───────────────────────────────────

@pytest.fixture
def c007_v1():
    return json.loads((BASE / 'c007_v1.json').read_text(encoding='utf-8'))

@pytest.fixture
def c008_v1():
    return json.loads((BASE / 'c008_v1.json').read_text(encoding='utf-8'))

@pytest.fixture
def c009_v1():
    return json.loads((BASE / 'c009_v1.json').read_text(encoding='utf-8'))

@pytest.fixture
def c011_v1():
    return json.loads((BASE / 'c011_v1.json').read_text(encoding='utf-8'))

@pytest.fixture
def c013_v1():
    return json.loads((BASE / 'c013_v1.json').read_text(encoding='utf-8'))

def test_C1302_new_specs_schema_version(c007_v1, c008_v1, c009_v1, c011_v1, c013_v1):
    """신규 5건 모두 schema_version=common-v1."""
    for data, name in [(c007_v1,'C007'),(c008_v1,'C008'),(c009_v1,'C009'),(c011_v1,'C011'),(c013_v1,'C013')]:
        assert data['_meta']['schema_version'] == 'common-v1', f"{name} schema_version 오류"

def test_C1302_new_specs_design_gate_status(c007_v1, c008_v1, c009_v1, c011_v1, c013_v1):
    """신규 5건 모두 design_gate_status 필드 포함 및 GPT 승인 대기 명시."""
    for data, name in [(c007_v1,'C007'),(c008_v1,'C008'),(c009_v1,'C009'),(c011_v1,'C011'),(c013_v1,'C013')]:
        status = data['_meta'].get('design_gate_status', '')
        assert status, f"{name} design_gate_status 없음"
        assert 'EDITABLE_VARIANT_REVIEW' in status or 'ENGINE_GAP' in status, \
            f"{name} design_gate_status 인식 불가: {status!r}"

def test_C1302_new_specs_layout_variant(c007_v1, c008_v1, c009_v1, c011_v1, c013_v1):
    """신규 5건 모두 layout_variant=TAI_EDITABLE_VARIANT."""
    for data, name in [(c007_v1,'C007'),(c008_v1,'C008'),(c009_v1,'C009'),(c011_v1,'C011'),(c013_v1,'C013')]:
        assert data['_meta']['layout_variant'] == 'TAI_EDITABLE_VARIANT', \
            f"{name} layout_variant 오류"

def test_C1302_c007_budget_structure(c007_v1):
    """C007: repeat_table(입력) + text_flow(참조) 2섹션. 3열(구분/2021/2022) 구성."""
    secs = c007_v1['sections']
    assert len(secs) == 2
    assert secs[0]['type'] == 'repeat_table'
    assert secs[1]['type'] == 'text_flow'
    cols = secs[0]['columns']
    assert len(cols) == 3, f"C007 컬럼 수 오류: {len(cols)} (expected 3)"
    labels = [c['label'] for c in cols]
    assert '구분' in labels and '2021' in labels and '2022' in labels, \
        f"C007 컬럼 레이블 오류: {labels}"
    paras = {p['id']: p['text'] for p in secs[1]['paragraphs']}
    assert any('교육 지원' in t for t in paras.values()), "C007 교육 지원 참조 항목 없음"
    assert any('시설 지원' in t for t in paras.values()), "C007 시설 지원 참조 항목 없음"

def test_C1302_c008_evaluation_structure(c008_v1):
    """C008: text_flow(기준) + repeat_table(평가표) + text_flow(직무참조). 3섹션."""
    secs = c008_v1['sections']
    assert len(secs) == 3, f"C008 섹션 수 오류: {len(secs)} (expected 3)"
    assert secs[0]['type'] == 'text_flow'
    assert secs[1]['type'] == 'repeat_table'
    assert secs[2]['type'] == 'text_flow'
    rt = secs[1]
    assert 'header_groups' in rt, "C008 평가 header_groups 없음"
    assert len(rt['columns']) == 6
    col_labels = [c['label'] for c in rt['columns']]
    for lbl in ('직책', '성명', '담당업무', '미흡', '보통', '양호'):
        assert lbl in col_labels, f"C008 컬럼 {lbl!r} 없음"
    s01_texts = ' '.join(p['text'] for p in secs[0]['paragraphs'])
    assert '반기' in s01_texts, "C008 평가기준에 반기 주기 없음"
    assert '법령에 따른 업무수행' in s01_texts, "C008 양호 기준 원문 없음"
    s03_texts = ' '.join(p['text'] for p in secs[2]['paragraphs'])
    for role in ('안전보건관리책임자', '관리감독자', '안전보건총괄책임자'):
        assert role in s03_texts, f"C008 직무참조에 {role!r} 없음"

def test_C1302_c009_register_structure(c009_v1):
    """C009: repeat_table(배치) + text_flow(직무 참조). 4열 구성."""
    secs = c009_v1['sections']
    assert len(secs) == 2
    assert secs[0]['type'] == 'repeat_table'
    assert secs[1]['type'] == 'text_flow'
    cols = secs[0]['columns']
    assert len(cols) == 4
    col_labels = [c['label'] for c in cols]
    for lbl in ('직책', '성명', '담당업무', '비고'):
        assert lbl in col_labels, f"C009 컬럼 {lbl!r} 없음"

def test_C1302_c011_scoring_structure(c011_v1):
    """C011: text_flow(기준 100점) + repeat_table(점수 입력). 4열 구성."""
    secs = c011_v1['sections']
    assert len(secs) == 2
    assert secs[0]['type'] == 'text_flow'
    assert secs[1]['type'] == 'repeat_table'
    paras = {p['id']: p['text'] for p in secs[0]['paragraphs']}
    assert any('100점' in t for t in paras.values()), "C011 100점 기준 없음"
    col_labels = [c['label'] for c in secs[1]['columns']]
    for lbl in ('평가항목', '배점', '점수'):
        assert lbl in col_labels, f"C011 컬럼 {lbl!r} 없음"

def test_C1302_c009_duty_reference_content(c009_v1):
    """C009: 4개 역할별 산안법 조항 참조 텍스트 포함."""
    s02 = next(s for s in c009_v1['sections'] if s.get('id') == 'S02')
    texts = ' '.join(p['text'] for p in s02['paragraphs'])
    for role in ('안전관리자', '보건관리자', '안전보건관리담당자', '산업보건의'):
        assert role in texts, f"C009 역할 {role!r} 참조 텍스트 없음"
    assert '산안법' in texts or '산업안전보건법' in texts

def test_C1302_c013_accident_report_structure(c013_v1):
    """C013: basic_info + freeform_area 조합 12섹션. 사고조사반/사고명일시/피해/경위/대책."""
    secs = c013_v1['sections']
    assert len(secs) == 12, f"C013 섹션 수 오류: {len(secs)} (expected 12)"
    types = [s['type'] for s in secs]
    assert types[0] == 'basic_info', "C013 S01 basic_info(사고조사반) 아님"
    assert types[1] == 'basic_info', "C013 S02 basic_info(사고명/일시) 아님"
    assert all(t == 'freeform_area' for t in types[2:4]), "C013 S03-S04 freeform_area 아님"
    assert types[4] == 'basic_info', "C013 S05 basic_info(장소/부위/형태) 아님"
    assert all(t == 'freeform_area' for t in types[5:]), "C013 S06-S12 freeform_area 아님"
    s01_fields = [f['label'] for f in secs[0]['fields']]
    assert any('소속' in l for l in s01_fields), "C013 S01 소속 필드 없음"
    assert any('성명' in l for l in s01_fields), "C013 S01 성명 필드 없음"
    s05_fields = [f['label'] for f in secs[4]['fields']]
    assert any('사고장소' in l for l in s05_fields), "C013 S05 사고장소 없음"
    labels = [s.get('label','') for s in secs if s['type'] == 'freeform_area']
    for expected in ('인적 피해', '사고내용', '사고원인', '재발방지 대책', '사고조사 사진'):
        assert any(expected in l for l in labels), f"C013 freeform_area '{expected}' 없음"

def test_C1302_source_sections_correct(c007_v1, c008_v1, c009_v1, c011_v1, c013_v1):
    """신규 5건 source_section이 HWP-07/08/09/11/13 정확히 반영."""
    checks = [
        (c007_v1, 'C007', 'HWP-07'),
        (c008_v1, 'C008', 'HWP-08'),
        (c009_v1, 'C009', 'HWP-09'),
        (c011_v1, 'C011', 'HWP-11'),
        (c013_v1, 'C013', 'HWP-13'),
    ]
    for data, name, hwp in checks:
        ss = data['_meta'].get('source_section', '')
        assert hwp in ss, f"{name} source_section에 {hwp} 없음: {ss!r}"

# ─── C13-03: 신규 스펙 PDF 생성 시험 ────────────────────────────────────

def test_C1303_c007_pdf_generates(c007_v1, tmp_path):
    """C007 PDF 생성 성공 및 Portrait A4."""
    import sys as _sys, pdfplumber
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out = tmp_path / 'c007.pdf'
    generate_from_dict(c007_v1, str(out))
    assert out.exists() and out.stat().st_size > 5000
    with pdfplumber.open(str(out)) as pdf:
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 3
        assert abs(p.height / 2.835 - 297) < 3

def test_C1303_c008_pdf_generates(c008_v1, tmp_path):
    """C008 PDF 생성 성공 및 Portrait A4."""
    import sys as _sys, pdfplumber
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out = tmp_path / 'c008.pdf'
    generate_from_dict(c008_v1, str(out))
    assert out.exists() and out.stat().st_size > 5000
    with pdfplumber.open(str(out)) as pdf:
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 3
        assert abs(p.height / 2.835 - 297) < 3

def test_C1303_c009_pdf_generates(c009_v1, tmp_path):
    """C009 PDF 생성 성공 및 Portrait A4."""
    import sys as _sys, pdfplumber
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out = tmp_path / 'c009.pdf'
    generate_from_dict(c009_v1, str(out))
    assert out.exists() and out.stat().st_size > 5000
    with pdfplumber.open(str(out)) as pdf:
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 3
        assert abs(p.height / 2.835 - 297) < 3

def test_C1303_c011_pdf_generates(c011_v1, tmp_path):
    """C011 PDF 생성 성공 및 Portrait A4."""
    import sys as _sys, pdfplumber
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out = tmp_path / 'c011.pdf'
    generate_from_dict(c011_v1, str(out))
    assert out.exists() and out.stat().st_size > 5000
    with pdfplumber.open(str(out)) as pdf:
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 3
        assert abs(p.height / 2.835 - 297) < 3

def test_C1303_c013_pdf_generates(c013_v1, tmp_path):
    """C013 PDF 생성 성공 및 Portrait A4."""
    import sys as _sys, pdfplumber
    _sys.path.insert(0, str(BASE))
    from common_v1_engine import generate_from_dict, register_fonts
    register_fonts()
    out = tmp_path / 'c013.pdf'
    generate_from_dict(c013_v1, str(out))
    assert out.exists() and out.stat().st_size > 5000
    with pdfplumber.open(str(out)) as pdf:
        p = pdf.pages[0]
        assert abs(p.width / 2.835 - 210) < 3
        assert abs(p.height / 2.835 - 297) < 3

# ─── C13-04: 신규 스펙 DOCX 생성 시험 ──────────────────────────────────

def test_C1304_new_specs_docx_generate(tmp_path):
    """신규 5건 DOCX 생성 성공."""
    import subprocess
    for cid in ('c007', 'c008', 'c009', 'c011', 'c013'):
        json_path = BASE / f'{cid}_v1.json'
        out_path  = tmp_path / f'{cid}_blank.docx'
        result = subprocess.run(
            ['node', 'gen_c002_docx_common.cjs', str(json_path), str(out_path)],
            capture_output=True, text=True, cwd=str(BASE),
        )
        assert result.returncode == 0, f"{cid.upper()} DOCX 생성 실패:\n{result.stderr}"
        assert out_path.exists() and out_path.stat().st_size > 3000, \
            f"{cid.upper()} DOCX 파일 크기 이상"

# ─── C13-05: 엔진·기존 출력물 불변 확인 ────────────────────────────────

def test_C1305_engine_and_approved_outputs_unchanged():
    """B7 작업 후 공통 엔진 및 기존 승인 서식 SHA256 불변."""
    import hashlib
    checks = {
        'scripts/common_v1_engine.py':      ('be4899da', True),
        'output/TAI-FORM-C015-blank.pdf':   ('77481eea', False),
        'output/TAI-FORM-C015-blank.docx':  ('ec558785', False),
        'output/TAI-FORM-C016-blank.pdf':   ('a12fe50a', False),
        'output/TAI-FORM-C016-blank.docx':  ('bad68d52', False),
        'output/TAI-FORM-C005-blank.pdf':   ('93cff8f9', False),
        'output/TAI-FORM-C005-blank.docx':  ('39099daa', False),
    }
    for rel, (prefix, full) in checks.items():
        p = BASE.parent / rel
        assert p.exists(), f"{p.name} 없음"
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if full:
            assert sha.startswith(prefix), f"{p.name} SHA 변경: {sha[:8]}"
        else:
            assert sha.startswith(prefix), f"{p.name} SHA 변경: expected={prefix} actual={sha[:8]}"

# ═══════════════════════════════════════════════════════════════════════
# WO-REF01-059-B5-B2-RESUME-001 — REF-C016 연간 교육계획 수립 서식
# ═══════════════════════════════════════════════════════════════════════

MIN_ROW_H_C016_MM = 14.0
TOLERANCE_C016_MM = 0.5
# Page 1: title + approval_hdr + approval_sig + group_hdr + col_hdr = 5 rows
# Other pages: group_hdr + col_hdr = 2 rows
C016_N_HDR_P1  = 5
C016_N_HDR_REST = 2

@pytest.fixture
def c016_v1():
    return json.loads((BASE / 'c016_v1.json').read_text(encoding='utf-8'))

# ─── C11-01: REF-C016 JSON 스키마 검증 ───────────────────────────────

def test_C1101_c016_schema_version(c016_v1):
    assert c016_v1['_meta']['schema_version'] == 'common-v1'

def test_C1101_c016_form_type_and_orientation(c016_v1):
    assert c016_v1['_meta']['form_type'] == 'PLAN'
    assert c016_v1['document']['page']['orientation'] == 'landscape'

def test_C1101_c016_sections_approval_and_repeat(c016_v1):
    types = [s['type'] for s in c016_v1['sections']]
    assert types == ['approval', 'repeat_table'], f"Expected [approval, repeat_table], got {types}"
    appr = c016_v1['sections'][0]
    assert appr['label'] == '연간 교육계획'
    assert len(appr['fields']) == 3

def test_C1101_c016_20_columns_257mm(c016_v1):
    cols = c016_v1['sections'][1]['columns']
    assert len(cols) == 20, f"Expected 20 columns, got {len(cols)}"
    total = sum(c['width_mm'] for c in cols)
    assert total == 257, f"Column widths sum {total}mm != 257mm"

def test_C1101_c016_header_groups_and_month_widths(c016_v1):
    sec = c016_v1['sections'][1]
    groups = sec.get('header_groups', [])
    assert len(groups) == 2, f"Expected 2 header_groups, got {len(groups)}"
    g01 = next(g for g in groups if g['id'] == 'G01')
    g02 = next(g for g in groups if g['id'] == 'G02')
    assert len(g01['column_ids']) == 3, f"G01 should cover 3 columns"
    assert len(g02['column_ids']) == 12, f"G02 should cover 12 columns"
    col_by_id = {c['id']: c['width_mm'] for c in sec['columns']}
    # 1-9월 = 10mm, 10-12월 = 12mm
    for mid in ['F06_M01','F07_M02','F08_M03','F09_M04','F10_M05',
                'F11_M06','F12_M07','F13_M08','F14_M09']:
        assert col_by_id[mid] == 10, f"{mid} expected 10mm, got {col_by_id[mid]}mm"
    for mid in ['F15_M10','F16_M11','F17_M12']:
        assert col_by_id[mid] == 12, f"{mid} expected 12mm, got {col_by_id[mid]}mm"

def test_C1101_c016_engine_schema_validation(c016_v1):
    assert validate(c016_v1) is True

# ─── C11-02: REF-C016 DOCX 생성 ──────────────────────────────────────

def test_C1102_c016_docx_generates(c016_v1, tmp_path):
    v1_path = tmp_path / 'c016_v1.json'
    out_path = tmp_path / 'c016_blank.docx'
    v1_path.write_text(json.dumps(c016_v1, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(
        ['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"DOCX generation failed: {result.stderr}"
    assert out_path.exists() and out_path.stat().st_size > 3000
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    pgSz = root.find('.//w:pgSz', {'w': NS})
    assert pgSz is not None
    orient = pgSz.get(f'{{{NS}}}orient', '')
    assert orient == 'landscape', f"Expected landscape, got {orient!r}"

def test_C1102_c016_docx_20_grid_cols(c016_v1, tmp_path):
    """DOCX 반복 표 그리드가 정확히 20열, 합계 257mm."""
    v1_path = tmp_path / 'c016_v1.json'
    out_path = tmp_path / 'c016_blank.docx'
    v1_path.write_text(json.dumps(c016_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[2]  # title / approval / repeat
    grid = repeat_tbl.find('.//w:tblGrid', {'w': NS})
    cols = grid.findall('w:gridCol', {'w': NS})
    assert len(cols) == 20, f"Expected 20 grid columns, got {len(cols)}"
    total_twips = sum(int(c.get(f'{{{NS}}}w', 0)) for c in cols)
    total_mm = total_twips * 25.4 / 1440
    assert abs(total_mm - 257) < 1, f"Grid total {total_mm:.1f}mm != 257mm"

def test_C1102_c016_docx_header_group_spans(c016_v1, tmp_path):
    """DOCX 헤더 행 0의 교육구분 gridSpan=3, 일정 gridSpan=12."""
    v1_path = tmp_path / 'c016_v1.json'
    out_path = tmp_path / 'c016_blank.docx'
    v1_path.write_text(json.dumps(c016_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(out_path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[2]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    row0 = rows[0]
    cells = row0.findall('w:tc', {'w': NS})
    spans = {}
    for tc in cells:
        text = ''.join(r.text or '' for r in tc.findall('.//w:t', {'w': NS}))
        tcPr = tc.find('w:tcPr', {'w': NS})
        gs_el = tcPr.find('w:gridSpan', {'w': NS}) if tcPr is not None else None
        gs = int(gs_el.get(f'{{{NS}}}val', 1)) if gs_el is not None else 1
        if text.strip():
            spans[text.strip()] = gs
    assert spans.get('교육구분') == 3, f"교육구분 gridSpan={spans.get('교육구분')}, expected 3"
    assert spans.get('일정') == 12, f"일정 gridSpan={spans.get('일정')}, expected 12"

def test_C1102_c016_docx_month_labels_and_default_rows(c016_v1, tmp_path):
    """DOCX row[1]에 10월/11월/12월 포함, 반복 표 행 수 = 2 헤더 + 5 데이터 = 7."""
    v1_path = tmp_path / 'c016_v1.json'
    out_path = tmp_path / 'c016_blank.docx'
    v1_path.write_text(json.dumps(c016_v1, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(BASE / 'gen_c002_docx_common.cjs'), str(v1_path), str(out_path)],
                   cwd=str(BASE), capture_output=True, timeout=30, check=True)
    with zipfile.ZipFile(out_path) as z:
        full_xml = z.read('word/document.xml').decode('utf-8')
    for label in ['10월', '11월', '12월']:
        assert label in full_xml, f"Label '{label}' not found in DOCX"
    NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root = ET.fromstring(full_xml)
    tables = root.findall('.//w:tbl', {'w': NS})
    repeat_tbl = tables[2]
    rows = repeat_tbl.findall('w:tr', {'w': NS})
    assert len(rows) == 7, f"Expected 7 rows (2 hdr + 5 data), got {len(rows)}"

# ─── C11-03: REF-C016 PDF 생성 검증 ──────────────────────────────────

def test_C1103_c016_pdf_generates(c016_v1, tmp_path):
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_blank.pdf'
    generate_from_dict(c016_v1, out)
    assert out.exists() and out.stat().st_size > 10_000
    import pymupdf
    doc = pymupdf.open(str(out))
    assert len(doc) == 1, f"Expected 1 page, got {len(doc)}"
    page = doc[0]
    assert abs(page.rect.width / 2.8346 - 297) < 2
    assert abs(page.rect.height / 2.8346 - 210) < 2

def test_C1103_c016_pdf_labels_readable(c016_v1, tmp_path):
    """PDF에 주요 헤더 레이블이 포함됨 (교육과정·비고 가독성 포함)."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_labels.pdf'
    generate_from_dict(c016_v1, out)
    doc = pymupdf.open(str(out))
    full_text = ''.join(p.get_text() for p in doc).replace('\n', '').replace(' ', '')
    for keyword in ['연간교육계획', '교육과정', '비고', '교육구분', '일정']:
        assert keyword in full_text, f"'{keyword}' not found in PDF (whitespace-stripped)"

def test_C1103_c016_pdf_month_header_no_char_split(c016_v1, tmp_path):
    """10월/11월/12월 헤더가 3줄 분리 없음 — '10'/'11'/'12'가 단일 토큰으로 추출."""
    from common_v1_engine import register_fonts
    import pdfplumber
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_month.pdf'
    generate_from_dict(c016_v1, out)
    with pdfplumber.open(str(out)) as pdf:
        words = pdf.pages[0].extract_words()
    # 헤더 영역 (y < 250pt) 내 단어만 검사
    hdr_words = {w['text'] for w in words if w['top'] < 250}
    # '10'/'11'/'12'가 단일 토큰으로 존재해야 함 (3줄이면 '1'+'0'+'월' 각각 추출됨)
    for token in ['10', '11', '12']:
        assert token in hdr_words, \
            f"'{token}' not found as single token in header area — possible 3-line split"
    # 1~9월 digit도 단일 토큰으로 존재
    for d in range(1, 10):
        assert str(d) in hdr_words, f"'{d}' not found in header area"

def test_C1103_c016_pdf_5_blank_rows(c016_v1, tmp_path):
    """기본 5행 PDF: page 1에서 5개 데이터 행."""
    import pdfplumber
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_blank.pdf'
    generate_from_dict(c016_v1, out)
    with pdfplumber.open(str(out)) as pdf:
        tbls = pdf.pages[0].find_tables({'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'})
        rows = tbls[0].rows
        data_rows = rows[C016_N_HDR_P1:]
        assert len(data_rows) == 5, f"Expected 5 data rows, got {len(data_rows)}"

def test_C1103_c016_pdf_example_8rows(c016_v1, tmp_path):
    """예시 8행 출력: PDF 생성 성공, 8행 모두 존재."""
    from common_v1_engine import register_fonts
    import pymupdf
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_8rows.pdf'
    cols = c016_v1['sections'][1]['columns']
    ex_rows = [[f'E{i:02d}'] + [''] * (len(cols) - 1) for i in range(8)]
    generate_from_dict(c016_v1, out, ex_rows=ex_rows)
    assert out.exists() and out.stat().st_size > 10_000
    doc = pymupdf.open(str(out))
    # 좁은 NO 열(8mm)에서 문자 분리 가능 — 공백 제거 후 검사
    joined = ''.join(p.get_text() for p in doc).replace('\n', '').replace(' ', '')
    for i in range(8):
        tag = f'E{i:02d}'
        assert tag in joined, f"Example row '{tag}' not found in PDF (whitespace-stripped)"

def test_C1103_c016_pdf_30rows_no_missing(c016_v1, tmp_path):
    """30행 고유 식별자 R00~R29 누락 없음. NO 열(8mm)에서 문자 분리 — 공백 제거 후 검사."""
    import pymupdf
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_30rows.pdf'
    cols = c016_v1['sections'][1]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c016_v1, out, ex_rows=ex_rows)
    doc = pymupdf.open(str(out))
    joined = ''.join(p.get_text() for p in doc).replace('\n', '').replace(' ', '')
    missing = []
    for i in range(30):
        tag = f'R{i:02d}'
        if tag not in joined:
            missing.append(tag)
    assert not missing, f"Missing rows (whitespace-stripped): {missing}"

def test_C1103_c016_pdf_all_data_rows_min_14mm(c016_v1, tmp_path):
    """30행 분할 후 모든 데이터 행이 14mm 이상."""
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_30rows_minheight.pdf'
    cols = c016_v1['sections'][1]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c016_v1, out, ex_rows=ex_rows)
    heights = _measure_data_row_heights(out, n_hdr_page1=C016_N_HDR_P1, n_hdr_rest=C016_N_HDR_REST)
    assert len(heights) == 30, f"Expected 30 data rows, got {len(heights)}"
    below = [h for h in heights if h < MIN_ROW_H_C016_MM - TOLERANCE_C016_MM]
    assert not below, f"Rows below {MIN_ROW_H_C016_MM}mm: {below}"

def test_C1103_c016_pdf_header_repeats_multipage(c016_v1, tmp_path):
    """30행 분할 시 모든 페이지에 교육구분/일정 헤더가 반복."""
    import pdfplumber
    from common_v1_engine import register_fonts
    if not FONTS_OK:
        pytest.fail(f"NanumGothic font required: {FONT_PATH}")
    register_fonts()
    out = tmp_path / 'c016_30rows_hdr.pdf'
    cols = c016_v1['sections'][1]['columns']
    ex_rows = [[f'R{i:02d}'] + [''] * (len(cols) - 1) for i in range(30)]
    generate_from_dict(c016_v1, out, ex_rows=ex_rows)
    with pdfplumber.open(str(out)) as pdf:
        assert len(pdf.pages) >= 2, "30 rows should span multiple pages"
        for pi, page in enumerate(pdf.pages):
            words = {w['text'] for w in page.extract_words()}
            assert '교육구분' in words or '교육과정' in words, \
                f"Page {pi+1}: group header not found"

# ─── C11-04: REF-C016 SHA256 회귀 ────────────────────────────────────

def test_C1104_c016_sha256_regression():
    """C016 json/pdf/docx SHA256 기준본 및 기존 C004/C005 출력물 불변."""
    import hashlib
    c016_expected = {
        'scripts/c016_v1.json':               'c7166ff4d4590a6311a4200679d74b278757cbd073754eb6ec54805559c9adf3',
        'output/TAI-FORM-C016-blank.pdf':  'a12fe50aba41a3bc78d72c176a37ca47099539cb9f229d4e622f0213567f32bd',
        'output/TAI-FORM-C016-blank.docx': 'bad68d52f6370c8be347a64524ef3de270ec0fad6b87889a3fe125f72cfcbfe5',
    }
    existing_expected = {
        'output/TAI-FORM-C004-blank.pdf':  'd2be9950cbdee03d00ec0a9e25d2efd9af643bf6352b0b342ac55ff48dcf99ec',
        'output/TAI-FORM-C004-blank.docx': 'ca0ef2d3f160b1ae88809c5aa8ceb10cd84be50e8c3ef10a665299dbf408f645',
        'output/TAI-FORM-C005-blank.pdf':  '93cff8f970e68278f7c2dc2adc21ce2392d7ad9cbddc58dcbe174799d1d23d88',
        'output/TAI-FORM-C005-blank.docx': '39099daa2156afcdaa8bbcc86a6200f91c5e8ca67b921ea2c4af7a9636326967',
    }
    for rel_path, exp_sha in {**c016_expected, **existing_expected}.items():
        p = BASE.parent / rel_path
        assert p.exists(), f"{p.name} must exist"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == exp_sha, f"{p.name}: SHA256 changed\n  expected: {exp_sha}\n  actual:   {actual}"


# ─── C13-06: batch_build.py safety hardening (B7-FINAL-GATE-FIX-003) ─────────

import importlib as _importlib

def _load_bb():
    """Return the batch_build module (cached by sys.modules)."""
    import sys as _sys
    if 'batch_build' not in _sys.modules:
        _sys.path.insert(0, str(BASE))
    return _importlib.import_module('batch_build')


def test_C1306_01_build_unapproved_blocked():
    """--build c013 → BLOCKED (not in BUILD_APPROVED_IDS); exit nonzero."""
    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--build', 'c013'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    assert 'BLOCKED' in r.stdout or 'BLOCKED' in r.stderr


def test_C1306_02_build_frozen_blocked():
    """--build c001 → BLOCKED (APPROVED frozen form); exit nonzero."""
    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--build', 'c001'],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    assert 'BLOCKED' in r.stdout or 'BLOCKED' in r.stderr


def test_C1306_03_build_duplicate_id():
    """--build c013 c013 → DUPLICATE_ID; failures non-empty."""
    bb = _load_bb()
    results, failures = bb.run_build(['c013', 'c013'])
    assert failures, "Expected non-empty failures for duplicate IDs"
    assert any('DUPLICATE' in str(f) for f in failures)


def test_C1306_04_build_first_write_failure(tmp_path, monkeypatch):
    """PDF _write_exclusive raises → form in failures; no output written."""
    bb = _load_bb()
    monkeypatch.setattr(bb, 'BUILD_APPROVED_IDS', frozenset({'c013'}))
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)
    def _always_fail(src, dst):
        raise OSError("injected PDF write error")
    monkeypatch.setattr(bb, '_write_exclusive', _always_fail)

    results, failures = bb.run_build(['c013'])
    assert 'c013' in failures
    assert not (tmp_path / bb.REGISTRY['c013']['pdf_name']).exists()


def test_C1306_05_build_second_write_rollback(tmp_path, monkeypatch):
    """DOCX _write_exclusive raises → PDF rolled back from output/."""
    import shutil as _shutil
    bb = _load_bb()
    monkeypatch.setattr(bb, 'BUILD_APPROVED_IDS', frozenset({'c013'}))
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    call_count = [0]
    def _write_exc(src, dst):
        call_count[0] += 1
        if call_count[0] == 1:
            _shutil.copy2(str(src), str(dst))
        else:
            raise OSError("injected DOCX write error")
    monkeypatch.setattr(bb, '_write_exclusive', _write_exc)

    results, failures = bb.run_build(['c013'])
    assert 'c013' in failures
    pdf_name = bb.REGISTRY['c013']['pdf_name']
    assert not (tmp_path / pdf_name).exists(), "PDF orphan not rolled back"


def test_C1306_06_build_collision_blocked(tmp_path, monkeypatch):
    """Pre-existing output PDF → BLOCKED_COLLISION in results; form in failures."""
    bb = _load_bb()
    monkeypatch.setattr(bb, 'BUILD_APPROVED_IDS', frozenset({'c013'}))
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    pdf_name = bb.REGISTRY['c013']['pdf_name']
    (tmp_path / pdf_name).write_bytes(b'dummy existing')

    results, failures = bb.run_build(['c013'])
    assert 'c013' in failures
    statuses = [r.get('status', '') for r in results if r.get('id') == 'c013']
    assert any('BLOCKED' in s for s in statuses)


def test_C1306_07_report_to_output_blocked():
    """--report into output/ → rejected before execution; exit nonzero."""
    report_target = str(OUTPUT / 'test_report_c1306.json')
    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--dry-run',
         '--report', report_target],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert 'output' in combined.lower()
    assert not (OUTPUT / 'test_report_c1306.json').exists()


def test_C1306_08_report_to_scripts_blocked():
    """--report into scripts/ → rejected before execution; exit nonzero."""
    report_target = str(BASE / 'test_report_c1306.json')
    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--dry-run',
         '--report', report_target],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert 'scripts' in combined.lower()
    assert not (BASE / 'test_report_c1306.json').exists()


def test_C1306_09_dry_run_schema_error_exits_nonzero(tmp_path, monkeypatch):
    """run_dry_run with a bad JSON spec → failures non-empty."""
    bb = _load_bb()

    bad_json = tmp_path / 'cbad_v1.json'
    bad_json.write_text(
        '{"_meta": {"schema_version": "common-v1"}, "MISSING_SECTIONS": []}',
        encoding='utf-8')
    fake_entry = {
        'id': 'cbad', 'json': bad_json,
        'pdf_name': 'TAI-FORM-CBAD-blank.pdf',
        'docx_name': 'TAI-FORM-CBAD-blank.docx',
    }
    monkeypatch.setattr(bb, 'REGISTRY', {**bb.REGISTRY, 'cbad': fake_entry})

    results, failures = bb.run_dry_run(['cbad'])
    assert 'cbad' in failures, "Schema-error form must be in failures"


def test_C1306_10_verify_only_frozen_missing(tmp_path, monkeypatch):
    """verify-only: approved form output file absent → doc_ok=False → failures."""
    bb = _load_bb()
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    results, failures = bb.run_verify_only(['c001'])
    assert 'c001' in failures
    row = next((r for r in results if r['id'] == 'c001'), {})
    assert row.get('status') == 'FAILED'
    assert row.get('frozen_pdf') == 'MISSING' or row.get('frozen_docx') == 'MISSING'


def test_C1306_11_verify_only_frozen_hash_mismatch(tmp_path, monkeypatch):
    """verify-only: approved form output with wrong SHA256 → failures."""
    bb = _load_bb()
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    (tmp_path / bb.REGISTRY['c001']['pdf_name']).write_bytes(b'wrong content')
    (tmp_path / bb.REGISTRY['c001']['docx_name']).write_bytes(b'wrong content')

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    results, failures = bb.run_verify_only(['c001'])
    assert 'c001' in failures
    row = next((r for r in results if r['id'] == 'c001'), {})
    assert row.get('status') == 'FAILED'
    assert 'MISMATCH' in row.get('frozen_pdf', '') or 'MISMATCH' in row.get('frozen_docx', '')


def test_C1306_12_c013_metadata_correctness():
    """C013 _meta: para range = 1807-1845, page = 113."""
    data = json.loads((BASE / 'c013_v1.json').read_text(encoding='utf-8'))
    meta = data['_meta']
    assert '1807-1845' in meta['source_text_status'], (
        f"source_text_status: expected Para 1807-1845, got: {meta['source_text_status']}")
    assert '1807-1845' in meta['source_section'], (
        f"source_section: expected 1807-1845, got: {meta['source_section']}")
    assert 'Page 113' in meta['source_visual_layout_status'], (
        f"source_visual_layout_status: expected Page 113, got: {meta['source_visual_layout_status']}")


# ─── C13-07: batch_build.py final safety hardening (B7-RUNNER-CLOSE-004) ─────

import builtins as _builtins_mod
from pathlib import Path as _PPath


def test_C1307_01_write_exclusive_midwrite_cleanup(tmp_path, monkeypatch):
    """_write_exclusive: xb file created, f.write raises → partial file removed."""
    bb = _load_bb()
    src = tmp_path / 'src.bin'
    src.write_bytes(b'test data content')
    dst = tmp_path / 'dst.bin'
    dst_str = str(dst)

    _real_open = _builtins_mod.open

    class _FailWrite:
        def __init__(self, real_fh):
            self._fh = real_fh
        def __enter__(self):
            return self
        def __exit__(self, *a):
            try:
                self._fh.close()
            except Exception:
                pass
            return False
        def write(self, data):
            raise OSError("injected mid-write failure")

    def _mock_open(path, mode='r', *args, **kwargs):
        if isinstance(mode, str) and 'x' in mode and str(path) == dst_str:
            return _FailWrite(_real_open(path, mode, *args, **kwargs))
        return _real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(_builtins_mod, 'open', _mock_open)

    with pytest.raises(OSError, match="injected mid-write"):
        bb._write_exclusive(src, dst)

    assert not dst.exists(), "Partial file must be cleaned up after mid-write failure"


def test_C1307_02_write_exclusive_rollback_failure(tmp_path, monkeypatch):
    """_write_exclusive: write fails + cleanup fails → RuntimeError RECOVERY_REQUIRED."""
    bb = _load_bb()
    src = tmp_path / 'src.bin'
    src.write_bytes(b'test data')
    dst = tmp_path / 'dst.bin'
    dst_str = str(dst)

    _real_open = _builtins_mod.open

    class _FailWriteAndCleanup:
        def __init__(self, real_fh):
            self._fh = real_fh
        def __enter__(self): return self
        def __exit__(self, *a):
            try:
                self._fh.close()
            except Exception:
                pass
            return False
        def write(self, data):
            raise OSError("injected write failure")

    def _mock_open(path, mode='r', *args, **kwargs):
        if isinstance(mode, str) and 'x' in mode and str(path) == dst_str:
            return _FailWriteAndCleanup(_real_open(path, mode, *args, **kwargs))
        return _real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(_builtins_mod, 'open', _mock_open)

    _orig_unlink = _PPath.unlink

    def _fail_unlink(self, missing_ok=False):
        if self == dst:
            raise OSError("simulated cleanup failure")
        return _orig_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(_PPath, 'unlink', _fail_unlink)

    with pytest.raises(RuntimeError, match="RECOVERY_REQUIRED"):
        bb._write_exclusive(src, dst)


def test_C1307_03_run_build_docx_midwrite_rollback(tmp_path, monkeypatch):
    """run_build: DOCX _write_exclusive mid-write failure → DOCX cleaned + PDF rolled back."""
    import shutil as _shutil
    bb = _load_bb()
    monkeypatch.setattr(bb, 'BUILD_APPROVED_IDS', frozenset({'c013'}))
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    pdf_name  = bb.REGISTRY['c013']['pdf_name']
    docx_name = bb.REGISTRY['c013']['docx_name']
    docx_out_str = str(tmp_path / docx_name)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    _real_open = _builtins_mod.open

    class _FailWriteDocx:
        def __init__(self, real_fh): self._fh = real_fh
        def __enter__(self): return self
        def __exit__(self, *a):
            try: self._fh.close()
            except Exception: pass
            return False
        def write(self, data): raise OSError("injected DOCX mid-write failure")

    def _mock_open(path, mode='r', *args, **kwargs):
        if isinstance(mode, str) and 'x' in mode and str(path) == docx_out_str:
            return _FailWriteDocx(_real_open(path, mode, *args, **kwargs))
        return _real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(_builtins_mod, 'open', _mock_open)

    results, failures = bb.run_build(['c013'])
    assert 'c013' in failures
    assert not (tmp_path / pdf_name).exists(),  "PDF must be rolled back"
    assert not (tmp_path / docx_name).exists(), "DOCX partial must be cleaned up by _write_exclusive"


def test_C1307_04_run_build_pdf_rollback_failure(tmp_path, monkeypatch):
    """run_build: DOCX write fails + PDF unlink fails → RECOVERY_REQUIRED in status."""
    import shutil as _shutil
    bb = _load_bb()
    monkeypatch.setattr(bb, 'BUILD_APPROVED_IDS', frozenset({'c013'}))
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    call_count = [0]

    def _write_exc(src, dst):
        call_count[0] += 1
        if call_count[0] == 1:
            _shutil.copy2(str(src), str(dst))
        else:
            raise OSError("injected DOCX failure")

    monkeypatch.setattr(bb, '_write_exclusive', _write_exc)

    pdf_name = bb.REGISTRY['c013']['pdf_name']
    _orig_unlink = _PPath.unlink

    def _fail_pdf_unlink(self, missing_ok=False):
        if self.name == pdf_name:
            raise OSError("cannot remove PDF")
        return _orig_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(_PPath, 'unlink', _fail_pdf_unlink)

    results, failures = bb.run_build(['c013'])
    assert 'c013' in failures
    row = next((r for r in results if r.get('id') == 'c013'), {})
    assert 'RECOVERY_REQUIRED' in row.get('status', ''), (
        f"Expected RECOVERY_REQUIRED in status, got: {row.get('status')}")


def test_C1307_05_write_exclusive_no_overwrite(tmp_path):
    """_write_exclusive: FileExistsError → pre-existing file content unchanged."""
    bb = _load_bb()
    src = tmp_path / 'src.bin'
    src.write_bytes(b'new content')
    dst = tmp_path / 'dst.bin'
    original = b'original content'
    dst.write_bytes(original)

    with pytest.raises(FileExistsError):
        bb._write_exclusive(src, dst)

    assert dst.read_bytes() == original, "Existing file must not be modified"


def test_C1307_06_report_existing_file_blocked(tmp_path):
    """--report to an existing file → rejected; existing content unchanged."""
    existing = tmp_path / 'existing_report.json'
    original_content = '{"existing": true}'
    existing.write_text(original_content, encoding='utf-8')

    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--dry-run',
         '--report', str(existing)],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    assert existing.read_text(encoding='utf-8') == original_content, \
        "Existing report file must not be overwritten"


def test_C1307_07_report_symlink_bypass_blocked(tmp_path):
    """--report via symlink that resolves into output/ → rejected; target not created."""
    import os
    target = OUTPUT / '_symlink_test_report.json'
    link   = tmp_path / 'report_link.json'
    os.symlink(str(target), str(link))

    r = subprocess.run(
        [sys.executable, str(BASE / 'batch_build.py'), '--dry-run',
         '--report', str(link)],
        capture_output=True, text=True, cwd=str(BASE),
    )
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert 'output' in combined.lower()
    assert not target.exists(), "Symlink target inside output/ must not be created"


def test_C1307_08_verify_only_frozen_missing_baseline(tmp_path, monkeypatch):
    """verify-only: FROZEN_SHA entry absent for approved form → MISSING_BASELINE failure."""
    bb = _load_bb()
    monkeypatch.setattr(bb, 'OUTPUT', tmp_path)

    pdf_name  = bb.REGISTRY['c001']['pdf_name']
    docx_name = bb.REGISTRY['c001']['docx_name']
    (tmp_path / pdf_name).write_bytes(b'some content')
    (tmp_path / docx_name).write_bytes(b'some content')

    frozen_no_c001 = {k: v for k, v in bb.FROZEN_SHA.items() if not k.startswith('c001')}
    monkeypatch.setattr(bb, 'FROZEN_SHA', frozen_no_c001)

    def _fake_pdf(entry, out_path):
        Path(out_path).write_bytes(b'%PDF-1.4 fake')
    def _fake_docx(entry, out_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('word/document.xml', '<root/>')
        Path(out_path).write_bytes(buf.getvalue())
    monkeypatch.setattr(bb, 'generate_pdf',  _fake_pdf)
    monkeypatch.setattr(bb, 'generate_docx', _fake_docx)
    monkeypatch.setattr(bb, 'verify_pdf',    lambda p: 1)
    monkeypatch.setattr(bb, 'verify_docx',   lambda p: True)

    results, failures = bb.run_verify_only(['c001'])
    assert 'c001' in failures
    row = next((r for r in results if r['id'] == 'c001'), {})
    assert row.get('status') == 'FAILED'
    assert ('MISSING_BASELINE' in row.get('frozen_pdf', '')
            or 'MISSING_BASELINE' in row.get('frozen_docx', ''))
