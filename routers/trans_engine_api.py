"""Trans Engine API — Operational Translation endpoints.

Routes:
    POST /trans/translate  — event → human message
    POST /trans/summary    — events → 상황 요약
    GET  /trans/examples   — 샘플 반환
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any

from watch_engine.trans_engine.event_translator import translate_event
from watch_engine.trans_engine.summary_builder import build_summary

router = APIRouter(prefix="/trans", tags=["Trans Engine"])


# ── Schemas ────────────────────────────────

class TranslateRequest(BaseModel):
    event: dict[str, Any] = Field(..., description="Runtime event dict")
    audience: str = Field("operator", description="operator | admin | developer")


class SummaryRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., description="Runtime event list")
    audience: str = Field("operator", description="operator | admin | developer")


# ── Endpoints ──────────────────────────────

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
