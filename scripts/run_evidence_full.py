"""증거 기반 파싱 전체 실행 — Stage 1 + Stage 2.

143,549 law_article_part 전체 대상.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_evidence_full.py
"""

import logging
import sys
import os
import time

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.evidence_extractor import extract_evidence
from engine.evidence_normalizer import load_registry, normalize_tokens

BATCH_SIZE = 500


def fetch_batch(conn, offset, limit):
    """OFFSET/LIMIT으로 배치 조회."""
    cur = conn.cursor()
    cur.execute("""
        SELECT lap.id::text, lap.part_text
        FROM law_article_part lap
        WHERE lap.part_text IS NOT NULL AND lap.part_text != ''
        ORDER BY lap.id
        OFFSET %s LIMIT %s
    """, (offset, limit))
    rows = cur.fetchall()
    cur.close()
    return rows


def save_batch(conn, results, normalized_all):
    """배치 단위 DB 저장."""
    import json
    cur = conn.cursor()

    for result in results:
        for tok in result.tokens:
            cur.execute("""
                INSERT INTO evidence_token (part_id, token_type, value, span_start, span_end, source_text)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (tok.part_id, tok.token_type, tok.value, tok.span_start, tok.span_end, tok.source_text))

        for cand in result.candidates:
            cur.execute("""
                INSERT INTO evidence_candidate (part_id, candidate_type, candidate_value, status, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (cand.part_id, cand.candidate_type, cand.candidate_value, cand.status, cand.reason))

        for rel in result.relations:
            cur.execute("""
                INSERT INTO evidence_relation
                    (part_id, actor_candidate, action_candidate, target_candidate,
                     condition_candidate, exception_candidate, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (rel.part_id, rel.actor_candidate, rel.action_candidate,
                  rel.target_candidate, rel.condition_candidate,
                  rel.exception_candidate, rel.status))

        cur.execute("""
            INSERT INTO evidence_validation (part_id, validation_status, total_tokens, valid_tokens, issues)
            VALUES (%s, %s, %s, %s, %s)
        """, (result.part_id, result.validation_status,
              len(result.tokens) + len(result.issues), len(result.tokens),
              json.dumps([{"type": i.issue_type, "detail": i.detail} for i in result.issues], ensure_ascii=False)))

        for iss in result.issues:
            cur.execute("""
                INSERT INTO evidence_issue (part_id, issue_type, detail, source_text)
                VALUES (%s, %s, %s, %s)
            """, (iss.part_id, iss.issue_type,
                  json.dumps(iss.detail, ensure_ascii=False), iss.source_text))

    for n in normalized_all:
        cur.execute("""
            INSERT INTO evidence_normalized
                (token_id, part_id, raw_token, canonical_token, normalization_type,
                 family, family_status, source_span_start, source_span_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(n.token_id) if n.token_id else None, n.part_id,
            n.raw_token, n.canonical_token, n.normalization_type,
            n.family, n.family_status, n.span_start, n.span_end,
        ))

    conn.commit()
    cur.close()


def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)

    registry = load_registry(conn)
    print(f"\n  📚 Registry: {len(registry)}개 canonical token")

    total = 143549
    offset = 0
    processed = 0
    s1_tokens = 0
    s2_normalized = 0
    s2_candidate = 0
    s2_unresolved = 0
    start = time.time()

    print(f"\n{'='*60}")
    print(f"  Stage 1 + Stage 2 전체 실행 — {total}건")
    print(f"{'='*60}\n")

    while offset < total:
        rows = fetch_batch(conn, offset, BATCH_SIZE)
        if not rows:
            break

        batch_results = []
        batch_normalized = []

        for part_id, part_text in rows:
            result = extract_evidence(part_id, part_text)
            s1_tokens += len(result.tokens)

            tok_dicts = [
                {"id": None, "token_type": t.token_type, "value": t.value,
                 "span_start": t.span_start, "span_end": t.span_end}
                for t in result.tokens
            ]
            normalized = normalize_tokens(conn, part_id, tok_dicts, registry)
            s2_normalized += len(normalized)
            s2_candidate += sum(1 for n in normalized if n.family_status == "CANDIDATE")
            s2_unresolved += sum(1 for n in normalized if n.family_status == "UNRESOLVED")

            batch_results.append(result)
            batch_normalized.extend(normalized)
            processed += 1

        try:
            save_batch(conn, batch_results, batch_normalized)
        except Exception as e:
            print(f"\n  ❌ DB 저장 오류 (offset {offset}): {e}")
            conn.rollback()

        offset += BATCH_SIZE
        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0
        print(
            f"  [{processed:>6}/{total}] "
            f"S1:{s1_tokens} S2:{s2_normalized} "
            f"C:{s2_candidate} U:{s2_unresolved} "
            f"({elapsed:.0f}s ~{eta:.0f}s)"
        )

    conn.close()
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"  완료 ({elapsed:.1f}초)")
    print(f"{'='*60}")
    print(f"  처리: {processed}건")
    print(f"  S1 토큰: {s1_tokens}건")
    print(f"  S2 정규화: {s2_normalized}건 (C:{s2_candidate} U:{s2_unresolved})")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
