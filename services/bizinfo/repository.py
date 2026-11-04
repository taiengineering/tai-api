"""OBJ-BZI-004/005 — Bizinfo Repository Interface.

STORAGE_GATE boundary.

This module defines the Protocol that any storage backend must satisfy
and provides an InMemoryBizinfoRepository for local integration tests.

Production implementation (Supabase) requires STORAGE_GATE Owner approval:
  - Table: bizinfo_source_records
  - Table: bizinfo_editorial_content
  Schemas are intentionally not defined here — schema creation requires
  a separate DB migration Gate.

Usage:
  - Tests inject InMemoryBizinfoRepository directly.
  - Production code will inject SupabaseBizinfoRepository (not yet implemented).
  - Application code depends on BizinfoRepository Protocol only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from services.bizinfo.approval import (
    ContentApprovalRecord,
    EditorialContent,
    RightsRecord,
)
from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.status import ChangeRecord


# ---------------------------------------------------------------------------
# Repository Protocol (STORAGE_GATE boundary)
# ---------------------------------------------------------------------------


@runtime_checkable
class BizinfoRepository(Protocol):
    """Storage interface for bizinfo source records and editorial content.

    All methods are synchronous.  A Supabase implementation would wrap
    each call in a service-role client call.  Requires STORAGE_GATE approval.
    """

    def get_prior_record(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[NormalizedSourceRecord]:
        """Return the most recently stored snapshot, or None if first observation."""
        ...

    def save_record(
        self,
        record: NormalizedSourceRecord,
        change: ChangeRecord,
    ) -> None:
        """Persist a new snapshot and its change record."""
        ...

    def get_editorial(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[EditorialContent]:
        """Return TAI editorial content, or None if not yet authored."""
        ...

    def get_rights(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[RightsRecord]:
        """Return rights confirmation record, or None if not yet confirmed."""
        ...

    def get_approval(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[ContentApprovalRecord]:
        """Return content approval record, or None if not yet approved."""
        ...

    def get_relevance_verdict(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[str]:
        """Return the selector/analyzer relevance verdict, or None if not assessed."""
        ...

    def save_relevance_verdict(
        self,
        source_kind: str,
        source_key: str,
        verdict: str,
    ) -> None:
        """Persist the selector/analyzer verdict for an existing record."""
        ...

    def list_eligible_keys(
        self,
        source_kind: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[str]:
        """Return source_keys of announcements cleared for public display."""
        ...


# ---------------------------------------------------------------------------
# In-memory stub — integration tests and dev only
# ---------------------------------------------------------------------------


@dataclass
class InMemoryBizinfoRepository:
    """Non-persistent in-memory implementation for local integration tests.

    Not for production use.  State is lost when the process exits.
    Pre-seed with synthetic records via seed_* methods.
    """
    _records:    dict[tuple[str, str], NormalizedSourceRecord] = field(
        default_factory=dict
    )
    _changes:    dict[tuple[str, str], ChangeRecord] = field(
        default_factory=dict
    )
    _editorials: dict[tuple[str, str], EditorialContent] = field(
        default_factory=dict
    )
    # Rights are keyed by source_key only — RightsRecord has no source_kind field.
    # (Rights belong to the content itself, not to its PROGRAM/EVENT classification.)
    _rights:     dict[str, RightsRecord] = field(
        default_factory=dict
    )
    _approvals:  dict[tuple[str, str], ContentApprovalRecord] = field(
        default_factory=dict
    )
    # Relevance verdicts from selector/analyzer (IN_SCOPE/INCLUDE/EXCLUDE/HOLD/etc.)
    _relevance:  dict[tuple[str, str], str] = field(
        default_factory=dict
    )

    def _key(self, source_kind: str, source_key: str) -> tuple[str, str]:
        return (source_kind, source_key)

    # -- BizinfoRepository Protocol ----------------------------------------

    def get_prior_record(
        self, source_kind: str, source_key: str
    ) -> Optional[NormalizedSourceRecord]:
        return self._records.get(self._key(source_kind, source_key))

    def save_record(
        self, record: NormalizedSourceRecord, change: ChangeRecord
    ) -> None:
        k = self._key(record.source_kind, record.source_key)
        self._records[k] = record
        self._changes[k] = change

    def get_editorial(
        self, source_kind: str, source_key: str
    ) -> Optional[EditorialContent]:
        return self._editorials.get(self._key(source_kind, source_key))

    def get_rights(
        self, source_kind: str, source_key: str
    ) -> Optional[RightsRecord]:
        return self._rights.get(source_key)

    def get_approval(
        self, source_kind: str, source_key: str
    ) -> Optional[ContentApprovalRecord]:
        return self._approvals.get(self._key(source_kind, source_key))

    def get_relevance_verdict(
        self, source_kind: str, source_key: str
    ) -> Optional[str]:
        return self._relevance.get(self._key(source_kind, source_key))

    def save_relevance_verdict(
        self, source_kind: str, source_key: str, verdict: str
    ) -> None:
        self._relevance[self._key(source_kind, source_key)] = verdict

    def list_eligible_keys(
        self, source_kind: str, limit: int = 50, offset: int = 0
    ) -> list[str]:
        return [
            key for (kind, key) in self._approvals
            if kind == source_kind
        ][offset : offset + limit]

    # -- Seed helpers (test/dev only) --------------------------------------

    def seed_record(
        self, record: NormalizedSourceRecord, change: ChangeRecord
    ) -> "InMemoryBizinfoRepository":
        self.save_record(record, change)
        return self

    def seed_editorial(
        self, editorial: EditorialContent
    ) -> "InMemoryBizinfoRepository":
        self._editorials[self._key(editorial.source_kind, editorial.source_key)] = editorial
        return self

    def seed_rights(
        self, rights: RightsRecord
    ) -> "InMemoryBizinfoRepository":
        self._rights[rights.source_key] = rights
        return self

    def seed_approval(
        self, approval: ContentApprovalRecord
    ) -> "InMemoryBizinfoRepository":
        self._approvals[self._key(approval.source_kind, approval.source_key)] = approval
        return self

    def seed_relevance(
        self, source_kind: str, source_key: str, verdict: str
    ) -> "InMemoryBizinfoRepository":
        self._relevance[self._key(source_kind, source_key)] = verdict
        return self
