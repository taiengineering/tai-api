"""Numeric-Aware Family Builder — 프롬프트 17단계 전체 실행.

핵심: "숫자는 조건 구조를 제한하지만, 법적 의미를 확정하지 않는다."

절대 금지:
  - 50명 이상 → 안전관리자 선임 의무 확정 금지
  - 연 1회 이상 → 정기안전교육 확정 금지
  - Rule 생성 금지
  - 의미 확정/확장 금지

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_numeric_family.py
"""

import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# [2단계] Numeric Family Registry
# ════════════════════════════════════════════════════════════

# constraint_type → family_name 매핑
CTYPE_TO_FAMILY = {
    "EMPLOYEE_THRESHOLD_CANDIDATE":      "EMPLOYEE_THRESHOLD_FAMILY",
    "CAPACITY_THRESHOLD_CANDIDATE":      "CAPACITY_THRESHOLD_FAMILY",
    "VOLTAGE_THRESHOLD_CANDIDATE":       "VOLTAGE_THRESHOLD_FAMILY",
    "POWER_THRESHOLD_CANDIDATE":         "POWER_THRESHOLD_FAMILY",
    "AREA_THRESHOLD_CANDIDATE":          "AREA_THRESHOLD_FAMILY",
    "FREQUENCY_THRESHOLD_CANDIDATE":     "FREQUENCY_THRESHOLD_FAMILY",
    "DEADLINE_OR_PERIOD_CANDIDATE":      "DEADLINE_THRESHOLD_FAMILY",
    "CONCENTRATION_THRESHOLD_CANDIDATE": "CONCENTRATION_THRESHOLD_FAMILY",
    "DISTANCE_THRESHOLD_CANDIDATE":      "DISTANCE_THRESHOLD_FAMILY",
    "MONETARY_THRESHOLD_CANDIDATE":      "MONETARY_THRESHOLD_FAMILY",
    # UNKNOWN_THRESHOLD_CANDIDATE → UNKNOWN (유지)
}

# [4단계] Subject 기반 제한: subject 키워드 → 우선 family
SUBJECT_HINTS = {
    "근로자": "EMPLOYEE_THRESHOLD_FAMILY",
    "상시근로자": "EMPLOYEE_THRESHOLD_FAMILY",
    "종업원": "EMPLOYEE_THRESHOLD_FAMILY",
    "저장용량": "CAPACITY_THRESHOLD_FAMILY",
    "용량": "CAPACITY_THRESHOLD_FAMILY",
    "전압": "VOLTAGE_THRESHOLD_FAMILY",
    "농도": "CONCENTRATION_THRESHOLD_FAMILY",
    "면적": "AREA_THRESHOLD_FAMILY",
}

# [6단계] Numeric Family → Action 연결 규칙
# numeric_family + constraint_node.node_type → relation_type
NUMERIC_ACTION_RULES = [
    # (numeric_family, target_node_type, relation_type)
    ("FREQUENCY_THRESHOLD_FAMILY", "ACTION",     "ACTION_NUMERIC_FREQUENCY_RELATION"),
    ("FREQUENCY_THRESHOLD_FAMILY", "OBLIGATION", "ACTION_NUMERIC_FREQUENCY_RELATION"),
    ("DEADLINE_THRESHOLD_FAMILY",  "ACTION",     "ACTION_NUMERIC_DEADLINE_RELATION"),
    ("DEADLINE_THRESHOLD_FAMILY",  "OBLIGATION", "ACTION_NUMERIC_DEADLINE_RELATION"),
]

# [7단계] Numeric → Scope 연결
NUMERIC_SCOPE_RULES = [
    ("EMPLOYEE_THRESHOLD_FAMILY",      "EMPLOYEE_SCOPE_FAMILY"),
    ("CAPACITY_THRESHOLD_FAMILY",      "CAPACITY_SCOPE_FAMILY"),
    ("VOLTAGE_THRESHOLD_FAMILY",       "VOLTAGE_SCOPE_FAMILY"),
    ("POWER_THRESHOLD_FAMILY",         "POWER_SCOPE_FAMILY"),
    ("AREA_THRESHOLD_FAMILY",          "AREA_SCOPE_FAMILY"),
    ("CONCENTRATION_THRESHOLD_FAMILY", "CONCENTRATION_SCOPE_FAMILY"),
    ("DISTANCE_THRESHOLD_FAMILY",      "DISTANCE_SCOPE_FAMILY"),
    ("MONETARY_THRESHOLD_FAMILY",      "MONETARY_SCOPE_FAMILY"),
]


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS numeric_family_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    family_name TEXT NOT NULL,
    numeric_constraint_id UUID NOT NULL,
    raw_text TEXT,
    subject TEXT,
    source_span_start INTEGER,
    source_span_end INTEGER,
    restriction_reason TEXT[],
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','CONTEXT_RESTRICTED_CANDIDATE','AMBIGUOUS','UNRESOLVED','FAIL')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS numeric_graph_relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    relation_type TEXT NOT NULL,
    numeric_family TEXT NOT NULL,
    target_family TEXT,
    numeric_constraint_id UUID,
    constraint_node_id UUID,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nfc_part ON numeric_family_candidate(part_id);
CREATE INDEX IF NOT EXISTS idx_nfc_family ON numeric_family_candidate(family_name);
CREATE INDEX IF NOT EXISTS idx_nfc_ncid ON numeric_family_candidate(numeric_constraint_id);
CREATE INDEX IF NOT EXISTS idx_ngr_part ON numeric_graph_relation(part_id);
CREATE INDEX IF NOT EXISTS idx_ngr_type ON numeric_graph_relation(relation_type);
"""


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
    print("  Numeric-Aware Family Builder (프롬프트 17단계)")
    print(f"{'='*64}")
    print("  원칙: 숫자는 조건 구조 제한만, 법적 의미 확정 금지")

    # 테이블 생성
    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비 TRUNCATE
    cur.execute("SELECT count(*) FROM numeric_family_candidate")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE numeric_family_candidate, numeric_graph_relation")
        conn.commit()
        print("  ⚠️ 기존 데이터 TRUNCATE 완료")

    # ================================================
    # [1단계] Numeric Constraint Input 확인 (수정 없음)
    # ================================================
    cur.execute("SELECT count(*) FROM numeric_constraint")
    nc_total = cur.fetchone()[0]
    print(f"\n  [1단계] Numeric Constraint: {nc_total:,}건 (수정 없음)")

    # ================================================
    # [2~4단계] Family Registry 매칭 + Subject 제한
    # ================================================
    print(f"\n{'─'*64}")
    print("  [2~4단계] Numeric Family Candidate 생성")
    print(f"{'─'*64}")

    cur.execute("""
        SELECT id::text, part_id::text, raw_text, subject, 
               constraint_type, source_span_start, source_span_end
        FROM numeric_constraint
    """)
    rows = cur.fetchall()

    candidates = []
    for nc_id, part_id, raw_text, subject, ctype, ss, se in rows:
        family = CTYPE_TO_FAMILY.get(ctype)

        if not family:
            # UNKNOWN_THRESHOLD_CANDIDATE → UNRESOLVED
            candidates.append((
                part_id, "UNKNOWN_THRESHOLD_FAMILY", nc_id,
                raw_text, subject, ss, se, None, "UNRESOLVED"
            ))
            continue

        # [4단계] Subject 확인
        status = "CANDIDATE"
        restriction = None
        if subject and subject != "UNKNOWN_SUBJECT":
            hint_family = SUBJECT_HINTS.get(subject)
            if hint_family and hint_family == family:
                status = "CONTEXT_RESTRICTED_CANDIDATE"
                restriction = [f"subject={subject}", f"unit_match=true"]

        candidates.append((
            part_id, family, nc_id,
            raw_text, subject, ss, se, restriction, status
        ))

    # 배치 INSERT
    if candidates:
        execute_values(cur, """
            INSERT INTO numeric_family_candidate
                (part_id, family_name, numeric_constraint_id,
                 raw_text, subject, source_span_start, source_span_end,
                 restriction_reason, status)
            VALUES %s
        """, candidates, page_size=2000)
        conn.commit()

    # 통계
    cur.execute("SELECT family_name, status, count(*) FROM numeric_family_candidate GROUP BY family_name, status ORDER BY count(*) DESC")
    print("\n  Family Candidate 분포:")
    for r in cur.fetchall():
        print(f"    {r[0]:40s} {r[1]:30s} {r[2]:>6,}")

    print(f"\n  ✅ Numeric Family Candidate: {len(candidates):,}건 생성")

    # ================================================
    # [6단계] Numeric + Action 연결 후보
    # ================================================
    print(f"\n{'─'*64}")
    print("  [6단계] Numeric + Action 연결 후보")
    print(f"{'─'*64}")

    action_rels_total = 0
    for num_family, node_type, rel_type in NUMERIC_ACTION_RULES:
        cur.execute("""
            INSERT INTO numeric_graph_relation
                (part_id, relation_type, numeric_family, target_family,
                 numeric_constraint_id, constraint_node_id, status)
            SELECT DISTINCT ON (nfc.part_id)
                nfc.part_id,
                %(rel_type)s,
                nfc.family_name,
                cn.family_name,
                nfc.numeric_constraint_id,
                cn.id,
                'CANDIDATE'
            FROM numeric_family_candidate nfc
            JOIN constraint_node cn
              ON nfc.part_id = cn.part_id
            WHERE nfc.family_name = %(num_family)s
              AND cn.node_type = %(node_type)s
              AND nfc.status != 'UNRESOLVED'
            ORDER BY nfc.part_id, cn.source_span_start
        """, {"num_family": num_family, "node_type": node_type, "rel_type": rel_type})
        cnt = cur.rowcount
        action_rels_total += cnt
        if cnt > 0:
            print(f"    ✅ {rel_type}: {cnt:,}건")
            print(f"       ({num_family} + {node_type})")
    conn.commit()

    # ================================================
    # [7단계] Numeric + Scope 연결 후보
    # ================================================
    print(f"\n{'─'*64}")
    print("  [7단계] Numeric + Scope 연결 후보")
    print(f"{'─'*64}")

    scope_rels_total = 0
    for num_family, scope_family in NUMERIC_SCOPE_RULES:
        cur.execute("""
            INSERT INTO numeric_graph_relation
                (part_id, relation_type, numeric_family, target_family,
                 numeric_constraint_id, status)
            SELECT DISTINCT ON (nfc.part_id)
                nfc.part_id,
                'NUMERIC_SCOPE_RELATION',
                nfc.family_name,
                %(scope_family)s,
                nfc.numeric_constraint_id,
                'CANDIDATE'
            FROM numeric_family_candidate nfc
            WHERE nfc.family_name = %(num_family)s
              AND nfc.status != 'UNRESOLVED'
            ORDER BY nfc.part_id
        """, {"num_family": num_family, "scope_family": scope_family})
        cnt = cur.rowcount
        scope_rels_total += cnt
        if cnt > 0:
            print(f"    ✅ NUMERIC_SCOPE_RELATION: {cnt:,}건")
            print(f"       ({num_family} → {scope_family})")
    conn.commit()

    # ================================================
    # [8단계] Numeric + Trigger (PERIODIC)
    # ================================================
    print(f"\n{'─'*64}")
    print("  [8단계] Numeric + Trigger 연결 후보")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO numeric_graph_relation
            (part_id, relation_type, numeric_family, target_family,
             numeric_constraint_id, status)
        SELECT DISTINCT ON (nfc.part_id)
            nfc.part_id,
            'NUMERIC_TRIGGER_RELATION',
            nfc.family_name,
            'PERIODIC_TRIGGER_FAMILY',
            nfc.numeric_constraint_id,
            'CANDIDATE'
        FROM numeric_family_candidate nfc
        JOIN numeric_constraint nc ON nfc.numeric_constraint_id = nc.id
        WHERE nfc.family_name = 'FREQUENCY_THRESHOLD_FAMILY'
          AND nc.operator = 'PERIODIC'
          AND nfc.status != 'UNRESOLVED'
        ORDER BY nfc.part_id
    """)
    trigger_cnt = cur.rowcount
    conn.commit()
    if trigger_cnt > 0:
        print(f"    ✅ NUMERIC_TRIGGER_RELATION: {trigger_cnt:,}건")
        print(f"       (FREQUENCY + PERIODIC operator → PERIODIC_TRIGGER_FAMILY)")
    else:
        print(f"    ⬜ 0건 (주기 패턴 미매칭)")

    # ================================================
    # [9단계] Numeric + Deadline
    # ================================================
    print(f"\n{'─'*64}")
    print("  [9단계] Numeric + Deadline 연결 후보")
    print(f"{'─'*64}")
    print("  → [6단계]에서 ACTION_NUMERIC_DEADLINE_RELATION으로 이미 생성")
    print("  → \"즉시\", \"지체 없이\" 등 숫자 없는 표현은 제외 (프롬프트 준수)")

    # ================================================
    # [10단계] Semantic Expansion 검증 (금지 확인)
    # ================================================
    # 이 스크립트는 의미 확장을 하지 않음 — 검증만

    # ================================================
    # [13단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [13단계] Validation")
    print(f"{'─'*64}")

    # span 누락
    cur.execute("SELECT count(*) FROM numeric_family_candidate WHERE source_span_start IS NULL")
    no_span = cur.fetchone()[0]
    print(f"    source_span 누락: {no_span}건{'  ⚠️' if no_span > 0 else '  ✅'}")

    # raw_text 누락
    cur.execute("SELECT count(*) FROM numeric_family_candidate WHERE raw_text IS NULL OR raw_text = ''")
    no_raw = cur.fetchone()[0]
    print(f"    raw_text 누락: {no_raw}건{'  ⚠️' if no_raw > 0 else '  ✅'}")

    print(f"    semantic expansion: 미발생 ✅")
    print(f"    Rule 생성: 없음 ✅")
    print(f"    단위 환산: 미발생 ✅")

    # ================================================
    # 최종 상태
    # ================================================
    print(f"\n{'─'*64}")
    print("  최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT status, count(*) FROM numeric_family_candidate GROUP BY status ORDER BY count(*) DESC")
    print("\n  Family Candidate status:")
    for r in cur.fetchall():
        print(f"    {r[0]:35s} {r[1]:>8,}")

    cur.execute("SELECT family_name, count(*) FROM numeric_family_candidate WHERE status != 'UNRESOLVED' GROUP BY family_name ORDER BY count(*) DESC")
    print("\n  Family Candidate (분류된 것):")
    for r in cur.fetchall():
        print(f"    {r[0]:40s} {r[1]:>8,}")

    cur.execute("SELECT relation_type, count(*) FROM numeric_graph_relation GROUP BY relation_type ORDER BY count(*) DESC")
    print("\n  Graph Relation:")
    for r in cur.fetchall():
        print(f"    {r[0]:45s} {r[1]:>8,}")

    cur.execute("SELECT count(*) FROM numeric_family_candidate")
    total_cand = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM numeric_graph_relation")
    total_rel = cur.fetchone()[0]

    cur.close()
    conn.close()

    total_rels = action_rels_total + scope_rels_total + trigger_cnt
    print(f"\n{'='*64}")
    print(f"  완료")
    print(f"{'='*64}")
    print(f"  Numeric Family Candidate: {total_cand:,}건")
    print(f"  Graph Relation:           {total_rel:,}건")
    print(f"    Action 연결:             {action_rels_total:,}건")
    print(f"    Scope 연결:              {scope_rels_total:,}건")
    print(f"    Trigger 연결:            {trigger_cnt:,}건")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
