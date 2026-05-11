"""Admin Review Queue 초기화 — 기존 데이터로 admin_review_queue 채움.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_admin_review_init.py
"""
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def get_conn():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    return conn

def safe_execute(sql, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql)
            result = cur.rowcount
            conn.commit(); cur.close(); conn.close()
            return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    \u26a0\ufe0f retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise

def safe_query(sql, timeout='300s'):
    import psycopg2
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(f"SET statement_timeout = '{timeout}'")
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close(); conn.close()
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"    \u26a0\ufe0f retry {attempt+1}/3: {e}")
            time.sleep(2)
            if attempt == 2: raise


def main():
    if not os.environ.get("DATABASE_URL"):
        print("\u274c DATABASE_URL \ubbf8\uc124\uc815"); sys.exit(1)

    print(f"\n{'='*64}")
    print("  Admin Review Queue Init")
    print(f"{'='*64}")

    start = time.time()

    # 재실행 대비
    safe_execute("DELETE FROM admin_audit_logs")
    safe_execute("DELETE FROM admin_reprocessing_queue")
    safe_execute("DELETE FROM admin_review_queue")
    safe_execute("DELETE FROM registry_versions")

    # ================================================
    # [1] Cluster → Admin Review
    # ================================================
    print(f"\n  [1] Cluster → Admin Review")
    cnt1 = safe_execute("""
        INSERT INTO admin_review_queue
            (review_type, target_entity_type, target_entity_id,
             title, source_text, occurrence_count, status)
        SELECT 'CLUSTER_REVIEW', 'residual_clusters', id,
               'Cluster: ' || cluster_name,
               representative_pattern,
               occurrence_count, 'NEW'
        FROM residual_clusters
    """)
    print(f"    \u2705 Cluster Review: {cnt1}\uac74")

    # ================================================
    # [2] Registry Gap → Admin Review
    # ================================================
    print(f"  [2] Registry Gap → Admin Review")
    cnt2 = safe_execute("""
        INSERT INTO admin_review_queue
            (review_type, target_entity_type, target_entity_id,
             title, source_text, failed_reason, occurrence_count, status)
        SELECT 'REGISTRY_EXPANSION_REVIEW', 'registry_gaps', id,
               'Gap: ' || target_registry || ' - ' || unmatched_token,
               unmatched_token,
               'Registry gap in ' || target_registry,
               occurrence_count, 'NEW'
        FROM registry_gaps
    """)
    print(f"    \u2705 Registry Gap Review: {cnt2}\uac74")

    # ================================================
    # [3] Penalty 미연결 → Admin Review
    # ================================================
    print(f"  [3] Penalty 미연결 → Admin Review")
    cnt3 = safe_execute("""
        INSERT INTO admin_review_queue
            (review_type, target_entity_type, target_entity_id,
             title, source_text, failed_reason, status)
        SELECT 'PENALTY_MAPPING_REVIEW', 'penalty_candidate', pc.id,
               'Penalty: ' || pc.penalty_family || ' - ' || left(pc.raw_token, 30),
               left(pc.source_text, 300),
               'UNKNOWN_PENALTY_FAMILY',
               'NEW'
        FROM penalty_candidate pc
        WHERE pc.penalty_family = 'UNKNOWN_PENALTY_FAMILY'
    """)
    print(f"    \u2705 Penalty Review: {cnt3}\uac74")

    # ================================================
    # [4] Compliance Conflict → Admin Review
    # ================================================
    print(f"  [4] Compatibility Conflict → Admin Review")
    cnt4 = safe_execute("""
        INSERT INTO admin_review_queue
            (review_type, target_entity_type, target_entity_id,
             title, failed_reason, status)
        SELECT 'RESIDUAL_REVIEW', 'compatibility_issue', ci.id,
               'Conflict: ' || ci.issue_type,
               ci.detail,
               'NEW'
        FROM compatibility_issue ci
        LIMIT 200
    """)
    print(f"    \u2705 Conflict Review: {cnt4}\uac74")

    # ================================================
    # [5] Audit
    # ================================================
    safe_execute("""
        INSERT INTO admin_audit_logs (action, entity_type, after_data)
        VALUES ('REVIEW_STARTED', 'SYSTEM',
                '{"event": "admin_review_queue_initialized"}')
    """)

    total = safe_query("SELECT count(*) FROM admin_review_queue")[0][0]
    elapsed = time.time() - start

    print(f"\n{'='*64}")
    print(f"  \uc644\ub8cc ({elapsed:.1f}\ucd08)")
    print(f"{'='*64}")
    print(f"  Admin Review Queue: {total}\uac74")
    print(f"{'='*64}")
    print(f"\n  \ud575\uc2ec: \uc0ac\ub78c\uc774 \uac80\ud1a0\ud55c \ubc95\ub839\ub9cc \uc5d4\uc9c4\uc5d0 \ucd94\uac00\ub41c\ub2e4.\n")


if __name__ == "__main__":
    main()
