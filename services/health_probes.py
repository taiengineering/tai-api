"""
인프라 레벨 프로브.
서비스 로직과 무관한 기반 시설 체크.
"""
from __future__ import annotations

import os

import httpx

from db.supabase_client import get_supabase
from services.health_registry import register_probe


async def _probe_db():
    sb = get_supabase()
    r = (
        sb.table("price_saas_plan")
        .select("plan_code", count="exact")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return {"active_plans": r.count or 0}


register_probe("db", _probe_db, critical=True, desc_ko="데이터베이스")


async def _probe_pdf():
    base = os.environ.get("GOTENBERG_URL", "http://gotenberg.railway.internal:3000").rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base}/health", timeout=5)
        if r.status_code != 200:
            raise RuntimeError(f"Gotenberg HTTP {r.status_code}")
    return {}


register_probe("pdf_engine", _probe_pdf, critical=True, desc_ko="PDF 생성 엔진")


async def _probe_sms():
    key = os.environ.get("MESSAGEMI_API_KEY", "")
    proxy = os.environ.get("SMS_PROXY_URL", "")
    if not key:
        return {"status": "warn", "detail": "MESSAGEMI_API_KEY 미설정"}
    if not proxy:
        return {"status": "warn", "detail": "SMS_PROXY_URL 미설정"}
    return {"proxy": proxy[:20] + "..."}


register_probe("sms", _probe_sms, critical=False, desc_ko="SMS 발송")


async def _probe_storage():
    sb = get_supabase()
    files = sb.storage.from_("diagrams").list("", {"limit": 5})
    if not files:
        return {"status": "warn", "detail": "diagrams 버킷 비어있음"}
    return {"file_count": len(files)}


register_probe("storage", _probe_storage, critical=False, desc_ko="파일 저장소")


async def _probe_frontend_safe():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://safe.taieng.co.kr", timeout=10, follow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
    return {}


register_probe("frontend_safe", _probe_frontend_safe, critical=True, desc_ko="SaaS 사이트")


async def _probe_frontend_marketing():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://new.taieng.co.kr", timeout=10, follow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
    return {}


register_probe(
    "frontend_marketing",
    _probe_frontend_marketing,
    critical=False,
    desc_ko="마케팅 사이트",
)
