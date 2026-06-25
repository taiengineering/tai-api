"""EXISTS MVP has_* 저장 + facility_profiles 동기화 (CURSOR-TASK-002).

field_code는 변경하지 않는다. factories 컬럼 매핑은 영속화 보조용.
Applicability generator가 읽는 contract는 profile_snapshot.exists_inputs 기준.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from constants.exists_mvp_fields import (
    FIELD_CODE_SYNONYMS,
    FIELD_CODE_TO_FACTORY_COLUMN,
    MVP_FIELD_CODES_BY_SECTOR,
)
from services.facility_profile_service import build_facility_profile, profile_to_db_row


def normalize_field_code(field_code: str) -> str:
    """TASK-003: 확인된 동의어 2건만 정식 field_code로 변환."""
    code = (field_code or "").strip()
    return FIELD_CODE_SYNONYMS.get(code, code)


def normalize_exists_payload(raw: Dict[str, Any]) -> Dict[str, bool]:
    """요청 본문 → {정식 field_code: bool}."""
    out: Dict[str, bool] = {}
    for key, value in raw.items():
        if not key.startswith("has_") and key not in FIELD_CODE_SYNONYMS:
            continue
        code = normalize_field_code(key)
        if value is None:
            continue
        out[code] = bool(value)
    return out


def _worker_count(factory_row: dict) -> Optional[int]:
    for key in ("total_worker_count_calc", "employee_count", "subcontractor_worker_count"):
        val = factory_row.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _merge_exists_inputs_from_factory(
    factory_row: dict,
    exists_inputs: Dict[str, bool],
) -> Dict[str, bool]:
    """factories 컬럼 → field_code 역매핑 (exists_inputs에 없을 때만)."""
    merged = dict(exists_inputs)
    for col, field_code in {
        v: k for k, v in FIELD_CODE_TO_FACTORY_COLUMN.items()
    }.items():
        if field_code in merged:
            continue
        if col not in factory_row:
            continue
        val = factory_row.get(col)
        if val is not None:
            merged[field_code] = bool(val)
    return merged


def load_exists_inputs(factory_id: str, supabase) -> Dict[str, bool]:
    """최신 facility_profiles.profile_snapshot.exists_inputs 로드."""
    res = (
        supabase.table("facility_profiles")
        .select("profile_snapshot")
        .eq("factory_id", factory_id)
        .order("profile_version", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return {}
    snap = res.data[0].get("profile_snapshot") or {}
    raw = snap.get("exists_inputs") or {}
    return {k: bool(v) for k, v in raw.items() if k.startswith("has_")}


def build_factory_column_patch(
    exists_inputs: Dict[str, bool],
    factory_row: Optional[dict] = None,
) -> Dict[str, Any]:
    """exists_inputs → factories UPDATE 패치 (매핑·스키마에 있는 컬럼만)."""
    known_cols = set(factory_row.keys()) if factory_row else None
    patch: Dict[str, Any] = {}
    for field_code, value in exists_inputs.items():
        col = FIELD_CODE_TO_FACTORY_COLUMN.get(field_code)
        if not col:
            continue
        if known_cols is not None and col not in known_cols:
            continue
        patch[col] = bool(value)
    return patch


def save_exists_inputs(
    factory_id: str,
    exists_inputs: Dict[str, bool],
    supabase,
) -> Dict[str, Any]:
    """has_* 저장 → factories(매핑 컬럼) + facility_profiles.exists_inputs."""
    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac_res.data:
        raise ValueError("사업장을 찾을 수 없습니다")

    factory_row = fac_res.data
    sector = (factory_row.get("sector") or "INDUSTRIAL").upper()
    allowed = set(MVP_FIELD_CODES_BY_SECTOR.get(sector, []))
    filtered = {
        k: v for k, v in exists_inputs.items()
        if k.startswith("has_")
        and (k in allowed or k in FIELD_CODE_SYNONYMS.values())
    }

    prior = load_exists_inputs(factory_id, supabase)
    merged_inputs = {**prior, **filtered}

    factory_patch = build_factory_column_patch(merged_inputs, factory_row)
    if factory_patch:
        supabase.table("factories").update(factory_patch).eq("id", factory_id).execute()
        fac_res = (
            supabase.table("factories")
            .select("*")
            .eq("id", factory_id)
            .single()
            .execute()
        )
        factory_row = fac_res.data or factory_row

    profile = build_facility_profile(factory_row)
    profile["exists_inputs"] = merged_inputs
    profile["worker_count"] = _worker_count(factory_row)

    existing = (
        supabase.table("facility_profiles")
        .select("profile_version")
        .eq("factory_id", factory_id)
        .order("profile_version", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        profile["profile_version"] = existing.data[0]["profile_version"] + 1

    db_row = profile_to_db_row(profile)
    insert_res = supabase.table("facility_profiles").insert(db_row).execute()
    saved = (insert_res.data or [{}])[0]

    return {
        "factory_id": factory_id,
        "sector": sector,
        "exists_inputs": merged_inputs,
        "factory_columns_updated": list(factory_patch.keys()),
        "profile_id": str(saved.get("id", "")),
        "profile_version": saved.get("profile_version") or profile["profile_version"],
        "true_count": sum(1 for v in merged_inputs.values() if v),
    }


def fetch_mvp_field_definitions(sector: str, supabase) -> List[Dict[str, Any]]:
    """diagnosis_input_fields 조회 + MVP 폴백 병합."""
    from constants.exists_mvp_fields import MVP_EXISTS_FIELDS
    from constants.sectors import sector_codes_for_query
    from services.legal_rules import normalize_sector_db

    sector = normalize_sector_db(sector)
    mvp_rows = MVP_EXISTS_FIELDS.get(sector, [])
    codes = [r[0] for r in mvp_rows]

    db_map: Dict[str, dict] = {}
    if codes:
        res = (
            supabase.table("diagnosis_input_fields")
            .select(
                "field_code, field_name, field_type, field_group, "
                "help_text, sort_order, is_required"
            )
            .in_("field_code", codes)
            .in_("sector", list(sector_codes_for_query(sector)))
            .eq("field_type", "boolean")
            .eq("is_active", True)
            .execute()
        )
        for row in res.data or []:
            db_map[row["field_code"]] = row

    fields: List[Dict[str, Any]] = []
    for idx, (code, fallback_name, expected_count) in enumerate(mvp_rows):
        row = db_map.get(code, {})
        fields.append({
            "field_code": code,
            "field_name": row.get("field_name") or fallback_name,
            "field_type": "boolean",
            "field_group": row.get("field_group") or "EXISTS_MVP",
            "help_text": row.get("help_text"),
            "is_required": row.get("is_required", False),
            "sort_order": row.get("sort_order", idx + 1),
            "expected_obligation_count": expected_count,
            "source": "diagnosis_input_fields" if code in db_map else "mvp_fallback",
        })
    return fields
