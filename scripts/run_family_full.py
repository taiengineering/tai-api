"""Family Grouping 전체 실행 — evidence_normalized → family_candidate + family_relation.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_family_full.py
"""

import logging
import sys
import os
import time

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.family_grouper import load_multi_registry, group_families, save_family_results

BATCH_SIZE = 500


def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)

    # Registry 로드
    registry = load_multi_registry(conn)
    multi_count = sum(1 for v in registry.values() if len(v) > 1)
    print(f"\n  📚 Registry: {len(registry)}개 canonical ({multi_count}개 Multi-Family)")

    # 대상 part_id 목록
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT part_id::text FROM evidence_normalized ORDER BY part_id")
    part_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    total = len(part_ids)

    print(f"\n{'='*60}")
    print(f"  Family Grouping — {total}개 part")
    print(f"{'='*60}\n")

    processed = 0
    fc_total = 0
    fr_total = 0
    fc_candidate = 0
    fc_ambiguous = 0
    fc_unresolved = 0
    fc_restricted = 0
    issue_total = 0
    start = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch_ids = part_ids[i:i + BATCH_SIZE]
        batch_candidates = []
        batch_relations = []

        for part_id in batch_ids:
            # normalized 데이터 조회
            cur = conn.cursor()
            cur.execute("""
                SELECT en.id::text, en.raw_token, en.canonical_token,
                       en.source_span_start, en.source_span_end
                FROM evidence_normalized en
                WHERE en.part_id = %s
            """, (part_id,))
            rows = [
                {"id": r[0], "raw_token": r[1], "canonical_token": r[2],
                 "source_span_start": r[3], "source_span_end": r[4]}
                for r in cur.fetchall()
            ]

            # source_text 조회 (Context Restriction용)
            cur.execute("SELECT part_text FROM law_article_part WHERE id = %s", (part_id,))
            st_row = cur.fetchone()
            source_text = st_row[0] if st_row else None
            cur.close()

            if not rows:
                processed += 1
                continue

            # Family Grouping 실행
            candidates, relations, issues = group_families(
                part_id, rows, registry, source_text,
            )

            batch_candidates.extend(candidates)
            batch_relations.extend(relations)

            fc_total += len(candidates)
            fr_total += len(relations)
            fc_candidate += sum(1 for c in candidates if c.status == "CANDIDATE")
            fc_ambiguous += sum(1 for c in candidates if c.status == "AMBIGUOUS")
            fc_unresolved += sum(1 for c in candidates if c.status == "UNRESOLVED")
            fc_restricted += sum(1 for c in candidates if c.status == "CONTEXT_RESTRICTED_CANDIDATE")
            issue_total += len(issues)
            processed += 1

        # 배치 저장
        try:
            save_family_results(conn, batch_candidates, batch_relations)
        except Exception as e:
            print(f"\n  ❌ DB 오류 (offset {i}): {e}")
            conn.rollback()

        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0
        print(
            f"  [{processed:>6}/{total}] "
            f"FC:{fc_total} FR:{fr_total} "
            f"C:{fc_candidate} A:{fc_ambiguous} CR:{fc_restricted} U:{fc_unresolved} "
            f"({elapsed:.0f}s ~{eta:.0f}s)"
        )

    conn.close()
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*60}")
    print(f"  처리: {processed}건")
    print(f"  Family Candidate: {fc_total}건")
    print(f"    CANDIDATE: {fc_candidate}")
    print(f"    AMBIGUOUS: {fc_ambiguous}")
    print(f"    CONTEXT_RESTRICTED: {fc_restricted}")
    print(f"    UNRESOLVED: {fc_unresolved}")
    print(f"  Family Relation: {fr_total}건")
    print(f"  Issues: {issue_total}건")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
