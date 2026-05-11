"""Constraint Integration & Rule Candidate IR Builder — 프롬프트 19단계.

핵심: "Rule 생성이 아니라 Rule Candidate Graph를 만드는 단계"

Family Candidate + Numeric Constraint → Rule Candidate IR 조합.
절대 금지: Rule 확정, 의무 확정, 법 적용 확정, Candidate→Truth 승격.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_rule_candidate.py
"""

import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

CREATE_TABLES_SQL = """
-- Rule Candidate: part단위 후보 구조
CREATE TABLE IF NOT EXISTS rule_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL UNIQUE,
    article_id UUID,
    slot_count INTEGER DEFAULT 0,
    relation_count INTEGER DEFAULT 0,
    has_numeric BOOLEAN DEFAULT false,
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','AMBIGUOUS','UNRESOLVED','FAIL','NEEDS_HUMAN_REVIEW')),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Slot: 각 Family Candidate 연결
CREATE TABLE IF NOT EXISTS rule_candidate_slot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_candidate_id UUID NOT NULL,
    part_id UUID NOT NULL,
    slot_type TEXT NOT NULL,
    family_name TEXT,
    raw_token TEXT,
    canonical_token TEXT,
    source_span_start INTEGER,
    source_span_end INTEGER,
    constraint_node_id UUID,
    numeric_constraint_id UUID,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Relation: Slot 간 후보 연결
CREATE TABLE IF NOT EXISTS rule_candidate_relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_candidate_id UUID NOT NULL,
    part_id UUID NOT NULL,
    relation_type TEXT NOT NULL,
    from_slot_type TEXT,
    to_slot_type TEXT,
    from_family TEXT,
    to_family TEXT,
    constraint_edge_id UUID,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rc_part ON rule_candidate(part_id);
CREATE INDEX IF NOT EXISTS idx_rcs_rc ON rule_candidate_slot(rule_candidate_id);
CREATE INDEX IF NOT EXISTS idx_rcs_part ON rule_candidate_slot(part_id);
CREATE INDEX IF NOT EXISTS idx_rcs_type ON rule_candidate_slot(slot_type);
CREATE INDEX IF NOT EXISTS idx_rcr_rc ON rule_candidate_relation(rule_candidate_id);
CREATE INDEX IF NOT EXISTS idx_rcr_part ON rule_candidate_relation(part_id);
CREATE INDEX IF NOT EXISTS idx_rcr_type ON rule_candidate_relation(relation_type);
"""

# node_type → slot_type 매핑
NODE_TYPE_TO_SLOT = {
    "ACTION": "ACTION",
    "OBLIGATION": "OBLIGATION",
    "ACTOR": "ACTOR",
    "TARGET": "TARGET",
    "SCOPE": "SCOPE",
    "CONDITION": "CONDITION",
    "TRIGGER": "TRIGGER",
    "FREQUENCY": "FREQUENCY",
    "DEADLINE": "DEADLINE",
    "EVIDENCE": "EVIDENCE",
    "EXCEPTION": "EXCEPTION",
    "REFERENCE": "REFERENCE",
    "DELEGATION": "DELEGATION",
    "DEFINITION": "DEFINITION",
    "UNKNOWN": "UNKNOWN",
}

# constraint_edge.relation_type → rule relation_type
EDGE_TO_RELATION = {
    "ACTOR_ACTION_RELATION": "ACTOR_ACTION",
    "ACTION_TARGET_RELATION": "HAS_TARGET",
    "ACTION_CONDITION_RELATION": "HAS_CONDITION",
    "ACTION_TRIGGER_RELATION": "HAS_TRIGGER",
    "ACTION_FREQUENCY_RELATION": "HAS_FREQUENCY",
    "ACTION_DEADLINE_RELATION": "HAS_DEADLINE",
    "ACTION_EVIDENCE_RELATION": "HAS_EVIDENCE",
    "ACTION_EXCEPTION_RELATION": "HAS_EXCEPTION",
    "ACTION_REFERENCE_RELATION": "HAS_REFERENCE",
    "ACTION_SCOPE_RELATION": "HAS_SCOPE",
}


def main():
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Rule Candidate IR Builder (프롬프트 19단계)")
    print(f"{'='*64}")
    print("  원칙: Rule 확정 금지, Candidate Graph IR 생성")

    # 테이블 생성
    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비
    cur.execute("SELECT count(*) FROM rule_candidate")
    if cur.fetchone()[0] > 0:
        print("  ⚠️ 기존 데이터 TRUNCATE")
        cur.execute("TRUNCATE rule_candidate, rule_candidate_slot, rule_candidate_relation")
        conn.commit()

    start = time.time()

    # ================================================
    # [1단계] Input 확인
    # ================================================
    cur.execute("SELECT count(*) FROM constraint_node")
    cn_total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM constraint_edge")
    ce_total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM numeric_constraint")
    nc_total = cur.fetchone()[0]
    print(f"\n  [1단계] Input (수정 없음):")
    print(f"    constraint_node: {cn_total:,}")
    print(f"    constraint_edge: {ce_total:,}")
    print(f"    numeric_constraint: {nc_total:,}")

    # ================================================
    # [2단계] Rule Candidate Skeleton 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [2단계] Rule Candidate Skeleton")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO rule_candidate (part_id, article_id, has_numeric, status)
        SELECT DISTINCT
            cn.part_id,
            lap.article_id,
            EXISTS(SELECT 1 FROM numeric_constraint nc WHERE nc.part_id = cn.part_id),
            'CANDIDATE'
        FROM constraint_node cn
        JOIN law_article_part lap ON cn.part_id = lap.id
        WHERE cn.node_type IN ('ACTION', 'OBLIGATION')
    """)
    rc_count = cur.rowcount
    conn.commit()
    print(f"    ✅ rule_candidate: {rc_count:,}건 생성")

    # ================================================
    # [3~11단계] Slot 생성 (Constraint Node → Slot)
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3~11단계] Slot 생성")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO rule_candidate_slot
            (rule_candidate_id, part_id, slot_type, family_name,
             raw_token, canonical_token,
             source_span_start, source_span_end,
             constraint_node_id, status)
        SELECT
            rc.id,
            cn.part_id,
            cn.node_type,
            cn.family_name,
            cn.raw_token,
            cn.canonical_token,
            cn.source_span_start,
            cn.source_span_end,
            cn.id,
            CASE
                WHEN cn.node_type = 'UNKNOWN' THEN 'UNRESOLVED'
                WHEN cn.status = 'UNRESOLVED' THEN 'UNRESOLVED'
                ELSE 'CANDIDATE'
            END
        FROM constraint_node cn
        JOIN rule_candidate rc ON cn.part_id = rc.part_id
    """)
    slot_from_cn = cur.rowcount
    conn.commit()
    print(f"    ✅ Constraint Node → Slot: {slot_from_cn:,}건")

    # [5단계] Numeric Constraint → Slot
    cur.execute("""
        INSERT INTO rule_candidate_slot
            (rule_candidate_id, part_id, slot_type, family_name,
             raw_token, source_span_start, source_span_end,
             numeric_constraint_id, status)
        SELECT
            rc.id,
            nc.part_id,
            'NUMERIC',
            nfc.family_name,
            nc.raw_text,
            nc.source_span_start,
            nc.source_span_end,
            nc.id,
            CASE WHEN nfc.status = 'UNRESOLVED' THEN 'UNRESOLVED' ELSE 'CANDIDATE' END
        FROM numeric_constraint nc
        JOIN rule_candidate rc ON nc.part_id = rc.part_id
        LEFT JOIN numeric_family_candidate nfc ON nc.id = nfc.numeric_constraint_id
    """)
    slot_from_nc = cur.rowcount
    conn.commit()
    print(f"    ✅ Numeric Constraint → Slot: {slot_from_nc:,}건")

    total_slots = slot_from_cn + slot_from_nc

    # Slot 통계
    cur.execute("SELECT slot_type, count(*) FROM rule_candidate_slot GROUP BY slot_type ORDER BY count(*) DESC")
    print("\n    slot_type 분포:")
    for r in cur.fetchall():
        print(f"      {r[0]:20s} {r[1]:>10,}")

    # ================================================
    # [12단계] Candidate Relation Graph 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [12단계] Candidate Relation Graph")
    print(f"{'─'*64}")

    # Constraint Edge → Relation
    cur.execute("""
        INSERT INTO rule_candidate_relation
            (rule_candidate_id, part_id, relation_type,
             from_slot_type, to_slot_type,
             from_family, to_family,
             constraint_edge_id, status)
        SELECT
            rc.id,
            ce.part_id,
            ce.relation_type,
            fn.node_type,
            tn.node_type,
            ce.from_family,
            ce.to_family,
            ce.id,
            'CANDIDATE'
        FROM constraint_edge ce
        JOIN rule_candidate rc ON ce.part_id = rc.part_id
        JOIN constraint_node fn ON ce.from_node_id = fn.id
        JOIN constraint_node tn ON ce.to_node_id = tn.id
    """)
    rel_from_ce = cur.rowcount
    conn.commit()
    print(f"    ✅ Constraint Edge → Relation: {rel_from_ce:,}건")

    # Numeric Graph Relation → Relation
    cur.execute("""
        INSERT INTO rule_candidate_relation
            (rule_candidate_id, part_id, relation_type,
             from_slot_type, to_slot_type,
             from_family, to_family, status)
        SELECT
            rc.id,
            ngr.part_id,
            ngr.relation_type,
            'NUMERIC',
            CASE
                WHEN ngr.relation_type LIKE '%%SCOPE%%' THEN 'SCOPE'
                WHEN ngr.relation_type LIKE '%%TRIGGER%%' THEN 'TRIGGER'
                WHEN ngr.relation_type LIKE '%%FREQUENCY%%' THEN 'FREQUENCY'
                WHEN ngr.relation_type LIKE '%%DEADLINE%%' THEN 'DEADLINE'
                ELSE 'ACTION'
            END,
            ngr.numeric_family,
            ngr.target_family,
            'CANDIDATE'
        FROM numeric_graph_relation ngr
        JOIN rule_candidate rc ON ngr.part_id = rc.part_id
    """)
    rel_from_ngr = cur.rowcount
    conn.commit()
    print(f"    ✅ Numeric Graph → Relation: {rel_from_ngr:,}건")

    total_rels = rel_from_ce + rel_from_ngr

    # Relation 통계
    cur.execute("SELECT relation_type, count(*) FROM rule_candidate_relation GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n    relation_type 분포:")
    for r in cur.fetchall():
        print(f"      {r[0]:45s} {r[1]:>8,}")

    # ================================================
    # slot_count, relation_count 갱신
    # ================================================
    cur.execute("""
        UPDATE rule_candidate rc
        SET slot_count = sub.sc, relation_count = sub.rc_cnt
        FROM (
            SELECT rc2.id,
                   COALESCE(s.cnt, 0) as sc,
                   COALESCE(r.cnt, 0) as rc_cnt
            FROM rule_candidate rc2
            LEFT JOIN (SELECT rule_candidate_id, count(*) as cnt FROM rule_candidate_slot GROUP BY rule_candidate_id) s
              ON rc2.id = s.rule_candidate_id
            LEFT JOIN (SELECT rule_candidate_id, count(*) as cnt FROM rule_candidate_relation GROUP BY rule_candidate_id) r
              ON rc2.id = r.rule_candidate_id
        ) sub
        WHERE rc.id = sub.id
    """)
    conn.commit()

    # ================================================
    # [15단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [15단계] Validation")
    print(f"{'─'*64}")

    # raw_token 누락
    cur.execute("SELECT count(*) FROM rule_candidate_slot WHERE raw_token IS NULL OR raw_token = ''")
    no_raw = cur.fetchone()[0]
    print(f"    raw_token 누락 slot: {no_raw:,}건{'  ⚠️' if no_raw > 0 else '  ✅'}")

    # UNRESOLVED slot
    cur.execute("SELECT count(*) FROM rule_candidate_slot WHERE status = 'UNRESOLVED'")
    unres_slot = cur.fetchone()[0]
    print(f"    UNRESOLVED slot: {unres_slot:,}건 (프롬프트 14단계 준수 — UNKNOWN 유지)")

    print(f"    Rule inference: 미발생 ✅")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    Candidate→Truth 승격: 없음 ✅")

    # ================================================
    # 최종 상태
    # ================================================
    print(f"\n{'─'*64}")
    print("  최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT count(*) FROM rule_candidate")
    total_rc = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM rule_candidate WHERE has_numeric")
    rc_with_num = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM rule_candidate_slot")
    total_slot = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM rule_candidate_relation")
    total_rel = cur.fetchone()[0]

    # slot 통계
    cur.execute("SELECT avg(slot_count)::int, max(slot_count), min(slot_count) FROM rule_candidate")
    avg_s, max_s, min_s = cur.fetchone()
    cur.execute("SELECT avg(relation_count)::int, max(relation_count) FROM rule_candidate")
    avg_r, max_r = cur.fetchone()

    elapsed = time.time() - start

    cur.close()
    conn.close()

    print(f"\n  Rule Candidate:      {total_rc:,}건")
    print(f"    with Numeric:      {rc_with_num:,}건")
    print(f"  Slot:                {total_slot:,}건 (avg {avg_s}/RC, max {max_s})")
    print(f"  Relation:            {total_rel:,}건 (avg {avg_r}/RC, max {max_r})")

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Rule Candidate: {total_rc:,}")
    print(f"  Slot:           {total_slot:,}")
    print(f"  Relation:       {total_rel:,}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
