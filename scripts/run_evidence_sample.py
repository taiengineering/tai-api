"""증거 기반 파싱 Stage 1 + Stage 2 통합 샘플.

Stage 1: Evidence Token 추출 (원문 보전, span 기반)
Stage 2: 정규화 (canonical token + family registry 매칭)

실행:
  railway run python3 scripts/run_evidence_sample.py
"""

import logging
import sys
import os

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.evidence_extractor import extract_evidence, save_result
from engine.evidence_normalizer import load_registry, normalize_tokens, save_normalized


def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # 소방시설법 20개 조항
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
    cur.close()

    if not parts:
        print("❌ 대상 법령 데이터 없음")
        conn.close()
        sys.exit(1)

    # Registry 로드
    registry = load_registry(conn)
    print(f"\n  📚 Registry: {len(registry)}개 canonical token 로드\n")

    print(f"{'='*70}")
    print(f"  Stage 1 + Stage 2 통합 — 소방시설법 {len(parts)}개 조항")
    print(f"{'='*70}\n")

    s1_tokens = 0
    s2_normalized = 0
    s2_resolved = 0
    s2_unresolved = 0

    for part_id, part_text, article_no, article_title, part_type in parts:
        # ── Stage 1: 토큰 추출 ──
        result = extract_evidence(part_id, part_text)
        save_result(conn, result)
        s1_tokens += len(result.tokens)

        # ── Stage 2: 정규화 ──
        tok_dicts = [
            {"id": None, "token_type": t.token_type, "value": t.value,
             "span_start": t.span_start, "span_end": t.span_end}
            for t in result.tokens
        ]
        normalized = normalize_tokens(conn, part_id, tok_dicts, registry)
        save_normalized(conn, normalized)
        s2_normalized += len(normalized)
        s2_resolved += sum(1 for n in normalized if n.family_status == "CANDIDATE")
        s2_unresolved += sum(1 for n in normalized if n.family_status == "UNRESOLVED")

        # ── 출력 ──
        title = f"제{article_no}조 ({article_title})" if article_title else f"제{article_no}조"
        pt = f"[{part_type}]" if part_type else ""
        text_preview = part_text[:70] + "..." if len(part_text) > 70 else part_text

        print(f"  📄 {title} {pt}")
        print(f"     원문: {text_preview}")
        print(f"     S1 토큰: {len(result.tokens)}건 | S2 정규화: {len(normalized)}건")

        if normalized:
            for n in normalized:
                family_str = f" → {n.family}" if n.family else ""
                status_mark = "✅" if n.family_status == "CANDIDATE" else "❓"
                print(f"       {status_mark} \"{n.raw_token}\" → canonical: \"{n.canonical_token}\"{family_str} [{n.family_status}]")

        print()

    print(f"{'='*70}")
    print(f"  Stage 1: 토큰 {s1_tokens}건")
    print(f"  Stage 2: 정규화 {s2_normalized}건 (CANDIDATE: {s2_resolved} | UNRESOLVED: {s2_unresolved})")
    print(f"  → evidence_token / evidence_normalized 저장 완료")
    print(f"{'='*70}\n")

    conn.close()


if __name__ == "__main__":
    main()
