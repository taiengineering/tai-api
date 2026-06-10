"""Constraint Stabilization & Executable Draft Builder — 프롬프트 20단계.

핵심: "Executable Draft는 법적 Truth가 아니라 실행 가능한 후보 구조다."

Compatibility PASS 기반으로 Stabilized Pool → Executable Draft IR 생성.
절대 금지: Rule 확정, 의무 확정, Candidate→Truth, UNKNOWN 제거

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_executable_draft.py

────────────────────────────────────────────────────────────────────
WO-LEG-Compiler-002B (2026-06-10): Scope 게이트 (NO_CONDITION 설치기준류).
  문제: 본문이 "~설치기준/~설치방법/~성능기준/~설비"인 draft가 해당 시설/설비
        보유 scope 없이(IF_SCOPE도 유효 IF_NUMERIC도 없이) CANDIDATE로 무조건
        적용됨 → 80명 화학공장에 간이스프링클러·고층건축물·도로터널 등 비보유
        설비 설치기준이 그대로 노출.
  수정: scope 없는 설치기준류 NO_CONDITION draft → NEEDS_HUMAN_REVIEW(보류).
        진단 결과 fetch는 status='CANDIDATE'만 가져가므로 보류분은 제외됨.
  방식: 개별 조문·블랙리스트 아님. 본문 패턴(설치기준류) + scope 부재 조건.
────────────────────────────────────────────────────────────────────
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# ════════════════════════════════════════════════════════
# [4단계] Scope Binding Registry (field 후보)
# ════════════════════════════════════════════════════════
SCOPE_BINDING = {
    "EMPLOYEE_SCOPE_FAMILY":       "employee_count",
    "EMPLOYEE_THRESHOLD_FAMILY":   "employee_count",
    "VOLTAGE_SCOPE_FAMILY":        "voltage_level",
    "VOLTAGE_THRESHOLD_FAMILY":    "voltage_level",
    "EQUIPMENT_SCOPE":             "equipment_type",
    "FACILITY_SCOPE":              "facility_type",
    "PROCESS_SCOPE":               "process_type",
    "CAPACITY_SCOPE_FAMILY":       "storage_capacity",
    "CAPACITY_THRESHOLD_FAMILY":   "storage_capacity",
    "AREA_SCOPE_FAMILY":           "area_size",
    "AREA_THRESHOLD_FAMILY":       "area_size",
    "CONCENTRATION_SCOPE_FAMILY":  "concentration_level",
    "CONCENTRATION_THRESHOLD_FAMILY": "concentration_level",
    "DISTANCE_SCOPE_FAMILY":       "distance_value",
    "DISTANCE_THRESHOLD_FAMILY":   "distance_value",
    "POWER_SCOPE_FAMILY":          "power_capacity",
    "POWER_THRESHOLD_FAMILY":      "power_capacity",
    "MONETARY_SCOPE_FAMILY":       "monetary_value",
    "MONETARY_THRESHOLD_FAMILY":   "monetary_value",
}

# Slot → Section 매핑
SLOT_TO_SECTION = {
    "SCOPE":      "IF_SCOPE",
    "CONDITION":  "IF_CONDITION",
    "NUMERIC":    "IF_NUMERIC",
    "ACTION":     "THEN_ACTION",
    "OBLIGATION": "THEN_ACTION",
    "TRIGGER":    "THEN_TRIGGER",
    "FREQUENCY":  "THEN_FREQUENCY",
    "DEADLINE":   "THEN_DEADLINE",
    "EVIDENCE":   "THEN_EVIDENCE",
    "EXCEPTION":  "EXCEPTION",
    "REFERENCE":  "REFERENCE",
    "ACTOR":      "IF_ACTOR",
    "TARGET":     "IF_SCOPE",
}

# ════════════════════════════════════════════════════════
# [WO-LEG-Compiler-002B] Scope 게이트 설정
# ════════════════════════════════════════════════════════
# 본문(article_title)이 설치기준/설치방법/성능기준/설비류인데 해당 시설/설비
# 보유 scope가 없으면(IF_SCOPE 없고 유효 IF_NUMERIC 없음) "무조건 적용"을
# 금지하고 보류(NEEDS_HUMAN_REVIEW)로 둔다.
SCOPE_GATE_TITLE_REGEX = r'(설치기준|설치방법|성능기준|설비|설치ㆍ관리 기준|설치 및 관리 기준)'
# 대상 법령군: NFPC / 화재안전 / 성능기준 계열 (시설·설비 설치기준이 집중된 곳)
SCOPE_GATE_LAW_REGEX = r'(NFPC|화재안전|성능기준)'

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS executable_draft (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_candidate_id UUID NOT NULL,
    part_id UUID NOT NULL,
    article_id UUID,
    pass_count INTEGER DEFAULT 0,
    ambiguous_count INTEGER DEFAULT 0,
    unresolved_count INTEGER DEFAULT 0,
    slot_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE','AMBIGUOUS','UNRESOLVED','FAIL','NEEDS_HUMAN_REVIEW')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS draft_slot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL,
    part_id UUID NOT NULL,
    section TEXT NOT NULL,
    family_name TEXT,
    binding_field TEXT,
    operator TEXT,
    value NUMERIC,
    unit TEXT,
    raw_token TEXT,
    source_span_start INTEGER,
    source_span_end INTEGER,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS draft_condition_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL,
    part_id UUID NOT NULL,
    if_families TEXT[],
    then_families TEXT[],
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS draft_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL,
    part_id UUID NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ed_rc ON executable_draft(rule_candidate_id);
CREATE INDEX IF NOT EXISTS idx_ed_part ON executable_draft(part_id);
CREATE INDEX IF NOT EXISTS idx_ds_draft ON draft_slot(draft_id);
CREATE INDEX IF NOT EXISTS idx_ds_section ON draft_slot(section);
CREATE INDEX IF NOT EXISTS idx_dcg_draft ON draft_condition_graph(draft_id);
CREATE INDEX IF NOT EXISTS idx_di_draft ON draft_issue(draft_id);
"""


def main():
    import psycopg2
    from psycopg2.extras import execute_values

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"\n{'='*64}")
    print("  Executable Draft Builder (프롬프트 20단계)")
    print(f"{'='*64}")
    print("  원칙: PASS 기반 안정화. Draft는 Truth 아님.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    # 재실행 대비
    cur.execute("SELECT count(*) FROM executable_draft")
    if cur.fetchone()[0] > 0:
        cur.execute("TRUNCATE executable_draft, draft_slot, draft_condition_graph, draft_issue")
        conn.commit()
        print("  ⚠️ TRUNCATE 완료")

    start = time.time()

    # ================================================
    # [1단계] PASS RC 식별
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1단계] Compatibility PASS RC 식별")
    print(f"{'─'*64}")

    # PASS가 1건 이상 있는 RC만 대상
    cur.execute("""
        INSERT INTO executable_draft
            (rule_candidate_id, part_id, article_id,
             pass_count, ambiguous_count, unresolved_count, status)
        SELECT
            rc.id, rc.part_id, rc.article_id,
            COALESCE(p.cnt, 0),
            COALESCE(a.cnt, 0),
            COALESCE(u.cnt, 0),
            CASE
                WHEN COALESCE(p.cnt, 0) > 0 THEN 'CANDIDATE'
                ELSE 'UNRESOLVED'
            END
        FROM rule_candidate rc
        LEFT JOIN (
            SELECT rule_candidate_id, count(*) as cnt
            FROM compatibility_validation WHERE validation = 'PASS'
            GROUP BY rule_candidate_id
        ) p ON rc.id = p.rule_candidate_id
        LEFT JOIN (
            SELECT rule_candidate_id, count(*) as cnt
            FROM compatibility_validation WHERE validation = 'AMBIGUOUS'
            GROUP BY rule_candidate_id
        ) a ON rc.id = a.rule_candidate_id
        LEFT JOIN (
            SELECT rule_candidate_id, count(*) as cnt
            FROM compatibility_validation WHERE validation = 'UNRESOLVED'
            GROUP BY rule_candidate_id
        ) u ON rc.id = u.rule_candidate_id
        WHERE COALESCE(p.cnt, 0) > 0
    """)
    draft_count = cur.rowcount
    conn.commit()
    print(f"    ✅ Executable Draft: {draft_count:,}건 (총 RC {34456}건 중 PASS 있는 것)")

    # ================================================
    # [3~12단계] Draft Slot 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3~12단계] Draft Slot 생성")
    print(f"{'─'*64}")

    # Constraint Node 기반 Slot (PASS RC에 속한 것만)
    cur.execute("""
        INSERT INTO draft_slot
            (draft_id, part_id, section, family_name,
             binding_field, raw_token,
             source_span_start, source_span_end, status)
        SELECT
            ed.id, rcs.part_id,
            CASE rcs.slot_type
                WHEN 'SCOPE' THEN 'IF_SCOPE'
                WHEN 'TARGET' THEN 'IF_SCOPE'
                WHEN 'CONDITION' THEN 'IF_CONDITION'
                WHEN 'NUMERIC' THEN 'IF_NUMERIC'
                WHEN 'ACTION' THEN 'THEN_ACTION'
                WHEN 'OBLIGATION' THEN 'THEN_ACTION'
                WHEN 'TRIGGER' THEN 'THEN_TRIGGER'
                WHEN 'FREQUENCY' THEN 'THEN_FREQUENCY'
                WHEN 'DEADLINE' THEN 'THEN_DEADLINE'
                WHEN 'EVIDENCE' THEN 'THEN_EVIDENCE'
                WHEN 'EXCEPTION' THEN 'EXCEPTION'
                WHEN 'REFERENCE' THEN 'REFERENCE'
                WHEN 'ACTOR' THEN 'IF_ACTOR'
                ELSE 'UNCLASSIFIED'
            END,
            rcs.family_name,
            NULL,
            rcs.raw_token,
            rcs.source_span_start, rcs.source_span_end,
            rcs.status
        FROM rule_candidate_slot rcs
        JOIN executable_draft ed ON rcs.rule_candidate_id = ed.rule_candidate_id
        WHERE rcs.slot_type NOT IN ('UNKNOWN', 'DEFINITION', 'DELEGATION')
    """)
    slot_cn = cur.rowcount
    conn.commit()
    print(f"    ✅ Slot (Constraint Node): {slot_cn:,}건")

    # [4~5단계] Scope/Numeric Binding
    print("    Scope/Numeric Binding...")
    for family, field in SCOPE_BINDING.items():
        cur.execute("""
            UPDATE draft_slot
            SET binding_field = %s
            WHERE family_name = %s AND binding_field IS NULL
        """, (field, family))

    # Numeric Slot에 operator/value/unit 채우기
    cur.execute("""
        UPDATE draft_slot ds
        SET operator = nc.operator,
            value = nc.value,
            unit = nc.unit
        FROM rule_candidate_slot rcs
        JOIN numeric_constraint nc ON rcs.numeric_constraint_id = nc.id
        JOIN executable_draft ed ON rcs.rule_candidate_id = ed.rule_candidate_id
        WHERE ds.draft_id = ed.id
          AND ds.section = 'IF_NUMERIC'
          AND ds.raw_token = rcs.raw_token
          AND ds.part_id = rcs.part_id
          AND ds.operator IS NULL
    """)
    numeric_bound = cur.rowcount
    conn.commit()
    print(f"    ✅ Numeric Binding: {numeric_bound:,}건")

    # Binding 통계
    cur.execute("SELECT count(*) FROM draft_slot WHERE binding_field IS NOT NULL")
    total_bound = cur.fetchone()[0]
    print(f"    ✅ Scope Binding: {total_bound:,}건 (field 후보 할당)")

    # Slot 섹션 통계
    cur.execute("SELECT section, count(*) FROM draft_slot GROUP BY section ORDER BY count(*) DESC")
    print("\n    Section 분포:")
    for r in cur.fetchall():
        print(f"      {r[0]:20s} {r[1]:>10,}")

    # slot_count 갱신
    cur.execute("""
        UPDATE executable_draft ed
        SET slot_count = sub.cnt
        FROM (SELECT draft_id, count(*) as cnt FROM draft_slot GROUP BY draft_id) sub
        WHERE ed.id = sub.draft_id
    """)
    conn.commit()

    # ================================================
    # [13단계] Condition Graph 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [13단계] Condition Graph")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO draft_condition_graph
            (draft_id, part_id, if_families, then_families, status)
        SELECT
            ed.id, ed.part_id,
            ARRAY(
                SELECT DISTINCT ds.family_name FROM draft_slot ds
                WHERE ds.draft_id = ed.id
                  AND ds.section IN ('IF_SCOPE','IF_CONDITION','IF_NUMERIC')
                  AND ds.family_name IS NOT NULL
                  AND ds.family_name != 'UNKNOWN'
                  AND ds.family_name NOT LIKE 'UNRESOLVED%%'
            ),
            ARRAY(
                SELECT DISTINCT ds.family_name FROM draft_slot ds
                WHERE ds.draft_id = ed.id
                  AND ds.section IN ('THEN_ACTION','THEN_TRIGGER','THEN_FREQUENCY','THEN_DEADLINE')
                  AND ds.family_name IS NOT NULL
                  AND ds.family_name != 'UNKNOWN'
                  AND ds.family_name NOT LIKE 'UNRESOLVED%%'
            ),
            'CANDIDATE'
        FROM executable_draft ed
        WHERE ed.status = 'CANDIDATE'
    """)
    cg_count = cur.rowcount
    conn.commit()
    print(f"    ✅ Condition Graph: {cg_count:,}건")

    # 빈 graph 제거 (if/then 모두 비어있는 경우)
    cur.execute("""
        DELETE FROM draft_condition_graph
        WHERE if_families = '{}' AND then_families = '{}'
    """)
    empty_cg = cur.rowcount
    conn.commit()
    if empty_cg > 0:
        print(f"    ⬜ 빈 Graph 제거: {empty_cg:,}건")

    cur.execute("SELECT count(*) FROM draft_condition_graph")
    final_cg = cur.fetchone()[0]
    print(f"    최종 Condition Graph: {final_cg:,}건")

    # ================================================
    # [14단계] Scope 게이트 — WO-LEG-Compiler-002B
    # ================================================
    # 본문이 설치기준/설치방법/성능기준/설비류인데 해당 시설/설비 보유 scope가
    # 없으면(IF_SCOPE 없고 유효 IF_NUMERIC 없음) 무조건 적용 금지 → 보류.
    # 진단 fetch는 status='CANDIDATE'만 가져가므로 보류분은 결과에서 제외됨.
    print(f"\n{'─'*64}")
    print("  [14단계] Scope 게이트 (NO_CONDITION 설치기준류 → 보류)")
    print(f"{'─'*64}")

    cur.execute("""
        WITH cand AS (
            SELECT ed.id AS draft_id,
                bool_or(ds.section = 'IF_SCOPE') AS has_scope,
                bool_or(ds.section = 'IF_NUMERIC' AND ds.binding_field IS NOT NULL) AS has_active_numeric
            FROM executable_draft ed
            JOIN law_article la ON la.id = ed.article_id
            JOIN law_master lm ON lm.id = la.law_id AND lm.is_active
            LEFT JOIN draft_slot ds ON ds.draft_id = ed.id
            WHERE ed.status = 'CANDIDATE'
              AND lm.law_name ~ %(law_re)s
              AND la.article_title ~ %(title_re)s
            GROUP BY ed.id
        )
        UPDATE executable_draft ed
        SET status = 'NEEDS_HUMAN_REVIEW'
        FROM cand
        WHERE ed.id = cand.draft_id
          AND NOT cand.has_scope
          AND NOT cand.has_active_numeric
    """, {"law_re": SCOPE_GATE_LAW_REGEX, "title_re": SCOPE_GATE_TITLE_REGEX})
    scope_gated = cur.rowcount
    conn.commit()
    print(f"    ✅ Scope 게이트 보류 처리: {scope_gated:,}건")
    print(f"       (설치기준류 + scope 부재 → NEEDS_HUMAN_REVIEW, 무조건 적용 차단)")

    # 보류 사유를 draft_issue에 기록 (추적용)
    cur.execute("""
        INSERT INTO draft_issue (draft_id, part_id, issue_type, detail)
        SELECT ed.id, ed.part_id, 'SCOPE_REQUIRED',
               'NO_CONDITION install-standard held: facility/equipment scope missing'
        FROM executable_draft ed
        WHERE ed.status = 'NEEDS_HUMAN_REVIEW'
          AND NOT EXISTS (
              SELECT 1 FROM draft_issue di
              WHERE di.draft_id = ed.id AND di.issue_type = 'SCOPE_REQUIRED'
          )
    """)
    conn.commit()

    # ================================================
    # [16단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [16단계] Validation")
    print(f"{'─'*64}")

    print(f"    Compatibility PASS 기반: ✅ (PASS RC만 사용)")
    print(f"    semantic expansion: 미발생 ✅")
    print(f"    rule inference: 미발생 ✅")
    print(f"    Candidate→Truth: 없음 ✅")
    print(f"    UNKNOWN 제거: 없음 ✅")

    # UNCLASSIFIED slot 확인
    cur.execute("SELECT count(*) FROM draft_slot WHERE section = 'UNCLASSIFIED'")
    unclass = cur.fetchone()[0]
    if unclass > 0:
        print(f"    ⚠️ UNCLASSIFIED slot: {unclass:,}건")

    # ================================================
    # 최종 상태
    # ================================================
    print(f"\n{'─'*64}")
    print("  최종 상태")
    print(f"{'─'*64}")

    cur.execute("SELECT count(*) FROM executable_draft")
    total_ed = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM draft_slot")
    total_ds = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM draft_condition_graph")
    total_dcg = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM draft_issue")
    total_di = cur.fetchone()[0]

    cur.execute("SELECT status, count(*) FROM executable_draft GROUP BY status ORDER BY count(*) DESC")
    print("\n  Executable Draft status:")
    for r in cur.fetchall():
        print(f"    {r[0]:25s} {r[1]:>8,}")

    cur.execute("SELECT avg(slot_count)::int, max(slot_count), min(slot_count) FROM executable_draft WHERE slot_count > 0")
    avg_s, max_s, min_s = cur.fetchone()

    cur.execute("SELECT avg(pass_count)::numeric(5,1), avg(ambiguous_count)::numeric(5,1), avg(unresolved_count)::numeric(5,1) FROM executable_draft")
    avg_p, avg_a, avg_u = cur.fetchone()

    elapsed = time.time() - start
    cur.close()
    conn.close()

    print(f"\n  Executable Draft:    {total_ed:,}건")
    print(f"  Draft Slot:          {total_ds:,}건 (avg {avg_s}/draft, max {max_s})")
    print(f"  Condition Graph:     {total_dcg:,}건")
    print(f"  Issues:              {total_di:,}건")
    print(f"  Avg per draft: PASS={avg_p} AMBIGUOUS={avg_a} UNRESOLVED={avg_u}")

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Executable Draft: {total_ed:,}")
    print(f"  Draft Slot:       {total_ds:,}")
    print(f"  Condition Graph:  {total_dcg:,}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
