# main.py — v5.6.5
# v5.6.5: schedule_pipeline 라우터 추가
#          POST /legal-engine/generate-schedules/{factory_id} — 진단→일정 자동생성
#          POST /notifications/trigger-due-alerts — D-7/D-3/당일 마감 알림
# v5.6.4: legal_engine — has_high_work(고소작업 2m이상) context 추가
# v5.6.3: legal_engine — DiagnoseStep1Body 수치 필드 추가
# v5.6.2: legal_engine — inspection_cycle 4필드 완비, schedule_type 분류
# v5.6.1: legal_engine — MANUFACTURING gas/boiler boolean→수치 변환
# v5.6.0: law_rule_generator v1.5.0 — has_condition 필터
# v5.5.5: contract_kmong 라우터 추가
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth                    import router as auth_router
from routers.users                   import router as users_router
from routers.companies               import router as companies_router
from routers.factories               import router as factories_router
from routers.system_codes            import router as system_codes_router
from routers.legal_engine            import router as legal_engine_router
from routers.engine_qa               import router as engine_qa_router
from routers.law_rule_generator      import router as law_rule_generator_router  # v5.5.2
from routers.engine_document         import router as engine_document_router     # v5.5.3
from routers.contract_kmong          import router as contract_kmong_router      # v5.5.5
from routers.schedule_pipeline       import router as schedule_pipeline_router   # v5.6.5
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
from routers.inspection_schedule     import router as inspection_schedule_router  # v5.5.4
from routers.work_schedules          import router as work_schedules_router
from routers.inspection_checklist    import router as inspection_router
from routers.admin_stats             import router as admin_stats_router
from routers.law_collector           import router as law_collector_router
from routers.cron_manager            import router as cron_manager_router
from routers.byulpyo                 import router as byulpyo_router
from routers.price_setting           import router as price_setting_router
from routers.internal_api_registry   import router as internal_api_registry_router
from routers.report_api_registry     import router as report_api_registry_router
from routers.construction            import router as construction_router
from routers.safety_template         import router as safety_template_router
from routers.event_trigger           import router as event_trigger_router
from routers.worker_registry         import router as worker_registry_router
from routers.diagnosis               import router as diagnosis_router
from routers.tbm                     import router as tbm_router
from routers.safety_meetings         import router as safety_meetings_router
from routers.risk_assessments        import router as risk_assessments_router
from routers.public                  import router as public_router
from routers.public_admin            import router as public_admin_router
from routers.alert_messages          import router as alert_messages_router
from routers.feature_flags           import router as feature_flags_router
from routers.site_public             import router as site_public_router, admin_router as site_faq_admin_router
from routers.anonymous_diagnosis     import router as anonymous_diagnosis_router
from routers.mail                    import router as mail_router

logger = logging.getLogger(__name__)

APP_VERSION = "5.6.5"


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
        "https://admin.taieng.co.kr",
        "https://tadmin.taieng.co.kr",
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

app.include_router(public_router)
app.include_router(public_admin_router)
app.include_router(alert_messages_router)
app.include_router(feature_flags_router)
app.include_router(site_public_router)
app.include_router(site_faq_admin_router)
app.include_router(anonymous_diagnosis_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(companies_router)
app.include_router(factories_router)
app.include_router(system_codes_router)
app.include_router(legal_engine_router)
app.include_router(engine_qa_router)
app.include_router(law_rule_generator_router)   # v5.5.2 AI 룰 생성기
app.include_router(engine_document_router)      # v5.5.3 문서메뉴
app.include_router(contract_kmong_router)       # v5.5.5 크몽 법령진단
app.include_router(schedule_pipeline_router)    # v5.6.5 진단→일정+알림 파이프
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
app.include_router(inspection_schedule_router)  # v5.5.4 일정관리
app.include_router(work_schedules_router)
app.include_router(inspection_router)
app.include_router(admin_stats_router)
app.include_router(law_collector_router)
app.include_router(cron_manager_router)
app.include_router(byulpyo_router)
app.include_router(price_setting_router)
app.include_router(internal_api_registry_router)
app.include_router(report_api_registry_router)
app.include_router(construction_router, prefix="/construction", tags=["건설안전"])
app.include_router(safety_template_router)
app.include_router(event_trigger_router)
app.include_router(worker_registry_router)
app.include_router(diagnosis_router)
app.include_router(tbm_router)
app.include_router(safety_meetings_router)
app.include_router(risk_assessments_router)
app.include_router(mail_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "TAI API", "version": APP_VERSION}


@app.get("/health")
def health():
    import requests as req
    try:
        ip = req.get("https://api.ipify.org", timeout=5).text
    except Exception as e:
        ip = f"확인불가: {e}"
    try:
        from scheduler import scheduler
        cron_status = f"{len(scheduler.get_jobs())}개 등록" if scheduler.running else "중지"
    except Exception:
        cron_status = "미초기화"
    return {"status": "healthy", "server_ip": ip, "version": APP_VERSION, "cron": cron_status}
