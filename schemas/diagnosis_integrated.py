import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class WorkRowInput(BaseModel):
    """Transient work row for Paid diagnosis. Reuses work_source.store.validate_payload
    for registry-based semantic validation after schema validation. extra=forbid prevents
    canonical LEG field injection."""
    model_config = ConfigDict(extra="forbid")

    work_type: str
    work_subtype: Optional[str] = None
    equipment_ref: Optional[str] = None
    material_ref: Optional[str] = None
    location_ref: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    active: StrictBool = True


class MaterialRowInput(BaseModel):
    """Transient material row for Paid diagnosis. classification_codes is EXCLUDED —
    legal classification is catalog-derived only via material_master_key → catalog.
    extra=forbid prevents classification_codes injection."""
    model_config = ConfigDict(extra="forbid")

    material_master_key: Optional[str] = None
    handling_mode_codes: Optional[List[str]] = None
    is_active: StrictBool = True


class DisclaimerBody(BaseModel):
    auth_token: str = Field(..., description="본인인증 auth_token")
    agreed: bool = Field(..., description="true이어야 진단 실행 가능")
    ip_address: Optional[str] = Field(None, description="FE에서 수집한 제출자 IP")
    user_agent: Optional[str] = Field(None, description="User-Agent")


class DiagnosisRunBody(BaseModel):
    auth_token: Optional[str] = Field(None, description="본인인증 auth_token. 없으면 로그인+본인인증 회원은 서버가 diagnosis_auth_log 를 복원(WO-006). anonymous 완화 아님")
    disclaimer_log_id: Optional[str] = Field(
        None, description="면책 동의 ID (무료 필수, 유료 직입 시 서버 자동 생성 가능)"
    )
    sector: str = Field(..., description="BUILDING | INDUSTRY | INDUSTRIAL | CONSTRUCTION | SPECIAL_FACILITY")
    tier: Optional[str] = Field(None, description="FREE | PAID | BASIC | STANDARD | PREMIUM")
    form_data: Optional[Dict[str, Any]] = Field(None, description="공식 유료 applicability envelope (field_code → value). run_diagnosis 가 canonical_applicability(_LEG_INPUT_FIELDS exact-name) 로 소비하여 DiagnoseStep1Body.input 으로 lossless materialize (WO-FE-CST-GAP-IMPL-001 E-B4 FROZEN, Nexas 무관)")
    floor_area: Optional[float] = Field(None, description="바닥면적(㎡) — BUILDING")
    total_floor_area: Optional[float] = Field(None, description="연면적(㎡)")
    contract_amount_eok: Optional[float] = Field(None, description="공사금액(억원) — CONSTRUCTION")
    user_tier: Optional[str] = Field(None, description="산업(INDUSTRIAL) 사용자 선택 티어")
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    worker_count: Optional[int] = None
    employee_count: Optional[int] = None
    ksic_major: Optional[str] = None
    building_use_type: Optional[str] = None
    construction_type: Optional[str] = Field(None, description="음/토/건축/기능 등")
    # WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001
    # Explicit canonical legal facts. Optional additive. missing != false.
    # No alias. No sector/order_type/kcsc derivation. Server fail-closed is later.
    is_construction: Optional[bool] = Field(
        None,
        description="산업안전보건법 시행령 별표 3 제49호 건설업 해당 여부. True=예, False=아니오, None=미확정",
    )
    is_relationship_contractor: Optional[bool] = Field(
        None,
        description="이 공사에서 관계수급인 해당 여부. True=예, False=아니오, None=미확정",
    )
    is_civil_construction: Optional[bool] = Field(
        None,
        description="해당 공사가 토목공사업 해당 여부. True=예, False=아니오, None=미확정",
    )
    # WO-SM-CORE22-AP01-05-EXPLICIT-APPENDIX3-INPUT-CONTRACT-001
    # Explicit legal classification fact (별표 3 호). Strict JSON integer 1..49.
    # Not KSIC/sector/industry derived. Internal AP01~05 leaves are not user fields.
    appendix3_item_no: Optional[StrictInt] = Field(
        None,
        ge=1,
        le=49,
        description="산업안전보건법 시행령 별표 3 사업 종류 호. JSON integer 1..49 only.",
    )
    is_real_estate_management: Optional[StrictBool] = Field(
        None,
        description="별표 3 제37호(부동산업)인 경우에만 사용. 부동산 관리업 여부. missing≠false.",
    )
    region: Optional[str] = None
    payment_ref: Optional[str] = Field(None, description="유료 결제 참조 번호 (무료이면 생략)")
    invoice_requested: bool = Field(False, description="세금계산서 요청 여부")
    invoice_biz_no: Optional[str] = Field(None, description="세금계산서 사업자등록번호")
    invoice_email: Optional[str] = Field(None, description="세금계산서 수신 이메일")
    invoice_company_name: Optional[str] = Field(None, description="세금계산서 상호")
    factory_id: Optional[str] = Field(None, description="SaaS 사업장 ID — 있으면 Binding Engine 호출")
    company_id: Optional[str] = Field(None, description="SaaS tenant(회사) ID — factory_id와 함께 사용")
    # P5-01: 시설 입력 전달용 (Week1 = 시설 범위)
    floor_count: Optional[int] = None
    electric_capacity: Optional[float] = None
    elevator_count: Optional[int] = None
    has_gas: Optional[bool] = None
    has_chemical: Optional[bool] = None
    is_multi_use: Optional[bool] = None
    has_boiler: Optional[bool] = None
    has_hazardous_material: Optional[bool] = None
    has_high_pressure_gas: Optional[bool] = None
    has_chemical_substance: Optional[bool] = None
    project_amount: Optional[float] = None
    # ── WO-FE-IND-GAP-051-TRANSPORT-001: paid structured RAW INPUT transport 계약 ──
    # RAW ENVELOPE(사용자가 실제 입력한 구조화 값)이며 CANONICAL LEG APPLICABILITY 와 분리된다.
    # 이 필드들은 backend 가 lossless 수신·보존(input_data JSONB)만 하며,
    # canonical_applicability(_LEG_INPUT_FIELDS) / build_facility semantic projection 에는
    # 자동 주입하지 않는다(RAW ≠ CANONICAL). form_data(=canonical envelope)에 넣지 않는다.
    input: Optional[Dict[str, Any]] = Field(None, description="paid STEP1 raw scalar/structured 값 (엔진 canonical 과 분리)")
    process_list: Optional[List[Dict[str, Any]]] = Field(None, description="paid STEP2 공정 row raw 구조(process_name/hazard_codes/worker_count/is_primary/future activity_type[])")
    equipment_list: Optional[List[Dict[str, Any]]] = Field(None, description="paid STEP3 설비 row raw 구조(equipment_type/asset_name/quantity/.../future usage_type[]/relation_type[])")
    ksic_list: Optional[List[str]] = Field(None, description="paid 다중 KSIC 대분류 raw 목록")
    # Wave A1 — transient structured source rows (Paid path).
    # work_rows: validated via work_source.store.validate_payload; projected via work_source.projector.
    # material_rows: projected via material_source.canonical_adapter; classification_codes FORBIDDEN.
    # Neither field mutates factory_work_facts or factory_materials (transient only).
    work_rows: Optional[List[WorkRowInput]] = Field(None, description="Wave A1: Paid 일시적 작업 rows. work_source validate_payload + projector 경유. DB 저장 없음.")
    material_rows: Optional[List[MaterialRowInput]] = Field(None, description="Wave A1: Paid 일시적 자재 rows. material_master_key → catalog 경유. classification_codes 금지. DB 저장 없음.")

    @field_validator("form_data", mode="before")
    @classmethod
    def _validate_form_data_numerics(cls, v):
        """Block negative / non-finite numbers in form_data.
        0 is valid (present, zero value). None/absent fields are not checked.

        Parent-child contract (matches FF-06 SafeXxxConsumerInput):
          truck_loading_height_m  requires has_truck_loading_unloading=true
          manual_handling_weight_kg requires has_manual_heavy_handling=true
        parent absent or false + child present → rejected.
        """
        if not isinstance(v, dict):
            return v
        for key, val in v.items():
            if isinstance(val, bool):
                continue
            if isinstance(val, (int, float)):
                if not math.isfinite(val):
                    raise ValueError(f"form_data[{key!r}] must be a finite number")
                if val < 0:
                    raise ValueError(f"form_data[{key!r}] must be non-negative (got {val})")
        # Strict type guard for fields that must be a finite number when present.
        # Strings, lists, dicts, and other non-numeric types are rejected — not coerced.
        _NUMERIC_STRICT = frozenset({"work_height_m", "truck_loading_height_m", "manual_handling_weight_kg"})
        for key in _NUMERIC_STRICT:
            val = v.get(key)
            if val is None:
                continue
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(
                    f"form_data[{key!r}] must be a number, got {type(val).__name__!r}"
                )
        # Parent-child enforcement — FF-06 contract parity on form_data envelope.
        _PARENT_CHILD: dict = {
            "truck_loading_height_m": "has_truck_loading_unloading",
            "manual_handling_weight_kg": "has_manual_heavy_handling",
        }
        for child_key, parent_key in _PARENT_CHILD.items():
            child_val = v.get(child_key)
            if child_val is None:
                continue  # absent child: allowed regardless of parent
            parent_val = v.get(parent_key)  # None = key absent from form_data
            if parent_val is not True:
                raise ValueError(
                    f"form_data[{child_key!r}] requires {parent_key!r}=true "
                    f"(got parent={'absent' if parent_key not in v else repr(parent_val)})"
                )
        return v

    @field_validator("appendix3_item_no", mode="before")
    @classmethod
    def _strict_appendix3_item_no(cls, v):
        if v is None:
            return None
        if type(v) is not int or type(v) is bool:
            raise ValueError("appendix3_item_no must be a JSON integer 1..49")
        return v

    @field_validator("is_real_estate_management", mode="before")
    @classmethod
    def _strict_is_real_estate_management(cls, v):
        if v is None:
            return None
        if type(v) is not bool:
            raise ValueError("is_real_estate_management must be a JSON boolean")
        return v


class UpgradeBody(BaseModel):
    auth_token: str = Field(..., description="본인인증 auth_token")
    public_token: str = Field(..., description="기존 진단 public_token")
    target_tier_code: str = Field(..., description="업그레이드 목표 티어")
    payment_ref: str = Field(..., description="결제 참조 번호")
    invoice_requested: bool = Field(False, description="세금계산서 요청 여부")
    invoice_biz_no: Optional[str] = Field(None, description="세금계산서 사업자등록번호")
    invoice_email: Optional[str] = Field(None, description="세금계산서 수신 이메일")
    invoice_company_name: Optional[str] = Field(None, description="세금계산서 상호")
