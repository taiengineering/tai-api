from fastapi import FastAPI
from routers.companies import router as companies_router
from routers.factories import router as factories_router
from routers.buildings import router as buildings_router
from routers.areas import router as areas_router
from routers.teams import router as teams_router
from routers.roles import router as roles_router
from routers.users import router as users_router
from routers.contracts import router as contracts_router
from routers.system_codes import router as system_codes_router
from routers.equipment_assets import router as assets_router
from routers.inspection_sets import router as inspection_sets_router
from routers.work_schedules import router as work_schedules_router
from routers.schedule_engine import router as schedule_engine_router
from routers.law_collector import router as law_collector_router
from routers.legal_engine import router as legal_engine_router
from routers.auth import router as auth_router
from routers.contacts import router as contacts_router



app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 조직/회원
app.include_router(companies_router)
app.include_router(factories_router)
app.include_router(buildings_router)
app.include_router(areas_router)
app.include_router(teams_router)
app.include_router(roles_router)
app.include_router(users_router)
app.include_router(contracts_router)
app.include_router(legal_engine_router)
app.include_router(auth_router) 
app.include_router(contacts_router)

# 공통 코드
app.include_router(system_codes_router)

# 설비/점검
app.include_router(assets_router)
app.include_router(inspection_sets_router)
app.include_router(work_schedules_router)
app.include_router(schedule_engine_router)

# 법령 수집
app.include_router(law_collector_router)

@app.get("/")
def root():
    return {"message": "TAI API running"}
