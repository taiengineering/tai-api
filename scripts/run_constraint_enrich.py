"""Constraint Graph Enrichment — UNKNOWN 노드 타입 복원 + 누락 Edge 생성.

프롬프트 "Family Relation & Constraint Builder" 실행.

원칙:
  - Family Candidate 수정 금지 (1단계)
  - 증거 기반만 사용: evidence_token.token_type (Stage 1 정규식 결과)
  - 의미 추론/확정 금지
  - UNKNOWN 유지 원칙 (증거 없으면 UNKNOWN 유지)
  - 모든 출력 CANDIDATE 상태
  - Rule 생성 금지

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_constraint_enrich.py
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# 매핑 설정
# ════════════════════════════════════════════════════════════

# token_type → node_type 매핑
# 조건: (1) Stage 1 정규식으로 결정된 증거 (2) check constraint 허용값
# 허용 node_type: ACTION, ACTOR, TARGET, SCOPE, CONDITION, TRIGGER,
#   FREQUENCY, DEADLINE, EVIDENCE, EXCEPTION, REFERENCE,
#   OBLIGATION, DEFINITION, DELEGATION, UNKNOWN

TOKEN_TYPE_TO_NODE_TYPE = {
    "ACTOR_TOKEN":      "ACTOR",       # 주체 표현 → ACTOR
    "TARGET_TOKEN":     "TARGET",      # 대상 표현 → TARGET
    "REFERENCE_TOKEN":  "REFERENCE",   # 참조 표현 → REFERENCE
    "EXCEPTION_TOKEN":  "EXCEPTION",   # 예외 표현 → EXCEPTION
    "ATTACHMENT_TOKEN": "EVIDENCE",    # 별표/서식 → EVIDENCE
    "CONDITION_TOKEN":  "CONDITION",   # 조건 표현 → CONDITION
    "DELEGATION_TOKEN": "DELEGATION",  # 위임 표현 → DELEGATION
    "DEFINITION_TOKEN": "DEFINITION",  # 정의 표현 → DEFINITION
    "OBLIGATION_TOKEN": "OBLIGATION",  # 의무 표현 → OBLIGATION
    "DEADLINE_TOKEN":   "DEADLINE",    # 기한 표현 → DEADLINE
    "FREQUENCY_TOKEN":  "FREQUENCY",   # 주기 표현 → FREQUENCY
    # AUTHORITY_TOKEN → UNKNOWN (check constraint에 AUTHORITY 없음)
    # PROHIBITION_TOKEN → UNKNOWN (OBLIGATION과 혼용되어 모호)
}

# Edge 생성 규칙 (프롬프트 2단계)
# (from_node_type, to_node_type) → relation_type
# 한 part 내에서 첫 번째 쌍만 연결 (과잉 생성 방지)
EDGE_RULES = [
    ("ACTOR",  "ACTION",    "ACTOR_ACTION_RELATION"),
    ("ACTOR",  "OBLIGATION","ACTOR_ACTION_RELATION"),
    ("ACTION", "TARGET",    "ACTION_TARGET_RELATION"),
    ("OBLIGATION", "TARGET","ACTION_TARGET_RELATION"),
    ("ACTION", "CONDITION", "ACTION_CONDITION_RELATION"),
    ("OBLIGATION", "CONDITION", "ACTION_CONDITION_RELATION"),
    ("ACTION", "EXCEPTION", "ACTION_EXCEPTION_RELATION"),
    ("OBLIGATION", "EXCEPTION", "ACTION_EXCEPTION_RELATION"),
    ("ACTION", "EVIDENCE",  "ACTION_EVIDENCE_RELATION"),
    ("OBLIGATION", "EVIDENCE", "ACTION_EVIDENCE_RELATION"),
    ("ACTION", "REFERENCE", "ACTION_REFERENCE_RELATION"),
    ("OBLIGATION", "REFERENCE", "ACTION_REFERENCE_RELATION"),
]

# 기존에 이미 충분히 생성된 관계 (재생성 불필요)
# ACTION_TRIGGER_RELATION: 15,883건
# ACTION_DEADLINE_RELATION: 591건
# ACTION_FREQUENCY_RELATION: 494건
# ACTION_CONDITION_RELATION: 6건 (보강 필요 → 위에 포함)

BATCH = 5000


def main():
    import psycopg2
    from psycopg2.extras import execute_values

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Constraint Graph Enrichment")
    print(f"{'='*64}")

    # ────────────────────────────────────────────────────────
    # Phase 0: 사전 상태 확인
    # ────────────────────────────────────────────────────────
    cur.execute("SELECT node_type, count(*) FROM constraint_node GROUP BY node_type ORDER BY count(*) DESC")
    print("\n  [Phase 0] 현재 node_type 분포:")
    before_counts = {}
    for r in cur.fetchall():
        before_counts[r[0]] = r[1]
        print(f"    {r[0]:20s} {r[1]:>10,}")

    cur.execute("SELECT relation_type, count(*) FROM constraint_edge GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  현재 edge relation_type 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>10,}")

    # ────────────────────────────────────────────────────────
    # Phase 1: UNKNOWN 노드 → evidence_token 기반 node_type 복원
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [Phase 1] UNKNOWN 노드 타입 복원 (evidence_token 증거 기반)")
    print(f"{'─'*64}")

    # 매핑 테이블 생성 (임시)
    cur.execute("DROP TABLE IF EXISTS _enrich_cn_map")
    cur.execute("""
        CREATE TEMP TABLE _enrich_cn_map AS
        SELECT DISTINCT cn.id AS cn_id, et.token_type
        FROM constraint_node cn
        JOIN family_candidate fc
          ON cn.part_id = fc.part_id
          AND cn.source_span_start = fc.source_span_start
          AND cn.source_span_end = fc.source_span_end
          AND cn.canonical_token = fc.canonical_token
        JOIN evidence_normalized en ON fc.normalized_id = en.id
        JOIN evidence_token et
          ON en.part_id = et.part_id
          AND en.source_span_start = et.span_start
          AND en.source_span_end = et.span_end
        WHERE cn.node_type = 'UNKNOWN'
    """)
    conn.commit()

    cur.execute("SELECT token_type, count(*) FROM _enrich_cn_map GROUP BY token_type ORDER BY count(*) DESC")
    print("\n  UNKNOWN 노드의 원본 token_type:")
    map_counts = {}
    for r in cur.fetchall():
        map_counts[r[0]] = r[1]
        mapped_to = TOKEN_TYPE_TO_NODE_TYPE.get(r[0], "UNKNOWN (유지)")
        print(f"    {r[0]:25s} {r[1]:>10,} → {mapped_to}")

    # 타입별 배치 UPDATE
    total_updated = 0
    for token_type, node_type in TOKEN_TYPE_TO_NODE_TYPE.items():
        if token_type not in map_counts:
            continue

        cur.execute("""
            UPDATE constraint_node cn
            SET node_type = %s
            FROM _enrich_cn_map m
            WHERE cn.id = m.cn_id
              AND m.token_type = %s
              AND cn.node_type = 'UNKNOWN'
        """, (node_type, token_type))
        updated = cur.rowcount
        total_updated += updated
        print(f"    ✅ {token_type} → {node_type}: {updated:,}건 갱신")

    conn.commit()
    print(f"\n  Phase 1 완료: {total_updated:,}건 노드 타입 복원")

    # 잔여 UNKNOWN 확인
    cur.execute("SELECT count(*) FROM constraint_node WHERE node_type = 'UNKNOWN'")
    remaining_unknown = cur.fetchone()[0]
    print(f"  잔여 UNKNOWN: {remaining_unknown:,}건")

    # ────────────────────────────────────────────────────────
    # Phase 2: 누락 Edge 생성
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [Phase 2] 누락 Edge 생성 (프롬프트 2단계 Relation)")
    print(f"{'─'*64}")

    total_edges = 0

    for from_type, to_type, rel_type in EDGE_RULES:
        # 이미 존재하는 edge가 있는 part는 건너뜀 (과잉 생성 방지)
        # 같은 part 내 첫 번째 (from, to) 쌍만 연결
        cur.execute(f"""
            INSERT INTO constraint_edge
                (part_id, relation_type,
                 from_node_id, to_node_id,
                 from_family, to_family,
                 from_token, to_token,
                 status)
            SELECT DISTINCT ON (f.part_id)
                f.part_id,
                %(rel_type)s,
                f.id, t.id,
                f.family_name, t.family_name,
                f.raw_token, t.raw_token,
                'CANDIDATE'
            FROM constraint_node f
            JOIN constraint_node t
              ON f.part_id = t.part_id
              AND f.id != t.id
            WHERE f.node_type = %(from_type)s
              AND t.node_type = %(to_type)s
              AND NOT EXISTS (
                  SELECT 1 FROM constraint_edge ce
                  WHERE ce.part_id = f.part_id
                    AND ce.relation_type = %(rel_type)s
              )
            ORDER BY f.part_id, f.source_span_start, t.source_span_start
        """, {"from_type": from_type, "to_type": to_type, "rel_type": rel_type})

        inserted = cur.rowcount
        total_edges += inserted
        if inserted > 0:
            print(f"    ✅ {rel_type}: {inserted:,}건 생성")
            print(f"       ({from_type} → {to_type})")

        conn.commit()

    print(f"\n  Phase 2 완료: {total_edges:,}건 Edge 생성")

    # ────────────────────────────────────────────────────────
    # Phase 3: Validation (프롬프트 13단계)
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [Phase 3] Validation")
    print(f"{'─'*64}")

    # 13-1. 모든 노드에 raw_token 존재하는지
    cur.execute("SELECT count(*) FROM constraint_node WHERE raw_token IS NULL OR raw_token = ''")
    no_raw = cur.fetchone()[0]
    print(f"    raw_token 누락 노드: {no_raw:,}건{'  ⚠️' if no_raw > 0 else '  ✅'}")

    # 13-5. semantic expansion 탐지 — 이 스크립트는 하지 않음
    print(f"    semantic expansion: 미발생 ✅ (token_type 증거만 사용)")

    # 13-6. 의미 확정 — 하지 않음
    print(f"    의미 확정: 미발생 ✅ (모든 출력 CANDIDATE)")

    # 13-9. cross-part edge 확인
    cur.execute("""
        SELECT count(*) FROM constraint_edge ce
        JOIN constraint_node fn ON ce.from_node_id = fn.id
        JOIN constraint_node tn ON ce.to_node_id = tn.id
        WHERE fn.part_id != tn.part_id
    """)
    cross_part = cur.fetchone()[0]
    print(f"    cross-part edge: {cross_part:,}건{'  ⚠️ FAIL' if cross_part > 0 else '  ✅'}")

    # ────────────────────────────────────────────────────────
    # Phase 4: 최종 상태 리포트
    # ────────────────────────────────────────────────────────
    print(f"\n{'─'*64}")
    print("  [Phase 4] 최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT node_type, count(*) FROM constraint_node GROUP BY node_type ORDER BY count(*) DESC")
    print("\n  node_type 분포 (after):")
    for r in cur.fetchall():
        before = before_counts.get(r[0], 0)
        delta = r[1] - before
        delta_str = f"(+{delta:,})" if delta > 0 else ""
        print(f"    {r[0]:20s} {r[1]:>10,}  {delta_str}")

    cur.execute("SELECT relation_type, count(*) FROM constraint_edge GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  edge relation_type 분포 (after):")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>10,}")

    cur.execute("SELECT count(*) FROM constraint_node")
    total_nodes = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM constraint_edge")
    total_edge_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료")
    print(f"{'='*64}")
    print(f"  Constraint Node 총: {total_nodes:,}건")
    print(f"  Constraint Edge 총: {total_edge_count:,}건")
    print(f"  Phase 1 노드 복원:  {total_updated:,}건")
    print(f"  Phase 2 Edge 생성:  {total_edges:,}건")
    print(f"  잔여 UNKNOWN:       {remaining_unknown:,}건")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
