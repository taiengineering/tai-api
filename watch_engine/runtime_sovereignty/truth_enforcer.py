"""Truth Enforcer — Runtime Capability 강제.

Operational Truth 관련 함수 호출 시 권한 검증.
위반 시 RuntimeCapabilityViolation 발생 + 로깅.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from watch_engine.runtime_sovereignty.capability_registry import (
    is_allowed, is_forbidden,
)

logger = logging.getLogger("watch_engine.runtime_sovereignty.enforcer")


class RuntimeCapabilityViolation(Exception):
    """Runtime이 허용되지 않은 Operational Truth action을 시도."""

    def __init__(self, runtime: str, action: str, detail: str = ""):
        self.runtime = runtime
        self.action = action
        self.detail = detail
        super().__init__(
            f"RuntimeCapabilityViolation: {runtime} cannot {action}. {detail}"
        )


def enforce(
    runtime: str,
    action: str,
    tenant_id: str = None,
    trace_id: str = None,
    raise_on_violation: bool = True,
) -> bool:
    """Runtime capability 검증.

    Args:
        runtime: \ud638\ucd9c\uc790 Runtime (control, notification, delivery, workflow, ui, adapter)
        action: \uc218\ud589\ud558\ub824\ub294 action (create_incident, set_severity, ...)
        tenant_id: \ud14c\ub10c\ud2b8 (\ub85c\uae45\uc6a9)
        trace_id: \ucd94\uc801 ID (\ub85c\uae45\uc6a9)
        raise_on_violation: True\uc774\uba74 \uc608\uc678 \ubc1c\uc0dd, False\uc774\uba74 False \ubc18\ud658

    Returns:
        True if allowed, False if denied

    Raises:
        RuntimeCapabilityViolation if denied and raise_on_violation=True
    """
    # 1. \uba85\uc2dc\uc801 \uae08\uc9c0 \ud655\uc778
    if is_forbidden(runtime, action):
        _log_violation(runtime, action, tenant_id, trace_id, "FORBIDDEN")
        if raise_on_violation:
            raise RuntimeCapabilityViolation(
                runtime, action,
                f"{runtime} is explicitly forbidden from {action}"
            )
        return False

    # 2. \ud5c8\uc6a9 \ubaa9\ub85d \ud655\uc778
    if not is_allowed(runtime, action):
        _log_violation(runtime, action, tenant_id, trace_id, "NOT_REGISTERED")
        if raise_on_violation:
            raise RuntimeCapabilityViolation(
                runtime, action,
                f"{runtime} does not have capability {action}"
            )
        return False

    return True


def _log_violation(
    runtime: str,
    action: str,
    tenant_id: Optional[str],
    trace_id: Optional[str],
    reason: str,
) -> None:
    """Violation \ub85c\uae45 (DB \uc800\uc7a5 \uac00\ub2a5)."""
    logger.warning(
        "[SOVEREIGNTY] VIOLATION: runtime=%s action=%s reason=%s tenant=%s trace=%s",
        runtime, action, reason, tenant_id, trace_id,
    )

    # DB \uc800\uc7a5 (\uc120\ud0dd\uc801 \u2014 \uc2e4\ud328\ud574\ub3c4 \ubb34\uc2dc)
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("engine_integrity_event").insert({
            "tenant_id": tenant_id or "system",
            "environment": "production",
            "service_key": "tai-api",
            "flow_key": "runtime_sovereignty",
            "trace_id": trace_id or f"violation_{runtime}_{action}",
            "event_type": "runtime_capability_violation",
            "severity": "CRITICAL",
            "integrity_status": "violation",
            "health_status": "critical",
            "domain": "sovereignty",
            "description": f"[SOVEREIGNTY] {runtime} attempted {action} (reason: {reason})",
            "resolved": False,
        }).execute()
    except Exception as e:
        logger.error("Failed to log sovereignty violation to DB: %s", e)
