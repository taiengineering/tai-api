"""DomainAdapter Protocol.

WO-TAI-SHARED-SEARCH-F2. Every Domain adapter implements the same
Protocol so the Common Indexer treats all Domains uniformly. Adapters
are STORE-agnostic — they never touch `search_documents`. They only:

    1. Read from Domain SoT (via injected reader).
    2. Filter to their own publication eligibility.
    3. Normalize each SoT row into a SearchDocument payload dict.

The Indexer does the SearchStore work.
"""
from __future__ import annotations

from typing import Iterator, Optional, Protocol, runtime_checkable


class AdapterBlockedSubtype(Exception):
    """Raised by an adapter when a Domain subtype cannot be
    deterministically indexed today.

    Example: the LEGAL adapter may support obligation-atom rows but
    block law-article rows until F2 evidence is complete. Raising
    this exception is a signal to the Indexer to skip THAT subtype
    without failing the run.
    """


@runtime_checkable
class DomainAdapter(Protocol):
    """Uniform Domain adapter surface.

    Attributes:
        domain_name  — human-readable identifier (used in run manifests)
        object_type  — the SearchDocument.object_type this adapter produces
    """

    domain_name: str
    object_type: str

    def iter_documents(self) -> Iterator[dict]:
        """Yield SearchDocument payload dicts for every eligible Domain row.

        `iter_documents` is what the Indexer streams into the writer. Each
        yielded dict must be acceptable to
        `services.shared_search.document.normalize_document` — the writer
        will validate + hash it.

        Ineligible / not-yet-published rows MUST NOT be yielded. HOLD /
        REMOVED payloads MAY be yielded — the writer treats them as
        tombstones — but Foundation-side each adapter's default is to
        omit non-PUBLISHED rows entirely (fewer round-trips).
        """
        ...

    def iter_expected_hashes(self) -> Iterator[dict]:
        """Yield {"canonical_id", "content_hash"} rows for reconciliation.

        Same set as `iter_documents` at PUBLISHED-only. The reconciler
        compares against `search_documents` for this `object_type`.
        """
        ...

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        """Return the SearchDocument payload for a single canonical id,
        or None if the Domain says it should be tombstoned. Used by the
        Indexer's `object_reindex()` API when a Domain publish/change
        event fires.
        """
        ...
