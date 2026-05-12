# main.py — v5.51.0
# v5.51.0: Phase 6 — Compliance Evidence Bridge 라우터 등록 (8 API — /bridge/evidence-*)
# v5.50.0: Phase 5 — Review Queue Runtime Bridge 라우터 등록 (8 API — /bridge/review-*)
# v5.49.0: Phase 4 — Notification Runtime Bridge 라우터 등록 (6 API — /bridge/notifications/*)
# v5.48.0: Phase 3 — My Inspection Runtime Bridge 라우터 등록 (8 API — /bridge/my-inspection/*)
# v5.47.0: Phase 2 — Obligation Bridge 라우터 등록 (7 API — /bridge/obligations/*)
# v5.46.0: Phase 2 — Inspection Bridge 라우터 등록 (4 API — /bridge/inspection/*)
# v5.45.0: Phase 1 — Legacy Write Freeze + Runtime Bridge (일정/문서/진단 Ownership 전환)
# v5.44.0: Persistence & Drift Control Engine (7 API — /persistence/*)
# v5.43.0: Simulation Engine (6 API — /simulation/*)
# v5.42.0: Runtime Evaluator Engine (7 API — /runtime-evaluator/*)
# v5.41.0: 문서엔진 API (15 API — /document-engine/*)
# v5.40.0: 법령진단서비스 + SaaS 반복설정 분리
# v5.39.0: Compiler Core + Residual Intelligence + Admin Review
import os
import sentry_sdk

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1, environment="production")
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import services.health_probes  # noqa: F401

from routers.auth                    import router as auth_router
from routers.auth_oauth              import router as auth_oauth_router
from routers.users                   import router as users_router
from routers.companies               import router as companies_router
from routers.factories               import router as factories_router
from routers.system_codes            import router as system_codes_router
from routers.legal_engine            import router as legal_engine_router
from routers.legal_engine_patch      import router as legal_engine_patch_router
from routers.engine_qa               import router as engine_qa_router
from routers.law_rule_generator      import router as law_rule_generator_router
from routers.engine_document         import router as engine_document_router
from routers.contract_kmong          import router as contract_kmong_router
from routers.schedule_pipeline       import router as schedule_pipeline_router
from routers.ksic_engine             import router as ksic_engine_router
from routers.factory_process_v3      import router as factory_process_router
from routers.process_management      import router as process_management_router
from routers.building_register       import router as building_register_router
from routers.quotes                  import router as quotes_router
from routers.report_forms            import router as report_forms_router
from routers.contracts               import router as contracts_router
from routers.contacts                import router as contacts_router
from routers.education               import router as education_router
from routers.education_assign        import router as education_assign_router
from routers.notifications           import router as notifications_router
from routers.equipment_assets        import router as equipment_assets_router
from routers.equipment_checkins      import router as equipment_checkins_router
from routers.engine_equipment        import router as engine_equipment_router
from routers.engine_model            import router as engine_model_router
from routers.engine_legal            import router as engine_legal_router
from routers.personnel               import router as personnel_router
from routers.repair                  import router as repair_router
from routers.biz_verify              import router as biz_verify_router
from routers.kosha_apis              import router as kosha_router
from routers.fire_hazmat             import router as fire_hazmat_router
from routers.safety_info             import router as safety_info_router
from routers.posts                   import router as posts_router
from routers.schedule_engine         import router as schedule_engine_router
from routers.roles                   import router as roles_router
from routers.teams                   import router as teams_router
from routers.areas                   import router as areas_router
from routers.buildings               import router as buildings_router
from routers.inspection_sets         import router as inspection_sets_router
from routers.inspection_schedule     import router as inspection_schedule_router
from routers.work_schedules          import router as work_schedules_router
from routers.inspection_checklist    import router as inspection_router
from routers.inspection_setup        import router as inspection_setup_router
from routers.admin_stats             import router as admin_stats_router
from routers.law_collector           import router as law_collector_router
from routers.cron_manager            import router as cron_manager_router
from routers.byulpyo                 import router as byulpyo_router
from routers.price_setting           import router as price_setting_router
from routers.product_pricing         import router as product_pricing_router
from routers.price_policy            import router as price_policy_router
from routers.connection_commission   import router as connection_commission_router
from routers.agent_service           import router as agent_service_router
from routers.precedent_api           import router as precedent_router
from routers.weather                 import router as weather_router
from routers.juso                    import router as juso_router
from routers.experts                 import router as experts_router
from routers.matching                import router as matching_router
from routers.matching_commission     import commission_router
from routers.contracts_engine        import router as contracts_engine_router
from routers.settlements             import router as settlements_router
from routers.identity                import router as identity_router
from routers.internal_api_registry   import router as internal_api_registry_router
from routers.report_api_registry     import router as report_api_registry_router
from routers.construction            import router as construction_router
from routers.safety_template         import router as safety_template_router
from routers.event_trigger           import router as event_trigger_router
from routers.worker_registry         import router as worker_registry_router
from routers.diagnosis               import router as diagnosis_router
from routers.tbm                     import router as tbm_router
from routers.tbm_templates           import router as tbm_templates_router
from routers.safety_meetings         import router as safety_meetings_router
from routers.risk_assessments        import router as risk_assessments_router
from routers.payment                 import router as payment_router
from routers.payment_ops             import router as payment_ops_router
from routers.payment_billing         import router as payment_billing_router
from routers.corrective_actions      import router as corrective_actions_router
from routers.messaging               import router as messaging_router
from routers.fcm                     import router as fcm_router
from routers.worker_check            import router as worker_check_router
from routers.worker_home             import router as worker_home_router
from routers.ai_copywrite            import router as ai_copywrite_router
from routers.public                  import router as public_router
from routers.public_admin            import router as public_admin_router
from routers.alert_messages          import router as alert_messages_router
from routers.feature_flags           import router as feature_flags_router
from routers.site_public             import router as site_public_router, admin_router as site_faq_admin_router
from routers.anonymous_diagnosis     import router as anonymous_diagnosis_router
from routers.mail                    import router as mail_router
from routers.public_pricing          import router as public_pricing_router
from routers.connect_registration    import router as connect_registration_router
from routers.admin_connect           import router as admin_connect_router
from routers.admin_pricing           import router as admin_pricing_router
from routers.fix_providers_api       import router as fix_providers_router
from routers.diagnosis_fields        import router as diagnosis_fields_router
from routers.fix_chat                import router as fix_chat_router
from routers.health                  import router as health_router
from routers.diagnosis_autofill      import router as diagnosis_autofill_router
from routers.diagnosis_roi           import router as diagnosis_roi_router
from routers.diagnosis_transform     import router as diagnosis_transform_router
from routers.overdue_checker         import router as overdue_checker_router
from routers.diagnosis_plan_recommend import router as plan_recommend_router
from routers.diagnosis_integrated    import router as diagnosis_integrated_router
from routers.diagnosis_report        import router as diagnosis_report_router
from routers.diagnosis_proposal      import router as diagnosis_proposal_router
from routers.diagram_proxy           import router as diagram_proxy_router
from routers.pw_reset                import router as pw_reset_router
from routers.internal_inbox          import router as internal_inbox_router
from routers.admin_inquiries         import router as admin_inquiries_router
from routers.compiler_core           import router as compiler_core_router
from routers.residual_intelligence   import router as ri_router
from routers.admin_review            import router as admin_review_router
from routers.diagnosis_engine        import router as diagnosis_engine_router
from routers.saas_setup              import router as saas_setup_router
from routers.document_engine_api     import router as document_engine_api_router
from routers.runtime_evaluator_api   import router as runtime_evaluator_api_router
from routers.simulation_api          import router as simulation_api_router
from routers.persistence_api         import router as persistence_api_router
from routers.legacy_freeze           import router as legacy_freeze_router
from routers.runtime_bridge          import router as runtime_bridge_router
from routers.inspection_bridge       import router as inspection_bridge_router
from routers.obligation_bridge       import router as obligation_bridge_router
from routers.my_inspection_bridge    import router as my_inspection_bridge_router
from routers.notification_bridge     import router as notification_bridge_router
from routers.review_bridge            import router as review_bridge_router
from routers.evidence_bridge          import router as evidence_bridge_router

logger = logging.getLogger(__name__)
APP_VERSION = "5.51.0"

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from scheduler import start_scheduler
        start_scheduler()
        logger.info("[STARTUP] APScheduler 시작 완료")
    except Exception as e:
        logger.error(f"[STARTUP] APScheduler 시작 실패: {e}")
    yield
    try:
        from scheduler import scheduler
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass

app = FastAPI(title="TAI API", version=APP_VERSION, description="TAI 산업안전 플랫폼 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taieng.co.kr","https://www.taieng.co.kr","https://new.taieng.co.kr",
        "https://admin.taieng.co.kr","https://tadmin.taieng.co.kr","https://safe.taieng.co.kr",
        "http://localhost:5500","http://127.0.0.1:5500","http://localhost:3000","http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*taieng\.co\.kr",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

for r in [public_router, health_router, public_admin_router, alert_messages_router, feature_flags_router,
          site_public_router, site_faq_admin_router, admin_inquiries_router, anonymous_diagnosis_router,
          public_pricing_router, connect_registration_router, admin_connect_router, admin_pricing_router,
          fix_providers_router, diagnosis_fields_router, fix_chat_router, diagnosis_autofill_router,
          plan_recommend_router, diagnosis_integrated_router, diagnosis_report_router,
          diagnosis_proposal_router, diagram_proxy_router]:
    app.include_router(r)

for r in [auth_router, auth_oauth_router, pw_reset_router, users_router, companies_router, factories_router,
          system_codes_router, legal_engine_router, legal_engine_patch_router, engine_qa_router,
          law_rule_generator_router, engine_document_router, contract_kmong_router,
          schedule_pipeline_router, ksic_engine_router, factory_process_router,
          process_management_router, quotes_router, report_forms_router, contracts_router,
          contacts_router, education_router, education_assign_router, notifications_router,
          equipment_assets_router, equipment_checkins_router, engine_equipment_router,
          engine_model_router, engine_legal_router, personnel_router, repair_router,
          biz_verify_router, kosha_router, fire_hazmat_router, safety_info_router, posts_router,
          schedule_engine_router, roles_router, teams_router, areas_router, buildings_router,
          inspection_sets_router, inspection_schedule_router, work_schedules_router,
          inspection_router, inspection_setup_router, admin_stats_router, law_collector_router,
          cron_manager_router, byulpyo_router, price_setting_router, product_pricing_router,
          price_policy_router, connection_commission_router, agent_service_router, precedent_router,
          weather_router, juso_router, internal_api_registry_router, internal_inbox_router,
          report_api_registry_router, safety_template_router, event_trigger_router,
          worker_registry_router, diagnosis_router, diagnosis_roi_router, diagnosis_transform_router,
          overdue_checker_router, tbm_router, tbm_templates_router, safety_meetings_router,
          risk_assessments_router, payment_router, payment_ops_router, payment_billing_router,
          corrective_actions_router, messaging_router, fcm_router, worker_check_router,
          worker_home_router, ai_copywrite_router, mail_router]:
    app.include_router(r)

app.include_router(building_register_router, prefix="/building-register")
app.include_router(experts_router, prefix="/experts", tags=["전문가"])
app.include_router(matching_router, prefix="/matching", tags=["매칭"])
app.include_router(commission_router, prefix="/price-commission", tags=["수수료설정"])
app.include_router(contracts_engine_router, prefix="/matching/contracts", tags=["계약서"])
app.include_router(settlements_router, prefix="/settlements", tags=["정산"])
app.include_router(identity_router, prefix="/identity", tags=["본인인증"])
app.include_router(construction_router, prefix="/construction", tags=["건설안전"])

# Runtime Engine Layer
app.include_router(compiler_core_router)          # /api/v1/compiler/*
app.include_router(ri_router)                      # /api/v1/residual-intelligence/*
app.include_router(admin_review_router)            # /api/v1/admin/*
app.include_router(diagnosis_engine_router)        # /api/v1/diagnosis-engine/*
app.include_router(saas_setup_router)              # /api/v1/saas-setup/*
app.include_router(document_engine_api_router)     # /document-engine/*
app.include_router(runtime_evaluator_api_router)   # /runtime-evaluator/*
app.include_router(simulation_api_router)          # /simulation/*
app.include_router(persistence_api_router)         # /persistence/*

# Phase 1-2: Legacy→Runtime Ownership Transition
app.include_router(legacy_freeze_router)           # Legacy write 차단 (HTTP 410)
app.include_router(runtime_bridge_router)          # /bridge/* — schedule/document/diagnosis
app.include_router(inspection_bridge_router)       # /bridge/inspection/* — 점검 매핑
app.include_router(obligation_bridge_router)       # /bridge/obligations/* — Phase 2 의무 관리
app.include_router(my_inspection_bridge_router)    # /bridge/my-inspection/* — Phase 3 점검 수행
app.include_router(notification_bridge_router)     # /bridge/notifications/* — Phase 4 알림
app.include_router(review_bridge_router)            # /bridge/review-* — Phase 5 검토 승인
app.include_router(evidence_bridge_router)          # /bridge/evidence-* — Phase 6 증빙

@app.get("/")
def root():
    return {"status": "ok", "service": "TAI API", "version": APP_VERSION}
