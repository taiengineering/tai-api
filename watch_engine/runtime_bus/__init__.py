"""Runtime Event Bus — 중앙 Event 발신 계층.

모든 Runtime Event는 이 Bus를 통과해야 한다.
Validation + Sovereignty + Tenant Boundary + Event Store.
"""

from watch_engine.runtime_bus.event_bus import emit_runtime_event
from watch_engine.runtime_bus.event_result import EventResult
from watch_engine.runtime_bus.runtime_context import (
    RuntimeContext, make_context,
    CONTROL, WORKFLOW, NOTIFICATION, DELIVERY, SCHEDULER, UI, ADAPTER,
)
