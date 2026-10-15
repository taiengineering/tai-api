import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")


def _resolve_service_role_key() -> str | None:
    """service_role 키 해석 — SUPABASE_KEY(anon) 폴백 금지.

    우선순위:
      1. SUPABASE_SERVICE_ROLE_KEY  — canonical (.env.example 정본)
      2. SUPABASE_SERVICE_KEY       — legacy alias (하위 호환)
    둘 다 없으면 None 반환 → get_supabase() 에서 FAIL-CLOSE.
    """
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or None
    )


def get_supabase():
    key = _resolve_service_role_key()
    if not key:
        raise RuntimeError(
            "service_role 키가 설정되지 않았습니다. "
            "SUPABASE_SERVICE_ROLE_KEY 또는 SUPABASE_SERVICE_KEY를 설정하세요. "
            "SUPABASE_KEY(anon 키) 폴백은 보안상 금지됩니다."
        )
    return create_client(SUPABASE_URL, key)
