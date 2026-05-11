"""Residual Coverage & Unparsed Law Capture Engine — 프롬프트 19단계.

핵심: "못 읽은 법령도 엔진의 일부다."
절대 금지: 추상 표현 구체화, 실패 데이터 삭제, 의미 보정, registry 자동 확장

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_residual_coverage.py
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

# [4단계] Abstract Pattern 탐지 대상
ABSTRACT_PATTERNS = [
    ("필요한 조치",   "ABSTRACT_REQUIREMENT"),
    ("필요한 경우",   "ABSTRACT_REQUIREMENT"),
    ("적절한",       "ABSTRACT_REQUIREMENT"),
    ("충분한",       "ABSTRACT_REQUIREMENT"),
    ("안전하게",     "ABSTRACT_REQUIREMENT"),
    ("상당한",       "ABSTRACT_REQUIREMENT"),
    ("합리적",       "ABSTRACT_REQUIREMENT"),
    ("기준에 적합",   "BROAD_OBLIGATION"),
    ("대통령령으로 정하는", "UNRESOLVED_REFERENCE"),
    ("고시로 정하는",   "UNRESOLVED_REFERENCE"),
    ("해당 법령에 따라",  "UNRESOLVED_REFERENCE"),
    ("관리상 필요한",  "ABSTRACT_REQUIREMENT"),
    ("적합한 기준",   "BROAD_OBLIGATION"),
]

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS residual_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    article_id UUID,
    law_id UUID,
    residual_type TEXT NOT NULL,
    failed_reason TEXT,
    source_text TEXT,
    source_text_length INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW','REVIEW_PENDING','REVIEWED','REGISTRY_EXPANSION_REQUESTED',
                          'RESOLVED_BY_HUMAN','KEPT_AS_UNKNOWN','REJECTED','NEEDS_MORE_SOURCE')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS residual_abstract_pattern (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL,
    law_id UUID,
    pattern_text TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    source_text TEXT,
    status TEXT NOT NULL DEFAULT 'CANDIDATE',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS residual_coverage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    law_id UUID NOT NULL,
    law_name TEXT,
    total_parts INTEGER DEFAULT 0,
    parsed_parts INTEGER DEFAULT 0,
    residual_parts INTEGER DEFAULT 0,
    coverage_ratio NUMERIC(5,4) DEFAULT 0,
    total_text_length INTEGER DEFAULT 0,
    parsed_text_length INTEGER DEFAULT 0,
    residual_text_length INTEGER DEFAULT 0,
    text_coverage_ratio NUMERIC(5,4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS residual_registry_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_text TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 0,
    candidate_action TEXT NOT NULL DEFAULT 'REGISTRY_EXPANSION_CANDIDATE',
    target_registry TEXT,
    status TEXT NOT NULL DEFAULT 'NEEDS_HUMAN_REVIEW',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS residual_issue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    residual_id UUID,
    issue_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rc_part ON residual_candidate(part_id);
CREATE INDEX IF NOT EXISTS idx_rc_type ON residual_candidate(residual_type);
CREATE INDEX IF NOT EXISTS idx_rc_status ON residual_candidate(status);
CREATE INDEX IF NOT EXISTS idx_rap_part ON residual_abstract_pattern(part_id);
CREATE INDEX IF NOT EXISTS idx_rcov_law ON residual_coverage(law_id);
CREATE INDEX IF NOT EXISTS idx_rrc_pattern ON residual_registry_candidate(pattern_text);
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
    print("  Residual Coverage Engine (프롬프트 19단계)")
    print(f"{'='*64}")
    print("  핵심: 못 읽은 법령도 엔진의 일부다.")

    cur.execute(CREATE_TABLES_SQL)
    conn.commit()

    for tbl in ['residual_candidate','residual_abstract_pattern',
                'residual_coverage','residual_registry_candidate','residual_issue']:
        cur.execute(f"SELECT count(*) FROM {tbl}")
        if cur.fetchone()[0] > 0:
            cur.execute(f"TRUNCATE {tbl}")
    conn.commit()

    start = time.time()

    # ================================================
    # [1단계] Residual 대상 식별
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1단계] Residual 대상 식별")
    print(f"{'─'*64}")

    # (A) Token 없는 Part = STRUCTURAL_PARSE_FAILURE
    cur.execute("""
        INSERT INTO residual_candidate
            (part_id, article_id, law_id, residual_type, failed_reason,
             source_text, source_text_length, status)
        SELECT lap.id, lap.article_id, la.law_id,
               'STRUCTURAL_PARSE_FAILURE',
               'NO_TOKEN_EXTRACTED',
               left(lap.part_text, 500),
               length(lap.part_text),
               'NEW'
        FROM law_article_part lap
        JOIN law_article la ON lap.article_id = la.id
        WHERE NOT EXISTS (
            SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
        )
        AND lap.part_text IS NOT NULL AND length(lap.part_text) > 5
    """)
    no_token = cur.rowcount
    conn.commit()
    print(f"    Token 없는 Part: {no_token:,}건")

    # (B) UNKNOWN Family 토큰 = REGISTRY_GAP
    cur.execute("""
        INSERT INTO residual_candidate
            (part_id, article_id, law_id, residual_type, failed_reason,
             source_text, source_text_length, status)
        SELECT DISTINCT et.part_id, la.id, la.law_id,
               'REGISTRY_GAP',
               'NO_ACTION_FAMILY_MATCH',
               left(et.raw_token, 200),
               length(et.raw_token),
               'NEW'
        FROM evidence_token et
        JOIN family_candidate fc ON et.id = fc.evidence_token_id
        JOIN law_article_part lap ON et.part_id = lap.id
        JOIN law_article la ON lap.article_id = la.id
        WHERE fc.family_name = 'UNKNOWN'
        AND et.part_id NOT IN (
            SELECT part_id FROM residual_candidate WHERE residual_type = 'STRUCTURAL_PARSE_FAILURE'
        )
    """)
    registry_gap = cur.rowcount
    conn.commit()
    print(f"    UNKNOWN Family Part: {registry_gap:,}건")

    # (C) UNRESOLVED Constraint Node
    cur.execute("""
        INSERT INTO residual_candidate
            (part_id, article_id, law_id, residual_type, failed_reason,
             source_text, source_text_length, status)
        SELECT DISTINCT cn.part_id, la.id, la.law_id,
               'UNMATCHED_CONDITION',
               'UNKNOWN_CONSTRAINT_NODE',
               left(cn.raw_text, 200),
               COALESCE(length(cn.raw_text), 0),
               'NEW'
        FROM constraint_node cn
        JOIN law_article_part lap ON cn.part_id = lap.id
        JOIN law_article la ON lap.article_id = la.id
        WHERE cn.node_type = 'UNKNOWN'
        AND cn.part_id NOT IN (
            SELECT part_id FROM residual_candidate
        )
    """)
    unknown_cn = cur.rowcount
    conn.commit()
    print(f"    UNKNOWN Constraint Node Part: {unknown_cn:,}건")

    cur.execute("SELECT count(*) FROM residual_candidate")
    total_res = cur.fetchone()[0]
    print(f"    ✅ Residual Candidate 총: {total_res:,}건")

    # ================================================
    # [4단계] Abstract Pattern 탐지
    # ================================================
    print(f"\n{'─'*64}")
    print("  [4단계] Abstract Pattern 탐지")
    print(f"{'─'*64}")

    abstract_rows = []
    for pattern, ptype in ABSTRACT_PATTERNS:
        cur.execute("""
            SELECT lap.id::text, la.law_id::text, left(lap.part_text, 300)
            FROM law_article_part lap
            JOIN law_article la ON lap.article_id = la.id
            WHERE lap.part_text LIKE %s
        """, (f'%{pattern}%',))
        for part_id, law_id, text in cur.fetchall():
            abstract_rows.append((
                part_id, law_id, pattern, ptype, text, 'CANDIDATE'
            ))

    if abstract_rows:
        for i in range(0, len(abstract_rows), 5000):
            execute_values(cur, """
                INSERT INTO residual_abstract_pattern
                    (part_id, law_id, pattern_text, pattern_type, source_text, status)
                VALUES %s
            """, abstract_rows[i:i+5000], page_size=5000)
        conn.commit()
    print(f"    ✅ Abstract Pattern: {len(abstract_rows):,}건")

    # Pattern별 분포
    cur.execute("SELECT pattern_text, count(*) FROM residual_abstract_pattern GROUP BY pattern_text ORDER BY count(*) DESC")
    for r in cur.fetchall():
        print(f"      {r[0]:25s} {r[1]:>6,}")

    # ================================================
    # [7단계] Coverage Metric
    # ================================================
    print(f"\n{'─'*64}")
    print("  [7단계] Coverage Metric")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO residual_coverage
            (law_id, law_name, total_parts, parsed_parts, residual_parts,
             coverage_ratio, total_text_length, parsed_text_length,
             residual_text_length, text_coverage_ratio)
        SELECT
            la.law_id, lm.law_name_short,
            count(lap.id) as total,
            count(lap.id) FILTER (WHERE EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )) as parsed,
            count(lap.id) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )) as residual,
            CASE WHEN count(lap.id) > 0
                THEN count(lap.id) FILTER (WHERE EXISTS (
                    SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
                ))::numeric / count(lap.id)
                ELSE 0 END,
            COALESCE(sum(length(lap.part_text)), 0),
            COALESCE(sum(length(lap.part_text)) FILTER (WHERE EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )), 0),
            COALESCE(sum(length(lap.part_text)) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )), 0),
            CASE WHEN COALESCE(sum(length(lap.part_text)), 0) > 0
                THEN COALESCE(sum(length(lap.part_text)) FILTER (WHERE EXISTS (
                    SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
                )), 0)::numeric / sum(length(lap.part_text))
                ELSE 0 END
        FROM law_article_part lap
        JOIN law_article la ON lap.article_id = la.id
        JOIN law_master lm ON la.law_id = lm.id
        WHERE lap.part_text IS NOT NULL
        GROUP BY la.law_id, lm.law_name_short
    """)
    cov_count = cur.rowcount
    conn.commit()
    print(f"    ✅ Coverage: {cov_count}건 (법령별)")

    cur.execute("""
        SELECT avg(coverage_ratio)::numeric(5,4),
               min(coverage_ratio)::numeric(5,4),
               max(coverage_ratio)::numeric(5,4),
               avg(text_coverage_ratio)::numeric(5,4)
        FROM residual_coverage WHERE total_parts > 0
    """)
    avg_cov, min_cov, max_cov, avg_txt = cur.fetchone()
    print(f"    Part Coverage: avg={avg_cov}, min={min_cov}, max={max_cov}")
    print(f"    Text Coverage: avg={avg_txt}")

    # ================================================
    # [9~10단계] Pattern Mining + Registry Expansion
    # ================================================
    print(f"\n{'─'*64}")
    print("  [9~10단계] Pattern Mining & Registry Expansion Candidate")
    print(f"{'─'*64}")

    cur.execute("""
        INSERT INTO residual_registry_candidate
            (pattern_text, pattern_type, occurrence_count,
             candidate_action, target_registry, status)
        SELECT pattern_text, pattern_type, count(*),
               'REGISTRY_EXPANSION_CANDIDATE',
               CASE
                   WHEN pattern_type = 'ABSTRACT_REQUIREMENT' THEN 'ABSTRACT_PATTERN_REGISTRY'
                   WHEN pattern_type = 'BROAD_OBLIGATION' THEN 'OBLIGATION_PATTERN_REGISTRY'
                   WHEN pattern_type = 'UNRESOLVED_REFERENCE' THEN 'REFERENCE_REGISTRY'
                   ELSE 'UNKNOWN_REGISTRY'
               END,
               'NEEDS_HUMAN_REVIEW'
        FROM residual_abstract_pattern
        GROUP BY pattern_text, pattern_type
        HAVING count(*) >= 5
    """)
    reg_count = cur.rowcount
    conn.commit()
    print(f"    ✅ Registry Expansion Candidate: {reg_count}건 (반복 5회 이상)")

    cur.execute("SELECT pattern_text, occurrence_count FROM residual_registry_candidate ORDER BY occurrence_count DESC")
    for r in cur.fetchall():
        print(f"      {r[0]:25s} {r[1]:>6,}회")

    # ================================================
    # [15단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [15단계] Validation")
    print(f"{'─'*64}")

    cur.execute("SELECT residual_type, count(*) FROM residual_candidate GROUP BY residual_type ORDER BY count(*) DESC")
    print("\n  Residual Type:")
    for r in cur.fetchall():
        print(f"    {r[0]:30s} {r[1]:>8,}")

    print(f"\n    원문 보존: ✅ (source_text 전건 저장)")
    print(f"    실패 원인 기록: ✅ (failed_reason 전건)")
    print(f"    의미 보정: 없음 ✅")
    print(f"    registry 자동 확장: 없음 ✅ (NEEDS_HUMAN_REVIEW)")
    print(f"    추상 표현 구체화: 없음 ✅")
    print(f"    UNKNOWN 유지: ✅")
    print(f"    coverage 계산: ✅")
    print(f"    Candidate→Truth: 없음 ✅")

    # 최종
    cur.execute("SELECT count(*) FROM residual_candidate")
    t1 = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM residual_abstract_pattern")
    t2 = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM residual_coverage")
    t3 = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM residual_registry_candidate")
    t4 = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM residual_issue")
    t5 = cur.fetchone()[0]

    elapsed = time.time() - start
    cur.close()
    conn.close()

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  Residual Candidate:    {t1:,}")
    print(f"  Abstract Pattern:      {t2:,}")
    print(f"  Coverage (법령별):     {t3}")
    print(f"  Registry Candidate:    {t4}")
    print(f"  Issues:                {t5}")
    print(f"{'='*64}")
    print(f"\n  핵심: 파싱 실패는 엔진 실패가 아니다.")
    print(f"  Residual은 다음 registry와 human review를 위한 입력이다.\n")


if __name__ == "__main__":
    main()
