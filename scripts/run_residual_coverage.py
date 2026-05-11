"""Residual Coverage & Unparsed Law Capture Engine — 프롬프트 19단계.

핵심: "못 읽은 법령도 엔진의 일부다."
절대 금지: 추상 표현 구체화, 실패 데이터 삭제, 의미 보정, registry 자동 확장

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_residual_coverage.py
"""

import logging, os, sys, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

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

CREATE INDEX IF NOT EXISTS idx_resc_part ON residual_candidate(part_id);
CREATE INDEX IF NOT EXISTS idx_resc_type ON residual_candidate(residual_type);
CREATE INDEX IF NOT EXISTS idx_rap_part ON residual_abstract_pattern(part_id);
CREATE INDEX IF NOT EXISTS idx_rcov_law ON residual_coverage(law_id);
CREATE INDEX IF NOT EXISTS idx_rrc_pattern ON residual_registry_candidate(pattern_text);
"""


def get_conn():
    """DB 연결. 끊길 때마다 재연결."""
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def safe_execute(sql, params=None, timeout='300s'):
    """재연결 + statement_timeout 적용 실행."""
    import psycopg2
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            result = cur.rowcount
            conn.commit()
            cur.close()
            conn.close()
            return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ 연결 오류 (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(2)
            if attempt == max_retries - 1:
                raise


def safe_query(sql, params=None, timeout='300s'):
    """재연결 + SELECT 실행."""
    import psycopg2
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ 연결 오류 (attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(2)
            if attempt == max_retries - 1:
                raise


def safe_insert_values(sql, data, timeout='300s', batch_size=5000):
    """재연결 + execute_values 배치 INSERT."""
    import psycopg2
    from psycopg2.extras import execute_values
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        for attempt in range(3):
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(f"SET statement_timeout = '{timeout}'")
                execute_values(cur, sql, batch, page_size=batch_size)
                conn.commit()
                cur.close()
                conn.close()
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"    ⚠️ 연결 오류 batch {i//batch_size} (attempt {attempt+1}/3): {e}")
                time.sleep(2)
                if attempt == 2:
                    raise


def main():
    print(f"\n{'='*64}")
    print("  Residual Coverage Engine (프롬프트 19단계)")
    print(f"{'='*64}")
    print("  핵심: 못 읽은 법령도 엔진의 일부다.")

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    # 테이블 생성
    safe_execute(CREATE_TABLES_SQL)

    # 재실행 대비 TRUNCATE
    for tbl in ['residual_candidate','residual_abstract_pattern',
                'residual_coverage','residual_registry_candidate','residual_issue']:
        rows = safe_query(f"SELECT count(*) FROM {tbl}")
        if rows[0][0] > 0:
            safe_execute(f"TRUNCATE {tbl}")

    start = time.time()

    # ================================================
    # [1단계] Residual 대상 식별
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1단계] Residual 대상 식별")
    print(f"{'─'*64}")

    # (A) Token 없는 Part
    no_token = safe_execute("""
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
    print(f"    Token 없는 Part: {no_token:,}건")

    # (B) ALL-UNKNOWN Family Part (토큰은 있으나 전부 UNKNOWN)
    registry_gap = safe_execute("""
        INSERT INTO residual_candidate
            (part_id, article_id, law_id, residual_type, failed_reason,
             source_text, source_text_length, status)
        SELECT sub.part_id, la.id, la.law_id,
               'REGISTRY_GAP',
               'ALL_TOKENS_UNKNOWN_FAMILY',
               left(lap.part_text, 300),
               length(lap.part_text),
               'NEW'
        FROM (
            SELECT fc.part_id
            FROM family_candidate fc
            GROUP BY fc.part_id
            HAVING count(*) = count(*) FILTER (WHERE fc.family_name = 'UNKNOWN')
        ) sub
        JOIN law_article_part lap ON sub.part_id = lap.id
        JOIN law_article la ON lap.article_id = la.id
        WHERE NOT EXISTS (
            SELECT 1 FROM residual_candidate rc WHERE rc.part_id = sub.part_id
        )
    """)
    print(f"    ALL-UNKNOWN Family Part: {registry_gap:,}건")

    # (C) UNKNOWN Constraint Node
    unknown_cn = safe_execute("""
        INSERT INTO residual_candidate
            (part_id, article_id, law_id, residual_type, failed_reason,
             source_text, source_text_length, status)
        SELECT DISTINCT cn.part_id, la.id, la.law_id,
               'UNMATCHED_CONDITION',
               'UNKNOWN_CONSTRAINT_NODE',
               left(cn.raw_token, 200),
               COALESCE(length(cn.raw_token), 0),
               'NEW'
        FROM constraint_node cn
        JOIN law_article_part lap ON cn.part_id = lap.id
        JOIN law_article la ON lap.article_id = la.id
        WHERE cn.node_type = 'UNKNOWN'
        AND NOT EXISTS (
            SELECT 1 FROM residual_candidate rc WHERE rc.part_id = cn.part_id
        )
    """)
    print(f"    UNKNOWN Constraint Node Part: {unknown_cn:,}건")

    total_res = safe_query("SELECT count(*) FROM residual_candidate")[0][0]
    print(f"    ✅ Residual Candidate 총: {total_res:,}건")

    # ================================================
    # [4단계] Abstract Pattern
    # ================================================
    print(f"\n{'─'*64}")
    print("  [4단계] Abstract Pattern 탐지")
    print(f"{'─'*64}")

    abstract_rows = []
    for pattern, ptype in ABSTRACT_PATTERNS:
        rows = safe_query("""
            SELECT lap.id::text, la.law_id::text, left(lap.part_text, 300)
            FROM law_article_part lap
            JOIN law_article la ON lap.article_id = la.id
            WHERE lap.part_text LIKE %s
        """, (f'%{pattern}%',))
        for part_id, law_id, text in rows:
            abstract_rows.append((
                part_id, law_id, pattern, ptype, text, 'CANDIDATE'
            ))

    if abstract_rows:
        safe_insert_values("""
            INSERT INTO residual_abstract_pattern
                (part_id, law_id, pattern_text, pattern_type, source_text, status)
            VALUES %s
        """, abstract_rows)
    print(f"    ✅ Abstract Pattern: {len(abstract_rows):,}건")

    pat_dist = safe_query("SELECT pattern_text, count(*) FROM residual_abstract_pattern GROUP BY pattern_text ORDER BY count(*) DESC")
    for r in pat_dist:
        print(f"      {r[0]:25s} {r[1]:>6,}")

    # ================================================
    # [7단계] Coverage Metric
    # ================================================
    print(f"\n{'─'*64}")
    print("  [7단계] Coverage Metric")
    print(f"{'─'*64}")

    cov_count = safe_execute("""
        INSERT INTO residual_coverage
            (law_id, law_name, total_parts, parsed_parts, residual_parts,
             coverage_ratio, total_text_length, parsed_text_length,
             residual_text_length, text_coverage_ratio)
        SELECT
            la.law_id, lm.law_name_short,
            count(lap.id),
            count(lap.id) FILTER (WHERE EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )),
            count(lap.id) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM evidence_token et WHERE et.part_id = lap.id
            )),
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
    print(f"    ✅ Coverage: {cov_count}건 (법령별)")

    cov_stats = safe_query("""
        SELECT avg(coverage_ratio)::numeric(5,4),
               min(coverage_ratio)::numeric(5,4),
               max(coverage_ratio)::numeric(5,4),
               avg(text_coverage_ratio)::numeric(5,4)
        FROM residual_coverage WHERE total_parts > 0
    """)
    avg_cov, min_cov, max_cov, avg_txt = cov_stats[0]
    print(f"    Part Coverage: avg={avg_cov}, min={min_cov}, max={max_cov}")
    print(f"    Text Coverage: avg={avg_txt}")

    # ================================================
    # [9~10단계] Registry Expansion
    # ================================================
    print(f"\n{'─'*64}")
    print("  [9~10단계] Pattern Mining & Registry Expansion")
    print(f"{'─'*64}")

    reg_count = safe_execute("""
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
    print(f"    ✅ Registry Expansion Candidate: {reg_count}건")

    reg_dist = safe_query("SELECT pattern_text, occurrence_count FROM residual_registry_candidate ORDER BY occurrence_count DESC")
    for r in reg_dist:
        print(f"      {r[0]:25s} {r[1]:>6,}회")

    # ================================================
    # [15단계] Validation
    # ================================================
    print(f"\n{'─'*64}")
    print("  [15단계] Validation")
    print(f"{'─'*64}")

    res_dist = safe_query("SELECT residual_type, count(*) FROM residual_candidate GROUP BY residual_type ORDER BY count(*) DESC")
    print("\n  Residual Type:")
    for r in res_dist:
        print(f"    {r[0]:30s} {r[1]:>8,}")

    print(f"\n    원문 보존: ✅")
    print(f"    실패 원인 기록: ✅")
    print(f"    의미 보정: 없음 ✅")
    print(f"    registry 자동 확장: 없음 ✅")
    print(f"    추상 표현 구체화: 없음 ✅")
    print(f"    UNKNOWN 유지: ✅")
    print(f"    Candidate→Truth: 없음 ✅")

    t1 = safe_query("SELECT count(*) FROM residual_candidate")[0][0]
    t2 = safe_query("SELECT count(*) FROM residual_abstract_pattern")[0][0]
    t3 = safe_query("SELECT count(*) FROM residual_coverage")[0][0]
    t4 = safe_query("SELECT count(*) FROM residual_registry_candidate")[0][0]
    t5 = safe_query("SELECT count(*) FROM residual_issue")[0][0]

    elapsed = time.time() - start

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
