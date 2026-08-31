"""
건설안전 라우터 집계 엔트리.
세부 엔드포인트는 기능별 서브 라우터로 분리한다.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from routers.construction_catalog_router import router as construction_catalog_router
from routers.construction_sites_router import router as construction_sites_router
from routers.construction_workflow_router import router as construction_workflow_router
from schemas.construction import InspectionCreate, SiteCreate
from services.construction_helpers import calc_safety_manager
from services.construction_svc import (
    auto_diagnose_and_schedule as _auto_diagnose_and_schedule_svc,
    create_factory_for_site as _create_factory_for_site_svc,
    run_diagnosis as _run_diagnosis_svc,
    run_generate_schedules as _run_generate_schedules_svc,
)
from services.time import now_kst, serialize_external_utc

router = APIRouter(tags=["건설안전"])
router.include_router(construction_sites_router)
router.include_router(construction_catalog_router)
router.include_router(construction_workflow_router)


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def _create_factory_for_site(supabase, site: dict) -> Optional[str]:
    return _create_factory_for_site_svc(supabase, site, _now_iso)


def _run_diagnosis(supabase, factory_id: str, site: dict) -> dict:
    return _run_diagnosis_svc(supabase, factory_id, site)


def _run_generate_schedules(supabase, factory_id: str, inspection_rules: list, company_id: Optional[str]) -> dict:
    return _run_generate_schedules_svc(supabase, factory_id, inspection_rules, company_id)


def _auto_diagnose_and_schedule(supabase, factory_id: str, site: dict) -> dict:
    return _auto_diagnose_and_schedule_svc(supabase, factory_id, site)
