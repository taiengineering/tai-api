"""Source registry — canonical list of all 12 persisted public-data sources."""
from __future__ import annotations

from services.public_data_sync.contracts import SourceKind, SourceMode, SourceSpec
from services.public_data_sync.errors import SourceNotFoundError

_SOURCES: list[SourceSpec] = [
    # 1. KOSHA_SAFETY_MATERIAL
    SourceSpec(
        source_id="KOSHA_SAFETY_MATERIAL",
        display_name="KOSHA 안전보건자료",
        provider="KOSHA",
        dataset_id="safety_material",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="kosha_safety_material",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="DAILY",
        consumer_tags=("safety",),
        auto_refresh_candidate=True,
    ),
    # 2. KOSHA_GUIDE
    SourceSpec(
        source_id="KOSHA_GUIDE",
        display_name="KOSHA 안전보건지침",
        provider="KOSHA",
        dataset_id="guide",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="kosha_guide",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="DAILY",
        consumer_tags=("safety",),
        auto_refresh_candidate=True,
    ),
    # 3. KOSHA_MSDS
    SourceSpec(
        source_id="KOSHA_MSDS",
        display_name="KOSHA MSDS 화학물질",
        provider="KOSHA",
        dataset_id="msds",
        sync_mode=SourceMode.ENUMERATE_HYDRATE,
        source_kind=SourceKind.API,
        adapter_key="kosha_msds",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="MONTHLY",
        consumer_tags=("chem",),
        auto_refresh_candidate=True,
        notes="FULL_BOOTSTRAP=329088 calls; incremental delta via plan_incremental()",
    ),
    # 4. KECO_15149420
    SourceSpec(
        source_id="KECO_15149420",
        display_name="KECO 화학물질 참조",
        provider="KECO",
        dataset_id="15149420",
        sync_mode=SourceMode.TARGET_REFRESH,
        source_kind=SourceKind.API,
        adapter_key="keco_chemical",
        credential_pool="DATA_GO_KR",
        rate_limit_group="KECO",
        refresh_policy="DAILY",
        max_run_seconds=7200,
        consumer_tags=("chem",),
        auto_refresh_candidate=True,
        notes="Central cadence=DAILY; target-level refresh bounded by KECO_REQUEST_BUDGET/BATCH; exclusive KECO domain lock preserved",
    ),
    # 5. KOSHA_ACCIDENT_CASES
    SourceSpec(
        source_id="KOSHA_ACCIDENT_CASES",
        display_name="KOSHA 산업재해 사례",
        provider="KOSHA",
        dataset_id="accident_cases",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.API,
        adapter_key="kosha_accident_cases",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="DAILY",
        consumer_tags=("safety", "csi"),
        auto_refresh_candidate=True,
    ),
    # 6. KOSHA_CONSTRUCTION_ACCIDENTS
    SourceSpec(
        source_id="KOSHA_CONSTRUCTION_ACCIDENTS",
        display_name="KOSHA 건설 산업재해",
        provider="KOSHA",
        dataset_id="construction_accidents",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.API,
        adapter_key="kosha_construction_accidents",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="DAILY",
        consumer_tags=("construction", "safety"),
        auto_refresh_candidate=True,
    ),
    # 7. KOSHA_CONSTRUCTION_SAFETY_LIGHT
    SourceSpec(
        source_id="KOSHA_CONSTRUCTION_SAFETY_LIGHT",
        display_name="KOSHA 건설안전정보 경량",
        provider="KOSHA",
        dataset_id="construction_safety_light",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="kosha_construction_safety_light",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="ON_DEMAND",
        consumer_tags=("construction",),
        auto_refresh_candidate=False,
        notes="source validity 미확정; endpoint mismatch in DIRECT handler",
    ),
    # 8. KOSHA_RISK_ASSESSMENT
    SourceSpec(
        source_id="KOSHA_RISK_ASSESSMENT",
        display_name="KOSHA 위험성평가",
        provider="KOSHA",
        dataset_id="risk_assessment",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.API,
        adapter_key="kosha_risk_assessment",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_KOSHA",
        refresh_policy="ON_DEMAND",
        consumer_tags=("safety",),
        auto_refresh_candidate=False,
        notes="source validity 미확정",
    ),
    # 9. CSI_ACCIDENT
    SourceSpec(
        source_id="CSI_ACCIDENT",
        display_name="CSI 재해사례",
        provider="CSI",
        dataset_id="accident",
        sync_mode=SourceMode.FILE_SNAPSHOT,
        source_kind=SourceKind.FILE,
        adapter_key="csi_accident",
        credential_pool="CSI_DEDICATED",
        rate_limit_group="CSI",
        refresh_policy="DAILY",
        consumer_tags=("csi", "safety"),
        auto_refresh_candidate=True,
        notes="DAILY = portal metadata discovery only; full CSV download only when NEW_ARTIFACT",
    ),
    # 10. KCSC
    SourceSpec(
        source_id="KCSC",
        display_name="KCSC KCS 공종·작업",
        provider="KCSC",
        dataset_id="kcs_work",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="kcsc",
        credential_pool="KCSC_DEDICATED",
        rate_limit_group="KCSC",
        refresh_policy="MONTHLY",
        consumer_tags=("construction",),
        auto_refresh_candidate=True,
    ),
    # 11. INDUSTRIAL_ACCIDENT_PRECEDENT
    SourceSpec(
        source_id="INDUSTRIAL_ACCIDENT_PRECEDENT",
        display_name="산업재해 판례",
        provider="SUPABASE_EDGE",
        dataset_id="industrial_accident_precedent",
        sync_mode=SourceMode.INCREMENTAL,
        source_kind=SourceKind.EDGE,
        adapter_key="industrial_accident_precedent",
        credential_pool="SUPABASE_EDGE",
        rate_limit_group="SUPABASE_EDGE",
        refresh_policy="WEEKLY",
        consumer_tags=("safety",),
        auto_refresh_candidate=True,
        notes="HTTP 503 precedent; fail-closed required",
    ),
    # 12. HOLIDAY
    SourceSpec(
        source_id="HOLIDAY",
        display_name="공휴일 정보",
        provider="DATA_GO_KR",
        dataset_id="holiday",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="holiday",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_HOLIDAY",
        refresh_policy="DAILY",
        consumer_tags=("calendar",),
        auto_refresh_candidate=True,
    ),
    # 13. EXT132_HAZARDOUS_MATERIAL (소방청 위험물안전관리)
    SourceSpec(
        source_id="EXT132_HAZARDOUS_MATERIAL",
        display_name="소방청 위험물안전관리",
        provider="NFA",
        dataset_id="ext132_hazardous_material",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="ext132_hazardous_material",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_NFA",
        refresh_policy="DAILY",
        consumer_tags=("safety", "hazmat"),
        auto_refresh_candidate=False,
        notes="WO-001B-R1 신규; 페이지 크기/최대값 UNVERIFIED; auto_refresh=False until sample call verified",
    ),
    # 14. EXT165_CHEMICAL_ACCIDENT (화학물질안전원 화학사고)
    SourceSpec(
        source_id="EXT165_CHEMICAL_ACCIDENT",
        display_name="화학물질안전원 화학사고",
        provider="NICS",
        dataset_id="ext165_chemical_accident",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="ext165_chemical_accident",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_NICS",
        refresh_policy="DAILY",
        consumer_tags=("safety", "chem"),
        auto_refresh_candidate=False,
        notes="WO-001B-R1 신규; yyyy 연도필터 지원; 페이지 크기/최대값 UNVERIFIED; auto_refresh=False until verified",
    ),
    # 15. EXT037_CHEMICAL_SAFETY (화학안전원 화학물질안전정보)
    SourceSpec(
        source_id="EXT037_CHEMICAL_SAFETY",
        display_name="화학안전원 화학물질안전정보",
        provider="NICS",
        dataset_id="ext037_chemical_safety",
        sync_mode=SourceMode.FULL_SNAPSHOT,
        source_kind=SourceKind.API,
        adapter_key="ext037_chemical_safety",
        credential_pool="DATA_GO_KR",
        rate_limit_group="DATA_GO_KR_NICS",
        refresh_policy="DAILY",
        consumer_tags=("safety", "chem"),
        auto_refresh_candidate=False,
        notes="TAI-WO-P0-05-EXT037 신규; G1 probe 확인(XML/dataNo/resultCode=00/7189건); auto_refresh=False until bootstrap verified",
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
