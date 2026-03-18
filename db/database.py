# db/database.py
import os
from supabase import create_client, Client

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url:
        raise Exception(f"SUPABASE_URL is None. All env vars: {list(os.environ.keys())}")
    if not key:
        raise Exception(f"SUPABASE_KEY is None")
    
    return create_client(url, key)
