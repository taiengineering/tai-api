"""연동 상태 관제 서비스 (WO-10 IntegrationHealth).

Goal: G-ms4je4z3-33eada
- core_integrations(): 핵심 연동(결제·증빙·메일·SMS·PDF·프록시) env 설정 여부. 네트워크 불필요.
- gov_api_status(): report_api_registry 정부 API 신청/승인 집계.
- probe_internal(): internal_api_registry 엔드포인트 실제 GET 헬스 probe(tai-api 자기 도메인).
- 미서비스 그룹(수선/선임/컨설팅/매칭) 제외 필터.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# 서비스 범위(법령진단·SaaS)에 해당하는 내부 그룹만 probe. 미서비스 제외.
_EXCLUDED_GROUPS = {"수선", "선임", "컨설팅", "매칭", "전문가", "견적"}


def _has_env(*keys: str) -> bool:
    """주어진 env 중 하나라도 설정돼 있으면 True."""
    return any(os.getenv(k, "").strip() for k in keys)


def core_integrations() -> List[Dict[str, Any]]:
    """핵심 연동의 env 설정 여부(configured/not_configured). 네트워크 불필요."""
    checks = [
        {
            "key": "payment_inicis", "label": "결제 (KG이니시스)",
            "configured": _has_env("INICIS_MID", "INICIS_INIAPI_KEY"),
            "critical": True,
        },
        {
            "key": "invoice_popbill", "label": "세금계산서·현금영수증 (팝빌)",
            "configured": _has_env("POPBILL_LINK_ID", "POPBILL_SECRET_KEY"),
            "critical": True,
        },
        {
            "key": "mail_gmail", "label": "메일 발송 (Gmail 도메인위임)",
            "configured": _has_env("GMAIL_SA_JSON", "GMAIL_SA_JSON_B64") and _has_env("GMAIL_SENDER"),
            "critical": False,
        },
        {
            "key": "mail_resend", "label": "메일 발송 (Resend fallback)",
            "configured": _has_env("RESEND_API_KEY"),
            "critical": False,
        },
        {
            "key": "sms_edge", "label": "SMS·알림톡 (MessageMi Edge)",
            "configured": _has_env("TAI_EDGE_SMS_URL", "SUPABASE_URL"),
            "critical": True,
        },
        {
            "key": "pdf_gotenberg", "label": "PDF (Gotenberg)",
            "configured": _has_env("GOTENBERG_URL"),
            "critical": False,
        },
        {
            "key": "outbound_proxy", "label": "아웃바운드 프록시 (한국 고정IP)",
            "configured": _has_env("OUTBOUND_PROXY"),
            "critical": False,
        },
    ]
    for c in checks:
        c["status"] = "configured" if c["configured"] else "not_configured"
    return checks


def gov_api_status() -> Dict[str, Any]:
    """report_api_registry 정부 API 신청/승인 집계."""
    rows = (
        get_supabase().table("report_api_registry")
        .select("system_name, operator, apply_status, api_key_issued, api_base_url")
        .order("system_name").execute()
    ).data or []

    approved = [r for r in rows if (r.get("apply_status") or "").upper() == "APPROVED"]
    pending = [r for r in rows if (r.get("apply_status") or "").upper() == "PENDING"]
    key_issued = [r for r in rows if r.get("api_key_issued")]

    return {
        "total": len(rows),
        "approved": len(approved),
        "pending": len(pending),
        "key_issued": len(key_issued),
        "items": rows,
    }


def get_health() -> Dict[str, Any]:
    """관제 종합(네트워크 불필요): 핵심 연동 env + 정부 API 집계."""
    core = core_integrations()
    core_ok = sum(1 for c in core if c["configured"])
    core_critical_missing = [c["label"] for c in core if c.get("critical") and not c["configured"]]
    return {
        "core_integrations": core,
        "core_configured": core_ok,
        "core_total": len(core),
        "core_critical_missing": core_critical_missing,
        "gov_api": gov_api_status(),
    }


def probe_internal(group: Optional[str] = None, base_url: Optional[str] = None,
                   limit: int = 50) -> Dict[str, Any]:
    """internal_api_registry 엔드포인트 실제 GET 헬스 probe.

    - tai-api 자기 도메인(base_url) 기준. base_url 미지정 시 API_SELF_URL env.
    - 미서비스 그룹 제외. is_active만.
    """
    import requests as _requests

    self_url = (base_url or os.getenv("API_SELF_URL", "")).strip().rstrip("/")
    if not self_url:
        return {"error": "base_url 또는 API_SELF_URL env가 필요합니다.", "results": []}

    q = (
        get_supabase().table("internal_api_registry")
        .select("group_name, api_name, method, endpoint, expect_status")
        .eq("is_active", True).order("sort_order")
    )
    if group:
        q = q.eq("group_name", group)
    rows = (q.limit(limit).execute()).data or []
    rows = [r for r in rows if r.get("group_name") not in _EXCLUDED_GROUPS]

    results = []
    ok_count = 0
    for r in rows:
        endpoint = r.get("endpoint") or ""
        expect = r.get("expect_status") or 200
        url = f"{self_url}{endpoint}"
        entry = {"group": r.get("group_name"), "api": r.get("api_name"),
                 "endpoint": endpoint, "expect": expect}
        try:
            resp = _requests.get(url, timeout=10)
            entry["actual"] = resp.status_code
            entry["ok"] = (resp.status_code == expect)
        except Exception as e:  # noqa: BLE001
            entry["actual"] = None
            entry["ok"] = False
            entry["error"] = str(e)[:120]
        if entry["ok"]:
            ok_count += 1
        results.append(entry)

    return {
        "probed": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
