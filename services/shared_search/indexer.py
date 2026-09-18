"""Common Index Orchestrator.

WO-TAI-SHARED-SEARCH-F2. One `Indexer` composes any set of Domain
adapters that satisfy `DomainAdapter`. Every adapter goes through
the same pipeline — no per-Domain orchestration code.

Exposes four operations:

    full_rebuild(adapters)          — Foundation §11.1
    domain_rebuild(adapter)         — same, single Domain
    object_reindex(adapter, cid)    — Foundation §11.2
    reconcile_domain(adapter)       — Foundation §11.3
    dry_run(adapter)                — normalize-only census, no writer
                                       side effects

The Indexer never touches Domain SoT directly and never touches the
Search Projection directly. It calls
`services.shared_search.RebuildFramework` and `Writer`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from services.shared_search.adapters.base import (
    AdapterBlockedSubtype,
    DomainAdapter,
)
from services.shared_search.document import normalize_document
from services.shared_search.hash_utils import content_hash
from services.shared_search.rebuild import RebuildFramework
from services.shared_search.reconcile import ReconcileReport, reconcile
from services.shared_search.store import SearchStore
from services.shared_search.writer import Writer


@dataclass
class RebuildResult:
    run_id: str
    status: str
    promoted_count: int
    per_domain: dict         # {domain_name: staged_count}
    blocked_subtypes: tuple  # ({"domain": ..., "reason": ...})


@dataclass
class DryRunCensus:
    domain: str
    object_type: str
    total_yielded: int
    unique_canonical_ids: int
    duplicate_canonical_ids: int
    source_key_null_count: int
    subject_pair_count: int
    context_tuple_count: int
    visibility_public: int
    visibility_saas: int
    visibility_paid: int
    hash_collisions: int
    normalization_failures: int


class Indexer:
    def __init__(self, store: SearchStore):
        self.store = store
        self.writer = Writer(store)
        self.rebuild = RebuildFramework(store, writer=self.writer)

    # ---------------------------------------------------------------
    # FULL REBUILD across a set of adapters.
    # ---------------------------------------------------------------
    def full_rebuild(
        self,
        adapters: Iterable[DomainAdapter],
        *,
        manifest: Optional[dict] = None,
    ) -> RebuildResult:
        adapters = list(adapters)
        expected = [a.domain_name for a in adapters]
        run = self.rebuild.begin(expected_domains=expected, manifest=manifest)

        per_domain: dict[str, int] = {a.domain_name: 0 for a in adapters}
        blocked: list[dict] = []

        for adapter in adapters:
            try:
                for payload in adapter.iter_documents():
                    self.rebuild.stage(run, payload)
                    per_domain[adapter.domain_name] += 1
            except AdapterBlockedSubtype as exc:
                blocked.append({
                    "domain": adapter.domain_name,
                    "reason": str(exc),
                })
            self.rebuild.mark_domain_done(run, adapter.domain_name)

        self.rebuild.validate(run)
        promoted = self.rebuild.promote(run)
        return RebuildResult(
            run_id=run.run_id,
            status=run.status,
            promoted_count=promoted,
            per_domain=per_domain,
            blocked_subtypes=tuple(blocked),
        )

    def domain_rebuild(
        self,
        adapter: DomainAdapter,
        *,
        manifest: Optional[dict] = None,
    ) -> RebuildResult:
        return self.full_rebuild([adapter], manifest=manifest)

    # ---------------------------------------------------------------
    # OBJECT REINDEX.
    # ---------------------------------------------------------------
    def object_reindex(
        self,
        adapter: DomainAdapter,
        canonical_id: str,
    ) -> Optional[bool]:
        """Reindex a single canonical object. Returns:
            True   — PUBLISHED payload written / updated
            False  — HOLD / REMOVED tombstoned
            None   — Domain says the object should be dropped (writer.tombstone)
        """
        payload = adapter.object_reindex_payload(canonical_id)
        if payload is None:
            existed = self.writer.tombstone(adapter.object_type, canonical_id)
            return None if existed else False
        doc = self.writer.upsert_current(payload)
        return doc.publication_status == "PUBLISHED"

    # ---------------------------------------------------------------
    # RECONCILE — READ-only.
    # ---------------------------------------------------------------
    def reconcile_domain(self, adapter: DomainAdapter) -> ReconcileReport:
        return reconcile(
            self.store,
            adapter.object_type,
            adapter.iter_expected_hashes(),
        )

    # ---------------------------------------------------------------
    # DRY RUN — normalize adapter output without writing.
    # Used by production census (F2 WO §26, §27).
    # ---------------------------------------------------------------
    def dry_run(self, adapter: DomainAdapter) -> DryRunCensus:
        seen: set[str] = set()
        duplicates = 0
        source_key_null = 0
        subject_count = 0
        context_count = 0
        vis_public = 0
        vis_saas = 0
        vis_paid = 0
        hashes: set[str] = set()
        collisions = 0
        norm_failures = 0
        total = 0

        for payload in adapter.iter_documents():
            total += 1
            try:
                doc = normalize_document(payload)
            except Exception:
                norm_failures += 1
                continue
            if doc.canonical_id in seen:
                duplicates += 1
            seen.add(doc.canonical_id)
            if doc.source_key is None:
                source_key_null += 1
            subject_count += len(doc.subjects)
            context_count += len(doc.context)
            if "PUBLIC" in doc.visibility_scopes:
                vis_public += 1
            if "SAAS" in doc.visibility_scopes:
                vis_saas += 1
            if "PAID" in doc.visibility_scopes:
                vis_paid += 1
            h = content_hash(doc)
            if h in hashes:
                collisions += 1
            hashes.add(h)

        return DryRunCensus(
            domain=adapter.domain_name,
            object_type=adapter.object_type,
            total_yielded=total,
            unique_canonical_ids=len(seen),
            duplicate_canonical_ids=duplicates,
            source_key_null_count=source_key_null,
            subject_pair_count=subject_count,
            context_tuple_count=context_count,
            visibility_public=vis_public,
            visibility_saas=vis_saas,
            visibility_paid=vis_paid,
            hash_collisions=collisions,
            normalization_failures=norm_failures,
        )
