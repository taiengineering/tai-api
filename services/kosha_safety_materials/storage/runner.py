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
from .binary_fetch import (
    BinaryFetchError,
    confirm_empty_binary_get,
    fetch_attachment_binary,
    fetch_file_list,
)
from .eligibility import (
    EligibilityError,
    is_eligible_asset,
    is_eligible_detail,
    live_kogl_ok,
    pending_without_version,
    require_asset_id,
    sort_pending_key,
)
from .hold_store import HOLD_REASONS, HoldError, UNAVAILABLE_REASON, assert_production_holds, oversize_report
from .limits import MAX_BINARY_BYTES, OVERSIZE_REASON, is_metadata_oversize, oversize_observed, parsed_file_size
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

STOP_EVIDENCE_KEYS = (
    "asset_id",
    "material_id",
    "file_name",
    "file_size",
    "source_med_seq",
    "stop_reason",
    "stop_subreason",
    "http_status",
    "body_bytes_read",
    "declared_content_length",
)


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


def stop_evidence_from_item(item: dict, *, reason: str, err=None, http_status=None) -> dict:
    """Item + error fields for STOP JSON. Does not change HOLD/STOP policy."""
    sub = None
    body = None
    declared = None
    st = http_status
    if err is not None:
        sub = getattr(err, "subreason", None)
        if not sub:
            code = getattr(err, "code", None)
            if code and code != reason:
                sub = code
            elif str(err) and str(err) != reason:
                sub = str(err)
        if st is None:
            st = getattr(err, "http_status", None)
        if st is None:
            st = getattr(err, "status", None)
        body = getattr(err, "body_bytes_read", None)
        declared = getattr(err, "declared_content_length", None)
    return {
        "asset_id": item.get("asset_id"),
        "material_id": item.get("material_id"),
        "file_name": item.get("file_name"),
        "file_size": item.get("file_size"),
        "source_med_seq": item.get("source_med_seq"),
        "stop_reason": reason,
        "stop_subreason": sub,
        "http_status": st,
        "body_bytes_read": body,
        "declared_content_length": declared,
    }


def attach_stop_evidence(stop: StopRun, item: dict, err=None) -> StopRun:
    incoming = stop_evidence_from_item(
        item, reason=stop.reason, err=err, http_status=stop.http_status,
    )
    for k, v in incoming.items():
        if stop.evidence.get(k) is None:
            stop.evidence[k] = v
    if stop.http_status is None:
        stop.http_status = incoming.get("http_status")
    return stop


def stop_run_payload(stop: StopRun) -> dict:
    ev = stop.evidence or {}
    out = {k: ev.get(k) for k in STOP_EVIDENCE_KEYS}
    out["status"] = stop.reason
    if out.get("stop_reason") is None:
        out["stop_reason"] = stop.reason
    if out.get("http_status") is None:
        out["http_status"] = stop.http_status
    return out


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


def _sweep_status(held: int) -> str:
    return "FULL_BULK_COMPLETE" if int(held or 0) == 0 else "STORAGE_SWEEP_COMPLETE_WITH_HOLDS"


def collect_eligible(store, query: StorageQuery, *, holds=None) -> dict:
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
    held_ids: set = set()
    if holds is not None:
        held_ids = set(holds.open_asset_ids(snap["id"]))
    try:
        pending = pending_without_version(eligible, versioned_ids, held_ids)
    except EligibilityError as e:
        raise StopRun(e.code) from e
    already_versioned = sum(1 for e in eligible if e.get("asset_id") in versioned_ids)
    held = sum(1 for e in eligible if e.get("asset_id") in held_ids and e.get("asset_id") not in versioned_ids)
    return {
        "snapshot_id": snap["id"],
        "snapshot_hash": snap.get("snapshot_hash"),
        "membership": len(members),
        "eligible_materials": len({e["material_id"] for e in eligible}),
        "eligible_assets": len(eligible),
        "already_versioned": already_versioned,
        "held": held,
        "actionable_pending": len(pending),
        "pending": pending,
        "pending_count": len(pending),
        "Type1": type1,
        "Type3": type3,
        "VIDEO_excluded": video_excluded,
        "fixed": True,
        "eligible_gt_20mib": sum(1 for e in eligible if (parsed_file_size(e.get("file_size")) or 0) > 20 * 1024 * 1024),
        "eligible_gt_64mib": sum(1 for e in eligible if is_metadata_oversize(e.get("file_size"))),
        "max_eligible_file_size": max((parsed_file_size(e.get("file_size")) or 0) for e in eligible) if eligible else 0,
        "max_binary_bytes": MAX_BINARY_BYTES,
    }


def lookup_eligible_item(store, query: StorageQuery, asset_id: int, *, holds=None) -> dict | None:
    """Find an eligible asset even if it already has a current version or OPEN hold."""
    plan = collect_eligible(store, query, holds=None)
    pending = plan.get("pending") or []
    for item in pending:
        if int(item.get("asset_id") or 0) == int(asset_id):
            return item
    pre = snapshot_precondition(store)
    members = pre["membership"]
    member_ids = [m["material_id"] for m in members]
    membership = set(member_ids)
    details = query.details_for(member_ids)
    for a in query.assets_for(member_ids):
        if int(a.get("id") or 0) != int(asset_id):
            continue
        d = details.get(a.get("material_id") or "")
        if not d or not is_eligible_asset(a, d, membership):
            return None
        return {
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
    return None


def dry_run_plan(store, query: StorageQuery, *, holds=None) -> dict:
    plan = collect_eligible(store, query, holds=holds)
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
        "hold_dml": 0,
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


def _hold_asset(holds, *, snapshot_id, item, material_id, source_med_seq, reason, observed_files) -> dict:
    if holds is None:
        raise StorageError("HOLD_STORE_REQUIRED")
    assert_production_holds(holds)
    if not snapshot_id:
        raise StorageError("HOLD_STORE_REQUIRED", "snapshot_id")
    recorded = holds.record_open(
        snapshot_id=snapshot_id,
        asset_id=item.get("asset_id"),
        material_id=material_id,
        source_med_seq=source_med_seq,
        reason=reason,
        expected_file_name=item.get("file_name"),
        observed_files=observed_files,
    )
    return {
        "status": "HOLD",
        "reason": reason,
        "asset_id": item.get("asset_id"),
        "hold_inserted": recorded.get("inserted"),
        "r2_put": 0,
        "version_dml": 0,
        "binary_get": 0,
    }


def _store_one(
    item: dict,
    *,
    membership_ids: set[str],
    r2: R2Store,
    versions,
    snapshot_id: str | None = None,
    holds=None,
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
    if is_metadata_oversize(item.get("file_size")):
        return _hold_asset(
            holds, snapshot_id=snapshot_id, item=item, material_id=mid,
            source_med_seq=medseq, reason=OVERSIZE_REASON,
            observed_files=oversize_observed(
                file_size=item.get("file_size"), file_name=item.get("file_name"),
            ),
        )
    try:
        raw = fetch_detail_fn(medseq)
    except StopRun:
        raise
    except Exception as e:
        map_fetch_stop(e)
        raise StorageError("BINARY_INTEGRITY_BLOCKED", type(e).__name__) from e
    parsed = parser.parse_detail(raw.get("json"), medseq, raw.get("status"))
    if parsed["status"] != "OK":
        raise StorageError(
            "BINARY_INTEGRITY_BLOCKED",
            parsed.get("failure_reason") or parsed["status"],
            subreason=parsed.get("failure_reason") or parsed["status"],
        )
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
        if e.code in HOLD_REASONS:
            return _hold_asset(
                holds, snapshot_id=snapshot_id, item=item, material_id=mid,
                source_med_seq=medseq, reason=e.code, observed_files=e.observed_files,
            )
        raise StorageError("SOURCE_ASSET_RESOLUTION_BLOCKED") from e
    except Exception as e:
        map_fetch_stop(e)
        raise StorageError("SOURCE_ASSET_RESOLUTION_BLOCKED") from e

    expect_pdf = (item.get("asset_type") or "").upper() == "PDF"

    def fetch_fn(**kwargs):
        def _one_get():
            return fetch_binary_fn(
                kogl_type=live_kogl,
                content_type=item.get("content_type") or item.get("asset_type"),
                atcfl_no=dl["atcfl_no"],
                atcfl_seq=dl["atcfl_seq"],
                file_name=dl.get("file_name"),
                mime_type=dl.get("mime_type") or item.get("mime_type"),
                expect_pdf=expect_pdf,
            )

        try:
            return confirm_empty_binary_get(_one_get)
        except BinaryFetchError as e:
            if e.code in (OVERSIZE_REASON, UNAVAILABLE_REASON):
                raise
            map_fetch_stop(e)
            if e.code == "TRANSIENT_UPSTREAM_FAILURE":
                raise StopRun("TRANSIENT_UPSTREAM_FAILURE") from e
            raise StorageError(
                "BINARY_INTEGRITY_BLOCKED", e.code,
                subreason=e.code,
                http_status=e.status,
                body_bytes_read=e.body_bytes_read,
                declared_content_length=getattr(e, "declared_content_length", None),
            ) from e

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
    try:
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
    except BinaryFetchError as e:
        if e.code == OVERSIZE_REASON:
            return _hold_asset(
                holds, snapshot_id=snapshot_id, item=item, material_id=mid,
                source_med_seq=medseq, reason=OVERSIZE_REASON,
                observed_files=oversize_observed(
                    file_size=item.get("file_size"),
                    file_name=item.get("file_name") or dl.get("file_name"),
                    extra={"body_bytes_read": e.body_bytes_read, "http_status": e.status},
                ),
            )
        if e.code == UNAVAILABLE_REASON:
            held = _hold_asset(
                holds, snapshot_id=snapshot_id, item=item, material_id=mid,
                source_med_seq=medseq, reason=UNAVAILABLE_REASON,
                observed_files=[{
                    "file_name": item.get("file_name") or dl.get("file_name"),
                    "expected_file_size": item.get("file_size"),
                    "http_status": 200,
                    "body_bytes_read": 0,
                    "confirmation_count": 2,
                    "observed_at": _utc(),
                }],
            )
            held["binary_get"] = 2
            return held
        raise
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
    holds=None,
    log=print,
) -> dict:
    if CONCURRENCY != 1:
        raise RuntimeError("concurrency must be 1")
    assert_production_versions(versions)
    pre = snapshot_precondition(store)
    membership_ids = {m["material_id"] for m in pre["membership"]}
    snapshot_id = pre["snapshot"]["id"]
    attempted = stored = no_change = new_v = promoted = held = 0
    last = None
    for item in items:
        attempted += 1
        try:
            r = _store_one(
                item, membership_ids=membership_ids, r2=r2, versions=versions,
                snapshot_id=snapshot_id, holds=holds,
            )
        except StopRun as e:
            attach_stop_evidence(e, item, e.__cause__)
            raise
        except HoldError as e:
            sr = StopRun(e.code)
            attach_stop_evidence(sr, item, e)
            raise sr from e
        except StorageError as e:
            sr = StopRun(e.code, http_status=e.http_status)
            attach_stop_evidence(sr, item, e)
            raise sr from e
        except R2Error as e:
            if e.code in ("R2_HEAD_AUTH", "R2_ACCESS_BLOCKED"):
                reason = "R2_ACCESS_BLOCKED"
            elif e.code in ("R2_HEAD_TRANSIENT", "R2_TRANSIENT"):
                reason = "R2_TRANSIENT"
            else:
                reason = e.code
            sr = StopRun(reason)
            attach_stop_evidence(sr, item, e)
            raise sr from e
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
        elif st == "HOLD":
            held += 1
            log(f"held asset_id={item.get('asset_id')} material_id={item.get('material_id')} reason={r.get('reason')}")
            continue
        log(f"stored asset_id={item.get('asset_id')} material_id={item.get('material_id')} status={st}")
    return {
        "attempted": attempted,
        "stored": stored,
        "NO_CHANGE": no_change,
        "NEW_VERSION": new_v,
        "PROMOTED_EXISTING_VERSION": promoted,
        "HOLD": held,
        "last": last,
    }


def apply_bulk(store, query, r2, versions, *, holds=None, batch_size: int = BATCH_SIZE, log=print, max_batches=None) -> dict:
    assert_production_versions(versions)
    try:
        assert_production_holds(holds)
    except HoldError as e:
        raise StopRun(e.code) from e
    totals = {
        "batches": 0, "attempted": 0, "stored": 0, "NO_CHANGE": 0,
        "NEW_VERSION": 0, "PROMOTED_EXISTING_VERSION": 0, "HOLD": 0,
    }
    while True:
        plan = collect_eligible(store, query, holds=holds)
        pending = plan["pending"]
        pending_before = len(pending)
        held_n = int(plan.get("held") or 0)
        if pending_before == 0:
            return {
                **totals, "remaining": 0, "held": held_n,
                "status": _sweep_status(held_n),
                **oversize_report(holds, plan.get("snapshot_id")),
            }
        if max_batches is not None and totals["batches"] >= max_batches:
            return {
                **totals, "remaining": pending_before, "held": held_n, "status": "BATCH_OK",
                **oversize_report(holds, plan.get("snapshot_id")),
            }
        chunk = pending[: max(1, min(int(batch_size), 50))]
        log(f"batch selected={len(chunk)} remaining_before={pending_before} held={held_n}")
        r = apply_assets(chunk, store=store, query=query, r2=r2, versions=versions, holds=holds, log=log)
        totals["batches"] += 1
        for k in ("attempted", "stored", "NO_CHANGE", "NEW_VERSION", "PROMOTED_EXISTING_VERSION", "HOLD"):
            totals[k] += r.get(k, 0)
        plan2 = collect_eligible(store, query, holds=holds)
        remaining = plan2["pending_count"]
        held_n = int(plan2.get("held") or 0)
        if remaining >= pending_before:
            raise StopRun("PENDING_NO_PROGRESS")
        if remaining == 0:
            return {
                **totals, "remaining": 0, "held": held_n,
                "status": _sweep_status(held_n),
                **oversize_report(holds, plan2.get("snapshot_id")),
            }
