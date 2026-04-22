#!/usr/bin/env python3
"""
전체 법령 재수집 (Pilot 1/2/3 통과 후 확장).

체크포인트 기반 재개 가능:
- /tmp/all_laws_checkpoint.json 에 진행 상태 저장
- 중단 시 해당 파일 읽어서 이어서 진행

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    python3 scripts/all_laws_recollect.py 2>&1 | tee -a /tmp/all_laws_output.log

옵션:
    --resume    : 체크포인트에서 이어서
    --dry-run   : 대상 목록만 출력하고 실제 재수집 안 함
    --limit N   : 최대 N개만 처리
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from scripts.pilot2_recollect import _check_emergency_stop, recollect_one, reconnect_one

CHECKPOINT_PATH = Path("/tmp/all_laws_checkpoint.json")
MAX_CONSECUTIVE_FAILURES = 3
PER_LAW_TIMEOUT = 600

COMPLETED_LAWS = {
    "산업안전보건법",
    "건축법",
    "건축법 시행령",
    "건설기술 진흥법",
    "화재의 예방 및 안전관리에 관한 법률",
    "위험물안전관리법 시행규칙",
    "전기안전관리법 시행규칙",
    "소방시설 설치 및 관리에 관한 법률",
    "고압가스 안전관리법 시행규칙",
    "화학물질관리법 시행규칙",
}


class TimeoutException(Exception):
    pass


def _timeout_handler(signum, frame):
    del signum, frame
    raise TimeoutException("법령별 타임아웃")


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed": [], "failed": [], "skipped": [], "started_at": None}


def save_checkpoint(state: dict) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def fetch_target_laws(supabase) -> list[str]:
    """law_master 활성 법령에서 Pilot 1/2/3 완료 법령을 제외."""
    try:
        res = supabase.table("law_master").select("law_name").eq("is_active", True).execute()
        all_names = [r["law_name"] for r in (res.data or []) if r.get("law_name")]
        return [n for n in all_names if n not in COMPLETED_LAWS]
    except Exception as e:
        print(f"❌ 대상 법령 조회 실패: {e}")
        return []


def process_one_law(law_name: str, supabase) -> dict:
    """한 법령 재수집 + 재연결. 타임아웃 600초."""
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(PER_LAW_TIMEOUT)
    try:
        result = recollect_one(law_name, supabase)
        if result.get("success"):
            try:
                rec = reconnect_one(result.get("matched_name", law_name), supabase)
                result.update(rec)
            except Exception as e:
                result["reconnect_success"] = False
                result["reconnect_error"] = str(e)
        return result
    except TimeoutException:
        return {"law_name": law_name, "success": False, "error": "per-law timeout 600s"}
    finally:
        signal.alarm(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="체크포인트 이어서")
    parser.add_argument("--dry-run", action="store_true", help="대상 목록만 출력")
    parser.add_argument("--limit", type=int, default=None, help="최대 N개 처리")
    args = parser.parse_args()

    supabase = get_supabase()
    all_targets = fetch_target_laws(supabase)
    state = load_checkpoint() if args.resume else {"processed": [], "failed": [], "skipped": [], "started_at": None}

    if state["started_at"] is None:
        state["started_at"] = datetime.now(timezone.utc).isoformat()

    done_names = {r.get("law_name") for r in state["processed"] + state["failed"] + state["skipped"] if r.get("law_name")}
    targets = [t for t in all_targets if t not in done_names]
    if args.limit:
        targets = targets[: args.limit]

    print(f"📋 전체 대상: {len(all_targets)}개, 이미 처리: {len(done_names)}개, 이번 실행: {len(targets)}개")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for t in targets[:20]:
            print(f"  - {t}")
        if len(targets) > 20:
            print(f"  ... 외 {len(targets) - 20}개")
        return 0

    consecutive_failures = 0
    start_time = time.time()

    for idx, law_name in enumerate(targets, 1):
        elapsed = time.time() - start_time
        print(f"\n[{idx}/{len(targets)}] ⏱ {elapsed:.0f}s 경과 | 🎯 {law_name}")

        should_stop, reason = _check_emergency_stop(supabase)
        if should_stop:
            print(f"🚨 긴급 중단: {reason}")
            state["skipped"].append({"law_name": law_name, "reason": f"emergency_stop: {reason}"})
            save_checkpoint(state)
            return 2

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            print(f"🚨 연속 {MAX_CONSECUTIVE_FAILURES}회 실패 → 즉시 중단")
            state["skipped"].append({"law_name": law_name, "reason": "max_consecutive_failures"})
            save_checkpoint(state)
            return 3

        result = process_one_law(law_name, supabase)
        if result.get("success"):
            state["processed"].append(result)
            consecutive_failures = 0
            print(f"  ✅ article_count={result.get('article_count')}")
        else:
            state["failed"].append(result)
            consecutive_failures += 1
            print(f"  ❌ {result.get('error')}")

        save_checkpoint(state)

    print("\n" + "=" * 70)
    print("📊 전체 완료")
    print(f"  ✅ 성공: {len(state['processed'])}")
    print(f"  ❌ 실패: {len(state['failed'])}")
    print(f"  ⏭  스킵: {len(state['skipped'])}")
    print("=" * 70)

    return 0 if len(state["failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
