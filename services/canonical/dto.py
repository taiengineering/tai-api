"""Canonical diagnosis request DTO + Origin enum.

Pydantic if available; otherwise a plain dataclass-like fallback so the module
is import-safe in any environment.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class Origin(str, Enum):
    ANONYMOUS = "ANONYMOUS"
    MEMBER = "MEMBER"
    PAID = "PAID"
    API = "API"
    ADMIN = "ADMIN"


try:  # pydantic v1/v2
    from pydantic import BaseModel

    class CanonicalDiagnosisRequest(BaseModel):
        origin: Origin = Origin.ANONYMOUS
        site_kind: Optional[str] = None
        scale: Optional[str] = None
        workers: Optional[int] = None
        region: Optional[str] = None
        sector: Optional[str] = None
        raw: Dict[str, Any] = {}

except Exception:  # pragma: no cover - fallback when pydantic absent
    class CanonicalDiagnosisRequest:  # type: ignore
        def __init__(
            self,
            origin: Origin = Origin.ANONYMOUS,
            site_kind: Optional[str] = None,
            scale: Optional[str] = None,
            workers: Optional[int] = None,
            region: Optional[str] = None,
            sector: Optional[str] = None,
            raw: Optional[Dict[str, Any]] = None,
        ) -> None:
            self.origin = origin
            self.site_kind = site_kind
            self.scale = scale
            self.workers = workers
            self.region = region
            self.sector = sector
            self.raw = raw or {}
