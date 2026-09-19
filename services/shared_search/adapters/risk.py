"""RISK adapter — WO-TAI-SHARED-SEARCH-F2 §24.

RISK adapter is present so the DomainAdapter surface is uniform, but
DELIBERATELY yields the empty iterable. RISK canonical is currently:

    status = DRAFT   (all 1,110 rows)
    status = ACTIVE  (0 rows)
    sector links     (0 rows)

RISK-C02 opens the ACTIVE gate. Until then this adapter MUST NOT
produce SearchDocuments — the F2 audit test proves it.
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import expected_hashes_from_documents


Fetcher = Callable[[], Iterable[dict]]


class RiskAdapter:
    domain_name = "RISK"
    object_type = "RISK"

    def __init__(
        self,
        *,
        fetch_active: Optional[Fetcher] = None,
    ):
        # Injectable so a future RISK-C02 WO can flip this on with a
        # single fetcher change — no other Foundation code needs to
        # move. Until RISK-C02 the default is "always empty".
        self._fetch_active = fetch_active or (lambda: iter(()))

    def iter_documents(self) -> Iterator[dict]:
        # Empty generator — F2 §24 requires RISK to produce zero
        # SearchDocuments until RISK-C02 opens the ACTIVE gate. Even
        # if a future misconfigured fetcher yields DRAFT rows, the
        # adapter maps NONE of them.
        return
        yield {}  # pragma: no cover  (marks this as a generator)

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        return None
