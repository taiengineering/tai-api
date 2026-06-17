"""SaaS Core — 인증·사용자·회사·시설·기본설정 라우터."""
ROUTERS = [
    {"module": "routers.auth"},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.factories"},
    {"module": "routers.system_codes"},
    # {"module": "routers.file_upload"},  # 모듈 삭제됨 — 필요 시 재생성
    {"module": "routers.notifications"},
    {"module": "routers.onboarding"},
    # Phase 1: FacilityProfile (입력 보존·복원·감사)
    {"module": "routers.facility_profile_api"},
    # Phase 2+3: ApplicabilityCondition + Condition Scope Layer
    {"module": "routers.applicability_api"},
    # Phase 4: Real Facility Validation (배치 검증)
    {"module": "routers.validation_api"},
]
