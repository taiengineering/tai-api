"""
services/document_link_review_read.py
WO-TAI-DOC-WP03A-LINK-REVIEW-WORKBENCH-001

Read-only candidate review service. DB writes: 0.

CSV snapshot: data/document_link_candidates.csv
  SHA256 : 2875016f404ac329fae79ebf1edd7fc4123ee99d948482875f38ed76db8b3017
  Git blob: ac4630aaa84234149e5354d8e2b0a6e84479f15b
  82 candidates: SAME_DOCUMENT_CANDIDATE=3 / AMBIGUOUS=14 / RELATED_WORKFLOW=43 / VARIANT=22

Note: CSV relation_type values (AMBIGUOUS, RELATED_WORKFLOW, VARIANT) are candidate
classifications only — they are NOT valid unified_document_link.relation_type values
and must never be inserted into the DB.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_CSV_PATH = Path(__file__).parent.parent / "data" / "document_link_candidates.csv"
_EXPECTED_SHA256 = "2875016f404ac329fae79ebf1edd7fc4123ee99d948482875f38ed76db8b3017"

_VALID_SORT_FIELDS = frozenset({
    "similarity_score", "saas_title", "ref_title", "relation_type",
})
_DEFAULT_SORT = "similarity_score"
_DEFAULT_PER_PAGE = 50
_MAX_PER_PAGE = 200


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CandidateSummary:
    candidate_id: str           # "{saas_source_code}__{ref_source_code}"
    saas_source_code: str
    saas_title: str
    ref_source_code: str
    ref_title: str
    similarity_score: float
    relation_type: str          # CSV classification — NOT a DB relation_type
    match_basis: str
    notes: str
    saas_exists: bool
    ref_exists: bool
    stale_source: bool
    stale_reason: Optional[str]
    current_link_status: Optional[str]   # latest non-RETIRED/REJECTED state, or None
    active_link_count: int               # count of PROPOSED/UNDER_REVIEW/APPROVED rows


@dataclass
class CandidateDetail(CandidateSummary):
    saas_document: Optional[dict[str, Any]]
    ref_document: Optional[dict[str, Any]]
    all_links: list[dict[str, Any]] = field(default_factory=list)
    audit_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CandidatePage:
    total: int
    page: int
    per_page: int
    class_counts: dict[str, int]
    items: list[CandidateSummary] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSV loading (cached singleton)
# ---------------------------------------------------------------------------

def _candidate_id(saas_code: str, ref_code: str) -> str:
    return f"{saas_code}__{ref_code}"


@lru_cache(maxsize=1)
def _load_csv() -> list[dict[str, Any]]:
    """Load and SHA256-verify the CSV. Cached after first call."""
    raw = _CSV_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _EXPECTED_SHA256:
        raise RuntimeError(
            f"document_link_candidates.csv SHA256 불일치 "
            f"(expected {_EXPECTED_SHA256[:16]}…, got {digest[:16]}…)"
        )
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        rows.append({
            "candidate_id": _candidate_id(
                row["saas_source_code"].strip(),
                row["ref_source_code"].strip(),
            ),
            "saas_source_code": row["saas_source_code"].strip(),
            "saas_title": row["saas_title"].strip(),
            "ref_source_code": row["ref_source_code"].strip(),
            "ref_title": row["ref_title"].strip(),
            "similarity_score": float(row["similarity_score"]),
            "relation_type": row["relation_type"].strip(),
            "match_basis": row["match_basis"].strip(),
            "notes": row["notes"].strip(),
        })
    return rows


def get_csv_class_counts() -> dict[str, int]:
    rows = _load_csv()
    counts: dict[str, int] = {}
    for r in rows:
        rt = r["relation_type"]
        counts[rt] = counts.get(rt, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# DB enrichment helpers
# ---------------------------------------------------------------------------

def _fetch_saas_docs(
    client: Any, codes: list[str]
) -> dict[str, dict[str, Any]]:
    """Return {doc_id: row} for the given doc_id codes."""
    if not codes:
        return {}
    in_val = "in.(" + ",".join(codes) + ")"
    rows = client.select(
        "document_forms",
        columns="id,doc_id,doc_name,sector,category,doc_format,file_url,is_active,law_ref,regulation_ref",
        filters={"doc_id": in_val},
    )
    return {r["doc_id"]: r for r in rows}


def _fetch_ref_docs(
    client: Any, slugs: list[str]
) -> dict[str, dict[str, Any]]:
    """Return {canonical_slug: row} from reference_form_public_view."""
    if not slugs:
        return {}
    in_val = "in.(" + ",".join(slugs) + ")"
    rows = client.select(
        "reference_form_public_view",
        columns="id,canonical_slug,title,qa_pass_files",
        filters={"canonical_slug": in_val},
    )
    return {r["canonical_slug"]: r for r in rows}


def _fetch_links_by_saas_ids(
    client: Any, saas_uuids: list[str]
) -> list[dict[str, Any]]:
    """Fetch all unified_document_link rows for the given saas_catalog_id UUIDs."""
    if not saas_uuids:
        return []
    in_val = "in.(" + ",".join(saas_uuids) + ")"
    return client.select(
        "unified_document_link",
        columns="id,saas_catalog_id,reference_form_id,relation_type,review_state,"
                "evidence_note,reviewed_by,reviewed_at,owner_approval_ref,version,"
                "created_at,updated_at",
        filters={"saas_catalog_id": in_val},
    )


def _fetch_links_for_pair(
    client: Any, saas_uuid: str, ref_uuid: str
) -> list[dict[str, Any]]:
    """Fetch all unified_document_link rows for a specific saas/ref UUID pair."""
    return client.select(
        "unified_document_link",
        columns="id,saas_catalog_id,reference_form_id,relation_type,review_state,"
                "evidence_note,reviewed_by,reviewed_at,owner_approval_ref,version,"
                "created_at,updated_at",
        filters={
            "saas_catalog_id": f"eq.{saas_uuid}",
            "reference_form_id": f"eq.{ref_uuid}",
        },
    )


def _fetch_audit_for_links(
    client: Any, link_ids: list[str]
) -> list[dict[str, Any]]:
    """Fetch unified_document_link_audit rows for the given link IDs."""
    if not link_ids:
        return []
    in_val = "in.(" + ",".join(link_ids) + ")"
    return client.select(
        "unified_document_link_audit",
        columns="id,link_id,event_type,actor,from_state,to_state,changed_at,"
                "change_note,old_evidence_note,old_value,new_value",
        filters={"link_id": in_val},
        order="changed_at.desc",
    )


# ---------------------------------------------------------------------------
# Enrichment logic
# ---------------------------------------------------------------------------

_ACTIVE_STATES = frozenset({"PROPOSED", "UNDER_REVIEW", "APPROVED"})
_TERMINAL_STATES = frozenset({"REJECTED", "RETIRED"})

# Priority for current_link_status: APPROVED > UNDER_REVIEW > PROPOSED
_STATE_PRIORITY = {"APPROVED": 3, "UNDER_REVIEW": 2, "PROPOSED": 1}


def _summarise_links(links: list[dict]) -> tuple[Optional[str], int]:
    """Return (current_link_status, active_link_count) from a list of link rows.

    current_link_status:
      - Highest active state (APPROVED > UNDER_REVIEW > PROPOSED) if any active link exists.
      - Latest terminal state (REJECTED/RETIRED) if no active links but terminal history exists.
      - None only when no link history at all (link_status filter NONE matches this).
    active_link_count: count of PROPOSED/UNDER_REVIEW/APPROVED rows only.
    Tiebreak on equal priority is deterministic: secondary sort by updated_at desc.
    """
    active = [lk for lk in links if lk["review_state"] in _ACTIVE_STATES]
    count = len(active)
    if active:
        best = max(
            active,
            key=lambda lk: (
                _STATE_PRIORITY.get(lk["review_state"], 0),
                lk.get("updated_at") or "",
            ),
        )
        return best["review_state"], count
    terminal = [lk for lk in links if lk["review_state"] in _TERMINAL_STATES]
    if not terminal:
        return None, 0
    latest = max(terminal, key=lambda lk: lk.get("updated_at") or "")
    return latest["review_state"], 0


def _build_summary(
    row: dict[str, Any],
    saas_row: Optional[dict],
    ref_row: Optional[dict],
    links: list[dict],
) -> CandidateSummary:
    saas_exists = saas_row is not None
    ref_exists = ref_row is not None

    stale_reasons: list[str] = []

    if not saas_exists:
        stale_reasons.append(f"SAAS 문서 {row['saas_source_code']} 원본 미확인")
    else:
        if saas_row.get("is_active") is False:
            stale_reasons.append(f"SAAS 문서 {row['saas_source_code']} 비활성화")
        db_saas_title = (saas_row.get("doc_name") or "").strip()
        if db_saas_title and db_saas_title != row["saas_title"]:
            stale_reasons.append(
                f"SaaS 제목 불일치: CSV='{row['saas_title']}' DB='{db_saas_title}'"
            )

    if not ref_exists:
        stale_reasons.append(f"참고서식 {row['ref_source_code']} 원본 미확인")
    else:
        db_ref_title = (ref_row.get("title") or "").strip()
        if db_ref_title and db_ref_title != row["ref_title"]:
            stale_reasons.append(
                f"참고서식 제목 불일치: CSV='{row['ref_title']}' DB='{db_ref_title}'"
            )

    stale = bool(stale_reasons)
    stale_reason: Optional[str] = "; ".join(stale_reasons) if stale_reasons else None

    current_status, active_count = _summarise_links(links)

    return CandidateSummary(
        candidate_id=row["candidate_id"],
        saas_source_code=row["saas_source_code"],
        saas_title=row["saas_title"],
        ref_source_code=row["ref_source_code"],
        ref_title=row["ref_title"],
        similarity_score=row["similarity_score"],
        relation_type=row["relation_type"],
        match_basis=row["match_basis"],
        notes=row["notes"],
        saas_exists=saas_exists,
        ref_exists=ref_exists,
        stale_source=stale,
        stale_reason=stale_reason,
        current_link_status=current_status,
        active_link_count=active_count,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_candidates(
    client: Any,
    *,
    q: Optional[str] = None,
    relation_type: Optional[str] = None,
    link_status: Optional[str] = None,
    stale_only: bool = False,
    sort: str = _DEFAULT_SORT,
    sort_desc: bool = True,
    page: int = 1,
    per_page: int = _DEFAULT_PER_PAGE,
) -> CandidatePage:
    """
    Return paginated, filtered list of link review candidates.

    q            — substring match on saas_title or ref_title (case-insensitive)
    relation_type — filter by CSV classification (SAME_DOCUMENT_CANDIDATE, etc.)
    link_status   — filter by current_link_status (PROPOSED, UNDER_REVIEW, APPROVED, REJECTED,
                    RETIRED, NONE — NONE means no active link yet)
    stale_only   — if True, only return rows with stale_source=True
    sort         — field name (default: similarity_score)
    sort_desc    — sort descending (default: True)
    page / per_page — pagination (per_page capped at _MAX_PER_PAGE)
    """
    per_page = min(per_page, _MAX_PER_PAGE)
    if sort not in _VALID_SORT_FIELDS:
        sort = _DEFAULT_SORT

    all_rows = _load_csv()
    class_counts = get_csv_class_counts()

    # --- CSV-side filters ---
    if q:
        q_lower = q.lower()
        all_rows = [
            r for r in all_rows
            if q_lower in r["saas_title"].lower() or q_lower in r["ref_title"].lower()
        ]
    if relation_type:
        all_rows = [r for r in all_rows if r["relation_type"] == relation_type]

    if not all_rows:
        return CandidatePage(
            total=0, page=page, per_page=per_page,
            class_counts=class_counts, items=[],
        )

    # --- Batch DB lookups ---
    saas_codes = list({r["saas_source_code"] for r in all_rows})
    ref_slugs = list({r["ref_source_code"] for r in all_rows})
    saas_map = _fetch_saas_docs(client, saas_codes)
    ref_map = _fetch_ref_docs(client, ref_slugs)

    # Collect UUIDs for saas docs that exist
    saas_uuids = [row["id"] for row in saas_map.values()]
    links_by_saas: dict[str, list[dict]] = {}
    if saas_uuids:
        all_links = _fetch_links_by_saas_ids(client, saas_uuids)
        for lk in all_links:
            links_by_saas.setdefault(lk["saas_catalog_id"], []).append(lk)

    # Build summaries
    summaries: list[CandidateSummary] = []
    for row in all_rows:
        saas_row = saas_map.get(row["saas_source_code"])
        ref_row = ref_map.get(row["ref_source_code"])

        # Find links for this pair (need ref UUID too)
        pair_links: list[dict] = []
        if saas_row and ref_row:
            saas_uuid = saas_row["id"]
            ref_uuid = ref_row["id"]
            pair_links = [
                lk for lk in links_by_saas.get(saas_uuid, [])
                if lk["reference_form_id"] == ref_uuid
            ]

        summaries.append(_build_summary(row, saas_row, ref_row, pair_links))

    # --- DB-side filters ---
    if stale_only:
        summaries = [s for s in summaries if s.stale_source]
    if link_status is not None:
        if link_status == "NONE":
            summaries = [s for s in summaries if s.current_link_status is None]
        else:
            summaries = [s for s in summaries if s.current_link_status == link_status]

    total = len(summaries)

    # --- Sort ---
    reverse = sort_desc
    summaries.sort(key=lambda s: getattr(s, sort), reverse=reverse)

    # --- Paginate ---
    offset = (page - 1) * per_page
    page_items = summaries[offset: offset + per_page]

    return CandidatePage(
        total=total,
        page=page,
        per_page=per_page,
        class_counts=class_counts,
        items=page_items,
    )


class CandidateValidationError(Exception):
    """Raised when a candidate pair fails validation before propose."""

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message


def validate_candidate_for_propose(
    client: Any,
    candidate_id: str,
) -> tuple[str, str]:
    """
    Validate that a candidate pair is safe to propose as a link.
    Returns (saas_uuid, ref_uuid) on success.
    Raises CandidateValidationError if:
      - candidate_id not in CSV
      - SAAS or REF document not found in DB
      - stale_source is True (inactive, title mismatch, source not found)

    The caller must use the returned UUIDs for the RPC — never the client-supplied UUIDs.
    """
    all_rows = _load_csv()
    row = next((r for r in all_rows if r["candidate_id"] == candidate_id), None)
    if row is None:
        raise CandidateValidationError(
            "CANDIDATE_NOT_FOUND",
            f"후보 ID '{candidate_id}'를 CSV 스냅샷에서 찾을 수 없습니다.",
        )

    saas_map = _fetch_saas_docs(client, [row["saas_source_code"]])
    ref_map = _fetch_ref_docs(client, [row["ref_source_code"]])
    saas_row = saas_map.get(row["saas_source_code"])
    ref_row = ref_map.get(row["ref_source_code"])

    summary = _build_summary(row, saas_row, ref_row, [])

    if summary.stale_source:
        raise CandidateValidationError(
            "CANDIDATE_STALE",
            f"후보 원본 검증 실패: {summary.stale_reason}",
        )

    return str(saas_row["id"]), str(ref_row["id"])


def get_link_by_id(
    client: Any,
    link_id: str,
) -> Optional[dict[str, Any]]:
    """Return a single unified_document_link row by UUID, or None if not found."""
    rows = client.select(
        "unified_document_link",
        columns="id,saas_catalog_id,reference_form_id,relation_type,review_state,"
                "evidence_note,reviewed_by,reviewed_at,owner_approval_ref,version,"
                "created_at,updated_at",
        filters={"id": f"eq.{link_id}"},
        limit=1,
    )
    return rows[0] if rows else None


def get_link_audit_history(
    client: Any,
    link_id: str,
) -> list[dict[str, Any]]:
    """Return unified_document_link_audit rows for a link, newest first."""
    return _fetch_audit_for_links(client, [link_id])


def get_candidate_detail(
    client: Any,
    candidate_id: str,
) -> Optional[CandidateDetail]:
    """
    Return full candidate detail including DB documents and link/audit history.
    Returns None if candidate_id not found in CSV.
    """
    all_rows = _load_csv()
    row = next((r for r in all_rows if r["candidate_id"] == candidate_id), None)
    if row is None:
        return None

    saas_map = _fetch_saas_docs(client, [row["saas_source_code"]])
    ref_map = _fetch_ref_docs(client, [row["ref_source_code"]])
    saas_row = saas_map.get(row["saas_source_code"])
    ref_row = ref_map.get(row["ref_source_code"])

    pair_links: list[dict] = []
    audit_history: list[dict] = []
    if saas_row and ref_row:
        pair_links = _fetch_links_for_pair(client, saas_row["id"], ref_row["id"])
        if pair_links:
            link_ids = [lk["id"] for lk in pair_links]
            audit_history = _fetch_audit_for_links(client, link_ids)

    summary = _build_summary(row, saas_row, ref_row, pair_links)
    return CandidateDetail(
        **{k: getattr(summary, k) for k in summary.__dataclass_fields__},
        saas_document=saas_row,
        ref_document=ref_row,
        all_links=pair_links,
        audit_history=audit_history,
    )
