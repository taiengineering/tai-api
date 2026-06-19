# routers/diagnosis_transform.py — v1.0.2 (BE-08)
# v1.0.1: import 경로 수정 + anonymous_diagnosis.py 호환 함수 추가
# v1.0.2: (WO-TRANSFORM-COLUMN-FIX-001) factory_diagnosis_results 스키마 불일치 수정
#   - SELECT에서 실재하지 않는 컬럼 제거: tier / company_name / user_id
#   - 실재 컬럼 추가: created_by / factory_id
#   - 권한 체크 user_id → created_by (b2: 소유자 확인, 우회 금지)
#   - tier/company_name은 _build_transform이 result_data 폴백으로 이미 처리
# Transform 레이어: result_data JSONB 읽기 전용 → FN-06 표준 응답 변환
# 원칙: legal_engine.py 미수정, 엔진 직접 호출 금지, result_data 읽기 전용

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.auth import get_current_user
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis/transform", tags=["BE-08 Transform"])

SCHEMA_VERSION = "v2026.04"
VERSION = "1.0.2"  # anonymous_diagnosis.py에서 참조


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def _safe_dict(val: Any) -> dict:
    """None이면 빈 dict, dict면 그대로, 그 외 {"value": val}."""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    return {"value": val}


# ─────────────────────────────────────────
# 응답 모델
# ─────────────────────────────────────────
class HeadlineModel(BaseModel):
    summary: str
    severity: str

class ObligationModel(BaseModel):
    id: str
    category: str
    title: str
    risk_level: str
    description: str
    evidence: list[str]
    action_url: Optional[str] = None
    auto_schedulable: bool = False

class WarningModel(BaseModel):
    level: str
    message: str

class RoiModel(BaseModel):
    penalty_max_krw: int
    subscription_annual_krw: int
    roi_ratio: float
    breakeven_days: int

class ScheduleMonthModel(BaseModel):
    month: int
    count: int
    items: list[str]

class NextActionModel(BaseModel):
    label: str
    url: str
    type: str

class TransformResponse(BaseModel):
    diagnosis_id: str
    sector: str
    tier: str
    company_name: str
    generated_at: str
    schema_version: str
    headline: HeadlineModel
    obligations: list[ObligationModel]
    warnings: list[WarningModel]
    roi: Optional[RoiModel] = None
    inspection_schedule: list[ScheduleMonthModel]
    next_actions: list[NextActionModel]


# ─────────────────────────────────────────
# 핵심 Transform 함수
# ─────────────────────────────────────────
CATEGORY_MAP = {
    "appointment": "선임", "선임": "선임",
    "inspection":  "점검", "점검": "점검",
    "report":      "신고", "신고": "신고",
    "education":   "교육", "교육": "교육",
    "document":    "서류", "서류": "서류",
}
RISK_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


def _severity_from_risk_summary(rd: dict) -> str:
    rs = rd.get("risk_summary") or {}
    if isinstance(rs, dict):
        level = (rs.get("overall_level") or rs.get("level") or "").upper()
        if level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            return level
    rc = rd.get("rule_count") or 0
    if rc >= 30:  return "CRITICAL"
    if rc >= 15:  return "HIGH"
    if rc >= 5:   return "MEDIUM"
    return "LOW"


def _extract_headline(rd: dict, rule_count: int = 0) -> dict:
    """폴백 체인: headline → headline_message → summary.headline → 자동생성.
    anonymous_diagnosis.py에서 (full, rule_count) 형태로 호출."""
    hl = rd.get("headline")
    if isinstance(hl, dict):
        return {
            "summary": hl.get("summary") or hl.get("text") or "진단 결과를 확인하세요.",
            "severity": (hl.get("severity") or _severity_from_risk_summary(rd)).upper(),
        }
    msg = rd.get("headline_message") or ""
    if not msg:
        summ = rd.get("summary") or {}
        if isinstance(summ, dict):
            msg = summ.get("headline") or summ.get("text") or ""
    if not msg:
        rc = rule_count or rd.get("rule_count") or rd.get("applicable_count") or 0
        msg = f"총 {rc}개 법령 의무가 확인됐습니다. 상세 내용을 검토하세요."
    return {"summary": msg, "severity": _severity_from_risk_summary(rd)}


def _normalize_category(raw: str) -> str:
    return CATEGORY_MAP.get((raw or "").lower().strip(), "서류")


def _evidence_text_list(item: dict) -> list[str]:
    """TAI 내부 evidence: text 배열만 (Check 계약 변환은 별도 어댑터)."""
    ev = item.get("evidence") or item.get("legal_basis") or []
    if isinstance(ev, str):
        return [ev] if ev.strip() else []
    if not isinstance(ev, list):
        return []
    return [str(x) for x in ev if x]


def _obligation_from_item(item: dict, *, group_category: str = "") -> dict:
    cat = _normalize_category(group_category or item.get("category") or item.get("type") or "")
    title = (
        item.get("obligation_summary")
        or item.get("title")
        or item.get("name")
        or item.get("item")
    )
    law_name = str(item.get("law_name") or "").strip()
    rule_type = str(item.get("rule_type") or "").strip()
    evidence = _evidence_text_list(item)
    if not evidence and law_name:
        law_art = str(item.get("law_article") or "").strip()
        ref = " ".join(p for p in (law_name, law_art) if p)
        if ref:
            evidence = [ref]
    return {
        "id": str(item.get("rule_id") or item.get("id") or uuid.uuid4()),
        "category": cat,
        "title": str(title or "의무사항"),
        "law_name": law_name,
        "rule_type": rule_type,
        "risk_level": (item.get("risk_level") or item.get("severity") or "MEDIUM").upper(),
        "description": str(item.get("description") or item.get("remarks") or item.get("detail") or ""),
        "evidence": evidence,
        "action_url": item.get("action_url"),
        "auto_schedulable": bool(item.get("auto_schedulable") or item.get("schedulable") or False),
    }


def _is_obligation_wrapper(obj: dict) -> bool:
    items = obj.get("items")
    return isinstance(items, list) and bool(items)


def _extract_obligations(rd: dict) -> list[dict]:
    raw_list: list = []
    for key in ("obligations", "key_obligations", "mandatory_obligations", "critical_obligations"):
        candidate = rd.get(key)
        if isinstance(candidate, list) and candidate:
            raw_list = candidate
            break

    if not raw_list:
        for cat_key, cat_label in CATEGORY_MAP.items():
            items = rd.get(f"{cat_key}_items") or rd.get(f"{cat_label}_항목") or []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        raw_list.append({"category": cat_label, "title": item,
                                         "risk_level": "MEDIUM", "description": item})
                    elif isinstance(item, dict):
                        item.setdefault("category", cat_label)
                        raw_list.append(item)

    result = []
    for obj in raw_list:
        if isinstance(obj, str):
            result.append({
                "id": str(uuid.uuid4()), "category": "서류",
                "title": obj, "law_name": "", "rule_type": "",
                "risk_level": "MEDIUM",
                "description": obj, "evidence": [],
            })
            continue
        if not isinstance(obj, dict):
            continue
        if _is_obligation_wrapper(obj):
            group_cat = str(obj.get("category") or obj.get("label") or "")
            for item in obj["items"]:
                if isinstance(item, str):
                    result.append({
                        "id": str(uuid.uuid4()),
                        "category": _normalize_category(group_cat),
                        "title": item,
                        "law_name": "",
                        "rule_type": "",
                        "risk_level": "MEDIUM",
                        "description": item,
                        "evidence": [],
                    })
                elif isinstance(item, dict):
                    result.append(_obligation_from_item(item, group_category=group_cat))
            continue
        result.append(_obligation_from_item(obj))

    result.sort(key=lambda o: RISK_ORDER.get(o.get("risk_level", ""), 0), reverse=True)
    return result


def _extract_warnings(rd: dict) -> list[dict]:
    result = []

    def _add(raw: Any, default_level: str = "WARN") -> None:
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    result.append({"level": default_level, "message": item})
                elif isinstance(item, dict):
                    lvl = (item.get("level") or item.get("severity") or default_level).upper()
                    msg = item.get("message") or item.get("text") or item.get("content") or ""
                    if msg:
                        result.append({"level": lvl, "message": str(msg)})
        elif isinstance(raw, dict):
            for k, v in raw.items():
                _add(v, default_level)
        elif isinstance(raw, str) and raw:
            result.append({"level": default_level, "message": raw})

    _add(rd.get("warnings"),                    "WARN")
    _add(rd.get("urgent_action_items"),          "DANGER")
    _add(rd.get("construction_specific_tips"),   "INFO")
    _add(rd.get("age_warnings"),                 "WARN")
    return result


def _extract_exposure(rd: dict, rule_count: int = 0) -> dict:
    """anonymous_diagnosis.py에서 호출하는 exposure 추출 함수."""
    exp_raw = rd.get("exposure") or {}
    penalty = 0
    if isinstance(exp_raw, dict):
        penalty = exp_raw.get("penalty_max_krw") or exp_raw.get("total_exposure_krw") or 0
    if not penalty:
        penalty = rd.get("penalty_risk") or rd.get("total_exposure_krw") or 0
    if not penalty:
        roi_raw = rd.get("roi") or {}
        penalty = roi_raw.get("annual_penalty_risk_krw") or roi_raw.get("penalty_max_krw") or 0
    if not penalty:
        rc = rule_count or rd.get("rule_count") or rd.get("applicable_count") or 0
        penalty = int(rc) * 3_000_000
    return {
        "penalty_max_krw": int(penalty),
        "rule_count": rule_count or rd.get("rule_count") or 0,
    }


def _extract_roi(rd: dict) -> Optional[dict]:
    roi_raw = rd.get("roi") or {}
    sub_annual = roi_raw.get("subscription_annual_krw") or roi_raw.get("annual_subscription_krw") or 0

    exp_raw = rd.get("exposure") or {}
    penalty = 0
    if isinstance(exp_raw, dict):
        penalty = exp_raw.get("penalty_max_krw") or exp_raw.get("total_exposure_krw") or 0
    if not penalty:
        penalty = rd.get("penalty_risk") or rd.get("total_exposure_krw") or 0
    if not penalty:
        penalty = roi_raw.get("annual_penalty_risk_krw") or roi_raw.get("penalty_max_krw") or 0
    if not penalty:
        rc = rd.get("rule_count") or 0
        penalty = rc * 3_000_000

    if not penalty:
        return None

    roi_ratio = roi_raw.get("roi_ratio") or (round(penalty / sub_annual, 1) if sub_annual else 0)
    breakeven = roi_raw.get("breakeven_days") or (round(sub_annual / penalty * 365) if penalty else 0)

    return {
        "penalty_max_krw": int(penalty),
        "subscription_annual_krw": int(sub_annual),
        "roi_ratio": float(roi_ratio),
        "breakeven_days": int(breakeven),
    }


def _extract_inspection_schedule(rd: dict) -> list[dict]:
    """anonymous_diagnosis.py에서 호출하는 점검 스케줄 추출 (별칭)."""
    return _extract_schedule(rd)


def _extract_schedule(rd: dict) -> list[dict]:
    raw = None
    for key in ("inspection_schedule", "inspection_schedule_ready", "inspection_schedule_summary"):
        candidate = rd.get(key)
        if isinstance(candidate, list) and candidate:
            raw = candidate
            break

    if not raw:
        return [{"month": m, "count": 0, "items": []} for m in range(1, 13)]

    result = []
    existing_months: set = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        month = int(item.get("month") or 0)
        if month < 1 or month > 12:
            continue
        items = item.get("items") or item.get("inspection_items") or []
        if isinstance(items, str):
            items = [items]
        count = int(item.get("count") or len(items))
        result.append({"month": month, "count": count, "items": list(items)})
        existing_months.add(month)

    for m in range(1, 13):
        if m not in existing_months:
            result.append({"month": m, "count": 0, "items": []})
    result.sort(key=lambda s: s["month"])
    return result


def _extract_next_actions(rd: dict, diagnosis_id: str) -> list[dict]:
    raw = rd.get("next_actions") or []
    result = []
    if isinstance(raw, list):
        for act in raw:
            if isinstance(act, dict):
                result.append({
                    "label": act.get("label") or act.get("text") or "바로가기",
                    "url": act.get("url") or "#",
                    "type": act.get("type") or "secondary",
                })
    if not result:
        result.append({
            "label": "ROI 대시보드 보기",
            "url": f"/diagnosis/roi/{diagnosis_id}",
            "type": "primary",
        })
    return result


def _build_transform(row: dict) -> dict:
    rd: dict = row.get("result_data") or {}
    diag_id = str(row.get("id") or "")
    schema_ver = rd.get("schema_version") or rd.get("version") or "unknown"
    # tier/company_name은 테이블 컬럼이 아님 → result_data 폴백 (v1.0.2)
    company_name = rd.get("company_name") or rd.get("factory_name") or "(정보없음)"
    sector = str(row.get("sector") or rd.get("sector") or "BUILDING").upper()
    tier   = str(rd.get("tier") or "FREE").upper()

    generated_at = ""
    if row.get("created_at"):
        try:
            dt = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            generated_at = dt.strftime("%Y년 %m월 %d일 %H:%M")
        except Exception:
            generated_at = str(row["created_at"])

    return {
        "diagnosis_id": diag_id,
        "sector": sector,
        "tier": tier,
        "company_name": company_name,
        "generated_at": generated_at,
        "schema_version": schema_ver,
        "headline": _extract_headline(rd),
        "obligations": _extract_obligations(rd),
        "warnings": _extract_warnings(rd),
        "roi": _extract_roi(rd),
        "inspection_schedule": _extract_schedule(rd),
        "next_actions": _extract_next_actions(rd, diag_id),
    }


# ─────────────────────────────────────────
# 공통 DB 조회
# v1.0.2: SELECT 컬럼을 factory_diagnosis_results 실재 컬럼으로 교정.
#   실재 컬럼: id, factory_id, sector, result_data, created_at, created_by, is_latest
#   권한 체크: created_by 기준 (b2, 우회 금지)
# ─────────────────────────────────────────
async def _fetch_row_by_id(diagnosis_id: str, user_id: str) -> dict:
    supabase = get_supabase()
    res = (
        supabase.table("factory_diagnosis_results")
        .select("id, factory_id, sector, created_at, result_data, created_by")
        .eq("id", diagnosis_id)
        .single()
        .execute()
    )
    row = res.data
    if not row:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")
    # b2: created_by 기준 소유자 확인 (우회 금지)
    if str(row.get("created_by") or "") != str(user_id):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return row


async def _fetch_latest_row(factory_id: str, sector: Optional[str],
                            stage: Optional[str], user_id: str) -> dict:
    supabase = get_supabase()
    q = (
        supabase.table("factory_diagnosis_results")
        .select("id, factory_id, sector, created_at, result_data, created_by")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .limit(1)
    )
    if sector:
        q = q.eq("sector", sector.upper())
    # stage 파라미터는 tier 컬럼이 없으므로 diagnosis_stage로 매핑하지 않고 무시.
    # (호환 유지: 인자는 받되 필터하지 않음. tier 컬럼 부재 — v1.0.2)
    res = q.execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="해당 시설의 진단 결과가 없습니다.")
    row = res.data[0]
    # b2: created_by 기준 소유자 확인 (우회 금지)
    if str(row.get("created_by") or "") != str(user_id):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return row


# ─────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────
@router.get("/{diagnosis_id}", summary="[BE-08] ID 기반 Transform")
async def transform_by_id(
    diagnosis_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = await _fetch_row_by_id(diagnosis_id, str(current_user["id"]))
    result = _build_transform(row)
    logger.info(f"[BE-08] transform_by_id: diagnosis_id={diagnosis_id}")
    return result


@router.get("/latest/{factory_id}", summary="[BE-08] 시설 최신 진단 Transform")
async def transform_latest(
    factory_id: str,
    sector: Optional[str] = Query(None),
    stage:  Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    row = await _fetch_latest_row(factory_id, sector, stage, str(current_user["id"]))
    result = _build_transform(row)
    logger.info(f"[BE-08] transform_latest: factory_id={factory_id}")
    return result
