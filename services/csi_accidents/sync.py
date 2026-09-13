"""CSI accident official CSV sync. Default is dry-run. Graph/R2 writes stay closed."""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from urllib.request import Request, urlopen

from services.csi_accidents.contract import (
    APPLY_ENABLE_ENV,
    ATCH_FILE_ID,
    DATASET_EFFECTIVE_DATE,
    DATASET_ID,
    DATASET_URL,
    DECLARED_ROWS,
    DOWNLOAD_URL,
    FINGERPRINT_VERSION,
    HEADER_COUNT,
    OFFICIAL_BYTES,
    OFFICIAL_FILENAME,
    OFFICIAL_HEADERS,
    OFFICIAL_SHA256,
    SOURCE_ENCODING,
    SOURCE_ID,
)
from services.csi_accidents.graph_adapter import GRAPH_WRITES_OPEN
from services.csi_accidents.identity import (
    CaseRecord,
    ResolvedRow,
    normalize_row,
    resolve_identities,
)
from services.csi_accidents.parse import CsiSyncError, parse_official_bytes
from services.csi_accidents.storage_policy import (
    R2_WRITES_OPEN,
    proposed_object_key,
    storage_report,
)
from services.csi_accidents.store import MemoryCsiStore, SupabaseCsiStore
from services.time import now_kst, serialize_business_datetime


@dataclass
class SyncResult:
    status: str
    dry_run: bool = True
    dataset_id: str = DATASET_ID
    filename: Optional[str] = None
    bytes: int = 0
    file_sha256: Optional[str] = None
    encoding: str = SOURCE_ENCODING
    declared_rows: int = DECLARED_ROWS
    parsed_rows: int = 0
    row_count_mismatch: bool = True
    malformed_rows: int = 0
    empty_rows: int = 0
    ready: int = 0
    hold: int = 0
    collision_fingerprints: int = 0
    new: int = 0
    matched: int = 0
    changed: int = 0
    unchanged: int = 0
    source_version_count: int = 0
    snapshot_id: Optional[str] = None
    business_dml: int = 0
    graph_writes: int = 0
    r2_writes: int = 0
    kosha_writes: int = 0
    failure_reason: Optional[str] = None
    extra: dict = field(default_factory=dict)


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_official_csv(url: str = DOWNLOAD_URL, timeout: int = 120) -> bytes:
    if ATCH_FILE_ID not in url.replace("&amp;", "&"):
        raise CsiSyncError("DATASET_MISMATCH", "official atchFileId missing")
    req = Request(url, headers={"User-Agent": "tai-api-csi-sync/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data


def assert_file_contract(data: bytes, *, filename: str) -> dict:
    digest = file_sha256(data)
    if filename != OFFICIAL_FILENAME:
        raise CsiSyncError("DATASET_MISMATCH", f"filename {filename!r}")
    if digest != OFFICIAL_SHA256:
        raise CsiSyncError(
            "DATASET_MISMATCH",
            f"sha256 {digest} != official {OFFICIAL_SHA256}",
        )
    if len(data) != OFFICIAL_BYTES:
        raise CsiSyncError(
            "DATASET_MISMATCH",
            f"bytes {len(data)} != official {OFFICIAL_BYTES}",
        )
    return {
        "filename": filename,
        "bytes": len(data),
        "sha256": digest,
        "encoding": SOURCE_ENCODING,
    }


def _history(store: Any) -> list[CaseRecord]:
    """Matching history is COMPLETED snapshot evidence only."""
    recs: list[CaseRecord] = []
    for row in store.load_reconciliation_history():
        recs.append(
            CaseRecord(
                content_id=row["content_id"],
                identity_fingerprint=row["identity_fingerprint"],
                identity_status=row["identity_status"],
                source_content_hashes=set(row.get("source_content_hashes") or []),
            )
        )
    return recs


def _item_row(resolved: ResolvedRow, snapshot_id: str) -> dict:
    r = resolved.row
    return {
        "snapshot_id": snapshot_id,
        "row_number": r.row_number,
        "content_id": resolved.content_id,
        "source_content_hash": r.source_content_hash,
        "identity_fingerprint": r.identity_fingerprint,
        "identity_status": resolved.identity_status,
        "identity_reason": resolved.identity_reason,
        "title": r.title,
        "occurred_at": r.occurred_at,
        "construction_type": r.construction_type,
        "process_major": r.process_major,
        "process_minor": r.process_minor,
        "object_major": r.object_major,
        "object_minor": r.object_minor,
        "work_process": r.work_process,
        "accident_type_major": r.accident_type_major,
        "accident_type": r.accident_type,
        "cause_major": r.cause_major,
        "cause_mid": r.cause_mid,
        "cause_minor": r.cause_minor,
        "cause_detail": r.cause_detail,
        "summary": r.summary,
        "death_count": r.death_count,
        "injury_count": r.injury_count,
        "source_dataset_url": r.source_dataset_url,
        "source_item_url": r.source_item_url,
        "raw_json": r.raw,
    }


def _case_row(resolved: ResolvedRow, now_s: str) -> dict:
    return {
        "content_id": resolved.content_id,
        "source_id": SOURCE_ID,
        "source_key": None,
        "identity_fingerprint": resolved.row.identity_fingerprint,
        "identity_status": resolved.identity_status,
        "identity_reason": resolved.identity_reason,
        "fingerprint_version": FINGERPRINT_VERSION,
        "first_seen_at": now_s,
        "updated_at": now_s,
        "source_content_hash": resolved.row.source_content_hash,
    }


def _match_stats(assigned: list[ResolvedRow], history: list[CaseRecord]) -> dict:
    hist_ids = {c.content_id for c in history}
    hist_hashes: dict[str, set[str]] = {}
    for c in history:
        hist_hashes[c.content_id] = set(c.source_content_hashes)
    new = matched = changed = unchanged = 0
    seen = set()
    for a in assigned:
        if a.content_id in seen:
            continue
        seen.add(a.content_id)
        if a.content_id not in hist_ids:
            new += 1
            continue
        matched += 1
        prev = hist_hashes.get(a.content_id, set())
        if a.row.source_content_hash in prev:
            unchanged += 1
        else:
            changed += 1
    return {"new": new, "matched": matched, "changed": changed, "unchanged": unchanged}


def _reject(code: str, message: str, dry_run: bool) -> SyncResult:
    return SyncResult(
        status="REJECT",
        dry_run=dry_run,
        failure_reason=f"{code}: {message}",
        extra={"error_code": code, "errors": {code: message}},
        graph_writes=0,
        r2_writes=0,
        kosha_writes=0,
        business_dml=0,
    )


def sync_csi_accidents(
    *,
    data: bytes,
    filename: str = OFFICIAL_FILENAME,
    dry_run: bool = True,
    store: Any = None,
    now: Optional[datetime] = None,
    uuid_fn=None,
    skip_file_pin: bool = False,
) -> SyncResult:
    extra = {
        "storage": storage_report(),
        "graph_writes_open": GRAPH_WRITES_OPEN,
        "r2_writes_open": R2_WRITES_OPEN,
        "source_key_available": False,
        "dataset_url": DATASET_URL,
        "errors": {},
    }
    if not GRAPH_WRITES_OPEN:
        extra["graph_write_path"] = "CLOSED"
    try:
        if not skip_file_pin:
            assert_file_contract(data, filename=filename)
        digest = file_sha256(data)
        parsed = parse_official_bytes(data)
        rows = [normalize_row(raw, i) for i, raw in enumerate(parsed.rows, start=1)]
        parsed_n = len(rows)
        mismatch = parsed_n != DECLARED_ROWS
        if parsed.headers != list(OFFICIAL_HEADERS) or len(parsed.headers) != HEADER_COUNT:
            raise CsiSyncError("HEADER_MISMATCH", "header identity failed")
    except CsiSyncError as e:
        return _reject(e.code, e.message, dry_run)

    if store is None:
        store = MemoryCsiStore()

    existing = store.get_snapshot_by_sha(digest) if hasattr(store, "get_snapshot_by_sha") else None
    if existing:
        conflict = []
        for key, val in (
            ("filename", filename),
            ("bytes", len(data)),
            ("encoding", SOURCE_ENCODING),
            ("declared_rows", DECLARED_ROWS),
            ("dataset_id", DATASET_ID),
            ("effective_date", DATASET_EFFECTIVE_DATE),
        ):
            if existing.get(key) not in (None, val) and existing.get(key) != val:
                conflict.append(key)
        if existing.get("parsed_rows") not in (None, parsed_n) and existing.get("parsed_rows") != parsed_n:
            conflict.append("parsed_rows")
        if conflict:
            return _reject(
                "DUPLICATE_SHA_CONFLICT",
                f"same file sha with conflicting metadata: {conflict}",
                dry_run,
            )

    history = _history(store)
    try:
        assigned, id_stats = resolve_identities(rows, history, uuid_fn=uuid_fn)
    except CsiSyncError as e:
        return _reject(e.code, e.message, dry_run)

    match = _match_stats(assigned, history)
    versions = {a.row.source_content_hash for a in assigned}
    result = SyncResult(
        status="VALIDATED",
        dry_run=dry_run,
        filename=filename,
        bytes=len(data),
        file_sha256=digest,
        encoding=SOURCE_ENCODING,
        declared_rows=DECLARED_ROWS,
        parsed_rows=parsed_n,
        row_count_mismatch=mismatch,
        malformed_rows=parsed.malformed_rows,
        empty_rows=parsed.empty_rows,
        ready=id_stats["ready_rows"],
        hold=id_stats["hold_rows"],
        collision_fingerprints=len(id_stats["collision_fingerprints"]),
        new=match["new"],
        matched=match["matched"],
        changed=match["changed"],
        unchanged=match["unchanged"],
        source_version_count=len(versions),
        extra=extra,
    )
    extra["collision_fingerprint_ids"] = id_stats["collision_fingerprints"]
    extra["row_count_mismatch_recorded"] = mismatch
    extra["declared_vs_parsed"] = {"declared": DECLARED_ROWS, "parsed": parsed_n}
    extra["history_source"] = "COMPLETED_SNAPSHOTS_ONLY"

    if dry_run:
        result.status = "DRY_RUN"
        result.business_dml = 0
        result.graph_writes = 0
        result.r2_writes = 0
        result.kosha_writes = 0
        extra["db_write"] = 0
        return result

    if os.getenv(APPLY_ENABLE_ENV) != "1":
        return _reject(
            "APPLY_GATE",
            f"{APPLY_ENABLE_ENV}=1 required for production write",
            dry_run=False,
        )

    if existing and existing.get("status") == "COMPLETED":
        result.status = "SNAPSHOT_NO_CHANGE"
        result.snapshot_id = existing.get("id")
        result.business_dml = 0
        return result

    clock = now or now_kst()
    now_s = serialize_business_datetime(clock)
    snapshot_id = str(uuid.uuid4())
    running = {
        "id": snapshot_id,
        "status": "RUNNING",
        "dataset_id": DATASET_ID,
        "effective_date": DATASET_EFFECTIVE_DATE,
        "filename": filename,
        "bytes": len(data),
        "file_sha256": digest,
        "encoding": SOURCE_ENCODING,
        "declared_rows": DECLARED_ROWS,
        "parsed_rows": parsed_n,
        "row_count_mismatch": mismatch,
        "header_count": HEADER_COUNT,
        "download_url": DOWNLOAD_URL,
        "proposed_raw_object_key": proposed_object_key(
            DATASET_EFFECTIVE_DATE, digest, filename
        ),
        "r2_written": False,
        "started_at": now_s,
        "completed_at": None,
        "failure_reason": None,
    }
    try:
        store.insert_running_snapshot(running)
        store.upsert_cases([_case_row(a, now_s) for a in assigned])
        store.mark_hold(id_stats["hold_content_ids"], "FINGERPRINT_COLLISION")
        store.insert_membership([_item_row(a, snapshot_id) for a in assigned])
        store.complete_snapshot(snapshot_id, now_s)
    except Exception as e:
        try:
            store.fail_snapshot(snapshot_id, str(e), now_s)
        except Exception:
            pass
        result.status = "FAILED"
        result.snapshot_id = snapshot_id
        result.failure_reason = str(e)[:500]
        result.business_dml = getattr(store, "dml", 1)
        extra["previous_completed_preserved"] = True
        extra["errors"] = {"FAILED": result.failure_reason}
        return result

    result.status = "COMPLETED"
    result.snapshot_id = snapshot_id
    result.business_dml = getattr(store, "dml", 1)
    result.graph_writes = getattr(store, "graph_writes", 0)
    result.r2_writes = getattr(store, "r2_writes", 0)
    result.kosha_writes = getattr(store, "kosha_writes", 0)
    extra["db_write"] = result.business_dml
    return result


__all__ = [
    "SyncResult",
    "SupabaseCsiStore",
    "sync_csi_accidents",
    "download_official_csv",
    "assert_file_contract",
]
