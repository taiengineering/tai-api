"""Construction & Safety — 건설안전·교육·장비·인력 라우터."""
ROUTERS = [
    {"module": "routers.construction", "prefix": "/construction", "tags": ["건설안전"]},
    {"module": "routers.tbm"},
    {"module": "routers.tbm_templates"},
    {"module": "routers.safety_meetings"},
    {"module": "routers.risk_assessments"},
    {"module": "routers.worker_registry"},
    {"module": "routers.worker_check"},
    {"module": "routers.worker_home"},
    {"module": "routers.equipment_assets"},
    {"module": "routers.equipment_checkins"},
    {"module": "routers.engine_equipment"},
    {"module": "routers.engine_model"},
    {"module": "routers.education"},
    {"module": "routers.education_assign"},
    {"module": "routers.personnel"},
    {"module": "routers.safety_info"},
]
