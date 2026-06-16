"""D-006: Reverse Check Engine 서비스

ObligationCandidate → ReverseCheckResult 역추적.
네트워크 호출 없음 — 순수 변환 함수.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from schemas.reverse_check_schema import ObligationCandidate, ReverseCheckResult

log = logging.getLogger(__name__)

_LAW_BASE_URL = "https://www.law.go.kr/법령"


def _build_law_url(law_name: Optional[str], article_no: Optional[str]) -> Optional[str]:
    if not law_name or not article_no:
        return None
    return f"{_LAW_BASE_URL}/{law_name}/{article_no}"


def build_reverse_trace(obligation: ObligationCandidate) -> ReverseCheckResult:
    """ObligationCandidate의 모든 필드에서 경로를 역으로 재구성.

    순수 함수 — 네트워크 호출 없음.
    """
    cr = obligation.check_result
    sc = obligation.section_clause
    ks = obligation.ksic_signal

    law_name = cr.law_name
    article_no = cr.article_no
    article_title = cr.article_title

    # 실제 법령 번호 형식화
    article_no_str = str(article_no) if article_no else None

    full_trace: dict = {
        "track_a": {
            "applicability_id": cr.applicability_id,
            "draft_id": cr.draft_id,
            "applicability_status": cr.applicability_status,
            "match_details": cr.match_details,
            "verdict": cr.verdict,
            "reason": cr.reason,
        },
        "section": None,
        "ksic": None,
    }

    # 섹터 trace
    sector_assigned: list = []
    sector_source: Optional[str] = None
    sieve_rule_id: Optional[str] = None
    sieve_class_label: Optional[str] = None
    executor_text: Optional[str] = None

    if sc:
        sector_assigned = sc.assigned_sectors
        sector_source = sc.sector_source
        sieve_rule_id = sc.sieve_rule_id
        sieve_class_label = sc.sieve_class_label
        executor_text = sc.executor_text
        full_trace["section"] = {
            "clause_id": sc.clause_id,
            "executor_text": sc.executor_text,
            "sieve_result": sc.sieve_result,
            "sieve_rule_id": sc.sieve_rule_id,
            "sieve_class_label": sc.sieve_class_label,
            "assigned_sectors": sc.assigned_sectors,
            "sector_source": sc.sector_source,
        }

    # KSIC trace
    ksic_boost = False
    ksic_matched_noun: Optional[str] = None
    if ks:
        ksic_boost = True
        ksic_matched_noun = ks.matched_noun
        full_trace["ksic"] = {
            "matched_noun": ks.matched_noun,
            "obligation_hits": ks.obligation_hits,
            "distinct_articles": ks.distinct_articles,
            "ksic_code": ks.ksic_code,
        }

    return ReverseCheckResult(
        clause_id=sc.clause_id if sc else None,
        facility_id=cr.facility_id,
        law_name=law_name,
        article_no=article_no_str,
        article_title=article_title,
        law_article_url=_build_law_url(law_name, article_no_str),
        sieve_rule_id=sieve_rule_id,
        sieve_class_label=sieve_class_label,
        executor_text=executor_text,
        sector_assigned=sector_assigned,
        sector_source=sector_source,
        check_verdict=cr.verdict,
        check_reason=cr.reason,
        check_method=cr.check_method,
        applicability_status=cr.applicability_status,
        ksic_boost=ksic_boost,
        ksic_matched_noun=ksic_matched_noun,
        full_trace=full_trace,
    )


def run_reverse_check_batch(
    obligations: List[ObligationCandidate],
) -> List[ReverseCheckResult]:
    """ObligationCandidate 목록 일괄 역추적. DB 조회 없음."""
    results = []
    for ob in obligations:
        try:
            results.append(build_reverse_trace(ob))
        except Exception as exc:
            log.error("build_reverse_trace 오류: %s", exc)
    return results
