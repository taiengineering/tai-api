"""EXT-037 Supabase 저장소 — STAGING → COMPLETED 원자적 프로모션 패턴.

GAP-D: atomic_complete_snapshot()은 DB RPC fn_ext037_complete_snapshot을 호출한다.
GAP-B: find_resumable_staging()으로 페이지 체크포인트 지원.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from services.ext037_chemical_safety.contract import (
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_STAGING,
    SOURCE_ID,
    TABLE_ITEMS,
    TABLE_SNAPSHOTS,
)
from services.ext037_chemical_safety.parse import Ext037Item

logger = logging.getLogger(__name__)


def _sb() -> Any:
    from db.supabase_client import get_supabase
    return get_supabase()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_staging_snapshot(
    run_id: str,
    *,
    source_id: str = SOURCE_ID,
    sb: Any = None,
) -> str:
    """STAGING 스냅샷 행 생성. snapshot_id 반환."""
    client = sb or _sb()
    row_data: dict[str, Any] = {
        "run_id": run_id,
        "source_id": source_id,
        "status": SNAPSHOT_STAGING,
        "last_page_no": 0,
        "created_at": _now_iso(),
    }
    res = client.table(TABLE_SNAPSHOTS).insert(row_data).execute()
    row = (res.data or [{}])[0]
    return str(row["id"])


def find_resumable_staging(source_id: str = SOURCE_ID, *, sb: Any = None) -> dict | None:
    """해당 소스의 기존 STAGING 스냅샷 반환. 없으면 None."""
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


def upsert_items(snapshot_id: str, items: list[Ext037Item], *, sb: Any = None) -> int:
    """스냅샷 ID 하위에 items 배치 upsert. 저장된 행 수 반환."""
    if not items:
        return 0
    client = sb or _sb()
    rows = [
        {
            "snapshot_id": snapshot_id,
            "datano": item.datano,
            "raw": item.raw,
            "created_at": _now_iso(),
        }
        for item in items
    ]
    res = client.table(TABLE_ITEMS).upsert(rows, on_conflict="snapshot_id,datano").execute()
    return len(res.data or [])


def save_page_checkpoint(
    snapshot_id: str,
    items: list[Ext037Item],
    page_no: int,
    api_total: int | None,
    *,
    run_id: str,
    sb: Any = None,
) -> int:
    """PATCH-02/03: 원자적 페이지 저장 + 체크포인트 갱신 (단일 DB 트랜잭션 via RPC).

    fn_ext037_save_page_checkpoint RPC가:
      0. 쓰기 전 소유권 + Lease 검증
      1. items upsert (snapshot_id,datano on_conflict)
      2. DB actual count 조회 (idempotent — 재실행 안전)
      3. checkpoint UPDATE (last_page_no, checkpoint_total_count = actual, checkpoint_api_total)
    Returns: 실제 DB unique item count.
    Raises PageFencedError if RPC returns RUN_FENCED.
    Raises RuntimeError on other RPC failures.
    """
    from services.public_data_sync.errors import PageFencedError
    client = sb or _sb()
    payload = [{"datano": item.datano, "raw": item.raw} for item in items]
    try:
        res = client.rpc("fn_ext037_save_page_checkpoint", {
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
        raise RuntimeError(f"fn_ext037_save_page_checkpoint RPC failed: {type(exc).__name__}") from exc


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

    RPC fn_ext037_complete_snapshot이 단일 트랜잭션에서:
      1. Run 소유권 검증: current_run_id 일치 + RUNNING + lease 유효
      2. snapshot_items 실제 count 검증 (== total_items)
      3. UPDATE snapshots SET status='COMPLETED' WHERE id=? AND source_id=? AND status='STAGING'
    조건 중 하나라도 실패하면 False 반환, 기존 COMPLETED 스냅샷 보존.
    """
    client = sb or _sb()
    try:
        res = client.rpc("fn_ext037_complete_snapshot", {
            "p_snapshot_id": snapshot_id,
            "p_source_id": source_id,
            "p_total_items": total_items,
            "p_content_hash": content_hash,
            "p_run_id": run_id,
        }).execute()
        data = res.data if hasattr(res, "data") else res
        return bool(data)
    except Exception as exc:
        raise RuntimeError(f"fn_ext037_complete_snapshot RPC failed: {type(exc).__name__}") from exc


def fail_snapshot(snapshot_id: str, *, run_id: str, error_message: str, sb: Any = None) -> None:
    """fn_ext037_fail_snapshot RPC — Run 소유권 검증 + STAGING guard 원자적 실행."""
    client = sb or _sb()
    client.rpc("fn_ext037_fail_snapshot", {
        "p_snapshot_id": snapshot_id,
        "p_run_id": run_id,
        "p_error_message": error_message,
    }).execute()


def compute_content_hash(items: list[Ext037Item]) -> str:
    """수집된 전체 항목의 결정적 해시 (순서 독립적)."""
    entries = sorted(
        (item.datano, json.dumps(item.raw, sort_keys=True, ensure_ascii=False))
        for item in items
    )
    payload = json.dumps(entries, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def compute_content_hash_from_db(snapshot_id: str, *, sb: Any = None) -> str:
    """Resume 시 DB에서 전체 항목을 페이지 순회하여 해시 계산."""
    client = sb or _sb()
    all_rows: list = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            client.table(TABLE_ITEMS)
            .select("datano,raw")
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
        (row["datano"], json.dumps(row.get("raw") or {}, sort_keys=True, ensure_ascii=False))
        for row in all_rows
    )
    payload = json.dumps(entries, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def get_latest_completed_snapshot(*, sb: Any = None) -> dict | None:
    """현행 COMPLETED 스냅샷 행 반환. 없으면 None."""
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
