# main.py — v3.8.0
# feat: personnel v1.1.0 + repair.py 신규
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth                    import router as auth_router
from routers.users                   import router as users_router
from routers.companies               import router as companies_router
from routers.factories               import router as factories_router
from routers.system_codes            import router as system_codes_router
from routers.legal_engine            import router as legal_engine_router
from routers.ksic_engine             import router as ksic_engine_router
from routers.factory_process_v3      import router as factory_process_router
from routers.process_management      import router as process_management_router
from routers.building_register       import router as building_register_router
from routers.quotes                  import router as quotes_router
from routers.report_forms            import router as report_forms_router
from routers.contracts               import router as contracts_router
from routers.contacts                import router as contacts_router
from routers.education               import router as education_router
from routers.notifications           import router as notifications_router
from routers.equipment_assets        import router as equipment_assets_router
from routers.engine_equipment        import router as engine_equipment_router
from routers.engine_model            import router as engine_model_router
from routers.personnel               import router as personnel_router
from routers.repair                  import router as repair_router
from routers.schedule_engine         import router as schedule_engine_router
from routers.roles                   import router as roles_router
from routers.teams                   import router as teams_router
from routers.areas                   import router as areas_router
from routers.buildings               import router as buildings_router
from routers.inspection_sets         import router as inspection_sets_router
from routers.work_schedules          import router as work_schedules_router
from routers.inspection_checklist    import router as inspection_router
from routers.admin_stats             import router as admin_stats_router

app = FastAPI(
    title="TAI API",
    version="3.8.0",
    description="TAI 산업안전 플랫폼 API",
)

# ── CORS ─────────────────────────────────────────────────
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

# ── 라우터 등록 ───────────────────────────────────────────
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(companies_router)
app.include_router(factories_router)
app.include_router(system_codes_router)
app.include_router(legal_engine_router)
app.include_router(ksic_engine_router)
app.include_router(factory_process_router)         # v3 only
app.include_router(process_management_router)
app.include_router(building_register_router, prefix="/building-register")
app.include_router(quotes_router)
app.include_router(report_forms_router)
app.include_router(contracts_router)
app.include_router(contacts_router)
app.include_router(education_router)
app.include_router(notifications_router)
app.include_router(equipment_assets_router)
app.include_router(engine_equipment_router)
app.include_router(engine_model_router)
app.include_router(personnel_router)
app.include_router(repair_router)
app.include_router(schedule_engine_router)
app.include_router(roles_router)
app.include_router(teams_router)
app.include_router(areas_router)
app.include_router(buildings_router)
app.include_router(inspection_sets_router)
app.include_router(work_schedules_router)
app.include_router(inspection_router)
app.include_router(admin_stats_router)


# ── 헬스체크 ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "TAI API", "version": "3.8.0"}


@app.get("/health")
def health():
    import requests as req
    try:
        ip = req.get("https://api.ipify.org", timeout=5).text
    except Exception as e:
        ip = f"확인불가: {e}"
    return {"status": "healthy", "server_ip": ip, "version": "3.8.0"}
