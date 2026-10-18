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


def _scan_os_chem_ids(client) -> dict[str, str]:
    """Returns {source_key (chem_id): canonical_id} for all CHEM PUBLIC docs.

    Uses search_after pagination — no 10k cap.
    Filter: object_type=CHEM, publication_status=PUBLISHED, visibility_scopes=PUBLIC.
    Returns empty dict on failure (graceful).
    """
    result: dict[str, str] = {}
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
            resp = client.search(index=CURRENT_ALIAS, body=body)
            hits = (resp.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for hit in hits:
                src = hit.get("_source") or {}
                source_key = src.get("source_key") or ""
                canonical_id = src.get("canonical_id") or ""
                if source_key and canonical_id:
                    result[source_key] = canonical_id
            search_after = hits[-1].get("sort")
            if len(hits) < _OS_PAGE_SIZE:
                break
    except Exception as exc:
        logger.warning("snapshot_proof: OS scan failed: %s", exc)
        return {}
    return result


# ---------------------------------------------------------------------------
# Read-only DB scan
# ---------------------------------------------------------------------------


def _scan_db_chem_ids(sb, scope: str) -> dict[str, str]:
    """Returns {chem_id: id (canonical_id)} from the published scope view.

    SEO_PREVIEW -> kosha_msds_seo_preview_current
    FULL        -> kosha_msds_current
    Paginates with page_size=1000 on chem_id order.
    Returns empty dict on failure (graceful).
    """
    view = (
        SEO_PREVIEW_CURRENT_VIEW
        if scope == PUBLICATION_SCOPE_SEO_PREVIEW
        else _FULL_CURRENT_VIEW
    )
    result: dict[str, str] = {}
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
            for row in rows:
                chem_id = str(row.get("chem_id") or "")
                canonical_id = str(row.get("id") or "")
                if chem_id and canonical_id:
                    result[chem_id] = canonical_id
            if len(rows) < _DB_PAGE_SIZE:
                break
            last_chem_id = str(rows[-1].get("chem_id") or "")
    except Exception as exc:
        logger.warning("snapshot_proof: DB scan failed (scope=%s): %s", scope, exc)
        return {}
    return result


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

    Searches for a doc with status=PROMOTED and matching index name,
    or directly with physical_index field matching. Returns '' if not found.
    """
    if not physical_index:
        return ""
    try:
        body = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"physical_index": physical_index}},
                        {
                            "bool": {
                                "filter": [
                                    {"term": {"status": "PROMOTED"}},
                                    {"term": {"index_name": physical_index}},
                                ]
                            }
                        },
                    ],
                    "minimum_should_match": 1,
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
    """Get MAX event_id from search_index_outbox where status='COMPLETED'.

    Returns 0 on error.
    """
    try:
        r = (
            sb.table("search_index_outbox")
            .select("event_id")
            .eq("status", "COMPLETED")
            .order("event_id", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if rows:
            return int(rows[0].get("event_id") or 0)
    except Exception as exc:
        logger.warning("snapshot_proof: outbox watermark lookup failed: %s", exc)
    return 0


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
    outbox_wm_pre = _get_outbox_watermark(sb)
    physical_index = _get_physical_index(client)
    rebuild_run_id = _get_rebuild_run_id(client, physical_index)

    # --- Scans ---
    db_map = _scan_db_chem_ids(sb, scope)
    os_map = _scan_os_chem_ids(client)

    # --- Post-scan state check ---
    snapshot_id_post, _ = _get_current_snapshot(sb, scope)
    outbox_wm_post = _get_outbox_watermark(sb)

    state_changed = (
        snapshot_id_pre != snapshot_id_post
        or outbox_wm_pre != outbox_wm_post
    )

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

    # --- Determine status ---
    error_message: Optional[str] = None
    if state_changed:
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
        error_message=error_message,
    )


def verify_proof(proof: SnapshotProof) -> bool:
    """Pure validation of a SnapshotProof object (no DB/OS calls).

    Returns True iff:
    - proof_version == "1.0"
    - verification_status == "PASS"
    - db_membership_sha256 == os_membership_sha256
    - db_membership_count == os_membership_count
    - missing_count == 0 and extra_count == 0
    """
    return (
        proof.proof_version == "1.0"
        and proof.verification_status == "PASS"
        and proof.db_membership_sha256 == proof.os_membership_sha256
        and proof.db_membership_count == proof.os_membership_count
        and proof.missing_count == 0
        and proof.extra_count == 0
    )


# ---------------------------------------------------------------------------
# PATCH-003B: In-memory proof registry
# ---------------------------------------------------------------------------

_registry_lock = threading.Lock()
_registered_proof: Optional[SnapshotProof] = None
_registered_state: Optional[tuple] = None  # (snapshot_id, physical_index, outbox_wm)


def register_proof(proof: SnapshotProof) -> None:
    """Register a proof for use by the runtime gate."""
    global _registered_proof, _registered_state
    state = (proof.snapshot_id, proof.physical_index, proof.chem_outbox_high_watermark)
    with _registry_lock:
        _registered_proof = proof
        _registered_state = state


def get_registered_proof() -> Optional[SnapshotProof]:
    """Return the currently registered proof, or None."""
    with _registry_lock:
        return _registered_proof


def clear_proof_registry() -> None:
    """Reset the registry. For tests only."""
    global _registered_proof, _registered_state
    with _registry_lock:
        _registered_proof = None
        _registered_state = None
