from fastapi import FastAPI
from supabase import create_client
import traceback

app = FastAPI(
    title="TAI API",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 임시: Railway 환경변수 문제가 해결되기 전까지 하드코딩 사용
# 나중에 반드시 os.environ 방식으로 변경하고 키 교체 필요
url = "https://xntdkrjhgcscmqctdzyo.supabase.co".strip()
key = "sb_secret_fBeYn64yjsdUuucIjGQu0Q_ZSkVqYfx".strip()

def get_supabase():
    return create_client(url, key)

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
