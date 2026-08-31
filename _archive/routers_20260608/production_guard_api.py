# routers/production_guard_api.py — Production Safety & Runtime Isolation
"""
Mock/Real 분리 + Production 환경 검증 + 안전 Guard.
신규 기능 개발 금지. 운영 안정화만.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/production", tags=["운영안정"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Environment Validation ═══

@router.get("/env-check")
def check_environment():
    """Production 환경변수 검증."""
    checks = {}
    required = {
        "SUPABASE_URL": "Supabase 연결",
        "SUPABASE_KEY": "Supabase 키",
    }
    optional = {
        "TELEGRAM_BOT_TOKEN": "Telegram 알\ub9bc",
        "TELEGRAM_CHAT_ID": "Telegram \ucc44\ud305",
        "GOTENBERG_URL": "PDF \uc0dd\uc131",
        "SYNTHETIC_TEST_EMAIL": "Synthetic \ub85c\uadf8\uc778",
        "SYNTHETIC_TEST_PASSWORD": "Synthetic \ube44\ubc00\ubc88\ud638",
        "SYNTHETIC_FACTORY_ID": "Synthetic \uc0ac\uc5c5\uc7a5",
        "PLAYWRIGHT_HEADLESS": "Browser Synthetic",
        "PLAYWRIGHT_BASE_URL": "Browser \ub300\uc0c1 URL",
        "INTERNAL_API_SECRET": "\ub0b4\ubd80 API \uc2dc\ud06c\ub9bf",
    }

    for key, desc in required.items():
        val = os.environ.get(key)
        checks[key] = {"description": desc, "status": "OK" if val else "MISSING", "required": True}

    for key, desc in optional.items():
        val = os.environ.get(key)
        checks[key] = {"description": desc, "status": "OK" if val else "NOT_SET", "required": False}

    missing_required = [k for k, v in checks.items() if v["status"] == "MISSING" and v["required"]]
    missing_optional = [k for k, v in checks.items() if v["status"] == "NOT_SET"]

    return {"status": "success", "data": {
        "checks": checks,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "production_ready": len(missing_required) == 0,
        "gotenberg_url": os.environ.get("GOTENBERG_URL", "NOT_SET"),
    }}


# ═══ Mock / Real Separation ═══

@router.get("/runtime-stats")
def get_runtime_stats():
    """Mock vs Real \ub7f0\ud0c0\uc784 \ud1b5\uacc4."""
    try:
        sb = _sb()

        be = sb.table("business_event").select("environment").execute()
        ie = sb.table("engine_integrity_event").select("environment").execute()
        tr = sb.table("tenant_operational_registry").select("tenant_id").execute()

        be_env = {}
        for r in (be.data or []):
            e = r.get("environment", "unknown")
            be_env[e] = be_env.get(e, 0) + 1

        ie_env = {}
        for r in (ie.data or []):
            e = r.get("environment", "unknown")
            ie_env[e] = ie_env.get(e, 0) + 1

        mock_tenants = [t["tenant_id"] for t in (tr.data or []) if t["tenant_id"].startswith("mock_")]
        real_tenants = [t["tenant_id"] for t in (tr.data or []) if not t["tenant_id"].startswith("mock_")]

        return {"status": "success", "data": {
            "business_events": be_env,
            "integrity_events": ie_env,
            "mock_tenants": len(mock_tenants),
            "real_tenants": len(real_tenants),
            "mock_tenant_ids": mock_tenants,
            "real_tenant_ids": real_tenants,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Production Safety Guard ═══

@router.get("/safety-guard")
def check_safety():
    """Production \uc548\uc804 \uc0c1\ud0dc \uac80\uc99d."""
    try:
        sb = _sb()
        dangers = []

        # 1. Mock \ub370\uc774\ud130 production \ud63c\uc7ac
        mixed = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("environment", "production").like("tenant_id", "mock_%").execute()
        if (mixed.count or 0) > 0:
            dangers.append({"severity": "CRITICAL", "type": "mock_in_production",
                          "message": f"Mock tenant\uc774 production\uc73c\ub85c \uae30\ub85d\ub428: {mixed.count}\uac74"})

        # 2. Scheduler \uc0c1\ud0dc
        jobs = sb.table("cron_job_master").select("job_code,is_active") \
            .eq("is_active", True).execute()
        direct_jobs = [j for j in (jobs.data or []) if True]  # all active
        if len(direct_jobs) < 5:
            dangers.append({"severity": "WARNING", "type": "scheduler_low",
                          "message": f"\ud65c\uc131 Scheduler job {len(direct_jobs)}\uac1c (\uae30\ub300: 9+)"})

        # 3. Alert burst \uc704\ud5d8
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent_alerts = sb.table("alert_history").select("id", count="exact") \
            .gte("created_at", hour_ago).execute()
        if (recent_alerts.count or 0) > 50:
            dangers.append({"severity": "WARNING", "type": "alert_burst",
                          "message": f"\uc9c0\ub09c 1\uc2dc\uac04 \uc54c\ub9bc {recent_alerts.count}\uac74 (\ud3ed\ud0c4 \uc704\ud5d8)"})

        # 4. \ubbf8\ud574\uacb0 Critical \uc774\uc288 \uc218
        critical = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("severity", "CRITICAL").eq("resolved", False).eq("ignored", False) \
            .eq("environment", "production").execute()
        if (critical.count or 0) > 10:
            dangers.append({"severity": "WARNING", "type": "high_critical_count",
                          "message": f"Production CRITICAL \ubbf8\ud574\uacb0 {critical.count}\uac74"})

        # 5. Stale PENDING \uacb0\uc81c
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        stale = sb.table("payments").select("id", count="exact") \
            .eq("status_code", "PENDING").lt("created_at", week_ago).execute()
        if (stale.count or 0) > 20:
            dangers.append({"severity": "INFO", "type": "stale_payments",
                          "message": f"7\uc77c+ PENDING \uacb0\uc81c {stale.count}\uac74"})

        return {"status": "success", "data": {
            "dangers": dangers,
            "danger_count": len(dangers),
            "critical_count": sum(1 for d in dangers if d["severity"] == "CRITICAL"),
            "safe": sum(1 for d in dangers if d["severity"] == "CRITICAL") == 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Scheduler Status ═══

@router.get("/scheduler-status")
def get_scheduler_status():
    """Scheduler \uc2e4\ud589 \ud604\ud669."""
    try:
        sb = _sb()
        jobs = sb.table("cron_job_master").select("job_code,job_name,cron_expression,endpoint_url,is_active") \
            .order("job_code").execute()

        results = []
        for j in (jobs.data or []):
            jc = j["job_code"]
            last = sb.table("cron_job_log").select("status,started_at,duration_seconds,result_summary") \
                .eq("job_code", jc).order("started_at", desc=True).limit(1).execute()

            results.append({
                "job_code": jc,
                "job_name": j.get("job_name"),
                "cron": j.get("cron_expression"),
                "type": "DIRECT" if "direct://" in (j.get("endpoint_url") or "") else "HTTP",
                "is_active": j.get("is_active"),
                "last_status": last.data[0]["status"] if last.data else None,
                "last_run": last.data[0]["started_at"] if last.data else None,
                "last_duration": last.data[0].get("duration_seconds") if last.data else None,
            })

        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Production Summary ═══

@router.get("/summary")
def production_summary():
    """Production \uc804\uccb4 \uc694\uc57d."""
    try:
        sb = _sb()

        # Core counts
        users = sb.table("users").select("id", count="exact").execute()
        factories = sb.table("factories").select("id", count="exact").execute()
        payments = sb.table("payments").select("id", count="exact").execute()
        paid = sb.table("payments").select("id", count="exact").eq("status_code", "PAID").execute()
        subs_active = sb.table("subscriptions").select("id", count="exact").eq("status", "ACTIVE").execute()

        # Watch Engine
        be_prod = sb.table("business_event").select("id", count="exact").eq("environment", "production").execute()
        ie_prod = sb.table("engine_integrity_event").select("id", count="exact").eq("environment", "production").execute()
        ie_active = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("environment", "production").eq("resolved", False).eq("ignored", False).execute()

        # Document
        gen_docs = sb.table("generated_document").select("id", count="exact").execute()
        gen_ready = sb.table("generated_document").select("id", count="exact").eq("status", "GENERATED").execute()

        return {"status": "success", "data": {
            "users": users.count or 0,
            "factories": factories.count or 0,
            "payments_total": payments.count or 0,
            "payments_paid": paid.count or 0,
            "subscriptions_active": subs_active.count or 0,
            "business_events_production": be_prod.count or 0,
            "integrity_events_production": ie_prod.count or 0,
            "integrity_active_production": ie_active.count or 0,
            "generated_documents": gen_docs.count or 0,
            "documents_ready": gen_ready.count or 0,
            "commercial_ready": (paid.count or 0) > 0 and (subs_active.count or 0) > 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
