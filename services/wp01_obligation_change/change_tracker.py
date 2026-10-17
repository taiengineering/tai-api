"""services/wp01_obligation_change/change_tracker.py

WP01-D: 의무 변경 추적 — ADDED / RETAINED / REMOVAL_CANDIDATE 계산.

법령 진단(C10)의 obligations_raw 를 비교하여
전 회차 대비 추가/유지/제거 후보 atom_id 세트를 산출한다.
DB 쓰기 없음(READ-ONLY). 실패 시 fail-closed(ValueError 발생).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

_CONSTRUCTION_SECTORS = {"CONSTRUCTION", "construction"}


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

def load_previous_materialized_obligations(
    supabase: Any,
    factory_id: str,
    exclude_diagnosis_id: str,
    site_id: Optional[str] = None,
    sector: Optional[str] = None,
    new_created_at: Optional[str] = None,
) -> Tuple[list, bool]:
    """공장의 직전 MATERIALIZED C10 obligations_raw 로드.

    조건: source_type=saas, status=ACTIVE,
          inspection_materialization_status=MATERIALIZED,
          input_data->>factory_id = factory_id,
          id != exclude_diagnosis_id.
    건설현장의 경우 site_id 도 추가 필터링.
    sector 가 지정된 경우 input_data->>sector 도 일치 확인.
    new_created_at 이 제공된 경우 신규 진단보다 이전 시점만 포함.

    반환: (obligations_raw: list, has_row: bool)
      has_row=True: 이전 기준 행이 존재(obligations_raw 가 빈 목록일 수 있음)
      has_row=False: 이전 기준 없음(첫 진단)
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

    if new_created_at:
        q = q.lt("created_at", new_created_at)

    if site_id:
        q = q.eq("input_data->>site_id", site_id)

    if sector:
        q = q.eq("input_data->>sector", sector)

    res = q.order("created_at", desc=True).limit(1).execute()

    if not res.data:
        log.debug(
            "load_previous_materialized_obligations: no previous MATERIALIZED row "
            "factory_id=%s sector=%s exclude=%s",
            factory_id,
            sector,
            exclude_diagnosis_id,
        )
        return [], False

    full_result = res.data[0].get("full_result") or {}
    obligations_raw = full_result.get("obligations_raw")
    # P4-05: 누락(None)과 정상 0건([])을 구분 — 구조 무결성 경고
    if obligations_raw is None:
        log.warning(
            "load_previous_materialized_obligations: obligations_raw 필드 누락 "
            "(None) — id=%s factory_id=%s",
            res.data[0].get("id"),
            factory_id,
        )
    return obligations_raw or [], True


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

    if not c10_res.data:
        # C10 없으면 기준 없음 → 빈 리스트 반환 (fail-closed)
        return []

    full_result = c10_res.data[0].get("full_result") or {}
    c10_atom_ids: Set[str] = extract_atom_ids(full_result.get("obligations_raw") or [])

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
    return [
        r for r in rows
        if r.get("legal_obligation_atom_id") not in c10_atom_ids
    ]


def _is_current_removal_candidate(
    supabase: Any, factory_id: str, inspection_set_id: str
) -> bool:
    """inspection_set 이 현재 유효한 REMOVAL_CANDIDATE 인지 서버 재확인.

    FIX-02 공식 비교 계약:
    1. inspection_set: is_active=True, source=LEGAL_ENGINE, atom_id 존재
    2. 최신 MATERIALIZED C10 obligations_raw 가 유효한 list 여야 함 (구조 무결성)
    3. atom 이 최신 C10 에 없어야 함 (REMOVAL CANDIDATE 조건)
    4. atom 이 이전 C10 에 있어야 함 (최소 1회 의무였음을 증명)
    5. sector/site 범위가 최신 C10 기준으로 일치해야 함

    4 불충족(이전 기준 없음 또는 atom 미포함) → False (제외 불허).
    """
    # 1. inspection_set 검증
    is_res = (
        supabase.table("inspection_sets")
        .select("legal_obligation_atom_id, is_active, source")
        .eq("id", inspection_set_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not is_res.data:
        return False
    iset = is_res.data[0]
    if not iset.get("is_active") or iset.get("source") != "LEGAL_ENGINE":
        return False

    atom_id = iset.get("legal_obligation_atom_id")
    if not atom_id:
        return False

    # 2+3. 최신 MATERIALIZED C10 — id/input_data/created_at 포함 로드
    c10_res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, full_result, input_data, created_at")
        .eq("source_type", "saas")
        .eq("status", "ACTIVE")
        .eq("inspection_materialization_status", "MATERIALIZED")
        .eq("input_data->>factory_id", factory_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not c10_res.data:
        return False  # C10 없음 → fail-closed

    latest_c10 = c10_res.data[0]
    latest_full_result = latest_c10.get("full_result") or {}
    latest_obligations_raw = latest_full_result.get("obligations_raw")

    if not isinstance(latest_obligations_raw, list):
        log.warning(
            "_is_current_removal_candidate: obligations_raw 비정상 구조 — "
            "factory_id=%s diagnosis_id=%s",
            factory_id,
            latest_c10.get("id"),
        )
        return False  # 구조 무결성 실패 → fail-closed

    latest_atom_ids = extract_atom_ids(latest_obligations_raw)
    if atom_id in latest_atom_ids:
        return False  # 최신 C10 에 존재 → 제외 후보 아님

    # 4+5. 이전 기준 C10 검증 — sector/site 범위 일치
    latest_input_data = latest_c10.get("input_data") or {}
    prev_obligations_raw, has_prev = load_previous_materialized_obligations(
        supabase,
        factory_id,
        exclude_diagnosis_id=latest_c10["id"],
        site_id=latest_input_data.get("site_id"),
        sector=latest_input_data.get("sector"),
        new_created_at=latest_c10.get("created_at"),
    )

    if not has_prev:
        log.debug(
            "_is_current_removal_candidate: 이전 기준 없음 → 제외 불허. "
            "factory_id=%s atom_id=%s",
            factory_id,
            atom_id,
        )
        return False  # 이전 기준 없으면 제외 불허

    # atom 이 이전 C10 에 포함돼야 제외 후보 성립
    prev_atom_ids = extract_atom_ids(prev_obligations_raw)
    return atom_id in prev_atom_ids


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

    fail-closed:
      - 신규 C10 미발견 또는 factory_id 불일치 → ValueError
      - CONSTRUCTION sector 이면서 site_id 없음 → ValueError
    """
    # 1. 신규 C10 — factory_id 소유권 + MATERIALIZED 상태 검증
    new_res = (
        supabase.table("anonymous_diagnosis_results")
        .select("full_result, input_data, created_at")
        .eq("id", new_diagnosis_id)
        .eq("input_data->>factory_id", factory_id)
        .eq("source_type", "saas")
        .eq("status", "ACTIVE")
        .eq("inspection_materialization_status", "MATERIALIZED")
        .limit(1)
        .execute()
    )

    if not new_res.data:
        raise ValueError(
            f"진단 결과를 찾을 수 없습니다: diagnosis_id={new_diagnosis_id}"
        )

    new_row = new_res.data[0]
    new_full_result = new_row.get("full_result") or {}
    _raw_val = new_full_result.get("obligations_raw")
    # P4-05: 누락(None)과 정상 0건([])을 구분 — 구조 무결성 경고
    if _raw_val is None:
        log.warning(
            "[compute_change_summary] obligations_raw 필드 누락 — diagnosis_id=%s",
            new_diagnosis_id,
        )
    new_obligations_raw = _raw_val or []
    new_created_at: Optional[str] = new_row.get("created_at")

    # sector / site_id 추출
    new_input_data = new_row.get("input_data") or {}
    new_sector: Optional[str] = new_input_data.get("sector")
    stored_site_id: Optional[str] = new_input_data.get("site_id")

    # site_id 불일치 검증
    if site_id and stored_site_id and site_id != stored_site_id:
        raise ValueError(
            f"site_id 불일치: 요청={site_id!r}, 진단={stored_site_id!r}"
        )

    new_site_id: Optional[str] = site_id or stored_site_id

    # CONSTRUCTION: site_id 필수
    if new_sector in _CONSTRUCTION_SECTORS and not new_site_id:
        raise ValueError(
            "건설업 진단의 변경 요약에는 site_id 가 필요합니다"
        )

    # 2. 이전 MATERIALIZED C10 (섹터·현장 일치, 신규 이전 시점)
    prev_obligations_raw, has_prev_row = load_previous_materialized_obligations(
        supabase,
        factory_id,
        exclude_diagnosis_id=new_diagnosis_id,
        site_id=new_site_id,
        sector=new_sector,
        new_created_at=new_created_at,
    )
    has_previous_baseline = has_prev_row  # row 존재 여부 — obligations 0건과 구분

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
