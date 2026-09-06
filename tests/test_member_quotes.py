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


def _base_store(quotes=None, companies=None):
    return {
        "price_master": _price_master_rows(),
        "quotes": list(quotes or []),
        # role_data_scope: COMPANY tier default → 회사 강제. ALL 은 별도 명시.
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "002", "scope_type": "COMPANY"},
        ],
        "companies": list(companies or []),
        "factories": [],
        # contracts / payments : REV-1 PURPOSE-3/4 write=0 관측용
        "contracts": [],
        "payments": [],
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


# ══════════════════════════════════════════════════════════════════
# STEP 2A REV-1 : 3 보정 (quote_no atomic retry · /me strict · company_name snapshot)
# ══════════════════════════════════════════════════════════════════
class _RaiseNTimesFake(FakeSupabase):
    """quotes insert 첫 N회에 지정 예외 raise. 그 외 정상. 다른 테이블은 정상."""
    def __init__(self, store, target_table, exc, n=1):
        super().__init__(store)
        self._target = target_table
        self._exc = exc
        self._remaining = int(n)
        self.attempts = 0     # target insert 시도 카운트 (성공 포함)

    def table(self, name):
        q = super().table(name)
        if name != self._target:
            return q
        orig_execute = q.execute

        def exec2():
            if q._op == "insert":
                self.attempts += 1
                if self._remaining > 0:
                    self._remaining -= 1
                    raise self._exc
            return orig_execute()
        q.execute = exec2
        return q


def _mk_uniq_exc(constraint="quotes_quote_no_key"):
    """Postgres UNIQUE 위반 유사 예외 (code=23505, constraint 문자열 포함)."""
    e = Exception('duplicate key value violates unique constraint "{}"'.format(constraint))
    e.code = "23505"
    e.constraint = constraint
    return e


# ── REV-1 PURPOSE (내부결재 첨부 문서 · contracts/payments write 0) ─────
@requires_client
def test_REV1_PURPOSE1_auto_status_issued():
    store = _base_store(companies=[{"id": "C-A", "name": "TAI Corp"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200
    assert r.json()["data"]["status_code"] == "ISSUED"


@requires_client
def test_REV1_PURPOSE2_custom_status_requested():
    store = _base_store(companies=[{"id": "C-A", "name": "TAI Corp"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/custom", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "request_title": "맞춤 문의", "request_detail": "내부 검토 필요",
    })
    assert r.status_code == 200
    assert r.json()["data"]["status_code"] == "REQUESTED"
    assert r.json()["data"]["total_amount"] == 0


@requires_client
def test_REV1_PURPOSE3_auto_no_contract_no_payment_write():
    store = _base_store(companies=[{"id": "C-A", "name": "TAI Corp"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "DIAGNOSIS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_STARTER",
    })
    assert r.status_code == 200
    assert store["contracts"] == []      # contract write 0
    assert store["payments"] == []       # payment write 0
    # supabase log 로도 이중 확인 : contracts/payments insert 로그 부재
    assert not any(t == "contracts" and op == "insert" for (t, op) in c._fake.log)
    assert not any(t == "payments" and op == "insert" for (t, op) in c._fake.log)


@requires_client
def test_REV1_PURPOSE4_custom_no_contract_no_payment_write():
    store = _base_store(companies=[{"id": "C-A", "name": "TAI Corp"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/custom", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "request_title": "맞춤", "request_detail": "",
    })
    assert r.status_code == 200
    assert store["contracts"] == []
    assert store["payments"] == []


# ── REV-1 COMPANY (/me strict — ALL 이라도 자사만) ────────────────────
@requires_client
def test_REV1_COMPANY1_no_company_auto_403():
    store = _base_store()
    c = _client(_no_company_user(), store)   # role=002 (COMPANY), company_id=None
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 403


@requires_client
def test_REV1_COMPANY2_no_company_list_403():
    store = _base_store()
    c = _client(_no_company_user(), store)
    r = c.get("/me/quotes")
    assert r.status_code == 403


@requires_client
def test_REV1_COMPANY3_all_role_list_still_scoped_to_own():
    """관리자(ALL) 이라도 /me/quotes 는 자사만. B 사 quote 는 미노출."""
    store = _base_store([
        # B 사 quote 이미 존재
        {"id": "q-b", "quote_no": "QT-B", "company_id": "C-B",
         "source": "member_auto", "status_code": "ISSUED", "service_type": "SAAS",
         "items": [], "supply_amount": 0, "vat_amount": 0, "total_amount": 0,
         "created_by": "U-B", "created_at": "2026-01-01T00:00:00"},
    ], companies=[{"id": "C-A", "name": "A"}, {"id": "C-B", "name": "B"}])
    # ALL user 인데 자기 회사는 C-A
    all_user = {"id": "U-admin", "company_id": "C-A", "role_code": "001",
                "factory_id": None, "team_id": None}
    c = _client(all_user, store)
    r = c.get("/me/quotes")
    assert r.status_code == 200
    data = r.json()["data"]
    assert all(it["id"] != "q-b" for it in data["items"])   # B 사 미노출
    # (C-A 사 quote 는 아직 없으므로 목록은 비어있어야 함)
    assert data["total"] == 0


@requires_client
def test_REV1_COMPANY4_all_role_detail_cross_company_404():
    """ALL user 라도 다른 회사 quote_id 상세 조회 시 404 (존재 은닉)."""
    store = _base_store([
        {"id": "q-b-1", "quote_no": "QT-B-1", "company_id": "C-B",
         "source": "member_auto", "status_code": "ISSUED", "service_type": "SAAS",
         "items": [], "supply_amount": 0, "vat_amount": 0, "total_amount": 0,
         "created_by": "U-B", "created_at": "2026-01-01T00:00:00"},
    ], companies=[{"id": "C-A", "name": "A"}, {"id": "C-B", "name": "B"}])
    all_user = {"id": "U-admin", "company_id": "C-A", "role_code": "001",
                "factory_id": None, "team_id": None}
    c = _client(all_user, store)
    r = c.get("/me/quotes/q-b-1")
    assert r.status_code == 404


# ── REV-1 COMPANY-5 : company_name snapshot ──────────────────────────
@requires_client
def test_REV1_COMPANY5_company_name_snapshot():
    store = _base_store(companies=[{"id": "C-A", "name": "정식법인명 주식회사"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200
    assert r.json()["data"]["company_name"] == "정식법인명 주식회사"

    # 이후 companies.name 을 바꿔도 저장된 quote 는 불변 (snapshot 계약)
    for row in store["companies"]:
        if row["id"] == "C-A":
            row["name"] = "이름 바뀐 회사"
    stored = store["quotes"][-1]
    assert stored["company_name"] == "정식법인명 주식회사"   # 스냅샷 유지


# ── REV-1 SNAPSHOT-1 : price_master.amount 변경 후 기존 quote 불변 ────
@requires_client
def test_REV1_SNAPSHOT1_price_master_change_does_not_affect_existing_quote():
    store = _base_store(companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A", "U-1"), store)
    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200
    qid = r.json()["data"]["id"]
    # 발급 후 price_master.amount 를 임의 변경
    for row in store["price_master"]:
        if row["tier_code"] == "INDUSTRY_BUSINESS":
            row["amount"] = 999_999
    # 저장된 quote 는 발급 당시 스냅샷 그대로
    stored = next(q for q in store["quotes"] if q["id"] == qid)
    assert stored["total_amount"] == 3_946_800
    assert stored["items"][0]["unit_amount"] == 299_000
    item = stored["items"][0]
    # 발급 당시 금액 4종 불변 (price_master.amount=999_999 변경 후에도)
    assert item["unit_amount"]   == 299_000
    assert item["supply_amount"] == 3_588_000
    assert item["vat_amount"]    == 358_800
    assert item["total_amount"]  == 3_946_800
    # 상위 row 금액 == item snapshot 금액 (정본 일치)
    assert stored["vat_amount"]   == item["vat_amount"]
    assert stored["total_amount"] == item["total_amount"]


# ── REV-1 QNO : quote_no atomic retry ───────────────────────────────
@requires_client
def test_REV1_QNO1_unique_conflict_retries_then_succeeds():
    """첫 INSERT 는 quote_no UNIQUE 위반 → 새 번호로 재시도 → 성공(attempts>=2)."""
    store = _base_store(companies=[{"id": "C-A", "name": "TAI"}])
    fake = _RaiseNTimesFake(store, "quotes", _mk_uniq_exc(), n=1)
    # _client 대신 직접 override (RaiseFake 주입)
    app = FastAPI()
    app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: _company_user("C-A", "U-1")
    mq.get_supabase = lambda: fake
    c = TestClient(app)

    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 200
    assert fake.attempts >= 2, "실 INSERT 에서 재시도가 일어나야 한다 (attempts={})".format(fake.attempts)
    # 성공한 quote 는 새 번호로 저장
    saved = store["quotes"][-1]
    assert saved["quote_no"].startswith("QT-")


@requires_client
def test_REV1_QNO2_retry_exhausted_returns_controlled_503():
    """5회 UNIQUE 충돌 → controlled MemberQuoteError(503) — 무한루프·raw 예외 없음."""
    store = _base_store(companies=[{"id": "C-A", "name": "TAI"}])
    fake = _RaiseNTimesFake(store, "quotes", _mk_uniq_exc(), n=99)   # 항상 충돌

    app = FastAPI()
    app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: _company_user("C-A", "U-1")
    mq.get_supabase = lambda: fake
    c = TestClient(app)

    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["code"] == "QUOTE_NO_CONFLICT"
    assert fake.attempts == 5   # 정확히 5회 시도 후 중단


@requires_client
def test_REV1_QNO3_non_quote_no_error_is_not_retried():
    """quote_no 외 오류(다른 23505 · FK 등)는 즉시 전파 (retry 없음)."""
    store = _base_store(companies=[{"id": "C-A", "name": "TAI"}])
    other_exc = Exception('duplicate key value violates unique constraint "some_other_key"')
    other_exc.code = "23505"
    other_exc.constraint = "some_other_key"
    fake = _RaiseNTimesFake(store, "quotes", other_exc, n=99)

    app = FastAPI()
    app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: _company_user("C-A", "U-1")
    mq.get_supabase = lambda: fake
    c = TestClient(app, raise_server_exceptions=False)   # 원 예외 → 500 response

    r = c.post("/me/quotes/auto", json={
        "service_type": "SAAS", "sector": "INDUSTRY",
        "tier_code": "INDUSTRY_BUSINESS", "term_months": 12,
    })
    # 원 예외 전파(200 아님) + 재시도 0 (attempts == 1). QUOTE_NO_CONFLICT 로 변환되면 안 됨.
    assert r.status_code == 500
    assert fake.attempts == 1, "quote_no 외 오류는 재시도 금지 (attempts={})".format(fake.attempts)


# ── REV-1 helper 유닛 ─────────────────────────────────────────────────
def test_REV1_conflict_detector_only_matches_quote_no_key():
    """`_is_quote_no_conflict` : 23505 + (quotes_quote_no_key | quote_no) 조건만 True."""
    yes = _mk_uniq_exc("quotes_quote_no_key")
    assert svc._is_quote_no_conflict(yes) is True

    other = Exception('duplicate key value violates unique constraint "another_uniq"')
    other.code = "23505"; other.constraint = "another_uniq"
    assert svc._is_quote_no_conflict(other) is False   # 23505 지만 quote_no 아님

    fk = Exception('foreign key violation'); fk.code = "23503"
    assert svc._is_quote_no_conflict(fk) is False

    generic = RuntimeError("boom")
    assert svc._is_quote_no_conflict(generic) is False


def test_REV1_company_name_snapshot_none_when_no_row():
    """companies 에 회사가 없으면 None (best-effort). 발급 자체는 막지 않음."""
    fake = FakeSupabase(_base_store())   # companies 비어있음
    assert svc._company_name_snapshot(fake, "C-MISSING") is None
    assert svc._company_name_snapshot(fake, None) is None
    assert svc._company_name_snapshot(fake, "") is None
