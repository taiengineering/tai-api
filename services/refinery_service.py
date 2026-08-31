"""D-007: Refinery Service

중복 제거 + 의무 문장 생성.
DB 쓰기 없음, 네트워크 없음 — 순수 변환.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from schemas.reverse_check_schema import ReverseCheckResult
from schemas.stored_diagnosis_schema import ObligationItem, StoredDiagnosisResult
from services.time import now_kst, serialize_external_utc


def generate_obligation_text(trace: ReverseCheckResult) -> str:
    """역추적 결과 → 사람이 읽는 의무 문장.

    형식: [법령명] 제{article_no}조({article_title}) — {check_verdict} 수준 적용
    executor_text가 있으면 주체 포함.
    """
    parts = []

    law = trace.law_name or ""
    article = trace.article_no or ""
    title = trace.article_title or ""

    if law:
        parts.append(f"[{law}]")
    if article:
        art_str = f"제{article}조"
        if title:
            art_str += f"({title})"
        parts.append(art_str)

    executor = trace.executor_text
    verdict = trace.check_verdict or ""
    if verdict == "APPLICABLE":
        level = "적용"
    elif verdict == "POSSIBLE":
        level = "잠정 적용"
    else:
        level = "검토 필요"

    if executor:
        parts.append(f"— {executor}의 의무 ({level})")
    else:
        parts.append(f"— 의무사항 ({level})")

    return " ".join(parts) if parts else "의무사항"


def deduplicate_obligations(
    traces: List[ReverseCheckResult],
) -> List[ReverseCheckResult]:
    """중복 제거: law_name + article_no 기준 첫 번째만 유지.

    중복 시 이유는 로그로 기록 (DROP_DUPLICATE).
    """
    seen: Dict[str, bool] = {}
    result: List[ReverseCheckResult] = []
    for t in traces:
        key = f"{t.law_name or ''}::{t.article_no or ''}::{t.check_verdict or ''}"
        if key in seen:
            continue
        seen[key] = True
        result.append(t)
    return result


def build_stored_diagnosis_result(
    traces: List[ReverseCheckResult],
    facility_id: str,
    sector: Optional[str] = None,
    pipeline_stages: Optional[Dict[str, Any]] = None,
) -> StoredDiagnosisResult:
    """ReverseCheckResult 목록 → StoredDiagnosisResult.

    순서:
    1) 중복 제거
    2) 의무 문장 생성
    3) ObligationItem 조립
    """
    before_dedup = len(traces)
    deduped = deduplicate_obligations(traces)
    after_dedup = len(deduped)

    obligations: List[ObligationItem] = []
    for t in deduped:
        text = generate_obligation_text(t)
        obligations.append(ObligationItem(
            obligation_id=t.clause_id or str(uuid.uuid4()),
            law_name=t.law_name,
            article_no=t.article_no,
            article_title=t.article_title,
            obligation_text=text,
            check_verdict=t.check_verdict,
            check_method=t.check_method or "track_a_facility_applicability",
            law_article_url=t.law_article_url,
            trace=t,
        ))

    return StoredDiagnosisResult(
        facility_id=facility_id,
        sector=sector,
        obligations=obligations,
        total_count=after_dedup,
        before_dedup=before_dedup,
        after_dedup=after_dedup,
        generated_at=serialize_external_utc(now_kst()),
        pipeline_version="WO-D-007-v1",
        pipeline_stages=pipeline_stages or {},
    )
