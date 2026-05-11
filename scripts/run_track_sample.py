"""Track A~E 샘플 실행 — 법령 5개로 검증 엔진 테스트.

실행:
  cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
  python scripts/run_track_sample.py
"""

import logging
import sys
import os

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# engine import 가능하도록 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.track_runner import TrackRunner, TRACK_ORDER


def main():
    sample_size = 5

    print(f"\n{'='*60}")
    print(f"  Track A~E 샘플 검증 ({sample_size}개 법령)")
    print(f"{'='*60}\n")

    # MorphemeEngine + Supabase 초기화 시도
    morpheme_engine = None
    supabase = None

    try:
        from db.supabase_client import get_supabase
        supabase = get_supabase()
        logger.info("Supabase 연결 완료")
    except Exception as e:
        logger.warning("Supabase 연결 실패 (Track E 제한): %s", e)

    try:
        from engine.morpheme import MorphemeEngine
        morpheme_engine = MorphemeEngine(supabase=supabase)
        logger.info("MorphemeEngine 초기화 완료 (dict=%d)", morpheme_engine.user_dict_size)
    except Exception as e:
        logger.warning("MorphemeEngine 초기화 실패 (Track A/C 제한): %s", e)

    runner = TrackRunner(morpheme_engine=morpheme_engine, supabase=supabase)

    # 전체 법령 목록에서 앞 5개만
    from engine.track_runner import _get_conn, _fetch_all_law_ids
    conn = _get_conn()
    if conn is None:
        print("❌ DATABASE_URL 미설정")
        sys.exit(1)

    all_ids = _fetch_all_law_ids(conn)
    sample_ids = all_ids[:sample_size]
    conn.close()

    print(f"  전체 법령: {len(all_ids)}개")
    print(f"  샘플 법령: {len(sample_ids)}개 (가장 작은 것부터)\n")

    # 실행
    conn = _get_conn()
    passed = 0
    failed = 0

    for i, law_id in enumerate(sample_ids):
        lr = runner._run_single_law(conn, law_id)

        # 이슈 DB 저장
        from engine.track_runner import _save_issues
        for vd in lr.verdicts:
            if vd.issues:
                _save_issues(conn, vd.issues)

        if lr.stopped_at is None:
            passed += 1
            tracks_passed = " → ".join(TRACK_ORDER)
            print(f"  ✅ [{i+1}/{sample_size}] law_id={law_id}")
            print(f"     {tracks_passed} 전부 PASS\n")
        else:
            failed += 1
            # 어디서 멈췄는지, 이슈 유형은 뭔지
            last_v = lr.verdicts[-1]
            issues_str = ", ".join(iss.issue_type for iss in last_v.issues) if last_v.issues else "분류 없음"
            direction = "정순" if not last_v.forward_pass else "역순"

            passed_tracks = [v.track for v in lr.verdicts[:-1]]
            passed_str = " → ".join(passed_tracks) + " → " if passed_tracks else ""

            print(f"  ❌ [{i+1}/{sample_size}] law_id={law_id}")
            print(f"     {passed_str}Track {lr.stopped_at} {direction} FAIL")
            print(f"     이슈: {issues_str}")
            if last_v.detail:
                print(f"     상세: {last_v.detail}")
            print()

    conn.close()

    # 요약
    print(f"{'='*60}")
    print(f"  결과: ✅ {passed}통과 / ❌ {failed}실패 / 전체 {sample_size}건")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
