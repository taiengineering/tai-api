"""Phase 9 — Quality Evaluator (service layer, NOT a new engine).

LEG Obligation + Check EvidenceReport -> quality_status. Pure and deterministic.
Does NOT modify Check or LEG, does NOT re-judge law. It only consumes the Check
EvidenceReport (status_summary / observation_records) and the obligation's own
fields, and maps them to an operational quality status.

Statuses (only 3):
    READY                의무 사용 가능 -> 스케줄 생성 가능
    TRACE_REQUIRED       근거/조치 부족 -> 추적 대상
    CORRECTION_REQUIRED  중복/Claim 오류/법령 연결 오류/데이터 오류 -> 어드민 큐
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

READY = "READY"
TRACE_REQUIRED = "TRACE_REQUIRED"
CORRECTION_REQUIRED = "CORRECTION_REQUIRED"

ALL_STATUSES = (READY, TRACE_REQUIRED, CORRECTION_REQUIRED)


def _result(status: str, reason: str) -> Dict[str, str]:
    return {"quality_status": status, "quality_reason": reason}


def _summary(check_report: Any, kind: str) -> Dict[str, int]:
    ss = (check_report or {}).get("status_summary") or {}
    counts = ss.get(kind) or {}
    return counts if isinstance(counts, dict) else {}


def _obligation_id(obligation: Any) -> Optional[str]:
    if not isinstance(obligation, dict):
        return None
    for k in ("obligation_id", "rule_id", "rule_code"):
        v = obligation.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _law_linked(obligation: Dict[str, Any]) -> bool:
    name = str(obligation.get("law_name") or "").strip()
    article = str(obligation.get("article_no") or obligation.get("law_article") or "").strip()
    return bool(name) and bool(article)


def evaluate_quality(
    obligation: Any,
    check_report: Any,
    *,
    duplicate: bool = False,
) -> Dict[str, str]:
    """Map one (obligation, check_report) pair to a quality status + reason code.

    Priority: DATA_ERROR -> CORRECTION(duplicate/law/claim/out-of-scope)
              -> TRACE(evidence/action insufficient) -> READY.
    """
    # --- data error: malformed inputs ---
    if not isinstance(obligation, dict):
        return _result(CORRECTION_REQUIRED, "DATA_ERROR")
    if (
        not isinstance(check_report, dict)
        or "status_summary" not in check_report
        or "observation_records" not in check_report
    ):
        return _result(CORRECTION_REQUIRED, "DATA_ERROR")

    claim = _summary(check_report, "claim")
    evidence = _summary(check_report, "evidence")
    chain = _summary(check_report, "chain")

    # --- CORRECTION_REQUIRED (관리자 보정 필요) ---
    if duplicate:
        return _result(CORRECTION_REQUIRED, "DUPLICATE_OBLIGATION")
    if not _law_linked(obligation):
        return _result(CORRECTION_REQUIRED, "LAW_LINK_ERROR")
    if claim.get("CLAIM_REF_MISSING", 0) > 0 or claim.get("CLAIM_OUT_OF_SCOPE", 0) > 0:
        return _result(CORRECTION_REQUIRED, "CLAIM_ERROR")
    if evidence.get("EVIDENCE_OUT_OF_SCOPE", 0) > 0 or chain.get("EVIDENCE_CHAIN_OUT_OF_SCOPE", 0) > 0:
        return _result(CORRECTION_REQUIRED, "OUT_OF_SCOPE")

    # --- TRACE_REQUIRED (근거/조치 부족) ---
    if evidence.get("EVIDENCE_NOT_ATTACHED", 0) > 0 or evidence.get("EVIDENCE_REF_MISSING", 0) > 0:
        return _result(TRACE_REQUIRED, "EVIDENCE_INSUFFICIENT")
    if (
        chain.get("EVIDENCE_CHAIN_BROKEN", 0) > 0
        or chain.get("EVIDENCE_CHAIN_NOT_DECLARED", 0) > 0
        or chain.get("EVIDENCE_CHAIN_PRESENT", 0) > 0
    ):
        return _result(TRACE_REQUIRED, "ACTION_INSUFFICIENT")
    if not (check_report.get("observation_records") or []):
        return _result(TRACE_REQUIRED, "EVIDENCE_INSUFFICIENT")

    # --- READY (사용 가능) ---
    return _result(READY, "OK")


def evaluate_batch(
    obligations: List[dict],
    reports_by_obligation: Optional[Dict[str, dict]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate many obligations. Duplicate obligation_id within the batch ->
    CORRECTION_REQUIRED(DUPLICATE_OBLIGATION) for every occurrence.
    """
    reports_by_obligation = reports_by_obligation or {}
    ids: List[Optional[str]] = [_obligation_id(o) for o in obligations]
    seen: Dict[str, int] = {}
    for oid in ids:
        if oid is not None:
            seen[oid] = seen.get(oid, 0) + 1

    out: List[Dict[str, Any]] = []
    for obligation, oid in zip(obligations, ids):
        is_dup = oid is not None and seen.get(oid, 0) > 1
        report = reports_by_obligation.get(oid) if oid is not None else None
        res = evaluate_quality(obligation, report, duplicate=is_dup)
        out.append({
            "obligation_id": oid,
            "quality_status": res["quality_status"],
            "quality_reason": res["quality_reason"],
            "check_report_id": (report or {}).get("report_id") if isinstance(report, dict) else None,
        })
    return out


def is_schedulable(quality_status: Optional[str]) -> bool:
    """Only READY obligations may generate schedules (Phase 9 gate)."""
    return quality_status == READY
