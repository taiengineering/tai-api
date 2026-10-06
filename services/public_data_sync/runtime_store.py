"""Public Data Runtime Store — thin wrapper around Supabase RPC calls."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.public_data_sync.contracts import RunResult, RunStatus, SourceSpec, TriggerKind

logger = logging.getLogger(__name__)

_CREDENTIAL_LIMIT_DEFAULT = 1
_RATE_LIMIT_LIMIT_DEFAULT = 1
_LEASE_SECONDS_DEFAULT = 900


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import parse as _parse  # type: ignore[import]
    return _parse(value)


@dataclass
class ClaimResult:
    claimed: bool
    run_id: str
    reason: str
    lease_until: datetime | None = None
    source_slot: int | None = None
    credential_slot: int | None = None
    rate_limit_slot: int | None = None


class PublicDataRuntimeStore:
    """Thin wrapper around Supabase RPCs for Public Data runtime state."""

    def __init__(self, supabase_client: Any = None) -> None:
        self._client = supabase_client

    @property
    def _sb(self) -> Any:
        if self._client is None:
            from db.supabase_client import get_supabase
            return get_supabase()
        return self._client

    def _rpc(self, name: str, params: dict) -> Any:
        res = self._sb.rpc(name, params).execute()
        return res.data if hasattr(res, "data") else res

    # ------------------------------------------------------------------
    # claim_run
    # ------------------------------------------------------------------

    def claim_run(
        self,
        run_id: str,
        spec: SourceSpec,
        *,
        trigger: TriggerKind = TriggerKind.SCHEDULED,
        scheduled_for: datetime | None = None,
        now: datetime | None = None,
        lease_seconds: int = _LEASE_SECONDS_DEFAULT,
        credential_limit: int = _CREDENTIAL_LIMIT_DEFAULT,
        rate_limit_limit: int = _RATE_LIMIT_LIMIT_DEFAULT,
    ) -> ClaimResult:
        now = now or _now()
        data = self._rpc("fn_public_data_claim_run", {
            "p_run_id":           run_id,
            "p_source_id":        spec.source_id,
            "p_trigger":          trigger.value,
            "p_scheduled_for":    _ts(scheduled_for),
            "p_now":              _ts(now),
            "p_lease_seconds":    lease_seconds,
            "p_credential_pool":  spec.credential_pool,
            "p_rate_limit_group": spec.rate_limit_group,
            "p_source_limit":     spec.max_concurrency,
            "p_credential_limit": credential_limit,
            "p_rate_limit_limit": rate_limit_limit,
        })
        return ClaimResult(
            claimed=data.get("claimed", False),
            run_id=data.get("run_id", run_id),
            reason=data.get("reason", "UNKNOWN"),
            lease_until=_parse_ts(data.get("lease_until")),
            source_slot=data.get("source_slot"),
            credential_slot=data.get("credential_slot"),
            rate_limit_slot=data.get("rate_limit_slot"),
        )

    # ------------------------------------------------------------------
    # heartbeat
    # ------------------------------------------------------------------

    def heartbeat(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = _LEASE_SECONDS_DEFAULT,
    ) -> bool:
        now = now or _now()
        return bool(self._rpc("fn_public_data_heartbeat_run", {
            "p_run_id":        run_id,
            "p_now":           _ts(now),
            "p_lease_seconds": lease_seconds,
        }))

    # ------------------------------------------------------------------
    # complete_run
    # ------------------------------------------------------------------

    def complete_run(
        self,
        run_id: str,
        result: RunResult,
        *,
        next_due_at: datetime | None = None,
        retry_not_before: datetime | None = None,
    ) -> bool:
        finished = result.finished_at or _now()
        return bool(self._rpc("fn_public_data_complete_run", {
            "p_run_id":           run_id,
            "p_status":           result.status.value,
            "p_finished_at":      _ts(finished),
            "p_fetched":          result.fetched,
            "p_created":          result.created,
            "p_changed":          result.changed,
            "p_unchanged":        result.unchanged,
            "p_removed":          result.removed,
            "p_failed":           result.failed,
            "p_source_version":   result.source_version,
            "p_content_hash":     result.content_hash,
            "p_change_detected":  result.change_detected,
            "p_error_code":       result.error_code,
            "p_error_message":    result.error_message,
            "p_details":          result.details or None,
            "p_next_due_at":      _ts(next_due_at),
            "p_retry_not_before": _ts(retry_not_before),
        }))

    # ------------------------------------------------------------------
    # read helpers
    # ------------------------------------------------------------------

    def get_source_runtime(self, source_id: str) -> dict | None:
        res = (
            self._sb.table("public_data_source_runtime")
            .select("*")
            .eq("source_id", source_id)
            .maybe_single()
            .execute()
        )
        return res.data if hasattr(res, "data") else None

    def get_run(self, run_id: str) -> dict | None:
        res = (
            self._sb.table("public_data_sync_runs")
            .select("*")
            .eq("id", run_id)
            .maybe_single()
            .execute()
        )
        return res.data if hasattr(res, "data") else None

    def list_due_sources(self, *, now: datetime | None = None) -> list[str]:
        """Return source_ids that are enabled, due, and not in future retry backoff.

        Includes sources where retry_not_before IS NULL (never failed) or
        retry_not_before <= now (backoff window has passed).
        """
        now = now or _now()
        ts = _ts(now)
        res = (
            self._sb.table("public_data_source_runtime")
            .select("source_id")
            .eq("is_enabled", True)
            .lte("next_due_at", ts)
            .or_(f"retry_not_before.is.null,retry_not_before.lte.{ts}")
            .execute()
        )
        rows = res.data if hasattr(res, "data") else []
        return [r["source_id"] for r in (rows or [])]
