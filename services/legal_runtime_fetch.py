"""
Runtime Engine (runtime_metadata_resolution) → v1 diagnosis rule fetch.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.rule_candidate_projection import (
    filter_runtime_for_sector,
    project_metadata_batch,
    project_metadata_to_v1,
)

USE_RUNTIME_ENGINE = os.environ.get("TAI_USE_RUNTIME_ENGINE", "false").lower() == "true"

_PAGE_SIZE = 1000
_METADATA_SELECT = "*"
_APPLICABLE_STATUSES = frozenset(
    {"APPLICABLE", "CONFIRMED", "MATCHED", "ACTIVE", "RESOLVED"}
)


def _paginate_table(supabase, table: str, select: str, *, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = supabase.table(table).select(select)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        res = q.range(offset, offset + _PAGE_SIZE - 1).execute()
        chunk = res.data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


def fetch_runtime_metadata_rows(supabase) -> List[Dict[str, Any]]:
    return _paginate_table(supabase, "runtime_metadata_resolution", _METADATA_SELECT)


def _factory_rule_candidate_ids(supabase, factory_id: str) -> List[str]:
    """factory별 적용 draft → rule_candidate_id (있으면 metadata 서브셋용)."""
    fa_rows = _paginate_table(
        supabase,
        "facility_applicability",
        "draft_id,applicability_status",
        filters={"factory_id": factory_id},
    )
    draft_ids = [
        str(r["draft_id"])
        for r in fa_rows
        if r.get("draft_id")
        and (r.get("applicability_status") or "").upper() in _APPLICABLE_STATUSES
    ]
    if not draft_ids:
        task_rows = _paginate_table(
            supabase,
            "task_candidate",
            "draft_id",
            filters={"factory_id": factory_id},
        )
        draft_ids = [str(r["draft_id"]) for r in task_rows if r.get("draft_id")]
    if not draft_ids:
        return []

    rc_ids: List[str] = []
    for i in range(0, len(draft_ids), 200):
        chunk = draft_ids[i : i + 200]
        res = (
            supabase.table("executable_draft")
            .select("rule_candidate_id")
            .in_("id", chunk)
            .execute()
        )
        for row in res.data or []:
            rid = row.get("rule_candidate_id")
            if rid:
                rc_ids.append(str(rid))
    return list(dict.fromkeys(rc_ids))


def _metadata_for_factory(supabase, factory_id: str, all_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    factory 연결 rule_candidate가 있으면 해당 article 기반으로 metadata를 좁힘.
    연결이 없으면 전체 metadata (anonymous와 동일).
    """
    rc_ids = _factory_rule_candidate_ids(supabase, factory_id)
    if not rc_ids:
        return all_metadata

    article_ids: List[str] = []
    for i in range(0, len(rc_ids), 200):
        chunk = rc_ids[i : i + 200]
        res = supabase.table("rule_candidate").select("article_id").in_("id", chunk).execute()
        for row in res.data or []:
            aid = row.get("article_id")
            if aid:
                article_ids.append(str(aid))
    article_ids = list(dict.fromkeys(article_ids))
    if not article_ids:
        return all_metadata

    law_article_keys: set[tuple[str, str]] = set()
    for i in range(0, len(article_ids), 100):
        chunk = article_ids[i : i + 100]
        try:
            res = supabase.table("law_article").select("law_name,article_no").in_("id", chunk).execute()
        except Exception:
            continue
        for row in res.data or []:
            law = (row.get("law_name") or "").strip()
            art = str(row.get("article_no") or "").strip()
            if law:
                law_article_keys.add((law, art))

    if not law_article_keys:
        return all_metadata

    narrowed: List[Dict[str, Any]] = []
    for m in all_metadata:
        law = (m.get("source_law_name") or "").strip()
        art_raw = str(m.get("source_article_no") or "").strip()
        art_digits = "".join(ch for ch in art_raw if ch.isdigit())
        matched = False
        for lk, ak in law_article_keys:
            if law != lk:
                continue
            ak_digits = "".join(ch for ch in ak if ch.isdigit())
            if art_digits and ak_digits and art_digits == ak_digits:
                matched = True
                break
            if art_raw and ak and art_raw in ak:
                matched = True
                break
        if matched:
            narrowed.append(m)
    return narrowed if narrowed else all_metadata


def fetch_runtime_rules_as_v1(
    supabase,
    *,
    sector_db: str,
    factory_id: Optional[str] = None,
    diagnosis_stage: Optional[int] = None,
    diagnosis_stage_lte: Optional[int] = None,
) -> List[Dict[str, Any]]:
    metadata_rows = fetch_runtime_metadata_rows(supabase)
    if factory_id:
        metadata_rows = _metadata_for_factory(supabase, factory_id, metadata_rows)

    rules = project_metadata_batch(metadata_rows, sector_hint=sector_db)
    rules = filter_runtime_for_sector(rules, sector_db)

    if diagnosis_stage is not None:
        rules = [r for r in rules if int(r.get("diagnosis_stage") or 1) == diagnosis_stage]
    elif diagnosis_stage_lte is not None:
        rules = [r for r in rules if int(r.get("diagnosis_stage") or 1) <= diagnosis_stage_lte]
    return rules
