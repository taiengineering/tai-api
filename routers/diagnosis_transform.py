# routers/diagnosis_transform.py — v1.0.0 (BE-08)
# Transform 레이어: result_data JSONB 읽기 전용 → FN-06 표준 응답 변환
# 원칙: legal_engine.py 미수정, 엔진 직접 호출 금지, result_data 읽기 전용
#
# 엔드포인트:
#   GET /diagnosis/transform/{diagnosis_id}              ID 기반 Transform
#   GET /diagnosis/transform/latest/{factory_id}          시설 최신 진단 Transform
#     ?sector=BUILDING|INDUSTRY|CONSTRUCTION
#     ?stage=FREE|PAID1|PAID2|PAID3

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dependencies import get_current_user
from supabase_client import supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis/transform", tags=["BE-08 Transform"])

SCHEMA_VERSION = "v2026.04"


# ─────────────────────────────────────────
# 응답 모델
# ─────────────────────────────────────────
class HeadlineModel(BaseModel):
    summary: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL


class ObligationModel(BaseModel):
    id: str
    category: str          # 선임 | 점검 | 신고 | 교육 | 서류
    title: str
    risk_level: str        # LOW | MEDIUM | HIGH | CRITICAL
    description: str
    evidence: list[str]
    action_url: Optional[str] = None
    auto_schedulable: bool = False


class WarningModel(BaseModel):
    level: str             # INFO | WARN | DANGER
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
    type: str              # primary | secondary


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
    """risk_summary → severity 추정"""
    rs = rd.get("risk_summary") or {}
    if isinstance(rs, dict):
        level = (rs.get("overall_level") or rs.get("level") or "").upper()
        if level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            return level
    # fallback: rule_count 추정
    rc = rd.get("rule_count") or 0
    if rc >= 30:  return "CRITICAL"
    if rc >= 15:  return "HIGH"
    if rc >= 5:   return "MEDIUM"
    return "LOW"


def _extract_headline(rd: dict) -> HeadlineModel:
    """폴백 체인: headline → headline_message → summary.headline → 자동생성"""
    hl = rd.get("headline")
    if isinstance(hl, dict):
        return HeadlineModel(
            summary=hl.get("summary") or hl.get("text") or "진단 결과를 확인하세요.",
            severity=(hl.get("severity") or _severity_from_risk_summary(rd)).upper()
        )
    msg = rd.get("headline_message") or ""
    if not msg:
        summ = rd.get("summary") or {}
        if isinstance(summ, dict):
            msg = summ.get("headline") or summ.get("text") or ""
    if not msg:
        rc = rd.get("rule_count") or 0
        msg = f"총 {rc}개 법령 의무가 확인됐습니다. 상세 내용을 검토하세요."
    return HeadlineModel(summary=msg, severity=_severity_from_risk_summary(rd))


def _normalize_category(raw: str) -> str:
    return CATEGORY_MAP.get((raw or "").lower().strip(), "서류")


def _extract_obligations(rd: dict) -> list[ObligationModel]:
    """폴백: obligations → key_obligations → mandatory_obligations → critical_obligations, legacy 평탄화"""
    import uuid

    raw_list: list = []
    for key in ("obligations", "key_obligations", "mandatory_obligations", "critical_obligations"):
        candidate = rd.get(key)
        if isinstance(candidate, list) and candidate:
            raw_list = candidate
            break

    # legacy: category/items 구조
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

    result: list[ObligationModel] = []
    for obj in raw_list:
        if isinstance(obj, str):
            result.append(ObligationModel(
                id=str(uuid.uuid4()), category="서류",
                title=obj, risk_level="MEDIUM",
                description=obj, evidence=[]
            ))
            continue
        if not isinstance(obj, dict):
            continue
        cat = _normalize_category(obj.get("category") or obj.get("type") or "")
        ev = obj.get("evidence") or obj.get("legal_basis") or []
        if isinstance(ev, str):
            ev = [ev]
        result.append(ObligationModel(
            id=str(obj.get("id") or uuid.uuid4()),
            category=cat,
            title=str(obj.get("title") or obj.get("name") or obj.get("item") or "의무사항"),
            risk_level=(obj.get("risk_level") or obj.get("severity") or "MEDIUM").upper(),
            description=str(obj.get("description") or obj.get("detail") or ""),
            evidence=list(ev),
            action_url=obj.get("action_url"),
            auto_schedulable=bool(obj.get("auto_schedulable") or obj.get("schedulable") or False),
        ))

    # risk_level 내림차순 정렬
    result.sort(key=lambda o: RISK_ORDER.get(o.risk_level, 0), reverse=True)
    return result


def _extract_warnings(rd: dict) -> list[WarningModel]:
    """폴백: warnings + urgent_action_items + construction_specific_tips + age_warnings (object 지원)"""
    result: list[WarningModel] = []

    def _add(raw: Any, default_level: str = "WARN") -> None:
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    result.append(WarningModel(level=default_level, message=item))
                elif isinstance(item, dict):
                    lvl = (item.get("level") or item.get("severity") or default_level).upper()
                    msg = item.get("message") or item.get("text") or item.get("content") or ""
                    if msg:
                        result.append(WarningModel(level=lvl, message=str(msg)))
        elif isinstance(raw, dict):
            for k, v in raw.items():
                _add(v, default_level)
        elif isinstance(raw, str) and raw:
            result.append(WarningModel(level=default_level, message=raw))

    _add(rd.get("warnings"),                    "WARN")
    _add(rd.get("urgent_action_items"),          "DANGER")
    _add(rd.get("construction_specific_tips"),   "INFO")
    _add(rd.get("age_warnings"),                 "WARN")
    return result


def _extract_roi(rd: dict) -> Optional[RoiModel]:
    """폴백: exposure → penalty_risk → total_exposure_krw → roi.annual_penalty_risk_krw → rule_count × 300만원"""
    # 구독 연간 요금: DB에서 조회해야 하나, Transform 레이어에서는 result_data 내 값만 사용
    roi_raw = rd.get("roi") or {}
    sub_annual = (roi_raw.get("subscription_annual_krw") or
                  roi_raw.get("annual_subscription_krw") or 0)

    # 노출액(패널티)
    exp_raw = rd.get("exposure") or {}
    penalty = 0
    if isinstance(exp_raw, dict):
        penalty = (exp_raw.get("penalty_max_krw") or
                   exp_raw.get("total_exposure_krw") or 0)
    if not penalty:
        penalty = (rd.get("penalty_risk") or
                   rd.get("total_exposure_krw") or 0)
    if not penalty:
        penalty = (roi_raw.get("annual_penalty_risk_krw") or
                   roi_raw.get("penalty_max_krw") or 0)
    if not penalty:
        rc = rd.get("rule_count") or 0
        penalty = rc * 3_000_000

    if not penalty:
        return None

    roi_ratio = (roi_raw.get("roi_ratio") or
                 (round(penalty / sub_annual, 1) if sub_annual else 0))
    breakeven = (roi_raw.get("breakeven_days") or
                 (round(sub_annual / penalty * 365) if penalty else 0))

    return RoiModel(
        penalty_max_krw=int(penalty),
        subscription_annual_krw=int(sub_annual),
        roi_ratio=float(roi_ratio),
        breakeven_days=int(breakeven),
    )


def _extract_schedule(rd: dict) -> list[ScheduleMonthModel]:
    """폴백: inspection_schedule → inspection_schedule_ready → inspection_schedule_summary"""
    raw = None
    for key in ("inspection_schedule", "inspection_schedule_ready", "inspection_schedule_summary"):
        candidate = rd.get(key)
        if isinstance(candidate, list) and candidate:
            raw = candidate
            break

    if not raw:
        return [ScheduleMonthModel(month=m, count=0, items=[]) for m in range(1, 13)]

    result: list[ScheduleMonthModel] = []
    existing_months: set[int] = set()
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
        result.append(ScheduleMonthModel(month=month, count=count, items=list(items)))
        existing_months.add(month)

    # 누락 월 0건으로 보완
    for m in range(1, 13):
        if m not in existing_months:
            result.append(ScheduleMonthModel(month=m, count=0, items=[]))
    result.sort(key=lambda s: s.month)
    return result


def _extract_next_actions(rd: dict, diagnosis_id: str) -> list[NextActionModel]:
    raw = rd.get("next_actions") or []
    result: list[NextActionModel] = []
    if isinstance(raw, list):
        for act in raw:
            if isinstance(act, dict):
                result.append(NextActionModel(
                    label=act.get("label") or act.get("text") or "바로가기",
                    url=act.get("url") or "#",
                    type=act.get("type") or "secondary",
                ))
    # 기본 next_action 보장
    if not result:
        result.append(NextActionModel(
            label="ROI 대시보드 보기",
            url=f"/diagnosis/roi/{diagnosis_id}",
            type="primary",
        ))
    return result


def _build_transform(row: dict) -> TransformResponse:
    """DB row → TransformResponse 변환 (result_data 읽기 전용)"""
    rd: dict = row.get("result_data") or {}
    diag_id = str(row.get("id") or "")

    # schema_version 확인 (≠ v2026.04 는 호출자가 처리)
    schema_ver = rd.get("schema_version") or rd.get("version") or "unknown"

    company_name = (
        row.get("company_name") or
        rd.get("company_name") or
        rd.get("factory_name") or "(정보없음)"
    )
    sector = str(row.get("sector") or rd.get("sector") or "BUILDING").upper()
    tier   = str(row.get("tier") or rd.get("tier") or "FREE").upper()

    generated_at = ""
    if row.get("created_at"):
        try:
            dt = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            generated_at = dt.strftime("%Y년 %m월 %d일 %H:%M")
        except Exception:
            generated_at = str(row["created_at"])

    return TransformResponse(
        diagnosis_id=diag_id,
        sector=sector,
        tier=tier,
        company_name=company_name,
        generated_at=generated_at,
        schema_version=schema_ver,
        headline=_extract_headline(rd),
        obligations=_extract_obligations(rd),
        warnings=_extract_warnings(rd),
        roi=_extract_roi(rd),
        inspection_schedule=_extract_schedule(rd),
        next_actions=_extract_next_actions(rd, diag_id),
    )


# ─────────────────────────────────────────
# 공통 DB 조회
# ─────────────────────────────────────────
async def _fetch_row_by_id(diagnosis_id: str, user_id: str) -> dict:
    res = (
        supabase.table("factory_diagnosis_results")
        .select("id, sector, tier, company_name, created_at, result_data, user_id")
        .eq("id", diagnosis_id)
        .single()
        .execute()
    )
    row = res.data
    if not row:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")
    if str(row.get("user_id") or "") != str(user_id):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return row


async def _fetch_latest_row(factory_id: str, sector: Optional[str],
                            stage: Optional[str], user_id: str) -> dict:
    q = (
        supabase.table("factory_diagnosis_results")
        .select("id, sector, tier, company_name, created_at, result_data, user_id")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .limit(1)
    )
    if sector:
        q = q.eq("sector", sector.upper())
    if stage:
        q = q.eq("tier", stage.upper())
    res = q.execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="해당 시설의 진단 결과가 없습니다.")
    row = res.data[0]
    if str(row.get("user_id") or "") != str(user_id):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return row


# ─────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────
@router.get(
    "/{diagnosis_id}",
    response_model=TransformResponse,
    summary="[BE-08] ID 기반 Transform",
    description="진단 ID로 result_data를 조회하여 FN-06 표준 포맷으로 변환합니다. "
                "엔진 재실행 없이 읽기 전용으로 동작합니다.",
)
async def transform_by_id(
    diagnosis_id: str,
    current_user: dict = Depends(get_current_user),
):
    row = await _fetch_row_by_id(diagnosis_id, str(current_user["id"]))
    result = _build_transform(row)

    # schema_version 불일치 경고 (200 반환하되 warnings에 추가)
    if result.schema_version not in (SCHEMA_VERSION, "v2026.04"):
        result.warnings.insert(0, WarningModel(
            level="DANGER",
            message=f"진단 스키마 버전({result.schema_version})이 최신({SCHEMA_VERSION})과 다릅니다. "
                    "재진단을 권장합니다."
        ))

    logger.info(f"[BE-08] transform_by_id: diagnosis_id={diagnosis_id}")
    return result


@router.get(
    "/latest/{factory_id}",
    response_model=TransformResponse,
    summary="[BE-08] 시설 최신 진단 Transform",
    description="시설(factory_id)의 최신 진단 결과를 Transform합니다. "
                "sector, stage(tier) 필터 선택 가능.",
)
async def transform_latest(
    factory_id: str,
    sector: Optional[str] = Query(None, description="BUILDING|INDUSTRY|CONSTRUCTION"),
    stage:  Optional[str] = Query(None, description="FREE|PAID1|PAID2|PAID3"),
    current_user: dict = Depends(get_current_user),
):
    row = await _fetch_latest_row(
        factory_id, sector, stage, str(current_user["id"])
    )
    result = _build_transform(row)

    if result.schema_version not in (SCHEMA_VERSION, "v2026.04"):
        result.warnings.insert(0, WarningModel(
            level="DANGER",
            message=f"진단 스키마 버전({result.schema_version})이 최신({SCHEMA_VERSION})과 다릅니다. "
                    "재진단을 권장합니다."
        ))

    logger.info(f"[BE-08] transform_latest: factory_id={factory_id} sector={sector} stage={stage}")
    return result
