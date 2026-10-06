"""Source registry — canonical list of all 12 persisted public-data sources."""
from __future__ import annotations

from services.public_data_sync.contracts import (
    SourceKind,
    SourceMode,
    SourceSpec,
)
from services.public_data_sync.errors import SourceNotFoundError

_SOURCES: list[SourceSpec] = [
    # S01 — KOSHA 산업재해 사례
    SourceSpec(
        source_id="KOSHA_ACCIDENT_CASES",
        display_name="KOSHA 산업재해 사례",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        consumer_tags=("leg", "csi"),
        auto_refresh_candidate=True,
    ),
    # S02 — KOSHA MSDS 화학물질
    SourceSpec(
        source_id="KOSHA_MSDS",
        display_name="KOSHA MSDS 화학물질",
        sync_mode=SourceMode.ENUMERATE_HYDRATE,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        consumer_tags=("chem",),
        auto_refresh_candidate=True,
        notes="FULL_BOOTSTRAP=329088 calls; incremental delta via plan_incremental()",
    ),
    # S03 — KOSHA 안전보건자료 (safety materials)
    SourceSpec(
        source_id="KOSHA_SAFETY_MATERIALS",
        display_name="KOSHA 안전보건자료",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        consumer_tags=("safety",),
        auto_refresh_candidate=True,
    ),
    # S04 — KECO 화학물질 참조
    SourceSpec(
        source_id="KECO_CHEMICAL",
        display_name="KECO 화학물질 참조",
        sync_mode=SourceMode.TARGET_REFRESH,
        source_kind=SourceKind.REST,
        credential_pool="KECO_DEDICATED",
        rate_limit_group="KECO",
        consumer_tags=("chem",),
        auto_refresh_candidate=True,
        notes="Targets leg-prod/msds_ref schema; exclusive DB run lock",
    ),
    # S05 — 재해사례 CSI
    SourceSpec(
        source_id="CSI_ACCIDENT_CASES",
        display_name="재해사례 CSI",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_CSI",
        consumer_tags=("csi",),
        auto_refresh_candidate=True,
    ),
    # S06 — KCSC 불법정보 신고
    SourceSpec(
        source_id="KCSC_SYNC",
        display_name="KCSC 불법정보 신고",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.REST,
        credential_pool="KCSC_DEDICATED",
        rate_limit_group="KCSC",
        consumer_tags=("compliance",),
        auto_refresh_candidate=True,
    ),
    # S07 — KOSHA 건설안전정보 경량
    SourceSpec(
        source_id="KOSHA_CONSTRUCTION_SAFETY_LIGHT",
        display_name="KOSHA 건설안전정보 경량",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        consumer_tags=("construction",),
        auto_refresh_candidate=False,
        notes="Endpoint mismatch in DIRECT handler; production rows=0 UNVERIFIED cause",
    ),
    # S08 — KOSHA 위험성평가
    SourceSpec(
        source_id="KOSHA_RISK_ASSESSMENT",
        display_name="KOSHA 위험성평가",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        consumer_tags=("safety",),
        auto_refresh_candidate=False,
    ),
    # S09 — 공휴일 정보
    SourceSpec(
        source_id="HOLIDAY_SYNC",
        display_name="공휴일 정보",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_HOLIDAY",
        consumer_tags=("calendar",),
        auto_refresh_candidate=True,
    ),
    # S10 — 법령 원문 (법제처)
    SourceSpec(
        source_id="LEGAL_TEXT_SYNC",
        display_name="법령 원문 (법제처)",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.REST,
        credential_pool="LAW_GO_KR",
        rate_limit_group="LAW_GO_KR",
        consumer_tags=("leg",),
        auto_refresh_candidate=True,
    ),
    # S11 — 판례 (PRECEDENT)
    SourceSpec(
        source_id="PRECEDENT_COLLECT",
        display_name="판례 수집",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.EDGE,
        credential_pool="SUPABASE_EDGE",
        rate_limit_group="SUPABASE_EDGE",
        consumer_tags=("leg",),
        auto_refresh_candidate=True,
        notes="HTTP 503 precedent; fail-closed required",
    ),
    # S12 — 표준산업분류 (KSIC)
    SourceSpec(
        source_id="KSIC_SYNC",
        display_name="표준산업분류 (KSIC)",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.REST,
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KSIC",
        consumer_tags=("classification",),
        auto_refresh_candidate=True,
    ),
]

_REGISTRY: dict[str, SourceSpec] = {s.source_id: s for s in _SOURCES}


class SourceRegistry:
    def get(self, source_id: str) -> SourceSpec:
        spec = _REGISTRY.get(source_id)
        if spec is None:
            raise SourceNotFoundError(source_id)
        return spec

    def list_all(self) -> list[SourceSpec]:
        return list(_SOURCES)

    def list_auto_refresh_candidates(self) -> list[SourceSpec]:
        return [s for s in _SOURCES if s.auto_refresh_candidate]


registry = SourceRegistry()
