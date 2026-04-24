# main.py — v5.35.0
# v5.35.0: payment_billing 라우터 등록 (POST /payments/inicis/billing/*, /payments/subscriptions/{id}/cancel)
# v5.34.0: Sentry 복원 + /health 개선 (항상 200 반환) + diagram_proxy 복원
# v5.33.0: Sentry 에러 모니터링 (SENTRY_DSN 환경 변수 시 초기화)
# v5.32.0: diagram_proxy 라우터 등록 (GET /api/v1/diagrams/{number}) — Supabase Storage 한글 SVG 우회
# v5.31.1: diagnosis_proposal 라우터 등록 (GET /diagnosis/proposal-pdf/{public_token})
# v5.31.0: diagnosis_report 라우터 등록 (GET /diagnosis/report-pdf/{public_token})
# v5.30.0: diagnosis_integrated 라우터 등록 (BE-10 진단통합 백엔드)
import os
import sentry_sdk

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        environment="production",
    )
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from db.database import get_supabase

from routers.auth                    import router as auth_router
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
from routers.matching                import commission_router
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
from routers.payment_billing         import router as payment_billing_router   # v5.35.0 정기결제
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
from routers.diagnosis_autofill      import router as diagnosis_autofill_router
from routers.diagnosis_roi           import router as diagnosis_roi_router
from routers.diagnosis_transform     import router as diagnosis_transform_router
from routers.overdue_checker         import router as overdue_checker_router
from routers.diagnosis_plan_recommend import router as plan_recommend_router
from routers.diagnosis_integrated    import router as diagnosis_integrated_router   # v5.30.0
from routers.diagnosis_report        import router as diagnosis_report_router        # v5.31.0
from routers.diagnosis_proposal      import router as diagnosis_proposal_router      # v5.31.1
from routers.diagram_proxy           import router as diagram_proxy_router           # v5.32.0
from routers.uploads                 import router as uploads_router                  # v5.36.0 사진업로드
from routers.emergency_report        import router as emergency_report_router         # v5.36.0 긴급신고
from routers.safety_reports          import router as safety_reports_router            # v5.36.0 이상신고

logger = logging.getLogger(__name__)

APP_VERSION = "5.35.0"


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
            logger.info("[SHUTDOWN] APScheduler 종료")
    except Exception:
        pass


app = FastAPI(
    title="TAI API",
    version=APP_VERSION,
    description="TAI 산업안전 플랫폼 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taieng.co.kr",
        "https://www.taieng.co.kr",
        "https://new.taieng.co.kr",
        "https://admin.taieng.co.kr",
        "https://tadmin.taieng.co.kr",
        "https://safe.taieng.co.kr",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*taieng\.co\.kr",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 공개 엔드포인트
app.include_router(public_router)
app.include_router(public_admin_router)
app.include_router(alert_messages_router)
app.include_router(feature_flags_router)
app.include_router(site_public_router)
app.include_router(site_faq_admin_router)
app.include_router(anonymous_diagnosis_router)
app.include_router(public_pricing_router)
app.include_router(connect_registration_router)
app.include_router(admin_connect_router)
app.include_router(admin_pricing_router)
app.include_router(fix_providers_router)
app.include_router(diagnosis_fields_router)
app.include_router(fix_chat_router)
app.include_router(diagnosis_autofill_router)
app.include_router(plan_recommend_router)
app.include_router(diagnosis_integrated_router)
app.include_router(diagnosis_report_router)
app.include_router(diagnosis_proposal_router)
app.include_router(diagram_proxy_router)

# 인증 필요 엔드포인트
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(companies_router)
app.include_router(factories_router)
app.include_router(system_codes_router)
app.include_router(legal_engine_router)
app.include_router(legal_engine_patch_router)
app.include_router(engine_qa_router)
app.include_router(law_rule_generator_router)
app.include_router(engine_document_router)
app.include_router(contract_kmong_router)
app.include_router(schedule_pipeline_router)
app.include_router(ksic_engine_router)
app.include_router(factory_process_router)
app.include_router(process_management_router)
app.include_router(building_register_router, prefix="/building-register")
app.include_router(quotes_router)
app.include_router(report_forms_router)
app.include_router(contracts_router)
app.include_router(contacts_router)
app.include_router(education_router)
app.include_router(education_assign_router)
app.include_router(notifications_router)
app.include_router(equipment_assets_router)
app.include_router(equipment_checkins_router)
app.include_router(engine_equipment_router)
app.include_router(engine_model_router)
app.include_router(engine_legal_router)
app.include_router(personnel_router)
app.include_router(repair_router)
app.include_router(biz_verify_router)
app.include_router(kosha_router)
app.include_router(fire_hazmat_router)
app.include_router(safety_info_router)
app.include_router(posts_router)
app.include_router(schedule_engine_router)
app.include_router(roles_router)
app.include_router(teams_router)
app.include_router(areas_router)
app.include_router(buildings_router)
app.include_router(inspection_sets_router)
app.include_router(inspection_schedule_router)
app.include_router(work_schedules_router)
app.include_router(inspection_router)
app.include_router(inspection_setup_router)
app.include_router(admin_stats_router)
app.include_router(law_collector_router)
app.include_router(cron_manager_router)
app.include_router(byulpyo_router)
app.include_router(price_setting_router)
app.include_router(product_pricing_router)
app.include_router(price_policy_router)
app.include_router(connection_commission_router)
app.include_router(agent_service_router)
app.include_router(precedent_router)
app.include_router(weather_router)
app.include_router(juso_router)
app.include_router(experts_router,  prefix="/experts",  tags=["전문가"])
app.include_router(matching_router,          prefix="/matching",          tags=["매칭"])
app.include_router(commission_router,        prefix="/price-commission",  tags=["수수료설정"])
app.include_router(contracts_engine_router,  prefix="/matching/contracts", tags=["계약서"])
app.include_router(settlements_router,       prefix="/settlements",        tags=["정산"])
app.include_router(identity_router, prefix="/identity", tags=["본인인증"])
app.include_router(internal_api_registry_router)
app.include_router(report_api_registry_router)
app.include_router(construction_router, prefix="/construction", tags=["건설안전"])
app.include_router(safety_template_router)
app.include_router(event_trigger_router)
app.include_router(worker_registry_router)
app.include_router(diagnosis_router)
app.include_router(diagnosis_roi_router)
app.include_router(diagnosis_transform_router)
app.include_router(overdue_checker_router)
app.include_router(tbm_router)
app.include_router(tbm_templates_router)
app.include_router(safety_meetings_router)
app.include_router(risk_assessments_router)
app.include_router(payment_router)
app.include_router(payment_billing_router)                                        # v5.35.0 정기결제
app.include_router(corrective_actions_router)
app.include_router(messaging_router)
app.include_router(fcm_router)
app.include_router(worker_check_router)
app.include_router(worker_home_router)
app.include_router(ai_copywrite_router)
app.include_router(mail_router)
app.include_router(uploads_router)
app.include_router(emergency_report_router)
app.include_router(safety_reports_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "TAI API", "version": APP_VERSION}


@app.get("/health")
def health_check():
    checks = {}
    try:
        sb = get_supabase()
        sb.table("system_codes").select("code").limit(1).execute()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {str(e)[:100]}"
    try:
        res = sb.table("master_building_legal_rules").select("id").eq("is_active", True).limit(1).execute()
        checks["law_engine"] = "ok" if res.data else "empty"
    except Exception as e:
        checks["law_engine"] = f"fail: {str(e)[:100]}"
    try:
        res = sb.table("fix_chat_sessions").select("id").limit(1).execute()
        checks["fix_chat"] = "ok"
    except Exception as e:
        checks["fix_chat"] = f"fail: {str(e)[:100]}"
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200,
        content={"status": "healthy" if all_ok else "degraded", "checks": checks}
    )
