"""
routers/diagnosis_result_web.py — v1.3.0

유료/무료 진단 결과 웹 조회 API (JSON)
  GET /diagnosis/result/{public_token}
  GET /diagnosis/paid-result/{public_token}

v1.1.0: BE-08 Transform 정제 함수 연동 (rules_table dedupe + FAMILY→한글)
v1.2.0: 의무 제목/설명 표시 보정 — obligation_summary/remarks가 코드 토큰
        (예: "APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY")일 때 description의
        사람이 읽는 텍스트를 우선 사용. 엔진/판정 로직 미변경(표시 transform만).
v1.3.0: LEG(법령엔진) 결과 표시 변환 — LEG 파이프라인은 rules_table 대신
        obligations_raw(rich: enrichment/obligation_detail)를 저장한다.
        rules_table 부재 시 obligations_raw에서 '값 생성 없이' 페이지가 소비하는
        rules_table/summary 형태로 이미 추출된 값만 운반. 축1(Compiler) 경로 무변경.
        엔진·프론트·조립기 무변경(조회 시점 표시 transform만).
"""
from __future__ import annotations

import logging
import re
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

# 엔진이 obligation_summary/remarks에 넣는 코드 토큰 패턴.
# 예: "APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY", "INSPECT_FAMILY"
_TOKEN_RE = re.compile(r"_CANDIDATE|_FAMILY|^[A-Z][A-Z0-9_]*\s*:\s*[A-Z][A-Z0-9_]*$")


def _is_token(v: Any) -> bool:
    """사람이 읽는 문장이 아니라 코드 토큰이면 True."""
    s = (v or "").strip() if isinstance(v, str) else str(v or "").strip()
    if not s:
        return True
    return bool(_TOKEN_RE.search(s))


def _human_text(*cands: Any) -> str:
    """후보 중 코드 토큰이 아닌 첫 사람이 읽는 텍스트를 반환."""
    for c in cands:
        s = (c or "").strip() if isinstance(c, str) else str(c or "").strip()
        if s and not _is_token(s):
            return s
    return ""


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
    # 코드 토큰(obligation_summary/remarks)보다 사람이 읽는 description을 우선.
    human = _human_text(
        row.get("description"),
        row.get("obligation_summary"),
        row.get("remarks"),
        row.get("rule_name"),
    )
    return {
        "id": str(row.get("rule_id") or row.get("id") or ""),
        "category": cat_key,
        "type": cat_key,
        "title": human or "의무사항",
        "name": human or "",
        "description": human or "",
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
    # 사람이 읽는 텍스트로 obligation_summary/description를 보정.
    # 원본이 코드 토큰이면 정제된 obligation 텍스트로 덮어쓴다.
    human = _human_text(
        obligation.get("title"),
        obligation.get("description"),
        original.get("description"),
        original.get("obligation_summary"),
        original.get("remarks"),
    )
    if human:
        if _is_token(merged.get("obligation_summary")):
            merged["obligation_summary"] = human
        if _is_token(merged.get("description")):
            merged["description"] = human
    # remarks가 코드 토큰이면 화면 노출되지 않도록 비운다.
    if _is_token(merged.get("remarks")):
        merged["remarks"] = ""
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


# ─────────────────────────────────────────────────────────────
# LEG(법령엔진) 결과 표시 변환
#   LEG 파이프라인은 rules_table 대신 obligations_raw(rich)를 저장한다.
#   (obligations_raw[].enrichment / .obligation_detail = Check Layer 산출)
#   페이지(free-diagnosis-result)가 소비하는 rules_table/summary 형태로
#   '값 생성 없이' 이미 추출된 값만 운반한다. 엔진·프론트 무변경.
# ─────────────────────────────────────────────────────────────

# enrichment.obligation_type → 페이지 칩(OB_TYPE_LABEL: APPOINT/INSPECT/ACTION/REPORT/NOTIFY)
_LEG_TYPE_TO_PAGE: Dict[str, str] = {
    "APPOINT": "APPOINT",
    "INSPECT": "INSPECT",
    "REPORT": "REPORT",
    "NOTIFY": "NOTIFY",
    "ACTION": "ACTION",
    "TRAINING": "ACTION",   # 교육 → 조치 버킷(페이지 전용 칩 없음)
    "PROHIBIT": "ACTION",   # 금지 → 조치 버킷(페이지 전용 칩 없음)
}

# 페이지 obligation_type → summary 집계 버킷
_LEG_PAGE_TYPE_TO_SUMMARY: Dict[str, str] = {
    "APPOINT": "appointment",
    "INSPECT": "inspection",
    "ACTION": "action",
    "REPORT": "report",
    "NOTIFY": "notify",
}


def _leg_obligation_type(o: Dict[str, Any]) -> str:
    enr = o.get("enrichment") or {}
    raw = (enr.get("obligation_type") or "").strip().upper()
    return _LEG_TYPE_TO_PAGE.get(raw, "ACTION")


def _leg_rule_row(o: Dict[str, Any]) -> Dict[str, Any]:
    """obligations_raw 1건 → 페이지 rules_table 1행 (값 생성 없음)."""
    enr = o.get("enrichment") or {}
    det = o.get("obligation_detail") or {}
    law_name = (o.get("law_name") or "").strip()
    law_article = (o.get("law_article") or "").strip()
    # 의무 설명 = obligation_detail.what(실제 의무 문장). 없으면 법령명+조번호.
    what = (det.get("what") or "").strip()
    summary_text = what or " ".join(p for p in (law_name, law_article) if p)
    return {
        "law_name": law_name,
        "law_article": law_article,
        "obligation_type": _leg_obligation_type(o),
        "obligation_summary": summary_text,
        "description": summary_text,
        "inspection_cycle": (enr.get("inspection_cycle") or "").strip(),
        # trace (페이지 미표시, 감사용)
        "atom_id": o.get("atom_id") or "",
        "source": "LEG",
    }


def _leg_rules_from_obligations_raw(obligations_raw: List[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_atom: set = set()
    for o in obligations_raw:
        if not isinstance(o, dict):
            continue
        # 적용(APPLICABLE)만 표시. (필터 — 값 생성 아님)
        appl = (o.get("applicability") or "").strip().upper()
        if appl and appl != "APPLICABLE":
            continue
        aid = str(o.get("atom_id") or "")
        if aid and aid in seen_atom:
            continue
        if aid:
            seen_atom.add(aid)
        row = _leg_rule_row(o)
        if not (row["law_name"] or row["obligation_summary"]):
            continue
        rows.append(row)
    return rows


def _leg_summary_from_rules(rules: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"appointment": 0, "inspection": 0, "action": 0, "report": 0, "notify": 0}
    for r in rules:
        bucket = _LEG_PAGE_TYPE_TO_SUMMARY.get(r.get("obligation_type") or "", "action")
        counts[bucket] += 1
    counts["total"] = len(rules)
    counts["form_linked"] = 0
    return counts


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
    leg_summary: Optional[Dict[str, int]] = None
    if raw_rules:
        # 축1(Compiler) 결과: 기존 경로 무변경.
        rules_table = _refine_rules_table(raw_rules)
    else:
        # LEG 결과: rules_table 부재 → obligations_raw(rich)에서 표시용 rules_table 파생.
        # 값 생성 없음 — enrichment/obligation_detail의 이미 추출된 값만 운반.
        obligations_raw = [
            o for o in (full_result.get("obligations_raw") or []) if isinstance(o, dict)
        ]
        rules_table = _leg_rules_from_obligations_raw(obligations_raw)
        if rules_table:
            leg_summary = _leg_summary_from_rules(rules_table)
    warnings = _extract_warnings(full_result)

    inspection_required = [r for r in (full_result.get("inspection_required") or []) if isinstance(r, dict)]
    appointment_required = [r for r in (full_result.get("appointment_required") or []) if isinstance(r, dict)]
    if raw_rules:
        # candidate slot 보강은 축1 rows 전용(rule_id 기반). LEG rows는 미해당.
        enrich_rules_with_candidate_slots(
            supabase, rules_table + inspection_required + appointment_required
        )
    key_obligations = full_result.get("key_obligations") or []
    law_badges = full_result.get("law_badges") or []
    # LEG 결과의 law_badges는 빈약(≤1)한 경우가 많음 → 파생 rules_table의 실제 법령명으로 보강.
    if leg_summary is not None and len(law_badges) <= 1:
        _derived_badges: List[str] = []
        _seen_law: set = set()
        for r in rules_table:
            ln = (r.get("law_name") or "").strip()
            if ln and ln not in _seen_law:
                _seen_law.add(ln)
                _derived_badges.append(ln)
        if _derived_badges:
            law_badges = _derived_badges
    inspection_schedule = full_result.get("inspection_schedule_ready") or {}

    summary = full_result.get("summary") or leg_summary or {}
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
