"""
H02 occupancy capacity assessment CRUD — service_role only.
Lifecycle: DRAFT → CONFIRMED → VOID (no hard DELETE).
Lifecycle contract: DRAFT→CONFIRMED only; CONFIRMED→VOID only; DRAFT→VOID forbidden.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from services.occupancy_capacity.legal_registry import RULESET_VERSION, get_ruleset_sha256
from services.time import now_kst, serialize_external_utc


def create_draft(
    supabase,
    factory_id: str,
    input_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    sha = get_ruleset_sha256()
    row = {
        "id": str(uuid4()),
        "factory_id": factory_id,
        "status": "DRAFT",
        "ruleset_version": RULESET_VERSION,
        "ruleset_sha256": sha,
        "input_segments": json.dumps(input_segments),
        "coverage_attested": False,
    }
    resp = supabase.table("factory_occupancy_capacity_assessments").insert(row).execute()
    if not resp.data:
        raise RuntimeError("create_draft: insert returned no data")
    return resp.data[0]


def update_assessment_draft(
    supabase,
    assessment_id: str,
    input_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace input_segments on a DRAFT assessment and clear any attached calculation."""
    sha = get_ruleset_sha256()
    resp = (
        supabase.table("factory_occupancy_capacity_assessments")
        .update({
            "input_segments": json.dumps(input_segments),
            "ruleset_version": RULESET_VERSION,
            "ruleset_sha256": sha,
            # clear any previously attached calculation — segments changed
            "result_numerator": None,
            "result_denominator": None,
            "calculation_trace": None,
            "updated_at": serialize_external_utc(now_kst()),
        })
        .eq("id", assessment_id)
        .eq("status", "DRAFT")
        .execute()
    )
    if not resp.data:
        raise RuntimeError("update_assessment_draft: no matching DRAFT row or update failed")
    return resp.data[0]


def attach_calculation(
    supabase,
    assessment_id: str,
    result_num: int,
    result_den: int,
    calculation_trace: dict[str, Any],
) -> dict[str, Any]:
    resp = (
        supabase.table("factory_occupancy_capacity_assessments")
        .update({
            "result_numerator": str(result_num),
            "result_denominator": str(result_den),
            "calculation_trace": json.dumps(calculation_trace),
            "updated_at": serialize_external_utc(now_kst()),
        })
        .eq("id", assessment_id)
        .eq("status", "DRAFT")
        .execute()
    )
    if not resp.data:
        raise RuntimeError("attach_calculation: no matching DRAFT row or update failed")
    return resp.data[0]


def confirm_assessment(
    supabase,
    assessment_id: str,
    confirmed_by_user_id: str,
    coverage_attested: bool,
) -> dict[str, Any]:
    if not coverage_attested:
        raise ValueError("coverage_attested must be True to confirm assessment")

    current_sha = get_ruleset_sha256()
    row = _get_exact(supabase, assessment_id)
    if row["status"] != "DRAFT":
        raise ValueError(f"Only DRAFT assessments can be confirmed, got {row['status']!r}")
    if row["ruleset_version"] != RULESET_VERSION:
        raise ValueError(
            f"Ruleset version mismatch: assessment has {row['ruleset_version']!r}, "
            f"current code is {RULESET_VERSION!r}. Re-calculate with current ruleset."
        )
    if row["ruleset_sha256"] != current_sha:
        raise ValueError(
            f"Ruleset SHA mismatch: assessment has {row['ruleset_sha256']!r}, "
            f"current code has {current_sha!r}. Re-calculate with current ruleset."
        )
    if row["result_numerator"] is None:
        raise ValueError("Cannot confirm: calculation not yet attached")

    now = serialize_external_utc(now_kst())
    resp = (
        supabase.table("factory_occupancy_capacity_assessments")
        .update({
            "status": "CONFIRMED",
            "coverage_attested": True,
            "confirmed_by_user_id": confirmed_by_user_id,
            "confirmed_at": now,
            "updated_at": now,
        })
        .eq("id", assessment_id)
        .eq("status", "DRAFT")
        .execute()
    )
    if not resp.data:
        raise RuntimeError("confirm_assessment: update returned no data")
    return resp.data[0]


def void_assessment(
    supabase,
    assessment_id: str,
) -> dict[str, Any]:
    row = _get_exact(supabase, assessment_id)
    # DRAFT→VOID is forbidden; only CONFIRMED→VOID allowed
    if row["status"] != "CONFIRMED":
        raise ValueError(
            f"Only CONFIRMED assessments can be voided, got {row['status']!r}. "
            "Lifecycle contract: DRAFT→CONFIRMED→VOID only."
        )

    now = serialize_external_utc(now_kst())
    resp = (
        supabase.table("factory_occupancy_capacity_assessments")
        .update({
            "status": "VOID",
            "voided_at": now,
            "updated_at": now,
        })
        .eq("id", assessment_id)
        .eq("status", "CONFIRMED")
        .execute()
    )
    if not resp.data:
        raise RuntimeError("void_assessment: update returned no data")
    return resp.data[0]


def get_assessment(supabase, assessment_id: str) -> dict[str, Any] | None:
    resp = (
        supabase.table("factory_occupancy_capacity_assessments")
        .select("*")
        .eq("id", assessment_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def list_assessments_for_factory(
    supabase, factory_id: str, status: str | None = None
) -> list[dict[str, Any]]:
    q = (
        supabase.table("factory_occupancy_capacity_assessments")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
    )
    if status:
        q = q.eq("status", status)
    resp = q.execute()
    return resp.data or []


def _get_exact(supabase, assessment_id: str) -> dict[str, Any]:
    row = get_assessment(supabase, assessment_id)
    if row is None:
        raise ValueError(f"Assessment not found: {assessment_id!r}")
    return row
