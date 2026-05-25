"""
routers/diagnosis_result_web.py — v1.1.0

유료/무료 진단 결과 웹 조회 API (JSON)
  GET /diagnosis/result/{public_token}
  GET /diagnosis/paid-result/{public_token}

v1.1.0: BE-08 Transform 정제 함수 연동 (rules_table dedupe + FAMILY→한글)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from services.diagnosis_runtime_step1 import enrich_rules_with_candidate_slots
from routers.diagnosis_transform import (
    CATEGORY_MAP,
    _extract_obligations,
    _extract_warnings,
    _normalize_category,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단결과웹"])

FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE",
    "free", "FREE",
})

SECTOR_LABEL = {
    "BUILDING": "건물", "INDUSTRY": "산업",
    "CONSTRUCTION": "건설", "MANUFACTURING": "산업(제조)",
}

# FAMILY / obligation 코드 → diagnosis_transform CATEGORY_MAP 키
_FAMILY_STEM_TO_CATEGORY_KEY: Dict[str, str] = {
    "APPOINT": "appointment",
    "APPOINTMENT": "appointment",
    "DESIGNATE": "appointment",
    "INSPECT": "inspection",
    "MEASURE": "inspection",
    "VERIFY": "inspection",
    "TEST": "inspection",
    "REPORT": "report",
    "NOTIFY": "report",
    "REGISTER": "report",
    "PERMIT": "report",
    "PRESERVE": "document",
    "RECORD": "document",
    "MANAGE": "document",
    "INSTALL": "document",
    "MAINTAIN": "document",
    "TRAINING": "education",
    "EDUCATION": "education",
    "ACTION": "document",
    "MANDATORY": "document",
    "PERMISSIVE": "document",
    "PROHIBITION": "document",
}

_OBLIGATION_TYPE_TO_CATEGORY_KEY: Dict[str, str] = {
    "APPOINT": "appointment",
    "INSPECT": "inspection",
    "REPORT": "report",
    "NOTIFY": "report",
    "ACTION": "document",
    "OTHER": "document",
}


def _rule_kind_key(row: Dict[str, Any]) -> str:
    """dedupe 키: law_article + rule_kind (FAMILY / obligation_type / category)."""
    for field in (
        "rule_kind",
        "source_action_family",
        "obligation_family",
        "obligation_type",
        "rule_type",
    ):
        val = (row.get(field) or "").strip().upper()
        if val:
            return val
    cat = (row.get("category") or "").strip().upper()
    if cat.endswith("_FAMILY") or cat.endswith("_TASK_CANDIDATE"):
        return cat
    for eng, kor in CATEGORY_MAP.items():
        if kor == row.get("category"):
            return eng.upper()
    return cat or "UNKNOWN"


def _law_article_key(row: Dict[str, Any]) -> str:
    law = (row.get("law_name") or "").strip()
    art = (row.get("law_article") or "").strip()
    return f"{law}|{art}"


def _category_key_for_row(row: Dict[str, Any]) -> str:
    """FAMILY 코드·obligation_type → CATEGORY_MAP 영문 키."""
    raw = (
        row.get("rule_kind")
        or row.get("source_action_family")
        or row.get("obligation_family")
        or ""
    ).strip().upper()
    if raw.endswith("_FAMILY"):
        stem = raw[: -len("_FAMILY")]
        if stem in _FAMILY_STEM_TO_CATEGORY_KEY:
            return _FAMILY_STEM_TO_CATEGORY_KEY[stem]
    if raw.endswith("_TASK_CANDIDATE"):
        stem = raw.split("_TASK_CANDIDATE", 1)[0]
        if stem in _FAMILY_STEM_TO_CATEGORY_KEY:
            return _FAMILY_STEM_TO_CATEGORY_KEY[stem]
    obl = (row.get("obligation_type") or "").strip().upper()
    if obl in _OBLIGATION_TYPE_TO_CATEGORY_KEY:
        return _OBLIGATION_TYPE_TO_CATEGORY_KEY[obl]
    cat = (row.get("category") or "").strip().lower()
    if cat in CATEGORY_MAP:
        return cat
    kor = (row.get("category") or "").strip()
    for eng, label in CATEGORY_MAP.items():
        if label == kor:
            return eng
    return "document"


def _dedupe_rules_table(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for row in rules_table:
        key = (_law_article_key(row), _rule_kind_key(row))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _rule_row_to_obligation_src(row: Dict[str, Any]) -> Dict[str, Any]:
    cat_key = _category_key_for_row(row)
    law_ref = " ".join(
        p for p in ((row.get("law_name") or "").strip(), (row.get("law_article") or "").strip()) if p
    )
    return {
        "id": str(row.get("rule_id") or row.get("id") or ""),
        "category": cat_key,
        "type": cat_key,
        "title": (
            row.get("obligation_summary")
            or row.get("description")
            or row.get("remarks")
            or "의무사항"
        ),
        "name": row.get("obligation_summary") or row.get("description") or "",
        "description": row.get("remarks") or row.get("description") or "",
        "risk_level": row.get("risk_level") or "MEDIUM",
        "legal_basis": law_ref,
        "evidence": [law_ref] if law_ref else [],
    }


def _merge_obligation_into_rule_row(
    obligation: Dict[str, Any], original: Dict[str, Any]
) -> Dict[str, Any]:
    merged = dict(original)
    merged["category"] = obligation.get("category") or _normalize_category(
        _category_key_for_row(original)
    )
    merged["rule_kind"] = _rule_kind_key(original)
    merged["rule_kind_label"] = merged["category"]
    if obligation.get("title"):
        merged["obligation_summary"] = obligation["title"]
    if obligation.get("description"):
        merged["description"] = obligation["description"]
    return merged


def _refine_rules_table(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """dedupe → BE-08 _extract_obligations 정제 → rules_table 형태 복원."""
    deduped = _dedupe_rules_table(rules_table)
    if not deduped:
        return []

    lookup: Dict[str, Dict[str, Any]] = {}
    for row in deduped:
        rid = str(row.get("rule_id") or row.get("id") or "")
        if rid:
            lookup[rid] = row
        title_key = (row.get("obligation_summary") or row.get("description") or "")[:120]
        if title_key:
            lookup[f"title:{title_key}"] = row

    extracted = _extract_obligations(
        {"obligations": [_rule_row_to_obligation_src(r) for r in deduped]}
    )
    refined: List[Dict[str, Any]] = []
    for ob in extracted:
        oid = str(ob.get("id") or "")
        orig = lookup.get(oid) if oid else None
        if not orig:
            tkey = f"title:{(ob.get('title') or '')[:120]}"
            orig = lookup.get(tkey)
        if orig:
            refined.append(_merge_obligation_into_rule_row(ob, orig))
    return refined if refined else deduped


RECOMMEND_PLAN = {
    "BUILDING_V2":          {"name": "건물 소형 플랜",  "price": "월 59,000원~"},
    "BUILDING_LARGE_V2":    {"name": "건물 대형 플랜",  "price": "월 145,000원~"},
    "INDUSTRY_V2":          {"name": "산업 STARTER",   "price": "월 79,000원~"},
    "INDUSTRY_STANDARD":    {"name": "산업 BUSINESS",  "price": "월 149,000원~"},
    "INDUSTRY_PREMIUM":     {"name": "산업 PRO",       "price": "월 249,000원~"},
    "CONSTRUCTION":         {"name": "건설 STANDARD",  "price": "월 145,000원~"},
    "CONSTRUCTION_PREMIUM": {"name": "건설 PREMIUM",   "price": "월 385,000원~"},
}


@router.get("/result/{public_token}")
def get_diagnosis_result_web(public_token: str):
    """
    무료/유료 공통 진단 결과 웹 조회.
    free-diagnosis-result.html → GET /diagnosis/result/{token}
    """
    return _build_result_payload(public_token, free_preview_limit=5)


@router.get("/paid-result/{public_token}")
def get_paid_result_web(public_token: str):
    """
    유료 진단 결과 웹 조회.
    paid-diagnosis-result.html에서 fetch하여 인터랙티브 대시보드 렌더링.
    """
    return _build_result_payload(public_token, free_preview_limit=None)


def _build_result_payload(public_token: str, free_preview_limit: Optional[int]) -> Dict[str, Any]:
    supabase = get_supabase()

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

    if rec.get("status") != "ACTIVE":
        raise HTTPException(status_code=410, detail="비활성화된 진단 결과입니다.")

    tier_code = rec.get("tier_code") or ""
    is_free = tier_code in FREE_TIER_CODES or tier_code.endswith("_FREE") or "FREE" in tier_code.upper()

    full_result = rec.get("full_result") or {}
    input_data = rec.get("input_data") or {}

    sector = (full_result.get("sector") or input_data.get("sector") or "BUILDING").upper()
    sector_label = SECTOR_LABEL.get(sector, sector)

    raw_rules = [r for r in (full_result.get("rules_table") or []) if isinstance(r, dict)]
    rules_table = _refine_rules_table(raw_rules)
    warnings = _extract_warnings(full_result)

    inspection_required = [r for r in (full_result.get("inspection_required") or []) if isinstance(r, dict)]
    appointment_required = [r for r in (full_result.get("appointment_required") or []) if isinstance(r, dict)]
    enrich_rules_with_candidate_slots(
        supabase, rules_table + inspection_required + appointment_required
    )
    key_obligations = full_result.get("key_obligations") or []
    law_badges = full_result.get("law_badges") or []
    inspection_schedule = full_result.get("inspection_schedule_ready") or {}

    summary = full_result.get("summary") or {}
    total = full_result.get("applicable_count") or summary.get("total") or len(rules_table)
    risk_level = full_result.get("risk_level") or "MEDIUM"
    worker_count = input_data.get("workers") or input_data.get("worker_count") or 0

    law_groups: Dict[str, list] = {}
    for r in rules_table:
        law = r.get("law_name") or "기타"
        law_groups.setdefault(law, []).append(r)

    law_group_list = sorted(
        [{"law_name": k, "count": len(v), "rules": v} for k, v in law_groups.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    ob_counts: Dict[str, int] = {}
    for r in rules_table:
        label = r.get("category") or r.get("obligation_type") or "기타"
        ob_counts[label] = ob_counts.get(label, 0) + 1

    plan_info = RECOMMEND_PLAN.get(tier_code, {})
    company_name = input_data.get("company_name") or full_result.get("company_name") or "사업장"

    limit = free_preview_limit if is_free else None
    rules_out = rules_table[:limit] if limit else rules_table
    key_ob_out = key_obligations[:limit] if limit else key_obligations
    law_grp_out = law_group_list[:limit] if limit else law_group_list

    engine_version = full_result.get("engine_version") or "v3.0-runtime-compiler"

    return {
        "status": "success",
        "data": {
            "public_token": public_token,
            "tier_code": tier_code,
            "is_free": is_free,
            "sector": sector,
            "sector_label": sector_label,
            "company_name": company_name,
            "risk_level": risk_level,
            "risk_reason": full_result.get("risk_reason"),
            "applicable_count": total,
            "engine_version": engine_version,
            "summary": {
                "total": total,
                "inspection": summary.get("inspection") or len(inspection_required),
                "appointment": summary.get("appointment") or len(appointment_required),
                "action": summary.get("action") or 0,
                "report": (summary.get("report") or 0) + (summary.get("notify") or 0),
                "form_linked": summary.get("form_linked") or 0,
                "law_count": len(law_badges),
                "worker_count": worker_count,
                "csia_applicable": int(worker_count or 0) >= 5,
            },
            "obligation_counts": ob_counts,
            "warnings": warnings,
            "rules_table": rules_out,
            "appointment_required": appointment_required,
            "inspection_required": inspection_required,
            "law_badges": law_badges,
            "key_obligations": key_ob_out,
            "inspection_schedule": inspection_schedule if not is_free else {},
            "law_groups": law_grp_out,
            "input_data": {
                "company_name": company_name,
                "business_no": input_data.get("business_no") or "",
                "ceo_name": input_data.get("ceo_name") or "",
                "address": input_data.get("address") or "",
                "worker_count": worker_count,
                "floor_area": input_data.get("floor_area") or input_data.get("total_floor_area") or "",
            },
            "recommended_plan": plan_info,
            "pdf_url": f"/diagnosis/report-pdf/{public_token}",
        },
    }
