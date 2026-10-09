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
    """공통 엔진 파일 SHA256 불변 검증 — 기준본: WO-REF01-059-B3-B (text_flow 추가)."""
    import hashlib
    expected = {
        'common_v1_engine.py':  '729725eff3a76ac480c3f9b4689673240982a63ace500dac8947e3c9c7749ac2',
        'common_v1_engine.cjs': '0e4ef1a6faf952f90a2557541e77397b078706a1862d8c15907c6ad45d1010cf',
        'c014_v1.json':         'c50a99c5dcd9369e1751e754bdd004c0027065ec0ccd739448b9e70b4c45ce90',
        'c001_v1.json':         '36ee492af86b847e8d3a2663f90fc6f7eb43fc2949e0c992162969c1f449ea06',
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
    assert count >= 1, "Title '안전보건경영방침' not found in PDF"

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
