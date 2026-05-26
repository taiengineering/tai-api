"""Legal Engine — 법령엔진 전용 라우터.

격리 필수: 이 그룹 실패해도 SaaS Core 정상 작동.
"""
ROUTERS = [
    {"module": "routers.legal_engine"},
    {"module": "routers.legal_engine_patch"},
    {"module": "routers.engine_qa"},
    {"module": "routers.law_rule_generator"},
    {"module": "routers.engine_legal"},
    # {"module": "routers.law_collector"},  # _get_cfg import 오류 — messaging.py 리팩토링 후 복원
    {"module": "routers.byulpyo"},
    {"module": "routers.compiler_core"},
    {"module": "routers.residual_intelligence"},
    {"module": "routers.legal_intake"},
    {"module": "routers.legal_diff"},
    {"module": "routers.deterministic_qa"},
    {"module": "routers.engine_publish"},
    {"module": "routers.integrity_monitor"},
    {"module": "routers.engine_monitoring"},
    {"module": "routers.runtime_activation"},
    {"module": "routers.runtime_chaos"},
    {"module": "routers.persistence_api"},
    {"module": "routers.runtime_evaluator_api"},
    {"module": "routers.simulation_api"},
]
