"""Diagnosis — 법령진단 서비스 라우터."""
ROUTERS = [
    {"module": "routers.diagnosis"},
    {"module": "routers.diagnosis_engine"},
    {"module": "routers.diagnosis_integrated"},
    {"module": "routers.diagnosis_autofill"},
    {"module": "routers.diagnosis_fields"},
    {"module": "routers.exists_input_api"},
    {"module": "routers.diagnosis_report"},
    {"module": "routers.diagnosis_proposal"},
    {"module": "routers.diagnosis_roi"},
    {"module": "routers.diagnosis_transform"},
    {"module": "routers.diagnosis_plan_recommend"},
    {"module": "routers.diagnosis_result_web"},
    {"module": "routers.diagnosis_runtime_projection"},
    {"module": "routers.diagnosis_factory_test"},
    {"module": "routers.obligation_adapter"},
    {"module": "routers.trigger_diagnosis"},
    {"module": "routers.saas_setup"},
    # WO-CUTOVER-PIPELINE-001: 축2 LEG standalone 컷오버 — WO-ISOLATE-001 격리 해제.
    #   DEFINITION_consumer_pipeline_v1 이 규정한 Consumer Entry 를 운영 배선에 연결한다.
    {"module": "routers.anonymous_diagnosis_leg"},  # WO-PIPE-004: LEG standalone endpoint
    {"module": "routers.diagnosis_integrated_leg"},  # WO-PIPE-004(paid): LEG standalone paid endpoint
]
