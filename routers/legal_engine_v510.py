"""Legal engine router v510."""
from fastapi import APIRouter, HTTPException
from typing import Optional, Any, Dict, List
from datetime import date, timedelta
from db.supabase_client import get_supabase
from schemas.legal_engine import DiagnoseStep1Body
from schemas.legal_engine_v510 import DiagnoseStep2Body
from services import legal_v510_svc
from services.legal_v510_helpers import (
    CONDITION_CODE_TO_CONTEXT_KEY_V510,
    CONSTRUCTION_RELEVANT_LAW_PREFIXES,
    _db_rule_matches_facility_v510,
    _evaluate_facility_conditions_db_v510,
    _get_construction_summary,
    _input_to_facility_context_v510,
)
from services.legal_rules import (
    _evaluate_condition,
    normalize_sector_db as _normalize_sector_db,
)

router = APIRouter(prefix="/legal-engine", tags=["법령엔진v510"])

ENGINE_VERSION = "5.1.0"
ALLOWED_DIAGNOSE_SECTORS = frozenset({"BUILDING", "MANUFACTURING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"})

@router.post("/diagnose/step1")
async def diagnose_step1_v510(body: DiagnoseStep1Body):
    supabase = get_supabase()
    try:
        return legal_v510_svc.run_diagnose_step1_v510(
            supabase=supabase,
            body=body,
            allowed_sectors=ALLOWED_DIAGNOSE_SECTORS,
            engine_version=ENGINE_VERSION,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/diagnose/step2")
def diagnose_step2_v510(body: DiagnoseStep2Body):
    supabase = get_supabase()
    try:
        return legal_v510_svc.run_diagnose_step2_v510(
            supabase=supabase,
            body=body,
            engine_version=ENGINE_VERSION,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
