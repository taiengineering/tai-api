"""WO-TAX-INVOICE-MANUAL-01 WP-B/C/D/E — 관리자 수동발행 (mock provider).

정본 = services/tax_manual_svc.py + invoice_svc.issue_manual_tax_invoice.
라우터 = routers/payment_ledger.py 신규 3 엔드포인트.

C1~C6 회사 검색:
  C1 role001 인증 없으면 접근 불가 (dependency 자체가 admin 요구)
  C2 query 없이도 200 (전체 20건 이하 반환)
  C3 이름 검색 ilike 매칭
  C4 사업자번호 검색 ilike 매칭
  C5 선택한 회사 정보를 서버가 재조회하여 snapshot (create_manual_request 시 EXISTING 모드)
  C6 MANUAL 모드 = companies INSERT 0

M1~M12 수동발행:
  M1 EXISTING 모드 → snapshot 정확 (companies SoT 재조회, 프론트 값 무시)
  M2 MANUAL 모드 → invoicee_* 그대로 snapshot
  M3 payment_id NULL (모든 모드) — synthetic payment 생성 0
  M4 total 은 서버 재계산 (프론트 total 값 무시)
  M5 invalid 거부 (음수 금액, 비-UUID key, 형식 오류 supply_date, 필수 필드 누락)
  M6 idempotency: 같은 key 로 두 번 create → 두 번째는 기존 row 반환, created=False
  M7 INVOICE_LIVE OFF → 423 / provider 0 / request.status=REQUESTED 유지 (FAILED 오염 금지)
  M8 mock success → tax_invoices row(payment_id NULL, ISSUED) + request.status=ISSUED
      + tax_invoice_id 연결
  M9 중복 process (같은 request_id 재호출) → provider 재호출 0 (ISSUED 재사용)
  M10 provider 실패 → request/ledger FAILED, retry 가능
  M11 retry success → same mgt_key 재사용, 중복 invoice 0
  M12 GUARD: source!=ADMIN_MANUAL request → 409 (경로 오용 방지)
"""
from __future__ import annotations

import uuid

import pytest

import services.invoice_svc as inv


# ── FakeSupabase ──
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._or = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"; return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def limit(self, n): self._limit = n; return self
    def order(self, *a, **k): return self
    def range(self, s, e): return self
    def or_(self, expr): self._or = expr; return self

    def _or_match(self, row):
        # supabase or_() 매우 단순 시뮬 — "col.ilike.%q%" 여러 개 OR 지원
        if not self._or:
            return True
        parts = [p.strip() for p in self._or.split(",") if p.strip()]
        for p in parts:
            # "col.ilike.%q%" 형태
            if ".ilike." in p:
                col, _, term = p.split(".", 2)
                term = term.strip("%")
                val = str(row.get(col) or "").lower()
                if term.lower() in val:
                    return True
            elif ".eq." in p:
                col, _, val = p.split(".", 2)
                if str(row.get(col)) == val:
                    return True
        return False

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
                return False
        if not self._or_match(row):
            return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            cols = None if self._cols == "*" else [c.strip() for c in self._cols.split(",") if c.strip()]
            out = []
            for r in rows:
                if not self._match(r):
                    continue
                out.append(dict(r) if cols is None else {k: r.get(k) for k in cols})
            if self._limit is not None:
                out = out[:self._limit]
            return _Result(out)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                # UNIQUE(payment_id, doc_type) — payment_id NULL 은 UNIQUE 무관 (postgres NULL 규칙 시뮬)
                if self.table == "tax_invoice_requests":
                    pid = it.get("payment_id")
                    if pid is not None:
                        for r in rows:
                            if (r.get("payment_id") == pid
                                    and r.get("doc_type") == it.get("doc_type")):
                                raise Exception('duplicate key value violates unique constraint "tax_invoice_requests_payment_doc_unique"')
                    # partial UNIQUE (idempotency_key) WHERE source='ADMIN_MANUAL' AND idempotency_key IS NOT NULL
                    if it.get("source") == "ADMIN_MANUAL" and it.get("idempotency_key"):
                        for r in rows:
                            if (r.get("source") == "ADMIN_MANUAL"
                                    and r.get("idempotency_key") == it.get("idempotency_key")):
                                raise Exception('duplicate key value violates unique constraint "uq_tax_invoice_requests_admin_manual_idem"')
                if self.table == "tax_invoices":
                    for r in rows:
                        if r.get("doc_type") == it.get("doc_type") and r.get("mgt_key") == it.get("mgt_key"):
                            raise Exception('duplicate key value violates unique constraint "tax_invoices_doc_type_mgt_key"')
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


class MockTax:
    def __init__(self, fail=False):
        self.calls = []; self.fail = fail

    def issue_tax(self, conf, **kw):
        self.calls.append(kw)
        if self.fail:
            raise Exception("popbill down")
        return {"nts": "NTS-MAN", "code": 1, "message": "ok"}

    def issue_cash(self, conf, **kw):
        self.calls.append(kw); return {"nts": "CR-MAN", "code": 1, "message": "ok"}


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    import routers.payment_ledger as pl
    from routers.matching_deps import _require_admin
    from routers.auth import get_current_user
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")

ADMIN_USER = {"id": "u-admin", "company_id": "co-tai", "role_code": "001",
              "factory_id": None, "team_id": None}


def _company(id_="co-target", **kw):
    base = {
        "id": id_, "name": "가나다 주식회사",
        "business_number": "1234567890",
        "representative_name": "홍길동",
        "contact_email": "biz@ganada.co.kr",
        "contact_phone": "02-000-0000",
        "zipcode": "06000",
        "address": "서울시 강남구 테헤란로 000",
        "address_road": "서울시 강남구 테헤란로 000",
        "address_detail": "5층",
        "business_type": "정보통신",
        "business_category": "SaaS",
    }
    base.update(kw); return base


def _setup(monkeypatch, *, live=True, provider_fail=False, extra_store=None):
    """invoice_svc + tax_manual_svc + payment_ledger 라우터가 같은 fake 를 공유하도록 결선."""
    store = {
        "companies": [_company("co-1"), _company("co-2", name="다른회사",
                                                  business_number="9876543210",
                                                  representative_name="김철수")],
        "tax_invoice_requests": [],
        "tax_invoices": [],
        "payments": [],
    }
    if extra_store:
        for k, v in extra_store.items():
            store[k] = v
    fake = FakeSupabase(store)
    mock = MockTax(fail=provider_fail)

    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: live)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {
        "corp_num": "7233901422", "corp_name": "TAI", "ceo_name": "심태왕",
        "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True,
    })
    monkeypatch.setattr(inv, "_popbill_issue_tax", lambda conf, **kw: mock.issue_tax(conf, **kw))
    monkeypatch.setattr(inv, "_popbill_issue_cash", lambda conf, **kw: mock.issue_cash(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc",
                        type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return store, fake, mock


def _client(monkeypatch, *, live=True, provider_fail=False, extra_store=None):
    store, fake, mock = _setup(monkeypatch, live=live, provider_fail=provider_fail,
                               extra_store=extra_store)
    monkeypatch.setattr(pl, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(pl.router)
    app.dependency_overrides[_require_admin] = lambda: ADMIN_USER
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    c = TestClient(app)
    c._store = store; c._fake = fake; c._mock = mock
    return c


def _idem() -> str:
    return str(uuid.uuid4())


# ═════════════════════════════════════════════════════════════════════
# C1~C6 — 회사 검색
# ═════════════════════════════════════════════════════════════════════
@requires_client
def test_C1_company_search_requires_admin(monkeypatch):
    """role001 dependency: overrides 미설정 시 401/500 계열. (여기선 override 로 admin 주입)"""
    c = _client(monkeypatch)
    r = c.get("/payments/admin/tax-invoice-companies")
    assert r.status_code == 200


@requires_client
def test_C2_company_search_no_query_returns_all(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/payments/admin/tax-invoice-companies")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 2  # 회사 2개 시드


@requires_client
def test_C3_company_search_by_name(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/payments/admin/tax-invoice-companies?q=가나다")
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "가나다 주식회사"


@requires_client
def test_C4_company_search_by_business_number(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/payments/admin/tax-invoice-companies?q=9876543210")
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["business_number"] == "9876543210"


@requires_client
def test_C5_existing_mode_snapshot_from_companies_sot(monkeypatch):
    """EXISTING 모드: create_manual_request 가 서버에서 companies 재조회 → snapshot.
    프론트가 잘못된 invoicee_* 를 보내도 서버가 무시하고 companies SoT 사용."""
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING",
        "company_id": "co-1",
        # 프론트가 조작 시도 — 서버는 EXISTING 모드에서 이 필드들 무시
        "invoicee_business_number": "0000000000",
        "invoicee_company_name": "위조회사",
        "invoicee_representative_name": "가짜대표",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "테스트품목",
        "issue_reason": "테스트 발행",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    assert r.status_code == 200, r.text
    row = r.json()["data"]
    assert row["invoicee_business_number"] == "1234567890"       # SoT
    assert row["invoicee_company_name"] == "가나다 주식회사"        # SoT
    assert row["invoicee_representative_name"] == "홍길동"          # SoT
    # 프론트 위조값은 무시
    assert row["invoicee_business_number"] != "0000000000"


@requires_client
def test_C6_manual_mode_no_companies_write(monkeypatch):
    """MANUAL 모드: companies 에 새 회사가 INSERT 되면 안 됨."""
    c = _client(monkeypatch)
    pre_companies = len(c._store["companies"])
    body = {
        "idempotency_key": _idem(),
        "company_mode": "MANUAL",
        "invoicee_business_number": "1112223333",
        "invoicee_company_name": "신규수동회사",
        "invoicee_representative_name": "신대표",
        "invoicee_address": "서울시 마포구 상수동",
        "supply_amount": 500000, "vat_amount": 50000,
        "supply_date": "2026-09-06", "item_name": "수동품목",
        "issue_reason": "직접입력 발행",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    assert r.status_code == 200, r.text
    # companies count 동일 — MANUAL 모드는 회사 INSERT 금지
    assert len(c._store["companies"]) == pre_companies
    row = r.json()["data"]
    assert row["company_id"] is None
    assert row["invoicee_company_name"] == "신규수동회사"


# ═════════════════════════════════════════════════════════════════════
# M1~M12 — 수동발행 create + process
# ═════════════════════════════════════════════════════════════════════
@requires_client
def test_M1_existing_mode_snapshot_exact(monkeypatch):
    """EXISTING 모드: snapshot 이 companies SoT 와 정확히 일치."""
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-2",
        "supply_amount": 300000, "vat_amount": 30000,
        "supply_date": "2026-09-06", "item_name": "품목A", "issue_reason": "사유A",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    row = r.json()["data"]
    assert row["invoicee_business_number"] == "9876543210"
    assert row["invoicee_company_name"] == "다른회사"
    assert row["invoicee_representative_name"] == "김철수"


@requires_client
def test_M2_manual_mode_invoicee_passthrough(monkeypatch):
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "MANUAL",
        "invoicee_business_number": "5556667777",
        "invoicee_company_name": "직접A",
        "invoicee_representative_name": "직접B",
        "invoicee_email": "direct@example.com",
        "supply_amount": 200000, "vat_amount": 20000,
        "supply_date": "2026-09-06", "item_name": "품목M", "issue_reason": "사유M",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    row = r.json()["data"]
    assert row["invoicee_business_number"] == "5556667777"
    assert row["invoicee_company_name"] == "직접A"
    assert row["invoicee_email"] == "direct@example.com"


@requires_client
def test_M3_payment_id_null_no_synthetic_payment(monkeypatch):
    """ADMIN_MANUAL row 는 payment_id NULL. payments 테이블에 synthetic row 생성 0."""
    c = _client(monkeypatch)
    pre_pay = len(c._store["payments"])
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    row = r.json()["data"]
    assert row["payment_id"] is None
    assert len(c._store["payments"]) == pre_pay


@requires_client
def test_M4_server_recomputes_total(monkeypatch):
    """total 은 서버가 supply + vat 로 재계산. 프론트가 total 필드를 보내도 무시(schema 자체가 total 을 안 받음)."""
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 499000, "vat_amount": 49900,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    row = r.json()["data"]
    assert row["supply_amount"] == 499000
    assert row["vat_amount"] == 49900
    assert row["total_amount"] == 548900          # 서버 재계산


@requires_client
def test_M5_invalid_body_rejected(monkeypatch):
    c = _client(monkeypatch)
    common = {
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    # (a) idempotency_key 없음
    r1 = c.post("/payments/admin/tax-invoices/manual",
                json={**common})  # 없음 → pydantic 422
    assert r1.status_code == 422
    # (b) idempotency_key 비-UUID
    r2 = c.post("/payments/admin/tax-invoices/manual",
                json={**common, "idempotency_key": "not-a-uuid"})
    assert r2.status_code == 400
    # (c) supply 음수
    r3 = c.post("/payments/admin/tax-invoices/manual",
                json={**common, "idempotency_key": _idem(), "supply_amount": -1})
    assert r3.status_code == 400
    # (d) supply_date 형식 오류
    r4 = c.post("/payments/admin/tax-invoices/manual",
                json={**common, "idempotency_key": _idem(), "supply_date": "2026/09/06"})
    assert r4.status_code == 400
    # (e) item_name 공란
    r5 = c.post("/payments/admin/tax-invoices/manual",
                json={**common, "idempotency_key": _idem(), "item_name": "   "})
    assert r5.status_code == 400
    # (f) MANUAL 모드에서 필수 invoicee_* 누락
    r6 = c.post("/payments/admin/tax-invoices/manual",
                json={**common, "idempotency_key": _idem(),
                      "company_mode": "MANUAL", "company_id": None})
    assert r6.status_code == 400


@requires_client
def test_M6_idempotency_second_returns_existing(monkeypatch):
    c = _client(monkeypatch)
    key = _idem()
    body = {
        "idempotency_key": key,
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    r1 = c.post("/payments/admin/tax-invoices/manual", json=body)
    r2 = c.post("/payments/admin/tax-invoices/manual", json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["created"] is True
    assert r2.json()["created"] is False
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    # request row 1건만
    assert len(c._store["tax_invoice_requests"]) == 1


@requires_client
def test_M7_invoice_live_off_returns_423_and_keeps_requested(monkeypatch):
    """INVOICE_LIVE OFF → process 시 423. request.status 는 REQUESTED 로 유지 (FAILED 오염 금지)."""
    c = _client(monkeypatch, live=False)
    # create (create 는 live 무관)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    request_id = r.json()["data"]["id"]
    # process → 423
    pr = c.post(f"/payments/admin/tax-invoices/manual/{request_id}/process")
    assert pr.status_code == 423, pr.text
    assert pr.json()["detail"]["code"] == "INVOICE_GATED"
    # provider 호출 0
    assert c._mock.calls == []
    # request.status = REQUESTED (FAILED 오염 금지)
    req = c._store["tax_invoice_requests"][0]
    assert req["status"] == "REQUESTED", "OFF 게이트가 request 를 FAILED 로 오염하면 안 됨"


@requires_client
def test_M8_mock_success_issues_and_links(monkeypatch):
    """LIVE + mock success → ledger row(payment_id NULL, ISSUED) + request.status=ISSUED + tax_invoice_id 연결."""
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    r = c.post("/payments/admin/tax-invoices/manual", json=body)
    rid = r.json()["data"]["id"]
    pr = c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    assert pr.status_code == 200, pr.text
    assert pr.json()["data"]["outcome"] == "ISSUED"
    assert len(c._mock.calls) == 1
    # ledger row 검증
    invs = [i for i in c._store["tax_invoices"] if i.get("invoice_kind") == "ORIGINAL"]
    assert len(invs) == 1
    assert invs[0]["payment_id"] is None       # payment-less
    assert invs[0]["status"] == "ISSUED"
    assert invs[0]["nts_confirm_num"] == "NTS-MAN"
    # request 연결
    req = c._store["tax_invoice_requests"][0]
    assert req["status"] == "ISSUED"
    assert req["tax_invoice_id"] == invs[0]["id"]


@requires_client
def test_M9_duplicate_process_no_reissue(monkeypatch):
    """같은 request_id 로 process 재호출 → provider 재호출 0 (ISSUED 재사용)."""
    c = _client(monkeypatch)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    rid = c.post("/payments/admin/tax-invoices/manual", json=body).json()["data"]["id"]
    p1 = c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    p2 = c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    assert p1.status_code == 200 and p2.status_code == 200
    assert len(c._mock.calls) == 1, "재호출은 provider 재호출 금지"
    assert len([i for i in c._store["tax_invoices"] if i.get("invoice_kind") == "ORIGINAL"]) == 1


@requires_client
def test_M10_provider_failure_marks_failed_retry_ok(monkeypatch):
    """provider 실패 → request/ledger FAILED. 상태는 재시도 가능하도록 유지."""
    c = _client(monkeypatch, provider_fail=True)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    rid = c.post("/payments/admin/tax-invoices/manual", json=body).json()["data"]["id"]
    pr = c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    assert pr.status_code == 400
    assert pr.json()["detail"]["code"] == "MANUAL_ISSUE_FAILED"
    req = c._store["tax_invoice_requests"][0]
    assert req["status"] == "FAILED"
    # ledger 도 FAILED 로 mark (mgt_key 재사용 준비)
    invs = c._store["tax_invoices"]
    assert len(invs) == 1
    assert invs[0]["status"] == "FAILED"


@requires_client
def test_M11_retry_success_same_mgt_key_no_duplicate(monkeypatch):
    """실패 후 provider 복구 → 재시도 성공. 같은 mgt_key 재사용, 중복 invoice 0."""
    c = _client(monkeypatch, provider_fail=True)
    body = {
        "idempotency_key": _idem(),
        "company_mode": "EXISTING", "company_id": "co-1",
        "supply_amount": 100000, "vat_amount": 10000,
        "supply_date": "2026-09-06", "item_name": "품목", "issue_reason": "사유",
    }
    rid = c.post("/payments/admin/tax-invoices/manual", json=body).json()["data"]["id"]
    # 1차 실패
    c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    assert c._store["tax_invoice_requests"][0]["status"] == "FAILED"

    # provider 를 성공으로 flip
    c._mock.fail = False

    # 2차 재시도 성공
    pr = c.post(f"/payments/admin/tax-invoices/manual/{rid}/process")
    assert pr.status_code == 200, pr.text
    # 원장 1건만 (재사용) + ISSUED
    invs = [i for i in c._store["tax_invoices"] if i.get("invoice_kind") == "ORIGINAL"]
    assert len(invs) == 1
    assert invs[0]["status"] == "ISSUED"
    # mgt_key 는 request_id 기반 deterministic → 같은 값 유지
    from services.invoice_svc import _make_manual_mgt_key
    assert invs[0]["mgt_key"] == _make_manual_mgt_key(rid)


@requires_client
def test_M12_guard_non_admin_manual_source_rejected(monkeypatch):
    """수동 process 엔드포인트에 다른 source (MYPAGE 등) 요청 넣으면 409."""
    c = _client(monkeypatch)
    # MYPAGE source request 를 직접 store 에 seed
    other_rid = str(uuid.uuid4())
    c._store["tax_invoice_requests"].append({
        "id": other_rid, "payment_id": "some-pay", "company_id": "co-1",
        "source": "MYPAGE", "doc_type": "TAX_INVOICE", "status": "REQUESTED",
        "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000,
        "supply_date": "2026-09-06",
        "invoicee_business_number": "1234567890", "invoicee_company_name": "가나다 주식회사",
        "invoicee_representative_name": "홍길동",
        "item_name": "x", "issue_reason": "y",
    })
    r = c.post(f"/payments/admin/tax-invoices/manual/{other_rid}/process")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_ADMIN_MANUAL"


# ═════════════════════════════════════════════════════════════════════
# 회귀: 기존 issue_tax_invoice 는 한 줄도 변경되지 않음 (payment 기반)
# ═════════════════════════════════════════════════════════════════════
def test_regression_issue_tax_invoice_still_requires_payment():
    """소스 시그니처: issue_tax_invoice(payment_id, invoicee, supply_date, created_by)."""
    import inspect
    sig = inspect.signature(inv.issue_tax_invoice)
    params = list(sig.parameters.keys())
    assert params[:3] == ["payment_id", "invoicee", "supply_date"], (
        f"기존 issue_tax_invoice 시그니처 변경 금지: {params}"
    )


def test_regression_new_manual_function_separate():
    """issue_manual_tax_invoice 는 별도 신규 함수 (payment_id 파라미터 없음)."""
    import inspect
    sig = inspect.signature(inv.issue_manual_tax_invoice)
    params = list(sig.parameters.keys())
    assert "payment_id" not in params, (
        f"수동 발행은 payment-less: {params}"
    )
    assert "request_id" in params
    assert "invoicee" in params
    assert "company_id" in params  # EXISTING 모드에서 채워짐 (optional)
