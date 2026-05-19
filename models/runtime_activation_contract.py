"""Universal Runtime Activation Contract.

Engine-independent activation structure.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class RuntimeActivationContract(BaseModel):
    """Standard activation request for any candidate."""
    candidate_id: str
    activation_mode: str = "manual"  # manual | automatic | conditional | delegated
    assignment_strategy: str = "user"  # user | team | facility | auto_routing
    assignee_id: Optional[str] = None
    team_id: Optional[str] = None
    schedule_strategy: str = "none"  # periodic | one_time | deadline | none
    recurrence_rule: Optional[str] = None
    next_due_date: Optional[str] = None
    escalation_policy: str = "standard"  # standard | strict | none
    runtime_policy: str = "default"  # default | custom
    governance_policy: str = "standard"  # passive | standard | strict | critical
    capability_scope: list[str] = Field(default_factory=list)
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    selected_document_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
