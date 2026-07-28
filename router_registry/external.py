"""External & Communication — 외부API·메시징·매칭·어드민 라우터."""
ROUTERS = [
    {"module": "routers.weather"},
    {"module": "routers.juso"},
    {"module": "routers.building_register", "prefix": "/building-register"},
    {"module": "routers.biz_verify"},
    {"module": "routers.kosha_apis"},
    {"module": "routers.messaging"},
    {"module": "routers.fcm"},
    {"module": "routers.mail"},
    {"module": "routers.gmail_inbox"},  # WO-8B Gmail 수신 폴링 (POST /mail/pull)
    {"module": "routers.notify"},       # WO-8C 통합 발송 (POST /notify/send, /notify/dry-run)
    {"module": "routers.integration_health"},  # WO-10 연동 관제 (GET /integrations/health, POST /probe)
    {"module": "routers.automation"},   # WO-12 운영 자동화 (/automation/*)
    {"module": "routers.ops_home"},     # WO-13 관제홈 (GET /ops/home)
    {"module": "routers.stats_provider"},  # WO-14 경영 지표 (GET /stats/business)
    {"module": "routers.ai_copywrite"},
    {"module": "routers.event_trigger"},
    {"module": "routers.repair"},
    {"module": "routers.fix_chat"},
    {"module": "routers.fix_providers_api"},
    {"module": "routers.matching", "prefix": "/matching", "tags": ["매칭"]},
    {"module": "routers.matching_commission", "attr": "commission_router", "prefix": "/price-commission", "tags": ["수수료설정"]},
    {"module": "routers.experts", "prefix": "/experts", "tags": ["전문가"]},
    {"module": "routers.identity", "prefix": "/identity", "tags": ["본인인증"]},
    {"module": "routers.identity_test"},
    {"module": "routers.agent_service"},
    {"module": "routers.admin_review"},
    {"module": "routers.admin_stats"},
    {"module": "routers.cron_manager"},
    {"module": "routers.internal_api_registry"},
    {"module": "routers.report_api_registry"},
    {"module": "routers.fire_hazmat"},
    {"module": "routers.precedent_api"},
    {"module": "routers.contract_kmong"},
    {"module": "routers.pricing_validation_api"},
    {"module": "routers.payment_activation_api"},
    {"module": "routers.feedback_api"},

    # ── SaaS 대시보드 의존 모듈 (유지) ──
    {"module": "routers.situation_dashboard_api"},
    {"module": "routers.attention_dashboard_api"},
    {"module": "routers.situation_detail_api"},
    {"module": "routers.situation_history_api"},
    {"module": "routers.response_guidance_api"},
    {"module": "routers.operational_learning_api"},
    {"module": "routers.operational_closure_api"},

    # ── 임시: executor 3층 LLM 보정 (작업 완료 후 제거) ──
    {"module": "routers.admin_executor_llm_fix", "tags": ["executor-llm-fix-temp"]},
    # ── 임시: D단계 의미절 직접 진단 테스트 (검증 후 정식 통합·제거) ──
    {"module": "routers.semantic_diagnosis_test", "tags": ["semantic-diagnosis-test"]},
    # ── 임시: D단계 법령엔진 어댑터 경로 테스트 (검증 후 정식 통합·제거) ──
    {"module": "routers.legal_adapter_test", "tags": ["legal-adapter-test"]},
]
