"""Equipment source row validator + shared reader.

Authority: equipment_assets.equipment_type_code (numeric codes 001–040 + string aliases).
validate_equipment_source_row() gates structured source rows before projection.
load_equipment_rows_optional() is the shared diagnosis seam reader (extracted from
the CONSTRUCTION inline reader in diagnosis_integrated_svc — READ FAILURE != EMPTY SOURCE).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.equipment_source.canonicalizer import normalize_equipment_type_code

log = logging.getLogger(__name__)

# All valid equipment_type_code values recognised by the authority system.
# Numeric codes match equipment_type_inspection_map table (001–040, zero-padded).
# String aliases exist for legacy structured source rows in some integrations.
EQUIPMENT_AUTHORITY_CODES: frozenset = frozenset(
    {str(i).zfill(3) for i in range(1, 41)}
    | {"CRANE", "CONVEYOR", "PRESS", "PRESSURE_VESSEL"}
)


class EquipmentSourceValidationError(ValueError):
    pass


class EquipmentSourceLoadError(RuntimeError):
    code = "EQUIPMENT_SOURCE_UNAVAILABLE"

    def __init__(self, msg: str = "", *, factory_id: str = "") -> None:
        super().__init__(msg)
        self.factory_id = factory_id


def validate_equipment_source_row(
    payload: Dict[str, Any], *, partial: bool = False
) -> Dict[str, Any]:
    """Validate one equipment source row.

    - No code or None code → legacy row, returned as-is (backward compatibility).
    - Code in AUTHORITY but not in EQUIPMENT_CODE_MAP → valid; projector emits nothing.
    - Code not in AUTHORITY → EquipmentSourceValidationError.
    - is_operating present and not None → must be type(v) is bool.
    - attributes present and not None → must be dict.
    """
    code = payload.get("equipment_type_code")
    if code is None:
        return payload

    if not isinstance(code, str) or not code.strip():
        raise EquipmentSourceValidationError(
            "equipment_type_code: must be a non-empty string"
        )

    code = normalize_equipment_type_code(code)
    payload = {**payload, "equipment_type_code": code}

    if code not in EQUIPMENT_AUTHORITY_CODES:
        raise EquipmentSourceValidationError(
            "equipment_type_code {!r}: not in equipment authority (001–040)".format(code)
        )

    if "is_operating" in payload:
        val = payload["is_operating"]
        if val is not None and type(val) is not bool:
            raise EquipmentSourceValidationError(
                "is_operating: expected bool, got {!r}".format(type(val).__name__)
            )

    if "attributes" in payload:
        val = payload["attributes"]
        if val is not None and not isinstance(val, dict):
            raise EquipmentSourceValidationError(
                "attributes: expected dict, got {!r}".format(type(val).__name__)
            )

    return payload


def load_equipment_rows_optional(
    supabase, factory_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Diagnosis seam reader — extracted from CONSTRUCTION inline reader.

    No factory_id → no query (return []).
    Query failure → EquipmentSourceLoadError (READ FAILURE != EMPTY SOURCE).
    Callers must not treat [] and a load error the same way.
    SELECT minimum: equipment_type_code only (numeric attributes = HOLD).
    """
    if not factory_id:
        return []
    if supabase is None:
        raise EquipmentSourceLoadError(
            "equipment source client missing",
            factory_id=factory_id,
        )
    try:
        res = (
            supabase.table("equipment_assets")
            .select("equipment_type_code")
            .eq("factory_id", factory_id)
            .eq("is_operating", True)
            .execute()
        )
    except EquipmentSourceLoadError:
        raise
    except Exception as exc:
        log.error("equipment_assets query failed factory=%s: %s", factory_id, exc)
        raise EquipmentSourceLoadError(
            "equipment_assets query failed",
            factory_id=factory_id,
        ) from exc
    data = res.data if hasattr(res, "data") else None
    if data is None:
        raise EquipmentSourceLoadError(
            "equipment_assets response missing data",
            factory_id=factory_id,
        )
    if not isinstance(data, list):
        log.error(
            "equipment_assets response malformed factory=%s type=%s",
            factory_id,
            type(data).__name__,
        )
        raise EquipmentSourceLoadError(
            "equipment_assets response malformed: expected list, got {!r}".format(
                type(data).__name__
            ),
            factory_id=factory_id,
        )
    return data


# STRUCTURED_SOURCE_UPGRADE_REPLAY_CANDIDATE — STATUS: SEPARATE WO / NOT IMPLEMENTED
#
# initial run_diagnosis:
#   work_rows / material_rows / equipment_list → source validator/projector path exists.
#
# upgrade_diagnosis (tier upgrade re-run):
#   raw_structured_input stored on initial diagnosis is not replayed through
#   source validator/projector. Path not confirmed in diagnosis_integrated_svc.py.
#
# Possible effect:
#   Between initial diagnosis and a tier upgrade re-run, structured-source canonical
#   facts (e.g. has_boiler, has_press from equipment_list) may diverge because the
#   upgrade path does not re-project from stored structured sources.
#
# Note: this is distinct from the equipment_assets.attributes historical backfill
# problem (pre-Wave-A2 rows lacking attributes JSONB data) — that is a separate candidate.
#
# PATCH2: comment only. Implementation deferred to a dedicated WO.
