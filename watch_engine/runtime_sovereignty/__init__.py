"""Runtime Sovereignty — Capability Registry + Truth Enforcer.

Runtime별 권한 중앙 관리. Operational Truth 생성/수정 권한 강제.
"""

from watch_engine.runtime_sovereignty.capability_registry import (
    CAPABILITY_REGISTRY,
    FORBIDDEN_REGISTRY,
    get_capabilities,
    is_allowed,
    is_forbidden,
)
from watch_engine.runtime_sovereignty.truth_enforcer import (
    enforce,
    RuntimeCapabilityViolation,
)
from watch_engine.runtime_sovereignty.runtime_permission import (
    with_runtime_context,
    RuntimeContext,
)
