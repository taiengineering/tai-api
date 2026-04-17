# routers/diagnosis_transform.py — v1.0.1 (BE-08)
# Transform 레이어: result_data JSONB 읽기 전용 → FN-06 표준 응답 변환
# 원칙: legal_engine.py 미수정, 엔진 직접 호출 금지, result_data 읽기 전용
#
# v1.0.1: import 경로 수정 (db.supabase_client), auth 의존성 제거
# v1.0.0: 초기 구현

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional, List, Dict

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis/transform", tags=["BE-08 Transform"])

# ─────────────────────────────────────────
# 상수
# ─────────────────────────────────────────
CATEGORY_MAP = {
    "appointment": "선임", "inspection": "점검",
    "report": "신고", "notify": "보고",
    "action": "조치", "education": "교육",
    "document": "서류",
}

SAAS_MIN_ANNUAL = {
    "BUILDING": 59000 * 10,      # 기본관리 10개월 (연간 2개월 무료)
    "INDUSTRY": 79000 * 10,
    "MANUFACTURING": 79000 * 10,
    "CONSTRUCTION": 145000 * 10,
}

THRESHOLDS = [
    (50,  "중대재해법 적용"),
    (100, "안전보건관리체제 강화"),
    (300, "안전관리자 추가 선임"),
    (500, "안전관리자 전담 전환"),
]


# ─────────────────────────────────────────
# Transform 핵심 함수
# ─────────────────────────────────────────
def _build_headline(rd: dict) -> dict:
    summary = rd.get("summary") or {}
    total = summary.get("total", 0) if isinstance(summary, dict) else 0
    law_badges = rd.get("law_badges") or rd.get("applicable_law_categories") or []
    risk = (rd.get("risk_level") or "LOW").upper()
    return {
        "risk_level": risk,
        "applicable_count": total,
        "law_count": len(law_badges),
        "law_names": law_badges,
        "summary_text": f"{len(law_badges)}개 법령에서 {total}건의 의무사항이 발견되었습니다."
    }


def _build_obligations(rd: dict) -> list:
    obligations = []
    cat_keys = [
        ("appointment_required", "appointment", "선임"),
        ("inspection_required", "inspection", "점검"),
        ("action_required", "action", "조치"),
        ("report_required", "report", "신고"),
    ]
    for key, cat, label in cat_keys:
        items = rd.get(key, [])
        if items:
            obligations.append({
                "category": cat,
                "category_label": label,
                "count": len(items),
                "items": items
            })
    return obligations


def _build_warnings(rd: dict) -> list:
    warnings = []
    ctx = rd.get("facility_context") or {}
    workers = int(ctx.get("worker_count") or ctx.get("employee_count") or 0)
    for threshold, msg in THRESHOLDS:
        diff = threshold - workers
        if 0 < diff <= 5:
            warnings.append({
                "level": "DANGER",
                "message": f"근로자 {workers}명 — {threshold}명 도달 시 {msg} ({diff}명 차이)"
            })
    # 건설 construction_summary 경고
    cs = rd.get("construction_summary")
    if cs and cs.get("safety_manager_required"):
        warnings.append({
            "level": "WARN",
            "message": f"안전관리자 선임 의무 — {cs.get('safety_manager_basis', '')}"
        })
    return warnings


def _build_exposure(rd: dict) -> dict:
    total = 0
    items = []
    for cat_key in ["appointment_required", "inspection_required", "action_required", "report_required"]:
        for rule in rd.get(cat_key, []):
            ps = rule.get("penalty_summary") or rule.get("penalty_amount") or ""
            if not ps:
                continue
            # 숫자 추출 시도
            import re
            nums = re.findall(r'[\d,]+', str(ps).replace(',', ''))
            for n in nums:
                try:
                    val = int(n)
                    if val >= 10000:  # 1만원 이상만
                        total += val
                        items.append({
                            "law": rule.get("law_name", ""),
                            "article": rule.get("law_article", ""),
                            "amount": val,
                            "type": "과태료"
                        })
                        break
                except ValueError:
                    continue
    return {"total_penalty_krw": total, "penalty_items": items}


def _build_roi(exposure_total: int, sector: str) -> dict:
    annual = SAAS_MIN_ANNUAL.get(sector.upper(), 79000 * 10)
    ratio = round(exposure_total / annual, 1) if annual > 0 and exposure_total > 0 else 0
    return {
        "annual_subscription": annual,
        "total_exposure": exposure_total,
        "roi_ratio": ratio,
        "message": f"연 구독료 대비 {ratio}배 리스크 감소" if ratio > 0 else "과태료 정보 부족"
    }


def _build_schedule(rd: dict) -> dict:
    insp = rd.get("inspection_schedule_ready") or {}
    return {
        "periodic_count": insp.get("periodic_count", 0),
        "before_work_count": insp.get("before_work_count", 0),
        "on_demand_count": insp.get("on_demand_count", 0),
        "periodic": insp.get("periodic", []),
        "before_work": insp.get("before_work", []),
    }


def transform_result(raw: dict, sector: str) -> dict:
    headline = _build_headline(raw)
    obligations = _build_obligations(raw)
    warnings = _build_warnings(raw)
    exposure = _build_exposure(raw)
    roi = _build_roi(exposure["total_penalty_krw"], sector)
    schedule = _build_schedule(raw)
    return {
        "headline": headline,
        "obligations": obligations,
        "warnings": warnings,
        "exposure": exposure,
        "roi": roi,
        "inspection_schedule": schedule,
        "construction_summary": raw.get("construction_summary"),
        "facility_context": raw.get("facility_context"),
    }


# ─────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────
@router.get("/{diagnosis_id}")
async def get_transformed_result(diagnosis_id: str):
    """진단 ID 기반 Transform 결과 조회"""
    supabase = get_supabase()
    try:
        res = supabase.table("factory_diagnosis_results").select(
            "id, factory_id, sector, result_data, created_at"
        ).eq("id", diagnosis_id).single().execute()
    except Exception:
        raise HTTPException(404, "진단 결과 없음")
    if not res.data:
        raise HTTPException(404, "진단 결과 없음")

    row = res.data
    result_data = row.get("result_data") or {}
    sector = row.get("sector") or ""
    transformed = transform_result(result_data, sector)

    return {
        "status": "success",
        "data": {
            "diagnosis_id": diagnosis_id,
            "factory_id": row.get("factory_id"),
            "sector": sector,
            "evaluated_at": row.get("created_at"),
            "engine_version": result_data.get("engine_version", "5.6.8"),
            **transformed
        }
    }


@router.get("/latest/{factory_id}")
async def get_latest_transformed(factory_id: str):
    """시설의 최신 진단 결과 Transform 조회"""
    supabase = get_supabase()
    try:
        res = supabase.table("factory_diagnosis_results").select(
            "id, factory_id, sector, result_data, created_at"
        ).eq("factory_id", factory_id).eq(
            "is_latest", True
        ).order("created_at", desc=True).limit(1).execute()
    except Exception:
        raise HTTPException(404, "진단 결과 없음")
    if not res.data:
        raise HTTPException(404, "진단 결과 없음")

    row = res.data[0]
    result_data = row.get("result_data") or {}
    sector = row.get("sector") or ""
    transformed = transform_result(result_data, sector)

    return {
        "status": "success",
        "data": {
            "diagnosis_id": row["id"],
            "factory_id": factory_id,
            "sector": sector,
            "evaluated_at": row.get("created_at"),
            "engine_version": result_data.get("engine_version", "5.6.8"),
            **transformed
        }
    }
