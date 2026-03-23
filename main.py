# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.auth               import router as auth_router
from routers.users              import router as users_router
from routers.companies          import router as companies_router
from routers.factories          import router as factories_router
from routers.system_codes       import router as system_codes_router
from routers.legal_engine       import router as legal_engine_router
from routers.ksic_engine        import router as ksic_engine_router
from routers.factory_process_v3 import router as factory_process_router
from routers.process_management import router as process_management_router
from routers.building_register  import router as building_register_router
from routers.quotes             import router as quotes_router

app = FastAPI(
    title="TAI API",
    version="3.0.0",
    description="TAI 산업안전 플랫폼 API",
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taieng.co.kr",
        "https://www.taieng.co.kr",
        "https://admin.taieng.co.kr",
        "https://tadmin.taieng.co.kr",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
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
app.include_router(factory_process_router)
app.include_router(process_management_router)
app.include_router(building_register_router)
app.include_router(quotes_router)


# ── 헬스체크 ──────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "TAI API", "version": "3.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
