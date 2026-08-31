"""Common Event Contract v1 — canonical core builder (§87 / §90).

Single source of truth for turning caller-supplied canonical inputs into the
physical v1 core written to ``business_event``. Pure and side-effect-free:
building never raises and never touches the database.

Contract of build_contract_core (§90 PATCH-1):
    valid   -> (core_dict, [])
    invalid -> (None, [errors])

This module does NOT decide "legacy vs v1" and never implies a legacy
fallback. Once a caller requests a canonical event, the emitter records it as
v1 or does not record it at all (no silent legacy downgrade). No legacy
fabrication (§7): canonical values are never inferred from legacy-only data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from services.time import now_kst, serialize_external_utc

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


def is_tz_aware_datetime(value: Optional[str]) -> bool:
    """True iff value is a parseable, timezone-aware ISO-8601 timestamp (§12).

    A trailing 'Z' is accepted as UTC. Naive datetimes (no offset) are rejected.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return False
    return dt.tzinfo is not None and dt.utcoffset() is not None


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
    return serialize_external_utc(now_kst())


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
    """Assemble the v1 canonical core, or return ``(None, errors)`` if invalid.

    Never raises. Returns:
        ``(core_dict, [])``        when a COMPLETE valid v1 core is produced
        ``(None, [error, ...])``   when the canonical request is invalid

    The caller MUST NOT persist an invalid request in any other form (§90
    PATCH-1). ``core_dict`` keys: event_name, event_version, occurred_at,
    actor_kind, actor_ref, and (optionally, §6) outcome.
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

    # §12 occurred_at: caller-supplied must be parseable + timezone-aware;
    # when absent, a server-side UTC-aware timestamp is generated.
    if occurred_at is not None:
        if not is_tz_aware_datetime(occurred_at):
            errors.append(
                "occurred_at must be a parseable timezone-aware datetime: %r"
                % (occurred_at,)
            )
        resolved_occurred = occurred_at
    else:
        resolved_occurred = now_occurred_at()

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
        "occurred_at": resolved_occurred,
        "actor_kind": actor_kind,
        "actor_ref": actor_ref,
    }
    if resolved_outcome is not None:
        core["outcome"] = resolved_outcome
    return core, []
