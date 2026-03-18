# db/database.py
# Supabase PostgreSQL 연결 공통 모듈

import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("https://xntdkrjhgcscmqctdzyo.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("sb_secret_sb_secret_fBeYn64yjsdUuucIjGQu0Q_ZSkVqYfx")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

