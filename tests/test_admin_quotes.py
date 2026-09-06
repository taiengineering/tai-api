"""STEP 2D-A /admin/quotes 관리자 견적 백엔드 — service + router 단위테스트.

WO-MYPAGE-QUOTE-PROCESS-001 STEP 2D-A. FakeSupabase(quotes/companies/documents/role_data_scope)
+ 실 DB / 네트워크 불사용. member_auto 회귀 diff = 0 (기존 test_member_quotes.py 전량 GREEN 조건).

케이스 매트릭스 (A-01 ~ A-63 + INV static grep):
  AUTH        A-01 401  A-02 non-admin 403  A-03 admin 200
  LIST        A-04 ADMIN_SOURCES 포함 · survey_web 제외
              A-05 source=member_auto 필터
              A-06 source=admin_manual 필터
              A-07 status_code=REQUESTED 필터
              A-08 search quote_no 부분
              A-09 search company_name 부분
              A-10 search contact_name 부분
              A-11 페이지네이션 · order desc
              A-12 legacy source(survey_web) 목록 부재
  DETAIL      A-13 admin_manual 상세
              A-14 member_custom REQUESTED 상세 + requested_at
              A-15 member_custom ISSUED 상세 + requested_at & issued_at
              A-16 member_auto 상세 + issued_at=created_at
              A-17 survey_web / 미존재 → 404
  MANUAL CALC A-18 MONTHLY 계산(supply=ua*m, vat=round(supply*vr), total)
              A-19 ONCE 계산(supply=ua*q)
              A-20 vat_rate=0.05 반영
              A-21 unit_amount<=0 → 422 INVALID_UNIT_AMOUNT
              A-22 vat_rate 범위 위반 → 422 INVALID_VAT_RATE
              A-23 MONTHLY term<1 → 422 TERM_REQUIRED
              A-24 ONCE quantity<1 → 422 QUANTITY_REQUIRED
              A-25 미지원 billing_unit → 422
              A-26 item shape (member_auto 와 key 동일)
              A-27 sector/service_type 대문자 정규화
  MANUAL PREVIEW  A-28 write=0(quotes insert 0) · pdf=0(quotes/documents insert 0)
                  A-29 응답 company_name snapshot + contact normalized echo
                  A-30 quote_no 발급 없음(응답에 quote_no 부재)
                  A-31 company_id 없으면 422
  MANUAL ISSUE    A-32 source=admin_manual · status=ISSUED · created_by=admin
                  A-33 quote_no 발급 · items=1 · 3금액 = item 3금액
                  A-34 company_name snapshot 저장
                  A-35 contact_name 정규화 저장(공백 → NULL)
                  A-36 client supply/vat/total 위조 무시 (body에 그 필드 없음 — 계약)
                  A-37 non-admin 이면 403 (write 0)
                  A-38 company_id 없으면 422
                  A-39 unit_amount<=0 이면 422 + write 0
                  A-40 vat_rate 응답 기록 확인 (item.vat_rate = 요청 vr)
  CUSTOM PREVIEW  A-41 REQUESTED 만 · ISSUED / member_auto → 409
                  A-42 write=0 · row 필드 immutable
                  A-43 sector fallback = survey_data.member_custom.sector
                  A-44 service_type fallback = 기존 row.service_type
                  A-45 non-admin 403 (write 0)
  CUSTOM ISSUE    A-46 REQUESTED → ISSUED (same-row)
                  A-47 quote_no 보존
                  A-48 company_id / company_name 보존
                  A-49 contact_name 보존(원래 값)
                  A-50 survey_data 보존
                  A-51 created_at 보존 (issue 후에도 원래 값)
                  A-52 updated_at 갱신
                  A-53 items 갱신 · 상위 3금액 = item 3금액
                  A-54 status_code = ISSUED
                  A-55 member_auto 대상 issue → 409 (NOT_CUSTOM_REQUESTED)
                  A-56 없는 id → 404
  DOUBLE ISSUE    A-57 2회째 issue → 409 QUOTE_ALREADY_ISSUED · row mutation 0
  PDF ELIG        A-58 member_auto ISSUED → 통과
                  A-59 admin_manual ISSUED → 통과
                  A-60 member_custom ISSUED → 통과
                  A-61 member_custom REQUESTED → 409 PDF_NOT_AVAILABLE
                       + survey_web ISSUED → 409 (source 미지원)
  PDF DATE        A-62 auto/manual = created_at / custom_issued = updated_at
  ADMIN PDF AUTH  A-63 non-admin PDF endpoint 403 (write 0)

INV static (routers/admin_quotes.py 소스 grep) : PENDING_PAYMENT / CONFIRMED / APPROVED /
  CONTRACT_CREATED / *_APPROVAL / contracts.insert / contact_phone / contact_email = 0
"""
from __future__ import annotations

import os
import uuid

import pytest

# main 로드 시 필요한 최소 env
os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.admin_quotes as aq
from services import admin_quote_svc as svc
from services import member_quote_svc as mq_svc

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


# ── FakeSupabase (in-memory, chainable · update+eq chain 지원) ────────
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


# ── Fixtures ─────────────────────────────────────────────────────────
# PATCH-1 : _require_company_name 이 재조회를 강제하므로 기본 store 에 C-A 회사 포함.
#   companies 를 명시 지정한 테스트는 override(기존 동작 유지).
_DEFAULT_COMPANIES = [{"id": "C-A", "name": "A사"}]


def _base_store(quotes=None, companies=None):
    return {
        "quotes": list(quotes or []),
        # ALL=관리자, COMPANY=일반 회원 (member_quotes 관례 재사용)
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "002", "scope_type": "COMPANY"},
        ],
        "companies": list(companies) if companies is not None else list(_DEFAULT_COMPANIES),
        "factories": [],
    }


def _admin_user(uid="U-ADMIN"):
    # role_code=001 → scope ALL → _require_admin 통과
    return {"id": uid, "company_id": None, "role_code": "001", "factory_id": None, "team_id": None}


def _non_admin_user(uid="U-NON", company_id="C-X"):
    return {"id": uid, "company_id": company_id, "role_code": "002",
            "factory_id": None, "team_id": None}


def _client(current_user, store):
    app = FastAPI()
    app.include_router(aq.router)
    app.dependency_overrides[aq.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    aq.get_supabase = lambda: fake   # 라우터 모듈 레벨 이름 대체
    c = TestClient(app)
    c._fake = fake
    return c


def _member_auto_quote(company_id="C-A", **over):
    q = {
        "id": "q-auto-1", "quote_no": "QT-20260906-AUTO",
        "company_id": company_id, "company_name": "A사",
        "source": "member_auto", "status_code": "ISSUED",
        "service_type": "SAAS", "contact_name": "홍길동",
        "items": [{"display_name": "산업 비즈니스", "billing_unit": "MONTHLY",
                   "unit_amount": 299000, "term_months": 12, "quantity": 12,
                   "supply_amount": 3_588_000, "vat_rate": 0.1,
                   "vat_amount": 358_800, "total_amount": 3_946_800,
                   "service_type": "SAAS", "sector": "INDUSTRY",
                   "tier_code": "INDUSTRY_BUSINESS", "price_id": "pm-1"}],
        "supply_amount": 3_588_000, "vat_amount": 358_800, "total_amount": 3_946_800,
        "created_by": "U-A", "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "is_active": True,
    }
    q.update(over); return q


def _member_custom_requested(company_id="C-A", **over):
    q = {
        "id": "q-custom-1", "quote_no": "QT-20260906-CUSTOM",
        "company_id": company_id, "company_name": "A사",
        "source": "member_custom", "status_code": "REQUESTED",
        "service_type": "SAAS", "contact_name": "김담당",
        "items": [], "supply_amount": 0, "vat_amount": 0, "total_amount": 0,
        "survey_data": {"member_custom": {"sector": "INDUSTRY",
                                          "request_title": "다사업장 통합",
                                          "request_detail": "검토 부탁"}},
        "memo": "[개별견적] 다사업장 통합",
        "created_by": "U-A", "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "is_active": True,
    }
    q.update(over); return q


def _survey_web_quote(company_id="C-A", **over):
    q = {
        "id": "q-survey-1", "quote_no": "QT-SURVEY-1",
        "company_id": company_id, "company_name": "A사",
        "source": "survey_web", "status_code": "ISSUED",
        "service_type": "SAAS",
        "items": [], "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
        "created_by": "U-A", "created_at": "2026-08-01T00:00:00+00:00",
    }
    q.update(over); return q


# ════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A01_no_auth_returns_401():
    """의존성 오버라이드 없이 실제 get_current_user 경로가 401."""
    app = FastAPI()
    app.include_router(aq.router)
    fake = FakeSupabase(_base_store())
    aq.get_supabase = lambda: fake
    c = TestClient(app)
    r = c.get("/admin/quotes")
    assert r.status_code == 401


@requires_client
def test_A02_non_admin_returns_403():
    c = _client(_non_admin_user(), _base_store())
    r = c.get("/admin/quotes")
    assert r.status_code == 403


@requires_client
def test_A03_admin_can_list():
    c = _client(_admin_user(), _base_store())
    r = c.get("/admin/quotes")
    assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════
# LIST / DETAIL
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A04_admin_sources_included_survey_excluded():
    store = _base_store([
        _member_auto_quote(),
        _member_custom_requested(id="q-custom-2"),
        _survey_web_quote(),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes")
    data = r.json()["data"]
    sources = sorted([it["source"] for it in data["items"]])
    assert "survey_web" not in sources
    assert set(sources) == {"member_auto", "member_custom"}


@requires_client
def test_A05_list_filter_source_member_auto():
    store = _base_store([
        _member_auto_quote(),
        _member_custom_requested(id="q-c2"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?source=member_auto")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["source"] == "member_auto"


@requires_client
def test_A06_list_filter_source_admin_manual():
    store = _base_store([
        _member_auto_quote(),
        {**_member_auto_quote(id="q-manual-1", quote_no="QT-M", source="admin_manual"),
         "contact_name": None},
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?source=admin_manual")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["source"] == "admin_manual"


@requires_client
def test_A07_list_filter_status_requested():
    store = _base_store([
        _member_auto_quote(),
        _member_custom_requested(id="q-c2"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?status_code=REQUESTED")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["status_code"] == "REQUESTED"


@requires_client
def test_A08_search_quote_no_partial():
    store = _base_store([
        _member_auto_quote(quote_no="QT-20260906-AAAA"),
        _member_auto_quote(id="q-auto-2", quote_no="QT-20260906-BBBB", company_id="C-B", company_name="B사"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?search=AAAA")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["quote_no"] == "QT-20260906-AAAA"


@requires_client
def test_A09_search_company_name_partial():
    store = _base_store([
        _member_auto_quote(),
        _member_auto_quote(id="q-a2", quote_no="QT-B", company_id="C-B", company_name="ㅇㅇ주식회사"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?search=주식회사")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["company_name"] == "ㅇㅇ주식회사"


@requires_client
def test_A10_search_contact_name_partial():
    store = _base_store([
        _member_auto_quote(),
        _member_auto_quote(id="q-a2", quote_no="QT-B", contact_name="박담당"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?search=박담당")
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["contact_name"] == "박담당"


@requires_client
def test_A11_pagination_order_desc():
    quotes = [_member_auto_quote(id=f"q-{i}", quote_no=f"QT-{i:02d}",
                                 created_at=f"2026-09-{i:02d}T00:00:00+00:00")
              for i in range(1, 6)]
    store = _base_store(quotes)
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes?page=1&page_size=2")
    data = r.json()["data"]
    assert data["total"] == 5
    assert data["total_pages"] == 3
    # 최신순 desc → 첫 항목은 09-05
    assert data["items"][0]["quote_no"] == "QT-05"


@requires_client
def test_A12_survey_web_absent_from_list():
    store = _base_store([_survey_web_quote()])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes")
    assert r.json()["data"]["items"] == []


@requires_client
def test_A13_detail_admin_manual():
    store = _base_store([
        {**_member_auto_quote(id="q-m", quote_no="QT-M", source="admin_manual",
                              created_at="2026-09-01T00:00:00+00:00",
                              updated_at="2026-09-01T00:00:00+00:00")},
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes/q-m")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["source"] == "admin_manual"
    assert d.get("issued_at") == d.get("created_at")


@requires_client
def test_A14_detail_custom_requested_has_requested_at():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes/q-custom-1")
    d = r.json()["data"]
    assert d["source"] == "member_custom" and d["status_code"] == "REQUESTED"
    assert d.get("requested_at") == d.get("created_at")
    assert d.get("issued_at") is None


@requires_client
def test_A15_detail_custom_issued_has_both_dates():
    store = _base_store([
        _member_custom_requested(id="q-ci", status_code="ISSUED",
                                 updated_at="2026-09-05T12:00:00+00:00"),
    ])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes/q-ci")
    d = r.json()["data"]
    assert d.get("requested_at") == "2026-09-01T00:00:00+00:00"
    assert d.get("issued_at") == "2026-09-05T12:00:00+00:00"


@requires_client
def test_A16_detail_member_auto_has_issued_at():
    store = _base_store([_member_auto_quote()])
    c = _client(_admin_user(), store)
    r = c.get("/admin/quotes/q-auto-1")
    d = r.json()["data"]
    assert d.get("issued_at") == d.get("created_at")


@requires_client
def test_A17_detail_survey_or_missing_returns_404():
    store = _base_store([_survey_web_quote()])
    c = _client(_admin_user(), store)
    assert c.get("/admin/quotes/q-survey-1").status_code == 404       # source out of scope
    assert c.get("/admin/quotes/nope").status_code == 404              # 존재 없음


# ════════════════════════════════════════════════════════════════════
# MANUAL CALC (unit — 서비스 함수 직접 호출)
# ════════════════════════════════════════════════════════════════════
def test_A18_calc_monthly():
    it = svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "산업 프로", "MONTHLY", 12, None, 100000, 0.1)
    assert it["supply_amount"] == 1_200_000
    assert it["vat_amount"] == 120_000
    assert it["total_amount"] == 1_320_000
    assert it["quantity"] == 12 and it["term_months"] == 12


def test_A19_calc_once():
    it = svc.calc_manual_quote("DIAGNOSIS", "INDUSTRY", "T", "1회 진단", "ONCE", None, 3, 50000, 0.1)
    assert it["supply_amount"] == 150_000
    assert it["quantity"] == 3 and it["term_months"] is None


def test_A20_calc_vat_rate_reflected():
    it = svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "MONTHLY", 1, None, 100000, 0.05)
    assert it["vat_rate"] == 0.05
    assert it["vat_amount"] == 5000 and it["total_amount"] == 105_000


def test_A21_calc_unit_amount_zero_raises_422():
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "MONTHLY", 1, None, 0, 0.1)
    assert e.value.code == "INVALID_UNIT_AMOUNT" and e.value.http_status == 422


def test_A22_calc_vat_rate_out_of_range_422():
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "MONTHLY", 1, None, 100000, 1.5)
    assert e.value.code == "INVALID_VAT_RATE" and e.value.http_status == 422


def test_A23_calc_monthly_term_missing_422():
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "MONTHLY", 0, None, 100000, 0.1)
    assert e.value.code == "TERM_REQUIRED"


def test_A24_calc_once_quantity_missing_422():
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("DIAGNOSIS", "INDUSTRY", "T", "T", "ONCE", None, 0, 100000, 0.1)
    assert e.value.code == "QUANTITY_REQUIRED"


def test_A25_calc_unsupported_billing_unit_422():
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "YEARLY", 1, None, 100000, 0.1)
    assert e.value.code == "BILLING_UNIT_UNSUPPORTED"


def test_A26_calc_item_shape_matches_member_auto_keys():
    it = svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "T", "MONTHLY", 1, None, 100000, 0.1)
    expected_keys = {"price_id", "service_type", "sector", "tier_code", "display_name",
                     "billing_unit", "unit_amount", "term_months", "quantity",
                     "supply_amount", "vat_rate", "vat_amount", "total_amount"}
    assert expected_keys.issubset(set(it.keys()))


def test_A27_calc_normalizes_upper_service_and_sector():
    it = svc.calc_manual_quote("saas", "industry", "t", "T", "MONTHLY", 1, None, 100000, 0.1)
    assert it["service_type"] == "SAAS" and it["sector"] == "INDUSTRY"


# ════════════════════════════════════════════════════════════════════
# MANUAL PREVIEW (router)
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A28_manual_preview_no_write_no_pdf():
    store = _base_store()
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual/preview", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12,
        "unit_amount": 100000, "display_name": "산업 프로",
    })
    assert r.status_code == 200
    # quotes / documents insert 0
    assert not any(op == "insert" and t == "quotes" for (t, op) in c._fake.log)
    assert not any(op == "insert" and t == "documents" for (t, op) in c._fake.log)


@requires_client
def test_A29_manual_preview_echoes_company_snapshot_and_contact():
    store = _base_store(companies=[{"id": "C-A", "name": "A 주식회사"}])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual/preview", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12,
        "unit_amount": 100000, "contact_name": " 김담당 ", "display_name": "산업 프로",
    })
    d = r.json()["data"]
    assert d["company_name"] == "A 주식회사"
    assert d["contact_name"] == "김담당"


@requires_client
def test_A30_manual_preview_no_quote_no():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual/preview", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12,
        "unit_amount": 100000, "display_name": "산업 프로",
    })
    d = r.json()["data"]
    assert "quote_no" not in d


@requires_client
def test_A31_manual_preview_missing_company_id_422():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual/preview", json={
        "company_id": "", "billing_unit": "MONTHLY", "term_months": 12, "unit_amount": 100000,
    })
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
# MANUAL ISSUE (router)
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A32_manual_issue_source_status_created_by():
    store = _base_store(companies=[{"id": "C-A", "name": "A"}])
    c = _client(_admin_user(uid="U-ADMIN-2"), store)
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12, "unit_amount": 100000,
        "display_name": "산업 프로", "contact_name": "김담당",
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["source"] == "admin_manual"
    assert d["status_code"] == "ISSUED"
    assert d["created_by"] == "U-ADMIN-2"


@requires_client
def test_A33_manual_issue_quote_no_and_amount_snapshot():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12, "unit_amount": 100000,
        "display_name": "산업 프로",
    })
    d = r.json()["data"]
    assert d.get("quote_no", "").startswith("QT-")
    assert len(d["items"]) == 1
    it = d["items"][0]
    assert (d["supply_amount"], d["vat_amount"], d["total_amount"]) == \
           (it["supply_amount"], it["vat_amount"], it["total_amount"])


@requires_client
def test_A34_manual_issue_company_name_snapshot():
    store = _base_store(companies=[{"id": "C-A", "name": "테스트 주식회사"}])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12,
        "unit_amount": 100000, "display_name": "산업 프로",
    })
    assert r.json()["data"]["company_name"] == "테스트 주식회사"


@requires_client
def test_A35_manual_issue_contact_name_normalized_and_blank_null():
    c = _client(_admin_user(), _base_store())
    r1 = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 100000,
        "contact_name": " 이담당 ", "display_name": "T",
    })
    r2 = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 100000,
        "contact_name": "   ", "display_name": "T",
    })
    assert r1.json()["data"]["contact_name"] == "이담당"
    assert r2.json()["data"]["contact_name"] is None


@requires_client
def test_A36_manual_issue_ignores_client_forged_amounts():
    """body 스키마에 supply/vat/total 필드 없음 → extra ignored, 서버 재계산 결과만 저장."""
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 12, "unit_amount": 100000,
        "display_name": "산업 프로",
        "supply_amount": 1, "vat_amount": 1, "total_amount": 1,             # 위조 시도 (extra ignored)
    })
    d = r.json()["data"]
    assert d["supply_amount"] == 1_200_000
    assert d["vat_amount"] == 120_000
    assert d["total_amount"] == 1_320_000


@requires_client
def test_A37_manual_issue_non_admin_403_no_write():
    store = _base_store()
    c = _client(_non_admin_user(), store)
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 100000,
    })
    assert r.status_code == 403
    assert not any(op == "insert" and t == "quotes" for (t, op) in c._fake.log)


@requires_client
def test_A38_manual_issue_missing_company_id_422():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual", json={
        "company_id": "", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 100000,
    })
    # Pydantic accepts "" as str; svc raises COMPANY_REQUIRED 422 (or router 422)
    assert r.status_code == 422


@requires_client
def test_A39_manual_issue_zero_unit_amount_422_no_write():
    store = _base_store()
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 0,
    })
    assert r.status_code == 422
    assert not any(op == "insert" and t == "quotes" for (t, op) in c._fake.log)


@requires_client
def test_A40_manual_issue_vat_rate_recorded_in_item():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-A", "billing_unit": "MONTHLY", "term_months": 1, "unit_amount": 100000,
        "vat_rate": 0.05, "display_name": "T",
    })
    it = r.json()["data"]["items"][0]
    assert it["vat_rate"] == 0.05


# ════════════════════════════════════════════════════════════════════
# CUSTOM PREVIEW (router)
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A41_custom_preview_requires_requested():
    store = _base_store([
        _member_custom_requested(),                                          # REQUESTED (OK)
        _member_custom_requested(id="q-ci", status_code="ISSUED"),          # ISSUED (409)
        _member_auto_quote(),                                                # member_auto (409)
    ])
    c = _client(_admin_user(), store)
    body = {"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"}
    assert c.post("/admin/quotes/q-custom-1/custom/preview", json=body).status_code == 200
    assert c.post("/admin/quotes/q-ci/custom/preview", json=body).status_code == 409
    assert c.post("/admin/quotes/q-auto-1/custom/preview", json=body).status_code == 409


@requires_client
def test_A42_custom_preview_row_immutable_no_write():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    before = dict(store["quotes"][0])
    body = {"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"}
    c.post("/admin/quotes/q-custom-1/custom/preview", json=body)
    assert store["quotes"][0] == before
    assert not any(op == "update" and t == "quotes" for (t, op) in c._fake.log)
    assert not any(op == "insert" and t == "quotes" for (t, op) in c._fake.log)


@requires_client
def test_A43_custom_preview_sector_fallback_survey_data():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    body = {"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"}
    r = c.post("/admin/quotes/q-custom-1/custom/preview", json=body)
    it = r.json()["data"]["item"]
    assert it["sector"] == "INDUSTRY"  # survey_data.member_custom.sector 값


@requires_client
def test_A44_custom_preview_service_type_fallback_row():
    store = _base_store([_member_custom_requested()])   # service_type='SAAS'
    c = _client(_admin_user(), store)
    body = {"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"}
    r = c.post("/admin/quotes/q-custom-1/custom/preview", json=body)
    assert r.json()["data"]["item"]["service_type"] == "SAAS"


@requires_client
def test_A45_custom_preview_non_admin_403_no_write():
    store = _base_store([_member_custom_requested()])
    c = _client(_non_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/preview",
               json={"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"})
    assert r.status_code == 403
    assert not any(op == "update" and t == "quotes" for (t, op) in c._fake.log)


# ════════════════════════════════════════════════════════════════════
# CUSTOM ISSUE (router)
# ════════════════════════════════════════════════════════════════════
def _custom_issue_body(**over):
    body = {"billing_unit": "ONCE", "quantity": 1, "unit_amount": 100000, "display_name": "산업 상담"}
    body.update(over)
    return body


@requires_client
def test_A46_custom_issue_requested_to_issued_same_row():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["id"] == "q-custom-1"
    # store 실체 확인
    saved = store["quotes"][0]
    assert saved["id"] == "q-custom-1" and saved["status_code"] == "ISSUED"


@requires_client
def test_A47_custom_issue_quote_no_preserved():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0]["quote_no"] == "QT-20260906-CUSTOM"


@requires_client
def test_A48_custom_issue_company_preserved():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0]["company_id"] == "C-A"
    assert store["quotes"][0]["company_name"] == "A사"


@requires_client
def test_A49_custom_issue_contact_name_preserved():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0]["contact_name"] == "김담당"


@requires_client
def test_A50_custom_issue_survey_data_preserved():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    sd = store["quotes"][0]["survey_data"]["member_custom"]
    assert sd["sector"] == "INDUSTRY" and sd["request_title"] == "다사업장 통합"


@requires_client
def test_A51_custom_issue_created_at_preserved():
    store = _base_store([_member_custom_requested()])
    orig_created = store["quotes"][0]["created_at"]
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0]["created_at"] == orig_created


@requires_client
def test_A52_custom_issue_updated_at_advances():
    store = _base_store([_member_custom_requested()])
    orig_updated = store["quotes"][0]["updated_at"]
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0]["updated_at"] != orig_updated


@requires_client
def test_A53_custom_issue_items_and_top_amounts_reflect_calc():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/issue",
               json=_custom_issue_body(billing_unit="MONTHLY", term_months=6, unit_amount=200000, quantity=None))
    d = r.json()["data"]
    it = d["items"][0]
    assert it["supply_amount"] == 1_200_000
    assert (d["supply_amount"], d["vat_amount"], d["total_amount"]) == \
           (it["supply_amount"], it["vat_amount"], it["total_amount"])


@requires_client
def test_A54_custom_issue_status_becomes_issued():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert r.json()["data"]["status_code"] == "ISSUED"


@requires_client
def test_A55_custom_issue_on_member_auto_returns_409():
    store = _base_store([_member_auto_quote()])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-auto-1/custom/issue", json=_custom_issue_body())
    assert r.status_code == 409


@requires_client
def test_A56_custom_issue_missing_id_returns_404():
    c = _client(_admin_user(), _base_store())
    r = c.post("/admin/quotes/no-such/custom/issue", json=_custom_issue_body())
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# DOUBLE ISSUE
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A57_double_issue_returns_409_no_further_mutation():
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    # 1회 : 성공
    r1 = c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert r1.status_code == 200
    snapshot_after_first = dict(store["quotes"][0])
    # 2회 : 409, row 추가 mutation 없음
    r2 = c.post("/admin/quotes/q-custom-1/custom/issue",
                json=_custom_issue_body(unit_amount=999999))
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "QUOTE_ALREADY_ISSUED"
    assert store["quotes"][0] == snapshot_after_first


# ════════════════════════════════════════════════════════════════════
# PDF ELIGIBILITY (pdf_svc._validate_snapshot 확장분)
# ════════════════════════════════════════════════════════════════════
from services import member_quote_pdf_svc as pdf_svc


def _issued_shape(**over):
    """member_quote_pdf_v1 이 요구하는 최소 유효 snapshot."""
    q = {
        "id": "q", "company_id": "C", "quote_no": "QT-X", "company_name": "A",
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "source": "member_auto", "status_code": "ISSUED",
        "items": [{"display_name": "T", "billing_unit": "ONCE", "unit_amount": 100,
                   "quantity": 1, "supply_amount": 100, "vat_amount": 10, "total_amount": 110}],
        "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
    }
    q.update(over); return q


def test_A58_pdf_eligibility_member_auto_issued_passes():
    pdf_svc._validate_snapshot(_issued_shape())


def test_A59_pdf_eligibility_admin_manual_issued_passes():
    pdf_svc._validate_snapshot(_issued_shape(source="admin_manual"))


def test_A60_pdf_eligibility_member_custom_issued_passes():
    pdf_svc._validate_snapshot(_issued_shape(source="member_custom"))


def test_A61_pdf_eligibility_blocks_requested_and_unknown_source():
    with pytest.raises(pdf_svc.QuotePdfError) as e1:
        pdf_svc._validate_snapshot(_issued_shape(source="member_custom", status_code="REQUESTED"))
    assert e1.value.code == "PDF_NOT_AVAILABLE" and e1.value.http_status == 409

    with pytest.raises(pdf_svc.QuotePdfError) as e2:
        pdf_svc._validate_snapshot(_issued_shape(source="survey_web"))
    assert e2.value.code == "PDF_NOT_AVAILABLE"


# ════════════════════════════════════════════════════════════════════
# PDF DATE (auto=created / custom_issued=updated / manual=created)
# ════════════════════════════════════════════════════════════════════
def test_A62_pdf_date_source_split():
    ca = "2026-09-01T00:00:00+00:00"
    ua = "2026-09-05T00:00:00+00:00"
    # member_auto: created_at
    assert pdf_svc._quote_date_for_pdf({"source": "member_auto", "status_code": "ISSUED",
                                        "created_at": ca, "updated_at": ua}) == "2026-09-01"
    # admin_manual: created_at
    assert pdf_svc._quote_date_for_pdf({"source": "admin_manual", "status_code": "ISSUED",
                                        "created_at": ca, "updated_at": ua}) == "2026-09-01"
    # member_custom ISSUED: updated_at
    assert pdf_svc._quote_date_for_pdf({"source": "member_custom", "status_code": "ISSUED",
                                        "created_at": ca, "updated_at": ua}) == "2026-09-05"
    # member_custom ISSUED, updated_at 누락 → created_at fallback
    assert pdf_svc._quote_date_for_pdf({"source": "member_custom", "status_code": "ISSUED",
                                        "created_at": ca}) == "2026-09-01"


# ════════════════════════════════════════════════════════════════════
# ADMIN PDF AUTH
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_A63_admin_pdf_non_admin_403_no_write():
    store = _base_store([_member_auto_quote()])
    c = _client(_non_admin_user(), store)
    r = c.post("/admin/quotes/q-auto-1/pdf")
    assert r.status_code == 403
    assert not any(op == "insert" and t == "documents" for (t, op) in c._fake.log)


# ════════════════════════════════════════════════════════════════════
# INV static grep — routers/admin_quotes.py 소스 상 금지 상태/개념 부재
# ════════════════════════════════════════════════════════════════════
def test_INV_STATIC_no_forbidden_states_in_admin_router():
    """PENDING_PAYMENT/CONFIRMED/APPROVED/CONTRACT_CREATED/*_APPROVAL/
    contracts.insert/contact_phone/contact_email = 0."""
    import inspect
    src = inspect.getsource(aq)
    for tok in ("PENDING_PAYMENT", "CONFIRMED", "APPROVED", "CONTRACT_CREATED",
                "CUSTOMER_APPROVAL", "INTERNAL_APPROVAL",
                "contracts.insert", "contact_phone", "contact_email"):
        assert tok not in src, f"admin_quotes router 소스에 금지 토큰 '{tok}' 발견"


def test_INV_STATIC_no_forbidden_states_in_admin_svc():
    """svc 소스에도 동일 금지 토큰 부재."""
    import inspect
    src = inspect.getsource(svc)
    for tok in ("PENDING_PAYMENT", "CONFIRMED", "APPROVED", "CONTRACT_CREATED",
                "CUSTOMER_APPROVAL", "INTERNAL_APPROVAL",
                "contracts.insert", "contact_phone", "contact_email"):
        assert tok not in src, f"admin_quote_svc 소스에 금지 토큰 '{tok}' 발견"


def test_INV_STATIC_pdf_svc_eligibility_uses_three_sources_and_issued():
    import inspect
    src = inspect.getsource(pdf_svc._validate_snapshot)
    # 3소스 명시 + ISSUED 조건 존재
    for s in ("member_auto", "member_custom", "admin_manual", "ISSUED"):
        assert s in src, f"pdf_svc._validate_snapshot 에 '{s}' 명시 필수"


def test_INV_STATIC_pdf_svc_tag_source_aware():
    import inspect
    src = inspect.getsource(pdf_svc.issue_or_get_quote_pdf)
    assert 'quote.get("source")' in src, "tag 는 quote.source 기반이어야 한다"


def test_INV_STATIC_router_registry_has_admin_quotes():
    import router_registry.payment as rp
    modules = [r.get("module") for r in rp.ROUTERS]
    assert "routers.admin_quotes" in modules
    # 순서 : member_quotes 이후 (STEP 2A 뒤에 STEP 2D)
    i_m = modules.index("routers.member_quotes")
    i_a = modules.index("routers.admin_quotes")
    assert i_a == i_m + 1


# ════════════════════════════════════════════════════════════════════
# STEP 2D-A PATCH-1 : 3블로커 대응
#   블로커 1 : CustomIssueBody 에 service_type/sector 를 노출해서 관리자가
#              회원의 신청 컨텍스트를 임의로 갈아치울 수 있었음
#   블로커 2 : calc_manual_quote 가 display_name None/빈문자를 허용 → PDF 렌더 시
#              product_name 슬롯이 비어 나감(검증 실패 or 상품 불명 견적)
#   블로커 3 : manual issue/preview 가 존재하지 않는 company_id 로도 통과 → 이름 스냅샷 None,
#              custom issue 가 원래 row 의 company_name 이 None 인 채로 발행 가능
# ════════════════════════════════════════════════════════════════════
def test_P1_01_custom_issue_body_no_service_type_field():
    """블로커 1a : CustomIssueBody 에 service_type 필드 부재 (Pydantic 스키마)."""
    fields = set(aq.CustomIssueBody.model_fields.keys())
    assert "service_type" not in fields, \
        "CustomIssueBody 에 service_type 을 노출하면 안 된다 (관리자가 회원 컨텍스트 override 금지)"


def test_P1_02_custom_issue_body_no_sector_field():
    """블로커 1b : CustomIssueBody 에 sector 필드 부재 (Pydantic 스키마)."""
    fields = set(aq.CustomIssueBody.model_fields.keys())
    assert "sector" not in fields, \
        "CustomIssueBody 에 sector 를 노출하면 안 된다"


def test_P1_03_resolve_custom_context_service_type_from_row():
    """블로커 1c : _resolve_custom_context 는 row.service_type 만 사용 (body 인자 없음)."""
    row = {"service_type": "SAAS",
           "survey_data": {"member_custom": {"sector": "INDUSTRY"}}}
    st, sec = aq._resolve_custom_context(row)
    assert st == "SAAS"


def test_P1_04_resolve_custom_context_sector_from_survey_data():
    """블로커 1d : sector 는 survey_data.member_custom.sector 만."""
    row = {"service_type": "SAAS",
           "survey_data": {"member_custom": {"sector": "INDUSTRY"}}}
    _st, sec = aq._resolve_custom_context(row)
    assert sec == "INDUSTRY"
    # survey_data 없으면 None
    row2 = {"service_type": "SAAS"}
    _st2, sec2 = aq._resolve_custom_context(row2)
    assert sec2 is None


def test_P1_05_display_name_none_raises_422():
    """블로커 2a : calc_manual_quote(display_name=None) → 422 DISPLAY_NAME_REQUIRED."""
    with pytest.raises(svc.AdminQuoteError) as e:
        svc.calc_manual_quote("SAAS", "INDUSTRY", "T", None,
                              "MONTHLY", 1, None, 100000, 0.1)
    assert e.value.code == "DISPLAY_NAME_REQUIRED"
    assert e.value.http_status == 422


def test_P1_06_display_name_blank_raises_422():
    """블로커 2b : 빈문자/공백만인 display_name → 422."""
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(svc.AdminQuoteError) as e:
            svc.calc_manual_quote("SAAS", "INDUSTRY", "T", blank,
                                  "MONTHLY", 1, None, 100000, 0.1)
        assert e.value.code == "DISPLAY_NAME_REQUIRED", f"blank={blank!r}"


def test_P1_07_display_name_normalized_trim_preserves_middle():
    """블로커 2c : 저장 값은 trim (외곽 공백 제거, 내부 공백 보존)."""
    it = svc.calc_manual_quote("SAAS", "INDUSTRY", "T", "  산업 프로  ",
                               "MONTHLY", 1, None, 100000, 0.1)
    assert it["display_name"] == "산업 프로"


@requires_client
def test_P1_08_manual_preview_nonexistent_company_returns_404():
    """블로커 3a : preview 도 존재하지 않는 company_id 는 404 (재조회 강제)."""
    store = _base_store(companies=[])   # 빈 회사 리스트
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual/preview", json={
        "company_id": "C-NONE", "billing_unit": "MONTHLY", "term_months": 1,
        "unit_amount": 100000, "display_name": "T",
    })
    assert r.status_code == 404
    body = r.json()
    assert body["detail"]["code"] == "COMPANY_NOT_FOUND"


@requires_client
def test_P1_09_manual_issue_nonexistent_company_404_no_insert():
    """블로커 3b : issue 도 404 + quotes insert 0 (fail-closed)."""
    store = _base_store(companies=[])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/manual", json={
        "company_id": "C-NONE", "billing_unit": "MONTHLY", "term_months": 1,
        "unit_amount": 100000, "display_name": "T",
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "COMPANY_NOT_FOUND"
    assert not any(op == "insert" and t == "quotes" for (t, op) in c._fake.log)


def test_P1_10_require_company_name_helper():
    """블로커 3c : _require_company_name 헬퍼 계약."""
    # 미존재 → 404 COMPANY_NOT_FOUND
    fake_empty = FakeSupabase({"companies": []})
    with pytest.raises(svc.AdminQuoteError) as e:
        svc._require_company_name(fake_empty, "C-X")
    assert e.value.code == "COMPANY_NOT_FOUND" and e.value.http_status == 404
    # 존재 → 이름 반환
    fake_ok = FakeSupabase({"companies": [{"id": "C-A", "name": "A사"}]})
    assert svc._require_company_name(fake_ok, "C-A") == "A사"
    # 빈 이름 → 404
    fake_blank = FakeSupabase({"companies": [{"id": "C-B", "name": "  "}]})
    with pytest.raises(svc.AdminQuoteError) as e2:
        svc._require_company_name(fake_blank, "C-B")
    assert e2.value.code == "COMPANY_NOT_FOUND"


@requires_client
def test_P1_11_custom_issue_missing_company_name_returns_409():
    """블로커 3d : 원래 row 의 company_name 이 없으면 발행 금지 (409 QUOTE_SNAPSHOT_INCOMPLETE)."""
    row = _member_custom_requested()
    row["company_name"] = None
    store = _base_store([row])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QUOTE_SNAPSHOT_INCOMPLETE"


@requires_client
def test_P1_12_custom_issue_incomplete_snapshot_zero_mutation():
    """블로커 3e : 발행 실패 케이스에서 row 어떤 필드도 변경되지 않음."""
    row = _member_custom_requested()
    row["company_name"] = None
    store = _base_store([row])
    orig = dict(store["quotes"][0])
    c = _client(_admin_user(), store)
    c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert store["quotes"][0] == orig
    assert not any(op == "update" and t == "quotes" for (t, op) in c._fake.log)


@requires_client
def test_P1_13_conditional_update_still_works_after_patch():
    """정상 케이스 회귀 : PATCH-1 이후에도 REQUESTED→ISSUED same-row conditional UPDATE 정상."""
    store = _base_store([_member_custom_requested()])
    c = _client(_admin_user(), store)
    r = c.post("/admin/quotes/q-custom-1/custom/issue", json=_custom_issue_body())
    assert r.status_code == 200
    assert store["quotes"][0]["status_code"] == "ISSUED"
    assert store["quotes"][0]["quote_no"] == "QT-20260906-CUSTOM"


@requires_client
def test_P1_14_auth_and_pdf_eligibility_unchanged_after_patch():
    """회귀 : AUTH(non-admin 403) + PDF eligibility(3소스 + ISSUED) 그대로."""
    # AUTH
    c = _client(_non_admin_user(), _base_store())
    assert c.get("/admin/quotes").status_code == 403
    # PDF eligibility : admin_manual + ISSUED 유효
    pdf_svc._validate_snapshot({
        "id": "q", "company_id": "C", "quote_no": "QT", "company_name": "A",
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "source": "admin_manual", "status_code": "ISSUED",
        "items": [{"display_name": "T", "billing_unit": "ONCE", "unit_amount": 100,
                   "quantity": 1, "supply_amount": 100, "vat_amount": 10, "total_amount": 110}],
        "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
    })
    # member_custom + REQUESTED : 여전히 차단
    with pytest.raises(pdf_svc.QuotePdfError) as e:
        pdf_svc._validate_snapshot({
            "id": "q", "company_id": "C", "quote_no": "QT", "company_name": "A",
            "created_at": "2026-09-01T00:00:00+00:00",
            "updated_at": "2026-09-01T00:00:00+00:00",
            "source": "member_custom", "status_code": "REQUESTED",
            "items": [{"display_name": "T", "billing_unit": "ONCE", "unit_amount": 100,
                       "quantity": 1, "supply_amount": 100, "vat_amount": 10, "total_amount": 110}],
            "supply_amount": 100, "vat_amount": 10, "total_amount": 110,
        })
    assert e.value.code == "PDF_NOT_AVAILABLE"
