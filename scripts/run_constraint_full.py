"""Constraint Graph 전체 실행 — family_candidate → constraint_node + constraint_edge.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_constraint_full.py
"""

import logging
import sys
import os
import time

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.constraint_builder import build_constraint_graph, validate_graph, save_constraint_graph

BATCH_SIZE = 500


def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)

    # 대상 part_id 목록 (family_candidate에 있는 것)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT part_id::text FROM family_candidate ORDER BY part_id")
    part_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    total = len(part_ids)

    print(f"\n{'='*60}")
    print(f"  Constraint Graph 생성 — {total}개 part")
    print(f"{'='*60}\n")

    processed = 0
    node_total = 0
    edge_total = 0
    issue_total = 0
    start = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch_ids = part_ids[i:i + BATCH_SIZE]
        batch_nodes = []
        batch_edges = []

        for part_id in batch_ids:
            cur = conn.cursor()
            cur.execute("""
                SELECT family_name, raw_token, canonical_token,
                       source_span_start, source_span_end, status
                FROM family_candidate
                WHERE part_id = %s
            """, (part_id,))
            rows = [
                {"family_name": r[0], "raw_token": r[1], "canonical_token": r[2],
                 "source_span_start": r[3], "source_span_end": r[4], "status": r[5]}
                for r in cur.fetchall()
            ]
            cur.close()

            if not rows:
                processed += 1
                continue

            nodes, edges = build_constraint_graph(part_id, rows)
            issues = validate_graph(nodes, edges)

            batch_nodes.extend(nodes)
            batch_edges.extend(edges)
            node_total += len(nodes)
            edge_total += len(edges)
            issue_total += len(issues)
            processed += 1

        try:
            save_constraint_graph(conn, batch_nodes, batch_edges)
        except Exception as e:
            print(f"\n  ❌ DB 오류 (offset {i}): {e}")
            conn.rollback()

        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0
        print(
            f"  [{processed:>6}/{total}] "
            f"N:{node_total} E:{edge_total} I:{issue_total} "
            f"({elapsed:.0f}s ~{eta:.0f}s)"
        )

    conn.close()
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*60}")
    print(f"  처리: {processed}건")
    print(f"  Constraint Node: {node_total}건")
    print(f"  Constraint Edge: {edge_total}건")
    print(f"  Issues: {issue_total}건")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
