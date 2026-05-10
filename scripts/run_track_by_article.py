"""Track A~E 조항 단위 검증 — 정규화/비정규화 분리 실행.

실행:
  railway run python3 scripts/run_track_by_article.py normalized
  railway run python3 scripts/run_track_by_article.py denormalized
"""

import logging
import sys
import os
import time

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.track_runner import (
    TrackRunner, _get_conn, _save_issues, TRACK_ORDER,
    run_track_a, run_track_b, run_track_c, run_track_d, run_track_e,
    _v, LawResult, TrackIssue,
)


def fetch_articles(conn, mode: str) -> list[dict]:
    """law_article 조회. mode='normalized' → 조문, 'denormalized' → 나머지."""
    cur = conn.cursor()
    if mode == "normalized":
        cur.execute("""
            SELECT la.id, la.law_id, la.article_type, la.article_title, lm.law_name
            FROM law_article la
            JOIN law_master lm ON lm.id = la.law_id
            WHERE la.article_type = '조문'
            ORDER BY lm.law_name, la.article_no_sort
        """)
    else:
        cur.execute("""
            SELECT la.id, la.law_id, la.article_type, la.article_title, lm.law_name
            FROM law_article la
            JOIN law_master lm ON lm.id = la.law_id
            WHERE la.article_type != '조문'
            ORDER BY lm.law_name, la.article_no_sort
        """)
    rows = [
        {"article_id": r[0], "law_id": r[1], "article_type": r[2],
         "article_title": r[3], "law_name": r[4]}
        for r in cur.fetchall()
    ]
    cur.close()
    return rows


def run_article(conn, article: dict, morpheme_engine=None, supabase=None) -> LawResult:
    """조항 하나에 대해 A→B→C→D→E 순차 검증."""
    article_id = article["article_id"]
    law_id = article["law_id"]
    lr = LawResult(law_id=law_id)

    for track in TRACK_ORDER:
        if track == "A":
            v = run_track_a(conn, law_id, morpheme_engine)
        elif track == "B":
            v = run_track_b(conn, law_id)
        elif track == "C":
            v = run_track_c(conn, law_id, morpheme_engine)
        elif track == "D":
            v = run_track_d(conn, law_id)
        elif track == "E":
            v = run_track_e(conn, law_id, supabase)
        else:
            continue

        # article_id를 이슈에 기록
        for iss in v.issues:
            iss.article_id = str(article_id)

        lr.verdicts.append(v)
        if not v.forward_pass or not v.reverse_pass:
            lr.stopped_at = track
            return lr

    return lr


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("normalized", "denormalized"):
        print("사용법: railway run python3 scripts/run_track_by_article.py [normalized|denormalized]")
        sys.exit(1)

    mode = sys.argv[1]
    label = "정규화 (조문)" if mode == "normalized" else "비정규화 (본칙/항/전문/조/절/목/장)"

    print(f"\n{'='*60}")
    print(f"  Track A~E {label} 검증")
    print(f"{'='*60}\n")

    morpheme_engine = None
    supabase = None

    try:
        from db.supabase_client import get_supabase
        supabase = get_supabase()
        print("  ✅ Supabase 연결")
    except Exception as e:
        print(f"  ⚠️ Supabase 연결 실패: {e}")

    try:
        from engine.morpheme import MorphemeEngine
        morpheme_engine = MorphemeEngine(supabase=supabase)
        print(f"  ✅ Kiwi 초기화 (dict={morpheme_engine.user_dict_size})")
    except Exception as e:
        print(f"  ⚠️ Kiwi 초기화 실패: {e}")

    conn = _get_conn()
    if conn is None:
        print("  ❌ DATABASE_URL 미설정")
        sys.exit(1)

    articles = fetch_articles(conn, mode)
    total = len(articles)
    print(f"  📋 대상 조항: {total}건\n")

    # 같은 law_id 중복 검증 방지 (법령 단위 캐싱)
    law_cache = {}
    passed = 0
    failed = 0
    fail_at = {t: 0 for t in TRACK_ORDER}
    issue_counts = {}
    start = time.time()

    for i, article in enumerate(articles):
        law_id = article["law_id"]

        # 같은 법령은 결과 재사용
        if law_id in law_cache:
            lr = law_cache[law_id]
        else:
            lr = run_article(conn, article, morpheme_engine, supabase)
            law_cache[law_id] = lr

            # 이슈 DB 저장 (법령 첫 조항에서만)
            for vd in lr.verdicts:
                if vd.issues:
                    _save_issues(conn, vd.issues)

        if lr.stopped_at is None:
            passed += 1
        else:
            failed += 1
            fail_at[lr.stopped_at] = fail_at.get(lr.stopped_at, 0) + 1
            for vd in lr.verdicts:
                for iss in vd.issues:
                    issue_counts[iss.issue_type] = issue_counts.get(iss.issue_type, 0) + 1

        if (i + 1) % 500 == 0 or (i + 1) == total:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1:>6}/{total}] "
                f"✅{passed} ❌{failed} "
                f"({elapsed:.0f}s, ~{eta:.0f}s 남음)"
            )

    conn.close()
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"  {label} 최종 결과 ({elapsed:.1f}초)")
    print(f"{'='*60}")
    print(f"  ✅ PASS: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  ❌ FAIL: {failed}/{total} ({failed/total*100:.1f}%)")
    print(f"  📋 법령 수: {len(law_cache)}개 (캐싱)")

    if failed > 0:
        print(f"\n  Track별 FAIL:")
        for t in TRACK_ORDER:
            cnt = fail_at.get(t, 0)
            if cnt > 0:
                print(f"    Track {t}: {cnt}건")

    if issue_counts:
        print(f"\n  이슈 유형별:")
        for issue_type, cnt in sorted(issue_counts.items(), key=lambda x: -x[1]):
            print(f"    {issue_type}: {cnt}건")

    print(f"\n  → track_issue_log 테이블에 저장 완료")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
