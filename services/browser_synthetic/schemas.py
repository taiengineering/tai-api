"""Browser Synthetic Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Check Registry ────────────────────────────────────────

class SyntheticCheckOut(BaseModel):
    id: UUID
    check_code: str
    check_name: str
    workflow_type: str
    target_url: str
    check_type: str
    enabled: bool
    interval_sec: int
    timeout_sec: int
    expected_result: dict[str, Any] = Field(default_factory=dict)
    severity: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ── Execution Log ────────────────────────────────────────

class ExecutionLogCreate(BaseModel):
    check_code: str
    workflow_id: Optional[UUID] = None
    trace_id: Optional[str] = None
    execution_status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    screenshot_url: Optional[str] = None
    artifact_url: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionLogOut(BaseModel):
    id: UUID
    execution_id: str
    check_code: str
    workflow_id: Optional[UUID] = None
    trace_id: Optional[str] = None
    execution_status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    screenshot_url: Optional[str] = None
    artifact_url: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Synthetic Event Contract (3.4) ────────────────────────

class SyntheticEvent(BaseModel):
    """Synthetic → Platform Event 규약."""
    synthetic_check: str
    workflow_type: str
    execution_status: str
    duration_ms: Optional[int] = None
    trace_id: Optional[str] = None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Metrics ─────────────────────────────────────────────

class SyntheticMetricsOut(BaseModel):
    """Synthetic 운영 상태 관측 응답."""
    check_code: str
    total_executions: int
    success_count: int
    fail_count: int
    timeout_count: int
    error_count: int
    success_ratio: float
    fail_ratio: float
    timeout_ratio: float
    avg_duration_ms: Optional[float] = None


# ── Timeline ────────────────────────────────────────────

class SyntheticTimelineOut(BaseModel):
    """Synthetic Timeline API 응답."""
    trace_id: str
    executions: list[ExecutionLogOut]
    related_workflow_id: Optional[UUID] = None
    related_alerts: list[dict[str, Any]] = Field(default_factory=list)
