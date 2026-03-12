from fastapi import FastAPI
from routers.companies import router as companies_router

app = FastAPI()

app.include_router(companies_router)

@app.get("/")
def root():
    return {"message": "TAI API running"}
