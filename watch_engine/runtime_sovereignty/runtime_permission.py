"""Runtime Permission — Runtime Context 기반 권한 검증.

함수 호출 시 Runtime Context를 주입하여 권한 검증.
"""

import logging
import functools
from dataclasses import dataclass, field
from typing import Optional

from watch_engine.runtime_sovereignty.truth_enforcer import enforce

logger = logging.getLogger("watch_engine.runtime_sovereignty.permission")


@dataclass
class RuntimeContext:
    """Runtime \ud638\ucd9c \ucee8\ud14d\uc2a4\ud2b8."""
    runtime: str                         # control, notification, delivery, workflow, ui, adapter
    namespace: str = ""                  # watch.control, watch.notification, ...
    tenant_id: Optional[str] = None
    trace_id: Optional[str] = None
    actor_id: Optional[str] = None
    capabilities: set = field(default_factory=set)  # \uc790\ub3d9 \ub85c\ub4dc

    def __post_init__(self):
        if not self.capabilities:
            from watch_engine.runtime_sovereignty.capability_registry import get_capabilities
            self.capabilities = get_capabilities(self.runtime)
        if not self.namespace:
            self.namespace = f"watch.{self.runtime}"


# \uae30\ubcf8 Runtime Context (\ud3b8\uc758\uc6a9)
CONTROL_CONTEXT = RuntimeContext(runtime="control")
NOTIFICATION_CONTEXT = RuntimeContext(runtime="notification")
DELIVERY_CONTEXT = RuntimeContext(runtime="delivery")
WORKFLOW_CONTEXT = RuntimeContext(runtime="workflow")
UI_CONTEXT = RuntimeContext(runtime="ui")
ADAPTER_CONTEXT = RuntimeContext(runtime="adapter")


def with_runtime_context(runtime: str, action: str):
    """Decorator: \ud568\uc218 \ud638\ucd9c \uc2dc Runtime capability \uac80\uc99d.

    Usage:
        @with_runtime_context("control", "create_incident")
        def create_incident(...):
            ...

        @with_runtime_context("notification", "create_incident")  # \u2192 \ucc28\ub2e8\ub428
        def bad_function(...):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tenant_id = kwargs.get("tenant_id")
            trace_id = kwargs.get("trace_id")
            enforce(
                runtime=runtime,
                action=action,
                tenant_id=tenant_id,
                trace_id=trace_id,
                raise_on_violation=True,
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator
