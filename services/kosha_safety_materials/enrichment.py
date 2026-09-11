"""Current-membership detail enrichment — WP-1C-4B.

latest COMPLETED snapshot only. data.go.kr 금지. binary/R2/asset_versions 금지.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import asset_parser
from . import normalizer
from . import parser
from . import validator
from .detail_client import MaterialFetchError, StopRun, fetch_attachments, fetch_detail
from .writer import (
    ASSETS,
    CATALOG,
    DETAILS,
    ITEMS,
    SNAPSHOTS,
    VERSIONS,
    Writer,
)

OFFICIAL_EMBED_CONFIRMED = False
DEFAULT_BATCH = 100
MAX_BATCH = 200
MIN_BATCH = 1
DEFAULT_SLEEP_S = 0.35
CONCURRENCY = 1

_FAILURE_WRITE_CODES = frozenset({
    "DETAIL_HTTP_ERROR",
    "DETAIL_EMPTY",
    "INVALID_RESPONSE",
    "ATTACHMENT_PARSE_ERROR",
    "DETAIL_HTTP_404",
    "PARSER_FAILED",
    "CURRENT_NO_DETAIL",
})


class SnapshotInvalid(Exception):
    def __init__(self, reason: str = "SNAPSHOT_INVALID"):
        super().__init__(reason)
        self.reason = reason


def _bounded_reason(code: str | None) -> str:
    c = (code or "").strip()
    if c in ("CURRENT_NO_DETAIL", "DETAIL_EMPTY"):
        return "DETAIL_EMPTY"
    if c in _FAILURE_WRITE_CODES:
        return c
    if c == "PARSER_FAILED":
        return "PARSER_FAILED"
    return "INVALID_RESPONSE"


def _seq_sort_key(item: dict) -> tuple:
    seq = str(item.get("source_med_seq") or item.get("medseq") or "")
    mid = str(item.get("material_id") or "")
    if seq.isdigit():
        return (0, int(seq), mid)
    return (1, seq, mid)


def snapshot_precondition(store) -> dict:
    snap = store.latest_completed()
    if not snap or snap.get("status") != "COMPLETED":
        raise SnapshotInvalid("SNAPSHOT_INVALID")
    members = store.membership(snap["id"])
    unique = int(snap.get("unique_count") or 0)
    if len(members) != unique:
        raise SnapshotInvalid("SNAPSHOT_INVALID")
    return {"snapshot": snap, "membership": members, "membership_count": len(members)}


def select_pending(store, snapshot_id: str, *, limit: int) -> list[dict]:
    members = store.membership(snapshot_id)
    have = store.detail_ids()
    pending = [m for m in members if m.get("material_id") not in have]
    pending.sort(key=_seq_sort_key)
    return pending[:limit]


def counts(store) -> dict[str, int]:
    return {
        "catalog": store.count(CATALOG),
        "details": store.count(DETAILS),
        "assets": store.count(ASSETS),
        "snapshots": store.count(SNAPSHOTS),
        "snapshot_items": store.count(ITEMS),
        "asset_versions": store.count(VERSIONS),
    }


def prepare_failure(material_id: str, url: str, title: str, medseq: str, reason: str) -> dict:
    bounded = _bounded_reason(reason)
    fields = {
        "medSeq": medseq, "medName": title, "medGonggongnuri": None, "medNote": None,
        "contsRegYmd": None, "frstRegDt": None, "contsFbctnShpCd": None, "contsFbctnShpNm": None,
        "medThumbnailPath": None, "thumbPath": None, "medGonggongnuriNm": None,
    }
    row = normalizer.normalize_detail(
        material_id=material_id,
        catalog_url=url,
        catalog_title=title,
        fields=fields,
        assets=[],
        official_embed_confirmed=False,
        enrichment_status="FAILED",
        failure_reason=bounded,
    )
    row["kogl_type"] = "UNKNOWN"
    row["render_policy"] = "LINK_ONLY"
    row["content_type"] = "OTHER"
    row["license_name"] = None
    row["license_source_url"] = None
    row["official_embed_confirmed"] = False
    row["failure_reason"] = bounded
    row["source_content_hash"] = normalizer.canonical_hash(row, [])
    return row


def validate_and_write_failure(
    writer: Writer,
    *,
    material_id: str,
    url: str,
    title: str,
    medseq: str,
    reason: str,
) -> dict:
    identity = {"material_id": material_id, "source_url": url, "medseq": medseq}
    fail = prepare_failure(material_id, url, title, medseq, reason)
    fail["source_checked_at"] = datetime.now(timezone.utc).isoformat()
    fail["source_content_hash"] = normalizer.canonical_hash(fail, [])
    errs = validator.validate(fail, [], catalog_exists=True, requested_med_seq=medseq)
    if errs:
        return {
            **identity, "result": "BLOCKED", "failure_reason": ";".join(errs)[:200],
            "title": title, "writable": False, "validated": True, "errors": errs,
            "write": {"op": "BLOCKED", "detail_writes": 0, "asset_writes": 0},
        }
    wr = writer.upsert(fail, [], allow_update=False)
    return {
        **identity, "result": wr["op"] if wr["op"] != "INSERT" else "FAILED",
        "failure_reason": fail["failure_reason"],
        "title": title, "writable": True, "validated": True, "write": wr, "detail": fail,
    }


def enrich_one(
    item: dict,
    writer: Writer,
    *,
    fetch_detail_fn: Callable = fetch_detail,
    fetch_attachments_fn: Callable = fetch_attachments,
    sleep_s: float = 0,
    sleeper=time.sleep,
) -> dict:
    material_id = item.get("material_id") or item.get("id")
    medseq = str(item.get("source_med_seq") or item.get("medseq") or "")
    catalog = writer.catalog_get(material_id) if material_id else None
    title = (catalog or {}).get("title") or item.get("source_title") or item.get("title") or ""
    url = (catalog or {}).get("url") or item.get("source_url") or item.get("url") or ""
    identity = {"material_id": material_id, "source_url": url, "medseq": medseq, "title": title}

    if not catalog or not material_id:
        return {**identity, "result": "BLOCKED", "failure_reason": "catalog identity missing",
                "writable": False, "write": {"op": "BLOCKED", "detail_writes": 0, "asset_writes": 0}}

    existing = writer.details_get(material_id)
    if existing:
        return {**identity, "result": "SKIP_EXISTING", "write": {"op": "SKIP_EXISTING", "detail_writes": 0, "asset_writes": 0}}

    try:
        raw = fetch_detail_fn(medseq)
        if sleep_s:
            sleeper(sleep_s)
    except StopRun:
        raise
    except MaterialFetchError as e:
        if e.code in ("DETAIL_HTTP_404", "PARSER_FAILED", "DETAIL_HTTP_ERROR"):
            return validate_and_write_failure(
                writer, material_id=material_id, url=url, title=title, medseq=medseq, reason=e.code,
            )
        raise

    parsed = parser.parse_detail(raw.get("json"), medseq, raw.get("status"))
    if parsed["status"] == "MEDSEQ_MISMATCH":
        raise StopRun("MEDSEQ_MISMATCH", endpoint="selectMediaList")
    if parsed["status"] != "OK":
        code = parsed["failure_reason"] or parsed["status"]
        if parsed["status"] in ("INVALID_RESPONSE",) or code == "not object":
            code = "PARSER_FAILED" if parsed["status"] == "INVALID_RESPONSE" else code
        if parsed["status"] == "CURRENT_NO_DETAIL":
            code = "DETAIL_EMPTY"
        return validate_and_write_failure(
            writer, material_id=material_id, url=url, title=title, medseq=medseq, reason=code,
        )

    try:
        atch = fetch_attachments_fn(medseq)
        if sleep_s:
            sleeper(sleep_s)
    except StopRun:
        raise
    except MaterialFetchError as e:
        return validate_and_write_failure(
            writer, material_id=material_id, url=url, title=title, medseq=medseq,
            reason=e.code if e.code in _FAILURE_WRITE_CODES else "ATTACHMENT_PARSE_ERROR",
        )

    ap = asset_parser.parse_attachments(
        atch.get("json"), material_id=material_id, source_url=url,
        video_storage_false=True, http_status=atch.get("status"),
    )
    if not ap["ok"]:
        return validate_and_write_failure(
            writer, material_id=material_id, url=url, title=title, medseq=medseq,
            reason="ATTACHMENT_PARSE_ERROR",
        )

    fields = parsed["fields"]
    assets = ap["assets"]
    detail = normalizer.normalize_detail(
        material_id=material_id,
        catalog_url=url,
        catalog_title=title,
        fields=fields,
        assets=assets,
        official_embed_confirmed=OFFICIAL_EMBED_CONFIRMED,
        enrichment_status="OK",
    )
    detail["source_checked_at"] = datetime.now(timezone.utc).isoformat()
    detail["source_content_hash"] = normalizer.canonical_hash(detail, assets)
    errs = validator.validate(detail, assets, catalog_exists=True, requested_med_seq=medseq)
    if errs:
        return {
            **identity, "result": "BLOCKED", "failure_reason": ";".join(errs)[:200],
            "writable": False, "errors": errs,
            "write": {"op": "BLOCKED", "detail_writes": 0, "asset_writes": 0},
        }
    wr = writer.upsert(detail, assets, allow_update=False)
    status = wr["op"]
    if detail["enrichment_status"] == "PARTIAL" and status == "INSERT":
        status = "PARTIAL"
    return {
        **identity,
        "result": status,
        "kogl_type": detail["kogl_type"],
        "render_policy": detail["render_policy"],
        "content_type": detail["content_type"],
        "hash": detail["source_content_hash"],
        "asset_count": len(assets),
        "official_embed": False,
        "writable": True,
        "write": wr,
        "detail": detail,
        "assets": assets,
    }


def dry_run_plan(store, *, batch_size: int = DEFAULT_BATCH) -> dict:
    pre = snapshot_precondition(store)
    snap = pre["snapshot"]
    members = pre["membership"]
    have = store.detail_ids()
    member_ids = {m["material_id"] for m in members}
    existing_in_current = len(member_ids & have)
    pending = [m for m in members if m.get("material_id") not in have]
    pending.sort(key=_seq_sort_key)
    first = pending[: max(MIN_BATCH, min(int(batch_size), MAX_BATCH))]
    before = counts(store)
    return {
        "status": "DRY_RUN",
        "run_snapshot_id": snap["id"],
        "run_snapshot_hash": snap.get("snapshot_hash"),
        "membership": len(members),
        "existing_detail_in_current": existing_in_current,
        "pending_missing": len(pending),
        "batch_size": max(MIN_BATCH, min(int(batch_size), MAX_BATCH)),
        "planned_first_batch": len(first),
        "planned_first_medseqs": [x.get("source_med_seq") for x in first[:5]],
        "api_calls": 0,
        "counts_before": before,
        "counts_after": counts(store),
        "fixed_for_run": True,
    }


def run_one_batch(
    store,
    *,
    run_snapshot_id: str,
    batch_size: int = DEFAULT_BATCH,
    dry_run: bool = False,
    sleep_s: float = DEFAULT_SLEEP_S,
    fetch_detail_fn=fetch_detail,
    fetch_attachments_fn=fetch_attachments,
    sleeper=time.sleep,
    log=print,
) -> dict:
    if CONCURRENCY != 1:
        raise RuntimeError("concurrency must be 1")
    size = max(MIN_BATCH, min(int(batch_size), MAX_BATCH))
    writer = Writer(dry_run=dry_run, store=store)
    if hasattr(store, "reconnect"):
        store.reconnect()
    selected = select_pending(store, run_snapshot_id, limit=size)
    attempted = 0
    success = 0
    failed = 0
    skipped = 0
    no_change = 0
    last_medseq = None
    last_success = None
    stop_reason = None
    http_counts = {"429": 0, "403": 0, "401": 0, "5xx": 0, "timeouts": 0}
    detail_calls = 0
    atch_calls = 0
    new_details = 0
    new_assets = 0

    def _fd(seq):
        nonlocal detail_calls
        detail_calls += 1
        return fetch_detail_fn(seq)

    def _fa(seq):
        nonlocal atch_calls
        atch_calls += 1
        return fetch_attachments_fn(seq)

    for item in selected:
        last_medseq = str(item.get("source_med_seq") or "")
        attempted += 1
        try:
            r = enrich_one(
                item, writer,
                fetch_detail_fn=_fd,
                fetch_attachments_fn=_fa,
                sleep_s=0 if dry_run else sleep_s,
                sleeper=sleeper,
            )
        except StopRun as e:
            stop_reason = e.reason
            if e.http_status == 429:
                http_counts["429"] += 1
            elif e.http_status == 403:
                http_counts["403"] += 1
            elif e.http_status == 401:
                http_counts["401"] += 1
            elif e.http_status and e.http_status >= 500:
                http_counts["5xx"] += 1
            elif e.reason == "TRANSIENT_UPSTREAM_FAILURE" and not e.http_status:
                http_counts["timeouts"] += 1
            attempted -= 1  # current material not completed
            break
        except Exception as e:
            if type(e).__name__ in (
                "APIError", "RemoteProtocolError", "ConnectError",
                "ReadTimeout", "WriteTimeout", "ConnectTimeout", "ReadError",
            ):
                stop_reason = "TRANSIENT_UPSTREAM_FAILURE"
                attempted -= 1
                break
            raise
        wr = r.get("write") or {}
        new_details += int(wr.get("detail_writes") or 0)
        new_assets += int(wr.get("asset_writes") or 0)
        result = r.get("result")
        if result in ("INSERT", "OK", "PARTIAL"):
            success += 1
            last_success = last_medseq
        elif result == "FAILED":
            failed += 1
            last_success = last_medseq
        elif result == "NO_CHANGE":
            no_change += 1
        elif result == "SKIP_EXISTING":
            skipped += 1
        elif result == "BLOCKED":
            failed += 1

    remaining = len(select_pending(store, run_snapshot_id, limit=10**9))
    log(
        f"batch snapshot_id={run_snapshot_id} selected={len(selected)} "
        f"attempted={attempted} success={success} failed={failed} "
        f"remaining={remaining} last_medseq={last_medseq}"
    )
    status = "BATCH_OK"
    if stop_reason:
        status = stop_reason
    elif remaining == 0:
        status = "FULL_SWEEP_COMPLETE"
    return {
        "status": status,
        "snapshot_id": run_snapshot_id,
        "selected": len(selected),
        "attempted": attempted,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "no_change": no_change,
        "remaining": remaining,
        "last_medseq": last_medseq,
        "last_successful_medseq": last_success,
        "detail_api_calls": detail_calls,
        "attachment_metadata_calls": atch_calls,
        "new_detail_rows": new_details,
        "new_asset_rows": new_assets,
        "http": http_counts,
        "stop_reason": stop_reason,
        "endpoint_class": None if not stop_reason else stop_reason,
    }


def run_until_done(
    store,
    *,
    batch_size: int = DEFAULT_BATCH,
    dry_run: bool = False,
    sleep_s: float = DEFAULT_SLEEP_S,
    fetch_detail_fn=fetch_detail,
    fetch_attachments_fn=fetch_attachments,
    sleeper=time.sleep,
    log=print,
    max_batches: Optional[int] = None,
) -> dict:
    pre = snapshot_precondition(store)
    snap = pre["snapshot"]
    run_id = snap["id"]
    run_hash = snap.get("snapshot_hash")
    before = counts(store)
    pending0 = len(select_pending(store, run_id, limit=10**9))
    current_with = pre["membership_count"] - pending0
    totals = {
        "batches": 0,
        "detail_api_calls": 0,
        "attachment_metadata_calls": 0,
        "attempted": 0,
        "new_detail_rows": 0,
        "new_asset_rows": 0,
        "NO_CHANGE": 0,
        "FAILED": 0,
        "success": 0,
        "http": {"429": 0, "403": 0, "401": 0, "5xx": 0, "timeouts": 0},
    }
    last = None
    status = "FULL_SWEEP_COMPLETE"
    while True:
        if max_batches is not None and totals["batches"] >= max_batches:
            status = last["status"] if last else "BATCH_OK"
            break
        try:
            last = run_one_batch(
                store,
                run_snapshot_id=run_id,
                batch_size=batch_size,
                dry_run=dry_run,
                sleep_s=sleep_s,
                fetch_detail_fn=fetch_detail_fn,
                fetch_attachments_fn=fetch_attachments_fn,
                sleeper=sleeper,
                log=log,
            )
        except StopRun as e:
            status = e.reason
            remaining = len(select_pending(store, run_id, limit=10**9))
            last = {
                "status": e.reason,
                "stop_reason": e.reason,
                "remaining": remaining,
                "detail_api_calls": 0,
                "attachment_metadata_calls": 0,
                "attempted": 0,
                "new_detail_rows": 0,
                "new_asset_rows": 0,
                "no_change": 0,
                "failed": 0,
                "success": 0,
                "http": {"429": 0, "403": 0, "401": 0, "5xx": 0, "timeouts": 0},
                "last_successful_medseq": None,
            }
            break
        totals["batches"] += 1
        totals["detail_api_calls"] += last["detail_api_calls"]
        totals["attachment_metadata_calls"] += last["attachment_metadata_calls"]
        totals["attempted"] += last["attempted"]
        totals["new_detail_rows"] += last["new_detail_rows"]
        totals["new_asset_rows"] += last["new_asset_rows"]
        totals["NO_CHANGE"] += last["no_change"]
        totals["FAILED"] += last["failed"]
        totals["success"] += last["success"]
        for k in totals["http"]:
            totals["http"][k] += last["http"][k]
        if last["status"] in (
            "QUOTA_BLOCKED", "ACCESS_BLOCKED", "UPSTREAM_UNSTABLE",
            "TRANSIENT_UPSTREAM_FAILURE", "MEDSEQ_MISMATCH", "FULL_SWEEP_COMPLETE",
        ):
            status = last["status"]
            break
        if last["remaining"] == 0:
            status = "FULL_SWEEP_COMPLETE"
            break
        if last["selected"] == 0:
            status = "FULL_SWEEP_COMPLETE"
            break
        if dry_run:
            status = "DRY_RUN"
            break

    after = counts(store)
    remaining = last["remaining"] if last else pending0
    members = store.membership(run_id)
    member_ids = {m["material_id"] for m in members}
    dist = {"OK": 0, "PARTIAL": 0, "FAILED": 0, "missing": 0}
    for mid in member_ids:
        row = store.details_get(mid)
        if not row:
            dist["missing"] += 1
        else:
            st = row.get("enrichment_status") or "OK"
            if st in dist:
                dist[st] += 1
            else:
                dist["OK"] += 1

    return {
        "status": status,
        "run_snapshot_id": run_id,
        "run_snapshot_hash": run_hash,
        "fixed_for_run": True,
        "membership": pre["membership_count"],
        "counts_before": before,
        "counts_after": after,
        "current_with_detail_before": current_with,
        "current_missing_before": pending0,
        "batch_size": batch_size,
        "concurrency": CONCURRENCY,
        "delay": sleep_s,
        "resume_source": "DB",
        "last": last,
        "totals": totals,
        "remaining": remaining,
        "distribution": dist,
        "last_successful_medseq": last.get("last_successful_medseq") if last else None,
        "stop_reason": last.get("stop_reason") if last else None,
        "dml": dict(store.dml),
        "binary_gets": getattr(store, "binary_gets", 0),
        "r2_ops": getattr(store, "r2_ops", 0),
        "data_go_kr_calls": getattr(store, "data_go_kr_calls", 0),
    }
