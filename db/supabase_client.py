import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
# service_role 키 사용 — RLS 우회 (서버 전용)
# 우선순위: SUPABASE_SERVICE_ROLE_KEY(canonical, .env.example 정본)
#          > SUPABASE_SERVICE_KEY(legacy alias)
#          > SUPABASE_KEY(anon key — 폴백 금지 의도이나 기존 호환 유지)
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_KEY")
)

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
