"""Trans Engine API — Operational Translation endpoints.

Routes:
    POST /trans/translate        — event → human message
    POST /trans/translate-batch  — events → human messages (batch)
    POST /trans/summary          — events → 상황 요약
    GET  /trans/examples         — 샘플 반환
    POST /trans/build-situation  — events → 운영 상황
    POST /trans/build-storyline  — events → 흐름 설명
    POST /trans/explain-risk     — severity → 운영 위험 설명
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any

from watch_engine.trans_engine.event_translator import translate_event
from watch_engine.trans_engine.summary_builder import build_summary
from watch_engine.trans_engine.situation_builder import build_operational_situation
from watch_engine.trans_engine.storyline_builder import build_storyline
from watch_engine.trans_engine.risk_explainer import explain_severity, explain_risk_level

router = APIRouter(prefix="/trans", tags=["Trans Engine"])


# ── Schemas ────────────────────────────────

class TranslateRequest(BaseModel):
    event: dict[str, Any] = Field(..., description="Runtime event dict")
    audience: str = Field("operator", description="operator | admin | developer")


class BatchTranslateRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., description="Runtime event list")
    audience: str = Field("operator", description="operator | admin | developer")


class SummaryRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., description="Runtime event list")
    audience: str = Field("operator", description="operator | admin | developer")


class SituationRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., description="Runtime event list")
    audience: str = Field("operator", description="operator | admin | developer")


class StorylineRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., description="Runtime event list")
    audience: str = Field("operator", description="operator | admin | developer")


class RiskRequest(BaseModel):
    severity: str = Field(..., description="INFO | WARNING | CRITICAL | FATAL")
    risk_level: str | None = Field(None, description="HEALTHY | RISK | DEGRADED | CRITICAL")


# ── T-01 Endpoints ─────────────────────────

@router.post("/translate")
async def api_translate(req: TranslateRequest):
    """단일 event → Human Message 변환."""
    return translate_event(req.event, req.audience)


@router.post("/summary")
async def api_summary(req: SummaryRequest):
    """다건 events → 상황 요약."""
    return build_summary(req.events, req.audience)


@router.get("/examples")
async def api_examples():
    """번역 샘플 반환."""
    sample_event = {
        "event_type": "workflow.failed",
        "flow_key": "payment_attempt",
        "severity": "WARNING",
    }
    return {
        "sample_event": sample_event,
        "operator": translate_event(sample_event, "operator"),
        "admin": translate_event(sample_event, "admin"),
        "developer": translate_event(sample_event, "developer"),
    }


# ── T-02 Endpoints ─────────────────────────

@router.post("/build-situation")
async def api_build_situation(req: SituationRequest):
    """여러 events → 운영 상황 종합."""
    return build_operational_situation(req.events, req.audience)


@router.post("/build-storyline")
async def api_build_storyline(req: StorylineRequest):
    """여러 events → 흐름 설명 (원인→악화→영향→확인사항)."""
    return {"storyline": build_storyline(req.events, req.audience)}


@router.post("/explain-risk")
async def api_explain_risk(req: RiskRequest):
    """severity/risk_level → 운영 위험 설명."""
    result: dict[str, Any] = {
        "severity": explain_severity(req.severity),
    }
    if req.risk_level:
        result["risk_level"] = explain_risk_level(req.risk_level)
    return result


# ── T-04 Endpoints ─────────────────────────

@router.post("/translate-batch")
async def api_translate_batch(req: BatchTranslateRequest):
    """다건 events → Human Messages 배치 변환.

    - 순서 유지
    - 개별 실패 시 fallback message 반환
    - N+1 호출 해소용
    """
    messages: list[dict[str, Any]] = []
    for event in req.events:
        try:
            msg = translate_event(event, req.audience)
        except Exception:
            msg = {
                "title": "번역 처리 중 오류가 발생했습니다",
                "summary": "이벤트를 운영 언어로 변환하지 못했습니다.",
                "urgency": "확인 필요",
                "impact": "확인 필요",
                "recommended_checks": ["해당 이벤트 상세를 확인하세요"],
                "recommended_actions": [],
                "confidence": 0.0,
            }
        messages.append(msg)
    return {"messages": messages}
