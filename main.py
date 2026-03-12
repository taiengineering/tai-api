from fastapi import FastAPI
from supabase import create_client
import traceback

app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

url = "https://xntdkrjhgcscmqctdzyo.supabase.co".strip()
key = "sb_secret_fBeYn64yjsdUuucIjGQu0Q_ZSkVqYfx".strip()

supabase = create_client(url, key)

@app.get("/")
def root():
    return {"message": "TAI API running"}

@app.get("/env-check")
def env_check():
    return {
        "SUPABASE_URL": url,
        "SUPABASE_KEY_EXISTS": bool(key),
        "SUPABASE_URL_PREFIX": url[:30],
        "SUPABASE_KEY_PREFIX": key[:20],
    }

@app.get("/test-db")
def test_db():
    try:
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
