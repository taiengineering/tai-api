from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth import router as auth_router
from routers.companies import router as companies_router
from routers.factories import router as factories_router
from routers.buildings import router as buildings_router
from routers.areas import router as areas_router
from routers.teams import router as teams_router
from routers.roles import router as roles_router
from routers.users import router as users_router
from routers.contracts import router as contracts_router
from routers.contacts import router as contacts_router
from routers.system_codes import router as system_codes_router
from routers.notifications import router as notifications_router
from routers.education import router as education_router
from routers.equipment_assets import router as assets_router
from routers.inspection_sets import router as inspection_sets_router
from routers.work_schedules import router as work_schedules_router
from routers.schedule_engine import router as schedule_engine_router
from routers.law_collector import router as law_collector_router
from routers.legal_engine import router as legal_engine_router
from routers.ksic_engine import router as ksic_engine_router
from routers.factory_process_v2 import router as factory_process_router      # ✅ 수정: factory_process_v2_router → factory_process_router
from routers.building_register import router as building_register_router
from routers.process_management import router as process_management_router
from routers.factory_process_v3 import router as factory_process_router
from routers.legal_engine_v3 import router as legal_engine_router

app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admin.taieng.co.kr",
        "https://taieng-admin.pages.dev",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 인증 ───────────────────────────────────────────────────
app.include_router(auth_router, prefix="/auth", tags=["인증"])

# ─── 조직 ───────────────────────────────────────────────────
app.include_router(companies_router, prefix="/companies", tags=["사업장"])
app.include_router(factories_router, prefix="/factories", tags=["시설"])
app.include_router(buildings_router, prefix="/buildings", tags=["건물"])
app.include_router(areas_router, prefix="/areas", tags=["구역"])
app.include_router(teams_router, prefix="/teams", tags=["팀"])
app.include_router(roles_router, prefix="/roles", tags=["역할"])
app.include_router(users_router, prefix="/users", tags=["회원"])
app.include_router(contacts_router, tags=["담당자/파일"])

# ─── 계약 ───────────────────────────────────────────────────
app.include_router(contracts_router, tags=["견적/계약"])
app.include_router(building_register_router, prefix="/building-register", tags=["건축물대장"])

# ─── 전역변수 ─────────────────────────────────────────────────
app.include_router(system_codes_router, prefix="/system-codes", tags=["전역변수"])

# ─── 알림 ───────────────────────────────────────────────────
app.include_router(notifications_router, tags=["알림"])

# ─── 교육관리 ─────────────────────────────────────────────────
app.include_router(education_router, tags=["교육관리"])

# ─── 설비/점검 ────────────────────────────────────────────────
app.include_router(assets_router, prefix="/equipment-assets", tags=["설비자산"])
app.include_router(inspection_sets_router, prefix="/inspection-sets", tags=["점검세트"])
app.include_router(work_schedules_router, prefix="/work-schedules", tags=["작업일정"])
app.include_router(schedule_engine_router, prefix="/schedule-engine", tags=["일정엔진"])
app.include_router(factory_process_router, prefix="/factory-process", tags=["공정관리"])  # ✅ 수정

# ─── 공정 마스터 ──────────────────────────────────────────────
app.include_router(process_management_router, tags=["공정마스터"])  # ✅ 추가: 누락된 등록

# ─── 법령 ───────────────────────────────────────────────────
app.include_router(law_collector_router, prefix="/law-collector", tags=["법령수집"])
app.include_router(legal_engine_router, prefix="/legal-engine", tags=["법령엔진"])
app.include_router(ksic_engine_router, prefix="/ksic-engine", tags=["KSIC엔진"])


@app.get("/", tags=["헬스체크"])
def root():
    return {"message": "TAI API Server", "version": "1.0", "docs": "/docs"}


@app.get("/health", tags=["헬스체크"])
def health():
    return {"status": "ok"}
