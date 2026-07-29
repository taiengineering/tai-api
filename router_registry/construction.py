"""Construction & Safety — 건설안전·교육·장비·인력 라우터."""
ROUTERS = [
    {"module": "routers.construction", "prefix": "/construction", "tags": ["건설안전"]},
    {"module": "routers.subcontractors"},
    {"module": "routers.tbm"},
    {"module": "routers.tbm_templates"},
    {"module": "routers.safety_meetings"},
    {"module": "routers.risk_assessments"},
    {"module": "routers.ra_settings"},  # 위험성평가 설정(운영 파라미터·척도) /ra/*
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
