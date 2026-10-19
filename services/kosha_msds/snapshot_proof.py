"""MSDS snapshot membership proof — WO-WWW-PERF-004-P0S PATCH-003A/B.

A read-only membership proof system that verifies OS/DB parity at the
document-identity level (chem_id, canonical_id pairs) rather than just
comparing counts.

PATCH-003A: SnapshotProof dataclass, scan helpers, generate_proof_dry_run,
            verify_proof, compute_membership_sha256.

PATCH-003B: In-memory thread-safe proof registry (register_proof,
            get_registered_proof, clear_proof_registry).

No production DB writes or OS index changes in this WO.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from services.kosha_msds.contract import (
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
)
from services.kosha_msds.read import SEO_PREVIEW_CURRENT_VIEW
from services.shared_search.opensearch_client import CURRENT_ALIAS, RUNS_INDEX

logger = logging.getLogger(__name__)

_FULL_CURRENT_VIEW = "kosha_msds_current"
_DB_PAGE_SIZE = 1000
_OS_PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class SnapshotProofError(Exception):
    """Base for snapshot proof errors."""


class SnapshotProofScanError(SnapshotProofError):
    """DB or OS scan failed."""


class SnapshotProofMembershipMismatch(SnapshotProofError):
    """Membership SHA256 or count mismatch between DB and OS."""


class SnapshotProofStateChanged(SnapshotProofError):
    """System state changed during scan (outbox watermark or snapshot_id moved)."""


# ---------------------------------------------------------------------------
# Proof dataclass
# ---------------------------------------------------------------------------


@dataclass
class SnapshotProof:
    proof_version: str               # "1.0"
    publication_scope: str           # PUBLICATION_SCOPE_SEO_PREVIEW or PUBLICATION_SCOPE_FULL
    snapshot_id: str                 # UUIDv4
    snapshot_completed_at: str       # ISO8601
    opensearch_alias: str            # "tai-shared-search-current"
    physical_index: str              # "tai-shared-search-v1-..."
    rebuild_run_id: str              # from tai-shared-search-runs index
    db_membership_count: int
    os_membership_count: int
    db_membership_sha256: str
    os_membership_sha256: str
    chem_outbox_high_watermark: int  # max completed event_id from search_index_outbox
    verified_at: str                 # ISO8601
    verification_status: str         # "PASS" or "FAIL"
    missing_count: int = 0
    extra_count: int = 0
    duplicate_db_count: int = 0      # chem_id rows that collapsed under dedup (data anomaly)
    os_duplicate_count: int = 0      # OS hits with duplicate source_key (index anomaly)
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Membership SHA256 (deterministic contract)
# ---------------------------------------------------------------------------


def compute_membership_sha256(pairs: list[tuple[str, str]]) -> str:
    """Public helper for tests.

    Sorts pairs by (chem_id, canonical_id) — both as strings — then
    computes SHA256 over lines of "chem_id,canonical_id\\n" (UTF-8).
    Bit-for-bit deterministic regardless of input order.
    """
    sorted_pairs = sorted(pairs, key=lambda p: (str(p[0]), str(p[1])))
    lines = "".join(f"{cid},{cid2}\n" for cid, cid2 in sorted_pairs)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Read-only OS scan
# ---------------------------------------------------------------------------


def _scan_os_chem_ids(client, *, index: str = "") -> tuple[dict[str, str], int]:
    """Returns ({source_key (chem_id): canonical_id}, raw_valid_hit_count) for all CHEM PUBLIC docs.

    Uses search_after pagination — no 10k cap.
    Filter: object_type=CHEM, publication_status=PUBLISHED, visibility_scopes=PUBLIC.
    index: physical index to scan; defaults to CURRENT_ALIAS when empty (proof gen
           should always pass physical_index to pin the scan to one generation).
    raw_valid_hit_count tracks valid hits; if > len(result) there are duplicate
    source_key values in the index (OS anomaly).
    Raises SnapshotProofScanError on any scan failure (fail-closed).
    """
    scan_index = index if index else CURRENT_ALIAS
    result: dict[str, str] = {}
    raw_valid_count = 0
    search_after = None
    try:
        while True:
            body: dict = {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"object_type": "CHEM"}},
                            {"term": {"publication_status": "PUBLISHED"}},
                            {"term": {"visibility_scopes": "PUBLIC"}},
                        ]
                    }
                },
                "_source": ["source_key", "canonical_id"],
                "size": _OS_PAGE_SIZE,
                "sort": [{"canonical_id": "asc"}],
            }
            if search_after:
                body["search_after"] = search_after
            resp = client.search(index=scan_index, body=body)
            hits = (resp.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for hit in hits:
                src = hit.get("_source") or {}
                source_key = src.get("source_key") or ""
                canonical_id = src.get("canonical_id") or ""
                if source_key and canonical_id:
                    raw_valid_count += 1
                    result[source_key] = canonical_id
            search_after = hits[-1].get("sort")
            if len(hits) < _OS_PAGE_SIZE:
                break
    except Exception as exc:
        raise SnapshotProofScanError(
            f"snapshot_proof: OS scan failed: {exc}"
        ) from exc
    return result, raw_valid_count


# ---------------------------------------------------------------------------
# Read-only DB scan
# ---------------------------------------------------------------------------


def _scan_db_chem_ids(sb, scope: str) -> tuple[dict[str, str], int]:
    """Returns ({chem_id: canonical_id}, raw_row_count) from the published scope view.

    SEO_PREVIEW -> kosha_msds_seo_preview_current
    FULL        -> kosha_msds_current
    Paginates with page_size=1000 on chem_id order.
    raw_row_count tracks total rows returned; if > len(result) there are
    duplicate chem_id rows in the view (data anomaly).
    Raises SnapshotProofScanError on any scan failure (fail-closed).
    """
    view = (
        SEO_PREVIEW_CURRENT_VIEW
        if scope == PUBLICATION_SCOPE_SEO_PREVIEW
        else _FULL_CURRENT_VIEW
    )
    result: dict[str, str] = {}
    raw_row_count = 0
    try:
        last_chem_id: Optional[str] = None
        while True:
            q = sb.table(view).select("chem_id,id").order("chem_id").limit(_DB_PAGE_SIZE)
            if last_chem_id is not None:
                q = q.gt("chem_id", last_chem_id)
            r = q.execute()
            rows = r.data or []
            if not rows:
                break
            raw_row_count += len(rows)
            for row in rows:
                chem_id = str(row.get("chem_id") or "")
                canonical_id = str(row.get("id") or "")
                if chem_id and canonical_id:
                    result[chem_id] = canonical_id
            if len(rows) < _DB_PAGE_SIZE:
                break
            last_chem_id = str(rows[-1].get("chem_id") or "")
    except Exception as exc:
        raise SnapshotProofScanError(
            f"snapshot_proof: DB scan failed (scope={scope}): {exc}"
        ) from exc
    return result, raw_row_count


# ---------------------------------------------------------------------------
# Physical index resolution
# ---------------------------------------------------------------------------


def _get_physical_index(client) -> str:
    """Resolve CURRENT_ALIAS to the current physical index name.

    Returns '' on failure.
    """
    try:
        alias_info = client.indices.get_alias(name=CURRENT_ALIAS)
        # alias_info is {physical_index_name: {...}}
        if alias_info:
            return next(iter(alias_info))
    except Exception as exc:
        logger.warning("snapshot_proof: physical index resolution failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Rebuild run_id resolution
# ---------------------------------------------------------------------------


def _get_rebuild_run_id(client, physical_index: str) -> str:
    """Query RUNS_INDEX for the rebuild run that produced physical_index.

    Looks for a PROMOTED run whose candidate_index matches the current
    physical index (candidate_index is set by begin_run; after promote it
    becomes the live index). Returns '' if not found or on error.
    """
    if not physical_index:
        return ""
    try:
        body = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"status": "PROMOTED"}},
                        {"term": {"candidate_index": physical_index}},
                    ]
                }
            },
            "size": 1,
            "sort": [{"_score": "desc"}],
        }
        resp = client.search(index=RUNS_INDEX, body=body)
        hits = (resp.get("hits") or {}).get("hits") or []
        if hits:
            src = hits[0].get("_source") or {}
            run_id = src.get("run_id") or hits[0].get("_id") or ""
            return str(run_id)
    except Exception as exc:
        logger.warning("snapshot_proof: rebuild run_id lookup failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Outbox watermark
# ---------------------------------------------------------------------------


def _get_outbox_watermark(sb) -> int:
    """Get MAX id from search_index_outbox where domain_name='CHEM' and status='COMPLETED'.

    Raises SnapshotProofScanError on query failure (fail-closed).
    Returns 0 when no COMPLETED CHEM events exist yet (valid empty state).
    """
    try:
        r = (
            sb.table("search_index_outbox")
            .select("id")
            .eq("status", "COMPLETED")
            .eq("domain_name", "CHEM")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if rows:
            return int(rows[0].get("id") or 0)
        return 0
    except Exception as exc:
        raise SnapshotProofScanError(
            f"snapshot_proof: outbox watermark lookup failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Outbox pending guard
# ---------------------------------------------------------------------------


def _get_outbox_pending_count(sb) -> int:
    """Count PENDING+CLAIMED CHEM events in search_index_outbox.

    A non-zero count means there are uncommitted changes not yet applied to
    OS — the proof state is potentially dirty.
    Returns 0 when no uncommitted events exist.
    Raises SnapshotProofScanError on query failure (fail-closed).
    """
    try:
        r = (
            sb.table("search_index_outbox")
            .select("id", count="exact")
            .eq("domain_name", "CHEM")
            .in_("status", ["PENDING", "CLAIMED"])
            .limit(0)
            .execute()
        )
        return int(getattr(r, "count", None) or 0)
    except Exception as exc:
        raise SnapshotProofScanError(
            f"snapshot_proof: outbox pending count failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Snapshot lookup
# ---------------------------------------------------------------------------


def _get_current_snapshot(sb, scope: str) -> tuple[str, str]:
    """Returns (snapshot_id, completed_at_iso) for the given scope.

    Queries the scope's view for snapshot_id, then kosha_msds_snapshots
    for completed_at. Returns ('', '') on failure.
    """
    view = (
        SEO_PREVIEW_CURRENT_VIEW
        if scope == PUBLICATION_SCOPE_SEO_PREVIEW
        else _FULL_CURRENT_VIEW
    )
    try:
        r = (
            sb.table(view)
            .select("snapshot_id")
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return ("", "")
        snapshot_id = str(rows[0].get("snapshot_id") or "")
        if not snapshot_id:
            return ("", "")

        # Look up completed_at from kosha_msds_snapshots
        sr = (
            sb.table("kosha_msds_snapshots")
            .select("completed_at")
            .eq("id", snapshot_id)
            .limit(1)
            .execute()
        )
        s_rows = sr.data or []
        if s_rows:
            completed_at = str(s_rows[0].get("completed_at") or "")
            return (snapshot_id, completed_at)
        return (snapshot_id, "")
    except Exception as exc:
        logger.warning("snapshot_proof: snapshot lookup failed (scope=%s): %s", scope, exc)
    return ("", "")


# ---------------------------------------------------------------------------
# Main functions
# ---------------------------------------------------------------------------


def generate_proof_dry_run(*, scope: str, sb=None, client=None) -> SnapshotProof:
    """Generate a proof without writing anywhere.

    Scans DB and OS (sequential), computes SHA256, validates membership.
    Verifies state consistency by checking outbox watermark and snapshot_id
    before AND after the scan. If state changed mid-scan, sets
    verification_status=FAIL.

    Raises SnapshotProofScanError only for fatal pre-condition failures;
    scan sub-failures return FAIL proof with error_message set.
    """
    if sb is None:
        from db.supabase_client import get_supabase
        sb = get_supabase()
    if client is None:
        from services.shared_search.opensearch_client import get_client
        client = get_client()

    verified_at = datetime.now(timezone.utc).isoformat()

    # --- Pre-scan state ---
    snapshot_id_pre, snapshot_completed_at = _get_current_snapshot(sb, scope)
    outbox_wm_pre = _get_outbox_watermark(sb)  # raises SnapshotProofScanError on failure
    pending_count = _get_outbox_pending_count(sb)  # raises SnapshotProofScanError on failure
    physical_index = _get_physical_index(client)
    rebuild_run_id = _get_rebuild_run_id(client, physical_index)

    # --- Scans (fail → FAIL proof, not exception) ---
    scan_error: Optional[str] = None
    db_map: dict[str, str] = {}
    db_raw_count: int = 0
    os_map: dict[str, str] = {}
    os_raw_count: int = 0

    try:
        db_map, db_raw_count = _scan_db_chem_ids(sb, scope)
    except SnapshotProofScanError as exc:
        scan_error = str(exc)

    if scan_error is None:
        try:
            # Pin scan to physical_index at proof-generation time (P0-01 index generation parity)
            os_map, os_raw_count = _scan_os_chem_ids(client, index=physical_index)
        except SnapshotProofScanError as exc:
            scan_error = str(exc)

    # --- Post-scan state check (skip if scans failed) ---
    # CLOSURE-01/J03: also re-check physical_index to detect alias swap during scan.
    # FIX-02/K04: re-check pending_count post-scan — new PENDING events during scan
    # mean the proof is potentially dirty even if pre-scan state was clean.
    postscan_error: Optional[str] = None
    state_changed = False
    postscan_pending: int = 0
    snapshot_id_post: str = snapshot_id_pre
    outbox_wm_post: int = outbox_wm_pre
    physical_index_post: str = physical_index
    if scan_error is None:
        try:
            snapshot_id_post, _ = _get_current_snapshot(sb, scope)
            outbox_wm_post = _get_outbox_watermark(sb)
            physical_index_post = _get_physical_index(client)
            postscan_pending = _get_outbox_pending_count(sb)
        except SnapshotProofScanError as exc:
            postscan_error = f"Post-scan state check failed: {exc}"
        state_changed = (
            snapshot_id_pre != snapshot_id_post
            or outbox_wm_pre != outbox_wm_post
            or physical_index != physical_index_post
        )

    # --- Duplicate detection ---
    duplicate_db_count = db_raw_count - len(db_map)  # >0 → same chem_id appeared multiple times
    os_duplicate_count = os_raw_count - len(os_map)   # >0 → same source_key in OS index

    # --- Compute SHA256 ---
    db_pairs: list[tuple[str, str]] = list(db_map.items())
    os_pairs: list[tuple[str, str]] = list(os_map.items())

    db_sha = compute_membership_sha256(db_pairs)
    os_sha = compute_membership_sha256(os_pairs)

    db_count = len(db_map)
    os_count = len(os_map)

    # --- Diff ---
    db_keys = set(db_map)
    os_keys = set(os_map)
    missing_count = len(db_keys - os_keys)   # in DB but not OS
    extra_count = len(os_keys - db_keys)      # in OS but not DB

    # --- Determine status (priority: scan_error > postscan_error > empty_snapshot
    #     > pending_pre > postscan_pending > duplicate_db > duplicate_os
    #     > state_changed > membership > empty_run_id) ---
    error_message: Optional[str] = None
    if scan_error is not None:
        error_message = scan_error
        verification_status = "FAIL"
    elif postscan_error is not None:
        error_message = postscan_error
        verification_status = "FAIL"
    elif not snapshot_id_pre:
        error_message = "No current snapshot: snapshot_id is empty — publication scope has no active snapshot"
        verification_status = "FAIL"
    elif pending_count > 0:
        error_message = (
            f"Uncommitted CHEM events in outbox: pending_count={pending_count}"
        )
        verification_status = "FAIL"
    elif postscan_pending > 0:
        # FIX-02/K04: new PENDING events arrived during scan window
        error_message = (
            f"Uncommitted CHEM events in outbox (post-scan): "
            f"postscan_pending={postscan_pending}"
        )
        verification_status = "FAIL"
    elif duplicate_db_count > 0:
        error_message = (
            f"Duplicate chem_id rows in DB view: duplicate_db_count={duplicate_db_count}"
        )
        verification_status = "FAIL"
    elif os_duplicate_count > 0:
        error_message = (
            f"Duplicate source_key in OS index: os_duplicate_count={os_duplicate_count}"
        )
        verification_status = "FAIL"
    elif state_changed:
        error_message = (
            f"State changed during scan: "
            f"snapshot_id {snapshot_id_pre!r} → {snapshot_id_post!r}, "
            f"outbox_wm {outbox_wm_pre} → {outbox_wm_post}"
        )
        verification_status = "FAIL"
    elif db_sha != os_sha or db_count != os_count or missing_count != 0 or extra_count != 0:
        error_message = (
            f"Membership mismatch: db_count={db_count} os_count={os_count} "
            f"missing={missing_count} extra={extra_count}"
        )
        verification_status = "FAIL"
    elif not rebuild_run_id:
        error_message = "rebuild_run_id is empty — cannot verify OS index provenance"
        verification_status = "FAIL"
    else:
        verification_status = "PASS"

    return SnapshotProof(
        proof_version="1.0",
        publication_scope=scope,
        snapshot_id=snapshot_id_pre,
        snapshot_completed_at=snapshot_completed_at,
        opensearch_alias=CURRENT_ALIAS,
        physical_index=physical_index,
        rebuild_run_id=rebuild_run_id,
        db_membership_count=db_count,
        os_membership_count=os_count,
        db_membership_sha256=db_sha,
        os_membership_sha256=os_sha,
        chem_outbox_high_watermark=outbox_wm_pre,
        verified_at=verified_at,
        verification_status=verification_status,
        missing_count=missing_count,
        extra_count=extra_count,
        duplicate_db_count=duplicate_db_count,
        os_duplicate_count=os_duplicate_count,
        error_message=error_message,
    )


def verify_proof(proof: SnapshotProof) -> bool:
    """Pure validation of a SnapshotProof object (no DB/OS calls).

    Returns True iff:
    - proof_version == "1.0"
    - verification_status == "PASS"
    - snapshot_id is non-empty
    - db_membership_sha256 == os_membership_sha256
    - db_membership_count == os_membership_count
    - missing_count == 0 and extra_count == 0
    - duplicate_db_count == 0 and os_duplicate_count == 0
    - rebuild_run_id is non-empty (OS index provenance must be known)
    """
    return (
        proof.proof_version == "1.0"
        and proof.verification_status == "PASS"
        and bool(proof.snapshot_id)
        and proof.db_membership_sha256 == proof.os_membership_sha256
        and proof.db_membership_count == proof.os_membership_count
        and proof.missing_count == 0
        and proof.extra_count == 0
        and proof.duplicate_db_count == 0
        and proof.os_duplicate_count == 0
        and bool(proof.rebuild_run_id)
    )


# ---------------------------------------------------------------------------
# PATCH-003B: In-memory proof registry
# ---------------------------------------------------------------------------

_registry_lock = threading.Lock()
# CLOSURE-01: scope-keyed registry — SEO_PREVIEW and FULL proofs are independent.
# Prevents a SEO_PREVIEW proof from passing a FULL scope gate.
_registered_proofs: dict[str, SnapshotProof] = {}


def register_proof(proof: SnapshotProof) -> None:
    """Register a proof keyed by publication_scope."""
    with _registry_lock:
        _registered_proofs[proof.publication_scope] = proof


def get_registered_proof(scope: str) -> Optional[SnapshotProof]:
    """Return the registered proof for the given scope, or None."""
    with _registry_lock:
        return _registered_proofs.get(scope)


def clear_proof_registry() -> None:
    """Reset the registry. For tests only."""
    with _registry_lock:
        _registered_proofs.clear()
