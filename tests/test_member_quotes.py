"""STEP 2A /me/quotes 회원 견적 Core — service + router 단위테스트 (FakeSupabase 격리).

WO-MYPAGE-QUOTE-PROCESS-001. 운영 DB/네트워크 불사용. price_master fixture 실측값
(SAAS INDUSTRY_BUSINESS 299,000 · DIAGNOSIS INDUSTRY_STARTER 149,000 · INDUSTRY_CUSTOM 0)
로 계산 정확성 검증. 소유권/회사스코프/created_by/source 필터/회귀 quotes 라우터 부재.

케이스 매트릭스 (지시서 §T1~T18 + REG):
  T1 401  T2 403  T3 타사 company_id 무시    T4 unit_amount 299000
  T5 클라이언트 total 위조 무시              T6 SaaS×12 총합
  T7 DIAGNOSIS 1회성                         T8 CUSTOM 409/route_to_custom
  T9 미존재 tier 404                         T10 vat_rate=row(하드코딩 검증)
  T11 total == supply+vat                    T12 A사→A사 목록 노출
  T13 A사→B사 목록 미노출                     T14 B사가 A사 상세 404
  T15 created_by=current.id                  T16 survey_web 미노출
  T17 member_auto 노출                       T18 member_custom 노출
  REG 기존 /quotes 라우터 무접촉(모듈 import 유지)
"""
from __future__ import annotations

import os
import uuid

import pytest

# main 로드 시 필요한 최소 env
os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.member_quotes as mq
from services import member_quote_svc as svc

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


# ── FakeSupabase (in-memory, chainable) ─────────────────────────────
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._count_exact = False
        self._range = None; self._order = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        if k.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def limit(self, n): self._limit = n; return self
    def order(self, col, *, desc=False, **k): self._order = (col, desc); return self
    def range(self, s, e): self._range = (s, e); return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
                return False
            if op == "is" and v == "null" and row.get(c) is not None:
                return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys}

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            if self._order:
                col, desc = self._order
                matched = sorted(matched, key=lambda r: (r.get(col) or ""), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e + 1]
            elif self._limit is not None:
                matched = matched[:self._limit]
            projected = [self._project(r) for r in matched]
            return _Result(projected, count=total if self._count_exact else None)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            return _Result([dict(r) for r in matched])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)


# ── price_master 실측값 fixture ──────────────────────────────────────
def _price_master_rows():
    return [
        {"id": "pm-saas-ind-biz", "service_type": "SAAS", "sector": "INDUSTRY",
         "tier_code": "INDUSTRY_BUSINESS", "billing_unit": "MONTHLY",
         "amount": 299000, "vat_rate": 0.1, "vat_included": False,
         "display_name": "산업 비즈니스", "is_active": True},
        {"id": "pm-diag-ind-start", "service_type": "DIAGNOSIS", "sector": "INDUSTRY",
         "tier_code": "INDUSTRY_STARTER", "billing_unit": "ONCE",
         "amount": 149000, "vat_rate": 0.1, "vat_included": False,
         "display_name": "산업 스타터 진단", "is_active": True},
        {"id": "pm-saas-ind-custom", "service_type": "SAAS", "sector": "INDUSTRY",
         "tier_code": "INDUSTRY_CUSTOM", "billing_unit": "MONTHLY",
         "amount": 0, "vat_rate": 0.1, "vat_included": False,
         "display_name": "산업 맞춤", "is_active": True},
    ]


def _base_store(quotes=None):
    return {
        "price_master": _price_master_rows(),
        "quotes": list(quotes or []),
        # role_data_scope: COMPANY tier default → 회사 강제
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "002", "scope_type": "COMPANY"},
        ],
        "factories": [],
    }


def _company_user(company_id="C-A", uid="U-A", role_code="002"):
    return {"id": uid, "company_id": company_id, "role_code": role_code,
            "factory_id": None, "team_id": None}


def _no_company_user(uid="U-N", role_code="002"):
    return {"id": uid, "company_id": None, "role_code": role_code,
            "factory_id": None, "team_id": None}


# ── client factory ──────────────────────────────────────────────────
def _client(current_user, store):
    app = FastAPI()
    app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    mq.get_supabase = lambda: fake   # 라우터 모듈 레벨 이름 대체
    c = TestClient(app)
    c._fake = fake
    return c


# ────────────────────────────────────────────────────────────────────
# service 단위 — 계산 정확성 (T4~T11)
# ────────────────────────────────────────────────────────────────────
def test_T4_unit_amount_saas_ind_business():
    fake = FakeSupabase(_base_store())
    c = svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_BUSINESS", 1)
    assert c["unit_amount"] == 299000
    assert c["billing_unit"] == "MONTHLY"
    assert c["term_months"] == 1


def test_T6_saas_12_month_totals():
    fake = FakeSupabase(_base_store())
    c = svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_BUSINESS", 12)
    assert c["supply_amount"] == 3_588_000
    assert c["vat_amount"] == 358_800
    assert c["total_amount"] == 3_946_800
    assert c["quantity"] == 12


def test_T7_diagnosis_once_starter():
    fake = FakeSupabase(_base_store())
    c = svc.calc_quote(fake, "DIAGNOSIS", "INDUSTRY", "INDUSTRY_STARTER", None)
    assert c["quantity"] == 1
    assert c["term_months"] is None
    assert c["supply_amount"] == 149_000
    assert c["vat_amount"] == 14_900
    assert c["total_amount"] == 163_900


def test_T8_custom_amount_zero_raises_409():
    fake = FakeSupabase(_base_store())
    with pytest.raises(svc.MemberQuoteError) as e:
        svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_CUSTOM", 12)
    assert e.value.code == "CUSTOM_QUOTE_REQUIRED"
    assert e.value.http_status == 409


def test_T9_missing_tier_raises_404():
    fake = FakeSupabase(_base_store())
    with pytest.raises(svc.MemberQuoteError) as e:
        svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_FAKE", 12)
    assert e.value.code == "PRICE_NOT_FOUND"
    assert e.value.http_status == 404


def test_T10_vat_rate_from_row_not_hardcoded():
    """price_master.vat_rate 를 그대로 사용해야 한다. 하드코딩 10% 미사용."""
    store = _base_store()
    # vat_rate 를 0.05 로 조작 → 계산도 0.05 를 따라야 정상
    store["price_master"][0]["vat_rate"] = 0.05
    fake = FakeSupabase(store)
    c = svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_BUSINESS", 12)
    assert c["vat_rate"] == 0.05
    assert c["vat_amount"] == round(3_588_000 * 0.05)      # 179400
    assert c["vat_amount"] == 179_400
    assert c["total_amount"] == 3_588_000 + 179_400


def test_T11_total_equals_supply_plus_vat():
    fake = FakeSupabase(_base_store())
    for tier, st, months in [("INDUSTRY_BUSINESS", "SAAS", 12),
                              ("INDUSTRY_STARTER", "DIAGNOSIS", None)]:
        c = svc.calc_quote(fake, st, "INDUSTRY", tier, months)
        assert c["total_amount"] == c["supply_amount"] + c["vat_amount"]


def test_service_saas_requires_term_months():
    """term_months 미제공 SaaS → 422 TERM_REQUIRED (서비스 계약)."""
    fake = FakeSupabase(_base_store())
    with pytest.raises(svc.MemberQuoteError) as e:
        svc.calc_quote(fake, "SAAS", "INDUSTRY", "INDUSTRY_BUSINESS", None)
    assert e.value.code == "TERM_REQUIRED"
    assert e.value.http_status == 422


# ────────────────────────────────────────────────────────────────────
# router endpoint — 인증/소유권/필터 (T1~T3, T5, T12~T18)
# ────────────────────────────────────────────────────────────────────
@requires_client
def test_T1_no_auth_returns_401():
    """dependency_overrides 미주입 → get_current_user 실 401 코드 경로 실행."""
    app = FastAPI()
    app.include_router(mq.router)
    fake = FakeSupabase(_base_store())
    mq.get_supabase = lambda: fake
    c = TestClient(app)
    r = c.get("/me/quotes")
    assert r.status_code == 401


@requires_client
def test_T2_no_company_user_auto_returns_403():
    store = _base_store()
    c = _client(_no_company_user(), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 403


@requires_client
def test_T3_body_company_id_is_ignored_server_uses_token_company():
    """body 에 타사 company_id 를 주입해도 서버는 토큰 회사로 저장 (body에 그 필드 자체가 없음 계약)."""
    store = _base_store()
    c = _client(_company_user("C-TOKEN", "U-1"), store)
    # 실 스키마에 company_id 필드가 없어 무시됨 (extra 무시). 저장은 토큰 회사로.
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
        "company_id": "C-OTHER",   # 무시 대상 (schema 밖)
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["company_id"] == "C-TOKEN"


@requires_client
def test_T5_client_forged_total_is_ignored_server_recalculates():
    store = _base_store()
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
        "total_amount": 1,        # 위조 시도 (extra ignored)
        "supply_amount": 1,
        "vat_amount": 0,
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["supply_amount"] == 3_588_000
    assert data["vat_amount"] == 358_800
    assert data["total_amount"] == 3_946_800


@requires_client
def test_T8_router_custom_409_route_to_custom_true():
    store = _base_store()
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_CUSTOM", "term_months": 12,
    })
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "CUSTOM_QUOTE_REQUIRED"
    assert body["detail"]["route_to_custom"] is True


@requires_client
def test_T12_T13_list_scoped_to_own_company():
    """A 회사 사용자에게는 A 회사 견적만 노출 (B 회사 미노출)."""
    store = _base_store()
    c_a = _client(_company_user("C-A", "U-A"), store)
    # A 회사 발행
    r = c_a.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200
    a_qid = r.json()["data"]["id"]
    # B 회사 발행 (같은 store 사용)
    c_b = _client(_company_user("C-B", "U-B"), store)
    r = c_b.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200

    # A 회사 목록 → A 견적만
    la = c_a.get("/me/quotes").json()["data"]
    assert la["total"] == 1
    assert la["items"][0]["id"] == a_qid
    # B 회사 목록 → B 견적만 (A 미노출)
    lb = c_b.get("/me/quotes").json()["data"]
    assert lb["total"] == 1
    assert lb["items"][0]["id"] != a_qid


@requires_client
def test_T14_cross_company_detail_returns_404_hides_existence():
    """B 사가 A 사 quote_id 로 상세 조회 → 404 (존재 은닉)."""
    store = _base_store()
    c_a = _client(_company_user("C-A", "U-A"), store)
    r = c_a.post("/me/quotes/auto", json={
        "service_type": "DIAGNOSIS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_STARTER",
    })
    a_qid = r.json()["data"]["id"]
    c_b = _client(_company_user("C-B", "U-B"), store)
    r = c_b.get(f"/me/quotes/{a_qid}")
    assert r.status_code == 404


@requires_client
def test_T15_created_by_equals_current_user_id():
    store = _base_store()
    c = _client(_company_user("C-A", "U-alice"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "DIAGNOSIS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_STARTER",
    })
    assert r.status_code == 200
    assert r.json()["data"]["created_by"] == "U-alice"


@requires_client
def test_T16_survey_web_source_is_not_in_member_list():
    """/me/quotes 는 source in (member_auto, member_custom) 만. survey_web 미노출."""
    store = _base_store([{
        "id": "q-survey-1", "quote_no": "QT-SURVEY", "company_id": "C-A",
        "source": "survey_web", "status_code": "ISSUED",
        "service_type": "SAAS", "items": [],
        "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
        "created_by": "U-A", "created_at": "2026-01-01T00:00:00",
    }])
    c = _client(_company_user("C-A", "U-A"), store)
    r = c.get("/me/quotes")
    data = r.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


@requires_client
def test_T17_T18_member_sources_are_listed():
    """member_auto + member_custom 모두 노출. survey_web 만 배제 확인."""
    store = _base_store([
        {"id": "q-survey", "quote_no": "QT-SURVEY", "company_id": "C-A",
         "source": "survey_web", "status_code": "ISSUED", "service_type": "SAAS",
         "items": [], "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
         "created_by": "U-A", "created_at": "2026-01-01T00:00:00"},
    ])
    c = _client(_company_user("C-A", "U-A"), store)
    # auto
    c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 6,
    })
    # custom
    r = c.post("/me/quotes/custom", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "request_title": "맞춤 상담", "request_detail": "내부 검토 부탁",
    })
    assert r.status_code == 200
    assert r.json()["data"]["source"] == "member_custom"
    assert r.json()["data"]["total_amount"] == 0
    # 목록 : 2건(auto+custom), survey_web 배제
    lst = c.get("/me/quotes").json()["data"]
    assert lst["total"] == 2
    sources = sorted(it["source"] for it in lst["items"])
    assert sources == ["member_auto", "member_custom"]


# ────────────────────────────────────────────────────────────────────
# 회귀 (REG) — 기존 /quotes 라우터 무접촉 확인
# ────────────────────────────────────────────────────────────────────
def test_REG_legacy_quotes_router_module_intact():
    """/quotes/survey 등 legacy 라우터 파일은 변경 없이 import 가능해야 한다."""
    import routers.quotes as legacy
    assert legacy.router.prefix == "/quotes"
    # 신규 라우터 접두는 별개 (분리 보장)
    assert mq.router.prefix == "/me/quotes"


def test_REG_registry_line_present():
    """router_registry/payment.py 에 신규 라우터 등록이 존재 (order/의존 유지)."""
    import router_registry.payment as rp
    modules = [r.get("module") for r in rp.ROUTERS]
    assert "routers.member_quotes" in modules
    # 기존 라우터 순서 유지 (quotes → member_quotes → price_setting)
    idx = modules.index("routers.member_quotes")
    assert modules[idx - 1] == "routers.quotes"
    assert modules[idx + 1] == "routers.price_setting"
