"""Compiler Engine Gateway — the ONLY module that touches the isolated Compiler
Core tables (engine_isolated schema: draft_slot, executable_draft,
facility_applicability).

TAI–Compiler boundary: platform services (anonymous_factory_service,
compiler_core_svc, …) call these functions and never reference the
engine_isolated schema or its tables directly. This preserves the intentional
isolation of the Compiler Core's polluted middle from the platform and LEG.

Rules:
  - Only this module names engine_isolated / its tables.
  - Query semantics here are byte-identical to the pre-isolation platform queries
    (same columns / filters / pagination) so runtime results are unchanged.
  - public tables (factories, law_article, law_master, law_sector_mapping,
    task_candidate, …) are NOT accessed here; callers keep using them directly.
  - LEG path must never call this module (LEG uses /rtm/evaluate only).
"""
from __future__ import annotations

from typing import Any, Dict, List

_ENGINE_SCHEMA = "engine_isolated"


def _eng(sb):
    """Return a PostgREST handle bound to the isolated Compiler schema."""
    return sb.schema(_ENGINE_SCHEMA)


# ── executable_draft ─────────────────────────────────────────────────────────
def fetch_executable_draft_articles(sb, offset: int, page: int) -> List[Dict[str, Any]]:
    res = (
        _eng(sb).table("executable_draft")
        .select("id, article_id")
        .not_.is_("article_id", "null")
        .range(offset, offset + page - 1)
        .execute()
    )
    return res.data or []


def fetch_executable_draft_meta(sb, ids_chunk: List[str]) -> List[Dict[str, Any]]:
    res = (
        _eng(sb).table("executable_draft")
        .select("id, article_id, rule_candidate_id, part_id")
        .in_("id", ids_chunk)
        .execute()
    )
    return res.data or []


# ── draft_slot ───────────────────────────────────────────────────────────────
def fetch_draft_slots_numeric_scope(sb, offset: int, page: int) -> List[Dict[str, Any]]:
    res = (
        _eng(sb).table("draft_slot")
        .select("draft_id, part_id, section, binding_field, operator, value, unit, family_name")
        .not_.is_("binding_field", "null")
        .in_("section", ["IF_NUMERIC", "IF_SCOPE"])
        .range(offset, offset + page - 1)
        .execute()
    )
    return res.data or []


def fetch_draft_slots_then_action(sb, draft_ids_chunk: List[str]) -> List[Dict[str, Any]]:
    res = (
        _eng(sb).table("draft_slot")
        .select("draft_id, section, family_name, raw_token")
        .in_("draft_id", draft_ids_chunk)
        .eq("section", "THEN_ACTION")
        .execute()
    )
    return res.data or []


# ── facility_applicability ────────────────────────────────────────────────────
def insert_facility_applicability(sb, batch: List[Dict[str, Any]]) -> None:
    _eng(sb).table("facility_applicability").insert(batch).execute()


def delete_facility_applicability_by_factory(sb, factory_id: str) -> None:
    _eng(sb).table("facility_applicability").delete().eq("factory_id", factory_id).execute()


def fetch_facility_applicability_by_factory(
    sb, factory_id: str, statuses: List[str]
) -> List[Dict[str, Any]]:
    res = (
        _eng(sb).table("facility_applicability")
        .select("id, draft_id, applicability_status, part_id, match_details")
        .eq("factory_id", factory_id)
        .in_("applicability_status", statuses)
        .execute()
    )
    return res.data or []
