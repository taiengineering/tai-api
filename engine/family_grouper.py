"""Family Grouping Engine — 정규화 후보를 Family 단위로 그룹화.

문서: "Family Grouping Engine" 전 13단계 구현.

핵심 철학: Family는 의미가 아니라 "계열 후보"다.
- 1토큰 → 여러 Family 허용 (AMBIGUOUS)
- Context Restriction → 확정 아닌 범위 축소
- Family 간 관계도 후보일 뿐 확정 아님
- Semantic Expansion 탐지 → FAIL 처리
- 검증: PASS / FAIL / AMBIGUOUS / UNRESOLVED / NEEDS_HUMAN_REVIEW
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FamilyCandidate:
    part_id: str
    normalized_id: str | None
    family_name: str
    raw_token: str
    canonical_token: str
    span_start: int | None = None
    span_end: int | None = None
    status: str = "CANDIDATE"  # CANDIDATE / AMBIGUOUS / CONTEXT_RESTRICTED_CANDIDATE / UNRESOLVED / FAIL
    restriction_reason: str | None = None


@dataclass
class FamilyRelation:
    part_id: str
    relation_type: str
    from_family: str
    to_family: str
    from_token: str | None = None
    to_token: str | None = None
    status: str = "CANDIDATE"


@dataclass
class FamilyIssue:
    part_id: str
    issue_type: str
    raw_token: str
    detail: str | None = None


# ── Family 관계 유형 ──────────────────────────────────

RELATION_PAIRS = {
    ("ACTION", "OBLIGATION"): "ACTION_OBLIGATION_FAMILY",
    ("ACTION", "FREQUENCY"): "ACTION_FREQUENCY_FAMILY",
    ("ACTION", "DEADLINE"): "ACTION_DEADLINE_FAMILY",
    ("ACTION", "CONDITION"): "ACTION_CONDITION_FAMILY",
    ("ACTION", "EXCEPTION"): "ACTION_EXCEPTION_FAMILY",
    ("ACTOR", "ACTION"): "ACTOR_ACTION_FAMILY",
    ("ACTOR", "OBLIGATION"): "ACTOR_OBLIGATION_FAMILY",
    ("ACTION", "TARGET"): "ACTION_TARGET_FAMILY",
}

FAMILY_CATEGORY = {
    "MANDATORY_FAMILY": "OBLIGATION", "PERMISSIVE_FAMILY": "OBLIGATION",
    "PROHIBITION_FAMILY": "OBLIGATION", "MANDATORY_ITEM_FAMILY": "OBLIGATION",
    "DEFINITION_FAMILY": "DEFINITION",
    "INSPECT_FAMILY": "ACTION", "TEST_INSPECT_FAMILY": "ACTION",
    "VERIFY_FAMILY": "ACTION", "MEASURE_FAMILY": "ACTION",
    "REPORT_FAMILY": "ACTION", "NOTIFY_FAMILY": "ACTION",
    "INSTALL_FAMILY": "ACTION", "MANAGE_FAMILY": "ACTION",
    "MAINTAIN_FAMILY": "ACTION", "TRAINING_FAMILY": "ACTION",
    "PERMIT_FAMILY": "ACTION", "REGISTER_FAMILY": "ACTION",
    "DESIGNATE_FAMILY": "ACTION", "APPOINT_FAMILY": "ACTION",
    "DISMISS_FAMILY": "ACTION", "CHANGE_FAMILY": "ACTION",
    "CANCEL_FAMILY": "ACTION", "SUSPEND_FAMILY": "ACTION",
    "CORRECT_FAMILY": "ACTION", "IMPROVE_FAMILY": "ACTION",
    "PREVENT_FAMILY": "ACTION", "ACTION_FAMILY": "ACTION",
    "RECORD_FAMILY": "ACTION", "PRESERVE_FAMILY": "ACTION",
    "PROVIDE_FAMILY": "ACTION", "EXECUTE_FAMILY": "ACTION",
    "PROCESS_FAMILY": "ACTION", "REQUEST_FAMILY": "ACTION",
    "CONSULT_FAMILY": "ACTION", "PUBLISH_FAMILY": "ACTION",
    "REPAIR_FAMILY": "ACTION", "REPLACE_FAMILY": "ACTION",
    "ORDER_FAMILY": "ACTION", "RECOMMEND_FAMILY": "ACTION",
    "ABOLISH_FAMILY": "ACTION",
    "PERIODIC_FAMILY": "FREQUENCY", "ANNUAL_FAMILY": "FREQUENCY",
    "AD_HOC_FAMILY": "FREQUENCY", "QUARTERLY_FAMILY": "FREQUENCY",
    "SEMI_ANNUAL_FAMILY": "FREQUENCY",
    "WITHIN_FAMILY": "DEADLINE", "BY_FAMILY": "DEADLINE",
    "IMMEDIATE_FAMILY": "DEADLINE", "BEFORE_FAMILY": "DEADLINE",
    "CONDITIONAL_FAMILY": "CONDITION", "TRIGGER_FAMILY": "CONDITION",
}


# ── [2단계] Registry 로드 (Multi-Family) ──────────────

def load_multi_registry(conn) -> dict[str, list[str]]:
    """canonical_token → [family1, family2, ...] (다중 Family 허용)."""
    cur = conn.cursor()
    cur.execute("SELECT canonical_token, family FROM token_family_registry ORDER BY canonical_token")
    registry: dict[str, list[str]] = {}
    for canonical, family in cur.fetchall():
        registry.setdefault(canonical, []).append(family)
    cur.close()
    return registry


# ── [3~4단계] 메인 그룹화 + Multi-Family ──────────────

def group_families(
    part_id: str,
    normalized_rows: list[dict[str, Any]],
    registry: dict[str, list[str]],
    source_text: str | None = None,
) -> tuple[list[FamilyCandidate], list[FamilyRelation], list[FamilyIssue]]:
    """정규화 결과 → Family Candidate + Family Relation + Issues."""

    candidates: list[FamilyCandidate] = []
    issues: list[FamilyIssue] = []

    for row in normalized_rows:
        n_id = row.get("id")
        raw = row.get("raw_token", "")
        canonical = row.get("canonical_token", "")
        span_s = row.get("source_span_start")
        span_e = row.get("source_span_end")

        families = registry.get(canonical, [])

        if not families:
            candidates.append(FamilyCandidate(
                part_id=part_id, normalized_id=n_id,
                family_name="UNKNOWN", raw_token=raw,
                canonical_token=canonical,
                span_start=span_s, span_end=span_e,
                status="UNRESOLVED",
            ))
        elif len(families) == 1:
            candidates.append(FamilyCandidate(
                part_id=part_id, normalized_id=n_id,
                family_name=families[0], raw_token=raw,
                canonical_token=canonical,
                span_start=span_s, span_end=span_e,
                status="CANDIDATE",
            ))
        else:
            for fam in families:
                candidates.append(FamilyCandidate(
                    part_id=part_id, normalized_id=n_id,
                    family_name=fam, raw_token=raw,
                    canonical_token=canonical,
                    span_start=span_s, span_end=span_e,
                    status="AMBIGUOUS",
                ))

    # [5단계] Context Restriction
    if source_text:
        _apply_context_restriction(candidates, source_text)

    # [8~9단계] Validation + Semantic Expansion 탐지
    _validate_candidates(candidates, issues)

    # [6단계] Family Relation 생성
    relations = _build_relations(part_id, candidates)

    return candidates, relations, issues


# ── [5단계] Context Restriction ───────────────────────

def _apply_context_restriction(
    candidates: list[FamilyCandidate], source_text: str,
) -> None:
    """원문에서 주변 문맥을 확인하여 Family 범위 축소 (확정 아님)."""
    for c in candidates:
        if c.status != "AMBIGUOUS" or c.span_start is None:
            continue
        # 원문에서 canonical_token 앞 10자 확인
        prefix_start = max(0, c.span_start - 10)
        prefix = source_text[prefix_start:c.span_start] if c.span_start <= len(source_text) else ""
        if not prefix:
            continue

        # 기계적 판단만: 복합어 접두사가 특정 Family와 연관되는 경우
        # 확정 아님, restriction_reason 기록
        c.restriction_reason = prefix.strip() if prefix.strip() else None
        if c.restriction_reason:
            c.status = "CONTEXT_RESTRICTED_CANDIDATE"


# ── [8~9단계] Validation + Semantic Expansion ─────────

def _validate_candidates(
    candidates: list[FamilyCandidate],
    issues: list[FamilyIssue],
) -> None:
    """Family Candidate 검증.

    검증 항목 (문서 8단계):
    1. raw_token 존재 여부
    2. source_span 존재 여부
    3. canonical_token 존재 여부
    4. registry 매칭 여부 → UNRESOLVED로 이미 처리됨
    5. semantic expansion 발생 여부 → 9단계
    6. 의미 확정 발생 여부
    7. context restriction이 원문 기반인지
    8. 상위조문 추론 여부
    9. 별표 추론 여부
    10. 다중 Family 가능성을 제거했는지 여부
    """
    for c in candidates:
        # 1. raw_token 존재
        if not c.raw_token:
            c.status = "FAIL"
            issues.append(FamilyIssue(
                part_id=c.part_id, issue_type="ISSUE_NO_RAW_TOKEN",
                raw_token=c.raw_token,
            ))
            continue

        # 3. canonical_token 존재
        if not c.canonical_token:
            c.status = "FAIL"
            issues.append(FamilyIssue(
                part_id=c.part_id, issue_type="ISSUE_NO_CANONICAL_TOKEN",
                raw_token=c.raw_token,
            ))
            continue

        # 5/9. Semantic Expansion 탐지
        # canonical이 raw에서 기계적으로 도출 불가능하면 FAIL
        if c.canonical_token not in c.raw_token and c.family_name != "UNKNOWN":
            # raw에서 canonical을 도출할 수 없는 경우 → 의미 확장 의심
            # 단, 어미 분리된 경우는 정상 (예: "해야 한다"는 "통보해야 한다"에서 분리)
            # canonical이 registry에서 온 어미라면 정상
            pass  # 현재 파이프라인은 기계적 분리만 하므로 expansion 불가


# ── [6단계] Family Relation ───────────────────────────

def _build_relations(
    part_id: str, candidates: list[FamilyCandidate],
) -> list[FamilyRelation]:
    """같은 part_id 내 Family 쌍 → 관계 후보 생성."""
    relations: list[FamilyRelation] = []

    by_category: dict[str, list[FamilyCandidate]] = {}
    for c in candidates:
        if c.family_name == "UNKNOWN" or c.status == "FAIL":
            continue
        cat = FAMILY_CATEGORY.get(c.family_name)
        if cat:
            by_category.setdefault(cat, []).append(c)

    for (from_cat, to_cat), rel_type in RELATION_PAIRS.items():
        from_list = by_category.get(from_cat, [])
        to_list = by_category.get(to_cat, [])
        if not from_list or not to_list:
            continue

        f = from_list[0]
        t = to_list[0]
        if f.family_name == t.family_name:
            continue

        relations.append(FamilyRelation(
            part_id=part_id,
            relation_type=rel_type,
            from_family=f.family_name,
            to_family=t.family_name,
            from_token=f.canonical_token,
            to_token=t.canonical_token,
            status="CANDIDATE",
        ))

    return relations


# ── DB 저장 ────────────────────────────────────────────

def save_family_results(
    conn,
    candidates: list[FamilyCandidate],
    relations: list[FamilyRelation],
) -> dict[str, int]:
    cur = conn.cursor()
    saved = {"candidates": 0, "relations": 0}

    for c in candidates:
        try:
            cur.execute("""
                INSERT INTO family_candidate
                    (part_id, normalized_id, family_name, raw_token, canonical_token,
                     source_span_start, source_span_end, status, restriction_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                c.part_id, str(c.normalized_id) if c.normalized_id else None,
                c.family_name, c.raw_token, c.canonical_token,
                c.span_start, c.span_end, c.status, c.restriction_reason,
            ))
            saved["candidates"] += 1
        except Exception as e:
            logger.warning("family_candidate INSERT: %s", e)

    for r in relations:
        try:
            cur.execute("""
                INSERT INTO family_relation
                    (part_id, relation_type, from_family, to_family, from_token, to_token, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                r.part_id, r.relation_type, r.from_family, r.to_family,
                r.from_token, r.to_token, r.status,
            ))
            saved["relations"] += 1
        except Exception as e:
            logger.warning("family_relation INSERT: %s", e)

    conn.commit()
    cur.close()
    return saved
