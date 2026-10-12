#!/usr/bin/env python3
"""EXT-165 화학물질안전원 화학사고 — 로컬 CLI 수집기.

사용법:
    python tools/ext165/bootstrap.py preflight              # 환경변수 검증
    python tools/ext165/bootstrap.py status                 # 최근 COMPLETED 스냅샷 조회
    python tools/ext165/bootstrap.py dry-run                # fixture 기반 검증 (HTTP=0, DB=0)
    python tools/ext165/bootstrap.py dry-run --yyyy 2024    # fixture 검증 (yyyy 무관, 동일 fixture)
    python tools/ext165/bootstrap.py probe                  # 실제 API 1페이지 표본조회 (DB 저장 없음)
    python tools/ext165/bootstrap.py probe --yyyy 2024      # 특정 연도 1페이지
    python tools/ext165/bootstrap.py bootstrap              # 전체 수집 + 스냅샷 저장
    python tools/ext165/bootstrap.py bootstrap --yyyy 2024  # 특정 연도 전체
    python tools/ext165/bootstrap.py refresh                # 최신 수집 실행
    python tools/ext165/bootstrap.py resume                 # 기존 STAGING 스냅샷 재개

PATCH-01: dry-run = fixture 기반, HTTP=0, DB=0. probe = 실제 API 1페이지 (Owner 승인 후).
R3-01: bootstrap/refresh/resume 는 기존 공용 fn_public_data_claim_run MANUAL 잠금을 사용한다.
       잠금 RPC 실패 시 FAIL-CLOSED (실행 차단).
       public_data_source_runtime 행이 없으면 UNKNOWN_SOURCE_RUNTIME 으로 실패.
bootstrap/refresh/resume 는 Owner 승인 후 실행할 것.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ext165.bootstrap")

_SOURCE_ID = "EXT165_CHEMICAL_ACCIDENT"


def cmd_preflight() -> int:
    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "")
    if not key:
        print("FAIL: DATA_GO_KR_SERVICE_KEY not set")
        return 1
    masked = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
    print(f"PASS: DATA_GO_KR_SERVICE_KEY present (masked={masked})")
    return 0


def cmd_status() -> int:
    from services.ext165_chemical_accident.store import get_latest_completed_snapshot
    snap = get_latest_completed_snapshot()
    if snap is None:
        print("STATUS: no COMPLETED snapshot found")
        return 0
    print(json.dumps({
        "id": snap.get("id"),
        "status": snap.get("status"),
        "total_fetched": snap.get("total_fetched"),
        "content_hash": snap.get("content_hash"),
        "completed_at": str(snap.get("completed_at")),
    }, indent=2, ensure_ascii=False))
    return 0


# PATCH-01: fixture XML — HTTP=0, DB=0.
_DRY_RUN_FIXTURE_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<response>"
    b"<header><resultCode>00</resultCode><resultMsg>DRY-RUN FIXTURE</resultMsg></header>"
    b"<body><pageNo>1</pageNo><numOfRows>2</numOfRows><totalCount>2</totalCount>"
    b"<items>"
    b"<item><datano>FIXTURE-001</datano></item>"
    b"<item><datano>FIXTURE-002</datano></item>"
    b"</items></body></response>"
)


def cmd_dry_run(yyyy: str | None = None) -> int:
    """PATCH-01: fixture 기반 검증. HTTP=0, DB=0."""
    from services.ext165_chemical_accident.parse import parse_page
    print("DRY-RUN: fixture-based verification (HTTP=0, DB=0)")
    page = parse_page(_DRY_RUN_FIXTURE_XML)
    print(json.dumps({
        "mode": "dry-run",
        "http_calls": 0,
        "db_writes": 0,
        "fixture_items": len(page.items),
        "sample_datanos": [i.datano for i in page.items[:5]],
        "sample_raw_keys": list(page.items[0].raw.keys()) if page.items else [],
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_probe(yyyy: str | None = None) -> int:
    """PATCH-01: 실제 API 표본조회 (1페이지). HTTP 발생. DB 저장 없음. Owner 승인 후 실행."""
    from services.ext165_chemical_accident.sync import collect_all, SyncStatus
    label = f"yyyy={yyyy}" if yyyy else "all years"
    print(f"PROBE: fetching page 1 from real API ({label}, no DB write)")
    result = collect_all(yyyy=yyyy, dry_run=True)
    print(json.dumps({
        "mode": "probe",
        "status": result.status.value,
        "fetched": result.fetched,
        "pages_fetched": result.pages_fetched,
        "budget_used": result.budget_used,
        "error_code": result.error_code,
        "sample_datanos": [i.datano for i in result.items[:5]],
        "sample_raw_keys": list(result.items[0].raw.keys()) if result.items else [],
    }, indent=2, ensure_ascii=False))
    return 0 if result.status != SyncStatus.FAILED else 1


def _claim_run(run_id: str) -> tuple[object | None, str]:
    """R3-01: 기존 공용 잠금으로 MANUAL 실행 권한 획득. FAIL-CLOSED."""
    from services.public_data_sync.runtime_store import PublicDataRuntimeStore
    from services.public_data_sync.registry import registry
    from services.public_data_sync.contracts import TriggerKind

    try:
        spec = registry.get(_SOURCE_ID)
        store = PublicDataRuntimeStore()
        now = datetime.now(timezone.utc)
        claim = store.claim_run(
            run_id,
            spec,
            trigger=TriggerKind.MANUAL,
            now=now,
        )
        if not claim.claimed:
            print(f"LOCK_FAIL: reason={claim.reason}")
            if claim.reason == "UNKNOWN_SOURCE_RUNTIME":
                print("  → public_data_source_runtime 행이 없습니다. migration 적용 후 재실행하세요.")
            elif claim.reason == "SOURCE_BUSY":
                print("  → 다른 실행이 진행 중입니다. 완료 후 재시도하세요.")
            return None, claim.reason
        print(f"LOCK: claimed run_id={run_id} lease_until={claim.lease_until}")
        return store, run_id
    except Exception as exc:
        print(f"LOCK_ERROR: 잠금 RPC 실패 ({type(exc).__name__}: {exc}) — 실행 차단")
        return None, str(exc)


def _complete_run(store: object, run_id: str, *, succeeded: bool, fetched: int = 0) -> None:
    from services.public_data_sync.contracts import RunResult, RunStatus

    try:
        status = RunStatus.SUCCESS if succeeded else RunStatus.FAILED
        result = RunResult(
            run_id=run_id,
            source_id=_SOURCE_ID,
            status=status,
            finished_at=datetime.now(timezone.utc),
            fetched=fetched,
        )
        store.complete_run(run_id, result)
    except Exception as exc:
        logger.warning("complete_run failed: %s", exc)


def cmd_bootstrap(yyyy: str | None = None) -> int:
    from services.ext165_chemical_accident.store import (
        atomic_complete_snapshot, compute_content_hash,
        create_staging_snapshot, fail_snapshot, save_page_checkpoint,
    )
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.ext165_chemical_accident.contract import SOURCE_ID

    run_id = str(uuid.uuid4())
    label = f"yyyy={yyyy}" if yyyy else "all years"

    store, claim_info = _claim_run(run_id)
    if store is None:
        return 1

    print(f"BOOTSTRAP: starting full collection ({label})")
    snapshot_id: str | None = None
    total_in_db = [0]
    succeeded = False
    try:
        # PATCH-002-06: store yyyy as collect_scope to prevent year-scoped snapshots
        # from replacing the global is_current snapshot
        snapshot_id = create_staging_snapshot(run_id, source_id=SOURCE_ID, collect_scope=yyyy)
        print(f"  snapshot_id={snapshot_id}")

        def _on_page(page_no, page_items, total_collected, total_count_from_api):
            from services.public_data_sync.errors import PageFencedError, PageSaveError
            # PATCH-02/03: atomic save + pre-write fencing via RPC
            try:
                actual = save_page_checkpoint(snapshot_id, page_items, page_no, total_count_from_api, run_id=run_id)
                total_in_db[0] = actual
            except PageFencedError:
                raise  # RPC-level fencing — stop collection
            except Exception as exc:
                raise PageSaveError(f"page {page_no} save failed: {type(exc).__name__}") from exc
            # PATCH-03/PATCH-B: belt-and-suspenders post-save heartbeat check
            try:
                alive = store.heartbeat(run_id)
            except Exception as exc:
                raise PageSaveError(f"heartbeat RPC failed: {type(exc).__name__}") from exc
            if not alive:
                raise PageFencedError("heartbeat returned False — lease may have expired")

        result = collect_all(yyyy=yyyy, on_page_complete=_on_page)
        print(f"  status={result.status.value} fetched={result.fetched} pages={result.pages_fetched}")

        # PATCH-003/PATCH-C: PARTIAL/FENCED/SAVE_ERROR → preserve STAGING snapshot for resume (no fail_snapshot)
        if result.status == SyncStatus.PARTIAL or (
            result.status == SyncStatus.FAILED and result.error_code in ("FENCED", "SAVE_ERROR")
        ):
            print(f"PARTIAL: collection incomplete ({result.error_code}) — snapshot preserved for resume")
            return 1

        # PATCH-002-03: only COMPLETED is eligible for promotion
        if result.status != SyncStatus.COMPLETED:
            fail_snapshot(snapshot_id, run_id=run_id, error_message=result.error_code or "COLLECT_FAILED")
            print("FAIL: collection failed — snapshot marked FAILED")
            return 1

        content_hash = compute_content_hash(result.items)
        promoted = atomic_complete_snapshot(
            snapshot_id,
            source_id=SOURCE_ID,
            total_items=total_in_db[0],
            content_hash=content_hash,
            run_id=run_id,
        )
        if promoted:
            print(f"DONE: snapshot {snapshot_id} COMPLETED hash={content_hash} items={total_in_db[0]}")
            succeeded = True
            return 0
        else:
            print("FAIL: snapshot promotion rejected (fenced or lease expired)")
            return 1

    except Exception as exc:
        if snapshot_id:
            try:
                fail_snapshot(snapshot_id, run_id=run_id, error_message=type(exc).__name__)
            except Exception:
                pass
        raise
    finally:
        _complete_run(store, run_id, succeeded=succeeded, fetched=total_in_db[0])


def cmd_refresh(yyyy: str | None = None) -> int:
    return cmd_bootstrap(yyyy=yyyy)


def cmd_resume() -> int:
    """GAP-B/R3-01: 기존 STAGING 스냅샷 재개 (공용 잠금 사용)."""
    from services.ext165_chemical_accident.store import (
        atomic_complete_snapshot, compute_content_hash_from_db,
        fail_snapshot, find_resumable_staging, save_page_checkpoint,
    )
    from services.ext165_chemical_accident.sync import SyncStatus, collect_all
    from services.ext165_chemical_accident.contract import SOURCE_ID

    staging = find_resumable_staging(source_id=SOURCE_ID)
    if not staging:
        print("RESUME: no STAGING snapshot found — run bootstrap instead")
        return 1

    snapshot_id = str(staging["id"])
    resume_from_page = int(staging.get("last_page_no") or 1)
    expected_total = staging.get("checkpoint_api_total")
    initial_db_count = int(staging.get("checkpoint_total_count") or 0)
    # PATCH-002-06: restore original year filter from collect_scope stored in staging snapshot
    collect_scope = staging.get("collect_scope")
    run_id = str(uuid.uuid4())

    print(f"RESUME: snapshot_id={snapshot_id} from_page={resume_from_page} db_items={initial_db_count}")

    store, claim_info = _claim_run(run_id)
    if store is None:
        return 1

    total_in_db = [initial_db_count]
    succeeded = False
    try:
        def _on_page(page_no, page_items, total_collected, total_count_from_api):
            from services.public_data_sync.errors import PageFencedError, PageSaveError
            # PATCH-02/03: atomic save + pre-write fencing via RPC
            try:
                actual = save_page_checkpoint(snapshot_id, page_items, page_no, total_count_from_api, run_id=run_id)
                total_in_db[0] = actual
            except PageFencedError:
                raise  # RPC-level fencing — stop collection
            except Exception as exc:
                raise PageSaveError(f"page {page_no} save failed: {type(exc).__name__}") from exc
            # PATCH-03/PATCH-B: belt-and-suspenders post-save heartbeat check
            try:
                alive = store.heartbeat(run_id)
            except Exception as exc:
                raise PageSaveError(f"heartbeat RPC failed: {type(exc).__name__}") from exc
            if not alive:
                raise PageFencedError("heartbeat returned False — lease may have expired")

        result = collect_all(
            yyyy=collect_scope,
            start_page_no=resume_from_page,
            on_page_complete=_on_page,
            expected_total_count=expected_total,
            initial_items_count=initial_db_count,
        )
        print(f"  status={result.status.value} fetched={result.fetched} pages={result.pages_fetched}")

        # PATCH-003/PATCH-C: PARTIAL/FENCED/SAVE_ERROR → preserve STAGING snapshot for resume (no fail_snapshot)
        if result.status == SyncStatus.PARTIAL or (
            result.status == SyncStatus.FAILED and result.error_code in ("FENCED", "SAVE_ERROR")
        ):
            print(f"PARTIAL: collection incomplete ({result.error_code}) — snapshot preserved for resume")
            return 1

        # PATCH-002-03: only COMPLETED is eligible for promotion
        if result.status != SyncStatus.COMPLETED:
            fail_snapshot(snapshot_id, run_id=run_id, error_message=result.error_code or "COLLECT_FAILED")
            print("FAIL: collection failed/aborted — snapshot marked FAILED, restart bootstrap")
            return 1

        content_hash = compute_content_hash_from_db(snapshot_id)
        promoted = atomic_complete_snapshot(
            snapshot_id,
            source_id=SOURCE_ID,
            total_items=total_in_db[0],
            content_hash=content_hash,
            run_id=run_id,
        )
        if promoted:
            print(f"DONE: snapshot {snapshot_id} COMPLETED hash={content_hash} items={total_in_db[0]}")
            succeeded = True
            return 0
        else:
            print("FAIL: snapshot promotion rejected (fenced or lease expired)")
            return 1

    except Exception as exc:
        try:
            fail_snapshot(snapshot_id, run_id=run_id, error_message=type(exc).__name__)
        except Exception:
            pass
        raise
    finally:
        _complete_run(store, run_id, succeeded=succeeded, fetched=total_in_db[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="EXT-165 화학물질안전원 화학사고 수집기 CLI")
    parser.add_argument(
        "command",
        choices=["preflight", "status", "dry-run", "probe", "bootstrap", "refresh", "resume"],
    )
    parser.add_argument("--yyyy", default=None, help="연도 필터 (예: 2024)")
    args = parser.parse_args()

    if args.command == "preflight":
        return cmd_preflight()
    if args.command == "status":
        return cmd_status()
    if args.command == "dry-run":
        return cmd_dry_run(yyyy=args.yyyy)
    if args.command == "probe":
        return cmd_probe(yyyy=args.yyyy)
    if args.command == "resume":
        return cmd_resume()
    if args.command in ("bootstrap", "refresh"):
        return cmd_bootstrap(yyyy=args.yyyy)
    return 1


if __name__ == "__main__":
    sys.exit(main())
