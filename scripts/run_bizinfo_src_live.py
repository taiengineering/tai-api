"""G-SRC LIVE — Bizinfo 최소 실제 API 호출 파이프라인.

WO-TAI-BIZINFO STAGE-B G-SRC-LIVE-001.

사용법:
  cd <tai-api-root>
  python scripts/run_bizinfo_src_live.py [--kind PROGRAM|EVENT] [--size N] [--dry-run]

기본값: PROGRAM 5건, EVENT 3건. --dry-run이면 DB 저장 없이 결과만 출력.

의존 환경변수:
  BIZINFO_API_KEY            — 지원사업 API 키
  BIZINFO_EVENT_API_KEY      — 행사정보 API 키 (EVENT 실행 시)
  SUPABASE_URL + SUPABASE_KEY (또는 get_supabase() 경로에 따라 달라짐)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from services.bizinfo.api_access import fetch_source_batch
from services.bizinfo.normalizer import NormalizedSourceRecord, ParseFailure, normalize_bizinfo_record
from services.bizinfo.selector import review_relevance
from services.bizinfo.status import ChangeRecord


def _run_kind(
    kind: Literal["PROGRAM", "EVENT"],
    size: int,
    dry_run: bool,
    repo,
) -> dict:
    now = datetime.now(timezone.utc)
    print(f"\n[{kind}] fetch page=1 size={size} ...")

    batch = fetch_source_batch(kind, page=1, size=size)

    if batch.error_code:
        print(f"  ERROR {batch.error_code} — 중단")
        return {"kind": kind, "error": batch.error_code, "fetched": 0}

    print(f"  API 응답: {len(batch.items)}건 / total_count={batch.total_count}")

    results = {
        "kind": kind,
        "fetched": len(batch.items),
        "total_api": batch.total_count,
        "parse_ok": 0,
        "parse_fail": 0,
        "in_scope": 0,
        "out_of_scope": 0,
        "review_required": 0,
        "saved": 0,
        "items": [],
    }

    for raw in batch.items:
        normalized = normalize_bizinfo_record(kind, raw, now)

        if isinstance(normalized, ParseFailure):
            results["parse_fail"] += 1
            print(f"  PARSE_FAIL key={normalized.raw_key} reasons={normalized.reasons}")
            continue

        results["parse_ok"] += 1

        decision = review_relevance(normalized)
        verdict = decision.verdict

        if verdict == "IN_SCOPE":
            results["in_scope"] += 1
        elif verdict == "OUT_OF_SCOPE":
            results["out_of_scope"] += 1
        else:
            results["review_required"] += 1

        item_summary = {
            "key": normalized.source_key,
            "title": normalized.title[:40] if normalized.title else "",
            "source_org": normalized.source_org,
            "verdict": verdict,
            "basis": decision.basis[:3],
            "parse_errors": normalized.parse_errors[:3],
        }
        results["items"].append(item_summary)

        if not dry_run and repo is not None:
            change = ChangeRecord(
                source_key=normalized.source_key,
                source_kind=kind,
                verdict="CHANGE_UNKNOWN",
                changed_fields=(),
                checked_at=now,
                source_updated_at=normalized.source_updated_at,
            )
            try:
                repo.save_record(normalized, change)
                repo.save_relevance_verdict(kind, normalized.source_key, verdict)
                results["saved"] += 1
            except Exception as exc:
                print(f"  SAVE_ERROR key={normalized.source_key}: {exc}")

    return results


def _print_summary(results: dict) -> None:
    kind = results.get("kind", "?")
    if "error" in results:
        print(f"\n[{kind}] 결과: ERROR={results['error']}")
        return

    items = results.pop("items", [])
    print(f"\n[{kind}] 결과 요약:")
    print(f"  API 총 건수 : {results['total_api']}")
    print(f"  수신         : {results['fetched']}")
    print(f"  정규화 성공  : {results['parse_ok']}")
    print(f"  정규화 실패  : {results['parse_fail']}")
    print(f"  IN_SCOPE     : {results['in_scope']}")
    print(f"  OUT_OF_SCOPE : {results['out_of_scope']}")
    print(f"  REVIEW_REQ   : {results['review_required']}")
    print(f"  DB 저장      : {results['saved']}")
    print()
    for it in items:
        flag = {"IN_SCOPE": "●", "OUT_OF_SCOPE": "○", "REVIEW_REQUIRED": "△"}.get(it["verdict"], "?")
        errs = f" [!{', '.join(it['parse_errors'])}]" if it["parse_errors"] else ""
        print(f"  {flag} {it['key']}  {it['title']}")
        print(f"      org={it['source_org']}  basis={it['basis']}{errs}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bizinfo G-SRC LIVE 최소 파이프라인")
    parser.add_argument("--kind", choices=["PROGRAM", "EVENT", "BOTH"], default="BOTH")
    parser.add_argument("--size", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 결과만 출력")
    args = parser.parse_args()

    repo = None
    if not args.dry_run:
        try:
            from db.supabase_client import get_supabase
            from services.bizinfo.supabase_repository import SupabaseBizinfoRepository
            repo = SupabaseBizinfoRepository(get_supabase())
            print("Supabase 연결 성공.")
        except Exception as exc:
            print(f"Supabase 연결 실패 — dry-run으로 전환: {exc}")
            args.dry_run = True

    if args.dry_run:
        print("[DRY-RUN] DB 저장 없이 실행합니다.\n")

    kinds: list[Literal["PROGRAM", "EVENT"]]
    if args.kind == "BOTH":
        kinds = ["PROGRAM", "EVENT"]
        event_size = max(3, args.size // 2)
    elif args.kind == "PROGRAM":
        kinds = ["PROGRAM"]
        event_size = args.size
    else:
        kinds = ["EVENT"]
        event_size = args.size

    for kind in kinds:
        sz = args.size if kind == "PROGRAM" else event_size
        result = _run_kind(kind, sz, args.dry_run, repo)
        _print_summary(result)


if __name__ == "__main__":
    main()
