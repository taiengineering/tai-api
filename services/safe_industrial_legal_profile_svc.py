"""services/safe_industrial_legal_profile_svc.py

WO-SAFE-LEGAL-IND-IMPLEMENT-001-R2 / STEP 3 — facility-level supplemental persistence (R2 contract).

R2 corrections vs R1:
- total_floor_area REMOVED from profile (정본 = factories.building_area; assembler TRANSFORM. 중복 SoT 금지).
- building_use_type_override / main_structure_override ADDED (string|NULL only; vocabulary 검증은 후속 단계).
- PROFILE FIELD SET = 13 (ADD7 + GAP/normalized6).
- sparse partial-merge: router 가 body.dict(exclude_unset=True) 를 넘김 → provided-only keys 만 처리.
    omitted field = 기존 값 보존 / explicit NULL = NULL 로 clear (upsert_profile 이 existing 읽어 merge).
- unknown field(총 total_floor_area 포함) → pydantic extra='forbid' 로 422.

불변 원칙: NULL(미확인) / [](명시적 없음) / false / 0 을 절대 병합/삭제하지 않는다(truthy filter 금지).
server-managed(id/factory_id/contract_version/created_at/updated_at)는 client 가 못 덮어쓴다. company_id 미저장.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, StrictStr

from services.time import now_kst, serialize_business_datetime


class LegalDiagnosisProfileBody(BaseModel):
    """PUT body — 정확히 facility supplemental 13개만. 추가 key(total_floor_area/company_id/contract_version/
    factory_id/created_at/updated_at 등)는 extra=forbid 로 422 거부(R2 §7). overrides 는 StrictStr(문자열만)."""
    work_height_m: Optional[float] = None
    has_truck_loading_unloading: Optional[bool] = None
    truck_loading_height_m: Optional[float] = None
    has_manual_heavy_handling: Optional[bool] = None
    manual_handling_weight_kg: Optional[float] = None
    business_activity_types: Optional[List[str]] = None
    hazardous_work_environments: Optional[List[str]] = None
    ksic_list: Optional[List[str]] = None
    material_profile: Optional[List[Dict[str, Any]]] = None
    building_qualifications: Optional[List[str]] = None
    regulated_facility_types: Optional[List[str]] = None
    building_use_type_override: Optional[StrictStr] = None
    main_structure_override: Optional[StrictStr] = None

    class Config:
        extra = "forbid"

# ── contract (server-fixed single SoT) ──────────────────
CONTRACT_VERSION = "MKT_IND_PAID_CONTRACT_V1"

# facility supplemental allowlist — 정확히 13개 (R2: ADD7 + GAP/normalized6; total_floor_area 제거)
FACILITY_SUPPLEMENTAL_FIELDS = (
    "work_height_m",
    "has_truck_loading_unloading",
    "truck_loading_height_m",
    "has_manual_heavy_handling",
    "manual_handling_weight_kg",
    "business_activity_types",
    "hazardous_work_environments",
    "ksic_list",
    "material_profile",
    "building_qualifications",
    "regulated_facility_types",
    "building_use_type_override",
    "main_structure_override",
)

NUMERIC_FIELDS = ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg")  # total_floor_area 제거
BOOLEAN_FIELDS = ("has_truck_loading_unloading", "has_manual_heavy_handling")
VOCAB_ARRAY_FIELDS = ("business_activity_types", "hazardous_work_environments",
                      "building_qualifications", "regulated_facility_types")
OVERRIDE_FIELDS = ("building_use_type_override", "main_structure_override")  # string|NULL only

SERVER_MANAGED_FIELDS = ("id", "factory_id", "contract_version", "created_at", "updated_at")


def _now_iso() -> str:
    return serialize_business_datetime(now_kst())


# ── vocabulary loader (Marketing diagnosis_input_fields = SoT) ───────────────
def _opt_value(o: Any) -> Optional[str]:
    if isinstance(o, str):
        return o
    if isinstance(o, dict):
        return o.get("value") or o.get("label")
    return None


def load_marketing_vocab(supabase) -> Dict[str, set]:
    """current active INDUSTRIAL diagnosis_input_fields 에서 허용 vocabulary set 로드(하드코딩 금지)."""
    res = (
        supabase.table("diagnosis_input_fields")
        .select("field_code, field_type, input_options")
        .eq("sector", "INDUSTRIAL")
        .eq("is_active", True)
        .execute()
    )
    rows = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else None) or []
    vocab: Dict[str, set] = {f: set() for f in VOCAB_ARRAY_FIELDS}
    vocab["material_category"] = set()
    vocab["material_handling_modes"] = set()
    for r in rows:
        fc = r.get("field_code")
        opts = r.get("input_options")
        if fc in VOCAB_ARRAY_FIELDS and isinstance(opts, list):
            vocab[fc] = {v for v in (_opt_value(o) for o in opts) if v is not None}
        elif fc == "material_profile" and isinstance(opts, dict):
            for col in opts.get("columns", []) or []:
                key = col.get("key")
                if key == "material_category":
                    vocab["material_category"] = {v for v in (_opt_value(o) for o in (col.get("options") or [])) if v is not None}
                elif key == "handling_modes":
                    vocab["material_handling_modes"] = {v for v in (_opt_value(o) for o in (col.get("options") or [])) if v is not None}
    return vocab


# ── validation (pure; sparse provided-only; vocab injected) ──────────────
def _reject(msg: str, code: int = 422):
    raise HTTPException(status_code=code, detail=msg)


def validate_profile(body: Dict[str, Any], vocab: Dict[str, set]) -> Dict[str, Any]:
    """body(provided-only dict) → cleaned(provided-only, 동일 key). 값 verbatim.

    sparse: body 에 없는 key 는 cleaned 에도 없음(omitted). 있는 key 만 검증(explicit NULL 포함).
    None/[]/False/0 각각 보존. 잘못된 값만 422. omitted key 를 None 으로 만들지 않는다.
    """
    if not isinstance(body, dict):
        _reject("본문(dict) 형식이 아닙니다")

    cleaned: Dict[str, Any] = {f: body[f] for f in FACILITY_SUPPLEMENTAL_FIELDS if f in body}

    for f in NUMERIC_FIELDS:
        if f not in cleaned:
            continue
        v = cleaned[f]
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            _reject(f"'{f}' 값이 숫자가 아닙니다")
        if v < 0:
            _reject(f"'{f}' 값은 0 이상이어야 합니다")

    for f in BOOLEAN_FIELDS:
        if f not in cleaned:
            continue
        v = cleaned[f]
        if v is None:
            continue
        if not isinstance(v, bool):
            _reject(f"'{f}' 값이 boolean 이 아닙니다")

    for f in VOCAB_ARRAY_FIELDS:
        if f not in cleaned:
            continue
        v = cleaned[f]
        if v is None:
            continue
        if not isinstance(v, list):
            _reject(f"'{f}' 값이 배열이 아닙니다")
        bad = [x for x in v if x not in (vocab.get(f) or set())]
        if bad:
            _reject(f"'{f}' 에 허용되지 않은 값: {bad}")

    if "ksic_list" in cleaned:
        kv = cleaned["ksic_list"]
        if kv is not None:
            if not isinstance(kv, list) or any(not isinstance(x, str) for x in kv):
                _reject("'ksic_list' 는 문자열 배열이어야 합니다")

    if "material_profile" in cleaned:
        mp = cleaned["material_profile"]
        if mp is not None:
            if not isinstance(mp, list):
                _reject("'material_profile' 는 배열이어야 합니다")
            for row in mp:
                if not isinstance(row, dict):
                    _reject("'material_profile' 원소는 object 여야 합니다")
                extra = set(row.keys()) - {"material_category", "handling_modes"}
                if extra:
                    _reject(f"'material_profile' 허용되지 않은 key: {sorted(extra)}")
                mc = row.get("material_category")
                if mc is None or mc not in (vocab.get("material_category") or set()):
                    _reject(f"'material_profile.material_category' 허용되지 않은 값: {mc!r}")
                hm = row.get("handling_modes")
                if hm is not None:
                    if not isinstance(hm, list):
                        _reject("'material_profile.handling_modes' 는 배열이어야 합니다")
                    badm = [x for x in hm if x not in (vocab.get("material_handling_modes") or set())]
                    if badm:
                        _reject(f"'material_profile.handling_modes' 허용되지 않은 값: {badm}")

    # overrides: string|NULL only (vocabulary 검증은 후속 단계; bool 은 str 아님 → 거부)
    for f in OVERRIDE_FIELDS:
        if f not in cleaned:
            continue
        v = cleaned[f]
        if v is None:
            continue
        if not isinstance(v, str):
            _reject(f"'{f}' 값은 문자열이어야 합니다")

    return cleaned


# ── row build / representations (pure) ───────────────────
def build_upsert_row(factory_id: str, effective: Dict[str, Any]) -> Dict[str, Any]:
    """DB upsert row(full 13-field effective state). server-managed 강제, company_id 미포함."""
    row: Dict[str, Any] = {"factory_id": factory_id, "contract_version": CONTRACT_VERSION}
    for f in FACILITY_SUPPLEMENTAL_FIELDS:
        row[f] = effective.get(f)  # None/[]/False/0 그대로
    row["updated_at"] = _now_iso()
    return row


def empty_profile_representation(factory_id: str) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "factory_id": factory_id,
        "contract_version": CONTRACT_VERSION,
        "profile_exists": False,
        "updated_at": None,
    }
    for f in FACILITY_SUPPLEMENTAL_FIELDS:
        d[f] = None
    return d


def to_response(factory_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "factory_id": factory_id,
        "contract_version": row.get("contract_version") or CONTRACT_VERSION,
        "profile_exists": True,
        "updated_at": row.get("updated_at"),
    }
    for f in FACILITY_SUPPLEMENTAL_FIELDS:
        d[f] = row.get(f)
    return d


# ── DB thin wrappers ──────────────────────
def get_profile(supabase, factory_id: str) -> Dict[str, Any]:
    """profile 조회. 없으면 empty representation(=DB mutation 0). total_floor_area ABSENT."""
    res = (
        supabase.table("factory_legal_diagnosis_profile")
        .select("*")
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return empty_profile_representation(factory_id)
    return to_response(factory_id, rows[0])


def upsert_profile(supabase, factory_id: str, cleaned: Dict[str, Any]) -> Dict[str, Any]:
    """sparse partial-merge upsert (R2 §4).

    existing 13-field state 를 읽어 provided cleaned 로 overlay → full deterministic upsert.
    omitted key = 기존 보존 / explicit NULL(cleaned 에 None) = NULL clear. truthy merge 금지.
    factory_id UNIQUE → 반복 PUT row 증가 0.
    """
    res = (
        supabase.table("factory_legal_diagnosis_profile")
        .select("*")
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    existing = rows[0] if rows else None

    effective: Dict[str, Any] = {
        f: (existing.get(f) if existing else None) for f in FACILITY_SUPPLEMENTAL_FIELDS
    }
    for f, value in cleaned.items():   # provided-only overlay (explicit None 포함)
        effective[f] = value

    row = build_upsert_row(factory_id, effective)
    saved_res = (
        supabase.table("factory_legal_diagnosis_profile")
        .upsert(row, on_conflict="factory_id")
        .execute()
    )
    saved = (getattr(saved_res, "data", None) or [row])[0]
    return to_response(factory_id, saved)
