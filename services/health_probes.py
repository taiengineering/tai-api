"""
인프라 레벨 프로브.
서비스 로직과 무관한 기반 시설 체크.
v1.1.0 (2026-04-29): 구 프로젝트 URL → 서울 프로젝트로 변경
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


register_probe(
    "db",
    _probe_db,
    critical=True,
    desc_ko="데이터베이스",
    meta={
        "impacts": [{"name": "모든 서비스", "page": "전체"}],
        "fix_links": [
            {"name": "Supabase 대시보드", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax"},
        ],
        "api": "전체 (DB 의존)",
        "code": "db/supabase_client.py",
    },
)


async def _probe_pdf():
    base = os.environ.get("GOTENBERG_URL", "http://gotenberg.railway.internal:3000").rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base}/health", timeout=5)
        if r.status_code != 200:
            raise RuntimeError(f"Gotenberg HTTP {r.status_code}")
    return {}


register_probe(
    "pdf_engine",
    _probe_pdf,
    critical=True,
    desc_ko="PDF 생성 엔진",
    meta={
        "impacts": [
            {"name": "유료 진단 PDF", "url": "https://taieng.co.kr/paid-diagnosis-result.html"},
            {"name": "기안 PDF", "page": "SaaS > 문서관리"},
        ],
        "fix_links": [
            {"name": "Railway Gotenberg", "url": "https://railway.com/project/7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b"},
        ],
        "api": "POST /diagnosis/report-pdf, POST /proposals/{id}/pdf",
        "code": "services/diagnosis_report.py, services/diagnosis_proposal.py",
    },
)


async def _probe_sms():
    edge_url = os.environ.get("TAI_EDGE_SMS_URL", "")
    sb_url = os.environ.get("SUPABASE_URL", "")
    if not edge_url and not sb_url:
        return {"status": "warn", "detail": "TAI_EDGE_SMS_URL/SUPABASE_URL 미설정"}
    return {"mode": "edge_function(seoul)"}


register_probe(
    "sms",
    _probe_sms,
    critical=False,
    desc_ko="SMS 발송",
    meta={
        "impacts": [{"name": "알림 발송", "page": "전체 알림"}],
        "fix_links": [
            {"name": "Railway 환경변수", "url": "https://railway.com/project/7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b/variables"},
            {"name": "Supabase Edge Functions", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax/functions"},
        ],
        "api": "POST /messaging/send",
        "code": "routers/messaging.py",
    },
)


async def _probe_storage():
    sb = get_supabase()
    files = sb.storage.from_("diagrams").list("", {"limit": 5})
    if not files:
        return {"status": "warn", "detail": "diagrams 버킷 비어있음"}
    return {"file_count": len(files)}


register_probe(
    "storage",
    _probe_storage,
    critical=False,
    desc_ko="파일 저장소",
    meta={
        "impacts": [
            {"name": "다이어그램", "url": "https://taieng.co.kr/service/saas.html"},
            {"name": "문서 관리", "page": "SaaS > 문서관리"},
        ],
        "fix_links": [
            {"name": "Supabase Storage", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax/storage"},
        ],
        "api": "Supabase Storage API",
        "code": "services/document_svc.py",
    },
)


async def _probe_frontend_safe():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://safe.taieng.co.kr", timeout=10, follow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
    return {}


register_probe(
    "frontend_safe",
    _probe_frontend_safe,
    critical=True,
    desc_ko="SaaS 사이트",
    meta={
        "impacts": [{"name": "SaaS 전체", "url": "https://safe.taieng.co.kr"}],
        "fix_links": [
            {"name": "Cloudflare Pages", "url": "https://dash.cloudflare.com"},
            {"name": "tai-admin 레포", "url": "https://github.com/taiengineering/tai-admin"},
        ],
        "api": "Cloudflare Pages",
        "code": "tai-admin 레포",
    },
)


async def _probe_frontend_marketing():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://taieng.co.kr", timeout=10, follow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
    return {}


register_probe(
    "frontend_marketing",
    _probe_frontend_marketing,
    critical=False,
    desc_ko="마케팅 사이트",
    meta={
        "impacts": [{"name": "마케팅 사이트", "url": "https://taieng.co.kr"}],
        "fix_links": [
            {"name": "Cloudflare Pages", "url": "https://dash.cloudflare.com"},
            {"name": "taieng 레포", "url": "https://github.com/taiengineering/taieng"},
        ],
        "api": "Cloudflare Pages",
        "code": "taieng 레포",
    },
)
