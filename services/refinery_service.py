"""D-007: Refinery Service

중복 제거 + 의무 문장 생성.

금지:
  emit_stored_diagnosis_result 삭제
  assemble_refinery_result 삭제
  기존 Track A 결과 제거
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from schemas.check_input_schema import CheckResult
from schemas.reverse_check_schema import ReverseCheckResult
from schemas.stored_diagnosis_schema import ObligationItem, StoredDiagnosisResult


def generate_obligation_text(trace: ReverseCheckResult) -> str:
    """의무 문장 생성.

    형식: [법령명] 제{article_no}조({article_title}) — {verdict} 의무
    executor_text가 있으면 포함.
    """
    law_part = trace.law_name or "(법령 미확인)"
    art_part = f"제{trace.article_no}조" if trace.article_no else ""
    title_part = f"({trace.article_title})" if trace.article_title else ""
    verdict_label = {
        "APPLICABLE": "해당",
        "POSSIBLE": "해당 가능성",
        "UNKNOWN": "판단 보류",
    }.get(trace.check_verdict or "", "확인 필요")

    if trace.executor_text:
        return f"[{law_part}] {art_part}{title_part} — {trace.executor_text}는 {verdict_label} 의무입니다."
    return f"[{law_part}] {art_part}{title_part} — {verdict_label} 의무입니다."


def deduplicate_obligations(
    traces: List[ReverseCheckResult],
) -> Tuple[List[ReverseCheckResult], int]:
    """중복 제거.

    기준: (law_name, article_no) 조합 중복 시 check_verdict 우선순위 높은 것 유지.
    APPLICABLE > POSSIBLE > UNKNOWN

    Returns:
        (deduplicated_list, removed_count)
    """
    priority = {"APPLICABLE": 0, "POSSIBLE": 1, "UNKNOWN": 2}
    seen: dict = {}  # key=(law_name, article_no) → trace

    for trace in traces:
        key = (trace.law_name or "", trace.article_no or "")
        if key not in seen:
            seen[key] = trace
        else:
            existing_p = priority.get(seen[key].check_verdict or "", 99)
            new_p = priority.get(trace.check_verdict or "", 99)
            if new_p < existing_p:  # 새것이 우선순위 높으면 교체
                seen[key] = trace

    deduped = list(seen.values())
    removed = len(traces) - len(deduped)
    return deduped, removed


def build_stored_diagnosis_result(
    facility_id: str,
    traces: List[ReverseCheckResult],
) -> StoredDiagnosisResult:
    """ReverseCheckResult 목록 → StoredDiagnosisResult.

    기존 emit_stored_diagnosis_result / assemble_refinery_result 삭제 금지.
    이 함수는 관찰 파이프라인 전용 병행 경로.
    """
    before_count = len(traces)
    deduped, removed = deduplicate_obligations(traces)

    items: List[ObligationItem] = []
    for trace in deduped:
        text = generate_obligation_text(trace)
        items.append(ObligationItem(
            obligation_id=trace.clause_id or str(uuid.uuid4()),
            law_name=trace.law_name,
            article_no=trace.article_no,
            article_title=trace.article_title,
            obligation_text=text,
            check_verdict=trace.check_verdict,
            applicability_status=trace.applicability_status,
            law_article_url=trace.law_article_url,
            trace=trace,
        ))

    return StoredDiagnosisResult(
        facility_id=facility_id,
        obligations=items,
        total_count=len(items),
        dedup_removed=removed,
        generated_at=datetime.now(timezone.utc),
        pipeline_version="WO-D-007-v1",
    ), before_count
