"""Track A~E 전체 실행 — 704개 법령 순차 검증.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  railway run python3 scripts/run_track_full.py
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

from engine.track_runner import TrackRunner, _get_conn, _fetch_all_law_ids, _save_issues, TRACK_ORDER


def main():
    print(f"\n{'='*60}")
    print(f"  Track A~E 전체 검증 (704 법령)")
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

    law_ids = _fetch_all_law_ids(conn)
    total = len(law_ids)
    print(f"  📋 대상 법령: {total}개\n")

    runner = TrackRunner(morpheme_engine=morpheme_engine, supabase=supabase)

    passed = 0
    failed = 0
    fail_at = {t: 0 for t in TRACK_ORDER}
    issue_counts = {}
    start = time.time()

    for i, law_id in enumerate(law_ids):
        lr = runner._run_single_law(conn, law_id)

        for vd in lr.verdicts:
            if vd.issues:
                _save_issues(conn, vd.issues)
                for iss in vd.issues:
                    issue_counts[iss.issue_type] = issue_counts.get(iss.issue_type, 0) + 1

        if lr.stopped_at is None:
            passed += 1
        else:
            failed += 1
            fail_at[lr.stopped_at] = fail_at.get(lr.stopped_at, 0) + 1

        # 50개마다 진행률 출력
        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1:>4}/{total}] "
                f"✅{passed} ❌{failed} "
                f"({elapsed:.0f}s, ~{eta:.0f}s 남음)"
            )

    conn.close()
    elapsed = time.time() - start

    # 최종 요약
    print(f"\n{'='*60}")
    print(f"  최종 결과 ({elapsed:.1f}초)")
    print(f"{'='*60}")
    print(f"  ✅ PASS: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  ❌ FAIL: {failed}/{total} ({failed/total*100:.1f}%)")

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
