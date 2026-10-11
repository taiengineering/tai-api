"""
C002 flat JSON → common-v1 변환 어댑터 — WO-058 Phase C-01
C002 호환성 테스트 fixture용. c002_fields.json 또는 gen_c002_*.py 변경 없음.
"""

def adapt_c002_to_v1(flat):
    """
    c002_fields.json (flat) → common-v1 sections 형식.

    어댑터 주의사항:
    1. basic_info 표시 순서: [N01, N02, N04, N03]
       gen_c002_pdf.py build_basic_info()의 실제 렌더링 순서와 일치.
       (JSON 필드 순서 N01/N02/N03/N04 ≠ 렌더링 순서)
    2. freeform_area min_height_mm=20 — 기존 생성기의 ROW_H_GOAL=20mm 상수에 맞춤.
       (c002_fields.json corporate_goal.min_height_mm=22 와 불일치 — 기존 동작 보존)
    3. repeat_table columns[].width_mm — c002_fields.json에 이미 존재 → 그대로 사용.
    """
    bi_map = {f['id']: f for f in flat['basic_info']['fields']}
    appr   = flat['approval']
    cg     = flat['corporate_goal']
    pt     = flat['plan_table']

    return {
        '_meta': {
            'schema_version': 'common-v1',
            'form_type': 'PLAN',
            'source_id': 'REF-C002',
            'adapter': 'c002_v1_adapter',
        },
        'document': flat['document'],
        'sections': [
            {
                'type': 'approval',
                'total_width_mm': appr['total_width_mm'],
                'min_header_height_mm': 7,
                'min_sign_height_mm': appr['min_height_mm'],
                'fields': appr['fields'],
            },
            {
                'type': 'basic_info',
                'layout': '2col_2row',
                # N01(row0L) N02(row0R) N04(row1L) N03(row1R) — 기존 렌더링 순서 보존
                'fields': [
                    bi_map['N01'], bi_map['N02'],
                    bi_map['N04'], bi_map['N03'],
                ],
            },
            {
                'type': 'freeform_area',
                'id': cg['id'],
                'label': cg['label'],
                'min_height_mm': 20,  # 기존 ROW_H_GOAL=20mm 일치 (JSON 22mm 아님)
                'requiredness': 'UNVERIFIED',
            },
            {
                'type': 'repeat_table',
                'default_row_count': pt['default_row_count'],
                'extra_rows_note': pt.get('extra_rows_note', ''),
                'columns': pt['columns'],
            },
        ],
    }
