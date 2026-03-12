from fastapi import FastAPI

from routers.companies import router as companies_router
from routers.factories import router as factories_router

app = FastAPI(
    title="TAI API",
    version="1.0"
)

app.include_router(companies_router)
app.include_router(factories_router)


@app.get("/")
def root():
    return {"message": "TAI API running"}
