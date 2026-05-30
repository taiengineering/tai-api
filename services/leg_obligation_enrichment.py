"""
services/leg_obligation_enrichment.py — LEG Obligation Enrichment Layer v1

역할:
- obligation별 6하원칙 필드 확인
- 부족한 필드 표시 (missing_fields)
- 부모법령 역추적으로 조건 보강 가능 여부 표시
- usable_for_evaluation 판정
- applicable / review_required 분리

원칙:
- 조건 없는 rule을 applicable 처리 금지
- 하드코딩으로 업종/인원 조건 주입 금지
- legal_format.py 수정 없음
- legal_runtime.py 핵심 평가로직 수정 없음
- engine 재작성 없음
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.leg_parent_trace_resolver import batch_resolve_numeric_flags


# ── 6하원칙 필드 정의 ─────────────────────────────────

REQUIRED_FIELDS = {
    "who": "의무 주체",
    "when": "이행 시점/주기",
    "what": "해야 할 의무",
    "condition_code": "기계 판독 조건",
}

OPTIONAL_FIELDS = {
    "where": "적용 장소/대상",
    "how": "이행 방법",
    "why": "법적 근거/목적",
    "condition_value": "조건 기준값",
    "condition_source": "조건 출처",
}


def _extract_who(ob: Dict[str, Any]) -> str:
    """obligation에서 who 추출."""
    ex = ob.get("executor") or {}
    return (
        ex.get("appointment_target")
        or ex.get("type_label")
        or ex.get("type_code")
        or ""
    ).strip()


def _extract_when(ob: Dict[str, Any]) -> str:
    """obligation에서 when 추출."""
    si = ob.get("schedule_info") or {}
    label = (si.get("cycle_label") or "").strip()
    if label:
        return label
    unit = (si.get("cycle_unit") or "").strip()
    val = si.get("cycle_int") or 0
    if unit and val:
        return f"{val} {unit}".strip()
    return ""


def _extract_what(ob: Dict[str, Any]) -> str:
    """obligation에서 what 추출."""
    return (ob.get("title") or ob.get("description") or "").strip()


def _extract_condition(ob: Dict[str, Any]) -> str:
    """obligation에서 condition_code 추출."""
    ev = ob.get("evidence") or {}
    return (ev.get("condition_code") or "").strip()


def _check_missing_fields(ob: Dict[str, Any]) -> List[str]:
    """누락된 6하원칙 필드 목록."""
    missing = []
    if not _extract_who(ob):
        missing.append("who")
    if not _extract_when(ob):
        missing.append("when")
    if not _extract_what(ob):
        missing.append("what")
    if not _extract_condition(ob):
        missing.append("condition_code")
    return missing


# ── Enrichment 메인 ───────────────────────────────────

def enrich(
    obligations: List[Dict[str, Any]],
    supabase,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    obligation 목록에 6하원칙 보강 + 판정 가능 여부 표시.

    Args:
        obligations: adapt()가 반환한 obligations 리스트
        supabase: Supabase 클라이언트
        context: facility_context (선택)

    Returns:
        {
            "applicable": [...],
            "review_required": [...],
            "not_applicable": [...],
            "enrichment_stats": {...},
        }
    """
    if not obligations:
        return {
            "applicable": [],
            "review_required": [],
            "not_applicable": [],
            "enrichment_stats": _empty_stats(),
        }

    # Step 1: 부모 추적 — rule_candidate.has_numeric 플래그 배치 조회
    law_article_pairs = []
    for ob in obligations:
        law_name = (ob.get("law_name") or "").strip()
        law_article = (ob.get("law_article") or "").strip()
        if law_name:
            law_article_pairs.append((law_name, law_article))

    numeric_flags = batch_resolve_numeric_flags(supabase, law_article_pairs)

    # Step 2: 각 obligation에 enrichment 적용
    applicable = []
    review_required = []
    not_applicable_out = []

    stats = {
        "total": len(obligations),
        "complete": 0,
        "partial": 0,
        "catalog_only": 0,
        "usable_true": 0,
        "usable_false": 0,
        "missing_who": 0,
        "missing_when": 0,
        "missing_what": 0,
        "missing_condition": 0,
    }

    for ob in obligations:
        missing = _check_missing_fields(ob)

        # 부모 추적 결과
        law_name = (ob.get("law_name") or "").strip()
        law_article = (ob.get("law_article") or "").strip()
        key = (law_name, law_article)
        needs_numeric = numeric_flags.get(key)

        # usable_for_evaluation 판정
        has_condition = "condition_code" not in missing
        if has_condition:
            # 조건 있음 → 평가 가능
            usable = True
        elif needs_numeric is True:
            # 조건 없지만 rule_candidate에 수치 조건이 있어야 함 → 평가 불가
            usable = False
        elif needs_numeric is False:
            # 조건 없고, rule_candidate에도 수치 조건 없음 → 조건 불필요, 평가 가능
            usable = True
        else:
            # 역추적 실패 (needs_numeric=None) → 평가 불가
            usable = False

        # completeness 분류
        if len(missing) == 0:
            completeness = "COMPLETE"
            stats["complete"] += 1
        elif "what" not in missing:
            completeness = "PARTIAL"
            stats["partial"] += 1
        else:
            completeness = "CATALOG_ONLY"
            stats["catalog_only"] += 1

        # 통계
        if usable:
            stats["usable_true"] += 1
        else:
            stats["usable_false"] += 1
        for field in missing:
            stats_key = f"missing_{field}"
            if stats_key in stats:
                stats[stats_key] += 1

        # enrichment 필드 추가
        ob["enrichment"] = {
            "usable_for_evaluation": usable,
            "completeness": completeness,
            "missing_fields": missing,
            "needs_numeric_condition": needs_numeric,
            "condition_confidence": "HIGH" if has_condition else (
                "MEDIUM" if needs_numeric is False else "LOW"
            ),
        }

        # 분리
        if usable:
            applicable.append(ob)
        else:
            review_required.append(ob)

    return {
        "applicable": applicable,
        "review_required": review_required,
        "not_applicable": not_applicable_out,
        "enrichment_stats": stats,
    }


def _empty_stats() -> Dict[str, int]:
    return {
        "total": 0,
        "complete": 0,
        "partial": 0,
        "catalog_only": 0,
        "usable_true": 0,
        "usable_false": 0,
        "missing_who": 0,
        "missing_when": 0,
        "missing_what": 0,
        "missing_condition": 0,
    }
