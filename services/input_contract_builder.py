"""Input Contract Builder — sector + worker_count + has_* (CURSOR-TASK-002 TASK-004)."""
from __future__ import annotations

from typing import Any, Dict, List

from constants.exists_mvp_fields import (
    FACTORY_COLUMN_TO_FIELD_CODE,
    MVP_FIELD_CODES_BY_SECTOR,
)
from services.exists_input_service import (
    _merge_exists_inputs_from_factory,
    _worker_count,
    load_exists_inputs,
)


def _true_has_keys(contract: Dict[str, Any]) -> List[str]:
    return sorted(k for k, v in contract.items() if k.startswith("has_") and v is True)


def _all_has_keys(contract: Dict[str, Any]) -> List[str]:
    return sorted(k for k in contract if k.startswith("has_"))


def build_input_contract(factory_row: dict, exists_inputs: Dict[str, bool]) -> Dict[str, Any]:
    """단일 Contract 조립. Applicability Engine이 읽는 형태."""
    sector = (factory_row.get("sector") or "INDUSTRIAL").upper()
    merged = _merge_exists_inputs_from_factory(factory_row, exists_inputs)

    contract: Dict[str, Any] = {
        "factory_id": str(factory_row["id"]),
        "sector": sector,
        "ksic_code": factory_row.get("ksic_code"),
        "worker_count": _worker_count(factory_row),
    }

    mvp_codes = MVP_FIELD_CODES_BY_SECTOR.get(sector, [])
    for code in mvp_codes:
        if code in merged:
            contract[code] = bool(merged[code])

    for code, value in merged.items():
        if code.startswith("has_") and code not in contract:
            contract[code] = bool(value)

    return contract


def build_input_contract_for_factory(factory_id: str, supabase) -> Dict[str, Any]:
    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac_res.data:
        raise ValueError("사업장을 찾을 수 없습니다")
    exists_inputs = load_exists_inputs(factory_id, supabase)
    return build_input_contract(fac_res.data, exists_inputs)


def contract_has_stats(contract: Dict[str, Any]) -> Dict[str, Any]:
    true_keys = _true_has_keys(contract)
    all_keys = _all_has_keys(contract)
    return {
        "has_field_count": len(all_keys),
        "has_true_count": len(true_keys),
        "has_true_fields": true_keys,
    }


def reverse_factory_has_fields(factory_row: dict) -> Dict[str, bool]:
    """factories 컬럼만으로 복원 가능한 has_* (디버그/검증용)."""
    out: Dict[str, bool] = {}
    for col, field_code in FACTORY_COLUMN_TO_FIELD_CODE.items():
        if col in factory_row and factory_row[col] is not None:
            out[field_code] = bool(factory_row[col])
    return out
