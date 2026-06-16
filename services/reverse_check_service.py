"""D-006: Reverse Check Service

'왜 포함됐는가' 역추적 — 순수 변환 함수.
DB 쓰기 없음, 네트워크 없음.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from schemas.check_input_schema import CheckResult
from schemas.reverse_check_schema import ReverseCheckResult


def _build_law_article_url(law_name: Optional[str], article_no: Optional[str]) -> Optional[str]:
    """법제처 조문 링크 생성."""
    if not law_name or not article_no:
        return None
    return f"https://www.law.go.kr/법령/{law_name}/제{article_no}조"


def build_reverse_trace(
    check_result: CheckResult,
    sieve_rule_id: Optional[str] = None,
    sieve_class_label: Optional[str] = None,
    sieve_result: Optional[str] = None,
    assigned_sectors: Optional[List[str]] = None,
    sector_source: Optional[str] = None,
    clause_text: Optional[str] = None,
    executor_text: Optional[str] = None,
    ksic_boost: bool = False,
    ksic_matched_noun: Optional[str] = None,
    ksic_code: Optional[str] = None,
) -> ReverseCheckResult:
    """CheckResult + 부가 맥락 → ReverseCheckResult.

    순수 함수. 입력만으로 결과 결정.
    """
    law_article_url = _build_law_article_url(
        check_result.law_name, check_result.article_no
    )

    full_trace: Dict[str, Any] = {
        "stage_sieve": {
            "sieve_rule_id": sieve_rule_id,
            "sieve_class_label": sieve_class_label,
            "sieve_result": sieve_result,
        },
        "stage_sector": {
            "assigned_sectors": assigned_sectors or [],
            "sector_source": sector_source,
        },
        "stage_check": {
            "verdict": check_result.verdict,
            "reason": check_result.reason,
            "check_method": check_result.check_method,
            "applicability_status": check_result.applicability_status,
            "draft_id": check_result.draft_id,
        },
        "stage_ksic": {
            "ksic_boost": ksic_boost,
            "matched_noun": ksic_matched_noun,
            "ksic_code": ksic_code,
        },
        "law": {
            "law_name": check_result.law_name,
            "article_no": check_result.article_no,
            "article_title": check_result.article_title,
            "article_url": law_article_url,
        },
    }

    return ReverseCheckResult(
        clause_id=check_result.applicability_id,  # Track A에서는 applicability_id를 clause_id 대용으로 사용
        facility_id=check_result.facility_id,
        law_name=check_result.law_name,
        article_no=check_result.article_no,
        article_title=check_result.article_title,
        executor_text=executor_text,
        clause_text=clause_text,
        law_article_url=law_article_url,
        sieve_rule_id=sieve_rule_id,
        sieve_class_label=sieve_class_label,
        sieve_result=sieve_result,
        assigned_sectors=assigned_sectors or [],
        sector_source=sector_source,
        check_verdict=check_result.verdict,
        check_reason=check_result.reason,
        check_method=check_result.check_method,
        applicability_status=check_result.applicability_status,
        ksic_boost=ksic_boost,
        ksic_matched_noun=ksic_matched_noun,
        ksic_code=ksic_code,
        full_trace=full_trace,
    )


def run_reverse_check_batch(
    check_results: List[CheckResult],
) -> List[ReverseCheckResult]:
    """CheckResult 목록 → ReverseCheckResult 목록.

    Track A 결과만 있을 때 사용.
    sieve/sector 맥락 없이 check 경로만 역추적.
    """
    results = []
    for cr in check_results:
        trace = build_reverse_trace(
            check_result=cr,
            sieve_result="TRACK_A_DIRECT",  # Track A는 거름망 통과 경로가 다름
            sector_source="track_a",
        )
        results.append(trace)
    return results
