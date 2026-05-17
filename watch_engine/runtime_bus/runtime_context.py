"""Runtime Context — Event 발신자 식별."""

from dataclasses import dataclass, field
from typing import Optional

VALID_RUNTIMES = {"control", "workflow", "notification", "delivery", "scheduler", "ui", "adapter", "semantic"}


@dataclass
class RuntimeContext:
    runtime: str
    service: str = "tai-api"
    environment: str = "production"
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    namespace: str = ""

    def __post_init__(self):
        if self.runtime not in VALID_RUNTIMES:
            raise ValueError(f"Invalid runtime: {self.runtime}. Must be one of {VALID_RUNTIMES}")
        if not self.namespace:
            self.namespace = self.runtime


def make_context(
    runtime: str,
    tenant_id: str = None,
    actor_id: str = None,
    environment: str = "production",
) -> RuntimeContext:
    return RuntimeContext(
        runtime=runtime,
        tenant_id=tenant_id,
        actor_id=actor_id,
        environment=environment,
    )


# \ud3b8\uc758 \uc0c1\uc218
CONTROL = "control"
WORKFLOW = "workflow"
NOTIFICATION = "notification"
DELIVERY = "delivery"
SCHEDULER = "scheduler"
UI = "ui"
ADAPTER = "adapter"
