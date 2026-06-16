"""D-005: KSIC Signal Engine 서비스

process_noun_match_stats의 noun을 clause_text에서 매칭해
업종(KSIC) 기반 의무 신호 생성.

원칙:
  KSICSignal = 의무 추가용 (제거 근거 가능 금지)
  매칭 없어도 기존 CheckResult 유지
  obligation_hits가 높을수록 신호 우선

금지:
  process_noun_match_stats 수정
  factories 수정
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from schemas.ksic_signal_schema import KSICSignal
from schemas.section_candidate_schema import SectionCandidateClause

log = logging.getLogger(__name__)

# 너무 일반적인 명사는 신호로 부적합 — 최소 글자수 필터
_MIN_NOUN_LEN = 2
# 의무 함의 낮음 효율성 필터
_MIN_OBLIGATION_HITS = 10


def load_noun_stats(supabase) -> List[dict]:
    """process_noun_match_stats 전체 로드.

    obligation_hits 내림차순 정렬. 최소조건 필터.
    """
    all_stats: List[dict] = []
    offset = 0
    page = 1000
    while True:
        res = (
            supabase.table("process_noun_match_stats")
            .select("id, noun, noun_len, obligation_hits, distinct_articles")
            .gte("noun_len", _MIN_NOUN_LEN)
            .gte("obligation_hits", _MIN_OBLIGATION_HITS)
            .order("obligation_hits", desc=True)
            .range(offset, offset + page - 1)
            .execute()
        )
        batch = res.data or []
        all_stats.extend(batch)
        if len(batch) < page:
            break
        offset += page
    log.info("noun_stats 로드: %d개", len(all_stats))
    return all_stats


def get_facility_ksic(supabase, facility_id: str) -> Dict[str, Optional[str]]:
    """factories에서 ksic_code, ksic_name 조회."""
    try:
        res = (
            supabase.table("factories")
            .select("id, ksic_code, ksic_name")
            .eq("id", facility_id)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return {
                "ksic_code": row.get("ksic_code"),
                "ksic_name": row.get("ksic_name"),
            }
    except Exception as exc:
        log.error("get_facility_ksic 오류: %s", exc)
    return {"ksic_code": None, "ksic_name": None}


def generate_ksic_signals(
    supabase,
    clauses: List[SectionCandidateClause],
    facility_id: str,
    noun_stats: List[dict],
) -> List[KSICSignal]:
    """SectionCandidateClause 목록에서 KSICSignal 생성.

    clause_text에 noun이 포함되면 신호 생성.
    신호 없는 clause는 또도 버리지 않음.

    Returns:
        KSICSignal 목록 (하나의 clause에 여러 신호 가능)
    """
    ksic_info = get_facility_ksic(supabase, facility_id)
    signals: List[KSICSignal] = []

    for clause in clauses:
        clause_text = clause.clause_text or ""
        for stat in noun_stats:
            noun = stat.get("noun", "")
            if not noun:
                continue
            if noun in clause_text:
                signals.append(KSICSignal(
                    clause_id=clause.clause_id,
                    facility_id=facility_id,
                    ksic_code=ksic_info["ksic_code"],
                    ksic_name=ksic_info["ksic_name"],
                    matched_noun=noun,
                    obligation_hits=stat.get("obligation_hits", 0),
                    distinct_articles=stat.get("distinct_articles", 0),
                ))
                break  # 첫 매칭 noun만 (obligation_hits 내림차순 이미 정렬)

    return signals
