"""Canonical Runtime Payload Contract.

Defines the standard payload structure for all runtime candidates.
Binding Engine reads core + runtime only.
domain is stored opaquely. governance is forwarded to Watch Engine.
"""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class CorePayload(BaseModel):
    """Engine-agnostic required fields. Read by Binding Engine."""
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    severity: Optional[str] = None
    confidence: float = 1.0


class DomainPayload(BaseModel):
    """Engine-specific data. Binding Engine does NOT interpret this."""
    domain_type: str = "manual"  # legal | construction | manufacturing | marketing | manual
    data: dict[str, Any] = Field(default_factory=dict)


class RuntimePayloadFlags(BaseModel):
    """Runtime behavior flags. Binding Engine uses for projection decisions."""
    requires_activation: bool = True
    schedule_supported: bool = True
    evidence_required: bool = False
    document_required: bool = False
    auto_assignable: bool = False


class GovernancePayload(BaseModel):
    """Governance policy hints. Watch Engine consumes."""
    escalation_enabled: bool = True
    digest_enabled: bool = True
    storm_protection: bool = False
    governance_level: str = "standard"  # passive | standard | strict | critical


class CanonicalRuntimePayload(BaseModel):
    """Complete canonical payload."""
    core: CorePayload
    domain: DomainPayload = Field(default_factory=DomainPayload)
    runtime: RuntimePayloadFlags = Field(default_factory=RuntimePayloadFlags)
    governance: GovernancePayload = Field(default_factory=GovernancePayload)
