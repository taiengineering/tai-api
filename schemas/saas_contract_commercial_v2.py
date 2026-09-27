"""TAI Safe SaaS Commercial Contract Storage V2 — Persistence Domain Contract.

이 모듈은 DB 저장 계약과 validation만 정의한다.
- DB I/O: 0
- Runtime wiring: 0
- API endpoint: 0
- Legacy plan_code 재해석: 0
- max_user_count 재사용: 0
- max_factory_count 재사용: 0
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Set, Tuple
from uuid import UUID

from pydantic import BaseModel, StrictInt, field_validator, model_validator

from schemas.saas_pricing_v2 import (
    EntityType,
    ProductTier,
    PricingMode,
    SaasSector,
    SaasPricingSnapshotV2,
    VALID_TERM_MONTHS,
)

# ── Storage Schema Version ────────────────────────────────────────────────────

COMMERCIAL_STORAGE_SCHEMA_VERSION = "SAAS_CONTRACT_COMMERCIAL_V2"

# Sector → expected EntityType canonical mapping (mirrors saas_pricing_v2._SECTOR_ENTITY_MAP)
_SECTOR_ENTITY_MAP: Dict[str, str] = {
    "INDUSTRY":     "factory",
    "BUILDING":     "factory",
    "CONSTRUCTION": "site",
}

# Valid tier+mode combinations
_VALID_TIER_MODE_PAIRS: Set[Tuple[str, str]] = {
    ("MANAGER", "STANDARD"),
    ("FIELD",   "STANDARD"),
    ("CUSTOM",  "CUSTOM"),
}

# DB-storable pricing result statuses — TERM_DISCOUNT_UNRESOLVED은 저장 금지
CommercialPricingResultStorageStatus = Literal["READY", "CUSTOM_REQUIRED"]


# ── Site Scope V2 ─────────────────────────────────────────────────────────────

class SaasContractSiteScopeV2(BaseModel):
    """계약 Commercial Version에 포함된 사업장 운영 범위.

    가격 breakdown 컬럼 없음 — Frozen pricing_snapshot에만 보관.
    """

    entity_type: EntityType
    entity_id: UUID
    sector: SaasSector
    base_band_code: Optional[str] = None  # CUSTOM은 None 허용

    @model_validator(mode="after")
    def _entity_sector_match(self) -> "SaasContractSiteScopeV2":
        expected = _SECTOR_ENTITY_MAP.get(self.sector)
        if self.entity_type != expected:
            raise ValueError(
                f"sector={self.sector}에는 entity_type='{expected}'이어야 합니다. "
                f"(받은 값: '{self.entity_type}')"
            )
        return self


# ── Commercial Version V2 ─────────────────────────────────────────────────────

class SaasContractCommercialVersionV2(BaseModel):
    """계약 Commercial 조건의 버전 레코드 (Append-only)."""

    commercial_schema_version: str
    contract_id: UUID
    version_no: StrictInt

    product_tier: ProductTier
    pricing_mode: PricingMode

    worker_capacity: StrictInt
    term_months: StrictInt

    pricing_result_status: CommercialPricingResultStorageStatus
    pricing_policy_version: Optional[str] = None
    pricing_snapshot: Optional[SaasPricingSnapshotV2] = None

    effective_from: datetime
    superseded_at: Optional[datetime] = None

    created_by: Optional[UUID] = None

    @field_validator("commercial_schema_version")
    @classmethod
    def _schema_version_canonical(cls, v: str) -> str:
        if v != COMMERCIAL_STORAGE_SCHEMA_VERSION:
            raise ValueError(
                f"commercial_schema_version은 '{COMMERCIAL_STORAGE_SCHEMA_VERSION}'이어야 합니다."
            )
        return v

    @field_validator("version_no")
    @classmethod
    def _version_no_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("version_no는 1 이상이어야 합니다.")
        return v

    @field_validator("worker_capacity")
    @classmethod
    def _worker_capacity_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("worker_capacity는 0 이상이어야 합니다.")
        return v

    @field_validator("term_months")
    @classmethod
    def _term_months_allowed(cls, v: int) -> int:
        if v not in VALID_TERM_MONTHS:
            raise ValueError(f"term_months는 {sorted(VALID_TERM_MONTHS)} 중 하나여야 합니다.")
        return v

    @model_validator(mode="after")
    def _tier_mode_combination(self) -> "SaasContractCommercialVersionV2":
        if (self.product_tier, self.pricing_mode) not in _VALID_TIER_MODE_PAIRS:
            raise ValueError(
                f"product_tier={self.product_tier}와 pricing_mode={self.pricing_mode} "
                f"조합은 허용되지 않습니다. 허용: MANAGER+STANDARD, FIELD+STANDARD, CUSTOM+CUSTOM"
            )
        return self

    @model_validator(mode="after")
    def _manager_no_workers(self) -> "SaasContractCommercialVersionV2":
        if self.product_tier == "MANAGER" and self.worker_capacity != 0:
            raise ValueError("MANAGER tier는 worker_capacity가 0이어야 합니다.")
        return self

    @model_validator(mode="after")
    def _effective_period_ordering(self) -> "SaasContractCommercialVersionV2":
        if self.superseded_at is not None and self.superseded_at < self.effective_from:
            raise ValueError("superseded_at은 effective_from보다 이전일 수 없습니다.")
        return self

    @model_validator(mode="after")
    def _standard_persistence_rules(self) -> "SaasContractCommercialVersionV2":
        """STANDARD 저장 조건: READY + pricing_policy_version + pricing_snapshot 필수."""
        if self.product_tier in ("MANAGER", "FIELD"):
            if self.pricing_result_status != "READY":
                raise ValueError(
                    f"MANAGER/FIELD는 pricing_result_status=READY이어야 합니다. "
                    f"(받은 값: {self.pricing_result_status})"
                )
            if self.pricing_policy_version is None:
                raise ValueError("MANAGER/FIELD는 pricing_policy_version이 필수입니다.")
            if self.pricing_snapshot is None:
                raise ValueError("MANAGER/FIELD는 pricing_snapshot이 필수입니다.")
        return self

    @model_validator(mode="after")
    def _custom_persistence_rules(self) -> "SaasContractCommercialVersionV2":
        """CUSTOM 저장 조건: CUSTOM_REQUIRED + pricing_policy_version=None + pricing_snapshot=None."""
        if self.product_tier == "CUSTOM":
            if self.pricing_result_status != "CUSTOM_REQUIRED":
                raise ValueError(
                    f"CUSTOM은 pricing_result_status=CUSTOM_REQUIRED이어야 합니다. "
                    f"(받은 값: {self.pricing_result_status})"
                )
            if self.pricing_policy_version is not None:
                raise ValueError("CUSTOM은 pricing_policy_version이 None이어야 합니다.")
            if self.pricing_snapshot is not None:
                raise ValueError("CUSTOM은 pricing_snapshot이 None이어야 합니다.")
        return self

    @model_validator(mode="after")
    def _snapshot_cross_validation(self) -> "SaasContractCommercialVersionV2":
        """Snapshot 내부 메타데이터와 Commercial Version 값 일치 검증."""
        if self.pricing_snapshot is None:
            return self
        snap = self.pricing_snapshot
        mismatches: List[str] = []
        if snap.product_tier != self.product_tier:
            mismatches.append(
                f"product_tier: version={self.product_tier}, snapshot={snap.product_tier}"
            )
        if snap.pricing_mode != self.pricing_mode:
            mismatches.append(
                f"pricing_mode: version={self.pricing_mode}, snapshot={snap.pricing_mode}"
            )
        if snap.term_months != self.term_months:
            mismatches.append(
                f"term_months: version={self.term_months}, snapshot={snap.term_months}"
            )
        if snap.policy_version != self.pricing_policy_version:
            mismatches.append(
                f"policy_version: version={self.pricing_policy_version}, snapshot={snap.policy_version}"
            )
        if mismatches:
            raise ValueError(
                f"Snapshot과 Commercial Version 메타데이터 불일치: {'; '.join(mismatches)}"
            )
        return self


# ── Storage Bundle V2 ─────────────────────────────────────────────────────────

class SaasContractStorageBundleV2(BaseModel):
    """DB 저장 단위: Commercial Version + Site Scope rows."""

    commercial_version: SaasContractCommercialVersionV2
    site_scopes: List[SaasContractSiteScopeV2]

    @model_validator(mode="after")
    def _no_duplicate_sites(self) -> "SaasContractStorageBundleV2":
        seen: Set[Tuple[str, str]] = set()
        for scope in self.site_scopes:
            key = (scope.entity_type, str(scope.entity_id))
            if key in seen:
                raise ValueError(
                    f"중복 사업장: (entity_type={scope.entity_type}, entity_id={scope.entity_id})"
                )
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _standard_scope_snapshot_identity(self) -> "SaasContractStorageBundleV2":
        """STANDARD: site_scopes와 snapshot.sites의 사업장 identity 일치 검증."""
        cv = self.commercial_version
        if cv.product_tier not in ("MANAGER", "FIELD"):
            return self  # CUSTOM은 이 검증 대상 아님

        snap = cv.pricing_snapshot
        if snap is None:
            return self  # Commercial Version validator가 이미 차단

        snap_set: Set[Tuple[str, str]] = {
            (s.entity_type, str(s.entity_id)) for s in snap.sites
        }
        scope_set: Set[Tuple[str, str]] = {
            (s.entity_type, str(s.entity_id)) for s in self.site_scopes
        }

        if snap_set != scope_set:
            missing = snap_set - scope_set
            extra = scope_set - snap_set
            parts: List[str] = []
            if missing:
                parts.append(f"Snapshot에 있고 Scope에 없음: {missing}")
            if extra:
                parts.append(f"Scope에 있고 Snapshot에 없음: {extra}")
            raise ValueError(
                f"STANDARD: site_scopes와 snapshot.sites 사업장 identity 불일치. {'; '.join(parts)}"
            )

        # sector와 base_band_code 일치 검증
        scope_by_key = {
            (s.entity_type, str(s.entity_id)): s for s in self.site_scopes
        }
        for snap_site in snap.sites:
            key = (snap_site.entity_type, str(snap_site.entity_id))
            scope_site = scope_by_key[key]
            if scope_site.sector != snap_site.sector:
                raise ValueError(
                    f"사업장 {key}: sector 불일치 "
                    f"(scope={scope_site.sector}, snapshot={snap_site.sector})"
                )
            if scope_site.base_band_code != snap_site.base_band_code:
                raise ValueError(
                    f"사업장 {key}: base_band_code 불일치 "
                    f"(scope={scope_site.base_band_code}, snapshot={snap_site.base_band_code})"
                )
        return self
