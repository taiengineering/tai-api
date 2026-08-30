"""Common Event Contract v1 — canonical core builder (§87 / §90).

Single source of truth for turning caller-supplied canonical inputs into the
physical v1 core written to ``business_event``. Pure and side-effect-free:
building never raises and never touches the database. The emitter decides
legacy-vs-v1 purely from whether a COMPLETE, non-placeholder core is produced.

v1 promotion rule (§16): an event becomes ``event_version = 1`` ONLY when the
writer can supply a complete, non-placeholder canonical core. Otherwise it stays
legacy (``event_version IS NULL``). No legacy fabrication (§7): this module never
infers canonical values from legacy-only data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

CONTRACT_VERSION = 1

# ─── §5 canonical enums ───
VALID_ACTOR_KINDS = frozenset(
    {"USER", "WORKER", "SYSTEM", "SERVICE", "CRON", "ENGINE", "LLM", "EXTERNAL"}
)
VALID_OUTCOMES = frozenset(
    {"SUCCESS", "FAILURE", "PARTIAL", "DENIED", "SKIPPED", "NOOP"}
)

# §5 event_name grammar: <DOMAIN>_<EVENT>, UPPER_SNAKE, ASCII, >= 2 segments,
# no leading/trailing/double underscore, no spaces.
EVENT_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")

# §15 / §9 placeholder trace values that MUST NOT become v1.
PLACEHOLDER_TRACE = frozenset({"no_trace", "unknown", ""})
# emitter fallback placeholders that disqualify a v1 identity.
PLACEHOLDER_IDENT = frozenset({"unknown", ""})

# §11 lossless legacy result -> canonical outcome. Only unambiguous mappings.
# timeout / pending are intentionally ABSENT -> no fabrication.
_RESULT_OUTCOME_LOSSLESS = {
    "success": "SUCCESS",
    "failure": "FAILURE",
    "skipped": "SKIPPED",
}

# §9 convenience: legacy actor_type -> canonical actor_kind. Uses a server-side
# value only; never rewrites legacy rows. Callers MAY use this to derive a kind
# for a NEW event. Unmapped values return None (caller must supply kind).
_ACTOR_TYPE_KIND = {
    "user": "USER",
    "admin": "USER",
    "system": "SYSTEM",
    "scheduler": "CRON",
    "synthetic_user": "EXTERNAL",
}


def is_valid_event_name(name: Optional[str]) -> bool:
    return isinstance(name, str) and bool(EVENT_NAME_RE.match(name))


def is_valid_actor_kind(kind: Optional[str]) -> bool:
    return kind in VALID_ACTOR_KINDS


def is_valid_outcome(outcome: Optional[str]) -> bool:
    return outcome is None or outcome in VALID_OUTCOMES


def derive_actor_kind(actor_type: Optional[str]) -> Optional[str]:
    """Map a server-side legacy actor_type to a canonical actor_kind.

    Returns None when there is no unambiguous mapping (caller must supply kind).
    """
    if not isinstance(actor_type, str):
        return None
    return _ACTOR_TYPE_KIND.get(actor_type.strip().lower())


def map_outcome(result: Optional[str]) -> Optional[str]:
    """Lossless legacy result -> canonical outcome, else None (§11)."""
    if not isinstance(result, str):
        return None
    return _RESULT_OUTCOME_LOSSLESS.get(result.strip().lower())


def now_occurred_at() -> str:
    """Server-side UTC event time as an ISO-8601 timestamptz string (§12)."""
    return datetime.now(timezone.utc).isoformat()


def _nonempty(v: Optional[str]) -> bool:
    return isinstance(v, str) and bool(v.strip())


def build_contract_core(
    *,
    event_name: Optional[str],
    actor_kind: Optional[str],
    actor_ref: Optional[str],
    trace_id: Optional[str],
    service_key: Optional[str],
    tenant_id: Optional[str],
    environment: Optional[str],
    occurred_at: Optional[str] = None,
    outcome: Optional[str] = None,
    result: Optional[str] = None,
) -> "tuple[Optional[dict], list[str]]":
    """Assemble the v1 canonical core, or return ``(None, errors)`` if incomplete.

    Never raises. Returns:
        ``(core_dict, [])``        when a COMPLETE valid v1 core is produced
        ``(None, [error, ...])``   when canonical emission must fall back to legacy

    ``core_dict`` keys: event_name, event_version, occurred_at, actor_kind,
    actor_ref, and (optionally, §6) outcome. ``outcome`` is omitted when it
    cannot be resolved losslessly.
    """
    errors: list[str] = []

    if not is_valid_event_name(event_name):
        errors.append("invalid or missing event_name: %r" % (event_name,))
    if not is_valid_actor_kind(actor_kind):
        errors.append("invalid or missing actor_kind: %r" % (actor_kind,))
    if not _nonempty(actor_ref):
        errors.append("actor_ref is required and must be a non-empty string")

    # §15/§9 placeholder + presence guards on inherited required core.
    if not _nonempty(trace_id) or trace_id in PLACEHOLDER_TRACE:
        errors.append("trace_id missing or placeholder: %r" % (trace_id,))
    if not _nonempty(service_key) or service_key in PLACEHOLDER_IDENT:
        errors.append("service_key missing or placeholder: %r" % (service_key,))
    if not _nonempty(tenant_id) or tenant_id in PLACEHOLDER_IDENT:
        errors.append("tenant_id missing or placeholder: %r" % (tenant_id,))
    if not _nonempty(environment):
        errors.append("environment is required")

    # outcome: explicit value validated; else lossless mapping from result; else None.
    resolved_outcome = outcome if outcome is not None else map_outcome(result)
    if not is_valid_outcome(resolved_outcome):
        errors.append("invalid outcome: %r" % (resolved_outcome,))
        resolved_outcome = None

    if errors:
        return None, errors

    core = {
        "event_name": event_name,
        "event_version": CONTRACT_VERSION,
        "occurred_at": occurred_at if _nonempty(occurred_at) else now_occurred_at(),
        "actor_kind": actor_kind,
        "actor_ref": actor_ref,
    }
    if resolved_outcome is not None:
        core["outcome"] = resolved_outcome
    return core, []
