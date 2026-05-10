"""law 단위 stage_1_clauses 로드 — Track A P3 (Supabase만 사용, DB 스키마 정합)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)

LawKey = int | str


def _chunks(xs: list[Any], n: int) -> list[list[Any]]:
    return [xs[i : i + n] for i in range(0, len(xs), n)]


def fetch_clauses_by_law_id(supabase: SupabaseClient | None, law_id: LawKey) -> list[dict[str, Any]]:
    """해당 법령(law.id)에 속한 모든 stage_1_clauses 행(dict)."""
    if supabase is None:
        logger.warning("fetch_clauses_by_law_id: supabase 없음")
        return []

    arts = (
        supabase.table("law_article")
        .select("id")
        .eq("law_id", law_id)
        .execute()
        .data
        or []
    )
    aids = [a["id"] for a in arts]
    if not aids:
        return []

    parts: list[dict[str, Any]] = []
    for ch in _chunks(aids, 150):
        res = (
            supabase.table("law_article_part")
            .select("id")
            .in_("article_id", ch)
            .execute()
            .data
            or []
        )
        parts.extend(res)
    pids = [p["id"] for p in parts]
    if not pids:
        return []

    clauses: list[dict[str, Any]] = []
    for ch in _chunks(pids, 150):
        res = (
            supabase.table("stage_1_clauses")
            .select("id, source_text, tokenization_json, part_id")
            .in_("part_id", ch)
            .execute()
            .data
            or []
        )
        clauses.extend(res)
    return clauses


def fetch_clauses_by_law_batch(
    supabase: SupabaseClient | None,
    law_batch: list[LawKey],
) -> list[dict[str, Any]]:
    """여러 법령에 속한 stage_1_clauses 합집합."""
    acc: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for lid in law_batch:
        for row in fetch_clauses_by_law_id(supabase, lid):
            rid = row.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            acc.append(row)
    return acc


def fetch_isolated_clauses_by_law_id(
    supabase: SupabaseClient | None,
    law_id: LawKey,
) -> list[dict[str, Any]]:
    """해당 법령에서 stage_2_elements.is_isolated=true 인 clause만 (Phase 2.2 v3)."""
    all_clauses = fetch_clauses_by_law_id(supabase, law_id)
    if not all_clauses or supabase is None:
        return []

    cids = [c["id"] for c in all_clauses if c.get("id")]
    if not cids:
        return []

    isolated: set[Any] = set()
    for ch in _chunks(cids, 150):
        res = (
            supabase.table("stage_2_elements")
            .select("clause_id, is_isolated")
            .in_("clause_id", ch)
            .eq("is_isolated", True)
            .execute()
            .data
            or []
        )
        for row in res:
            isolated.add(row.get("clause_id"))

    return [c for c in all_clauses if c.get("id") in isolated]
