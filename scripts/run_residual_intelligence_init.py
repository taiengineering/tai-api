"""Residual Intelligence 초기 데이터 이전 스크립트.

기존 residual_candidate(111,142건) → residuals 테이블로 이전.
기존 residual_abstract_pattern(10,020건) → residual_patterns로 이전.
registry_gaps 생성.
review_queue 생성.
audit_log 기록.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_residual_intelligence_init.py
"""
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def get_conn():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    return conn

def safe_execute(sql, params=None, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql, params) if params else cur.execute(sql)
            result = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise

def safe_query(sql, params=None, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql, params) if params else cur.execute(sql)
            rows = cur.fetchall()
            cur.close(); conn.close()
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    ⚠️ retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise


def main():
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL 미설정"); sys.exit(1)

    print(f"\n{'='*64}")
    print("  Residual Intelligence Init")
    print(f"{'='*64}")

    start = time.time()

    # 재실행 대비
    for tbl in ['residual_cluster_items','residual_clusters','residual_failed_reasons',
                'review_queue','human_review_decisions','registry_updates',
                'reprocessing_queue','coverage_metrics','ri_audit_logs']:
        try:
            cnt = safe_query(f"SELECT count(*) FROM {tbl}")[0][0]
            if cnt > 0:
                safe_execute(f"DELETE FROM {tbl}")
                print(f"  클리어: {tbl} ({cnt}건)")
        except Exception:
            pass

    # residuals 테이블 비우기 (외래키 참조 있으므로 마지막에)
    try:
        cnt = safe_query("SELECT count(*) FROM residuals")[0][0]
        if cnt > 0:
            safe_execute("DELETE FROM residuals")
            print(f"  클리어: residuals ({cnt}건)")
    except Exception:
        pass

    # residual_patterns 비우기
    try:
        cnt = safe_query("SELECT count(*) FROM residual_patterns")[0][0]
        if cnt > 0:
            safe_execute("DELETE FROM residual_patterns")
    except Exception:
        pass

    # registry_gaps 비우기
    try:
        cnt = safe_query("SELECT count(*) FROM registry_gaps")[0][0]
        if cnt > 0:
            safe_execute("DELETE FROM registry_gaps")
    except Exception:
        pass

    # ================================================
    # [1] residual_candidate → residuals 이전
    # ================================================
    print(f"\n{'─'*64}")
    print("  [1] residual_candidate → residuals 이전")
    print(f"{'─'*64}")

    cnt = safe_execute("""
        INSERT INTO residuals
            (part_id, law_id, source_text, residual_text,
             source_span_start, source_span_end,
             residual_type, status)
        SELECT
            rc.part_id, rc.law_id,
            rc.source_text, rc.source_text,
            0, rc.source_text_length,
            rc.residual_type, rc.status
        FROM residual_candidate rc
    """)
    print(f"    ✅ Residuals: {cnt:,}건")

    # failed_reasons 추가
    cnt2 = safe_execute("""
        INSERT INTO residual_failed_reasons (residual_id, failed_reason)
        SELECT r.id, 
            CASE rc.failed_reason
                WHEN 'NO_TOKEN_EXTRACTED' THEN 'STRUCTURE_NOT_SUPPORTED'
                WHEN 'ALL_TOKENS_UNKNOWN_FAMILY' THEN 'NO_ACTION_FAMILY_MATCH'
                WHEN 'UNKNOWN_CONSTRAINT_NODE' THEN 'RELATION_OUT_OF_SCOPE'
                ELSE 'HUMAN_REVIEW_REQUIRED'
            END
        FROM residuals r
        JOIN residual_candidate rc ON r.part_id = rc.part_id AND r.law_id = rc.law_id
    """)
    print(f"    ✅ Failed Reasons: {cnt2:,}건")

    # ================================================
    # [2] Pattern Mining
    # ================================================
    print(f"\n{'─'*64}")
    print("  [2] Pattern Mining")
    print(f"{'─'*64}")

    cnt3 = safe_execute("""
        INSERT INTO residual_patterns
            (pattern_text, pattern_type, occurrence_count, related_law_count, status)
        SELECT pattern_text, pattern_type, count(*),
               count(DISTINCT law_id),
               'PATTERN_CANDIDATE'
        FROM residual_abstract_pattern
        GROUP BY pattern_text, pattern_type
    """)
    print(f"    ✅ Patterns: {cnt3}건")

    # ================================================
    # [3] Cluster Build
    # ================================================
    print(f"\n{'─'*64}")
    print("  [3] Cluster Build (반복 10회 이상)")
    print(f"{'─'*64}")

    cnt4 = safe_execute("""
        INSERT INTO residual_clusters
            (cluster_name, representative_pattern, occurrence_count, status)
        SELECT
            'CLUSTER_' || pattern_type || '_' || left(pattern_text, 20),
            pattern_text, occurrence_count, 'NEEDS_HUMAN_REVIEW'
        FROM residual_patterns
        WHERE occurrence_count >= 10
    """)
    print(f"    ✅ Clusters: {cnt4}건")

    # ================================================
    # [4] Registry Gaps
    # ================================================
    print(f"\n{'─'*64}")
    print("  [4] Registry Gaps")
    print(f"{'─'*64}")

    cnt5 = safe_execute("""
        INSERT INTO registry_gaps
            (target_registry, unmatched_token, occurrence_count, status)
        SELECT
            CASE
                WHEN pattern_type = 'ABSTRACT_REQUIREMENT' THEN 'ACTION_REGISTRY'
                WHEN pattern_type = 'BROAD_OBLIGATION' THEN 'CONDITION_REGISTRY'
                WHEN pattern_type = 'UNRESOLVED_REFERENCE' THEN 'REFERENCE_REGISTRY'
                ELSE 'FAMILY_REGISTRY'
            END,
            pattern_text, occurrence_count, 'EXPANSION_CANDIDATE'
        FROM residual_patterns
        WHERE occurrence_count >= 5
    """)
    print(f"    ✅ Registry Gaps: {cnt5}건")

    # ================================================
    # [5] Review Queue 생성
    # ================================================
    print(f"\n{'─'*64}")
    print("  [5] Review Queue")
    print(f"{'─'*64}")

    # Cluster → Review
    cnt6 = safe_execute("""
        INSERT INTO review_queue (review_type, cluster_id, reason, status)
        SELECT 'CLUSTER_REVIEW', id,
               'Repeated pattern: ' || representative_pattern || ' (' || occurrence_count || ' times)',
               'PENDING_REVIEW'
        FROM residual_clusters
    """)
    print(f"    Cluster Review: {cnt6}건")

    # Registry Gap → Review
    cnt7 = safe_execute("""
        INSERT INTO review_queue (review_type, registry_gap_id, reason, status)
        SELECT 'REGISTRY_EXPANSION_REVIEW', id,
               'Gap in ' || target_registry || ': ' || unmatched_token || ' (' || occurrence_count || ' times)',
               'PENDING_REVIEW'
        FROM registry_gaps
    """)
    print(f"    Registry Gap Review: {cnt7}건")

    total_rq = safe_query("SELECT count(*) FROM review_queue")[0][0]
    print(f"    ✅ Review Queue 총: {total_rq}건")

    # ================================================
    # [6] Audit Log
    # ================================================
    safe_execute("""
        INSERT INTO ri_audit_logs (entity_type, action, after_data)
        VALUES ('SYSTEM', 'RESIDUAL_INTELLIGENCE_INIT', '{"status": "completed"}')
    """)

    # ================================================
    # 최종
    # ================================================
    t1 = safe_query("SELECT count(*) FROM residuals")[0][0]
    t2 = safe_query("SELECT count(*) FROM residual_failed_reasons")[0][0]
    t3 = safe_query("SELECT count(*) FROM residual_patterns")[0][0]
    t4 = safe_query("SELECT count(*) FROM residual_clusters")[0][0]
    t5 = safe_query("SELECT count(*) FROM registry_gaps")[0][0]
    t6 = safe_query("SELECT count(*) FROM review_queue")[0][0]
    t7 = safe_query("SELECT count(*) FROM ri_audit_logs")[0][0]

    elapsed = time.time() - start

    print(f"\n{'='*64}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*64}")
    print(f"  residuals:              {t1:,}")
    print(f"  failed_reasons:         {t2:,}")
    print(f"  patterns:               {t3}")
    print(f"  clusters:               {t4}")
    print(f"  registry_gaps:          {t5}")
    print(f"  review_queue:           {t6}")
    print(f"  audit_logs:             {t7}")
    print(f"{'='*64}")
    print(f"\n  핵심: 애매함은 제거 대상이 아니라 관리 대상이다.\n")


if __name__ == "__main__":
    main()
