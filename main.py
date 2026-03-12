from fastapi import FastAPI
from supabase import create_client
import os
import traceback

app = FastAPI()

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url:
        raise ValueError("SUPABASE_URL missing")
    if not key:
        raise ValueError("SUPABASE_KEY missing")

    return create_client(url, key)


@app.get("/")
def root():
    return {"message": "TAI API running"}


@app.get("/test-db")
def test_db():
    try:
        supabase = get_supabase()
        result = supabase.table("companies").select("*").limit(1).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}
