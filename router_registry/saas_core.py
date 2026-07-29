"""SaaS Core — 인증·사용자·회사·시설·기본설정 라우터."""
ROUTERS = [
    {"module": "routers.auth"},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.customer360"},  # WO-6 고객360 통합 집계 (GET /companies/{id}/360)
    {"module": "routers.onboarding_ops"},  # WO-17 온보딩 체크리스트 (GET /companies/{id}/onboarding)
    {"module": "routers.global_search"},  # WO-11 통합 교차검색 (GET /search)
    {"module": "routers.factories"},
    {"module": "routers.system_codes"},
    # {"module": "routers.file_upload"},  # 모듈 삭제됨 — 필요 시 재생성
    {"module": "routers.notifications"},
    {"module": "routers.onboarding"},
    # 공용 휴무 캘린더 — 캘린더를 쓰는 모든 기능이 공유 (org_holiday / holiday_svc)
    {"module": "routers.holidays"},
    # Phase 1: FacilityProfile (입력 보존·복원·감사)
    {"module": "routers.facility_profile_api"},
    # Phase 2+3: ApplicabilityCondition + Condition Scope Layer
    {"module": "routers.applicability_api"},
    # Phase 4: Real Facility Validation (배치 검증)
    {"module": "routers.validation_api"},
]
