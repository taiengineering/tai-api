"""D-004A: Track A Check Adapter 서비스

facility_applicability 테이블에서 facility_id 기준 rows를 읽어
CheckResult로 변환.

금지:
  evaluate_single_factory 수정
  evaluate_draft_for_facility 수정
  SemanticClause → facility_applicability_eval 연결 시도
  facility_applicability 테이블 수정
"""
from __future__ import annotations

import logging
from typing import List, Optional

from schemas.check_input_schema import CheckResult, CheckVerdict

log = logging.getLogger(__name__)


def _status_to_verdict(status: str) -> CheckVerdict:
    """applicability_status → CheckVerdict 변환."""
    if status == "MATCH_CANDIDATE":
        return CheckVerdict.APPLICABLE
    if status == "POSSIBLE_CANDIDATE":
        return CheckVerdict.POSSIBLE
    return CheckVerdict.UNKNOWN


def _status_to_reason(status: str, match_details: Optional[dict]) -> str:
    """applicability_status + match_details → 판정 근거 문자열."""
    checks = (match_details or {}).get("checks", "?")
    if status == "MATCH_CANDIDATE":
        return f"Track A MATCH_CANDIDATE: {checks}개 조건 매칭"
    if status == "POSSIBLE_CANDIDATE":
        return f"Track A POSSIBLE_CANDIDATE: {checks}개 조건 일부 매칭"
    return f"Track A {status}: 판단 불가"


def load_track_a_results(
    supabase,
    facility_id: str,
    status_filter: Optional[List[str]] = None,
) -> List[CheckResult]:
    """facility_applicability에서 해당 facility_id의 결과 읽기.

    Args:
        facility_id: factories.id
        status_filter: [’MATCH_CANDIDATE’, ’POSSIBLE_CANDIDATE’] 등. None이면 전체.

    가장 중요: 이 함수는 읽기 전용.
    evaluate_single_factory / evaluate_draft_for_facility 호출 없음.
    """
    try:
        q = (
            supabase.table("facility_applicability")
            .select("id, factory_id, draft_id, applicability_status, match_details")
            .eq("factory_id", facility_id)
        )
        if status_filter:
            q = q.in_("applicability_status", status_filter)

        res = q.execute()
        rows = res.data or []
        if not rows:
            return []

        # draft_id 목록로 executable_draft → law_article → law_master 조회
        draft_ids = [str(r["draft_id"]) for r in rows if r.get("draft_id")]
        drafts_res = (
            supabase.table("executable_draft")
            .select("id, article_id")
            .in_("id", draft_ids)
            .execute()
        )
        draft_map = {str(d["id"]): d for d in (drafts_res.data or [])}

        article_ids = list({str(d["article_id"]) for d in draft_map.values() if d.get("article_id")})
        if article_ids:
            articles_res = (
                supabase.table("law_article")
                .select("id, law_id, article_no, article_title")
                .in_("id", article_ids)
                .execute()
            )
            article_map = {str(a["id"]): a for a in (articles_res.data or [])}

            law_ids = list({str(a["law_id"]) for a in article_map.values() if a.get("law_id")})
            laws_res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("id", law_ids)
                .execute()
            )
            law_map = {str(lm["id"]): lm for lm in (laws_res.data or [])}
        else:
            article_map = {}
            law_map = {}

        # 조립
        results: List[CheckResult] = []
        for r in rows:
            status = r.get("applicability_status", "UNKNOWN")
            match_details = r.get("match_details")
            draft = draft_map.get(str(r.get("draft_id") or ""))
            article = article_map.get(str((draft or {}).get("article_id") or "")) if draft else None
            law = law_map.get(str((article or {}).get("law_id") or "")) if article else None

            results.append(CheckResult(
                applicability_id=str(r["id"]),
                facility_id=str(r["factory_id"]),
                draft_id=str(r["draft_id"]),
                applicability_status=status,
                match_details=match_details,
                article_id=str(article["id"]) if article else None,
                article_no=str(article.get("article_no") or "") if article else None,
                article_title=str(article.get("article_title") or "") if article else None,
                law_name=str(law.get("law_name") or "") if law else None,
                verdict=_status_to_verdict(status),
                reason=_status_to_reason(status, match_details),
                check_method="track_a_facility_applicability",
            ))
        return results

    except Exception as exc:
        log.error("load_track_a_results 오류: %s", exc)
        return []
