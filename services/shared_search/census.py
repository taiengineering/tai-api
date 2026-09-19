"""Shared READ-only Domain census.

WO-TAI-SHARED-SEARCH-F2 CO §36. Any capability used by 2+ Domains
lives here (Foundation shared-use rule). The census module walks a
Domain adapter's `iter_documents()` output — WITHOUT touching the
search projection — and returns a `DomainCensus`.

Zero SearchStore calls. Zero Writer calls. Zero
Indexer.full_rebuild calls. Zero RPC. Zero DML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from services.shared_search.adapters.base import (
    AdapterBlockedSubtype, DomainAdapter,
)
from services.shared_search.contract import SearchContractError
from services.shared_search.document import normalize_document
from services.shared_search.hash_utils import content_hash


@dataclass
class DomainCensus:
    domain: str
    object_type: str
    # SoT-side visibility
    source_row_count: Optional[int] = None    # optional if adapter/reader supplies it
    # Adapter-side counts
    yielded_count: int = 0
    unique_canonical_ids: int = 0
    duplicate_canonical_ids: int = 0
    source_key_null_count: int = 0
    identity_failures: int = 0
    title_failures: int = 0
    timestamp_failures: int = 0
    normalization_failures: int = 0
    subject_pair_count: int = 0
    context_pair_count: int = 0
    hash_collisions: int = 0
    same_hash_different_payload: int = 0
    # publication_status breakdown after normalization
    published: int = 0
    hold: int = 0
    removed: int = 0
    # visibility scope breakdown at PUBLISHED rows
    visibility_public: int = 0
    visibility_saas: int = 0
    visibility_paid: int = 0
    visibility_internal: int = 0
    blocked_subtypes: tuple = ()
    warnings: tuple = ()

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.__dict__.items()}


def run_census(
    adapter: DomainAdapter,
    *,
    source_row_count: Optional[int] = None,
) -> DomainCensus:
    """Enumerate the adapter's PUBLISHED-eligible output and return a
    `DomainCensus`. **READ-only** — never writes to a SearchStore.

    `source_row_count` is optional metadata the caller may supply so
    the census can report "yielded / source" ratio; the census
    otherwise only inspects the adapter's own output.
    """
    census = DomainCensus(
        domain=adapter.domain_name,
        object_type=adapter.object_type,
        source_row_count=source_row_count,
    )
    seen_ids: set[str] = set()
    hashes: dict[str, str] = {}   # content_hash -> canonical_id
    warnings: list[str] = []
    blocked: list[str] = []

    def _drain(iterable):
        while True:
            try:
                yield next(iterable)
            except StopIteration:
                return
            except AdapterBlockedSubtype as exc:
                blocked.append(str(exc))
                return

    it = iter(adapter.iter_documents())
    for payload in _drain(it):
        census.yielded_count += 1
        try:
            doc = normalize_document(payload)
        except SearchContractError as exc:
            msg = str(exc).lower()
            if "canonical_id" in msg or "object_type" in msg or "source_id" in msg:
                census.identity_failures += 1
            elif "title" in msg or "search_text" in msg:
                census.title_failures += 1
            elif "source_updated_at" in msg:
                census.timestamp_failures += 1
            else:
                census.normalization_failures += 1
            warnings.append(f"norm-fail: {exc}")
            continue
        # Identity + provenance counts
        if doc.canonical_id in seen_ids:
            census.duplicate_canonical_ids += 1
        seen_ids.add(doc.canonical_id)
        if doc.source_key is None:
            census.source_key_null_count += 1
        # Subject / context pair counts (from normalized shape)
        census.subject_pair_count += len(doc.subjects)
        census.context_pair_count += len(doc.context)
        # Publication + visibility
        if doc.publication_status == "PUBLISHED":
            census.published += 1
            if "PUBLIC" in doc.visibility_scopes:
                census.visibility_public += 1
            if "SAAS" in doc.visibility_scopes:
                census.visibility_saas += 1
            if "PAID" in doc.visibility_scopes:
                census.visibility_paid += 1
            if "INTERNAL" in doc.visibility_scopes:
                census.visibility_internal += 1
        elif doc.publication_status == "HOLD":
            census.hold += 1
        elif doc.publication_status == "REMOVED":
            census.removed += 1
        # Content-hash collision audit (§43)
        h = content_hash(doc)
        prev = hashes.get(h)
        if prev is not None and prev != doc.canonical_id:
            census.same_hash_different_payload += 1
        elif prev is not None:
            census.hash_collisions += 1
        hashes[h] = doc.canonical_id

    census.unique_canonical_ids = len(seen_ids)
    census.blocked_subtypes = tuple(blocked)
    census.warnings = tuple(warnings[:20])   # cap noise
    return census
