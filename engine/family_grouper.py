"""Family Grouping Engine — 정규화 후보를 Family 단위로 그룹화.

Family는 의미가 아니라 "계열 후보"다.
1토큰 → 여러 Family 허용 (AMBIGUOUS).
Family 간 관계도 후보일 뿐 확정 아님.
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
    status: str = "CANDIDATE"
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


# ── Family 관계 유형 ──────────────────────────────────

RELATION_PAIRS = {
    # (from_type, to_type) → relation_type
    ("ACTION", "OBLIGATION"): "ACTION_OBLIGATION_FAMILY",
    ("ACTION", "FREQUENCY"): "ACTION_FREQUENCY_FAMILY",
    ("ACTION", "DEADLINE"): "ACTION_DEADLINE_FAMILY",
    ("ACTION", "CONDITION"): "ACTION_CONDITION_FAMILY",
    ("ACTION", "EXCEPTION"): "ACTION_EXCEPTION_FAMILY",
    ("ACTOR", "ACTION"): "ACTOR_ACTION_FAMILY",
    ("ACTOR", "OBLIGATION"): "ACTOR_OBLIGATION_FAMILY",
    ("ACTION", "TARGET"): "ACTION_TARGET_FAMILY",
}

# normalized의 family → 어떤 카테고리인지
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


# ── Registry 로드 (Multi-Family) ─────────────────────

def load_multi_registry(conn) -> dict[str, list[str]]:
    """canonical_token → [family1, family2, ...] (다중 Family 허용)."""
    cur = conn.cursor()
    cur.execute("SELECT canonical_token, family FROM token_family_registry ORDER BY canonical_token")
    registry: dict[str, list[str]] = {}
    for canonical, family in cur.fetchall():
        registry.setdefault(canonical, []).append(family)
    cur.close()
    return registry


# ── 메인 그룹화 ───────────────────────────────────────

def group_families(
    part_id: str,
    normalized_rows: list[dict[str, Any]],
    registry: dict[str, list[str]],
) -> tuple[list[FamilyCandidate], list[FamilyRelation]]:
    """정규화 결과 → Family Candidate + Family Relation 생성."""

    candidates: list[FamilyCandidate] = []

    for row in normalized_rows:
        n_id = row.get("id")
        raw = row.get("raw_token", "")
        canonical = row.get("canonical_token", "")
        span_s = row.get("source_span_start")
        span_e = row.get("source_span_end")

        families = registry.get(canonical, [])

        if not families:
            # Registry에 없음 → UNRESOLVED
            candidates.append(FamilyCandidate(
                part_id=part_id, normalized_id=n_id,
                family_name="UNKNOWN", raw_token=raw,
                canonical_token=canonical,
                span_start=span_s, span_end=span_e,
                status="UNRESOLVED",
            ))
        elif len(families) == 1:
            # 단일 Family
            candidates.append(FamilyCandidate(
                part_id=part_id, normalized_id=n_id,
                family_name=families[0], raw_token=raw,
                canonical_token=canonical,
                span_start=span_s, span_end=span_e,
                status="CANDIDATE",
            ))
        else:
            # Multi-Family → AMBIGUOUS
            for fam in families:
                candidates.append(FamilyCandidate(
                    part_id=part_id, normalized_id=n_id,
                    family_name=fam, raw_token=raw,
                    canonical_token=canonical,
                    span_start=span_s, span_end=span_e,
                    status="AMBIGUOUS",
                ))

    # Family Relation 생성 (같은 part_id 내 Family 쌍)
    relations = _build_relations(part_id, candidates)

    return candidates, relations


def _build_relations(
    part_id: str, candidates: list[FamilyCandidate],
) -> list[FamilyRelation]:
    """같은 part_id 내 Family 쌍 → 관계 후보 생성."""
    relations: list[FamilyRelation] = []

    # Family별 분류
    by_category: dict[str, list[FamilyCandidate]] = {}
    for c in candidates:
        if c.family_name == "UNKNOWN":
            continue
        cat = FAMILY_CATEGORY.get(c.family_name)
        if cat:
            by_category.setdefault(cat, []).append(c)

    # 관계 쌍 매칭
    for (from_cat, to_cat), rel_type in RELATION_PAIRS.items():
        from_list = by_category.get(from_cat, [])
        to_list = by_category.get(to_cat, [])
        if not from_list or not to_list:
            continue

        # 첫 번째 쌍만 (과잉 생성 방지)
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
