"""Targeted OPEN-HOLD retry contract — WP-4B-1.

Production 74-item execution is WP-4B-2. This module is dry-run + mocked apply only.
DB OPEN HOLD is the source of truth. Asset IDs are not hardcoded.
"""
from __future__ import annotations

from typing import Callable, Optional

from services.kosha_safety_materials.detail_client import StopRun

from .hold_store import HoldError
from .limits import OVERSIZE_REASON
from .r2_store import ALLOWED_BUCKET, R2Error
from .runner import _store_one, attach_stop_evidence
from .store import StorageError

RETRYABLE_REASONS = frozenset({
    "SOURCE_ASSET_MULTI_MATCH",
    "SOURCE_BINARY_UNAVAILABLE",
})
MULTI_MATCH_REASON = "SOURCE_ASSET_MULTI_MATCH"
BINARY_UNAVAILABLE_REASON = "SOURCE_BINARY_UNAVAILABLE"
FILENAME_MISMATCH_REASON = "SOURCE_ASSET_FILENAME_MISMATCH"

RESOLUTION_NOTE_MULTI = "STORED_AFTER_STABLE_IDENTITY_DEDUPE"
RESOLUTION_NOTE_BINARY = "STORED_AFTER_BINARY_RETRY"
RESOLUTION_NOTE_STALE = "CURRENT_VERSION_ALREADY_PRESENT_VERIFIED"
RESOLUTION_NOTES = {
    MULTI_MATCH_REASON: RESOLUTION_NOTE_MULTI,
    BINARY_UNAVAILABLE_REASON: RESOLUTION_NOTE_BINARY,
}

STORAGE_OK_STATUSES = frozenset({
    "NEW_VERSION",
    "PROMOTED_EXISTING_VERSION",
    "NO_CHANGE",
})

SYSTEM_STOP_CODES = frozenset({
    "R2_ACCESS_BLOCKED",
    "R2_HEAD_AUTH",
    "QUOTA_BLOCKED",
    "ACCESS_BLOCKED",
    "TRANSIENT_UPSTREAM_FAILURE",
    "READBACK_MISMATCH",
    "R2_OBJECT_CONFLICT",
    "VERSION_OBJECT_MISSING",
    "VERSION_READBACK_MISMATCH",
    "CURRENT_NOT_UNIQUE",
    "HOST_NOT_ALLOWED",
    "REDIRECT_HOST_BLOCKED",
    "SCHEME_NOT_ALLOWED",
    "HOLD_RESOLVE_FAILED",
    "VERSION_IDENTITY_MISMATCH",
})

FROZEN_SNAPSHOT_ID = "5fbc70e6-0bce-4bd9-ba29-0e3fca72b572"
FROZEN_BASELINE = {
    "open_holds": 168,
    "multi_match_open": 9,
    "binary_unavailable_open": 65,
    "target_total": 74,
    "excluded_filename": 88,
    "excluded_oversize": 6,
    "excluded_total": 94,
}


def assert_retryable_reason(reason: str) -> str:
    if reason not in RETRYABLE_REASONS:
        raise HoldError("HOLD_REASON_NOT_RETRYABLE", reason)
    return reason


def resolution_note_for(reason: str) -> str:
    assert_retryable_reason(reason)
    return RESOLUTION_NOTES[reason]


def _asset_ids(rows: list[dict]) -> list:
    ids = [r.get("asset_id") for r in rows if r.get("asset_id") is not None]
    return sorted(ids, key=lambda x: (str(type(x).__name__), x))


def current_versions_for_asset(versions, asset_id) -> list[dict]:
    fn = getattr(versions, "current_for_asset", None)
    if callable(fn):
        rows = fn(asset_id) or []
        if isinstance(rows, dict):
            return [rows]
        return list(rows)
    rows_attr = getattr(versions, "rows", None)
    if isinstance(rows_attr, dict):
        out = []
        for r in rows_attr.values():
            if r.get("asset_id") != asset_id:
                continue
            if r.get("is_current_version") is False:
                continue
            out.append(r)
        return out
    if isinstance(rows_attr, list):
        return [
            r for r in rows_attr
            if r.get("asset_id") == asset_id and r.get("is_current_version")
        ]
    return []


def expected_source_asset_key(item: dict) -> str | None:
    key = item.get("source_asset_key")
    if key:
        return key
    return item.get("checksum")


def verify_existing_current_for_recovery(cur: dict, item: dict, r2) -> dict:
    """Idempotent recovery after storage success + hold-resolve failure.

    Does not fetch binary, PUT R2, or write a version. Fail closed on identity
    or integrity mismatch — never resolve because asset_id merely matches.
    """
    expected = expected_source_asset_key(item)
    if (
        cur.get("asset_id") != item.get("asset_id")
        or not expected
        or cur.get("source_asset_key") != expected
    ):
        raise StorageError("VERSION_IDENTITY_MISMATCH")
    if cur.get("is_current_version") is not True:
        raise StorageError("CURRENT_NOT_UNIQUE")
    if cur.get("is_derivative"):
        raise StorageError("DERIVATIVE_FORBIDDEN")
    if cur.get("storage_bucket") != ALLOWED_BUCKET:
        raise StorageError("UNEXPECTED_BUCKET", str(cur.get("storage_bucket")))
    if not cur.get("storage_key"):
        raise StorageError("VERSION_OBJECT_MISSING")
    if not cur.get("content_checksum"):
        raise StorageError("VERSION_READBACK_MISMATCH")
    try:
        r2.readback_verify(cur["storage_key"], cur["content_checksum"])
    except R2Error as e:
        if e.code in SYSTEM_STOP_CODES:
            raise StorageError(e.code, e.message) from e
        raise StorageError("READBACK_MISMATCH", e.code) from e
    return cur


def assert_ready_to_resolve(versions, r2, item: dict, store_out: dict) -> dict:
    """String status is not enough. Current version + R2 integrity must hold."""
    if store_out.get("status") not in STORAGE_OK_STATUSES:
        raise StorageError("STORAGE_STATUS_NOT_RESOLVABLE", str(store_out.get("status")))
    currs = current_versions_for_asset(versions, item.get("asset_id"))
    if len(currs) != 1:
        raise StorageError("CURRENT_NOT_UNIQUE")
    cur = currs[0]
    if cur.get("is_current_version") is False:
        raise StorageError("CURRENT_NOT_UNIQUE")
    if cur.get("is_derivative"):
        raise StorageError("DERIVATIVE_FORBIDDEN")
    if cur.get("storage_bucket") != ALLOWED_BUCKET:
        raise StorageError("UNEXPECTED_BUCKET", str(cur.get("storage_bucket")))
    if not cur.get("storage_key"):
        raise StorageError("VERSION_OBJECT_MISSING")
    if not cur.get("content_checksum"):
        raise StorageError("VERSION_READBACK_MISMATCH")
    r2.readback_verify(cur["storage_key"], cur["content_checksum"])
    return cur


def hold_retry_dry_run(
    *,
    snapshot_id: str,
    holds,
    versioned_asset_ids=None,
    enforce_baseline: bool = False,
) -> dict:
    """SELECT-only. binary GET = 0, R2 = 0, DB write = 0."""
    if holds is None or not snapshot_id:
        raise HoldError("HOLD_STORE_REQUIRED")
    all_open = holds.open_rows(snapshot_id)
    multi = holds.open_rows(snapshot_id, MULTI_MATCH_REASON)
    binary = holds.open_rows(snapshot_id, BINARY_UNAVAILABLE_REASON)
    filename = holds.open_rows(snapshot_id, FILENAME_MISMATCH_REASON)
    oversize = holds.open_rows(snapshot_id, OVERSIZE_REASON)
    versioned = set(versioned_asset_ids or [])
    targets = multi + binary
    already = [r for r in targets if r.get("asset_id") in versioned]
    plan = {
        "status": "HOLD_RETRY_DRY_RUN",
        "snapshot_id": snapshot_id,
        "open_holds": len(all_open),
        "multi_match_open": len(multi),
        "binary_unavailable_open": len(binary),
        "target_total": len(multi) + len(binary),
        "multi_match_target_ids": _asset_ids(multi),
        "binary_retry_target_ids": _asset_ids(binary),
        "excluded_filename": len(filename),
        "excluded_oversize": len(oversize),
        "excluded_total": len(filename) + len(oversize),
        "already_versioned": len(already),
        "kosha_binary_get": 0,
        "r2_put": 0,
        "r2_get": 0,
        "version_dml": 0,
        "hold_dml": 0,
    }
    if enforce_baseline:
        assert_hold_retry_baseline(plan)
    return plan


def assert_hold_retry_baseline(plan: dict) -> None:
    if plan.get("snapshot_id") != FROZEN_SNAPSHOT_ID:
        raise HoldError("HOLD_TARGET_DRIFT", "snapshot_id")
    for key, expected in FROZEN_BASELINE.items():
        if plan.get(key) != expected:
            raise HoldError("HOLD_TARGET_DRIFT", key)
    if plan["target_total"] + plan["excluded_total"] != plan["open_holds"]:
        raise HoldError("HOLD_TARGET_DRIFT", "sum")


def _stop(code: str, item: dict, err=None) -> None:
    sr = StopRun(code)
    attach_stop_evidence(sr, item, err)
    raise sr from err


def catalog_items_for_asset_ids(store, query, asset_ids) -> tuple[dict, set, str]:
    """Load eligible catalog rows for OPEN HOLD retry. Does not hardcode IDs."""
    from ..enrichment import snapshot_precondition
    from .eligibility import is_eligible_asset

    pre = snapshot_precondition(store)
    snapshot_id = pre["snapshot"]["id"]
    member_ids = [m["material_id"] for m in pre["membership"]]
    membership = set(member_ids)
    details = query.details_for(member_ids)
    want = set()
    for x in asset_ids:
        if x is None:
            continue
        want.add(x)
        try:
            want.add(int(x))
        except (TypeError, ValueError):
            pass
    items: dict = {}
    for a in query.assets_for(member_ids):
        aid = a.get("id")
        if aid not in want:
            try:
                if int(aid) not in want:
                    continue
            except (TypeError, ValueError):
                continue
        d = details.get(a.get("material_id") or "")
        if not d or not is_eligible_asset(a, d, membership):
            continue
        row = {
            "asset_id": aid,
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
        items[aid] = row
        try:
            items[int(aid)] = row
        except (TypeError, ValueError):
            pass
    return items, membership, snapshot_id


def apply_targeted_hold_retry(
    *,
    snapshot_id: str,
    holds,
    items_by_asset_id: dict,
    membership_ids: set,
    r2,
    versions,
    reasons=None,
    store_one_fn: Optional[Callable] = None,
    fetch_detail_fn=None,
    fetch_atch_fn=None,
    fetch_file_list_fn=None,
    fetch_binary_fn=None,
) -> dict:
    """Retry OPEN HOLDs for the two allowlisted reasons only.

    Resolve happens only after storage + exactly-one current version + R2 verify.
    Asset-local failures keep OPEN and continue. System STOP codes abort the run.
    """
    if holds is None or not snapshot_id:
        raise HoldError("HOLD_STORE_REQUIRED")
    selected = list(RETRYABLE_REASONS if reasons is None else reasons)
    try:
        for reason in selected:
            assert_retryable_reason(reason)
    except HoldError as e:
        if e.code == "HOLD_REASON_NOT_RETRYABLE":
            raise StopRun("HOLD_REASON_NOT_RETRYABLE") from e
        raise
    store_one = store_one_fn or _store_one
    attempted = resolved = open_kept = stale = 0
    results = []
    ordered = [r for r in (MULTI_MATCH_REASON, BINARY_UNAVAILABLE_REASON) if r in selected]
    for reason in ordered:
        for hold in holds.open_rows(snapshot_id, reason):
            attempted += 1
            asset_id = hold.get("asset_id")
            item = items_by_asset_id.get(asset_id)
            if item is None:
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": "TARGET_ITEM_MISSING",
                    "asset_id": asset_id,
                    "hold_reason": reason,
                    "binary_get": 0,
                })
                continue
            still_open = {
                r["asset_id"]
                for r in holds.open_rows(snapshot_id, reason)
                if r.get("asset_id") == asset_id
            }
            if asset_id not in still_open:
                open_kept += 1
                results.append({
                    "status": "HOLD_NOT_FOUND",
                    "asset_id": asset_id,
                    "hold_reason": reason,
                    "binary_get": 0,
                })
                continue
            preexisting = current_versions_for_asset(versions, asset_id)
            if preexisting:
                if len(preexisting) != 1:
                    _stop("CURRENT_NOT_UNIQUE", item)
                try:
                    verify_existing_current_for_recovery(preexisting[0], item, r2)
                except StorageError as e:
                    _stop(e.code, item, e)
                except R2Error as e:
                    code = e.code if e.code in SYSTEM_STOP_CODES else "READBACK_MISMATCH"
                    _stop(code, item, e)
                try:
                    resolved_out = holds.resolve_open(
                        snapshot_id=snapshot_id,
                        asset_id=asset_id,
                        reason=reason,
                        resolution_note=RESOLUTION_NOTE_STALE,
                    )
                except HoldError as e:
                    _stop("HOLD_RESOLVE_FAILED", item, e)
                except Exception as e:
                    _stop("HOLD_RESOLVE_FAILED", item, e)
                if resolved_out.get("status") not in ("RESOLVED", "ALREADY_RESOLVED"):
                    _stop("HOLD_RESOLVE_FAILED", item)
                resolved += 1
                stale += 1
                results.append({
                    "status": resolved_out["status"],
                    "asset_id": asset_id,
                    "hold_reason": reason,
                    "resolution_note": RESOLUTION_NOTE_STALE,
                    "recovery": RESOLUTION_NOTE_STALE,
                    "binary_get": 0,
                    "r2_put": 0,
                    "version_dml": 0,
                })
                continue
            kwargs = dict(
                membership_ids=membership_ids,
                r2=r2,
                versions=versions,
                snapshot_id=snapshot_id,
                holds=holds,
            )
            if fetch_detail_fn is not None:
                kwargs["fetch_detail_fn"] = fetch_detail_fn
            if fetch_atch_fn is not None:
                kwargs["fetch_atch_fn"] = fetch_atch_fn
            if fetch_file_list_fn is not None:
                kwargs["fetch_file_list_fn"] = fetch_file_list_fn
            if fetch_binary_fn is not None:
                kwargs["fetch_binary_fn"] = fetch_binary_fn
            try:
                out = store_one(item, **kwargs)
            except StopRun:
                raise
            except HoldError as e:
                if e.code in SYSTEM_STOP_CODES:
                    _stop(e.code, item, e)
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": e.code,
                    "asset_id": asset_id,
                    "hold_reason": reason,
                })
                continue
            except StorageError as e:
                if e.code in SYSTEM_STOP_CODES:
                    _stop(e.code, item, e)
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": e.code,
                    "asset_id": asset_id,
                    "hold_reason": reason,
                    "binary_get": 0,
                })
                continue
            except R2Error as e:
                code = "R2_ACCESS_BLOCKED" if e.code in ("R2_HEAD_AUTH", "R2_ACCESS_BLOCKED") else e.code
                if code in SYSTEM_STOP_CODES:
                    _stop(code, item, e)
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": e.code,
                    "asset_id": asset_id,
                    "hold_reason": reason,
                })
                continue
            if out.get("status") == "HOLD":
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": out.get("reason"),
                    "asset_id": asset_id,
                    "hold_reason": reason,
                    "binary_get": out.get("binary_get") or 0,
                    "hold_inserted": out.get("hold_inserted"),
                })
                continue
            try:
                assert_ready_to_resolve(versions, r2, item, out)
            except StorageError as e:
                if e.code in SYSTEM_STOP_CODES:
                    _stop(e.code, item, e)
                open_kept += 1
                results.append({
                    "status": "HOLD_OPEN",
                    "reason": e.code,
                    "asset_id": asset_id,
                    "hold_reason": reason,
                })
                continue
            except R2Error as e:
                code = e.code if e.code in SYSTEM_STOP_CODES else "READBACK_MISMATCH"
                _stop(code, item, e)
            try:
                resolved_out = holds.resolve_open(
                    snapshot_id=snapshot_id,
                    asset_id=asset_id,
                    reason=reason,
                    resolution_note=resolution_note_for(reason),
                )
            except HoldError as e:
                _stop("HOLD_RESOLVE_FAILED", item, e)
            except Exception as e:
                _stop("HOLD_RESOLVE_FAILED", item, e)
            if resolved_out.get("status") not in ("RESOLVED", "ALREADY_RESOLVED"):
                _stop("HOLD_RESOLVE_FAILED", item)
            resolved += 1
            results.append({
                "status": resolved_out["status"],
                "asset_id": asset_id,
                "hold_reason": reason,
                "resolution_note": resolved_out.get("row", {}).get("resolution_note"),
                "store_status": out.get("status"),
            })
    return {
        "status": "HOLD_RETRY_OK",
        "snapshot_id": snapshot_id,
        "attempted": attempted,
        "resolved": resolved,
        "open_kept": open_kept,
        "stale": stale,
        "results": results,
    }
