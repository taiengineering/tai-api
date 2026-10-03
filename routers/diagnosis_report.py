"""
routers/diagnosis_report.py — v4.0.0
WO-WP04-PDF-PREMIUM-CONTRACT-REPOINT-001

유료 진단 상세 PDF 생성 엔드포인트
  GET /diagnosis/report-pdf/{public_token}

v4.0.0 (2026-10-03):
  - PDF legal content source: full_result legacy → premium_result_v1
  - build_paid_result_product_v1 + build_public_premium_result_v1 재사용
  - build_paid_result_pdf_view_v1 pure presenter 추가
  - 레거시 rules_table/applicable_rules/appointment_required/inspection_required 제거
  - 레거시 _enrich_rules/_build_law_groups/OB_LABEL 제거
  - 레거시 penalty/submit_org/qualification 제거
  - diagnosis_report_paid_v2.html 전용 template
  - fail-closed: premium assembler 실패 → 503 (legacy fallback 0)
v3.0.0 (2026-09-21): SaaS 추천/과태료/heuristic/TOP5 리스크 제거
v2.0.0 (2026-04-20): xhtml2pdf → Gotenberg Chromium PDF 엔진 전환
v1.0.0 (2026-04-18): 최초 생성
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from urllib.parse import quote as _url_quote

from db.supabase_client import get_supabase
from services.paid_result_product_svc import build_paid_result_product_v1
from services.paid_result_public_projection_svc import build_public_premium_result_v1
from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1
from services.time import now_kst

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단리포트"])

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://tai-gotenberg.internal:3000")

FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE",
    "free", "FREE",
})


# ───────────────────────────────────────────────────────────
# 렌더링 / PDF 변환 헬퍼
# ───────────────────────────────────────────────────────────

def _report_date_str() -> str:
    return now_kst().strftime("%Y년 %m월 %d일")


def _render_html(template_vars: Dict[str, Any]) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    tmpl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    env = Environment(
        loader=FileSystemLoader(tmpl_dir),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("diagnosis_report_paid_v2.html")
    return template.render(**template_vars)


async def _generate_pdf(html: str) -> bytes:
    url = f"{GOTENBERG_URL}/forms/chromium/convert/html"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            files={"files": ("index.html", html.encode("utf-8"), "text/html")},
            data={
                "paperWidth": "8.27",
                "paperHeight": "11.69",
                "marginTop": "0",
                "marginBottom": "0",
                "marginLeft": "0",
                "marginRight": "0",
                "printBackground": "true",
                "scale": "1",
            },
        )
    if response.status_code != 200:
        log.error(
            "[REPORT PDF] Gotenberg 오류: %s %s",
            response.status_code,
            response.text[:200],
        )
        raise HTTPException(
            status_code=500,
            detail=f"PDF 생성 실패: Gotenberg {response.status_code}",
        )
    return response.content


# ───────────────────────────────────────────────────────────
# API 엔드포인트
# ───────────────────────────────────────────────────────────

@router.get("/report-pdf/{public_token}")
async def get_paid_report_pdf(public_token: str):
    """
    GET /diagnosis/report-pdf/{public_token}

    유료 진단 상세 PDF 생성 및 반환.
    법령 결과 정본: premium_result_v1 (build_paid_result_product_v1 경로).
    fail-closed: premium 생성 실패 → 503, legacy fallback 0.
    """
    supabase = get_supabase()

    # 1. 진단 결과 조회 (created_at, source_type은 contract builder 필요)
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select(
            "id, public_token, tier_code, full_result, input_data, "
            "status, expires_at, created_at, source_type"
        )
        .eq("public_token", public_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")

    rec = res.data[0]

    # 2. 유효성 체크
    if rec.get("status") != "ACTIVE":
        raise HTTPException(status_code=410, detail="비활성화된 진단 결과입니다.")

    # 3. 유료 tier 확인
    tier_code = rec.get("tier_code") or ""
    if tier_code in FREE_TIER_CODES or tier_code.endswith("_FREE") or "FREE" in tier_code.upper():
        raise HTTPException(
            status_code=402,
            detail="상세 PDF는 유료 진단 결과에만 제공됩니다. 유료 결제 후 이용해 주세요.",
        )

    # 4. Premium Result 생성 — fail-closed (legacy fallback 0)
    try:
        product = build_paid_result_product_v1(rec)
        premium = build_public_premium_result_v1(product)
    except Exception:
        log.exception("[REPORT PDF] premium product 생성 실패")
        raise HTTPException(status_code=503, detail="유료 진단 법령 결과를 불러오지 못했습니다.")

    # 5. PDF View Model 생성 (pure function)
    view = build_paid_result_pdf_view_v1(premium)

    # 6. 문서 등록용 운영 metadata (비법적 — §11 허용)
    input_data = rec.get("input_data") or {}
    full_result = rec.get("full_result") or {}

    template_vars: Dict[str, Any] = {
        "report_date":              _report_date_str(),
        "diagnosed_at":             view["diagnosed_at"],
        "profile":                  view["profile"],
        "total_obligation_count":   view["total_obligation_count"],
        "distinct_law_count":       view["distinct_law_count"],
        "obligation_type_counts":   view["obligation_type_counts"],
        "obligations":              view["obligations"],
        "law_portfolio":            view["law_portfolio"],
        "article_bundles":          view["article_bundles"],
        "legal_actor_map":          view["legal_actor_map"],
        "evidence":                 view["evidence"],
    }

    # 7. HTML 렌더링
    try:
        html = _render_html(template_vars)
    except Exception as e:
        log.error("[REPORT PDF] 렌더링 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"리포트 렌더링 실패: {e}")

    # 8. PDF 변환
    try:
        pdf_bytes = await _generate_pdf(html)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[REPORT PDF] PDF 변환 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")

    log.info(
        "[REPORT PDF] 생성 완료 — tier=%s size=%d bytes",
        tier_code, len(pdf_bytes),
    )

    # 9. 문서 등록 (운영 metadata — 실패해도 PDF 반환)
    diagnosis_id = rec.get("id")
    company_id = input_data.get("company_id") or full_result.get("company_id")
    factory_id = full_result.get("factory_id") or input_data.get("factory_id")
    if not company_id and factory_id:
        try:
            fac_res = (
                supabase.table("factories")
                .select("company_id")
                .eq("id", factory_id)
                .limit(1)
                .execute()
            )
            if fac_res.data:
                company_id = fac_res.data[0].get("company_id")
        except Exception:
            pass

    filename = "TAI_법령진단_상세보고서.pdf"
    try:
        from services.document_svc import register_generated
        if company_id:
            await register_generated(
                file_bytes=pdf_bytes,
                file_name=filename,
                mime_type="application/pdf",
                company_id=company_id,
                category="report",
                generated_by="diagnosis_report",
                factory_id=factory_id,
                linked_table="diagnosis_results",
                linked_id=diagnosis_id,
                title="법령진단 상세 보고서",
            )
    except Exception as _doc_err:
        log.warning("documents 기록 실패 (PDF는 정상 반환): %s", _doc_err)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"TAI_diagnosis.pdf\"; "
                f"filename*=UTF-8''{_url_quote(filename, safe='')}"
            ),
            "Content-Length": str(len(pdf_bytes)),
            "X-Tier-Code": tier_code,
        },
    )
