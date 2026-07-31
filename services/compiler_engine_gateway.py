"""Compiler Engine Gateway — the ONLY module that touches the isolated Compiler
Core tables (engine_isolated schema: draft_slot, executable_draft,
facility_applicability).

TAI–Compiler boundary: platform services (anonymous_factory_service,
compiler_core_svc, …) call these functions and never reference the
engine_isolated schema or its tables directly.

Schema binding is version-robust: it uses a dedicated Supabase client bound to
the engine_isolated schema via ClientOptions (works across supabase-py v1/v2),
falling back to Client.schema() only if ClientOptions is unavailable. This avoids
depending on Client.schema() existing on the caller's default client.
"""
from __future__ import annotations

from typing import Any, Dict, List

from supabase import create_client
from db.supabase_client import SUPABASE_URL, SUPABASE_KEY

_ENGINE_SCHEMA = "engine_isolated"
_engine_client = None


def _make_engine_client():
    # 1) Preferred: dedicated client whose default schema is engine_isolated.
    try:
        try:
            from supabase.lib.client_options import ClientOptions
        except Exception:  # pragma: no cover - alt import path
            from supabase import ClientOptions  # type: ignore
        return create_client(
            SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema=_ENGINE_SCHEMA)
        )
    except Exception:
        pass
    # 2) Fallback: default client scoped via .schema() (newer supabase-py).
    base = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        return base.schema(_ENGINE_SCHEMA)
    except Exception:
        # 3) Last resort: postgrest-level schema scope.
        return base.postgrest.schema(_ENGINE_SCHEMA)


def _eng():
    global _engine_client
    if _engine_client is None:
        _engine_client = _make_engine_client()
    return _engine_client


# ── executable_draft ─────────────────────────────────────────────────────────
def fetch_executable_draft_articles(sb, offset: int, page: int) -> List[Dict[str, Any]]:
    res = (
        _eng().table("executable_draft")
        .select("id, article_id")
        .not_.is_("article_id", "null")
        .order("id")
        .range(offset, offset + page - 1)
        .execute()
    )
    return res.data or []


def fetch_executable_draft_meta(sb, ids_chunk: List[str]) -> List[Dict[str, Any]]:
    res = (
        _eng().table("executable_draft")
        .select("id, article_id, rule_candidate_id, part_id")
        .in_("id", ids_chunk)
        .execute()
    )
    return res.data or []


# ── draft_slot ───────────────────────────────────────────────────────────────
def fetch_draft_slots_numeric_scope(sb, offset: int, page: int) -> List[Dict[str, Any]]:
    res = (
        _eng().table("draft_slot")
        .select("draft_id, part_id, section, binding_field, operator, value, unit, family_name")
        .not_.is_("binding_field", "null")
        .in_("section", ["IF_NUMERIC", "IF_SCOPE"])
        .order("draft_id")
        .order("part_id")
        .range(offset, offset + page - 1)
        .execute()
    )
    return res.data or []


def fetch_draft_slots_then_action(sb, draft_ids_chunk: List[str]) -> List[Dict[str, Any]]:
    res = (
        _eng().table("draft_slot")
        .select("draft_id, section, family_name, raw_token")
        .in_("draft_id", draft_ids_chunk)
        .eq("section", "THEN_ACTION")
        .execute()
    )
    return res.data or []


# ── facility_applicability ────────────────────────────────────────────────────
def insert_facility_applicability(sb, batch: List[Dict[str, Any]]) -> None:
    _eng().table("facility_applicability").insert(batch).execute()


def delete_facility_applicability_by_factory(sb, factory_id: str) -> None:
    _eng().table("facility_applicability").delete().eq("factory_id", factory_id).execute()


def fetch_facility_applicability_by_factory(
    sb, factory_id: str, statuses: List[str]
) -> List[Dict[str, Any]]:
    res = (
        _eng().table("facility_applicability")
        .select("id, draft_id, applicability_status, part_id, match_details")
        .eq("factory_id", factory_id)
        .in_("applicability_status", statuses)
        .execute()
    )
    return res.data or []
