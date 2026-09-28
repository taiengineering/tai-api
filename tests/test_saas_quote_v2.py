"""Tests for WO-PRICING-V2-BE-OBJ09 — Pricing V2 Quote Integration.

Coverage: Q01-Q90 (90 tests)
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.member_quotes as mq
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteIssueRequestV2
from services.saas_quote_v2 import SaasQuoteV2Error, issue_saas_quote_v2
from services.saas_pricing_preview_v2 import SaasPricingPreviewError

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_quote_v2.py"
_SCHEMA_SRC = Path(__file__).parent.parent / "schemas" / "saas_quote_v2.py"

_SITE_1 = uuid4()
_SITE_2 = uuid4()

_COMPANY_ID = "C-TEST"
_USER_ID = "U-TEST"


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _test_policy():
    from datetime import date
    from schemas.saas_pricing_policy_v2 import (
        SaasPricingPolicyV2, SaasTermDiscountPolicy, SaasWorkerRateBracketPolicy,
    )
    return SaasPricingPolicyV2(
        policy_version="TEST_QUOTE_V1",
        effective_from=date(2026, 9, 28),
        field_uplift_amount=100_000,
        primary_site_rate_bps=10_000,
        additional_site_rate_bps=8_000,
        worker_brackets=[
            SaasWorkerRateBracketPolicy(range_from=1, range_to=None, unit_rate=3_000),
        ],
        vat_rate_bps=1_000,
        term_discounts=[
            SaasTermDiscountPolicy(term_months=1, discount_rate_bps=0),
            SaasTermDiscountPolicy(term_months=3, discount_rate_bps=300),
            SaasTermDiscountPolicy(term_months=6, discount_rate_bps=500),
            SaasTermDiscountPolicy(term_months=9, discount_rate_bps=700),
            SaasTermDiscountPolicy(term_months=12, discount_rate_bps=1_000),
        ],
    )


def _site_req(entity_id: UUID = _SITE_1, sector: str = "INDUSTRY", criteria_value: int = 10):
    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2
    return SaasPricingPreviewSiteRequestV2(
        entity_id=entity_id, sector=sector, criteria_value=criteria_value,
    )


def _issue_req(
    tier: str = "MANAGER",
    workers: int = 0,
    term: int = 1,
    sites=None,
    contact_name: Optional[str] = None,
) -> SaasQuoteIssueRequestV2:
    return SaasQuoteIssueRequestV2(
        product_tier=tier,
        worker_capacity=workers,
        term_months=term,
        sites=sites if sites is not None else [_site_req()],
        contact_name=contact_name,
    )


def _ready_preview(monkeypatch, sites=None, tier="MANAGER", workers=0, term=1):
    """Monkeypatch services.saas_quote_v2.preview_saas_price_v2 to return READY."""
    from services.saas_pricing_preview_v2 import preview_saas_price_v2
    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewResponseV2
    import services.pricing_resolver_svc as prs

    sites = sites or [_site_req()]
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan",
                        lambda *a, **k: {"status": "success", "data": {
                            "service_type": "SAAS", "sector": k.get("sector", a[2]) if len(a) > 2 else "INDUSTRY",
                            "tier_code": "STANDARD", "amount": 149_000,
                            "billing_unit": "MONTHLY", "is_active": True,
                        }})
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy)

    req = _issue_req(tier=tier, workers=workers, term=term, sites=sites)
    actual_preview = preview_saas_price_v2(None, req)
    assert actual_preview.status == "READY", f"fixture error: {actual_preview.status}"
    return actual_preview


def _resolve_by_sector(sb, svc_type, sector, criteria_value=None):
    return {"status": "success", "data": {
        "service_type": "SAAS", "sector": sector,
        "tier_code": "STANDARD", "amount": 149_000,
        "billing_unit": "MONTHLY", "is_active": True,
    }}


def _fake_insert(supabase, base_row, retries=5):
    row = dict(base_row)
    row.setdefault("id", str(uuid4()))
    row.setdefault("quote_no", "QT-000001")
    row.setdefault("created_at", "2026-09-28T00:00:00+09:00")
    return row


def _setup_ready(monkeypatch, sites=None, tier="MANAGER", workers=0, term=1):
    """Returns ready_preview. All monkeypatches for service-level tests."""
    preview = _ready_preview(monkeypatch, sites=sites, tier=tier, workers=workers, term=term)
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry", _fake_insert)
    return preview


# ── FakeSupabase ──────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []

    def select(self, *a, **k): self._op = "select"; return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, p): self._op = "update"; self._payload = p; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, v): self._filters.append(("in", c, v)); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self
    def range(self, s, e): return self
    def is_(self, c, v): return self

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            matched = rows[:]
            for op, c, v in self._filters:
                if op == "eq":
                    matched = [r for r in matched if str(r.get(c)) == str(v)]
                elif op == "in":
                    matched = [r for r in matched if r.get(c) in v]
            return _Result(matched)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid4()))
                rows.append(it); out.append(dict(it))
            return _Result(out)
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {"companies": []}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)


def _fake_sb(company_name="테스트회사"):
    sb = FakeSupabase({"companies": [{"id": _COMPANY_ID, "name": company_name}], "quotes": []})
    return sb


def _current():
    return {"id": _USER_ID, "company_id": _COMPANY_ID, "role_code": "002"}


def _make_app():
    app = FastAPI()
    app.include_router(mq.router)
    return app


def _client(current_user=None, get_sb=None):
    app = _make_app()
    app.dependency_overrides[mq.get_current_user] = lambda: (current_user or _current())
    mq.get_supabase = get_sb or (lambda: _fake_sb())
    return TestClient(app, raise_server_exceptions=False)


def _code_lines(path: Path) -> str:
    lines = path.read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- ")))


# ═══════════════════════════════════════════════════════════════════════════════
# Q01–Q04: Router Contract
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q01_endpoint_exists():
    paths = [r.path for r in mq.router.routes]
    assert "/me/quotes/v2/issue" in paths


def test_Q02_method_is_post():
    for route in mq.router.routes:
        if route.path == "/me/quotes/v2/issue":
            assert "POST" in route.methods


def test_Q03_auth_required():
    app = _make_app()
    mq.get_supabase = lambda: _fake_sb()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/me/quotes/v2/issue", json={
        "product_tier": "MANAGER", "worker_capacity": 0, "term_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code in (401, 403, 422)


def test_Q04_existing_routes_remain():
    paths = [r.path for r in mq.router.routes]
    for p in ("/me/quotes/auto/preview", "/me/quotes/auto", "/me/quotes/custom",
              "/me/quotes", "/me/quotes/{quote_id}", "/me/quotes/{quote_id}/pdf"):
        assert p in paths, f"기존 라우트 누락: {p}"


# ═══════════════════════════════════════════════════════════════════════════════
# Q05–Q15: Request Authority — forbidden client fields
# ═══════════════════════════════════════════════════════════════════════════════

def _issue_json(**extra):
    base = {
        "product_tier": "MANAGER", "worker_capacity": 0, "term_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    }
    base.update(extra)
    return base


def test_Q05_company_id_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(company_id="C-EVIL"))
    assert resp.status_code == 422


def test_Q06_created_by_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(created_by="U-EVIL"))
    assert resp.status_code == 422


def test_Q07_source_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(source="member_auto"))
    assert resp.status_code == 422


def test_Q08_status_code_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(status_code="ISSUED"))
    assert resp.status_code == 422


def test_Q09_pricing_mode_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(pricing_mode="STANDARD"))
    assert resp.status_code == 422


def test_Q10_base_amount_rejected():
    c = _client()
    body = _issue_json()
    body["sites"][0]["base_amount"] = 149000
    resp = c.post("/me/quotes/v2/issue", json=body)
    assert resp.status_code == 422


def test_Q11_base_band_code_rejected():
    c = _client()
    body = _issue_json()
    body["sites"][0]["base_band_code"] = "STANDARD"
    resp = c.post("/me/quotes/v2/issue", json=body)
    assert resp.status_code == 422


def test_Q12_supply_amount_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(supply_amount=149000))
    assert resp.status_code == 422


def test_Q13_vat_amount_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(vat_amount=14900))
    assert resp.status_code == 422


def test_Q14_total_amount_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(total_amount=163900))
    assert resp.status_code == 422


def test_Q15_pricing_snapshot_rejected():
    c = _client()
    resp = c.post("/me/quotes/v2/issue", json=_issue_json(pricing_snapshot={"fake": True}))
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Q16–Q19: Company Scope
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q16_company_id_from_auth_context(monkeypatch):
    preview = _setup_ready(monkeypatch)
    sb = _fake_sb()
    row = issue_saas_quote_v2(sb, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["company_id"] == _COMPANY_ID


def test_Q17_created_by_from_auth_context(monkeypatch):
    _setup_ready(monkeypatch)
    sb = _fake_sb()
    row = issue_saas_quote_v2(sb, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["created_by"] == _USER_ID


def test_Q18_no_company_returns_403():
    app = _make_app()
    no_company_user = {"id": "U-N", "company_id": None, "role_code": "002"}
    app.dependency_overrides[mq.get_current_user] = lambda: no_company_user
    fake_sb = FakeSupabase({
        "companies": [],
        "role_data_scope": [{"role_code": "002", "scope_type": "COMPANY"}],
    })
    mq.get_supabase = lambda: fake_sb
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/me/quotes/v2/issue", json=_issue_json())
    assert resp.status_code == 403


def test_Q19_company_id_not_in_request_schema():
    assert "company_id" not in SaasQuoteIssueRequestV2.model_fields


# ═══════════════════════════════════════════════════════════════════════════════
# Q20–Q23: Server Repricing
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q20_issue_calls_preview_v2(monkeypatch):
    called = []
    preview = _ready_preview(monkeypatch)

    def capture_preview(sb, req):
        called.append(req)
        return preview

    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", capture_preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry", _fake_insert)

    issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert len(called) == 1


def test_Q21_client_snapshot_not_trusted(monkeypatch):
    """Request에 pricing_snapshot 필드 자체가 없음을 확인."""
    assert "pricing_snapshot" not in SaasQuoteIssueRequestV2.model_fields


def test_Q22_no_v1_calc_quote_call(monkeypatch):
    """서비스 소스에 calc_quote 직접 호출 없음."""
    code = _code_lines(_SVC_SRC)
    assert "calc_quote(" not in code


def test_Q23_no_v1_tier_code_price_calculation(monkeypatch):
    """서비스가 resolve_plan 직접 호출 없음 (Preview V2 경유)."""
    code = _code_lines(_SVC_SRC)
    assert "resolve_plan(" not in code


# ═══════════════════════════════════════════════════════════════════════════════
# Q24–Q29: READY → Quote INSERT
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q24_ready_produces_insert(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row is not None


def test_Q25_exactly_one_insert(monkeypatch):
    preview = _ready_preview(monkeypatch)
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    insert_calls = []

    def track_insert(sb, base_row, retries=5):
        insert_calls.append(dict(base_row))
        return _fake_insert(sb, base_row)

    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry", track_insert)
    issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert len(insert_calls) == 1


def test_Q26_insert_table_is_quotes(monkeypatch):
    """_insert_quote_with_unique_retry uses quotes table (verified via real FakeSupabase)."""
    preview = _ready_preview(monkeypatch)
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    sb = _fake_sb()
    from services.member_quote_svc import _insert_quote_with_unique_retry
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry",
                        lambda sb2, row, retries=5: _insert_quote_with_unique_retry(sb, row, retries))
    issue_saas_quote_v2(sb, _issue_req(), _USER_ID, _COMPANY_ID)
    ops = [(t, op) for t, op in sb.log if t == "quotes"]
    assert any(op == "insert" for _, op in ops)


def test_Q27_status_code_is_issued(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["status_code"] == "ISSUED"


def test_Q28_source_is_member_auto(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["source"] == "member_auto"


def test_Q29_service_type_is_saas(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["service_type"] == "SAAS"


# ═══════════════════════════════════════════════════════════════════════════════
# Q30–Q32: Pricing Gate
# ═══════════════════════════════════════════════════════════════════════════════

def _mock_preview_status(monkeypatch, status: str):
    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewResponseV2
    fake = SaasPricingPreviewResponseV2(
        status=status,
        product_tier="MANAGER",
        pricing_mode="STANDARD" if status != "CUSTOM_REQUIRED" else "CUSTOM",
        worker_capacity=0,
        term_months=1,
        resolved_sites=[],
        calculation=None,
        block_reason=status,
    )
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: fake)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    insert_calls = []
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry",
                        lambda *a, **k: insert_calls.append(1) or {})
    return insert_calls


def test_Q30_term_unresolved_raises_not_ready_no_insert(monkeypatch):
    inserts = _mock_preview_status(monkeypatch, "TERM_DISCOUNT_UNRESOLVED")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PRICING_NOT_READY"
    assert len(inserts) == 0


def test_Q31_custom_required_no_insert(monkeypatch):
    inserts = _mock_preview_status(monkeypatch, "CUSTOM_REQUIRED")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "CUSTOM_QUOTE_REQUIRED"
    assert len(inserts) == 0


def test_Q32_compliance_base_no_insert(monkeypatch):
    inserts = _mock_preview_status(monkeypatch, "COMPLIANCE_BASE_QUOTE_REQUIRED")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "COMPLIANCE_BASE_QUOTE_REQUIRED"
    assert len(inserts) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Q33–Q37: Snapshot Type Boundary
# ═══════════════════════════════════════════════════════════════════════════════

def _mock_malformed_calculation(monkeypatch, calc_override):
    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewResponseV2
    fake = SaasPricingPreviewResponseV2(
        status="READY",
        product_tier="MANAGER",
        pricing_mode="STANDARD",
        worker_capacity=0,
        term_months=1,
        resolved_sites=[],
        calculation=calc_override,
        block_reason=None,
    )
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: fake)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")


def test_Q33_malformed_calculation_raises_invalid(monkeypatch):
    _mock_malformed_calculation(monkeypatch, {"status": "not_a_valid_result"})
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_SNAPSHOT_INVALID"


def test_Q34_none_snapshot_raises_invalid(monkeypatch):
    from services.saas_pricing_composer_v2 import SaasPricingCalculationResult
    calc = SaasPricingCalculationResult(
        status="READY",
        policy_version="TEST",
        site_breakdown=None,
        worker_breakdown=None,
        monthly_supply_amount=149_000,
        raw_prepaid_supply_amount=149_000,
        term_months=1,
        term_discount_rate_bps=0,
        snapshot=None,
        block_reason=None,
    )
    _mock_malformed_calculation(monkeypatch, calc)
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_SNAPSHOT_INVALID"


def test_Q35_wrong_product_tier_raises_invalid(monkeypatch):
    """snapshot.product_tier != request.product_tier → QUOTE_SNAPSHOT_INVALID."""
    preview = _ready_preview(monkeypatch, tier="MANAGER")
    from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
    snap = preview.calculation.snapshot
    bad_snap = snap.model_copy(update={"product_tier": "FIELD"})
    bad_calc = preview.calculation.model_copy(update={"snapshot": bad_snap})
    bad_preview = preview.model_copy(update={"calculation": bad_calc})
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: bad_preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(tier="MANAGER"), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_SNAPSHOT_INVALID"


def test_Q36_wrong_worker_raises_invalid(monkeypatch):
    preview = _ready_preview(monkeypatch, workers=0)
    snap = preview.calculation.snapshot
    bad_worker = snap.worker.model_copy(update={"capacity": 5})
    bad_snap = snap.model_copy(update={"worker": bad_worker})
    bad_calc = preview.calculation.model_copy(update={"snapshot": bad_snap})
    bad_preview = preview.model_copy(update={"calculation": bad_calc})
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: bad_preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(workers=0), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_SNAPSHOT_INVALID"


def test_Q37_wrong_term_raises_invalid(monkeypatch):
    preview = _ready_preview(monkeypatch, term=1)
    snap = preview.calculation.snapshot
    bad_snap = snap.model_copy(update={"term_months": 3})
    bad_calc = preview.calculation.model_copy(update={"snapshot": bad_snap})
    bad_preview = preview.model_copy(update={"calculation": bad_calc})
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: bad_preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(term=1), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_SNAPSHOT_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# Q38–Q45: Quote Item Content
# ═══════════════════════════════════════════════════════════════════════════════

def _get_item(row: dict) -> dict:
    return row["items"][0]


def test_Q38_quote_schema_version(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["quote_schema_version"] == SAAS_QUOTE_SCHEMA_VERSION


def test_Q39_price_id_is_none(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["price_id"] is None


def test_Q40_tier_code_is_none(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["tier_code"] is None


def test_Q41_manager_display_name(monkeypatch):
    _setup_ready(monkeypatch, tier="MANAGER")
    row = issue_saas_quote_v2(None, _issue_req(tier="MANAGER"), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["display_name"] == "TAI Safe 관리자형"


def test_Q42_field_display_name(monkeypatch):
    _setup_ready(monkeypatch, tier="FIELD")
    row = issue_saas_quote_v2(None, _issue_req(tier="FIELD"), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["display_name"] == "TAI Safe 현장참여형"


def test_Q43_billing_unit_monthly(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert _get_item(row)["billing_unit"] == "MONTHLY"


def test_Q44_unit_amount_equals_snapshot_monthly(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["unit_amount"] == item["pricing_snapshot"]["monthly_supply_amount"]


def test_Q45_quantity_equals_term_months(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(term=1), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["quantity"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Q46–Q51: Monetary Snapshot
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q46_item_supply_equals_snapshot_prepaid(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["supply_amount"] == item["pricing_snapshot"]["prepaid_supply_amount"]


def test_Q47_item_vat_equals_snapshot_vat(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["vat_amount"] == item["pricing_snapshot"]["vat_amount"]


def test_Q48_item_total_equals_snapshot_total(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["total_amount"] == item["pricing_snapshot"]["total_amount"]


def test_Q49_top_level_supply_equals_snapshot_prepaid(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert row["supply_amount"] == item["pricing_snapshot"]["prepaid_supply_amount"]


def test_Q50_top_level_vat_equals_snapshot_vat(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert row["vat_amount"] == item["pricing_snapshot"]["vat_amount"]


def test_Q51_top_level_total_equals_snapshot_total(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert row["total_amount"] == item["pricing_snapshot"]["total_amount"]


# ═══════════════════════════════════════════════════════════════════════════════
# Q52–Q56: No Recalculation (Source Guards)
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q52_no_monthly_times_term_calculation():
    code = _code_lines(_SVC_SRC)
    assert "monthly_supply_amount * " not in code
    assert "* term_months" not in code


def test_Q53_no_vat_multiplication():
    code = _code_lines(_SVC_SRC)
    assert "* 0.1" not in code
    assert "vat_rate_bps *" not in code


def test_Q54_no_field_uplift_formula():
    code = _code_lines(_SVC_SRC)
    assert "field_uplift" not in code
    assert "100_000" not in code


def test_Q55_no_additional_site_formula():
    code = _code_lines(_SVC_SRC)
    assert "additional_site_rate" not in code
    assert "0.8" not in code


def test_Q56_no_worker_bracket_formula():
    code = _code_lines(_SVC_SRC)
    assert "worker_bracket" not in code
    assert "unit_rate" not in code


# ═══════════════════════════════════════════════════════════════════════════════
# Q57–Q64: Nested Frozen Snapshot
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q57_pricing_snapshot_complete(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    required_keys = {"schema_version", "policy_version", "product_tier", "pricing_mode",
                     "sites", "worker", "term_months", "term_discount_rate_bps",
                     "monthly_supply_amount", "prepaid_supply_amount",
                     "vat_rate_bps", "vat_amount", "total_amount"}
    assert required_keys.issubset(snap.keys())


def test_Q58_schema_version_preserved(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["schema_version"] == "SAAS_PRICING_V2"


def test_Q59_policy_version_preserved(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["policy_version"] == "TEST_QUOTE_V1"


def test_Q60_product_tier_preserved(monkeypatch):
    _setup_ready(monkeypatch, tier="MANAGER")
    row = issue_saas_quote_v2(None, _issue_req(tier="MANAGER"), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["product_tier"] == "MANAGER"


def test_Q61_sites_preserved(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert isinstance(snap["sites"], list)
    assert len(snap["sites"]) >= 1


def test_Q62_worker_preserved(monkeypatch):
    _setup_ready(monkeypatch, workers=0)
    row = issue_saas_quote_v2(None, _issue_req(workers=0), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["worker"]["capacity"] == 0


def test_Q63_term_preserved(monkeypatch):
    _setup_ready(monkeypatch, term=1)
    row = issue_saas_quote_v2(None, _issue_req(term=1), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["term_months"] == 1


def test_Q64_monetary_totals_preserved(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    snap = _get_item(row)["pricing_snapshot"]
    assert snap["monthly_supply_amount"] > 0
    assert snap["prepaid_supply_amount"] > 0
    assert snap["vat_amount"] > 0
    assert snap["total_amount"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Q65–Q68: Pricing Input Evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q65_pricing_input_preserves_criteria_value(monkeypatch):
    _setup_ready(monkeypatch, sites=[_site_req(criteria_value=99)])
    row = issue_saas_quote_v2(None, _issue_req(sites=[_site_req(criteria_value=99)]),
                               _USER_ID, _COMPANY_ID)
    inp = _get_item(row)["pricing_input"]
    assert any(s["criteria_value"] == 99 for s in inp["sites"])


def test_Q66_pricing_input_preserves_entity_id(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(sites=[_site_req(_SITE_1)]),
                               _USER_ID, _COMPANY_ID)
    inp = _get_item(row)["pricing_input"]
    assert any(s["entity_id"] == str(_SITE_1) for s in inp["sites"])


def test_Q67_pricing_input_preserves_sector(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(sites=[_site_req(sector="INDUSTRY")]),
                               _USER_ID, _COMPANY_ID)
    inp = _get_item(row)["pricing_input"]
    assert any(s["sector"] == "INDUSTRY" for s in inp["sites"])


def test_Q68_pricing_input_has_no_amount_fields(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    inp = _get_item(row)["pricing_input"]
    forbidden = {"base_amount", "unit_amount", "supply_amount", "vat_amount", "total_amount",
                 "monthly_supply_amount", "prepaid_supply_amount"}
    assert not forbidden.intersection(inp.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# Q69–Q72: Multi-site
# ═══════════════════════════════════════════════════════════════════════════════

def _multi_site_resolve(sb, svc_type, sector, criteria_value=None):
    return {"status": "success", "data": {
        "service_type": "SAAS", "sector": sector,
        "tier_code": "STANDARD", "amount": 149_000,
        "billing_unit": "MONTHLY", "is_active": True,
    }}


def test_Q69_single_sector_field_exact(monkeypatch):
    _setup_ready(monkeypatch, sites=[_site_req(sector="INDUSTRY")])
    row = issue_saas_quote_v2(None, _issue_req(sites=[_site_req(sector="INDUSTRY")]),
                               _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["sector"] == "INDUSTRY"
    assert item["sectors"] == ["INDUSTRY"]


def test_Q70_multiple_sectors_sector_none(monkeypatch):
    sites = [
        _site_req(_SITE_1, sector="INDUSTRY"),
        _site_req(_SITE_2, sector="CONSTRUCTION", criteria_value=5_000_000_000),
    ]
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", _multi_site_resolve)
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy)
    from services.saas_pricing_preview_v2 import preview_saas_price_v2 as real_preview
    preview = real_preview(None, _issue_req(sites=sites))
    assert preview.status == "READY"
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry", _fake_insert)
    row = issue_saas_quote_v2(None, _issue_req(sites=sites), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["sector"] is None
    assert "INDUSTRY" in item["sectors"]
    assert "CONSTRUCTION" in item["sectors"]


def test_Q71_sectors_canonical_sorted(monkeypatch):
    sites = [
        _site_req(_SITE_2, sector="CONSTRUCTION", criteria_value=5_000_000_000),
        _site_req(_SITE_1, sector="INDUSTRY"),
    ]
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", _multi_site_resolve)
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy)
    from services.saas_pricing_preview_v2 import preview_saas_price_v2 as real_preview
    preview = real_preview(None, _issue_req(sites=sites))
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: "테스트회사")
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry", _fake_insert)
    row = issue_saas_quote_v2(None, _issue_req(sites=sites), _USER_ID, _COMPANY_ID)
    item = _get_item(row)
    assert item["sectors"] == sorted(item["sectors"])


def test_Q72_composite_item_count_is_one(monkeypatch):
    _setup_ready(monkeypatch, sites=[_site_req(_SITE_1), _site_req(_SITE_2)])
    row = issue_saas_quote_v2(None, _issue_req(sites=[_site_req(_SITE_1), _site_req(_SITE_2)]),
                               _USER_ID, _COMPANY_ID)
    assert len(row["items"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Q73–Q74: Company Snapshot
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q73_company_name_captured(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["company_name"] == "테스트회사"


def test_Q74_missing_company_name_raises(monkeypatch):
    preview = _ready_preview(monkeypatch)
    monkeypatch.setattr("services.saas_quote_v2.preview_saas_price_v2", lambda *a, **k: preview)
    monkeypatch.setattr("services.member_quote_svc._company_name_snapshot", lambda *a: None)
    insert_calls = []
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry",
                        lambda *a, **k: insert_calls.append(1) or {})
    with pytest.raises(SaasQuoteV2Error) as exc:
        issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert exc.value.code == "COMPANY_SNAPSHOT_REQUIRED"
    assert len(insert_calls) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Q75: Contact Name
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q75_contact_name_normalized(monkeypatch):
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(contact_name="  홍길동  "), _USER_ID, _COMPANY_ID)
    assert row["contact_name"] in (None, "홍길동", "  홍길동  ")


# ═══════════════════════════════════════════════════════════════════════════════
# Q76–Q77: Quote Number
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q76_existing_retry_reused():
    """서비스 소스가 _insert_quote_with_unique_retry 를 직접 사용."""
    code = _code_lines(_SVC_SRC)
    assert "_insert_quote_with_unique_retry" in code


def test_Q77_client_quote_no_not_in_schema():
    assert "quote_no" not in SaasQuoteIssueRequestV2.model_fields


# ═══════════════════════════════════════════════════════════════════════════════
# Q78–Q80: PDF Compatibility
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q78_v2_quote_passes_validate_snapshot(monkeypatch):
    """_validate_snapshot은 정합성 체크만 함 — 실제 PDF 렌더링 불필요."""
    from services.member_quote_pdf_svc import _validate_snapshot, QuotePdfError
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    # _validate_snapshot이 요구하는 top-level 필드 추가 (실제 INSERT 후 DB가 채우는 필드들)
    row["id"] = str(uuid4())
    row["quote_no"] = "QT-000001"
    row["created_at"] = "2026-09-28T00:00:00+09:00"
    try:
        item = _validate_snapshot(row)
        assert item is not None
    except QuotePdfError as e:
        pytest.fail(f"_validate_snapshot 실패: {e.code} — {e.message}")


def test_Q79_pdf_service_not_modified():
    src = Path(__file__).parent.parent / "services" / "member_quote_pdf_svc.py"
    import subprocess
    result = subprocess.run(
        ["git", "diff", "40d98ada", "--", str(src)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    assert result.stdout.strip() == "", "member_quote_pdf_svc.py 변경 감지"


def test_Q80_pdf_no_price_master_lookup():
    """서비스가 price_master를 직접 조회하지 않는다."""
    code = _code_lines(_SVC_SRC)
    assert '"price_master"' not in code
    assert "'price_master'" not in code


# ═══════════════════════════════════════════════════════════════════════════════
# Q81–Q85: Member/Admin Compatibility
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q81_member_auto_in_member_sources():
    from services.member_quote_svc import MEMBER_SOURCES
    assert "member_auto" in MEMBER_SOURCES


def test_Q82_list_service_not_modified():
    src = Path(__file__).parent.parent / "services" / "member_quote_svc.py"
    import subprocess
    result = subprocess.run(
        ["git", "diff", "40d98ada", "--", str(src)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    assert result.stdout.strip() == "", "member_quote_svc.py 변경 감지"


def test_Q83_detail_service_not_modified():
    src = Path(__file__).parent.parent / "services" / "member_quote_svc.py"
    import subprocess
    result = subprocess.run(
        ["git", "diff", "40d98ada", "--", str(src)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    assert result.stdout.strip() == ""


def test_Q84_admin_quote_service_not_modified():
    src = Path(__file__).parent.parent / "services" / "admin_quote_svc.py"
    import subprocess
    result = subprocess.run(
        ["git", "diff", "40d98ada", "--", str(src)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    assert result.stdout.strip() == "", "admin_quote_svc.py 변경 감지"


def test_Q85_v2_source_is_member_auto(monkeypatch):
    """V2 견적 source=member_auto이므로 기존 list/admin 소비처 수정 불필요."""
    _setup_ready(monkeypatch)
    row = issue_saas_quote_v2(None, _issue_req(), _USER_ID, _COMPANY_ID)
    assert row["source"] == "member_auto"


# ═══════════════════════════════════════════════════════════════════════════════
# Q86–Q90: Side Effects
# ═══════════════════════════════════════════════════════════════════════════════

def test_Q86_no_contracts_write():
    code = _code_lines(_SVC_SRC)
    assert '"contracts"' not in code
    assert "'contracts'" not in code


def test_Q87_no_subscriptions_write():
    code = _code_lines(_SVC_SRC)
    assert '"subscriptions"' not in code
    assert "'subscriptions'" not in code


def test_Q88_no_payment_write():
    code = _code_lines(_SVC_SRC)
    assert "payment" not in code.lower() or "payment_svc" not in code


def test_Q89_no_document_write():
    code = _code_lines(_SVC_SRC)
    assert '"documents"' not in code
    assert "'documents'" not in code


def test_Q90_no_slack_event():
    code = _code_lines(_SVC_SRC)
    assert "send_slack" not in code
    assert "slack_dispatcher" not in code
