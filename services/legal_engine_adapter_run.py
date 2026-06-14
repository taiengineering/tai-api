"""
legal_engine_adapter_run — 어댑터를 실제로 붙여 돌려보는 경로 (검증용).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md
흐름:
  factory_id → 사용자입력 표준화(_input_to_facility_context, 기존 재사용)
           → 어댑터.facility_input_to_base (사업장 = 평가 주체측)
           → sector 해당 article의 의미절 적재(semantic_clause_fix, 보정 executor)
           → 어댑터.clause_to_context (의무 1건 → 표준 계약 1건)
           → 표준 계약 목록 반환

이 단계는 "붙여서 무엇이 나오는지 본다"가 목적. 엔진 평가/정제는 아직 안 붙임 —
표준 계약으로 변환된 의무 목록이 제대로 나오는지(수범자/조건이 표준 형식으로 실리는지)를
글로 읽어 확인하는 것이 1차. 기존 진단 경로 무수정.

영역: 어댑터 변환만. 분해기·판정로직(GPT)·엔진코어 무수정. 의미절 읽기만.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from services.legal_context import _input_to_facility_context
from services.anonymous_factory_service import normalize_consumer_inp, _mapping_sector_key
from services.legal_rules import normalize_sector_db
from schemas.legal_engine import DiagnoseStep1Body
from services import legal_engine_adapter as adapter

log = logging.getLogger(__name__)

_PAGE = 1000
_CHUNK = 200


def _load_sector_allowed_article_ids(supabase, sector_value: str) -> Optional[Set[str]]:
    """sector → 허용 article_id 집합 (기존 표준 law_article→law_master←law_sector_mapping 재사용).
    미매핑은 가지고 감. 매핑 없거나 실패 시 None(전체 폴백)."""
    key = _mapping_sector_key(sector_value)
    if not key:
        return None
    article_law: Dict[str, str] = {}
    law_ids: Set[str] = set()
    offset = 0
    while True:
        try:
            res = supabase.table("law_article").select("id, law_id").range(offset, offset + _PAGE - 1).execute()
        except Exception as exc:
            log.warning("adapter sector-filter law_article failed: %s", exc)
            return None
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("id") or "")
            lid = str(row.get("law_id") or "")
            if aid and lid:
                article_law[aid] = lid
                law_ids.add(lid)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    if not article_law:
        return None
    law_sectors: Dict[str, List[str]] = {}
    lid_list = list(law_ids)
    for i in range(0, len(lid_list), _CHUNK):
        chunk = lid_list[i:i + _CHUNK]
        try:
            res = supabase.table("law_sector_mapping").select("law_id, sectors").in_("law_id", chunk).execute()
        except Exception as exc:
            log.warning("adapter sector-filter mapping failed: %s", exc)
            return None
        for row in res.data or []:
            lid = str(row.get("law_id") or "")
            secs = row.get("sectors") or []
            if lid:
                law_sectors[lid] = [str(s).strip().upper() for s in secs if s]
    if not law_sectors:
        return None
    allowed: Set[str] = set()
    for aid, lid in article_law.items():
        secs = law_sectors.get(lid)
        if secs is None or key in secs:
            allowed.add(aid)
    return allowed


def _load_obligation_clauses(supabase, allowed_article_ids: Optional[Set[str]]) -> List[Dict[str, Any]]:
    """semantic_clause_fix(보정 executor)에서 OBLIGATION/PROHIBITION 의무절 적재."""
    clauses: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = (
                supabase.table("semantic_clause_fix")
                .select("id, source_article_id, source_part_id, source_text, executor_text, "
                        "action_text, condition_text, cycle_text, content_type, sector")
                .in_("content_type", ["OBLIGATION", "PROHIBITION"])
                .range(offset, offset + _PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.warning("adapter clause fetch failed: %s", exc)
            break
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("source_article_id") or "")
            if allowed_article_ids is not None and aid and aid not in allowed_article_ids:
                continue
            clauses.append(row)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    return clauses


def run_adapter_diagnosis(supabase, body: DiagnoseStep1Body) -> Dict[str, Any]:
    """어댑터를 붙여 표준 계약 목록을 만든다 (1차: 변환 결과 확인용)."""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    sector_db = normalize_sector_db(sector_raw)

    # 사용자 입력 → 사업장 base (어댑터)
    facility_base = adapter.facility_input_to_base(sector_raw, facility_ctx)

    # sector 해당 의무절 적재 → 어댑터로 표준 계약 변환
    allowed = _load_sector_allowed_article_ids(supabase, sector_db)
    clauses = _load_obligation_clauses(supabase, allowed)

    contexts: List[Dict[str, Any]] = []
    skipped = 0
    for c in clauses:
        ctx = adapter.clause_to_context(c, facility_ctx)
        if ctx is None:
            skipped += 1
            continue
        contexts.append(ctx)

    return {
        "adapter": adapter.adapter_definition(),
        "facility_base": facility_base,
        "sector": sector_raw,
        "counts": {
            "clauses_loaded": len(clauses),
            "contexts_built": len(contexts),
            "skipped_non_obligation": skipped,
            "sector_filtered": allowed is not None,
            "allowed_articles": len(allowed) if allowed else None,
        },
        "contexts": contexts,
    }
