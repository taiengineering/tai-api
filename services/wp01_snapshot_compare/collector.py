"""WP01-A Current Collector — 현재 입력 사실 수집.

각 섹터의 collect_*_leg_input() 을 호출하고 build_facility() 로 facility dict 생성.
DB WRITE 0 (BUILDING H01 write 차단), LEG EXECUTION 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple

from clients.leg_runtime_client import build_facility
from services.wp01_snapshot_compare.errors import CollectionError


def collect_current_facility_industrial(
    supabase: Any,
    factory_id: str,
    consumer_input: Any,
    app3_projection: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], list]:
    """INDUSTRIAL 현재 facility 수집.

    반환 (current_facility, unresolved_fields).
    CollectionError 는 호출부에서 UNRESOLVED 로 매핑한다.
    """
    from services.safe_industrial_leg_runtime import collect_industrial_leg_input
    from services.work_source.store import WorkSourceLoadError
    from services.work_source.merge import WorkSourceMergeConflict
    from services.equipment_source.store import EquipmentSourceLoadError

    try:
        step1, unresolved = collect_industrial_leg_input(
            supabase, factory_id, consumer_input, app3_projection
        )
    except (WorkSourceLoadError, WorkSourceMergeConflict, EquipmentSourceLoadError) as exc:
        raise CollectionError(str(exc), sector="INDUSTRIAL") from exc
    except Exception as exc:
        raise CollectionError(f"INDUSTRIAL 수집 실패: {exc}", sector="INDUSTRIAL") from exc

    return build_facility(step1), unresolved


def collect_current_facility_building(
    supabase: Any,
    factory_id: str,
    consumer_input: Any,
    material_inout_event_id: Optional[str] = None,
    occupancy_assessment_id: Optional[str] = None,
    app3_projection: Optional[Any] = None,
) -> Tuple[Dict[str, Any], list, Set[str]]:
    """BUILDING 현재 facility 수집. allow_h01_db_write=False 강제.

    반환 (current_facility, unresolved_fields, h01_absent_fields).
    h01_absent_fields 가 비어있지 않으면 UNRESOLVED 처리 여부를 호출부가 결정한다.
    """
    from services.safe_building_leg_runtime import collect_building_leg_input
    from services.work_source.store import WorkSourceLoadError
    from services.work_source.merge import WorkSourceMergeConflict
    from services.equipment_source.store import EquipmentSourceLoadError

    try:
        step1, unresolved, h01_absent_fields = collect_building_leg_input(
            supabase,
            factory_id,
            consumer_input,
            material_inout_event_id=material_inout_event_id,
            occupancy_assessment_id=occupancy_assessment_id,
            app3_projection=app3_projection,
            allow_h01_db_write=False,
        )
    except (WorkSourceLoadError, WorkSourceMergeConflict, EquipmentSourceLoadError) as exc:
        raise CollectionError(str(exc), sector="BUILDING") from exc
    except Exception as exc:
        raise CollectionError(f"BUILDING 수집 실패: {exc}", sector="BUILDING") from exc

    return build_facility(step1), unresolved, h01_absent_fields


def collect_current_facility_construction(
    supabase: Any,
    site_id: str,
    consumer_input: Any,
    subcontract_legal_event_id: Optional[str] = None,
    subcontractor_id: Optional[str] = None,
    app3_projection: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], list, str]:
    """CONSTRUCTION 현재 facility 수집.

    반환 (current_facility, unresolved_fields, factory_id).
    ConstructionSiteBridgeError 는 CollectionError 로 래핑하여 전파한다.
    """
    from services.safe_construction_leg_runtime import (
        collect_construction_leg_input,
        ConstructionSiteBridgeError,
    )
    from services.work_source.store import WorkSourceLoadError
    from services.work_source.merge import WorkSourceMergeConflict
    from services.equipment_source.store import EquipmentSourceLoadError

    try:
        step1, unresolved, factory_id = collect_construction_leg_input(
            supabase,
            site_id,
            consumer_input,
            subcontract_legal_event_id=subcontract_legal_event_id,
            subcontractor_id=subcontractor_id,
            app3_projection=app3_projection,
        )
    except ConstructionSiteBridgeError as exc:
        raise CollectionError(str(exc), sector="CONSTRUCTION") from exc
    except (WorkSourceLoadError, WorkSourceMergeConflict, EquipmentSourceLoadError) as exc:
        raise CollectionError(str(exc), sector="CONSTRUCTION") from exc
    except Exception as exc:
        raise CollectionError(f"CONSTRUCTION 수집 실패: {exc}", sector="CONSTRUCTION") from exc

    return build_facility(step1), unresolved, factory_id
