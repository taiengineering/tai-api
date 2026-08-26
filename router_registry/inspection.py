"""Inspection — 점검·일정·체크리스트·공정·법령상태 라우터."""
ROUTERS = [
    {"module": "routers.inspection_sets"},
    {"module": "routers.inspection_set_items"},
    {"module": "routers.inspection_schedule"},
    {"module": "routers.inspection_checklist"},
    {"module": "routers.inspection_view"},
    {"module": "routers.inspection_setup"},
    {"module": "routers.work_schedules"},
    {"module": "routers.schedule_engine"},
    {"module": "routers.schedule_pipeline"},
    {"module": "routers.overdue_checker"},
    {"module": "routers.safety_template"},
    {"module": "routers.corrective_actions"},
    {"module": "routers.factory_process_v3"},
    {"module": "routers.legal_status_api"},
]
