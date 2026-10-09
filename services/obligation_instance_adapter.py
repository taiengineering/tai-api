"""Applicability Engine(obligation_instance) → 45CM Adapter Glue (CURSOR-TASK-001).

원칙:
  - 변환만. 판단/필터/법령생성/Trigger 생성 없음.
  - FastAPI import 없음 (순수 서비스).
  - obligation_adapter_service 무수정 호출.
  - status='ACTIVE'는 Engine이 이미 정한 것 (새 판단 아님).

v1.1.0 (WO-ADAPTER-LAW-ENRICHMENT-001):
  - 누락 law_name/law_article 보강 추가 (source_article_id → law_article → law_master JOIN).
  - 새 판단/법령 생성 아님. DB에 이미 있는 법령식별 값을 후보에 채울 뿐.
  - 실패 시 빈 값 유지(graceful) — 파이프라인 무중단.
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


def _format_law_article(article_no: Any, article_sub_no: Any) -> str:
    """law_article 표기 문자열. 예: 139 → '제139조', (24, 2) → '제24조의2'.

    새 데이터 생성 아님 — law_article의 표준 표기일 뿐.
    """
    if article_no in (None, ""):
        return ""
    base = f"제{article_no}조"
    if article_sub_no not in (None, "", 0):
        return f"{base}의{article_sub_no}"
    return base


def obligation_instances_to_candidates(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """obligation_instance(+semantic_clause JOIN) rows → Adapter candidate.

    rows 각 항목 필요 키 (SQL JOIN으로 공급):
      source_clause_id, source_article_id, source_part_id,
      trigger_type, trigger_l2, executor_text,
      condition_text, action_text, content_type,
      applicable_sectors, confidence

    law_name/law_article는 빈 값으로 두고 _resolve_law_for_candidates()가 보강.
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
            "law_name": "",      # _resolve_law_for_candidates()가 보강
            "law_article": "",   # _resolve_law_for_candidates()가 보강
        })
    return candidates


def _resolve_law_for_candidates(
    supabase,
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """source_article_id → law_article → law_master JOIN으로 law_name/law_article 보강.

    원칙:
      - 새 판단/법령 생성 없음. DB에 이미 있는 식별값을 후보에 채울 뿐.
      - 실패 시 후보를 그대로 반환(빈 값 유지) — 파이프라인 무중단.
    """
    try:
        article_ids = list({
            str(c["source_article_id"])
            for c in candidates
            if c.get("source_article_id")
        })
        if not article_ids:
            return candidates

        # source_article_id → law_article
        article_map: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(article_ids), 200):
            chunk = article_ids[i:i + 200]
            res = (
                supabase.table("law_article")
                .select("id, law_id, article_no, article_sub_no")
                .in_("id", chunk)
                .execute()
            )
            for a in res.data or []:
                article_map[str(a["id"])] = a

        # law_id → law_master
        law_ids = list({
            str(a["law_id"])
            for a in article_map.values()
            if a.get("law_id")
        })
        law_map: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(law_ids), 200):
            chunk = law_ids[i:i + 200]
            res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("id", chunk)
                .execute()
            )
            for lm in res.data or []:
                law_map[str(lm["id"])] = lm

        # 후보 보강
        for c in candidates:
            art = article_map.get(str(c.get("source_article_id") or ""))
            if not art:
                continue
            law = law_map.get(str(art.get("law_id") or ""))
            c["law_name"] = str((law or {}).get("law_name") or "")
            c["law_article"] = _format_law_article(
                art.get("article_no"), art.get("article_sub_no")
            )
        return candidates
    except Exception as exc:
        log.warning("law enrichment failed, keep empty: %s", exc)
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
    law_name/law_article는 _resolve_law_for_candidates()가 DB JOIN으로 보강.
    """
    if supabase is None:
        from db.supabase_client import get_supabase
        supabase = get_supabase()
    rows = fetch_obligation_instance_rows(supabase, factory_id)
    candidates = obligation_instances_to_candidates(rows)
    candidates = _resolve_law_for_candidates(supabase, candidates)
    return candidates
