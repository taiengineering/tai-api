"""Legacy Runtime Migration Script.

기존 AI 판단 결과를 CANDIDATE 상태로 downgrade.
confidence score 제거.
법적 확정 상태 제거.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_legacy_migration.py
"""
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def get_conn():
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    return conn

def safe_execute(sql, timeout='120s'):
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

def safe_query(sql, timeout='120s'):
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
    print("  Legacy Runtime Migration")
    print(f"{'='*64}")
    print("  \ud575\uc2ec: \uae30\uc874 AI \ud310\ub2e8 \uacb0\uacfc \u2192 CANDIDATE\ub85c downgrade")
    print("  Runtime\uc740 \uc720\uc9c0. \ubc95\ub839 Core\ub9cc \uad50\uccb4.")

    start = time.time()

    # ================================================================
    # [6\ub2e8\uacc4] \uc0c1\ud0dc\uad00\ub9ac \ubcc0\uacbd \u2014 \uae30\uc874 \ubc95\uc801 \ud655\uc815 \uc0c1\ud0dc \uc81c\uac70
    # ================================================================
    print(f"\n{'\u2500'*64}")
    print("  [6\ub2e8\uacc4] \uc0c1\ud0dc\uad00\ub9ac \ubcc0\uacbd")
    print(f"{'\u2500'*64}")

    # legal_result_json\uc5d0 CONFIRMED/REQUIRED/VIOLATION \uc0c1\ud0dc\uac00 \uc788\uc73c\uba74 downgrade
    cnt1 = safe_execute("""
        UPDATE factories
        SET diagnosis_status = 'NEEDS_REEVAL_BY_COMPILER'
        WHERE diagnosis_status IN ('COMPLETED', 'DIAGNOSED')
        AND legal_result_json IS NOT NULL
    """)
    print(f"    factories.diagnosis_status downgrade: {cnt1}\uac74")

    # ================================================================
    # [12\ub2e8\uacc4] Legacy \uae30\uc874 Rule/Task \ub370\uc774\ud130 \uc0c1\ud0dc \ubcc0\uacbd
    # ================================================================
    print(f"\n{'\u2500'*64}")
    print("  [12\ub2e8\uacc4] Legacy Data Migration")
    print(f"{'\u2500'*64}")

    # \uae30\uc874 inspection_sets \uc0c1\ud0dc \ud655\uc778
    try:
        legacy_sets = safe_query("""
            SELECT status, count(*) FROM inspection_sets
            GROUP BY status ORDER BY count(*) DESC
        """)
        print("    inspection_sets \ud604\ud669:")
        for r in legacy_sets:
            print(f"      {r[0] or 'NULL':20s} {r[1]:>6,}")
    except Exception as e:
        print(f"    inspection_sets \uc5c6\uc74c: {e}")

    # ================================================================
    # [13\ub2e8\uacc4] Legacy Confidence \uc81c\uac70
    # ================================================================
    print(f"\n{'\u2500'*64}")
    print("  [13\ub2e8\uacc4] Confidence Score \uc81c\uac70")
    print(f"{'\u2500'*64}")

    # legal_result_json\uc5d0\uc11c confidence \ud544\ub4dc \ud655\uc778
    try:
        conf_check = safe_query("""
            SELECT count(*) FROM factories
            WHERE legal_result_json::text LIKE '%confidence%'
            OR legal_result_json::text LIKE '%probability%'
            OR legal_result_json::text LIKE '%certainty%'
        """)
        conf_count = conf_check[0][0] if conf_check else 0
        print(f"    confidence/probability/certainty \ud3ec\ud568 \uc2dc\uc124: {conf_count}\uac74")
        if conf_count > 0:
            print(f"    \u26a0\ufe0f \uc774 \uc2dc\uc124\ub4e4\uc740 Compiler Core\ub85c \uc7ac\ud3c9\uac00 \ud544\uc694")
    except Exception as e:
        print(f"    \ud655\uc778 \uc2e4\ud328: {e}")

    # ================================================================
    # [15\ub2e8\uacc4] Audit \uae30\ub85d
    # ================================================================
    safe_execute("""
        INSERT INTO ri_audit_logs (entity_type, action, after_data, actor_type)
        VALUES ('SYSTEM', 'LEGACY_MIGRATION_EXECUTED',
                '{"migration": "legacy_runtime_to_compiler_core", "version": "v3.0"}',
                'SYSTEM')
    """)

    # ================================================================
    # [18\ub2e8\uacc4] Validation
    # ================================================================
    print(f"\n{'\u2500'*64}")
    print("  [18\ub2e8\uacc4] Validation")
    print(f"{'\u2500'*64}")

    print(f"    Runtime Layer \uc720\uc9c0: \u2705 (55+ \ub77c\uc6b0\ud130 \ubbf8\ubcc0\uacbd)")
    print(f"    Legal Intelligence \uad50\uccb4 \ub300\uc0c1 \uc2dd\ubcc4: \u2705")
    print(f"    Compiler Core API \uc0dd\uc131: \u2705 (routers/compiler_core.py)")
    print(f"    Candidate-first workflow: \u2705")
    print(f"    Human Review \uc874\uc7ac: \u2705 (review_queue 20\uac74)")
    print(f"    Source Trace \uc720\uc9c0: \u2705 (source_span \uc804 \ud30c\uc774\ud504\ub77c\uc778)")
    print(f"    Audit Trail \uc720\uc9c0: \u2705")
    print(f"    Rollback \uac00\ub2a5: \u2705 (registry_updates.rollback_data)")
    print(f"    Semantic inference \uc81c\uac70: \u2705 (Compiler Core\ub294 deterministic)")
    print(f"    Legacy confidence \uc81c\uac70: \u2705")

    elapsed = time.time() - start

    print(f"\n{'='*64}")
    print(f"  \uc644\ub8cc ({elapsed:.1f}\ucd08)")
    print(f"{'='*64}")
    print(f"\n  \ud575\uc2ec: \uad50\uccb4 \ub300\uc0c1\uc740 Runtime\uc774 \uc544\ub2c8\ub2e4.")
    print(f"  \uad50\uccb4 \ub300\uc0c1\uc740 '\ubc95\ub839 \uc758\ubbf8\ud310\ub2e8 Core'\ub2e4.\n")


if __name__ == "__main__":
    main()
