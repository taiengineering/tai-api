"""Runtime Bridge — Legacy→Runtime 전환 브릿지 라우터.

 엔진 의존. 엔진 실패 시 graceful degradation.
"""
ROUTERS = [
    {"module": "routers.legacy_freeze"},
    {"module": "routers.runtime_bridge"},
    {"module": "routers.inspection_bridge"},
    {"module": "routers.obligation_bridge"},
    {"module": "routers.my_inspection_bridge"},
    {"module": "routers.notification_bridge"},
    {"module": "routers.notification_engine_api"},
    {"module": "routers.notification_inbox_api"},
    {"module": "routers.notification_preference_api"},
    {"module": "routers.notification_wiring_api"},
    {"module": "routers.notification_digest_api"},
    {"module": "routers.workflow_alert_api"},
    {"module": "routers.workflow_engine_api"},
    {"module": "routers.review_bridge"},
    {"module": "routers.evidence_bridge"},
    {"module": "routers.submission_bridge"},
    # --- Runtime Projection Layer MVP ---
    {"module": "routers.runtime_task_api"},
    {"module": "routers.runtime_schedule_api"},
    {"module": "routers.legal_adapter_api"},
    {"module": "routers.runtime_cockpit_api"},
]
