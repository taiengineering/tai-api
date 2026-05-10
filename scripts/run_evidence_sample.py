"""증거 기반 파싱 샘플 실행 — 건축법 10개 조항.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
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

    # 건축법에서 조문 10개 가져오기
    cur.execute("""
        SELECT lap.id::text, lap.part_text, la.article_no, la.article_title
        FROM law_article_part lap
        JOIN law_article la ON la.id = lap.article_id
        JOIN law_master lm ON lm.id = la.law_id
        WHERE lm.law_name = '건축법'
          AND la.article_type = '조문'
          AND lap.part_text IS NOT NULL
          AND lap.part_text != ''
        ORDER BY la.article_no, lap.sort_order
        LIMIT 10
    """)
    parts = cur.fetchall()
    cur.close()

    print(f"\n{'='*70}")
    print(f"  증거 기반 파싱 샘플 — 건축법 {len(parts)}개 조항")
    print(f"{'='*70}\n")

    total_tokens = 0
    total_candidates = 0
    total_issues = 0

    for part_id, part_text, article_no, article_title in parts:
        result = extract_evidence(part_id, part_text)
        saved = save_result(conn, result)

        total_tokens += len(result.tokens)
        total_candidates += len(result.candidates)
        total_issues += len(result.issues)

        # 출력
        title = f"제{article_no}조 ({article_title})" if article_title else f"제{article_no}조"
        text_preview = part_text[:80] + "..." if len(part_text) > 80 else part_text
        print(f"  📄 {title}")
        print(f"     원문: {text_preview}")
        print(f"     토큰: {len(result.tokens)}건 | 후보: {len(result.candidates)}건 | 이슈: {len(result.issues)}건 | 상태: {result.validation_status}")

        if result.tokens:
            for tok in result.tokens[:5]:
                print(f"       [{tok.token_type}] \"{tok.value}\" (span {tok.span_start}:{tok.span_end})")
            if len(result.tokens) > 5:
                print(f"       ... +{len(result.tokens) - 5}건")

        if result.relations:
            rel = result.relations[0]
            print(f"     관계후보: 주체={rel.actor_candidate} → 행위={rel.action_candidate} (조건={rel.condition_candidate})")

        if result.issues:
            for iss in result.issues[:3]:
                print(f"       ⚠️ {iss.issue_type}: {iss.detail}")

        print()

    print(f"{'='*70}")
    print(f"  합계: 토큰 {total_tokens}건 | 후보 {total_candidates}건 | 이슈 {total_issues}건")
    print(f"  → evidence_token / evidence_candidate / evidence_validation 테이블에 저장 완료")
    print(f"{'='*70}\n")

    conn.close()


if __name__ == "__main__":
    main()
