"""증거 기반 파싱 샘플 v2 — 소방시설법 의무 조항.

실행:
  railway run python3 scripts/run_evidence_sample.py
"""

import logging
import sys
import os

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.evidence_extractor import extract_evidence, save_result


def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # 소방시설 설치 및 관리에 관한 법률
    cur.execute("""
        SELECT lap.id::text, lap.part_text, la.article_no, la.article_title, lap.part_type
        FROM law_article_part lap
        JOIN law_article la ON la.id = lap.article_id
        JOIN law_master lm ON lm.id = la.law_id
        WHERE lm.law_name LIKE '소방시설 설치%%'
          AND la.article_type = '조문'
          AND lap.part_text IS NOT NULL AND lap.part_text != ''
          AND la.article_no BETWEEN 5 AND 30
        ORDER BY la.article_no, lap.sort_order
        LIMIT 20
    """)
    parts = cur.fetchall()

    if not parts:
        # fallback: 화학물질관리법
        cur.execute("""
            SELECT lap.id::text, lap.part_text, la.article_no, la.article_title, lap.part_type
            FROM law_article_part lap
            JOIN law_article la ON la.id = lap.article_id
            JOIN law_master lm ON lm.id = la.law_id
            WHERE lm.law_name LIKE '화학물질%%'
              AND la.article_type = '조문'
              AND lap.part_text IS NOT NULL AND lap.part_text != ''
              AND la.article_no BETWEEN 5 AND 30
            ORDER BY la.article_no, lap.sort_order
            LIMIT 20
        """)
        parts = cur.fetchall()

    cur.close()

    if not parts:
        print("❌ 대상 법령 데이터 없음")
        conn.close()
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  증거 기반 파싱 v2 — {len(parts)}개 조항")
    print(f"{'='*70}\n")

    total_tokens = 0
    total_candidates = 0
    total_issues = 0
    pass_cnt = 0
    unresolved_cnt = 0

    for part_id, part_text, article_no, article_title, part_type in parts:
        result = extract_evidence(part_id, part_text)
        saved = save_result(conn, result)

        total_tokens += len(result.tokens)
        total_candidates += len(result.candidates)
        total_issues += len(result.issues)
        if result.validation_status == "PASS":
            pass_cnt += 1
        elif result.validation_status == "UNRESOLVED":
            unresolved_cnt += 1

        title = f"제{article_no}조 ({article_title})" if article_title else f"제{article_no}조"
        pt = f"[{part_type}]" if part_type else ""
        text_preview = part_text[:80] + "..." if len(part_text) > 80 else part_text

        print(f"  📄 {title} {pt}")
        print(f"     원문: {text_preview}")
        print(f"     토큰: {len(result.tokens)}건 | 후보: {len(result.candidates)}건 | 상태: {result.validation_status}")

        if result.tokens:
            for tok in result.tokens[:6]:
                print(f"       [{tok.token_type}] \"{tok.value}\" (span {tok.span_start}:{tok.span_end})")
            if len(result.tokens) > 6:
                print(f"       ... +{len(result.tokens) - 6}건")

        if result.relations:
            rel = result.relations[0]
            parts_str = []
            if rel.actor_candidate:
                parts_str.append(f"주체={rel.actor_candidate}")
            if rel.action_candidate:
                parts_str.append(f"행위={rel.action_candidate}")
            if rel.target_candidate:
                parts_str.append(f"대상={rel.target_candidate}")
            if rel.condition_candidate:
                parts_str.append(f"조건={rel.condition_candidate}")
            if rel.exception_candidate:
                parts_str.append(f"예외={rel.exception_candidate}")
            print(f"     관계후보: {' | '.join(parts_str)} [{rel.status}]")

        print()

    print(f"{'='*70}")
    print(f"  합계: 토큰 {total_tokens}건 | 후보 {total_candidates}건 | 이슈 {total_issues}건")
    print(f"  PASS: {pass_cnt} | UNRESOLVED: {unresolved_cnt} | FAIL: {len(parts) - pass_cnt - unresolved_cnt}")
    print(f"{'='*70}\n")

    conn.close()


if __name__ == "__main__":
    main()
