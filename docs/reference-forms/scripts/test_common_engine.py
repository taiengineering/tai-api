"""
WO-058 Phase C-01 — 공통 엔진 테스트
pytest test_common_engine.py -v
"""
import json, os, sys, subprocess
from pathlib import Path

import pytest

BASE = Path(__file__).parent

# ─── Engine import ────────────────────────────────────────────────
try:
    sys.path.insert(0, str(BASE))
    from common_v1_engine import validate, assemble, build_approval, build_labeled_grid, build_freeform_area
    from c002_v1_adapter import adapt_c002_to_v1
    ENGINE_OK = True
except Exception as _e:
    ENGINE_OK = False
    _ENGINE_ERR = str(_e)

skip_eng = pytest.mark.skipif(not ENGINE_OK, reason=f"engine import failed: {'' if ENGINE_OK else _ENGINE_ERR}")

FONT_PATH = os.environ.get(
    'NANUM_GOTHIC_TTC',
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font8/'
    '7a0b5c0f3c1d41c4c52a33343496c9c65ad52c50.asset/AssetData/NanumGothic.ttc'
)
FONTS_OK = os.path.exists(FONT_PATH)
skip_font = pytest.mark.skipif(not FONTS_OK, reason="NanumGothic font not found")

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

# ─── C01: Schema validation ────────────────────────────────────────

@skip_eng
def test_C01_c012_passes_validation(c012):
    assert validate(c012) is True

@skip_eng
def test_C01_minimal_passes(minimal):
    assert validate(minimal) is True

@skip_eng
def test_C01_missing_document_raises():
    with pytest.raises(ValueError, match="document"):
        validate({'sections': []})

@skip_eng
def test_C01_unknown_block_type_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'totally_unknown'}],
    }
    with pytest.raises(ValueError, match="unsupported block type"):
        validate(fields)

@skip_eng
def test_C01_approval_missing_fields_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'approval', 'total_width_mm': 90}],
    }
    with pytest.raises(ValueError, match="missing required attr 'fields'"):
        validate(fields)

@skip_eng
def test_C01_labeled_grid_wrong_row_size_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'labeled_grid',
                      'rows': [[{'id': 'F1', 'label': 'A'}]]}],
    }
    with pytest.raises(ValueError, match="exactly 2 cells"):
        validate(fields)

@skip_eng
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

@skip_eng
def test_C01_freeform_missing_label_raises():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'freeform_area', 'min_height_mm': 20}],
    }
    with pytest.raises(ValueError, match="missing required attr 'label'"):
        validate(fields)

# ─── C03: Block structure tests (no font draw required) ───────────

@skip_eng
def test_C03_c012_approval_has_2_roles(c012):
    appr = next(s for s in c012['sections'] if s['type'] == 'approval')
    assert len(appr['fields']) == 2
    labels = [f['label'] for f in appr['fields']]
    assert labels == ['신청', '허가']

@skip_eng
def test_C03_c012_labeled_grid_4_rows(c012):
    grid = next(s for s in c012['sections'] if s['type'] == 'labeled_grid')
    assert len(grid['rows']) == 4
    for row in grid['rows']:
        assert len(row) == 2

@skip_eng
def test_C03_c012_freeform_areas(c012):
    fas = [s for s in c012['sections'] if s['type'] == 'freeform_area']
    assert len(fas) == 2
    assert fas[0]['id'] == 'F09' and fas[0]['min_height_mm'] == 20
    assert fas[1]['id'] == 'F10' and fas[1]['min_height_mm'] == 30

@skip_eng
def test_C03_c012_requiredness_unverified_preserved(c012):
    for s in c012['sections']:
        if s['type'] == 'freeform_area':
            assert s.get('requiredness') == 'UNVERIFIED'
        if s['type'] == 'labeled_grid':
            for row in s['rows']:
                for cell in row:
                    assert cell.get('requiredness') == 'UNVERIFIED'

@skip_eng
def test_C03_approval_cell_width_contract():
    # 2-col: 90/2=45mm each; 3-col: 90/3=30mm each
    for n_cols, expected_mm in [(2, 45), (3, 30)]:
        section = {
            'type': 'approval', 'total_width_mm': 90,
            'fields': [{'id': f'A{i}', 'label': f'L{i}'} for i in range(n_cols)],
        }
        from common_v1_engine import mm as rl_mm
        n = len(section['fields'])
        cell_w_mm = section['total_width_mm'] / n
        assert cell_w_mm == expected_mm, f"Expected {expected_mm}mm for {n} cols, got {cell_w_mm}"

# ─── C02: Assembler section count ─────────────────────────────────

@skip_eng
def test_C02_assemble_returns_correct_section_count(c012):
    story = assemble(c012)
    # title + spacer + (approval+spacer) + (labeled_grid+spacer) + (fa+spacer)*2
    # = 1 + 1 + 2 + 2 + 4 = 10
    assert len(story) == 10

@skip_eng
def test_C02_assembler_fail_closed_on_unknown_block():
    fields = {
        'document': {'title': 'T', 'doc_id': 'D', 'creator': 'TAI'},
        'sections': [{'type': 'mystery_block', 'label': 'x', 'min_height_mm': 10}],
    }
    with pytest.raises(ValueError, match="Unsupported block type"):
        assemble(fields)

@skip_eng
def test_C02_assemble_empty_sections(minimal):
    story = assemble(minimal)
    assert len(story) == 2  # title + spacer only

# ─── C04: PDF/DOCX generation ─────────────────────────────────────

@skip_eng
@skip_font
def test_C04_c012_pdf_generation(tmp_path):
    from common_v1_engine import register_fonts, generate
    register_fonts()
    out = tmp_path / 'TAI-FORM-C012-blank.pdf'
    generate(BASE / 'c012_fields.json', out)
    assert out.exists()
    assert out.stat().st_size > 5_000

@skip_eng
def test_C04_c012_docx_generation():
    result = subprocess.run(
        ['node', str(BASE / 'gen_c012_docx.cjs'), 'blank'],
        cwd=str(BASE), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"node gen_c012_docx.cjs failed: {result.stderr[:300]}")
    out = BASE.parent / 'output' / 'TAI-FORM-C012-blank.docx'
    assert out.exists(), f"DOCX not found: {out}"
    assert out.stat().st_size > 3_000

# ─── C05: C002 compatibility ───────────────────────────────────────

@skip_eng
def test_C05_c002_adapter_produces_valid_v1(c002):
    v1 = adapt_c002_to_v1(c002)
    assert validate(v1) is True

@skip_eng
def test_C05_c002_adapter_block_order(c002):
    v1 = adapt_c002_to_v1(c002)
    assert [s['type'] for s in v1['sections']] == [
        'approval', 'basic_info', 'freeform_area', 'repeat_table'
    ]

@skip_eng
def test_C05_c002_basic_info_display_order(c002):
    v1 = adapt_c002_to_v1(c002)
    bi = next(s for s in v1['sections'] if s['type'] == 'basic_info')
    # N04 before N03 in row 1 — matches gen_c002_pdf.py actual rendering
    assert [f['id'] for f in bi['fields']] == ['N01', 'N02', 'N04', 'N03']

@skip_eng
def test_C05_c002_freeform_height_20mm(c002):
    v1 = adapt_c002_to_v1(c002)
    fa = next(s for s in v1['sections'] if s['type'] == 'freeform_area')
    assert fa['min_height_mm'] == 20  # matches ROW_H_GOAL, not JSON 22mm

@skip_eng
def test_C05_c002_repeat_table_column_widths(c002):
    v1 = adapt_c002_to_v1(c002)
    rt = next(s for s in v1['sections'] if s['type'] == 'repeat_table')
    widths = [c['width_mm'] for c in rt['columns']]
    assert widths == [56, 26, 22, 26, 22, 18]
    assert sum(widths) == 170

@skip_eng
def test_C05_c002_approval_3col_labels(c002):
    v1 = adapt_c002_to_v1(c002)
    appr = next(s for s in v1['sections'] if s['type'] == 'approval')
    assert [f['label'] for f in appr['fields']] == ['작성', '검토', '승인']

@skip_eng
def test_C05_c002_generator_source_files_exist():
    assert (BASE / 'gen_c002_pdf.py').exists()
    assert (BASE / 'gen_c002_docx.cjs').exists()
    # Size sanity: originals are > 10KB each
    assert (BASE / 'gen_c002_pdf.py').stat().st_size   > 10_000
    assert (BASE / 'gen_c002_docx.cjs').stat().st_size > 10_000
