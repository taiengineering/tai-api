"""
routers/diagnosis_transform.py — v1.0.0

BE-08: 진단 결과 Transform 레이어

원칙:
  - legal_engine.py 코드 절대 미수정
  - DB result_data JSONB 읽기 전용 (쓰기 금지)
  - 엔진 출력을 표준화하여 FN 레이어에 단일 스키마 제공

제공 API:
  GET /diagnosis/transform/{diagnosis_id}
  GET /diagnosis/transform/latest/{factory_id}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["Transform"])

VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────
# 소그 Transform 함수·유틸
# ─────────────────────────────────────────────────────────────────────────

def _safe_list(val: Any) -> list:
    return val if isinstance(val, list) else []


def _safe_dict(val: Any) -> dict:
    return val if isinstance(val, dict) else {}


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val or default)
    except (TypeError, ValueError):
        return default


def _safe_str(val: Any, default: str = "") -> str:
    return str(val) if val is not None else default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 1. headline 정제 ───────────────────────────────────────────────────────────────

def _transform_headline(rd: dict, rule_count: int) -> dict:
    """
    result_data 내 headline 추출
    v2026.04: headline.{summary, severity}
    legacy:   headline_message 또는 summary.headline 또는 자동 생성
    """
    headline = _safe_dict(rd.get("headline"))
    if headline.get("summary"):
        severity = str(headline.get("severity") or "LOW").upper()
        if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            severity = "LOW"
        return {"summary": headline["summary"], "severity": severity}

    # legacy 폴백
    summary = (
        rd.get("headline_message")
        or _safe_dict(rd.get("summary")).get("headline")
        or f"적용된 의무 {rule_count}건"
    )
    rs = _safe_dict(rd.get("risk_summary"))
    if _safe_int(rs.get("critical")) > 0: severity = "CRITICAL"
    elif _safe_int(rs.get("high"))  > 0: severity = "HIGH"
    elif _safe_int(rs.get("medium"))> 0: severity = "MEDIUM"
    else: severity = "LOW"
    return {"summary": _safe_str(summary), "severity": severity}


# ── 2. obligations 정제 ───────────────────────────────────────────────────────────

def _transform_obligations(rd: dict) -> list:
    """
    obligations / key_obligations / mandatory_obligations / critical_obligations
    우선순위 수집, 각 항목에 is_retroactive 포함
    is_retroactive는 obligation 객체 내에 이미 있으면 사용, 없으면 false
    """
    raw: list = []
    for key in ("obligations", "key_obligations",
                "mandatory_obligations", "critical_obligations"):
        val = rd.get(key)
        if isinstance(val, list) and val:
            raw = val
            break

    result = []
    for obl in raw:
        if not isinstance(obl, dict):
            continue
        item: dict = dict(obl)
        # is_retroactive 기본값 보종
        item.setdefault("is_retroactive", False)
        # penalty 정제
        pen = _safe_dict(item.get("penalty"))
        if pen:
            item["penalty"] = {
                "krw":      _safe_int(pen.get("krw")),
                "criminal": pen.get("criminal"),
                "type":     pen.get("type"),
            }
        result.append(item)
    return result


# ── 3. warnings 정제 ──────────────────────────────────────────────────────────────

def _transform_warnings(rd: dict) -> list:
    """
    v2026.04 warnings[] + legacy urgent_action_items / construction_specific_tips
    / age_warnings 데이터 통합
    각 항목을 {code, message, level} 구조로 표준화
    """
    merged: list = []

    # 이미 v2026.04 형식으로 변환된 warnings[]
    for item in _safe_list(rd.get("warnings")):
        if isinstance(item, dict):
            merged.append({
                "code":    _safe_str(item.get("code"),  "WARN"),
                "message": _safe_str(item.get("message")),
                "level":   _safe_str(item.get("level"), "INFO"),
            })
        elif isinstance(item, str):
            merged.append({"code": "WARN", "message": item, "level": "INFO"})

    # legacy urgent_action_items
    for item in _safe_list(rd.get("urgent_action_items")):
        merged.append({"code": "URGENT", "message": str(item), "level": "HIGH"})

    # legacy construction_specific_tips
    for item in _safe_list(rd.get("construction_specific_tips")):
        merged.append({"code": "CONSTRUCTION_TIP", "message": str(item), "level": "INFO"})

    # legacy age_warnings (object 또는 list)
    age = rd.get("age_warnings")
    if isinstance(age, list):
        for item in age:
            merged.append({"code": "AGE_WARNING", "message": str(item), "level": "HIGH"})
    elif isinstance(age, dict):
        for k, v in age.items():
            if k != "age_years" and v is not None:
                merged.append({"code": "AGE_WARNING", "message": f"{k}: {v}", "level": "HIGH"})

    return merged


# ── 4. exposure 정제 ──────────────────────────────────────────────────────────────

def _transform_exposure(rd: dict, rule_count: int) -> dict:
    """
    exposure 상실 점수 보리
    v2026.04: exposure.{penalty_max_krw, criminal_risk, current_exposure}
    legacy: penalty_risk.max_fine_krw 또는 total_exposure_krw 또는 roi.annual_penalty_risk_krw
    """
    exposure = _safe_dict(rd.get("exposure"))
    if exposure.get("penalty_max_krw"):
        return {
            "penalty_max_krw":   _safe_int(exposure["penalty_max_krw"]),
            "criminal_risk":     exposure.get("criminal_risk"),
            "current_exposure":  exposure.get("current_exposure"),
            "source":            "exposure",
        }

    # legacy penalty_risk
    penalty_risk = _safe_dict(rd.get("penalty_risk"))
    if penalty_risk.get("max_fine_krw"):
        return {
            "penalty_max_krw":  _safe_int(penalty_risk["max_fine_krw"]),
            "criminal_risk":    penalty_risk.get("criminal_risk"),
            "current_exposure": None,
            "source":           "penalty_risk",
        }

    # legacy total_exposure_krw
    total = rd.get("total_exposure_krw")
    if total:
        try:
            return {
                "penalty_max_krw":  int(total),
                "criminal_risk":    None,
                "current_exposure": None,
                "source":           "total_exposure_krw",
            }
        except (TypeError, ValueError):
            pass

    # roi 기반 추정
    roi = _safe_dict(rd.get("roi"))
    if roi.get("annual_penalty_risk_krw"):
        return {
            "penalty_max_krw":  _safe_int(roi["annual_penalty_risk_krw"]),
            "criminal_risk":    None,
            "current_exposure": "추정치",
            "source":           "roi_estimate",
        }

    # 없으면 rule_count 기반 보수적 추정
    return {
        "penalty_max_krw":  rule_count * 3_000_000,
        "criminal_risk":    None,
        "current_exposure": "추정치(룰 수 기반)",
        "source":           "rule_count_estimate",
    }


# ── 5. inspection_schedule 정제 ────────────────────────────────────────────────────────

def _transform_inspection_schedule(rd: dict) -> dict:
    """
    점검일정 요약 순서:
      1. result_data.inspection_schedule (v2026.04 표준 dict)
      2. result_data.inspection_schedule_ready (diagnose_step1 출력)
      3. result_data.inspection_schedule_summary (stage2 legacy)
    표준 출력:
      {daily, weekly, monthly, quarterly, semiannual, annual, onetime,
       periodic_count, before_work_count, on_demand_count}
    """
    # 1순위: 직접 inspection_schedule
    insp = _safe_dict(rd.get("inspection_schedule"))
    if insp:
        return {
            "daily":           _safe_int(insp.get("daily")),
            "weekly":          _safe_int(insp.get("weekly")),
            "monthly":         _safe_int(insp.get("monthly")),
            "quarterly":       _safe_int(insp.get("quarterly")),
            "semiannual":      _safe_int(insp.get("semiannual")),
            "annual":          _safe_int(insp.get("annual")),
            "onetime":         _safe_int(insp.get("onetime")),
            "periodic_count":  _safe_int(insp.get("periodic_count")),
            "before_work_count": _safe_int(insp.get("before_work_count")),
            "on_demand_count": _safe_int(insp.get("on_demand_count")),
            "source":          "inspection_schedule",
        }

    # 2순위: inspection_schedule_ready (step1 출력)
    ready = _safe_dict(rd.get("inspection_schedule_ready"))
    if ready:
        periodic  = _safe_list(ready.get("periodic"))
        before_wk = _safe_list(ready.get("before_work"))
        return {
            "daily":           0,
            "weekly":          sum(1 for r in periodic if _safe_str(r.get("inspection_cycle_code")) == "002"),
            "monthly":         sum(1 for r in periodic if _safe_str(r.get("inspection_cycle_code")) == "003"),
            "quarterly":       sum(1 for r in periodic if _safe_str(r.get("inspection_cycle_code")) == "004"),
            "semiannual":      sum(1 for r in periodic if _safe_str(r.get("inspection_cycle_code")) == "005"),
            "annual":          sum(1 for r in periodic if _safe_str(r.get("inspection_cycle_code")) == "006"),
            "onetime":         0,
            "periodic_count":  _safe_int(ready.get("periodic_count",  len(periodic))),
            "before_work_count": _safe_int(ready.get("before_work_count", len(before_wk))),
            "on_demand_count": _safe_int(ready.get("on_demand_count")),
            "source":          "inspection_schedule_ready",
        }

    # 3순위: inspection_schedule_summary (legacy stage2)
    summary = _safe_dict(rd.get("inspection_schedule_summary"))
    if summary:
        return {
            "daily":           _safe_int(summary.get("daily")),
            "weekly":          _safe_int(summary.get("weekly")),
            "monthly":         _safe_int(summary.get("monthly")),
            "quarterly":       _safe_int(summary.get("quarterly")),
            "semiannual":      _safe_int(summary.get("semi_annual") or summary.get("semiannual")),
            "annual":          _safe_int(summary.get("annual")),
            "onetime":         _safe_int(summary.get("one_time") or summary.get("onetime")),
            "periodic_count":  _safe_int(summary.get("total_periodic")),
            "before_work_count": _safe_int(summary.get("before_work")),
            "on_demand_count": _safe_int(summary.get("on_demand")),
            "source":          "inspection_schedule_summary",
        }

    # 없음: 빈 객체
    return {
        "daily": 0, "weekly": 0, "monthly": 0, "quarterly": 0,
        "semiannual": 0, "annual": 0, "onetime": 0,
        "periodic_count": 0, "before_work_count": 0, "on_demand_count": 0,
        "source": None,
    }


# ── 6. roi 정제 ───────────────────────────────────────────────────────────────────

def _transform_roi(rd: dict, rule_count: int) -> dict:
    """
    roi 정제
    v2026.04: roi.{annual_penalty_risk_krw, tai_safe_annual_cost_krw,
                    payback_days, risk_reduction_percent, penalty_source}
    변환 없이 구조만 브리지
    """
    roi = _safe_dict(rd.get("roi"))
    if roi:
        return {
            "annual_penalty_risk_krw":  _safe_int(roi.get("annual_penalty_risk_krw")),
            "tai_safe_annual_cost_krw": _safe_int(roi.get("tai_safe_annual_cost_krw")),
            "payback_days":             _safe_int(roi.get("payback_days")),
            "risk_reduction_percent":   roi.get("risk_reduction_percent"),
            "penalty_source":           roi.get("penalty_source", "roi"),
            "calculated_at":            roi.get("calculated_at"),
        }
    return {
        "annual_penalty_risk_krw":  rule_count * 3_000_000,
        "tai_safe_annual_cost_krw": None,
        "payback_days":             None,
        "risk_reduction_percent":   None,
        "penalty_source":           "rule_count_estimate",
        "calculated_at":            None,
    }


# ─────────────────────────────────────────────────────────────────────────
# 진단 레코드 → 완성 Transform 응답
# ─────────────────────────────────────────────────────────────────────────

def _build_transform_response(row: dict) -> dict:
    """
    DB 레코드 한 행을 받아 Transform 응답 dict 반환.
    result_data JSONB 라이트원치(raw) 읽기 전용.
    """
    rd: dict = row.get("result_data") or {}
    rule_count: int = _safe_int(row.get("rule_count"))

    # schema_version: column 또는 JSONB 내 키 검상
    schema_version = (
        row.get("schema_version")
        or rd.get("schema_version")
        or "legacy"
    )

    return {
        "meta": {
            "diagnosis_id":    str(row.get("id", "")),
            "factory_id":      str(row.get("factory_id", "")),
            "sector":          row.get("sector") or rd.get("sector", ""),
            "diagnosis_stage": row.get("diagnosis_stage"),
            "rule_count":      rule_count,
            "is_latest":       row.get("is_latest", False),
            "schema_version":  schema_version,
            "created_at":      str(row.get("created_at", "")),
            # BE-08 신규 컨테스트 코드
            "expires_at":      str(row["expires_at"]) if row.get("expires_at") else None,
            "refund_at":       str(row["refund_at"])  if row.get("refund_at")  else None,
            "refund_reason":   row.get("refund_reason"),
            "transform_version": VERSION,
            "transformed_at":  _now_iso(),
        },
        "headline":            _transform_headline(rd, rule_count),
        "obligations":         _transform_obligations(rd),
        "warnings":            _transform_warnings(rd),
        "exposure":            _transform_exposure(rd, rule_count),
        "inspection_schedule": _transform_inspection_schedule(rd),
        "roi":                 _transform_roi(rd, rule_count),
        "risk_summary":        {
            "critical": _safe_int(_safe_dict(rd.get("risk_summary")).get("critical")),
            "high":     _safe_int(_safe_dict(rd.get("risk_summary")).get("high")),
            "medium":   _safe_int(_safe_dict(rd.get("risk_summary")).get("medium")),
            "low":      _safe_int(_safe_dict(rd.get("risk_summary")).get("low")),
        },
        "applicable_laws":  _safe_list(rd.get("applicable_laws")),
        "next_actions":     _safe_list(rd.get("next_actions")),
        "evidence":         _safe_list(rd.get("evidence")),
    }


# ─────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────

SELECT_COLS = (
    "id, factory_id, sector, diagnosis_stage, rule_count, "
    "is_latest, result_data, created_at, "
    "schema_version, expires_at, refund_at, refund_reason"
)


@router.get("/transform/{diagnosis_id}")
def get_transform_by_id(diagnosis_id: str):
    """
    단일 진단 결과 Transform.
    result_data JSONB 읽기 전용 — DB 쓰기 없음.
    """
    supabase = get_supabase()
    res = (
        supabase.table("factory_diagnosis_results")
        .select(SELECT_COLS)
        .eq("id", diagnosis_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 레코드를 찾을 수 없습니다.")

    data = _build_transform_response(res.data[0])
    return {"status": "success", "data": data}


@router.get("/transform/latest/{factory_id}")
def get_transform_latest(
    factory_id: str,
    sector: Optional[str] = Query(None, description="BUILDING|INDUSTRY|CONSTRUCTION (생략 시 최근 1건)"),
    stage:  Optional[int] = Query(None, description="진단 단계 필터 (1~4)"),
):
    """
    시설의 최신 진단 결과 Transform.
    sector/stage 필터 선택 가능.
    result_data JSONB 읽기 전용 — DB 쓰기 없음.
    """
    supabase = get_supabase()

    q = (
        supabase.table("factory_diagnosis_results")
        .select(SELECT_COLS)
        .eq("factory_id", factory_id)
        .eq("is_latest", True)
        .order("created_at", desc=True)
    )
    if sector:
        q = q.eq("sector", sector.strip().upper())
    if stage is not None:
        q = q.eq("diagnosis_stage", stage)

    res = q.limit(1).execute()
    if not res.data:
        raise HTTPException(
            status_code=404,
            detail="해당 조건에 맞는 진단 결과를 찾을 수 없습니다."
        )

    data = _build_transform_response(res.data[0])
    return {"status": "success", "data": data}
