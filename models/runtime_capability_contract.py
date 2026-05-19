"""Runtime Capability Contract.

Tenant-level feature flags for runtime behaviors.
Checked by Binding Engine, Activation Service, Watch Engine.
"""
from __future__ import annotations
from pydantic import BaseModel


class RuntimeCapabilityContract(BaseModel):
    """Tenant runtime capabilities."""
    runtime_overdue: bool = True
    runtime_candidate_projection: bool = True
    runtime_activation: bool = True
    advanced_governance: bool = False
    cross_runtime_monitoring: bool = False
    digest: bool = False
    auto_escalation: bool = False
    document_generation: bool = True
    evidence_collection: bool = True
    schedule_management: bool = True
    notification_dispatch: bool = False
    api_access: bool = False
    multi_facility: bool = False


# ----- Tier Presets -----

def capability_free() -> RuntimeCapabilityContract:
    return RuntimeCapabilityContract()


def capability_standard() -> RuntimeCapabilityContract:
    return RuntimeCapabilityContract(
        cross_runtime_monitoring=True,
        digest=True,
        notification_dispatch=True,
        multi_facility=True,
    )


def capability_premium() -> RuntimeCapabilityContract:
    return RuntimeCapabilityContract(
        cross_runtime_monitoring=True,
        digest=True,
        auto_escalation=True,
        notification_dispatch=True,
        api_access=True,
        multi_facility=True,
        advanced_governance=True,
    )
