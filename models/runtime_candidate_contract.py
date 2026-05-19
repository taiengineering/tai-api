"""Runtime Candidate Contracts — Normalized Input/Output for Binding Engine.

Engine-agnostic. No legal_rule_id, no Safe-specific fields at top level.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ========== INPUT CONTRACT ==========

class RuntimeCandidateInput(BaseModel):
    """Normalized input from any engine to the Binding Engine."""
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_type: str  # inspection, permit, report, training, ...
    candidate_category: Optional[str] = None
    title: str
    description: Optional[str] = None
    source_engine: str  # legal, manual, monitoring, marketing, ...
    source_ref_id: Optional[str] = None
    source_event_id: Optional[str] = None
    tenant_id: str
    facility_id: str
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    priority: str = "medium"
    confidence: float = 1.0
    payload: dict[str, Any] = Field(default_factory=dict)
    source_trace: dict[str, Any] = Field(default_factory=dict)
    requires_activation: bool = True

    # Document/Evidence/Schedule suggestions
    document_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    schedule_suggestion: Optional[dict[str, Any]] = None


# ========== OUTPUT CONTRACT ==========

class RuntimeCandidateProjection(BaseModel):
    """Output from Binding Engine — stored as runtime_candidate."""
    projection_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    projection_type: str
    tenant_id: str
    facility_id: str
    source_engine: str
    trace_id: str
    status: str = "projected"  # projected, pending_review, approved, rejected, activated


class RuntimeActivationRequest(BaseModel):
    """Input for activating a candidate into runtime objects."""
    candidate_id: str
    assignee_id: Optional[str] = None
    recurrence_rule: Optional[str] = None
    next_due_date: Optional[str] = None
    enabled: bool = True
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    selected_document_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
