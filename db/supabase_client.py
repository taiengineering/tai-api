from supabase import create_client

SUPABASE_URL = "https://xntdkrjhgcscmqctdzyo.supabase.co"
SUPABASE_KEY = "sb_secret_fBeYn64yjsdUuucIjGQu0Q_ZSkVqYfx"

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
