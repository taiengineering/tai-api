from fastapi import FastAPI
from supabase import create_client
import os
import traceback

app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url:
        raise ValueError("SUPABASE_URL is missing")
    if not key:
        raise ValueError("SUPABASE_KEY is missing")

    return create_client(url, key)

@app.get("/")
def root():
    return {"message": "TAI API running"}

@app.get("/env-check")
def env_check():
    return {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL"),
        "SUPABASE_KEY_EXISTS": bool(os.environ.get("SUPABASE_KEY")),
    }

@app.get("/test-db")
def test_db():
    try:
        supabase = get_supabase()
        result = supabase.table("companies").select("*").limit(1).execute()
        return {
            "success": True,
            "data": result.data
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error_repr": repr(e),
            "traceback": traceback.format_exc(),
        }
