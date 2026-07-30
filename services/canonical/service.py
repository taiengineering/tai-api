"""CanonicalDiagnosisService (STAGE B — by-construction wrapper).

Single Canonical entry. Zero business logic. evaluate() only executes the
identical delegate (the existing router impl), so output equals the legacy path
by construction. Engine selection is NOT done here (Decision Pending).

claim()/upgrade()/report() remain skeleton stubs for later WOs.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from .dto import CanonicalDiagnosisRequest
from .engine_interface import DiagnosisEngine


class CanonicalDiagnosisService:
    def __init__(self, engine: Optional[DiagnosisEngine] = None) -> None:
        self._engine = engine

    async def evaluate(
        self,
        dto: CanonicalDiagnosisRequest,
        delegate: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Canonical entry point. No business logic.

        `dto` proves the request passed through Adapter->Canonical. `delegate`
        is the identical legacy impl (bound with the original request object),
        so execution and output are byte-for-byte the legacy path.
        """
        return await delegate()

    def claim(self, public_token: str, user_id: str) -> Dict[str, Any]:
        raise NotImplementedError("later WO")

    def upgrade(self, public_token: str, target_tier: str,
                payment: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError("later WO")

    def report(self, public_token: str) -> Dict[str, Any]:
        raise NotImplementedError("later WO")
