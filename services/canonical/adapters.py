"""Input adapters: origin-specific raw payload -> CanonicalDiagnosisRequest.

STAGE B #0 skeleton. Each adapter only sets Origin and copies known fields.
Engine selection and business logic are NOT done here.
"""
from __future__ import annotations

from typing import Any, Dict

from .dto import CanonicalDiagnosisRequest, Origin


class _BaseAdapter:
    origin: Origin = Origin.ANONYMOUS

    def to_canonical(self, raw: Dict[str, Any]) -> CanonicalDiagnosisRequest:
        raw = raw or {}
        return CanonicalDiagnosisRequest(
            origin=self.origin,
            site_kind=raw.get("site_kind"),
            scale=raw.get("scale"),
            workers=raw.get("workers"),
            region=raw.get("region"),
            sector=raw.get("sector"),
            raw=dict(raw),
        )


class AnonymousAdapter(_BaseAdapter):
    origin = Origin.ANONYMOUS


class MemberAdapter(_BaseAdapter):
    origin = Origin.MEMBER


class PaidAdapter(_BaseAdapter):
    origin = Origin.PAID


class ApiAdapter(_BaseAdapter):
    origin = Origin.API


class AdminAdapter(_BaseAdapter):
    origin = Origin.ADMIN
