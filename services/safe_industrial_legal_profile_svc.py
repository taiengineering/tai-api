"""services/safe_industrial_legal_profile_svc.py

WO-SAFE-LEGAL-IND-IMPLEMENT-001 / STEP 3 — facility-level supplemental persistence.

Marketing INDUSTRIAL paid contract(29) 중 Safe 기본 factories model 에 없는
facility-level supplemental 12개를 factory_legal_diagnosis_profile 에 저장/조회한다.

이 STEP 은 persistence 만 담당한다. 29-field assembler / process_list / equipment_list /
input-preview / run-leg 는 후속 STEP. 여기서 process/equipment supplemental 도 다루지 않는다.

원칙:
- NULL=미확인 / []=명시적 없음 / false=명시적 아니오 / 0=실제 숫자 0 을 절대 병합하지 않는다(truthy filter 금지).
- server-managed field(id/factory_id/contract_version/created_at/updated_at)는 client 가 덮어쓸 수 없다.
- vocabulary 검증 SoT = current active Marketing INDUSTRIAL diagnosis_input_fields (하드카피 금지).
- 추정/파생/자동 mutate 금지(예: has_*=false 라고 짝 numeric 을 0 으로 강제하지 않는다).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from services.time import now_kst, serialize_business_datetime


class LegalDiagnosisProfileBody(BaseModel):
    """PUT body — 정확히 facility supplemental 12개만. 추가 key(company_id/contract_version/
    factory_id/created_at/updated_at 등)는 extra=forbid 로 422 거부(WO §6/§17)."""
    work_height_m: Optional[float] = None
    has_truck_loading_unloading: Optional[bool] = None
    truck_loading_height_m: Optional[float] = None
    has_manual_heavy_handling: Optional[bool] = None
    manual_handling_weight_kg: Optional[float] = None
    business_activity_types: Optional[List[str]] = None
    hazardous_work_environments: Optional[List[str]] = None
    ksic_list: Optional[List[str]] = None
    total_floor_area: Optional[float] = None
    material_profile: Optional[List[Dict[str, Any]]] = None
    building_qualifications: Optional[List[str]] = None
    regulated_facility_types: Optional[List[str]] = None

    class Config:
        extra = "forbid"

# ── contract (server-fixed single SoT) ─────────────────────────────────
CONTRACT_VERSION = "MKT_IND_PAID_CONTRACT_V1"

# facility supplemental allowlist — 정확히 12개 (WO §6)
FACILITY_SUPPLEMENTAL_FIELDS = (
    "work_height_m",
    "has_truck_loading_unloading",
    "truck_loading_height_m",
    "has_manual_heavy_handling",
    "manual_handling_weight_kg",
    "business_activity_types",
    "hazardous_work_environments",
    "ksic_list",
    "total_floor_area",
    "material_profile",
    "building_qualifications",
    "regulated_facility_types",
)

NUMERIC_FIELDS = ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg", "total_floor_area")
BOOLEAN_FIELDS = ("has_truck_loading_unloading", "has_manual_heavy_handling")
# diagnosis_input_fields.field_code 로 vocabulary 를 로드하는 multi_select 축
VOCAB_ARRAY_FIELDS = ("business_activity_types", "hazardous_work_environments",
                      "building_qualifications", "regulated_facility_types")

# server/DB 만 결정 — client body 에 오면 거부(라우터 pydantic extra=forbid) + row 조립에서 미반영
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
    """current active INDUSTRIAL diagnosis_input_fields 에서 허용 vocabulary set 로드.

    반환 key: 4개 multi_select field_code + 'material_category' + 'material_handling_modes'.
    로드 실패는 호출부에서 fail-closed 처리(검증 불가 시 저장 거부).
    """
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


# ── validation (pure; vocab injected) ──────────────────────────────
def _reject(msg: str, code: int = 422):
    raise HTTPException(status_code=code, detail=msg)


def validate_profile(body: Dict[str, Any], vocab: Dict[str, set]) -> Dict[str, Any]:
    """body(dict) → cleaned dict(정확히 12 key). 값은 verbatim(변형/추정 없음).

    None/[]/False/0 은 각각 보존한다. 잘못된 값만 422. truthy filter 금지.
    """
    if not isinstance(body, dict):
        _reject("본문(dict) 형식이 아닙니다")

    cleaned: Dict[str, Any] = {f: body.get(f) for f in FACILITY_SUPPLEMENTAL_FIELDS}

    # numeric: None 허용, 0 허용, 음수 거부, bool 은 numeric 아님
    for f in NUMERIC_FIELDS:
        v = cleaned[f]
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            _reject(f"'{f}' 값이 숫자가 아닙니다")
        if v < 0:
            _reject(f"'{f}' 값은 0 이상이어야 합니다")

    # boolean: None 허용, bool 만
    for f in BOOLEAN_FIELDS:
        v = cleaned[f]
        if v is None:
            continue
        if not isinstance(v, bool):
            _reject(f"'{f}' 값이 boolean 이 아닙니다")

    # vocab arrays: None 허용, [] 허용, 원소는 Marketing vocabulary subset
    for f in VOCAB_ARRAY_FIELDS:
        v = cleaned[f]
        if v is None:
            continue
        if not isinstance(v, list):
            _reject(f"'{f}' 값이 배열이 아닙니다")
        allowed = vocab.get(f) or set()
        bad = [x for x in v if x not in allowed]
        if bad:
            _reject(f"'{f}' 에 허용되지 않은 값: {bad}")

    # ksic_list: None 허용, [] 허용, 문자열 배열(STEP3 는 vocab merge 하지 않음)
    kv = cleaned["ksic_list"]
    if kv is not None:
        if not isinstance(kv, list) or any(not isinstance(x, str) for x in kv):
            _reject("'ksic_list' 는 문자열 배열이어야 합니다")

    # material_profile: None 허용, [] 허용, row exact keys ⊆ {material_category, handling_modes}
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

    return cleaned


# ── row build / representations (pure) ────────────────────────────
def build_upsert_row(factory_id: str, cleaned: Dict[str, Any]) -> Dict[str, Any]:
    """DB upsert row. server-managed field 강제(client 값 무시), 12 field verbatim."""
    row: Dict[str, Any] = {"factory_id": factory_id, "contract_version": CONTRACT_VERSION}
    for f in FACILITY_SUPPLEMENTAL_FIELDS:
        row[f] = cleaned.get(f)  # None/[]/False/0 그대로
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


# ── DB thin wrappers ───────────────────────────────────────
def get_profile(supabase, factory_id: str) -> Dict[str, Any]:
    """profile 조회. 없으면 empty representation(=DB mutation 0)."""
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
    """1 factory : 1 profile upsert(factory_id UNIQUE). 반복 PUT = row 증가 0."""
    row = build_upsert_row(factory_id, cleaned)
    res = (
        supabase.table("factory_legal_diagnosis_profile")
        .upsert(row, on_conflict="factory_id")
        .execute()
    )
    saved = (getattr(res, "data", None) or [row])[0]
    return to_response(factory_id, saved)
