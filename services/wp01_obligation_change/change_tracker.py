"""services/wp01_obligation_change/change_tracker.py

WP01-D: 의무 변경 추적 — ADDED / RETAINED / REMOVAL_CANDIDATE 계산.

법령 진단(C10)의 obligations_raw 를 비교하여
전 회차 대비 추가/유지/제거 후보 atom_id 세트를 산출한다.
DB 쓰기 없음(READ-ONLY). 실패 시 fail-closed(ValueError 발생).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def extract_atom_ids(obligations_raw: list) -> set:
    """obligations_raw 에서 atom_id 세트 추출.

    각 요소에 'atom_id' 키가 있을 때만 포함(None / 빈 문자열 제외).
    """
    return {
        o.get("atom_id")
        for o in (obligations_raw or [])
        if o.get("atom_id")
    }


def diff_obligations(prev_obligations_raw: list, new_obligations_raw: list) -> dict:
    """두 obligations_raw 목록 비교.

    반환:
        added_atom_ids: list — 신규 진단에만 있음
        retained_atom_ids: list — 양쪽 모두 있음
        removal_candidate_atom_ids: list — 이전에만 있음
    """
    prev_ids: Set[str] = extract_atom_ids(prev_obligations_raw)
    new_ids: Set[str] = extract_atom_ids(new_obligations_raw)

    added = sorted(new_ids - prev_ids)
    retained = sorted(new_ids & prev_ids)
    removal_candidates = sorted(prev_ids - new_ids)

    return {
        "added_atom_ids": added,
        "retained_atom_ids": retained,
        "removal_candidate_atom_ids": removal_candidates,
    }


# ---------------------------------------------------------------------------
# DB read helpers
# ---------------------------------------------------------------------------

def _get_obligations_raw_from_diagnosis(supabase: Any, diagnosis_id: str) -> list:
    """anonymous_diagnosis_results 에서 obligations_raw 로드."""
    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("full_result")
        .eq("id", diagnosis_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return []
    full_result = res.data[0].get("full_result") or {}
    return full_result.get("obligations_raw") or []


def load_previous_materialized_obligations(
    supabase: Any,
    factory_id: str,
    exclude_diagnosis_id: str,
    site_id: Optional[str] = None,
) -> list:
    """공장의 직전 MATERIALIZED C10 obligations_raw 로드.

    조건: source_type=saas, status=ACTIVE,
          inspection_materialization_status=MATERIALIZED,
          input_data->>factory_id = factory_id,
          id != exclude_diagnosis_id.
    건설현장의 경우 site_id 도 추가 필터링.
    결과 없으면 빈 목록 반환.
    """
    q = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, full_result, created_at")
        .eq("source_type", "saas")
        .eq("status", "ACTIVE")
        .eq("inspection_materialization_status", "MATERIALIZED")
        .eq("input_data->>factory_id", factory_id)
        .neq("id", exclude_diagnosis_id)
    )

    if site_id:
        q = q.eq("input_data->>site_id", site_id)

    res = q.order("created_at", desc=True).limit(1).execute()

    if not res.data:
        log.debug(
            "load_previous_materialized_obligations: no previous MATERIALIZED row "
            "factory_id=%s exclude=%s",
            factory_id,
            exclude_diagnosis_id,
        )
        return []

    full_result = res.data[0].get("full_result") or {}
    return full_result.get("obligations_raw") or []


def load_current_removal_candidates(supabase: Any, factory_id: str) -> list:
    """현재 REMOVAL_CANDIDATE 에 해당하는 inspection_sets 행 목록 반환.

    절차:
    1. 공장의 최신 MATERIALIZED C10 obligations_raw atom_id 세트 추출
    2. 공장의 활성 canonical inspection_sets 전체 로드
       (source=LEGAL_ENGINE, is_active=True)
    3. step2 중 step1 에 없는 행 반환

    반환 필드: id, inspection_set_name, law_name, law_article,
               legal_obligation_atom_id, obligation_type, status_code
    """
    # 1. 최신 MATERIALIZED C10 atom_ids
    c10_res = (
        supabase.table("anonymous_diagnosis_results")
        .select("full_result")
        .eq("source_type", "saas")
        .eq("status", "ACTIVE")
        .eq("inspection_materialization_status", "MATERIALIZED")
        .eq("input_data->>factory_id", factory_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    c10_atom_ids: Set[str] = set()
    if c10_res.data:
        full_result = c10_res.data[0].get("full_result") or {}
        c10_atom_ids = extract_atom_ids(full_result.get("obligations_raw") or [])

    # 2. 활성 canonical inspection_sets
    sets_res = (
        supabase.table("inspection_sets")
        .select(
            "id, inspection_set_name, law_name, law_article, "
            "legal_obligation_atom_id, obligation_type, status_code"
        )
        .eq("factory_id", factory_id)
        .eq("source", "LEGAL_ENGINE")
        .eq("is_active", True)
        .execute()
    )

    rows = sets_res.data or []

    # 3. C10 에 없는 rows = REMOVAL_CANDIDATE
    return [
        r for r in rows
        if r.get("legal_obligation_atom_id") not in c10_atom_ids
    ]


# ---------------------------------------------------------------------------
# High-level summary
# ---------------------------------------------------------------------------

def compute_change_summary(
    supabase: Any,
    factory_id: str,
    new_diagnosis_id: str,
    site_id: Optional[str] = None,
) -> dict:
    """신규 진단 결과에 대한 ADDED/RETAINED/REMOVAL_CANDIDATE 요약 계산.

    반환:
        added_count: int
        retained_count: int
        removal_candidate_count: int
        removal_candidates: list[{inspection_set_id, atom_id, name, law_name, law_article}]
        has_previous_baseline: bool

    fail-closed: 신규 C10 미발견 → ValueError 발생.
    """
    # 1. 신규 C10 obligations_raw
    new_res = (
        supabase.table("anonymous_diagnosis_results")
        .select("full_result")
        .eq("id", new_diagnosis_id)
        .limit(1)
        .execute()
    )

    if not new_res.data:
        raise ValueError(
            f"진단 결과를 찾을 수 없습니다: diagnosis_id={new_diagnosis_id}"
        )

    new_full_result = new_res.data[0].get("full_result") or {}
    new_obligations_raw = new_full_result.get("obligations_raw") or []

    # 2. 이전 MATERIALIZED C10
    prev_obligations_raw = load_previous_materialized_obligations(
        supabase, factory_id, exclude_diagnosis_id=new_diagnosis_id, site_id=site_id
    )
    has_previous_baseline = bool(prev_obligations_raw)

    # 3. Diff
    diff = diff_obligations(prev_obligations_raw, new_obligations_raw)
    removal_candidate_atom_ids: Set[str] = set(diff["removal_candidate_atom_ids"])

    # 4. inspection_sets for REMOVAL_CANDIDATE atoms (display data)
    removal_candidates: List[Dict] = []
    if removal_candidate_atom_ids:
        sets_res = (
            supabase.table("inspection_sets")
            .select(
                "id, inspection_set_name, law_name, law_article, "
                "legal_obligation_atom_id"
            )
            .eq("factory_id", factory_id)
            .eq("source", "LEGAL_ENGINE")
            .eq("is_active", True)
            .execute()
        )
        for row in (sets_res.data or []):
            atom_id = row.get("legal_obligation_atom_id")
            if atom_id in removal_candidate_atom_ids:
                removal_candidates.append(
                    {
                        "inspection_set_id": row.get("id"),
                        "atom_id": atom_id,
                        "name": row.get("inspection_set_name"),
                        "law_name": row.get("law_name"),
                        "law_article": row.get("law_article"),
                    }
                )

    return {
        "added_count": len(diff["added_atom_ids"]),
        "retained_count": len(diff["retained_atom_ids"]),
        "removal_candidate_count": len(diff["removal_candidate_atom_ids"]),
        "removal_candidates": removal_candidates,
        "has_previous_baseline": has_previous_baseline,
    }
