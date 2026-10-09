"""EXT-132 Supabase 저장소 — STAGING → COMPLETED 원자적 프로모션 패턴.

GAP-D: atomic_complete_snapshot()은 DB RPC fn_ext132_complete_snapshot을 호출한다.
       RPC가 미적용 상태이면 PROMOTE_RPC_UNAVAILABLE 오류를 반환한다.
GAP-B: update_checkpoint(), find_resumable_staging()으로 페이지 체크포인트 지원.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from services.ext132_hazardous_material.contract import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_STAGING,
    SOURCE_ID,
    TABLE_ITEMS,
    TABLE_SNAPSHOTS,
)
from services.ext132_hazardous_material.parse import Ext132Item

logger = logging.getLogger(__name__)


def _sb() -> Any:
    from db.supabase_client import get_supabase
    return get_supabase()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_staging_snapshot(run_id: str, *, source_id: str = SOURCE_ID, sb: Any = None) -> str:
    """STAGING 스냅샷 행 생성. snapshot_id 반환.

    source_id 열은 GAP-D migration 적용 후 사용된다.
    """
    client = sb or _sb()
    res = client.table(TABLE_SNAPSHOTS).insert({
        "run_id": run_id,
        "source_id": source_id,
        "status": SNAPSHOT_STAGING,
        "last_page_no": 0,
        "created_at": _now_iso(),
    }).execute()
    row = (res.data or [{}])[0]
    return str(row["id"])


def update_checkpoint(
    snapshot_id: str,
    last_page_no: int,
    items_so_far: int,
    total_count_from_api: int | None,
    *,
    sb: Any = None,
) -> None:
    """페이지 완료 후 체크포인트 갱신. 실패해도 수집 계속 (non-fatal).

    GAP-B: STAGING 스냅샷의 last_page_no를 갱신하여 resume 진입점을 보존한다.
    """
    client = sb or _sb()
    update_payload: dict[str, Any] = {
        "last_page_no": last_page_no,
    }
    if items_so_far is not None:
        update_payload["checkpoint_total_count"] = items_so_far
    if total_count_from_api is not None:
        update_payload["checkpoint_api_total"] = total_count_from_api
    client.table(TABLE_SNAPSHOTS).update(update_payload).eq("id", snapshot_id).execute()


def find_resumable_staging(source_id: str = SOURCE_ID, *, sb: Any = None) -> dict | None:
    """해당 소스의 기존 STAGING 스냅샷 반환. 없으면 None.

    GAP-B: resume 진입 전 미완료 스냅샷 식별용.
    """
    client = sb or _sb()
    res = (
        client.table(TABLE_SNAPSHOTS)
        .select("id,run_id,last_page_no,checkpoint_total_count,checkpoint_api_total,created_at")
        .eq("source_id", source_id)
        .eq("status", SNAPSHOT_STAGING)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def upsert_items(snapshot_id: str, items: list[Ext132Item], *, sb: Any = None) -> int:
    """스냅샷 ID 하위에 items 배치 upsert. 저장된 행 수 반환."""
    if not items:
        return 0
    client = sb or _sb()
    rows = [
        {
            "snapshot_id": snapshot_id,
            "chemicalno": item.chemicalno,
            "raw": item.raw,
            "created_at": _now_iso(),
        }
        for item in items
    ]
    res = client.table(TABLE_ITEMS).upsert(rows, on_conflict="snapshot_id,chemicalno").execute()
    return len(res.data or [])


def save_page_checkpoint(
    snapshot_id: str,
    items: list[Ext132Item],
    page_no: int,
    api_total: int | None,
    *,
    run_id: str,
    sb: Any = None,
) -> int:
    """PATCH-02/03: 원자적 페이지 저장 + 체크포인트 갱신 (단일 DB 트랜잭션 via RPC).

    fn_ext132_save_page_checkpoint RPC가:
      0. 쓰기 전 소유권 + Lease 검증 (PATCH-03)
      1. items upsert (snapshot_id,chemicalno on_conflict)
      2. DB actual count 조회 (idempotent — 재실행 안전)
      3. checkpoint UPDATE (last_page_no, checkpoint_total_count = actual, checkpoint_api_total)
    Returns: 실제 DB unique item count.
    Raises PageFencedError if RPC returns RUN_FENCED (lease lost / ownership stolen).
    Raises RuntimeError on other RPC failures.
    """
    from services.public_data_sync.errors import PageFencedError
    client = sb or _sb()
    payload = [{"chemicalno": item.chemicalno, "raw": item.raw} for item in items]
    try:
        res = client.rpc("fn_ext132_save_page_checkpoint", {
            "p_snapshot_id": snapshot_id,
            "p_items": payload,
            "p_page_no": page_no,
            "p_api_total": api_total,
            "p_run_id": run_id,
        }).execute()
        data = res.data if hasattr(res, "data") else res
        return int(data) if data is not None else 0
    except Exception as exc:
        err_str = str(exc)
        if "RUN_FENCED" in err_str or "SNAPSHOT_NOT_STAGING" in err_str:
            raise PageFencedError(f"save_page_checkpoint fenced: {err_str}") from exc
        raise RuntimeError(f"fn_ext132_save_page_checkpoint RPC failed: {type(exc).__name__}") from exc


def atomic_complete_snapshot(
    snapshot_id: str,
    *,
    source_id: str = SOURCE_ID,
    total_items: int,
    content_hash: str,
    run_id: str,
    sb: Any = None,
) -> bool:
    """GAP-D/R3-03: DB RPC를 통한 원자적 스냅샷 완결.

    RPC fn_ext132_complete_snapshot이 단일 트랜잭션에서:
      1. Run 소유권 검증: current_run_id 일치 + RUNNING + lease 유효
      2. snapshot_items 실제 count 검증 (== total_items)
      3. UPDATE snapshots SET status='COMPLETED' WHERE id=? AND source_id=? AND status='STAGING'
    조건 중 하나라도 실패하면 False 반환, 기존 COMPLETED 스냅샷 보존.

    RPC 미적용 상태이면 RuntimeError 발생.
    """
    client = sb or _sb()
    try:
        res = client.rpc("fn_ext132_complete_snapshot", {
            "p_snapshot_id": snapshot_id,
            "p_source_id": source_id,
            "p_total_items": total_items,
            "p_content_hash": content_hash,
            "p_run_id": run_id,
        }).execute()
        data = res.data if hasattr(res, "data") else res
        return bool(data)
    except Exception as exc:
        raise RuntimeError(f"fn_ext132_complete_snapshot RPC failed: {type(exc).__name__}") from exc


def promote_snapshot(
    snapshot_id: str,
    *,
    total_fetched: int,
    content_hash: str,
    sb: Any = None,
) -> bool:
    """Legacy direct promotion — kept for backward compatibility with existing tests.

    GAP-D requires atomic_complete_snapshot() in production. This function
    does NOT verify item count in DB and is NOT concurrency-safe across sources.
    """
    client = sb or _sb()
    res = (
        client.table(TABLE_SNAPSHOTS)
        .update({
            "status": SNAPSHOT_COMPLETED,
            "total_fetched": total_fetched,
            "content_hash": content_hash,
            "completed_at": _now_iso(),
        })
        .eq("id", snapshot_id)
        .eq("status", SNAPSHOT_STAGING)
        .execute()
    )
    updated = res.data or []
    return len(updated) == 1


def fail_snapshot(snapshot_id: str, *, error_message: str, sb: Any = None) -> None:
    """STAGING → FAILED 마킹. 이전 COMPLETED 스냅샷은 보존된다.

    PATCH-003: STAGING 상태인 경우에만 갱신 — COMPLETED 스냅샷을 덮어쓰지 않는다.
    """
    client = sb or _sb()
    client.table(TABLE_SNAPSHOTS).update({
        "status": SNAPSHOT_FAILED,
        "error_message": error_message[:500],
        "completed_at": _now_iso(),
    }).eq("id", snapshot_id).eq("status", SNAPSHOT_STAGING).execute()


def compute_content_hash(items: list[Ext132Item]) -> str:
    """수집된 전체 항목의 결정적 해시 (순서 독립적).

    PATCH-002-07: includes raw content so content changes (not just ID changes) are detected.
    """
    entries = sorted(
        (item.chemicalno, json.dumps(item.raw, sort_keys=True, ensure_ascii=False))
        for item in items
    )
    payload = json.dumps(entries, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def compute_content_hash_from_db(snapshot_id: str, *, sb: Any = None) -> str:
    """R3-02/PATCH-002-07: Resume 시 DB에서 전체 항목을 페이지 순회하여 해시 계산.

    PATCH-002-07: includes raw content + paginates to handle >1000 rows.
    """
    client = sb or _sb()
    all_rows: list = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            client.table(TABLE_ITEMS)
            .select("chemicalno,raw")
            .eq("snapshot_id", snapshot_id)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    entries = sorted(
        (row["chemicalno"], json.dumps(row.get("raw") or {}, sort_keys=True, ensure_ascii=False))
        for row in all_rows
    )
    payload = json.dumps(entries, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def get_latest_completed_snapshot(*, sb: Any = None) -> dict | None:
    """현행 COMPLETED 스냅샷 행 반환. 없으면 None.

    PATCH-04: is_current=true 포인터로 단일 현행판 조회.
    fn_ext132_complete_snapshot RPC가 승격 시 원자적으로 is_current를 전환한다.
    """
    client = sb or _sb()
    res = (
        client.table(TABLE_SNAPSHOTS)
        .select("*")
        .eq("status", SNAPSHOT_COMPLETED)
        .eq("is_current", True)
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None
