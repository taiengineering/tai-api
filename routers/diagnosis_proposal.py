"""
routers/diagnosis_proposal.py — v1.0.0
기안용 PDF 생성 — 결재권자용 3페이지 리스크 보고서

v1.0.0 (2026-04-18):
  GET /diagnosis/proposal-pdf/{public_token}
  - anonymous_diagnosis_results 테이블에서 public_token으로 조회
  - Jinja2 렌더링 (templates/proposal_pdf.html)
  - xhtml2pdf PDF 생성
  - StreamingResponse(application/pdf) 반환
  - 공개 엔드포인트: public_token 자체가 접근 제어
  - SVG 미사용 (xhtml2pdf 호환성): HTML 테이블·바차트로 대체
  - 플랜 추천: diagnosis_plan_recommend.py 함수 재사용
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["기안PDF"])

VERSION = "1.0.0"

# ─── 상수 ───────────────────────────────────────────────────────────────────

SECTOR_LABEL: Dict[str, str] = {
    "INDUSTRY":       "산업(제조)",
    "BUILDING":       "건물·시설",
    "CONSTRUCTION":   "건설",
    "MANUFACTURING":  "산업(제조)",
    "SPECIAL_FACILITY": "건물·시설",
}

SECTOR_NORMALIZE: Dict[str, str] = {
    "MANUFACTURING":    "INDUSTRY",
    "SPECIAL_FACILITY": "BUILDING",
}

# 가격은 PRICING_FINAL.md 기준 (diagnosis_plan_recommend._PLANS와 동기화)
_PLANS: Dict[str, Dict[str, Any]] = {
    "INDUSTRY_STARTER_V2":      {"name": "산업 STARTER",  "monthly": 79000},
    "INDUSTRY_BUSINESS_V2":     {"name": "산업 BUSINESS", "monthly": 149000},
    "INDUSTRY_PRO":             {"name": "산업 PRO",       "monthly": 249000},
    "INDUSTRY_CUSTOM_V2":       {"name": "산업 CUSTOM",    "monthly": None},
    "BUILDING_BASIC":           {"name": "건물 BASIC",     "monthly": 59000},
    "BUILDING_STANDARD":        {"name": "건물 STANDARD",  "monthly": 145000},
    "BUILDING_CUSTOM":          {"name": "건물 CUSTOM",    "monthly": 249000},
    "CONSTRUCTION_STANDARD_V2": {"name": "건설 STANDARD",  "monthly": 145000},
    "CONSTRUCTION_PREMIUM_V2":  {"name": "건설 PREMIUM",   "monthly": 385000},
    "CONSTRUCTION_CUSTOM_V2":   {"name": "건설 CUSTOM",    "monthly": None},
}

_AGENCY_MONTHLY_LOW  = 1_500_000   # 대행사 하한
_AGENCY_MONTHLY_HIGH = 3_000_000   # 대행사 상한


# ─── 유틸 ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_penalty(amount: float) -> str:
    """과태료 금액을 한국어 단위로 표시."""
    if amount <= 0:
        return "법령 기준"
    if amount >= 100_000_000:
        v = amount / 100_000_000
        return f"{int(v):,}억원" if v == int(v) else f"{v:.1f}억원"
    if amount >= 10_000:
        v = amount / 10_000
        return f"{int(v):,}만원"
    return f"{int(amount):,}원"


# ─── DB 조회 ────────────────────────────────────────────────────────────────

def _fetch_row(token: str) -> Dict[str, Any]:
    sb = get_supabase()
    res = (
        sb.table("anonymous_diagnosis_results")
        .select("*")
        .eq("public_token", token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")
    row = res.data[0]

    exp = row.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if _now() > exp_dt:
                raise HTTPException(status_code=410, detail="만료된 진단 결과입니다.")
        except HTTPException:
            raise
        except Exception:
            pass
    return row


# ─── TOP 5 리스크 추출 ──────────────────────────────────────────────────────

def _get_top5(full: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    penalty_amount 기준 TOP 5 리스크 추출.
    우선순위: rules_table → key_obligations → 카테고리별 required 리스트
    """
    def _parse_items(items: Optional[list]) -> List[Dict[str, Any]]:
        result = []
        for r in (items or []):
            if not isinstance(r, dict):
                continue
            amt = float(r.get("penalty_amount") or 0)
            result.append({
                "title": (
                    r.get("rule_name") or r.get("title") or
                    r.get("obligation") or r.get("name") or "법적 의무 사항"
                ),
                "law": (
                    r.get("law_name") or r.get("law") or
                    r.get("law_short_name") or "-"
                ),
                "penalty": (
                    r.get("penalty_text") or r.get("punishment") or
                    (_format_penalty(amt) if amt > 0 else "-")
                ),
                "amount": amt,
            })
        return result

    candidates: List[Dict[str, Any]] = []

    # 1순위: rules_table
    candidates = _parse_items(full.get("rules_table"))

    # 2순위: key_obligations
    if not candidates:
        candidates = _parse_items(full.get("key_obligations"))

    # 3순위: 카테고리별 required 리스트
    if not candidates:
        for key in ("appointment_required", "inspection_required",
                    "action_required", "report_required"):
            candidates.extend(_parse_items(full.get(key)))

    # 중복 제거 (title 앞 30자 기준)
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for c in candidates:
        key = c["title"][:30]
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    deduped.sort(key=lambda x: x["amount"], reverse=True)
    return deduped[:5]


# ─── 플랜 추천 ──────────────────────────────────────────────────────────────

def _recommend_plan(
    sector: str,
    severity: str,
    obl_cnt: int,
    workers: int,
) -> Tuple[str, Dict[str, Any]]:
    """diagnosis_plan_recommend.py 함수 재사용 (코드 중복 0줄)."""
    try:
        from routers.diagnosis_plan_recommend import (
            _recommend_industry,
            _recommend_building,
            _recommend_construction,
        )
        if sector == "INDUSTRY":
            code, _ = _recommend_industry(severity, obl_cnt, workers)
        elif sector == "BUILDING":
            code, _ = _recommend_building(severity, obl_cnt, workers)
        elif sector == "CONSTRUCTION":
            code, _ = _recommend_construction(severity, obl_cnt, workers)
        else:
            code = "INDUSTRY_STARTER_V2"
    except Exception as e:
        log.warning(f"[proposal-pdf] 플랜 추천 오류 (fallback): {e}")
        code = "INDUSTRY_STARTER_V2"
    return code, _PLANS.get(code, {"name": "맞춤 플랜", "monthly": None})


# ─── Jinja2 컨텍스트 빌드 ───────────────────────────────────────────────────

def _build_context(row: Dict[str, Any]) -> Dict[str, Any]:
    input_data: Dict[str, Any] = row.get("input_data") or {}
    partial:    Dict[str, Any] = row.get("partial_result") or {}
    full:       Dict[str, Any] = row.get("full_result") or {}

    # 섹터 정규화
    raw_sector = str(
        input_data.get("sector") or
        full.get("sector") or
        partial.get("sector") or
        "INDUSTRY"
    ).upper()
    sector       = SECTOR_NORMALIZE.get(raw_sector, raw_sector)
    sector_label = SECTOR_LABEL.get(raw_sector, "산업")

    # 기본 정보
    company_name = (
        input_data.get("company_name") or
        input_data.get("site_kind") or
        "귀 사업장"
    )
    report_date = _now().strftime("%Y년 %m월 %d일")
    workers     = int(
        input_data.get("workers") or
        input_data.get("worker_count") or
        0
    )

    # 요약 수치
    summary      = partial.get("summary") or full.get("summary") or {}
    total        = int(summary.get("total")   or full.get("applicable_count") or 0)
    appointment  = int(summary.get("appointment") or 0)
    inspection   = int(summary.get("inspection")  or 0)
    action       = int(summary.get("action")       or 0)
    report_notify = (
        int(summary.get("report") or 0) +
        int(summary.get("notify") or 0)
    )

    # 위험도·법령 수
    risk_level = str(
        partial.get("risk_level") or full.get("risk_level") or "MEDIUM"
    ).upper()
    law_count = len(
        partial.get("law_badges") or full.get("law_badges") or []
    )

    # 최대 과태료 산출
    all_rules_flat: List[Dict[str, Any]] = []
    for key in ("appointment_required", "inspection_required",
                "action_required", "report_required"):
        all_rules_flat.extend(full.get(key) or [])
    all_rules_flat.extend(full.get("rules_table") or [])
    all_rules_flat.extend(full.get("key_obligations") or [])
    max_penalty = max(
        (float(r.get("penalty_amount") or 0) for r in all_rules_flat),
        default=0.0,
    )
    max_penalty_text = _format_penalty(max_penalty)

    # TOP 5
    top5 = _get_top5(full)

    # 중대재해법
    csia_applicable = workers >= 50

    # 플랜 추천
    plan_code, plan_info = _recommend_plan(
        sector, risk_level, total, workers
    )
    monthly = plan_info.get("monthly")
    plan_price = f"월 {monthly:,}원" if monthly else "맞춤 견적"

    # 연간 절감액 (대행사 대비)
    monthly_plan = monthly or 149_000
    annual_savings_low  = max(0, int((_AGENCY_MONTHLY_LOW  - monthly_plan) * 12 / 10_000))
    annual_savings_high = max(0, int((_AGENCY_MONTHLY_HIGH - monthly_plan) * 12 / 10_000))

    return {
        # 기본
        "company_name": company_name,
        "report_date":  report_date,
        "sector_label": sector_label,
        "sector":       sector,
        "risk_level":   risk_level,
        "workers":      workers,
        "report_no":    str(row.get("public_token", ""))[:8].upper(),
        # 요약
        "total":         total,
        "appointment":   appointment,
        "inspection":    inspection,
        "action":        action,
        "report_notify": report_notify,
        "law_count":     law_count,
        "max_penalty_text": max_penalty_text,
        # 리스크
        "top5": top5,
        # 중처법
        "csia_applicable": csia_applicable,
        # 플랜
        "recommended_plan_name":    plan_info.get("name", ""),
        "recommended_plan_price":   plan_price,
        "recommended_plan_monthly": monthly or 0,
        "plan_code": plan_code,
        # 비용 비교
        "annual_savings_low":  annual_savings_low,
        "annual_savings_high": annual_savings_high,
    }


# ─── Jinja2 렌더링 ──────────────────────────────────────────────────────────

def _render_html(context: Dict[str, Any]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates",
        )
        env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=False,
        )
        template = env.get_template("proposal_pdf.html")
        return template.render(**context)
    except Exception as e:
        log.error(f"[proposal-pdf] 템플릿 렌더링 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"템플릿 렌더링 실패: {e}",
        )


# ─── xhtml2pdf PDF 생성 ─────────────────────────────────────────────────────

def _generate_pdf(html: str) -> bytes:
    try:
        from xhtml2pdf import pisa
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="xhtml2pdf 라이브러리가 설치되어 있지 않습니다.",
        )

    buf = io.BytesIO()
    result = pisa.pisaDocument(
        io.BytesIO(html.encode("utf-8")),
        buf,
        encoding="utf-8",
    )
    if result.err:
        raise HTTPException(
            status_code=500,
            detail=f"PDF 생성 실패: {result.err}",
        )
    return buf.getvalue()


# ─── 엔드포인트 ─────────────────────────────────────────────────────────────

@router.get("/proposal-pdf/{public_token}")
def get_proposal_pdf(public_token: str):
    """
    기안용 PDF 생성 — 결재권자용 3페이지 리스크 보고서

    공개 엔드포인트 (인증 불필요).
    public_token 자체가 접근 제어 역할을 합니다.

    Page 1: 경영진 요약 + 위험도 + TOP 5 리스크
    Page 2: 비용 비교 + 중대재해법 경고
    Page 3: TAI 소개 + 도입 4단계 + 추천 플랜 견적

    Returns:
        application/pdf — StreamingResponse
    """
    row     = _fetch_row(public_token)
    context = _build_context(row)
    html    = _render_html(context)
    pdf     = _generate_pdf(html)

    filename = f"TAI_proposal_{context['report_no']}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf)),
            "Cache-Control": "no-store",
        },
    )
