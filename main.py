from fastapi import FastAPI
from supabase import create_client
import os

app = FastAPI()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

supabase = create_client(url, key)

@app.get("/")
def root():
    return {"message": "TAI API running"}

@app.get("/test-db")
def test_db():
    result = supabase.table("companies").select("*").limit(1).execute()
    return result.data
