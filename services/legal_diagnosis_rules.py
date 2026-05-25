"""
진단 step1/2/3 공통 규칙 fetch — v1 테이블 / v2 adapter / runtime projection.

작업지시서 Step 5·6: 서비스 계층에서 데이터 소스 전환 + 환경변수 플래그.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.legal_helpers import get_sector_groups
from services.legal_runtime_fetch import USE_RUNTIME_ENGINE, fetch_runtime_rules_as_v1
from services.rule_v2_adapter import (
    adapt_v2_batch,
    build_relation_map,
    build_scope_map,
    filter_v2_rules_construction_work_types,
    filter_v2_rules_for_sector,
)

USE_V2_ENGINE = os.environ.get("TAI_USE_V2_ENGINE", "false").lower() == "true"

_V2_RULE_KINDS = ("OBLIGATION", "PROHIBITION")
_SELECT_ALL = "*"
_RELATION_CHUNK = 200


def diagnosis_rule_source_label() -> str:
    """anonymous_diagnosis_results.rule_version 등에 기록."""
    if USE_RUNTIME_ENGINE:
        return "runtime_metadata_resolution:v1"
    if USE_V2_ENGINE:
        return "master_rule_v2:v1"
    return "master_building_legal_rules:v1"


def _chunked_in_query(
    supabase,
    table: str,
    select: str,
    column: str,
    ids: List[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    clean = [x for x in ids if x]
    for i in range(0, len(clean), _RELATION_CHUNK):
        chunk = clean[i : i + _RELATION_CHUNK]
        if not chunk:
            continue
        res = supabase.table(table).select(select).in_(column, chunk).execute()
        rows.extend(res.data or [])
    return rows


def _load_v2_support_maps(
    supabase,
    obligation_ids: List[str],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    rel_rows = _chunked_in_query(
        supabase,
        "master_rule_v2_relation",
        "*",
        "source_rule_id",
        obligation_ids,
    )
    rel_map = build_relation_map(rel_rows)

    penalty_ids = list({str(r.get("target_rule_id")) for r in rel_rows if r.get("target_rule_id")})
    penalty_rules: Dict[str, Dict[str, Any]] = {}
    if penalty_ids:
        for row in _chunked_in_query(supabase, "master_rule_v2", _SELECT_ALL, "id", penalty_ids):
            pid = str(row.get("id") or "")
            if pid:
                penalty_rules[pid] = row

    mapping_rows = _chunked_in_query(
        supabase,
        "master_rule_scope_mapping",
        "rule_id,scope_id",
        "rule_id",
        obligation_ids,
    )
    scope_ids = list({str(m.get("scope_id")) for m in mapping_rows if m.get("scope_id")})
    scope_by_id: Dict[str, Dict[str, Any]] = {}
    thresholds_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    if scope_ids:
        for row in _chunked_in_query(supabase, "master_rule_scope", _SELECT_ALL, "id", scope_ids):
            sid = str(row.get("id") or "")
            if sid:
                scope_by_id[sid] = row
        for row in _chunked_in_query(
            supabase,
            "master_rule_scope_threshold",
            "*",
            "scope_id",
            scope_ids,
        ):
            sid = str(row.get("scope_id") or "")
            if sid:
                thresholds_by_scope.setdefault(sid, []).append(row)

    scope_map = build_scope_map(mapping_rows, scope_by_id, thresholds_by_scope)
    return rel_map, scope_map, penalty_rules


def fetch_rules_v1(
    supabase,
    *,
    sector_db: str,
    sector_groups: Optional[List[str]] = None,
    diagnosis_stage: Optional[int] = None,
    diagnosis_stage_lte: Optional[int] = None,
    work_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    groups = sector_groups or get_sector_groups(sector_db)
    q = (
        supabase.table("master_building_legal_rules")
        .select(_SELECT_ALL)
        .eq("is_active", True)
        .in_("sector", groups)
    )
    if diagnosis_stage is not None:
        q = q.eq("diagnosis_stage", diagnosis_stage)
    if diagnosis_stage_lte is not None:
        q = q.lte("diagnosis_stage", diagnosis_stage_lte)
    if work_types:
        work_type_csv = ",".join(work_types)
        q = q.or_(f"construction_work_type.is.null,construction_work_type.in.({work_type_csv})")
    return q.execute().data or []


def fetch_rules_v2_as_v1(
    supabase,
    *,
    sector_db: str,
    diagnosis_stage: Optional[int] = None,
    diagnosis_stage_lte: Optional[int] = None,
    work_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    q = (
        supabase.table("master_rule_v2")
        .select(_SELECT_ALL)
        .in_("rule_kind", list(_V2_RULE_KINDS))
    )
    try:
        res = q.neq("status", "DEPRECATED").execute()
    except Exception:
        try:
            res = q.eq("is_active", True).execute()
        except Exception:
            res = q.execute()

    raw_rows = res.data or []
    v2_rows = [r for r in raw_rows if (r.get("status") or "").strip().upper() != "DEPRECATED"]
    v2_rows = filter_v2_rules_for_sector(v2_rows, sector_db)
    if work_types:
        v2_rows = filter_v2_rules_construction_work_types(v2_rows, work_types)

    obligation_ids = [str(r.get("id")) for r in v2_rows if r.get("id")]
    rel_map, scope_map, penalty_map = _load_v2_support_maps(supabase, obligation_ids)
    all_rules = adapt_v2_batch(
        v2_rows,
        relations=rel_map,
        scopes=scope_map,
        penalty_rules=penalty_map,
        sector_hint=sector_db,
    )

    if diagnosis_stage is not None:
        all_rules = [r for r in all_rules if int(r.get("diagnosis_stage") or 1) == diagnosis_stage]
    elif diagnosis_stage_lte is not None:
        all_rules = [r for r in all_rules if int(r.get("diagnosis_stage") or 1) <= diagnosis_stage_lte]
    return all_rules


def fetch_diagnosis_rules(
    supabase,
    *,
    sector_db: str,
    diagnosis_stage: Optional[int] = None,
    diagnosis_stage_lte: Optional[int] = None,
    work_types: Optional[List[str]] = None,
    factory_id: Optional[str] = None,
    sector_groups: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    진단용 v1 호환 rule dict 목록.

    우선순위: TAI_USE_RUNTIME_ENGINE > TAI_USE_V2_ENGINE > master_building_legal_rules
    """
    if USE_RUNTIME_ENGINE:
        rules = fetch_runtime_rules_as_v1(
            supabase,
            sector_db=sector_db,
            factory_id=factory_id,
            diagnosis_stage=diagnosis_stage,
            diagnosis_stage_lte=diagnosis_stage_lte,
        )
        if work_types:
            allowed = {w.strip() for w in work_types if w}
            rules = [
                r
                for r in rules
                if not (r.get("construction_work_type") or "").strip()
                or (r.get("construction_work_type") or "").strip() in allowed
            ]
        return rules
    if USE_V2_ENGINE:
        return fetch_rules_v2_as_v1(
            supabase,
            sector_db=sector_db,
            diagnosis_stage=diagnosis_stage,
            diagnosis_stage_lte=diagnosis_stage_lte,
            work_types=work_types,
        )
    return fetch_rules_v1(
        supabase,
        sector_db=sector_db,
        sector_groups=sector_groups,
        diagnosis_stage=diagnosis_stage,
        diagnosis_stage_lte=diagnosis_stage_lte,
        work_types=work_types,
    )
