"""Shared READ-only Domain census.

WO-TAI-SHARED-SEARCH-F2 CO §36. Any capability used by 2+ Domains
lives here (Foundation shared-use rule). The census module walks a
Domain adapter's `iter_documents()` output — WITHOUT touching the
search projection — and returns a `DomainCensus`.

F2 FINAL2: also records eligible_source_count vs yielded_count so an
adapter `return None` cannot hide a silent drop. The invariant is:

    eligible_source_count - yielded_count = explicitly explained exclusions

Unexplained difference is recorded as `unexplained_drop`. Domain
adapters must not reimplement this comparison.

Zero SearchStore calls. Zero Writer calls. Zero
Indexer.full_rebuild calls. Zero RPC. Zero DML.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional

from services.shared_search.adapters.base import (
    AdapterBlockedSubtype, DomainAdapter,
)
from services.shared_search.contract import SearchContractError
from services.shared_search.document import normalize_document
from services.shared_search.hash_utils import content_hash


class CountingFetcher:
    """Wrap a zero-arg row factory and count how many source rows it
    produced. Shared across every Domain — no per-adapter copy."""

    def __init__(self, inner: Callable[[], Iterable[dict]]):
        self._inner = inner
        self.count = 0

    def __call__(self) -> Iterator[dict]:
        n = 0
        try:
            for row in self._inner():
                n += 1
                yield row
        finally:
            self.count = n


def source_yield_audit(
    *,
    eligible_source_count: int,
    yielded_count: int,
    explained_exclusions: Optional[Iterable[Mapping[str, Any]]] = None,
) -> dict:
    """Common eligible→yield comparison. Domain adapters MUST NOT
    duplicate this arithmetic.

    `explained_exclusions` is a sequence of `{"reason", "count"}`
    mappings. Any remaining difference is `unexplained_drop`.
    """
    explained = [dict(item) for item in (explained_exclusions or ())]
    explained_count = sum(int(item.get("count") or 0) for item in explained)
    difference = eligible_source_count - yielded_count
    return {
        "eligible_source_count": eligible_source_count,
        "yielded_count": yielded_count,
        "source_yield_difference": difference,
        "explained_exclusion_count": explained_count,
        "explained_exclusions": explained,
        "unexplained_drop": difference - explained_count,
    }


@dataclass
class DomainCensus:
    domain: str
    object_type: str
    # SoT-side visibility
    source_row_count: Optional[int] = None    # alias of eligible_source_count
    eligible_source_count: Optional[int] = None
    source_yield_difference: Optional[int] = None
    explained_exclusion_count: int = 0
    unexplained_drop: Optional[int] = None
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
    explained_exclusions: tuple = ()
    adapter_extras: dict = None  # filled after to_dict default

    def __post_init__(self):
        if self.adapter_extras is None:
            self.adapter_extras = {}

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in self.__dict__.items()}


def _apply_source_yield(
    census: DomainCensus,
    *,
    eligible_source_count: Optional[int],
    explained_exclusions: Optional[Iterable[Mapping[str, Any]]],
) -> None:
    if eligible_source_count is None:
        return
    audit = source_yield_audit(
        eligible_source_count=eligible_source_count,
        yielded_count=census.yielded_count,
        explained_exclusions=explained_exclusions,
    )
    census.eligible_source_count = audit["eligible_source_count"]
    census.source_row_count = audit["eligible_source_count"]
    census.source_yield_difference = audit["source_yield_difference"]
    census.explained_exclusion_count = audit["explained_exclusion_count"]
    census.explained_exclusions = tuple(audit["explained_exclusions"])
    census.unexplained_drop = audit["unexplained_drop"]
    if census.unexplained_drop:
        census.warnings = census.warnings + (
            f"unexplained source→yield drop={census.unexplained_drop}",
        )


def run_census(
    adapter: DomainAdapter,
    *,
    source_row_count: Optional[int] = None,
    eligible_source_count: Optional[int] = None,
    explained_exclusions: Optional[Iterable[Mapping[str, Any]]] = None,
) -> DomainCensus:
    """Enumerate the adapter's PUBLISHED-eligible output and return a
    `DomainCensus`. **READ-only** — never writes to a SearchStore.

    `eligible_source_count` (alias `source_row_count`) is optional.
    When omitted, census wraps the adapter's `_fetch_current` with
    `CountingFetcher` so source rows that the adapter silently
    drops as `None` are still visible as `unexplained_drop`.
    """
    if eligible_source_count is None:
        eligible_source_count = source_row_count

    census = DomainCensus(
        domain=adapter.domain_name,
        object_type=adapter.object_type,
        source_row_count=eligible_source_count,
        eligible_source_count=eligible_source_count,
    )
    seen_ids: set[str] = set()
    hashes: dict[str, str] = {}   # content_hash -> canonical_id
    warnings: list[str] = []
    blocked: list[str] = []

    original_fetch = getattr(adapter, "_fetch_current", None)
    wrapped: Optional[CountingFetcher] = None
    if eligible_source_count is None and callable(original_fetch):
        if isinstance(original_fetch, CountingFetcher):
            wrapped = original_fetch
        else:
            wrapped = CountingFetcher(original_fetch)
            adapter._fetch_current = wrapped

    def _drain(iterable):
        while True:
            try:
                yield next(iterable)
            except StopIteration:
                return
            except AdapterBlockedSubtype as exc:
                blocked.append(str(exc))
                return

    try:
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
    finally:
        if wrapped is not None and wrapped is not original_fetch:
            adapter._fetch_current = original_fetch

    census.unique_canonical_ids = len(seen_ids)
    census.blocked_subtypes = tuple(blocked)
    census.warnings = tuple(warnings[:20])   # cap noise
    extras = getattr(adapter, "census_extras", None)
    if extras:
        census.adapter_extras = dict(extras)
    fallback = getattr(adapter, "title_fallback_count", None)
    if fallback is not None:
        census.adapter_extras["title_fallback_count"] = fallback

    measured_eligible = eligible_source_count
    if measured_eligible is None and wrapped is not None:
        measured_eligible = wrapped.count
    elif measured_eligible is None and not callable(original_fetch) and census.yielded_count == 0:
        measured_eligible = 0
    _apply_source_yield(
        census,
        eligible_source_count=measured_eligible,
        explained_exclusions=explained_exclusions,
    )
    return census
