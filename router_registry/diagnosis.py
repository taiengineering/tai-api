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
    # WO-ISOLATE-001: 축2 LEG standalone 격리 (E2E 검증 전용, tai-www 미연결).
    #   LEG_PIPELINE_ENABLED=true 로 인프라는 살아있으나 라이브 컷오버 전까지 URL 격리.
    #   컷오버 시 아래 두 줄 주석 해제로 부활. 파일·서비스·클라이언트 모두 보존.
    # {"module": "routers.anonymous_diagnosis_leg"},  # WO-PIPE-004: LEG standalone endpoint
    # {"module": "routers.diagnosis_integrated_leg"},  # WO-PIPE-004(paid): LEG standalone paid endpoint
]
