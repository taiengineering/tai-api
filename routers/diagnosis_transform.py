"""
routers/diagnosis_transform.py — v1.0.0

BE-08: 진단 결과 읽기 전용 Transform 레이어

원칙:
  - legal_engine.py 코드 미수정
  - DB result_data JSONB 읽기 전용 (쓰기 금지)
  - 엔진 출력을 표준 스키마로 가공하는 별도 레이어

API:
  GET /diagnosis/transform/{diagnosis_id}
  GET /diagnosis/transform/latest/{factory_id}

표준 출력 스키마:
  headline / obligations / warnings / exposure / inspection_schedule / roi

신규 DB 코럼 (Migration: be08_diagnosis_transform_columns):
  factory_diagnosis_results.expires_at
  factory_diagnosis_results.refund_at
  factory_diagnosis_results.refund_reason
  master_building_legal_rules.is_retroactive
"""
from __future__ import annotations
import logging
import math
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["Transform"])

VERSION = "1.0.0"


# ──────────────────────────────────────────────────────────────────────────
# 내부 도우미 함수
# ──────────────────────────────────────────────────────────────────────────

def _safe_int(v: Any, default: int = 0) -> int:
    try: return int(v) if v is not None else default
    except (TypeError, ValueError): return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


def _safe_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _extract_headline(rd: dict, rule_count: int) -> dict:
    """
    result_data에서 headline 추출.
    키 우선순위: headline > headline_message > summary > 자동생성
    """
    h = rd.get("headline")
    if isinstance(h, dict):
        return {
            "summary":  str(h.get("summary") or ""),
            "severity": str(h.get("severity") or _infer_severity(rd, rule_count)),
        }

    msg = (
        rd.get("headline_message")
        or (_safe_dict(rd.get("summary")).get("headline"))
        or f"적용된 의무 {rule_count}건 발견"
    )
    return {
        "summary":  str(msg),
        "severity": _infer_severity(rd, rule_count),
    }


def _infer_severity(rd: dict, rule_count: int) -> str:
    rs = _safe_dict(rd.get("risk_summary"))
    if _safe_int(rs.get("critical")) > 0: return "CRITICAL"
    if _safe_int(rs.get("high"))     > 0: return "HIGH"
    if _safe_int(rs.get("medium"))   > 0: return "MEDIUM"
    if _safe_int(rs.get("low"))      > 0: return "LOW"
    rc = rule_count or 0
    if rc >= 100: return "HIGH"
    if rc >= 50:  return "MEDIUM"
    return "LOW"


def _extract_obligations(rd: dict) -> list:
    """
    obligations / key_obligations / mandatory_obligations / critical_obligations 우선순위로 수집.
    is_retroactive 필드는 master_building_legal_rules에서 옵.
    legacy 형식(category/items 구조)도 평탄화.
    """
    for key in ("obligations", "key_obligations", "mandatory_obligations", "critical_obligations"):
        val = rd.get(key)
        if isinstance(val, list) and val:
            # category/items 랜로 문자라면 평탄화
            flat: list = []
            for item in val:
                if isinstance(item, dict) and "items" in item:
                    # legacy: {category, label, items: [...]}
                    flat.extend(item["items"] if isinstance(item["items"], list) else [])
                else:
                    flat.append(item)
            return flat
    return []


def _extract_warnings(rd: dict) -> list:
    """
    warnings / urgent_action_items / construction_specific_tips / age_warnings 통합.
    이미 v2026.04로 변환된 데이터라면 warnings에 통합되어 있음.
    """
    result: list = list(_safe_list(rd.get("warnings")))

    for item in _safe_list(rd.get("urgent_action_items")):
        if isinstance(item, str):
            result.append({"code": "URGENT", "message": item, "level": "HIGH"})
        elif isinstance(item, dict):
            result.append(item)

    for item in _safe_list(rd.get("construction_specific_tips")):
        result.append({"code": "CONSTRUCTION_TIP", "message": str(item), "level": "INFO"})

    age = rd.get("age_warnings")
    if isinstance(age, list):
        for item in age:
            result.append({"code": "AGE_WARNING", "message": str(item), "level": "HIGH"})
    elif isinstance(age, dict):
        for k, v in age.items():
            if k != "age_years" and v is not None:
                result.append({"code": "AGE_WARNING", "message": f"{k}: {v}", "level": "HIGH"})

    return result


def _extract_exposure(rd: dict, rule_count: int) -> dict:
    """
    볈사rc 노출 정보 추출.
    우선순위: exposure > penalty_risk > roi.annual_penalty_risk_krw > rule_count 추정
    """
    # 1순위: 직접 exposure
    exp = rd.get("exposure")
    if isinstance(exp, dict) and exp.get("penalty_max_krw"):
        return {
            "penalty_max_krw":  _safe_int(exp["penalty_max_krw"]),
            "criminal_risk":    str(exp.get("criminal_risk") or ""),
            "current_exposure": str(exp.get("current_exposure") or ""),
            "source":           "exposure",
        }

    # 2순위: penalty_risk (legacy PAID2+ 부층 데이터)
    pr = _safe_dict(rd.get("penalty_risk"))
    if pr.get("max_fine_krw"):
        max_fine = _safe_int(pr["max_fine_krw"])
        return {
            "penalty_max_krw":  max_fine,
            "criminal_risk":    str(pr.get("criminal_risk") or ""),
            "current_exposure": "높음" if max_fine >= 50_000_000 else "중간",
            "source":           "penalty_risk",
        }

    # 3순위: total_exposure_krw (legacy)
    texp = rd.get("total_exposure_krw")
    if texp:
        amount = _safe_int(texp)
        return {
            "penalty_max_krw":  amount,
            "criminal_risk":    "",
            "current_exposure": "높음" if amount >= 50_000_000 else "중간",
            "source":           "total_exposure_krw",
        }

    # 4순위: roi에서
    roi = _safe_dict(rd.get("roi"))
    if roi.get("annual_penalty_risk_krw"):
        amount = _safe_int(roi["annual_penalty_risk_krw"])
        return {
            "penalty_max_krw":  amount,
            "criminal_risk":    "",
            "current_exposure": "높음" if amount >= 50_000_000 else "중간",
            "source":           "roi_estimate",
        }

    # 5순위: rule_count 추정
    estimate = (rule_count or 0) * 3_000_000
    return {
        "penalty_max_krw":  estimate,
        "criminal_risk":    "",
        "current_exposure": "높음" if estimate >= 50_000_000 else "중간",
        "source":           "rule_count_estimate",
    }


def _extract_inspection_schedule(rd: dict) -> dict:
    """
    점검 일정 요약 추출.
    우선순위: inspection_schedule > inspection_schedule_ready > inspection_schedule_summary
    """
    # v2026.04 표준 필드
    isch = rd.get("inspection_schedule")
    if isinstance(isch, dict) and isch:
        return isch

    # legal_engine.py diagnose_step1 출력 (inspection_schedule_ready)
    ready = _safe_dict(rd.get("inspection_schedule_ready"))
    if ready:
        return {
            "daily":      0,
            "weekly":     0,
            "monthly":    0,
            "quarterly":  0,
            "semiannual": 0,
            "annual":     0,
            "onetime":    0,
            "periodic_count":    _safe_int(ready.get("periodic_count")),
            "before_work_count": _safe_int(ready.get("before_work_count")),
            "on_demand_count":   _safe_int(ready.get("on_demand_count")),
        }

    # legacy PAID2+ (inspection_schedule_summary)
    summary = _safe_dict(rd.get("inspection_schedule_summary"))
    if summary:
        return {
            "daily":      _safe_int(summary.get("daily")),
            "weekly":     _safe_int(summary.get("weekly")),
            "monthly":    _safe_int(summary.get("monthly")),
            "quarterly":  _safe_int(summary.get("quarterly")),
            "semiannual": _safe_int(summary.get("semiannual")),
            "annual":     _safe_int(summary.get("annual")),
            "onetime":    _safe_int(summary.get("onetime")),
        }

    return {}


def _extract_roi(rd: dict) -> dict:
    """roi 필드 추출 (v2026.04/legacy 도일하게 복원)."""
    roi = _safe_dict(rd.get("roi"))
    if not roi:
        return {}
    return {
        "annual_penalty_risk_krw":   _safe_int(roi.get("annual_penalty_risk_krw")),
        "tai_safe_annual_cost_krw":  _safe_int(roi.get("tai_safe_annual_cost_krw")),
        "payback_days":              _safe_int(roi.get("payback_days")),
        "risk_reduction_percent":    _safe_float(roi.get("risk_reduction_percent")),
        "penalty_source":            str(roi.get("penalty_source") or "rule_count_estimate"),
    }


def _build_transform(diag: dict, factory: dict) -> dict:
    """
    factory_diagnosis_results 레코드 하나를 받아
    표준 Transform 응답 dict 반환.
    result_data를 읽기만 하고 쓰기는 절대 없음.
    """
    rd: dict = _safe_dict(diag.get("result_data"))
    rule_count: int = _safe_int(diag.get("rule_count"))

    return {
        "diagnosis_id":    str(diag["id"]),
        "factory_id":      str(diag["factory_id"]),
        "sector":          str(diag.get("sector") or ""),
        "diagnosis_stage": _safe_int(diag.get("diagnosis_stage")),
        "schema_version":  str(rd.get("schema_version") or diag.get("schema_version") or "legacy"),
        "created_at":      str(diag.get("created_at") or ""),
        "expires_at":      diag.get("expires_at"),
        "refund_at":       diag.get("refund_at"),
        "refund_reason":   diag.get("refund_reason"),
        "rule_count":      rule_count,

        # 그룹 A: 표준 스키마 섹션
        "headline":            _extract_headline(rd, rule_count),
        "obligations":         _extract_obligations(rd),
        "warnings":            _extract_warnings(rd),
        "exposure":            _extract_exposure(rd, rule_count),
        "inspection_schedule": _extract_inspection_schedule(rd),
        "roi":                 _extract_roi(rd),

        # 그룹 B: 보조 필드 (FN 렌더러 편의용)
        "risk_summary":     _safe_dict(rd.get("risk_summary")),
        "applicable_laws":  rd.get("applicable_laws") or [],
        "next_actions":     rd.get("next_actions") or [],
        "evidence":         rd.get("evidence") or [],
        "tier":             str(rd.get("tier") or ""),

        # 그룹 C: 시설 요약
        "factory": {
            "id":             str(factory.get("id") or ""),
            "name":           str(factory.get("name") or ""),
            "sector":         str(factory.get("sector") or ""),
            "employee_count": factory.get("employee_count"),
        },

        "transform_version": VERSION,
    }


def _fetch_diag_and_factory(supabase, diagnosis_id: str) -> tuple[dict, dict]:
    """diagnosis_id 기반으로 diagnosis + factory 레코드 동시 조회."""
    diag_res = (
        supabase.table("factory_diagnosis_results")
        .select(
            "id, factory_id, sector, diagnosis_stage, rule_count, "
            "result_data, schema_version, created_at, "
            "expires_at, refund_at, refund_reason"
        )
        .eq("id", diagnosis_id)
        .limit(1)
        .execute()
    )
    if not diag_res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = diag_res.data[0]
    fac_res = (
        supabase.table("factories")
        .select("id, name, sector, employee_count")
        .eq("id", diag["factory_id"])
        .limit(1)
        .execute()
    )
    factory = fac_res.data[0] if fac_res.data else {}
    return diag, factory


# ──────────────────────────────────────────────────────────────────────────
# GET /diagnosis/transform/{diagnosis_id}
# ──────────────────────────────────────────────────────────────────────────
@router.get("/transform/{diagnosis_id}")
def get_transform_by_id(diagnosis_id: str):
    """
    진단 ID 기반 Transform 응답.

    result_data JSONB를 읽기 전용으로 참조하여
    headline / obligations / warnings / exposure / inspection_schedule / roi
    표준 스키마로 원타임에 가공하여 반환.
    """
    supabase = get_supabase()
    diag, factory = _fetch_diag_and_factory(supabase, diagnosis_id)
    return {"status": "success", "data": _build_transform(diag, factory)}


# ──────────────────────────────────────────────────────────────────────────
# GET /diagnosis/transform/latest/{factory_id}
# ──────────────────────────────────────────────────────────────────────────
@router.get("/transform/latest/{factory_id}")
def get_transform_latest(
    factory_id: str,
    sector: Optional[str] = Query(None, description="섹터 필터 (BUILDING/INDUSTRY/CONSTRUCTION)"),
    stage: Optional[int]  = Query(None, description="진단 단계 필터 (1~4)"),
):
    """
    특정 시설의 최신 진단 원타임 Transform.

    sector / stage 쿼리파라미터로 필터 가능.
    필터 없으면 created_at DESC 최신 1건 반환.
    """
    supabase = get_supabase()

    q = (
        supabase.table("factory_diagnosis_results")
        .select(
            "id, factory_id, sector, diagnosis_stage, rule_count, "
            "result_data, schema_version, created_at, "
            "expires_at, refund_at, refund_reason"
        )
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
    )
    if sector:
        q = q.eq("sector", sector.strip().upper())
    if stage is not None:
        q = q.eq("diagnosis_stage", stage)

    res = q.limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    diag = res.data[0]
    fac_res = (
        supabase.table("factories")
        .select("id, name, sector, employee_count")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    factory = fac_res.data[0] if fac_res.data else {}

    return {"status": "success", "data": _build_transform(diag, factory)}
