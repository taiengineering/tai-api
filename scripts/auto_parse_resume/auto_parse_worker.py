#!/usr/bin/env python3
"""
TAI 법령엔진 auto-parse 재개용 worker (크롬 탭 대체)

사용법:
  export TAI_INTERNAL_SECRET="<Railway INTERNAL_API_SECRET 과 동일 값>"
  export TAI_API_URL="https://api.taieng.co.kr"    # 기본값 사용 시 생략 가능
  python3 auto_parse_worker.py

옵션:
  --max-per-law 50         법령당 최대 조문 수 (기본 50)
  --threshold 80           auto_approve_threshold (기본 80)
  --sleep 5                법령 간 대기 (초, 기본 5)
  --laws-file laws.csv     CSV 파일에서 law_id 읽기 (없으면 DB 쿼리 시도)
  --dry-run                실제 호출 없이 계획만 출력
  --max-laws N             최대 N개 법령만 처리 (테스트용)

로그:
  auto_parse.log  — 실행 로그 (tail -f 로 모니터링)

중단/재개:
  Ctrl+C로 안전 중단 가능. 다시 실행하면 아직 안 끝난 법령부터 재개 (DB가 알아서 건너뜀).

nohup 백그라운드 실행:
  nohup python3 auto_parse_worker.py > worker.out 2>&1 &
  tail -f auto_parse.log
"""

import os
import sys
import csv
import json
import time
import signal
import logging
import argparse
from datetime import datetime
from urllib import request as urlreq
from urllib.error import URLError, HTTPError

# ── 설정 ──────────────────────────────────────
API_URL = os.environ.get("TAI_API_URL", "https://api.taieng.co.kr").rstrip("/")
SECRET  = os.environ.get("TAI_INTERNAL_SECRET", "")

ENDPOINT = f"{API_URL}/law-rule-generator/auto-parse-and-approve"
LOG_FILE = "auto_parse.log"

# ── 로깅 ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("auto-parse")

# ── 안전 중단 ──────────────────────────────────
_stop_requested = False
def _handle_sigint(signum, frame):
    global _stop_requested
    _stop_requested = True
    log.warning("⚠️  중단 요청 감지. 현재 법령 완료 후 종료합니다…")
signal.signal(signal.SIGINT, _handle_sigint)
signal.signal(signal.SIGTERM, _handle_sigint)


# ── API 호출 ──────────────────────────────────
def call_auto_parse(law_id: str, max_articles: int, threshold: int, timeout: int = 600) -> dict:
    """POST /auto-parse-and-approve 호출"""
    payload = {
        "secret": SECRET,
        "law_id": law_id,
        "max_articles": max_articles,
        "auto_approve_threshold": threshold,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlreq.Request(
        ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlreq.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


# ── 법령 목록 로드 ────────────────────────────
def load_laws_from_csv(path: str) -> list:
    """CSV 포맷: law_id,law_name,remaining,status (헤더 포함)"""
    laws = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("law_id"):
                laws.append({
                    "law_id": row["law_id"].strip(),
                    "law_name": row.get("law_name", "").strip(),
                    "remaining": int(row.get("remaining") or 0),
                    "status": row.get("status", "").strip(),
                })
    return laws


def load_laws_from_stats() -> list:
    """GET /stats에서 법령 목록 간접 확인 — 불완전. CSV 권장."""
    log.error("⚠️  --laws-file CSV가 필요합니다 (/stats는 law_id 목록을 반환하지 않음).")
    sys.exit(1)


# ── 메인 ──────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-law", type=int, default=50)
    parser.add_argument("--threshold", type=int, default=80)
    parser.add_argument("--sleep", type=int, default=5)
    parser.add_argument("--laws-file", type=str, default="auto_parse_queue.csv")
    parser.add_argument("--max-laws", type=int, default=0, help="0=전체")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SECRET and not args.dry_run:
        raise RuntimeError(
            "TAI_INTERNAL_SECRET 환경변수 필수 (--dry-run 제외)"
        )

    if not os.path.exists(args.laws_file):
        log.error(f"❌ {args.laws_file} 파일이 없습니다. 같은 폴더에 두세요.")
        sys.exit(1)

    laws = load_laws_from_csv(args.laws_file)
    if args.max_laws > 0:
        laws = laws[:args.max_laws]

    total = len(laws)
    total_remaining = sum(l["remaining"] for l in laws)

    log.info(f"🚀 시작: {total} 법령, 총 {total_remaining} 조문 대기")
    log.info(f"   API: {ENDPOINT}")
    log.info(f"   max_per_law={args.max_per_law}, threshold={args.threshold}, sleep={args.sleep}s")
    if args.dry_run:
        log.info("   [DRY-RUN] 실제 호출 없음")

    processed_laws = 0
    total_parsed = 0
    total_drafts = 0
    total_auto_approved = 0
    total_errors = 0
    start_ts = time.time()

    for idx, law in enumerate(laws, 1):
        if _stop_requested:
            log.warning(f"중단됨. {idx - 1}/{total} 법령 처리 완료.")
            break

        log.info(f"[{idx:3d}/{total}] {law['status']} {law['law_name']} (남은 {law['remaining']})")

        if args.dry_run:
            continue

        try:
            result = call_auto_parse(
                law["law_id"], args.max_per_law, args.threshold,
            )
            data = result.get("data", {})
            parsed = data.get("parsed", 0)
            drafts = data.get("drafts_created", 0)
            approved = data.get("auto_approved", 0)
            errs = len(data.get("errors", []))

            total_parsed += parsed
            total_drafts += drafts
            total_auto_approved += approved
            total_errors += errs
            processed_laws += 1

            log.info(
                f"     ✓ parsed={parsed}, drafts={drafts}, "
                f"auto_approved={approved}, errors={errs}"
            )
            if errs > 0 and data.get("errors"):
                for e in data["errors"][:3]:
                    log.warning(f"       ↳ {e}")

        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            log.error(f"     ✗ HTTP {e.code}: {err_body}")
            total_errors += 1
            if e.code in (502, 503, 504):
                log.warning("     ⏸  서버 오류 60초 대기…")
                time.sleep(60)
        except URLError as e:
            log.error(f"     ✗ 네트워크 오류: {e}")
            total_errors += 1
            time.sleep(30)
        except Exception as e:
            log.error(f"     ✗ 예외: {e}")
            total_errors += 1

        if idx < total:
            time.sleep(args.sleep)

    elapsed = time.time() - start_ts
    log.info("=" * 60)
    log.info(f"📊 종합 결과 ({elapsed/60:.1f}분)")
    log.info(f"   처리된 법령: {processed_laws}/{total}")
    log.info(f"   파싱된 조문: {total_parsed}")
    log.info(f"   생성된 드래프트: {total_drafts}")
    log.info(f"   자동승인 master: {total_auto_approved}")
    log.info(f"   에러: {total_errors}")
    log.info("=" * 60)
    log.info("다음 스텝: POST /law-rule-generator/bulk-approve-unregistered 로 미등록 APPROVED 마무리")


if __name__ == "__main__":
    main()
