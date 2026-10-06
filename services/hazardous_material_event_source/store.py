"""factory_hazardous_material_events persistence.

Status contract:
  DRAFT     — editable, not a LEG source
  CONFIRMED — exact operational event, LEG canonical TRUE source; immutable
  VOID      — invalidated confirmed record; retained, not a LEG source

Transition allowed:
  DRAFT → CONFIRMED
  CONFIRMED → VOID

Hard delete = 0. DB failure raises HazardousMaterialEventSourceLoadError.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.time import now_kst, serialize_external_utc

log = logging.getLogger("hazardous_material_event_source.store")

TABLE = "factory_hazardous_material_events"

_CONFIRM_REQUIRED = (
    "event_direction",
    "occurred_at",
    "purpose",
    "material_type",
    "quantity",
    "quantity_unit",
    "material_use",
    "purchase_source",
    "carrier_name",
    "responsible_person_name",
    "vehicle_type",
)

_VALID_DIRECTIONS = frozenset({"INBOUND", "OUTBOUND"})
_VALID_STATUSES = frozenset({"DRAFT", "CONFIRMED", "VOID"})


class HazardousMaterialEventSourceLoadError(RuntimeError):
    """DB/query failure. Must not be treated as empty source."""

    code = "HAZARDOUS_MATERIAL_EVENT_SOURCE_UNAVAILABLE"

    def __init__(self, message: str, *, factory_id: Optional[str] = None):
        super().__init__(message)
        self.factory_id = factory_id


class HazardousMaterialEventValidationError(ValueError):
    pass


def _rows(res) -> List[Dict[str, Any]]:
    return list(getattr(res, "data", None) or [])


def create_event_draft(
    supabase,
    *,
    factory_id: str,
    event_direction: str,
    occurred_at: Optional[str] = None,
    purpose: Optional[str] = None,
    material_type: Optional[str] = None,
    quantity: Optional[float] = None,
    quantity_unit: Optional[str] = None,
    material_use: Optional[str] = None,
    purchase_source: Optional[str] = None,
    carrier_name: Optional[str] = None,
    responsible_person_name: Optional[str] = None,
    vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:
    if event_direction not in _VALID_DIRECTIONS:
        raise HazardousMaterialEventValidationError(
            f"event_direction must be one of {sorted(_VALID_DIRECTIONS)}"
        )
    payload: Dict[str, Any] = {
        "factory_id": factory_id,
        "event_direction": event_direction,
        "status": "DRAFT",
        "confirmed_at": None,
        "voided_at": None,
    }
    for k, v in [
        ("occurred_at", occurred_at),
        ("purpose", purpose),
        ("material_type", material_type),
        ("quantity", quantity),
        ("quantity_unit", quantity_unit),
        ("material_use", material_use),
        ("purchase_source", purchase_source),
        ("carrier_name", carrier_name),
        ("responsible_person_name", responsible_person_name),
        ("vehicle_type", vehicle_type),
    ]:
        if v is not None:
            payload[k] = v
    try:
        res = supabase.table(TABLE).insert(payload).execute()
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} insert failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    if not rows:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} insert returned no row", factory_id=factory_id
        )
    return rows[0]


def update_event_draft(
    supabase,
    *,
    factory_id: str,
    event_id: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    row = _fetch_one(supabase, factory_id=factory_id, event_id=event_id)
    if row["status"] != "DRAFT":
        raise HazardousMaterialEventValidationError(
            f"Only DRAFT records may be updated (current status={row['status']})"
        )
    if "event_direction" in patch and patch["event_direction"] not in _VALID_DIRECTIONS:
        raise HazardousMaterialEventValidationError(
            f"event_direction must be one of {sorted(_VALID_DIRECTIONS)}"
        )
    forbidden = {"status", "confirmed_at", "voided_at", "id", "factory_id", "created_at"}
    safe_patch = {k: v for k, v in patch.items() if k not in forbidden}
    safe_patch["updated_at"] = serialize_external_utc(now_kst())
    try:
        res = (
            supabase.table(TABLE)
            .update(safe_patch)
            .eq("id", event_id)
            .eq("factory_id", factory_id)
            .execute()
        )
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} update failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    if not rows:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} update returned no row", factory_id=factory_id
        )
    return rows[0]


def confirm_event(
    supabase,
    *,
    factory_id: str,
    event_id: str,
) -> Dict[str, Any]:
    row = _fetch_one(supabase, factory_id=factory_id, event_id=event_id)
    if row["status"] != "DRAFT":
        raise HazardousMaterialEventValidationError(
            f"Only DRAFT→CONFIRMED transition is allowed (current status={row['status']})"
        )
    _validate_confirm_fields(row)
    now = now_kst()
    occurred_at = row.get("occurred_at")
    if occurred_at:
        _occ = _parse_ts(occurred_at)
        if _occ is not None and _occ > now:
            raise HazardousMaterialEventValidationError(
                "occurred_at must not be in the future at confirmation time"
            )
    now_str = serialize_external_utc(now)
    patch = {
        "status": "CONFIRMED",
        "confirmed_at": now_str,
        "voided_at": None,
        "updated_at": now_str,
    }
    try:
        res = (
            supabase.table(TABLE)
            .update(patch)
            .eq("id", event_id)
            .eq("factory_id", factory_id)
            .execute()
        )
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} confirm failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    if not rows:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} confirm returned no row", factory_id=factory_id
        )
    return rows[0]


def void_event(
    supabase,
    *,
    factory_id: str,
    event_id: str,
) -> Dict[str, Any]:
    row = _fetch_one(supabase, factory_id=factory_id, event_id=event_id)
    if row["status"] != "CONFIRMED":
        raise HazardousMaterialEventValidationError(
            f"Only CONFIRMED→VOID transition is allowed (current status={row['status']})"
        )
    now_str = serialize_external_utc(now_kst())
    patch = {
        "status": "VOID",
        "voided_at": now_str,
        "updated_at": now_str,
    }
    try:
        res = (
            supabase.table(TABLE)
            .update(patch)
            .eq("id", event_id)
            .eq("factory_id", factory_id)
            .execute()
        )
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} void failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    if not rows:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} void returned no row", factory_id=factory_id
        )
    return rows[0]


def list_factory_events(
    supabase,
    *,
    factory_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    try:
        q = (
            supabase.table(TABLE)
            .select("*")
            .eq("factory_id", factory_id)
            .order("occurred_at", desc=True)
            .limit(limit)
        )
        if status is not None:
            q = q.eq("status", status)
        res = q.execute()
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} list failed: {exc}", factory_id=factory_id
        ) from exc
    return _rows(res)


def load_confirmed_event_context(
    supabase,
    *,
    factory_id: str,
    event_id: str,
) -> Optional[Dict[str, Any]]:
    """Exact CONFIRMED event for diagnosis context. None if not found/not CONFIRMED/wrong factory.

    DB failure raises HazardousMaterialEventSourceLoadError.
    Missing event / DRAFT / VOID / wrong factory = None (no canonical fact).
    """
    try:
        res = (
            supabase.table(TABLE)
            .select(
                "id, factory_id, event_direction, occurred_at, status, confirmed_at"
            )
            .eq("id", event_id)
            .eq("factory_id", factory_id)
            .eq("status", "CONFIRMED")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} load_confirmed_event_context failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    return rows[0] if rows else None


# ── internal helpers ────────────────────────────────────────────────────────────

def _fetch_one(supabase, *, factory_id: str, event_id: str) -> Dict[str, Any]:
    try:
        res = (
            supabase.table(TABLE)
            .select("*")
            .eq("id", event_id)
            .eq("factory_id", factory_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HazardousMaterialEventSourceLoadError(
            f"{TABLE} fetch failed: {exc}", factory_id=factory_id
        ) from exc
    rows = _rows(res)
    if not rows:
        raise LookupError(f"event {event_id} not found for factory {factory_id}")
    return rows[0]


def _validate_confirm_fields(row: Dict[str, Any]) -> None:
    for field in _CONFIRM_REQUIRED:
        v = row.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise HazardousMaterialEventValidationError(
                f"CONFIRMED requires {field} (got: {v!r})"
            )
    qty = row.get("quantity")
    if not isinstance(qty, (int, float)) or qty <= 0:
        raise HazardousMaterialEventValidationError(
            f"CONFIRMED requires quantity > 0 (got: {qty!r})"
        )


def _parse_ts(value: Any) -> Optional[datetime]:
    from services.time import parse_external_datetime
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        return None  # naive datetime → reject (no implicit UTC assumption)
    if isinstance(value, str):
        try:
            return parse_external_datetime(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
    return None
