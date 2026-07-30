"""Unit tests for the Canonical pipeline skeleton (STAGE B #0 + evaluate delegate).

Construction/interface + delegation only. No Runtime, no DB, no network.
"""
import asyncio

from services.canonical.dto import CanonicalDiagnosisRequest, Origin
from services.canonical.adapters import (
    AnonymousAdapter, MemberAdapter, PaidAdapter, ApiAdapter, AdminAdapter,
)
from services.canonical.engine_interface import (
    DiagnosisEngine, CompilerCoreEngine, LEGEngine,
)
from services.canonical.service import CanonicalDiagnosisService
from services.canonical.flags import canonical_enabled


def test_dto_construction():
    dto = AnonymousAdapter().to_canonical(
        {"sector": "CONSTRUCTION", "workers": 30, "region": "서울",
         "scale": "medium", "site_kind": "construction"}
    )
    assert dto.origin == Origin.ANONYMOUS
    assert dto.workers == 30


def test_all_adapters_set_origin():
    cases = [
        (AnonymousAdapter, Origin.ANONYMOUS), (MemberAdapter, Origin.MEMBER),
        (PaidAdapter, Origin.PAID), (ApiAdapter, Origin.API), (AdminAdapter, Origin.ADMIN),
    ]
    for adapter_cls, origin in cases:
        assert adapter_cls().to_canonical({}).origin == origin


def test_engines_implement_interface():
    assert issubclass(CompilerCoreEngine, DiagnosisEngine)
    assert issubclass(LEGEngine, DiagnosisEngine)


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("CANONICAL_PIPELINE", raising=False)
    assert canonical_enabled() is False


def test_evaluate_executes_identical_delegate():
    async def _run():
        svc = CanonicalDiagnosisService()
        marker = {"ran": 0}
        sentinel = {"status": "success", "publicToken": "X"}

        async def fake_impl():
            marker["ran"] += 1
            return sentinel

        dto = AnonymousAdapter().to_canonical(
            {"site_kind": "construction", "scale": "medium", "workers": 30, "region": "서울"}
        )
        out = await svc.evaluate(dto=dto, delegate=fake_impl)
        assert marker["ran"] == 1
        assert out is sentinel
    asyncio.run(_run())
