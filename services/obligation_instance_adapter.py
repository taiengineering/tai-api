"""Applicability Engine(obligation_instance) → 45CM Adapter Glue (CURSOR-TASK-001).

원칙:
  - 변환만. 판단/필터/법령생성/Trigger 생성 없음.
  - FastAPI import 없음 (순수 서비스).
  - obligation_adapter_service 무수정 호출.
  - status='ACTIVE'는 Engine이 이미 정한 것 (새 판단 아님).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_PAGE = 1000
_CLAUSE_SELECT = (
    "id, source_article_id, source_part_id, "
    "executor_text, condition_text, action_text, content_type"
)


def _confidence_band(value: Any) -> str:
    """numeric confidence → HIGH/MEDIUM/LOW."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "MEDIUM"
    if v >= 0.9:
        return "HIGH"
    if v >= 0.8:
        return "MEDIUM"
    return "LOW"


def obligation_instances_to_candidates(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """obligation_instance(+semantic_clause JOIN) rows → Adapter candidate.

    rows 각 항목 필요 키 (SQL JOIN으로 공급):
      source_clause_id, source_article_id, source_part_id,
      trigger_type, trigger_l2, executor_text,
      condition_text, action_text, content_type,
      applicable_sectors, confidence
    """
    candidates: List[Dict[str, Any]] = []
    for r in rows:
        trigger_l2 = r.get("trigger_l2") or "UNIVERSAL"
        sectors = r.get("applicable_sectors") or []
        candidates.append({
            "clause_id": str(r.get("source_clause_id") or ""),
            "source_article_id": str(r.get("source_article_id") or ""),
            "source_part_id": str(r.get("source_part_id") or ""),
            "trigger_code": f'{r.get("trigger_type")}:{trigger_l2}',
            "executor_text": r.get("executor_text"),
            "condition_text": r.get("condition_text"),
            "action_text": r.get("action_text"),
            "content_type": r.get("content_type"),
            "sector": sectors[0] if sectors else None,
            "confidence": _confidence_band(r.get("confidence")),
        })
    return candidates


def _flatten_embedded_join(row: Dict[str, Any]) -> Dict[str, Any]:
    """PostgREST embedded semantic_clause → flat row."""
    sc = row.get("semantic_clause") or {}
    return {
        "source_clause_id": row.get("source_clause_id"),
        "source_article_id": sc.get("source_article_id"),
        "source_part_id": sc.get("source_part_id"),
        "trigger_type": row.get("trigger_type"),
        "trigger_l2": row.get("trigger_l2"),
        "executor_text": sc.get("executor_text"),
        "condition_text": sc.get("condition_text"),
        "action_text": sc.get("action_text"),
        "content_type": sc.get("content_type"),
        "applicable_sectors": row.get("applicable_sectors"),
        "confidence": row.get("confidence"),
    }


def _fetch_via_embedded_join(supabase, factory_id: str) -> Optional[List[Dict[str, Any]]]:
    """PostgREST obligation_instance → semantic_clause!inner."""
    try:
        res = (
            supabase.table("obligation_instance")
            .select(
                "source_clause_id, trigger_type, trigger_l2, "
                "applicable_sectors, confidence, "
                f"semantic_clause!inner({_CLAUSE_SELECT})"
            )
            .eq("factory_id", factory_id)
            .eq("status", "ACTIVE")
            .execute()
        )
    except Exception as exc:
        log.warning("embedded join failed, fallback to 2-step: %s", exc)
        return None
    raw = res.data or []
    return [_flatten_embedded_join(r) for r in raw]


def _fetch_via_two_step(supabase, factory_id: str) -> List[Dict[str, Any]]:
    """obligation_instance 조회 → source_clause_id IN semantic_clause → 병합."""
    oi_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        res = (
            supabase.table("obligation_instance")
            .select(
                "source_clause_id, trigger_type, trigger_l2, "
                "applicable_sectors, confidence"
            )
            .eq("factory_id", factory_id)
            .eq("status", "ACTIVE")
            .range(offset, offset + _PAGE - 1)
            .execute()
        )
        chunk = res.data or []
        if not chunk:
            break
        oi_rows.extend(chunk)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE

    if not oi_rows:
        return []

    clause_ids = list({
        str(r["source_clause_id"])
        for r in oi_rows
        if r.get("source_clause_id")
    })
    clause_map: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(clause_ids), 200):
        chunk_ids = clause_ids[i:i + 200]
        res = (
            supabase.table("semantic_clause")
            .select(_CLAUSE_SELECT)
            .in_("id", chunk_ids)
            .execute()
        )
        for row in res.data or []:
            clause_map[str(row["id"])] = row

    merged: List[Dict[str, Any]] = []
    for oi in oi_rows:
        cid = str(oi.get("source_clause_id") or "")
        sc = clause_map.get(cid)
        if not sc:
            continue
        merged.append({
            "source_clause_id": oi.get("source_clause_id"),
            "source_article_id": sc.get("source_article_id"),
            "source_part_id": sc.get("source_part_id"),
            "trigger_type": oi.get("trigger_type"),
            "trigger_l2": oi.get("trigger_l2"),
            "executor_text": sc.get("executor_text"),
            "condition_text": sc.get("condition_text"),
            "action_text": sc.get("action_text"),
            "content_type": sc.get("content_type"),
            "applicable_sectors": oi.get("applicable_sectors"),
            "confidence": oi.get("confidence"),
        })
    return merged


def fetch_obligation_instance_rows(supabase, factory_id: str) -> List[Dict[str, Any]]:
    """ACTIVE obligation_instance + semantic_clause JOIN rows."""
    rows = _fetch_via_embedded_join(supabase, factory_id)
    if rows is not None:
        return rows
    return _fetch_via_two_step(supabase, factory_id)


def obligation_instances_to_trigger_candidates(
    factory_id: str,
    supabase=None,
) -> List[Dict[str, Any]]:
    """obligation_instance → build_obligations_from_trigger_candidates() 입력.

    변환만 수행. 새 판단/필터/법령/Trigger 없음.
    """
    if supabase is None:
        from db.supabase_client import get_supabase
        supabase = get_supabase()
    rows = fetch_obligation_instance_rows(supabase, factory_id)
    return obligation_instances_to_candidates(rows)
