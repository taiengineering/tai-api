"""Document workflow auto-activation (TASK 23).

Called from business routers after workflow success. Must stay side-effect
only from the caller's perspective — failures are swallowed by callers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_LOG = logging.getLogger("watch_engine.document")


def activate_documents_for_workflow(
    supabase: Any,
    *,
    flow_key: str,
    trace_id: str,
    tenant_id: str,
    actor_id: str = "user",
    factory_id: Any = None,
    workflow_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Resolve and persist document activations for a completed workflow trace.

    Parameters mirror router hook sites. Implementation may grow (Supabase
    tables, idempotency keys); for now we log at INFO for observability.
    """
    ctx = workflow_context or {}
    _LOG.info(
        "activate_documents_for_workflow flow=%s trace=%s tenant=%s actor=%s factory_id=%s ctx=%s",
        flow_key,
        trace_id,
        tenant_id,
        actor_id,
        factory_id,
        ctx,
    )
    # Future: insert / upsert document activation rows keyed by (flow_key, trace_id).
