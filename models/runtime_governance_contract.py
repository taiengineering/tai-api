"""Runtime Governance Contract.

Defines governance policies for runtime objects.
Consumed by Watch Engine.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class EscalationPolicy(BaseModel):
    enabled: bool = True
    threshold_hours: int = 48
    target: str = "facility_manager"  # user | team | facility_manager


class RetryPolicy(BaseModel):
    enabled: bool = True
    max_retries: int = 3
    backoff: str = "linear"  # linear | exponential


class DigestPolicy(BaseModel):
    enabled: bool = True
    frequency: str = "daily"  # daily | weekly
    channel: str = "in_app"  # email | sms | in_app


class ThrottlingPolicy(BaseModel):
    enabled: bool = False
    max_per_hour: int = 100


class StormProtection(BaseModel):
    enabled: bool = False
    threshold: int = 50
    window_minutes: int = 10


class ReplayPolicy(BaseModel):
    enabled: bool = False
    retention_days: int = 30


class IntegrityPolicy(BaseModel):
    validation_mode: str = "lenient"  # lenient | strict
    hash_verification: bool = False


class RuntimeGovernanceContract(BaseModel):
    """Complete governance contract for a runtime object."""
    governance_level: str = "standard"  # passive | standard | strict | critical
    escalation: EscalationPolicy = Field(default_factory=EscalationPolicy)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    digest: DigestPolicy = Field(default_factory=DigestPolicy)
    throttling: ThrottlingPolicy = Field(default_factory=ThrottlingPolicy)
    storm_protection: StormProtection = Field(default_factory=StormProtection)
    replay: ReplayPolicy = Field(default_factory=ReplayPolicy)
    integrity: IntegrityPolicy = Field(default_factory=IntegrityPolicy)


# ----- Presets -----

def governance_passive() -> RuntimeGovernanceContract:
    return RuntimeGovernanceContract(
        governance_level="passive",
        escalation=EscalationPolicy(enabled=False),
        retry=RetryPolicy(enabled=False),
    )

def governance_standard() -> RuntimeGovernanceContract:
    return RuntimeGovernanceContract(governance_level="standard")

def governance_strict() -> RuntimeGovernanceContract:
    return RuntimeGovernanceContract(
        governance_level="strict",
        escalation=EscalationPolicy(threshold_hours=24),
        retry=RetryPolicy(max_retries=5),
        storm_protection=StormProtection(enabled=True),
        integrity=IntegrityPolicy(validation_mode="strict"),
    )

def governance_critical() -> RuntimeGovernanceContract:
    return RuntimeGovernanceContract(
        governance_level="critical",
        escalation=EscalationPolicy(threshold_hours=4),
        retry=RetryPolicy(max_retries=10, backoff="exponential"),
        digest=DigestPolicy(frequency="daily", channel="sms"),
        storm_protection=StormProtection(enabled=True, threshold=20),
        integrity=IntegrityPolicy(validation_mode="strict", hash_verification=True),
    )
