"""
JSON → xlsx-ready normalized form spec.
Handles common-v1 (pass-through) and REF-C002 legacy format.
"""
import json
import os

_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'scripts')
)


def _json_path(research_id: str) -> str:
    name = research_id.lower()
    if name.startswith('ref-c'):
        cnum = name[5:]
        fields_path = os.path.join(_SCRIPTS_DIR, f'c{cnum}_fields.json')
        if os.path.exists(fields_path):
            return fields_path
        return os.path.join(_SCRIPTS_DIR, f'c{cnum}_v1.json')
    return os.path.join(_SCRIPTS_DIR, f'{name}_v1.json')


def load_form_spec(research_id: str) -> dict:
    path = _json_path(research_id)
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    if 'plan_table' in raw and 'corporate_goal' in raw:
        return _adapt_c002(raw, research_id)
    return raw


def _adapt_c002(flat: dict, research_id: str) -> dict:
    bi_map = {f['id']: f for f in flat['basic_info']['fields']}
    appr = flat['approval']
    cg = flat['corporate_goal']
    pt = flat['plan_table']
    return {
        '_meta': {
            'schema_version': 'common-v1',
            'form_type': 'PLAN',
            'source_id': research_id,
            'adapter': 'xlsx_schema_adapter',
        },
        'document': flat['document'],
        'sections': [
            {
                'type': 'approval',
                'total_width_mm': appr.get('total_width_mm', 90),
                'fields': appr['fields'],
            },
            {
                'type': 'basic_info',
                'fields': [
                    bi_map['N01'], bi_map['N02'],
                    bi_map['N04'], bi_map['N03'],
                ],
            },
            {
                'type': 'freeform_area',
                'id': cg['id'],
                'label': cg['label'],
                'min_height_mm': 20,
            },
            {
                'type': 'repeat_table',
                'default_row_count': pt.get('default_row_count', 10),
                'columns': pt['columns'],
            },
        ],
    }
