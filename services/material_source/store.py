"""factory_materials persistence + authoritative master catalog.

Legal classification authority is material_master_key → catalog only.
Free-text material_name is never classified. Query failure is not empty source.
This package is not wired into LEG diagnosis in this WO.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.time import now_kst, serialize_business_datetime
from services.material_source.builder import load_catalog
from services.material_source.registry import ALLOWED_FACTORY_PAYLOAD_KEYS

log = logging.getLogger("material_source.store")

TABLE = "factory_materials"
FACTORY_SELECT = (
    "id, factory_id, material_name, material_category_code, handling_mode_codes, "
    "material_master_key, is_active, created_at"
)


class MaterialSourceValidationError(ValueError):
    pass


class MaterialSourceLoadError(RuntimeError):
    """DB/query failure. Must not be treated as empty source."""

    code = "MATERIAL_SOURCE_UNAVAILABLE"

    def __init__(self, message: str, *, factory_id: Optional[str] = None):
        super().__init__(message)
        self.factory_id = factory_id


def _blank(val: Any) -> bool:
    return val is None or (isinstance(val, str) and not val.strip())


def catalog_index(authority_dir=None) -> Dict[str, Any]:
    catalog = load_catalog(authority_dir)
    materials = list(catalog["materials"])
    by_key = {row["material_key"]: row for row in materials}
    class_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for row in catalog["classifications"]:
        class_by_key.setdefault(row["material_key"], []).append(row)
    return {
        "materials": materials,
        "by_key": by_key,
        "classifications_by_key": class_by_key,
        "counts": catalog["counts"],
        "MATERIAL_MASTER_HASH": catalog["MATERIAL_MASTER_HASH"],
        "CLASSIFICATION_HASH": catalog["CLASSIFICATION_HASH"],
        "CATALOG_HASH": catalog["CATALOG_HASH"],
    }


def lookup_master_exact(query: str, *, authority_dir=None) -> List[Dict[str, Any]]:
    """Exact / deterministic master lookup. No fuzzy bind."""
    if _blank(query):
        return list(catalog_index(authority_dir)["materials"])
    q = str(query).strip()
    hits = []
    for row in catalog_index(authority_dir)["materials"]:
        if row["material_key"] == q or row["display_name"] == q or row.get("cas_no") == q:
            hits.append(row)
    return hits


def master_with_classifications(row: Dict[str, Any], *, authority_dir=None) -> Dict[str, Any]:
    idx = catalog_index(authority_dir)
    out = dict(row)
    classes = idx["classifications_by_key"].get(row["material_key"], [])
    out["classifications"] = [
        {
            "classification_code": c["classification_code"],
            "source_ref": c["source_ref"],
            "source_version": c["source_version"],
        }
        for c in classes
    ]
    return out


def validate_factory_payload(
    payload: Dict[str, Any], *, partial: bool = False, authority_dir=None
) -> Dict[str, Any]:
    extra = set(payload) - ALLOWED_FACTORY_PAYLOAD_KEYS
    if extra:
        raise MaterialSourceValidationError(
            "unsupported keys: {}".format(sorted(extra))
        )
    out: Dict[str, Any] = {}
    if "material_name" in payload or not partial:
        name = payload.get("material_name")
        if _blank(name):
            raise MaterialSourceValidationError("material_name required")
        out["material_name"] = str(name).strip()
    if "material_category_code" in payload:
        val = payload.get("material_category_code")
        out["material_category_code"] = None if _blank(val) else str(val)
    if "handling_mode_codes" in payload:
        val = payload.get("handling_mode_codes")
        if val is None:
            out["handling_mode_codes"] = None
        elif isinstance(val, list) and all(isinstance(x, str) for x in val):
            out["handling_mode_codes"] = val
        else:
            raise MaterialSourceValidationError("handling_mode_codes must be a string list or null")
    if "material_master_key" in payload:
        key = payload.get("material_master_key")
        if _blank(key):
            out["material_master_key"] = None
        else:
            key = str(key).strip()
            if key not in catalog_index(authority_dir)["by_key"]:
                raise MaterialSourceValidationError("unknown material_master_key")
            out["material_master_key"] = key
    if "is_active" in payload:
        if payload["is_active"] is not True and payload["is_active"] is not False:
            raise MaterialSourceValidationError("is_active must be boolean")
        out["is_active"] = payload["is_active"]
    elif not partial:
        out["is_active"] = True
    return out


def _rows_or_raise(res: Any, factory_id: str) -> List[Dict[str, Any]]:
    error = getattr(res, "error", None)
    if error:
        raise MaterialSourceLoadError(
            "factory_materials query error: {}".format(error),
            factory_id=factory_id,
        )
    data = getattr(res, "data", None)
    if not isinstance(data, list):
        raise MaterialSourceLoadError(
            "factory_materials returned non-list payload",
            factory_id=factory_id,
        )
    return data


def list_factory_materials(
    supabase, factory_id: str, *, include_inactive: bool = False
) -> List[Dict[str, Any]]:
    try:
        q = (
            supabase.table(TABLE)
            .select(FACTORY_SELECT)
            .eq("factory_id", factory_id)
        )
        if not include_inactive:
            q = q.eq("is_active", True)
        res = q.order("created_at").execute()
    except MaterialSourceLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 — missing table / transport / client errors
        log.error("factory_materials query failed factory=%s: %s", factory_id, exc)
        raise MaterialSourceLoadError(
            "factory_materials query failed",
            factory_id=factory_id,
        ) from exc
    return _rows_or_raise(res, factory_id)


def load_factory_material_rows_optional(supabase, factory_id: Optional[str]) -> List[Dict[str, Any]]:
    """Source seam. No factory_id → no query. Query failure is not empty source."""
    if not factory_id:
        return []
    if supabase is None:
        raise MaterialSourceLoadError(
            "material source client missing",
            factory_id=factory_id,
        )
    return list_factory_materials(supabase, factory_id, include_inactive=False)


def create_factory_material(
    supabase, factory_id: str, payload: Dict[str, Any], *, authority_dir=None
) -> Dict[str, Any]:
    row = validate_factory_payload(payload, partial=False, authority_dir=authority_dir)
    row["factory_id"] = factory_id
    row["created_at"] = serialize_business_datetime(now_kst())
    res = supabase.table(TABLE).insert(row).execute()
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise RuntimeError("factory_materials insert returned no row")
    return data[0]


def update_factory_material(
    supabase,
    factory_id: str,
    material_id: str,
    payload: Dict[str, Any],
    *,
    authority_dir=None,
) -> Dict[str, Any]:
    existing = (
        supabase.table(TABLE)
        .select(FACTORY_SELECT)
        .eq("id", material_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    rows = list(getattr(existing, "data", None) or [])
    if not rows:
        raise KeyError("factory material not found")
    merged = {
        "material_name": rows[0].get("material_name"),
        "material_category_code": rows[0].get("material_category_code"),
        "handling_mode_codes": rows[0].get("handling_mode_codes"),
        "material_master_key": rows[0].get("material_master_key"),
        "is_active": rows[0].get("is_active"),
    }
    merged.update({k: v for k, v in payload.items() if k in ALLOWED_FACTORY_PAYLOAD_KEYS})
    row = validate_factory_payload(merged, partial=False, authority_dir=authority_dir)
    res = (
        supabase.table(TABLE)
        .update(row)
        .eq("id", material_id)
        .eq("factory_id", factory_id)
        .execute()
    )
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise KeyError("factory material not found")
    return data[0]


def deactivate_factory_material(supabase, factory_id: str, material_id: str) -> Dict[str, Any]:
    return update_factory_material(
        supabase, factory_id, material_id, {"is_active": False}
    )
