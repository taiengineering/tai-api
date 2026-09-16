"""factory_work_facts persistence. Structured source only — no LEG booleans."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.time import now_kst, serialize_business_datetime
from services.work_source.registry import (
    ALLOWED_PAYLOAD_KEYS,
    CANONICAL_ATTR_PREFIXES,
    work_type_spec,
)

log = logging.getLogger("work_source.store")

TABLE = "factory_work_facts"


class WorkSourceValidationError(ValueError):
    pass


def _blank(val: Any) -> bool:
    return val is None or (isinstance(val, str) and not val.strip())


def validate_payload(payload: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    extra = set(payload) - ALLOWED_PAYLOAD_KEYS
    if extra:
        raise WorkSourceValidationError(
            "unsupported keys: {}".format(sorted(extra))
        )
    out: Dict[str, Any] = {}
    if "work_type" in payload or not partial:
        work_type = payload.get("work_type")
        spec = work_type_spec(work_type) if isinstance(work_type, str) else None
        if spec is None:
            raise WorkSourceValidationError("unknown work_type")
        out["work_type"] = work_type
    else:
        spec = None

    if "work_subtype" in payload:
        subtype = payload.get("work_subtype")
        if _blank(subtype):
            out["work_subtype"] = None
        else:
            if spec is None:
                raise WorkSourceValidationError("work_subtype requires work_type")
            allowed = spec.get("subtypes") or {}
            if subtype not in allowed:
                raise WorkSourceValidationError("unknown work_subtype")
            out["work_subtype"] = subtype

    for col in ("equipment_ref", "material_ref", "location_ref"):
        if col in payload:
            val = payload.get(col)
            out[col] = None if _blank(val) else str(val)

    if "attributes" in payload or not partial:
        attrs = payload.get("attributes") if "attributes" in payload else {}
        if attrs is None:
            attrs = {}
        if not isinstance(attrs, dict):
            raise WorkSourceValidationError("attributes must be an object")
        allowed_attrs = set((spec or {}).get("attributes") or {})
        for key in attrs:
            if any(str(key).startswith(p) for p in CANONICAL_ATTR_PREFIXES):
                raise WorkSourceValidationError(
                    "canonical LEG fields cannot be stored on work source"
                )
            if spec is not None and key not in allowed_attrs:
                raise WorkSourceValidationError("unknown attribute: {}".format(key))
        out["attributes"] = attrs

    if "active" in payload:
        if payload["active"] is not True and payload["active"] is not False:
            raise WorkSourceValidationError("active must be boolean")
        out["active"] = payload["active"]
    elif not partial:
        out["active"] = True

    return out


def list_work_facts(supabase, factory_id: str, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    q = supabase.table(TABLE).select(
        "id, factory_id, work_type, work_subtype, equipment_ref, material_ref, "
        "location_ref, attributes, active, created_at, updated_at"
    ).eq("factory_id", factory_id)
    if not include_inactive:
        q = q.eq("active", True)
    res = q.order("created_at").execute()
    data = getattr(res, "data", None)
    if not isinstance(data, list):
        return []
    return data


def load_work_rows_optional(supabase, factory_id: Optional[str]) -> List[Dict[str, Any]]:
    """Diagnosis seam. Missing table / factory → empty list. Never invents facts."""
    if not factory_id or supabase is None:
        return []
    try:
        return list_work_facts(supabase, factory_id, include_inactive=False)
    except Exception as exc:  # noqa: BLE001 — table may not exist until migration apply
        log.warning("factory_work_facts load skipped factory=%s: %s", factory_id, exc)
        return []


def create_work_fact(supabase, factory_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = validate_payload(payload, partial=False)
    now = serialize_business_datetime(now_kst())
    row.update(
        {
            "factory_id": factory_id,
            "created_at": now,
            "updated_at": now,
        }
    )
    if "attributes" not in row:
        row["attributes"] = {}
    res = supabase.table(TABLE).insert(row).execute()
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise RuntimeError("factory_work_facts insert returned no row")
    return data[0]


def update_work_fact(
    supabase, factory_id: str, fact_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    existing = (
        supabase.table(TABLE)
        .select("id, work_type, work_subtype, attributes, active")
        .eq("id", fact_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    rows = list(getattr(existing, "data", None) or [])
    if not rows:
        raise KeyError("work fact not found")
    merged = {
        "work_type": rows[0].get("work_type"),
        "work_subtype": rows[0].get("work_subtype"),
        "attributes": rows[0].get("attributes") or {},
        "active": rows[0].get("active"),
    }
    merged.update({k: v for k, v in payload.items() if k in ALLOWED_PAYLOAD_KEYS})
    row = validate_payload(merged, partial=False)
    row["updated_at"] = serialize_business_datetime(now_kst())
    res = (
        supabase.table(TABLE)
        .update(row)
        .eq("id", fact_id)
        .eq("factory_id", factory_id)
        .execute()
    )
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise KeyError("work fact not found")
    return data[0]


def deactivate_work_fact(supabase, factory_id: str, fact_id: str) -> Dict[str, Any]:
    return update_work_fact(supabase, factory_id, fact_id, {"active": False})
