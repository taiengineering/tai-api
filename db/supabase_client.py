import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
# service_role 키 사용 — RLS 우회 (서버 전용)
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
