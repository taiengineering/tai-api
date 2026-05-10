"""Family Relation & Constraint Builder — Constraint Graph IR 생성.

핵심: "Constraint는 법적 결론이 아니라 연결 후보다."

family_candidate → constraint_node + constraint_edge.
모든 출력은 CANDIDATE 상태. Rule 생성 금지.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConstraintNode:
    part_id: str
    node_type: str
    family_name: str
    raw_token: str
    canonical_token: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    status: str = "CANDIDATE"
    db_id: str | None = None  # INSERT 후 할당


@dataclass
class ConstraintEdge:
    part_id: str
    relation_type: str
    from_node: ConstraintNode
    to_node: ConstraintNode
    status: str = "CANDIDATE"


# ── Family → Node Type 매핑 ───────────────────────────
# 판단 개입 최소화: registry 기반 기계적 매핑만

FAMILY_TO_NODE_TYPE: dict[str, str] = {
    # ACTION
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
    # OBLIGATION
    "MANDATORY_FAMILY": "OBLIGATION", "PERMISSIVE_FAMILY": "OBLIGATION",
    "PROHIBITION_FAMILY": "OBLIGATION", "MANDATORY_ITEM_FAMILY": "OBLIGATION",
    # DEFINITION
    "DEFINITION_FAMILY": "DEFINITION",
    # FREQUENCY
    "PERIODIC_FAMILY": "FREQUENCY", "ANNUAL_FAMILY": "FREQUENCY",
    "AD_HOC_FAMILY": "FREQUENCY", "QUARTERLY_FAMILY": "FREQUENCY",
    "SEMI_ANNUAL_FAMILY": "FREQUENCY",
    # DEADLINE
    "WITHIN_FAMILY": "DEADLINE", "BY_FAMILY": "DEADLINE",
    "IMMEDIATE_FAMILY": "DEADLINE", "BEFORE_FAMILY": "DEADLINE",
    # CONDITION
    "CONDITIONAL_FAMILY": "CONDITION", "TRIGGER_FAMILY": "CONDITION",
    # UNKNOWN
    "UNKNOWN": "UNKNOWN",
}


# ── 관계 생성 규칙 (문서 2단계) ───────────────────────
# (from_node_type, to_node_type) → relation_type
# 기계적 매핑, 의미 판단 없음

EDGE_RULES: dict[tuple[str, str], str] = {
    ("ACTOR", "ACTION"): "ACTOR_ACTION_RELATION",
    ("ACTION", "TARGET"): "ACTION_TARGET_RELATION",
    ("ACTION", "CONDITION"): "ACTION_CONDITION_RELATION",
    ("ACTION", "FREQUENCY"): "ACTION_FREQUENCY_RELATION",
    ("ACTION", "DEADLINE"): "ACTION_DEADLINE_RELATION",
    ("ACTION", "EXCEPTION"): "ACTION_EXCEPTION_RELATION",
    ("ACTION", "REFERENCE"): "ACTION_REFERENCE_RELATION",
    ("ACTION", "SCOPE"): "ACTION_SCOPE_RELATION",
    ("ACTION", "OBLIGATION"): "ACTION_TRIGGER_RELATION",
    ("ACTOR", "OBLIGATION"): "ACTION_EVIDENCE_RELATION",
}


# ── 메인 빌드 ─────────────────────────────────────────

def build_constraint_graph(
    part_id: str,
    family_rows: list[dict[str, Any]],
) -> tuple[list[ConstraintNode], list[ConstraintEdge]]:
    """family_candidate rows → ConstraintNode + ConstraintEdge.

    모든 출력은 CANDIDATE. Rule 생성 없음. 의미 확정 없음.
    """

    # [1단계] Family → Node 변환
    nodes: list[ConstraintNode] = []
    for row in family_rows:
        family = row.get("family_name", "UNKNOWN")
        node_type = FAMILY_TO_NODE_TYPE.get(family, "UNKNOWN")

        # UNRESOLVED family는 원래 token_type에서 node_type 추론
        if node_type == "UNKNOWN" and family == "UNKNOWN":
            # family_candidate의 status가 UNRESOLVED인 경우
            # raw_token 기반으로 node_type 결정하지 않음 (판단 개입 금지)
            node_type = "UNKNOWN"

        nodes.append(ConstraintNode(
            part_id=part_id,
            node_type=node_type,
            family_name=family,
            raw_token=row.get("raw_token", ""),
            canonical_token=row.get("canonical_token"),
            span_start=row.get("source_span_start"),
            span_end=row.get("source_span_end"),
            status=row.get("status", "CANDIDATE"),
        ))

    # [2~10단계] Edge 생성 (같은 part 내 노드 쌍 연결)
    edges = _build_edges(part_id, nodes)

    return nodes, edges


def _build_edges(
    part_id: str, nodes: list[ConstraintNode],
) -> list[ConstraintEdge]:
    """노드 쌍에서 관계 후보 생성. 기계적 매핑만."""
    edges: list[ConstraintEdge] = []

    # node_type별 그룹화
    by_type: dict[str, list[ConstraintNode]] = {}
    for n in nodes:
        if n.status == "FAIL" or n.node_type == "UNKNOWN":
            continue
        by_type.setdefault(n.node_type, []).append(n)

    # 관계 규칙에 따라 첫 번째 쌍만 연결 (과잉 생성 방지)
    for (from_type, to_type), rel_type in EDGE_RULES.items():
        from_nodes = by_type.get(from_type, [])
        to_nodes = by_type.get(to_type, [])
        if not from_nodes or not to_nodes:
            continue

        fn = from_nodes[0]
        tn = to_nodes[0]
        if fn is tn:
            continue

        edges.append(ConstraintEdge(
            part_id=part_id,
            relation_type=rel_type,
            from_node=fn,
            to_node=tn,
            status="CANDIDATE",
        ))

    return edges


# ── [13단계] Validation ───────────────────────────────

def validate_graph(
    nodes: list[ConstraintNode], edges: list[ConstraintEdge],
) -> list[dict[str, str]]:
    """검증. 문제 발견 시 이슈 반환, 수정하지 않음."""
    issues = []

    for n in nodes:
        # 1. raw_token 존재
        if not n.raw_token:
            issues.append({"type": "ISSUE_NO_RAW_TOKEN", "detail": f"node {n.family_name}"})
            n.status = "FAIL"

    for e in edges:
        # 9. 없는 관계 생성 여부 (from/to가 같은 part인지)
        if e.from_node.part_id != e.to_node.part_id:
            issues.append({"type": "ISSUE_CROSS_PART_RELATION", "detail": f"{e.relation_type}"})
            e.status = "FAIL"

    return issues


# ── DB 저장 ────────────────────────────────────────────

def save_constraint_graph(
    conn,
    nodes: list[ConstraintNode],
    edges: list[ConstraintEdge],
) -> dict[str, int]:
    cur = conn.cursor()
    saved = {"nodes": 0, "edges": 0}

    # 노드 저장 + ID 회수
    node_id_map: dict[int, str] = {}  # python id(node) → db uuid
    for i, n in enumerate(nodes):
        try:
            cur.execute("""
                INSERT INTO constraint_node
                    (part_id, node_type, family_name, raw_token, canonical_token,
                     source_span_start, source_span_end, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text
            """, (
                n.part_id, n.node_type, n.family_name, n.raw_token,
                n.canonical_token, n.span_start, n.span_end, n.status,
            ))
            row = cur.fetchone()
            if row:
                node_id_map[id(n)] = row[0]
                saved["nodes"] += 1
        except Exception as e:
            logger.warning("constraint_node INSERT: %s", e)

    # 엣지 저장
    for e in edges:
        from_id = node_id_map.get(id(e.from_node))
        to_id = node_id_map.get(id(e.to_node))
        if not from_id or not to_id:
            continue
        try:
            cur.execute("""
                INSERT INTO constraint_edge
                    (part_id, relation_type, from_node_id, to_node_id,
                     from_family, to_family, from_token, to_token, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                e.part_id, e.relation_type, from_id, to_id,
                e.from_node.family_name, e.to_node.family_name,
                e.from_node.raw_token, e.to_node.raw_token, e.status,
            ))
            saved["edges"] += 1
        except Exception as e2:
            logger.warning("constraint_edge INSERT: %s", e2)

    conn.commit()
    cur.close()
    return saved
