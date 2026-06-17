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
    # Phase 2: ApplicabilityCondition 파일럿 (안전관리자 선임 7건)
    {"module": "routers.applicability_api"},
]
