from fastapi import FastAPI

from routers.companies import router as companies_router
from routers.factories import router as factories_router
from routers.buildings import router as buildings_router
from routers.areas import router as areas_router
from routers.equipment_assets import router as assets_router
from routers.inspection_sets import router as inspection_sets_router
from routers.work_schedules import router as work_schedules_router
from routers.schedule_engine import router as schedule_engine_router

app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(companies_router)
app.include_router(factories_router)
app.include_router(buildings_router)
app.include_router(areas_router)
app.include_router(assets_router)
app.include_router(inspection_sets_router)
app.include_router(work_schedules_router)
app.include_router(schedule_engine_router)

@app.get("/")
def root():
    return {"message": "TAI API running"}
