"""
routers/diagnosis_report.py — v2.0.0

유료 진단 상세 PDF 생성 엔드포인트
  GET /diagnosis/report-pdf/{public_token}

v2.0.0 (2026-04-20):
  - xhtml2pdf → Gotenberg Chromium PDF 엔진 전환
  - _replace_css_vars() 제거 (Gotenberg는 CSS 변수 지원)
v1.0.1 (2026-04-19):
  - xhtml2pdf CSS 변수(var()) 미지원 → _replace_css_vars() 자동 치환
  - _extract_max_penalty 징역 우선 로직 유지
v1.0.0 (2026-04-18):
  - 최초 생성
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단리포트"])

VERSION = "2.0.0"

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://tai-gotenberg.internal:3000")

# 무료 tier — PDF 생성 차단 대상
FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE",
    "free", "FREE",
})

# 섹터 한글 라벨
SECTOR_LABEL: Dict[str, str] = {
    "BUILDING":      "건물",
    "INDUSTRIAL":    "산업",
    "INDUSTRY":      "산업",
    "CONSTRUCTION":  "건설",
    "MANUFACTURING": "산업(제조)",
    "SPECIAL_FACILITY": "특정시설",
}

# 의무유형 한글 라벨
OB_LABEL: Dict[str, str] = {
    "APPOINT": "선임",
    "INSPECT": "점검",
    "ACTION":  "조치",
    "REPORT":  "보고",
    "NOTIFY":  "신고",
}

# 추천 플랜 매핑
RECOMMEND_PLAN: Dict[str, Dict[str, str]] = {
    "BUILDING_V2":          {"name": "건물 소형 플랜",  "price": "월 59,000원~"},
    "BUILDING_LARGE_V2":    {"name": "건물 대형 플랜",  "price": "월 145,000원~"},
    "INDUSTRY_V2":          {"name": "산업 STARTER",   "price": "월 79,000원~"},
    "INDUSTRY_STANDARD":    {"name": "산업 BUSINESS",  "price": "월 149,000원~"},
    "INDUSTRY_PREMIUM":     {"name": "산업 PRO",       "price": "월 249,000원~"},
    "CONSTRUCTION":         {"name": "건설 STANDARD",  "price": "월 145,000원~"},
    "CONSTRUCTION_PREMIUM": {"name": "건설 PREMIUM",   "price": "월 385,000원~"},
}


# ───────────────────────────────────────────────────────────
# 헬퍼
# ───────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _report_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y년 %m월 %d일")


def _ob_label(ob_type: str) -> str:
    return OB_LABEL.get(ob_type, ob_type)


def _enrich_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """rules_table 각 항목에 ob_label 추가."""
    for r in rules:
        r["ob_label"] = _ob_label(r.get("obligation_type") or "")
    return rules


def _load_compiler_report_tables(supabase, session_id: Optional[str]) -> Dict[str, Any]:
    """Compiler 산출물 — diagnosis_session.id 기준 (없으면 빈 리스트)."""
    empty: Dict[str, Any] = {"candidates": [], "penalties": [], "schedule_hints": []}
    if not session_id:
        return empty
    try:
        empty["candidates"] = (
            supabase.table("diagnosis_candidate").select("*").eq("session_id", session_id).limit(400).execute().data
            or []
        )
        empty["penalties"] = (
            supabase.table("diagnosis_penalty_link").select("*").eq("session_id", session_id).limit(200).execute().data
            or []
        )
        empty["schedule_hints"] = (
            supabase.table("diagnosis_schedule_hint").select("*").eq("session_id", session_id).limit(200).execute().data
            or []
        )
    except Exception as ex:
        log.warning("[REPORT PDF] compiler tables 조회 생략: %s", ex)
    return empty


def _build_law_groups(
    rules: List[Dict[str, Any]],
    max_groups: int = 10,
) -> tuple[List[Dict[str, Any]], int]:
    """
    rules_table → law_name 기준 그룹핑, 건수 내림차순 정렬.
    max_groups 초과 법령은 본문 제외 (부록 A로 안내).
    반환: (law_groups, remaining_law_count)
    """
    order: List[str] = []
    groups: Dict[str, List] = {}
    for r in rules:
        law = r.get("law_name") or "기타"
        if law not in groups:
            groups[law] = []
            order.append(law)
        groups[law].append(r)

    # 건수 내림차순 정렬
    sorted_laws = sorted(order, key=lambda k: len(groups[k]), reverse=True)
    main_laws = sorted_laws[:max_groups]
    remaining = max(0, len(sorted_laws) - max_groups)

    law_groups = [
        {"law_name": law, "rules": groups[law]}
        for law in main_laws
    ]
    return law_groups, remaining


def _build_top5_risks(
    rules: List[Dict[str, Any]],
    appointment: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    TOP 5 리스크 항목 구성:
      1. 선임 의무 우선
      2. 과태료 있는 항목
      3. 나머지 채우기
    """
    seen: set = set()
    result: List[Dict[str, Any]] = []

    def _add(r: Dict[str, Any]) -> None:
        key = (r.get("law_name"), r.get("law_article"), r.get("obligation_type"))
        if key not in seen and len(result) < 5:
            seen.add(key)
            result.append({
                "title":          r.get("obligation_summary") or "",
                "law_ref":        f"{r.get('law_name','')} {r.get('law_article','')}".strip(),
                "penalty_summary": r.get("penalty_summary") or "",
            })

    for r in appointment:
        _add(r)
    for r in rules:
        if r.get("penalty_summary"):
            _add(r)
    for r in rules:
        _add(r)

    return result


def _extract_max_penalty(rules: List[Dict[str, Any]]) -> str:
    """penalty_summary 중 가장 큰 금액 텍스트 반환 (단순 첫 번째 유의미 값 사용)."""
    # 중대재해 먼저
    for r in rules:
        ps = (r.get("penalty_summary") or "").strip()
        if ps and "징역" in ps:
            return ps
    for r in rules:
        ps = (r.get("penalty_summary") or "").strip()
        if ps:
            return ps
    return ""


def _render_html(template_vars: Dict[str, Any]) -> str:
    """Jinja2 템플릿 렌더링."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    # templates 디렉터리 (main.py 기준)
    tmpl_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    tmpl_dir = os.path.abspath(tmpl_dir)

    env = Environment(
        loader=FileSystemLoader(tmpl_dir),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("diagnosis_report_paid.html")
    return template.render(**template_vars)


async def _generate_pdf(html: str) -> bytes:
    """Gotenberg Chromium PDF 엔진으로 HTML → PDF 변환."""
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
    """
    supabase = get_supabase()

    # 1. 진단 결과 조회
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, public_token, tier_code, full_result, input_data, status, expires_at")
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
            detail="상세 PDF는 유료 진단 결과에만 제공됩니다. 유료 결제 후 이용해 주세요."
        )

    # 4. 데이터 추출
    full_result = rec.get("full_result") or {}
    input_data  = rec.get("input_data") or {}

    sector       = full_result.get("sector") or input_data.get("sector") or "BUILDING"
    sector_upper = sector.upper()
    sector_label = SECTOR_LABEL.get(sector_upper, sector)

    # rules_table 추출 (여러 키 시도)
    rules_raw: List[Dict[str, Any]] = (
        full_result.get("rules_table")
        or full_result.get("applicable_rules")
        or full_result.get("obligations")
        or []
    )

    # appointment / inspection 분리
    appointment_raw = (
        full_result.get("appointment_required")
        or [r for r in rules_raw if isinstance(r, dict) and r.get("obligation_type") == "APPOINT"]
    )
    inspection_raw = (
        full_result.get("inspection_required")
        or [r for r in rules_raw if isinstance(r, dict) and r.get("obligation_type") == "INSPECT"]
    )

    # dict가 아닌 항목 필터링 (str 배열 방어)
    rules_raw = [r for r in rules_raw if isinstance(r, dict)]
    appointment_raw = [r for r in appointment_raw if isinstance(r, dict)]
    inspection_raw = [r for r in inspection_raw if isinstance(r, dict)]

    # ob_label 추가
    all_rules        = _enrich_rules(list(rules_raw))
    appointment_rules = _enrich_rules(list(appointment_raw))
    inspection_rules  = _enrich_rules(list(inspection_raw))

    # 5. 전처리
    law_groups, remaining_law_count = _build_law_groups(all_rules, max_groups=10)
    top5_risks = _build_top5_risks(all_rules, appointment_rules)
    max_penalty_text = _extract_max_penalty(all_rules)

    summary = full_result.get("summary") or {}
    total           = full_result.get("applicable_count") or summary.get("total") or len(all_rules)
    appointment_cnt = summary.get("appointment") or len(appointment_rules)
    inspection_cnt  = summary.get("inspection")  or len(inspection_rules)
    action_cnt      = summary.get("action")       or 0
    report_cnt      = (summary.get("report") or 0) + (summary.get("notify") or 0)
    law_badges      = full_result.get("law_badges") or []
    law_count       = len(law_badges) or len({r.get("law_name") for r in all_rules if r.get("law_name")})
    risk_level      = full_result.get("risk_level") or "MEDIUM"

    # CSIA (중대재해처벌법) 적용 여부
    worker_count     = input_data.get("workers") or input_data.get("worker_count") or 0
    csia_applicable  = int(worker_count or 0) >= 5

    # Compiler 연동 세션 (match_info JSON 등)
    session_id: Optional[str] = None
    mi = full_result.get("match_info")
    if isinstance(mi, dict):
        session_id = mi.get("diagnosis_session_id") or mi.get("session_id")
    if not session_id:
        session_id = full_result.get("diagnosis_session_id") or full_result.get("session_id")
    compiler_pack = _load_compiler_report_tables(supabase, session_id)

    # 추천 플랜
    plan_info = RECOMMEND_PLAN.get(tier_code, {})

    # 6. 입력 데이터 추출
    company_name = (
        input_data.get("company_name")
        or full_result.get("company_name")
        or "사업장"
    )
    receipt_no = public_token[:8].upper()

    # 7. Jinja2 렌더링
    template_vars: Dict[str, Any] = {
        # 기본 정보
        "company_name":          company_name,
        "report_date":           _report_date_str(),
        "receipt_no":            receipt_no,
        "sector_label":          sector_label,
        "report_type":           "유료 상세 진단",
        "engine_version":        full_result.get("engine_version") or "v1",
        # 시설 개요
        "business_no":           input_data.get("business_no") or "",
        "ceo_name":              input_data.get("ceo_name") or "",
        "address":               input_data.get("address") or "",
        "industry_type":         input_data.get("industry_type") or input_data.get("ksic_major") or "",
        "worker_count":          worker_count or "",
        "area":                  input_data.get("floor_area") or input_data.get("total_floor_area") or "",
        "floors":                input_data.get("floor_count") or "",
        "equip_summary":         input_data.get("equip_summary") or "",
        "hazard_summary":        input_data.get("hazard_summary") or "",
        # 요약 숫자
        "total":                 total,
        "appointment_count":     appointment_cnt,
        "inspection_count":      inspection_cnt,
        "action_count":          action_cnt,
        "report_notify_count":   report_cnt,
        "law_count":             law_count,
        "risk_level":            risk_level,
        "max_penalty_text":      max_penalty_text,
        "csia_applicable":       csia_applicable,
        # 데이터 리스트
        "top5_risks":            top5_risks,
        "law_groups":            law_groups,
        "remaining_law_count":   remaining_law_count,
        "all_rules":             all_rules,
        "inspection_rules":      inspection_rules,
        "appointment_rules":     appointment_rules,
        # SaaS 추천
        "recommended_plan_name":  plan_info.get("name") or "",
        "recommended_plan_price": plan_info.get("price") or "",
        # Compiler (diagnosis_session 연동 시)
        "compiler_session_id":   session_id or "",
        "compiler_candidates":   compiler_pack["candidates"],
        "compiler_penalties":    compiler_pack["penalties"],
        "compiler_schedule_hints": compiler_pack["schedule_hints"],
    }

    try:
        html = _render_html(template_vars)
    except Exception as e:
        log.error("[REPORT PDF] Jinja2 렌더링 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"리포트 렌더링 실패: {e}")

    # 8. PDF 생성
    try:
        pdf_bytes = await _generate_pdf(html)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[REPORT PDF] PDF 변환 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")

    filename = f"tai_diagnosis_{receipt_no}.pdf"
    log.info(
        "[REPORT PDF] 생성 완료 — token=%s tier=%s size=%d bytes",
        receipt_no, tier_code, len(pdf_bytes)
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "X-Report-Token": receipt_no,
            "X-Tier-Code": tier_code,
        },
    )
