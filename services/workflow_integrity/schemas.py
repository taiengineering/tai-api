"""Workflow Integrity Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Rule Registry ──────────────────────────────────────────

class IntegrityRuleOut(BaseModel):
    id: UUID
    rule_code: str
    workflow_type: str
    rule_type: str
    severity: str
    enabled: bool
    description: Optional[str] = None
    evaluation_window_sec: int
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ── Integrity Event ────────────────────────────────────────

class IntegrityEventCreate(BaseModel):
    workflow_id: UUID
    workflow_type: str
    rule_id: Optional[UUID] = None
    integrity_type: str
    severity: str = "WARNING"
    trace_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class IntegrityEventOut(BaseModel):
    id: UUID
    workflow_id: UUID
    workflow_type: str
    rule_id: Optional[UUID] = None
    integrity_type: str
    severity: str
    trace_id: Optional[str] = None
    detected_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    resolved: bool
    resolved_at: Optional[datetime] = None


# ── Evaluation Result ──────────────────────────────────────

class DetectionResult(BaseModel):
    """단일 탐지 결과."""
    detected: bool
    rule_code: str
    integrity_type: str
    severity: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """전체 평가 보고서."""
    workflow_id: UUID
    workflow_type: str
    evaluated_at: datetime
    total_rules_checked: int
    violations_found: int
    detections: list[DetectionResult]


# ── Timeline ───────────────────────────────────────────────

class IntegrityTimelineOut(BaseModel):
    """Integrity Timeline API 응답."""
    workflow_id: UUID
    workflow_type: str
    integrity_events: list[IntegrityEventOut]
    triggered_rules: list[IntegrityRuleOut]
    timeline_events: list[dict[str, Any]]
