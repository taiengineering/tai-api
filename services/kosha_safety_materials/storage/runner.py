"""WP-1C-5B production storage runner. MemoryVersionStore forbidden on apply."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .. import license_policy
from .. import parser
from ..detail_client import StopRun, fetch_attachments, fetch_detail
from ..enrichment import snapshot_precondition
from .binary_fetch import BinaryFetchError, fetch_attachment_binary, fetch_file_list
from .eligibility import (
    EligibilityError,
    is_eligible_asset,
    is_eligible_detail,
    live_kogl_ok,
    pending_without_version,
    require_asset_id,
    sort_pending_key,
)
from .r2_store import R2Error, R2Store, credentials_from_env, make_s3_client
from .resolve import ResolutionError, match_downloadable_file, match_logical_attachment
from .store import StorageError, store_asset_original
from .version_service import (
    MemoryVersionStore,
    VersionError,
    assert_production_versions,
)

BATCH_SIZE = 20
CONCURRENCY = 1


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_fetch_stop(err: Exception) -> None:
    status = getattr(err, "status", None) or getattr(err, "http_status", None)
    if status == 429:
        raise StopRun("QUOTA_BLOCKED", http_status=429)
    if status in (401, 403):
        raise StopRun("ACCESS_BLOCKED", http_status=status)
    if status and int(status) >= 500:
        raise StopRun("TRANSIENT_UPSTREAM_FAILURE", http_status=status)
    if getattr(err, "code", None) == "TRANSIENT_UPSTREAM_FAILURE":
        raise StopRun("TRANSIENT_UPSTREAM_FAILURE")
    if getattr(err, "reason", None) in ("QUOTA_BLOCKED", "ACCESS_BLOCKED", "TRANSIENT_UPSTREAM_FAILURE"):
        raise err


class StorageQuery:
    def __init__(self, sb):
        self.sb = sb

    def _range(self, q, start, n=1000):
        return q.range(start, start + n - 1).execute()

    def versioned_asset_ids(self) -> set:
        ids: set = set()
        start = 0
        while True:
            r = self._range(
                self.sb.table("kosha_safety_material_asset_versions")
                .select("asset_id")
                .eq("is_current_version", True),
                start,
            )
            batch = r.data or []
            for row in batch:
                aid = row.get("asset_id")
                if aid is None or aid == "" or aid == "pending":
                    raise StopRun("ASSET_ID_REQUIRED")
                ids.add(aid)
            if len(batch) < 1000:
                break
            start += 1000
        return ids

    def details_for(self, material_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(material_ids), 100):
            chunk = material_ids[i:i + 100]
            r = (
                self.sb.table("kosha_safety_material_details")
                .select("material_id,source_med_seq,source_url,source_title,kogl_type,content_type,enrichment_status,license_name,license_source_url")
                .in_("material_id", chunk)
                .execute()
            )
            for row in r.data or []:
                out[row["material_id"]] = row
        return out

    def assets_for(self, material_ids: list[str]) -> list[dict]:
        rows: list[dict] = []
        for i in range(0, len(material_ids), 50):
            chunk = material_ids[i:i + 50]
            start = 0
            while True:
                r = self._range(
                    self.sb.table("kosha_safety_material_assets")
                    .select("id,material_id,asset_type,file_name,checksum,file_size,mime_type")
                    .in_("material_id", chunk),
                    start,
                )
                batch = r.data or []
                rows.extend(batch)
                if len(batch) < 1000:
                    break
                start += 1000
        return rows

    def current_versions(self) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            r = self._range(
                self.sb.table("kosha_safety_material_asset_versions")
                .select("id,asset_id,material_id,source_asset_key,content_checksum,storage_bucket,storage_key,is_current_version,license_observed_type,is_derivative")
                .eq("is_current_version", True),
                start,
            )
            batch = r.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            start += 1000
        return rows


def collect_eligible(store, query: StorageQuery) -> dict:
    pre = snapshot_precondition(store)
    snap = pre["snapshot"]
    members = pre["membership"]
    member_ids = [m["material_id"] for m in members]
    membership = set(member_ids)
    details = query.details_for(member_ids)
    assets = query.assets_for(member_ids)
    eligible: list[dict] = []
    video_excluded = 0
    type1 = type3 = 0
    for a in assets:
        d = details.get(a.get("material_id") or "")
        if not d:
            continue
        if (a.get("asset_type") or "").upper() == "VIDEO" or (d.get("content_type") or "").upper() == "VIDEO":
            video_excluded += 1
            continue
        if not is_eligible_asset(a, d, membership):
            continue
        item = {
            "asset_id": a.get("id"),
            "material_id": a["material_id"],
            "asset_type": a.get("asset_type"),
            "file_name": a.get("file_name"),
            "file_size": a.get("file_size"),
            "mime_type": a.get("mime_type"),
            "source_asset_key": a.get("checksum"),
            "checksum": a.get("checksum"),
            "kogl_type": d.get("kogl_type"),
            "content_type": d.get("content_type"),
            "source_med_seq": d.get("source_med_seq"),
            "source_url": d.get("source_url"),
            "source_title": d.get("source_title"),
            "license_name": d.get("license_name"),
            "license_source_url": d.get("license_source_url"),
        }
        eligible.append(item)
        if d.get("kogl_type") == "1":
            type1 += 1
        elif d.get("kogl_type") == "3":
            type3 += 1
    versioned_ids = query.versioned_asset_ids()
    try:
        pending = pending_without_version(eligible, versioned_ids)
    except EligibilityError as e:
        raise StopRun(e.code) from e
    return {
        "snapshot_id": snap["id"],
        "snapshot_hash": snap.get("snapshot_hash"),
        "membership": len(members),
        "eligible_materials": len({e["material_id"] for e in eligible}),
        "eligible_assets": len(eligible),
        "already_versioned": sum(1 for e in eligible if e.get("asset_id") in versioned_ids),
        "pending": pending,
        "pending_count": len(pending),
        "Type1": type1,
        "Type3": type3,
        "VIDEO_excluded": video_excluded,
        "fixed": True,
    }


def dry_run_plan(store, query: StorageQuery) -> dict:
    plan = collect_eligible(store, query)
    pending = plan.pop("pending")
    t1 = sum(1 for p in pending if p["kogl_type"] == "1")
    t3 = sum(1 for p in pending if p["kogl_type"] == "3")
    return {
        "status": "DRY_RUN",
        **plan,
        "pending": len(pending),
        "Type1_pending": t1,
        "Type3_pending": t3,
        "kosha_binary_get": 0,
        "r2_put": 0,
        "version_dml": 0,
    }


def verify_pilot_objects(query: StorageQuery, r2: R2Store) -> dict:
    rows = query.current_versions()
    if len(rows) != 2:
        raise StorageError("PILOT_VERSION_COUNT", str(len(rows)))
    results = []
    for row in rows:
        if row.get("storage_bucket") and row["storage_bucket"] != r2.bucket:
            raise R2Error("UNEXPECTED_BUCKET", row["storage_bucket"])
        status = r2.verify_existing(row["storage_key"], row["content_checksum"])
        results.append({
            "id": row["id"],
            "material_id": row["material_id"],
            "storage_key": row["storage_key"],
            "status": status,
        })
    if len(results) != 2 or any(r["status"] not in ("OBJECT_EXISTS_VERIFIED", "LEGACY_OBJECT") for r in results):
        raise StorageError("PILOT_INTEGRITY_FAILED")
    return {"integrity": "2/2", "rows": results, "r2_put": 0, "r2_delete": 0}


def _store_one(
    item: dict,
    *,
    membership_ids: set[str],
    r2: R2Store,
    versions,
    fetch_detail_fn=fetch_detail,
    fetch_atch_fn=fetch_attachments,
    fetch_file_list_fn=fetch_file_list,
    fetch_binary_fn=fetch_attachment_binary,
    sleeper=time.sleep,
) -> dict:
    assert_production_versions(versions)
    try:
        require_asset_id(item)
    except EligibilityError as e:
        raise StorageError(e.code) from e
    mid = item["material_id"]
    if mid not in membership_ids:
        raise StorageError("HISTORICAL_STORAGE_FORBIDDEN")
    medseq = str(item["source_med_seq"])
    try:
        raw = fetch_detail_fn(medseq)
    except StopRun:
        raise
    except Exception as e:
        map_fetch_stop(e)
        raise StorageError("BINARY_INTEGRITY_BLOCKED", type(e).__name__) from e
    parsed = parser.parse_detail(raw.get("json"), medseq, raw.get("status"))
    if parsed["status"] != "OK":
        raise StorageError("BINARY_INTEGRITY_BLOCKED", parsed.get("failure_reason") or parsed["status"])
    fields = parsed["fields"]
    live_kogl = license_policy.normalize_kogl_type(None if fields.get("medGonggongnuri") is None else str(fields.get("medGonggongnuri")))
    changed = live_kogl_ok(item["kogl_type"], live_kogl)
    if changed:
        raise StorageError(changed)
    try:
        atch = fetch_atch_fn(medseq)
        hit = match_logical_attachment(
            material_id=mid,
            expected_checksum=item["checksum"],
            expected_filename=item.get("file_name"),
            atch_json=atch.get("json"),
            http_status=atch.get("status"),
            requested_med_seq=medseq,
            response_med_seq=fields.get("medSeq"),
        )
        file_list = fetch_file_list_fn(str(hit.get("contsAtcflNo") or ""))
        dl = match_downloadable_file(
            file_list, file_name=hit.get("file_name") or item.get("file_name"),
            atcfl_no=str(hit.get("contsAtcflNo") or ""),
        )
    except StopRun:
        raise
    except ResolutionError as e:
        raise StorageError(e.code) from e
    except Exception as e:
        map_fetch_stop(e)
        raise StorageError("SOURCE_ASSET_RESOLUTION_BLOCKED") from e

    expect_pdf = (item.get("asset_type") or "").upper() == "PDF"

    def fetch_fn(**kwargs):
        try:
            return fetch_binary_fn(
                kogl_type=live_kogl,
                content_type=item.get("content_type") or item.get("asset_type"),
                atcfl_no=dl["atcfl_no"],
                atcfl_seq=dl["atcfl_seq"],
                file_name=dl.get("file_name"),
                mime_type=dl.get("mime_type") or item.get("mime_type"),
                expect_pdf=expect_pdf,
            )
        except BinaryFetchError as e:
            map_fetch_stop(e)
            if e.code == "TRANSIENT_UPSTREAM_FAILURE":
                raise StopRun("TRANSIENT_UPSTREAM_FAILURE") from e
            raise StorageError("BINARY_INTEGRITY_BLOCKED", e.code) from e

    payload = {
        "asset_id": item.get("asset_id"),
        "source_file_name": dl.get("file_name") or item.get("file_name"),
        "source_content_type": dl.get("mime_type") or item.get("mime_type"),
        "source_file_size": item.get("file_size"),
        "source_fetched_at": _utc(),
        "license_observed_at": _utc(),
        "license_observed_type": live_kogl,
        "license_name": fields.get("medGonggongnuriNm"),
        "license_source_url": item.get("source_url"),
        "storage_basis": "KOGL",
        "source_med_seq": medseq,
        "source_url": item.get("source_url"),
        "med_gonggongnuri_raw": None if fields.get("medGonggongnuri") is None else str(fields.get("medGonggongnuri")),
        "med_gonggongnuri_nm_raw": None if fields.get("medGonggongnuriNm") is None else str(fields.get("medGonggongnuriNm")),
        "is_derivative": False,
    }
    out = store_asset_original(
        kogl_type=live_kogl,
        content_type=item.get("content_type") or item.get("asset_type"),
        material_id=mid,
        atcfl_no=dl["atcfl_no"],
        atcfl_seq=dl["atcfl_seq"],
        file_name=dl.get("file_name") or item.get("file_name") or "file",
        mime_type=dl.get("mime_type") or item.get("mime_type"),
        membership_ids=membership_ids,
        fetch_fn=fetch_fn,
        r2=r2,
        versions=versions,
        version_payload=payload,
        dry_run=False,
    )
    cur = versions.current(out["source_asset_key"])
    if not cur or cur.get("content_checksum") != out["content_checksum"] or cur.get("storage_key") != out["storage_key"]:
        raise StorageError("VERSION_READBACK_MISMATCH")
    if versions.current_count(out["source_asset_key"]) != 1:
        raise StorageError("CURRENT_NOT_UNIQUE")
    return out


def apply_assets(
    items: list[dict],
    *,
    store,
    query: StorageQuery,
    r2: R2Store,
    versions,
    log=print,
) -> dict:
    if CONCURRENCY != 1:
        raise RuntimeError("concurrency must be 1")
    assert_production_versions(versions)
    pre = snapshot_precondition(store)
    membership_ids = {m["material_id"] for m in pre["membership"]}
    attempted = stored = no_change = new_v = promoted = 0
    last = None
    for item in items:
        attempted += 1
        try:
            r = _store_one(item, membership_ids=membership_ids, r2=r2, versions=versions)
        except StopRun:
            raise
        except StorageError as e:
            raise StopRun(e.code) from e
        except R2Error as e:
            if e.code in ("R2_HEAD_AUTH", "R2_ACCESS_BLOCKED"):
                raise StopRun("R2_ACCESS_BLOCKED") from e
            if e.code in ("R2_HEAD_TRANSIENT", "R2_TRANSIENT"):
                raise StopRun("R2_TRANSIENT") from e
            raise StopRun(e.code) from e
        last = r
        st = r.get("status")
        if st == "NO_CHANGE":
            no_change += 1
        elif st == "NEW_VERSION":
            new_v += 1
            stored += 1
        elif st == "PROMOTED_EXISTING_VERSION":
            promoted += 1
            stored += 1
        log(f"stored asset_id={item.get('asset_id')} material_id={item.get('material_id')} status={st}")
    return {
        "attempted": attempted,
        "stored": stored,
        "NO_CHANGE": no_change,
        "NEW_VERSION": new_v,
        "PROMOTED_EXISTING_VERSION": promoted,
        "last": last,
    }


def apply_bulk(store, query, r2, versions, *, batch_size: int = BATCH_SIZE, log=print, max_batches=None) -> dict:
    assert_production_versions(versions)
    totals = {"batches": 0, "attempted": 0, "stored": 0, "NO_CHANGE": 0, "NEW_VERSION": 0, "PROMOTED_EXISTING_VERSION": 0}
    while True:
        plan = collect_eligible(store, query)
        pending = plan["pending"]
        pending_before = len(pending)
        if pending_before == 0:
            return {**totals, "remaining": 0, "status": "FULL_BULK_COMPLETE"}
        if max_batches is not None and totals["batches"] >= max_batches:
            return {**totals, "remaining": pending_before, "status": "BATCH_OK"}
        chunk = pending[: max(1, min(int(batch_size), 50))]
        log(f"batch selected={len(chunk)} remaining_before={pending_before}")
        r = apply_assets(chunk, store=store, query=query, r2=r2, versions=versions, log=log)
        totals["batches"] += 1
        for k in ("attempted", "stored", "NO_CHANGE", "NEW_VERSION", "PROMOTED_EXISTING_VERSION"):
            totals[k] += r[k]
        plan2 = collect_eligible(store, query)
        remaining = plan2["pending_count"]
        if remaining >= pending_before:
            raise StopRun("PENDING_NO_PROGRESS")
        if remaining == 0:
            return {**totals, "remaining": 0, "status": "FULL_BULK_COMPLETE"}
