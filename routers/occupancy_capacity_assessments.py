"""
H02 occupancy capacity assessment API.

Auth: get_current_user (JWT) + _ensure_factory_own (ownership) — same pattern as P4.
Lifecycle: DRAFT → CONFIRMED → VOID. DRAFT→VOID is forbidden.
Direct numeric occupancy_capacity input is PROHIBITED (WO-LFR-OBJ-H02-P0).
Only structured legal calculation through this router produces canonical H02 values.

Routes:
  POST   /factories/{factory_id}/occupancy-assessments            create draft + calculate
  GET    /factories/{factory_id}/occupancy-assessments            list
  GET    /factories/{factory_id}/occupancy-assessments/{id}       get one
  PATCH  /factories/{factory_id}/occupancy-assessments/{id}       update DRAFT segments
  POST   /factories/{factory_id}/occupancy-assessments/{id}/confirm   confirm
  POST   /factories/{factory_id}/occupancy-assessments/{id}/void      void (CONFIRMED→VOID only)
  GET    /occupancy-assessments/ruleset-version                   current ruleset meta

DELETE is intentionally absent — lifecycle ends at VOID (no hard delete).
"""

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.occupancy_capacity.calculator import (
    calculate_total,
    deserialize_input_segments_from_storage,
    serialize_input_segments_for_storage,
)
from services.occupancy_capacity.canonical_adapter import SourceUnresolved
from services.occupancy_capacity.legal_registry import (
    RULESET_VERSION,
    get_ruleset_sha256,
    get_table_a_rows,
    get_table_b_na_rows,
)
from services.occupancy_capacity.store import (
    attach_calculation,
    confirm_assessment,
    create_draft,
    get_assessment,
    list_assessments_for_factory,
    update_assessment_draft,
    void_assessment,
)

router = APIRouter(tags=["H02 — 수용인원 법정산정"])


class SegmentInput(BaseModel):
    scope: str = Field(..., description="UNDERGROUND or ABOVE_GROUND")
    row_id: str = Field(..., description="e.g. A-1-가-1, B-나-업무")
    # Decimal for exact arithmetic — float is rejected
    area_m2: Optional[Decimal] = None
    # StrictInt: rejects bool (True/False) which Python treats as int
    seat_count: Optional[StrictInt] = None
    room_count: Optional[StrictInt] = None
    dwelling_unit_count: Optional[StrictInt] = None
    bench_length_cm: Optional[Decimal] = None
    wheelchair_space_count: Optional[StrictInt] = None
    fixed_seat_count: Optional[StrictInt] = None
    office_location_height_m: Optional[Decimal] = Field(
        None,
        description="Required for A-4-가 (>60m) and A-4-나 (<=60m) SM-03 guard"
    )


class CreateAssessmentRequest(BaseModel):
    input_segments: list[SegmentInput] = Field(..., min_length=1)


class PatchAssessmentRequest(BaseModel):
    input_segments: list[SegmentInput] = Field(..., min_length=1)


class ConfirmAssessmentRequest(BaseModel):
    coverage_attested: bool = Field(
        ...,
        description="True = all floors/spaces are covered; no segment omitted. Required to confirm."
    )


def _segments_to_dict(input_segments: list[SegmentInput]) -> list[dict[str, Any]]:
    """Convert Pydantic SegmentInput list to dict list for calculator."""
    return [s.model_dump() for s in input_segments]


@router.post("/factories/{factory_id}/occupancy-assessments")
def create_assessment(
    factory_id: str,
    body: CreateAssessmentRequest,
    current: dict = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    segments = _segments_to_dict(body.input_segments)

    try:
        calc = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    storage_segments = serialize_input_segments_for_storage(segments)
    row = create_draft(supabase, factory_id, storage_segments)
    row = attach_calculation(
        supabase,
        row["id"],
        calc["total_num"],
        calc["total_den"],
        {
            "segment_results": calc["segment_results"],
            "meets_5000_threshold": calc["meets_5000_threshold"],
            "total_exact": f"{calc['total_num']}/{calc['total_den']}",
        },
    )
    return row


@router.get("/factories/{factory_id}/occupancy-assessments")
def list_assessments(
    factory_id: str,
    status: Optional[str] = None,
    current: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    if status and status not in ("DRAFT", "CONFIRMED", "VOID"):
        raise HTTPException(status_code=422, detail="status must be DRAFT, CONFIRMED, or VOID")
    return list_assessments_for_factory(supabase, factory_id, status)


@router.get("/factories/{factory_id}/occupancy-assessments/{assessment_id}")
def get_one_assessment(
    factory_id: str,
    assessment_id: str,
    current: dict = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    row = get_assessment(supabase, assessment_id)
    if row is None or row["factory_id"] != factory_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return row


@router.patch("/factories/{factory_id}/occupancy-assessments/{assessment_id}")
def patch_assessment_draft(
    factory_id: str,
    assessment_id: str,
    body: PatchAssessmentRequest,
    current: dict = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    row = get_assessment(supabase, assessment_id)
    if row is None or row["factory_id"] != factory_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if row["status"] != "DRAFT":
        raise HTTPException(
            status_code=422,
            detail=f"Only DRAFT assessments can be patched, got {row['status']!r}"
        )

    segments = _segments_to_dict(body.input_segments)

    try:
        calc = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        storage_segments = serialize_input_segments_for_storage(segments)
        row = update_assessment_draft(supabase, assessment_id, storage_segments)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    row = attach_calculation(
        supabase,
        assessment_id,
        calc["total_num"],
        calc["total_den"],
        {
            "segment_results": calc["segment_results"],
            "meets_5000_threshold": calc["meets_5000_threshold"],
            "total_exact": f"{calc['total_num']}/{calc['total_den']}",
        },
    )
    return row


@router.post("/factories/{factory_id}/occupancy-assessments/{assessment_id}/confirm")
def confirm_one(
    factory_id: str,
    assessment_id: str,
    body: ConfirmAssessmentRequest,
    current: dict = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    row = get_assessment(supabase, assessment_id)
    if row is None or row["factory_id"] != factory_id:
        raise HTTPException(status_code=404, detail="Assessment not found")

    user_id = str(current.get("id") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    try:
        updated = confirm_assessment(
            supabase,
            assessment_id,
            confirmed_by_user_id=user_id,
            coverage_attested=body.coverage_attested,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return updated


@router.post("/factories/{factory_id}/occupancy-assessments/{assessment_id}/void")
def void_one(
    factory_id: str,
    assessment_id: str,
    current: dict = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    row = get_assessment(supabase, assessment_id)
    if row is None or row["factory_id"] != factory_id:
        raise HTTPException(status_code=404, detail="Assessment not found")

    try:
        updated = void_assessment(supabase, assessment_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return updated


@router.get("/occupancy-assessments/ruleset-version")
def ruleset_version_info() -> dict[str, str]:
    return {
        "ruleset_version": RULESET_VERSION,
        "ruleset_sha256": get_ruleset_sha256(),
    }
