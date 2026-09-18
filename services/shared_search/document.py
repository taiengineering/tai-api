"""SearchDocument dataclass + deterministic normalization.

WO-TAI-SHARED-SEARCH-F1. Contract source: docs/search/
TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md §3.

`normalize_document` is idempotent — running it twice yields the
same output. That property is what content_hash relies on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from services.shared_search.contract import (
    ALLOWED_CONTEXT_TYPES,
    ALLOWED_PUBLICATION_STATUSES,
    ALLOWED_VISIBILITY_SCOPES,
    FORBIDDEN_DOCUMENT_KEYS,
    SearchContractError,
)


@dataclass
class SearchDocument:
    """One row of the unified search projection.

    Field order matches supabase/migrations/20260919_shared_search_foundation.sql.
    Types are Python-side; the SQL migration owns the physical shape.
    """
    object_type: str
    canonical_id: str
    source_id: str
    source_key: Optional[str]
    title: str
    summary: Optional[str]
    search_text: str
    aliases: tuple = ()
    keywords: tuple = ()
    subjects: tuple = ()          # tuple of {"subject_type": str, "subject_key": str}
    context: tuple = ()           # tuple of {"context_type": str, "context_key": str}
    public_url: Optional[str] = None
    saas_url: Optional[str] = None
    publication_status: str = ""  # required at validate() time
    visibility_scopes: tuple = ()
    source_updated_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    indexed_at: Optional[datetime] = None

    # Extra keys are strictly forbidden — the writer rejects them.
    # But dataclass(kw_only) would break older tooling, so unknowns
    # come in via a plain dict at the writer boundary (see writer.py).


def _stripped(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SearchContractError(
            f"expected str, got {type(value).__name__}")
    return value.strip() or None


def _require_str(value: Any, field: str) -> str:
    s = _stripped(value)
    if not s:
        raise SearchContractError(f"missing required field: {field}")
    return s


def _canonical_str_list(values: Iterable[Any], field: str) -> tuple:
    """Sort + dedup a string list deterministically."""
    if values is None:
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v is None:
            continue
        if not isinstance(v, str):
            raise SearchContractError(
                f"{field}: expected str element, got {type(v).__name__}")
        v = v.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    out.sort()
    return tuple(out)


def _canonical_subjects(subjects: Iterable[Any]) -> tuple:
    if subjects is None:
        return ()
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for entry in subjects:
        if not isinstance(entry, dict):
            raise SearchContractError(
                f"subjects: entry must be dict, got {type(entry).__name__}")
        stype = _require_str(entry.get("subject_type"), "subjects[].subject_type")
        skey = _require_str(entry.get("subject_key"), "subjects[].subject_key")
        key = (stype, skey)
        if key in seen:
            continue
        seen.add(key)
        out.append({"subject_type": stype, "subject_key": skey})
    out.sort(key=lambda e: (e["subject_type"], e["subject_key"]))
    return tuple(out)


def _canonical_context(context: Iterable[Any]) -> tuple:
    if context is None:
        return ()
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for entry in context:
        if not isinstance(entry, dict):
            raise SearchContractError(
                f"context: entry must be dict, got {type(entry).__name__}")
        ctype = _require_str(entry.get("context_type"), "context[].context_type")
        ckey = _require_str(entry.get("context_key"), "context[].context_key")
        if ctype not in ALLOWED_CONTEXT_TYPES:
            raise SearchContractError(
                f"context[].context_type={ctype!r} is not in the allowed set "
                f"{sorted(ALLOWED_CONTEXT_TYPES)}")
        key = (ctype, ckey)
        if key in seen:
            continue
        seen.add(key)
        out.append({"context_type": ctype, "context_key": ckey})
    out.sort(key=lambda e: (e["context_type"], e["context_key"]))
    return tuple(out)


def _canonical_visibility_scopes(scopes: Iterable[Any]) -> tuple:
    if scopes is None:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for s in scopes:
        if not isinstance(s, str):
            raise SearchContractError(
                f"visibility_scopes: expected str, got {type(s).__name__}")
        s = s.strip()
        if not s:
            continue
        if s not in ALLOWED_VISIBILITY_SCOPES:
            raise SearchContractError(
                f"visibility_scopes: {s!r} not in {sorted(ALLOWED_VISIBILITY_SCOPES)}")
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    out.sort()
    return tuple(out)


def normalize_document(payload: dict) -> SearchDocument:
    """Turn a raw dict into a validated + normalized SearchDocument.

    Rejects on:
    - missing required fields (object_type, canonical_id, source_id,
      title, search_text, publication_status, source_updated_at)
    - unknown / forbidden keys (tenant / secret / applicability / LLM)
    - invalid publication_status
    - invalid visibility scope
    - invalid context_type
    - malformed subject / context entries

    Preserves NULL source_key (contract §3).
    """
    if not isinstance(payload, dict):
        raise SearchContractError("document payload must be a dict")

    # Forbidden key guard (tenant secrets, applicability leakage, LLM).
    for k in payload.keys():
        if k in FORBIDDEN_DOCUMENT_KEYS:
            raise SearchContractError(
                f"document must not carry forbidden key {k!r}")

    object_type = _require_str(payload.get("object_type"), "object_type")
    canonical_id = _require_str(payload.get("canonical_id"), "canonical_id")
    source_id = _require_str(payload.get("source_id"), "source_id")
    source_key = _stripped(payload.get("source_key"))   # may be None

    title = _require_str(payload.get("title"), "title")
    summary = _stripped(payload.get("summary"))
    search_text = _require_str(payload.get("search_text"), "search_text")

    aliases = _canonical_str_list(payload.get("aliases") or (), "aliases")
    keywords = _canonical_str_list(payload.get("keywords") or (), "keywords")

    subjects = _canonical_subjects(payload.get("subjects") or ())
    context = _canonical_context(payload.get("context") or ())

    public_url = _stripped(payload.get("public_url"))
    saas_url = _stripped(payload.get("saas_url"))

    publication_status = _require_str(
        payload.get("publication_status"), "publication_status")
    if publication_status not in ALLOWED_PUBLICATION_STATUSES:
        raise SearchContractError(
            f"publication_status={publication_status!r} not in "
            f"{sorted(ALLOWED_PUBLICATION_STATUSES)}")

    visibility_scopes = _canonical_visibility_scopes(
        payload.get("visibility_scopes") or ())

    src_upd = payload.get("source_updated_at")
    if src_upd is None:
        raise SearchContractError("missing required field: source_updated_at")
    if isinstance(src_upd, str):
        try:
            src_upd = datetime.fromisoformat(src_upd.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SearchContractError(
                f"source_updated_at not a valid ISO8601: {src_upd!r}") from exc
    if not isinstance(src_upd, datetime):
        raise SearchContractError(
            "source_updated_at must be datetime or ISO8601 string")

    return SearchDocument(
        object_type=object_type,
        canonical_id=canonical_id,
        source_id=source_id,
        source_key=source_key,
        title=title,
        summary=summary,
        search_text=search_text,
        aliases=aliases,
        keywords=keywords,
        subjects=subjects,
        context=context,
        public_url=public_url,
        saas_url=saas_url,
        publication_status=publication_status,
        visibility_scopes=visibility_scopes,
        source_updated_at=src_upd,
    )
