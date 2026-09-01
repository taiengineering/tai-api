"""SaaS Core — 인증·사용자·회사·시설·기본설정 라우터."""
ROUTERS = [
    {"module": "routers.auth"},
    # GET /users/roles 가 users.GET /{user_id} 에 잡히지 않도록 users 보다 먼저 등록
    {"module": "routers.role_menu_permissions", "prefix": "", "tags": ["role-menu-permissions"]},
    {"module": "routers.role_permissions", "prefix": "", "tags": ["role-permissions"]},
    {"module": "routers.menus", "prefix": "", "tags": ["menus"]},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.customer360"},  # WO-6 고객360 통합 집계 (GET /companies/{id}/360)
    {"module": "routers.onboarding_ops"},  # WO-17 온보딩 체크리스트 (GET /companies/{id}/onboarding)
    {"module": "routers.global_search"},  # WO-11 통합 교차검색 (GET /search)
    {"module": "routers.factories"},
    # WO-SAFE-LEGAL-IND-IMPLEMENT-001 STEP3: /factories/{id}/legal-diagnosis/profile (0-drift 확장)
    {"module": "routers.factory_legal_diagnosis"},
    {"module": "routers.system_codes"},
    # {"module": "routers.file_upload"},  # 모듈 삭제됨 — 필요 시 재생성
    {"module": "routers.notifications"},
    # LEDGER §32: 알럿 메시지 관리(system_alert_messages, role 001 전용). 구현돼 있었으나
    # 어느 ROUTERS 에도 등록되지 않아 /alert-messages 6개가 전부 404였음. 전역 시스템
    # 카탈로그이며 모든 변경 엔드포인트가 role_code=='001' 게이팅이라 회사 스코프 불필요.
    {"module": "routers.alert_messages"},
    {"module": "routers.onboarding"},
    # 조직 계층: 부서·팀·그룹·근로자배정 (TBM 팀·그룹 하이브리드 Phase 1)
    {"module": "routers.org"},
    # 작업자 조직배정 조회 (수정 패널 프리필: GET /worker-registry/{id}/org-assignment)
    {"module": "routers.worker_org"},
    # 공용 휴무 캘린더 — 캘린더를 쓰는 모든 기능이 공유 (org_holiday / holiday_svc)
    {"module": "routers.holidays"},
    # Phase 1: FacilityProfile (입력 보존·복원·감사)
    {"module": "routers.facility_profile_api"},
    # Phase 2+3: ApplicabilityCondition + Condition Scope Layer
    {"module": "routers.applicability_api"},
    # Phase 4: Real Facility Validation (배치 검증)
    {"module": "routers.validation_api"},
    # 고객응대 MVP 1단계: SaaS 회원 문의 저장 경로 + Question Context 보존 (POST /me/inquiries)
    {"module": "routers.member_inquiries"},
    # 고객응대 MVP: 질문 진입점 결선 (POST /me/support/ask — routing→answer→handoff)
    {"module": "routers.member_support"},
]
