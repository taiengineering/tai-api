"""BACKEND-2 세금계산서 eligibility/request 단위테스트 (FakeSupabase 격리).

service(sb 주입) 중심. 운영 DB/네트워크/ Popbill 불사용.
payments.proof_type · tax_invoices · invoice_svc 미변경 검증 포함.
"""
import uuid

import pytest

from services import tax_invoice_request_svc as svc

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    import routers.member_tax_invoice as mti
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


class _Result:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if data is not None else 0


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []; self._cols = "*"

    def select(self, cols="*", *a, **k): self._op = "select"; self._cols = cols or "*"; return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def delete(self): self._op = "delete"; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v): return False
            if op == "in" and row.get(c) not in v: return False
            if op == "is" and v == "null" and row.get(c) is not None: return False
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
            return _Result([self._project(r) for r in rows if self._match(r)])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                if self.table == "tax_invoice_requests":
                    for r in rows:
                        if r.get("payment_id") == it.get("payment_id") and r.get("doc_type") == it.get("doc_type"):
                            raise Exception('duplicate key value violates unique constraint "tax_invoice_requests_payment_doc_unique"')
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched: r.update(self._payload)
            return _Result([dict(r) for r in matched])
        if self._op == "delete":
            keep = [r for r in rows if not self._match(r)]
            removed = [r for r in rows if self._match(r)]
            self.store[self.table] = keep
            return _Result([dict(r) for r in removed])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []
    def table(self, name):
        return _Query(self.store, name, self.log)


def _payment(**kw):
    base = {"id": "p1", "status_code": "SUCCESS", "company_id": "co1", "pg_method": "VBank",
            "proof_type": None, "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000,
            "paid_at": "2026-09-01T00:00:00Z", "product_type": "DIAGNOSIS"}
    base.update(kw); return base


def _company(**kw):
    base = {"id": "co1", "name": "TAI", "business_number": "1234567890",
            "representative_name": "심태왕", "contact_email": "a@b.c",
            "address": "서울", "address_road": "테헤란로", "address_detail": "3층",
            "business_type": "정보통신업", "business_category": "응용SW"}
    base.update(kw); return base


def _store(payment=None, company=None, requests=None, tax_invoices=None):
    return {
        "payments": [payment or _payment()],
        "companies": [company or _company()],
        "tax_invoice_requests": list(requests or []),
        "tax_invoices": list(tax_invoices or []),
    }


def _elig(store):
    sb = FakeSupabase(store)
    payment = store["payments"][0]
    return svc.evaluate_eligibility(sb, payment)


# ══ canonical method ══
def test_canonical_method():
    assert svc.canonical_payment_instrument("Card") == "CARD"
    assert svc.canonical_payment_instrument("CardBilling") == "CARD"
    assert svc.canonical_payment_instrument("DirectBank") == "ACCOUNT_TRANSFER"
    for v in ("VBank", "VBANK", "Vbank"):
        assert svc.canonical_payment_instrument(v) == "VBANK"
    assert svc.canonical_payment_instrument("HPP") == "UNKNOWN"
    assert svc.canonical_payment_instrument(None) == "UNKNOWN"


# ══ method/proof policy (T5~T16) ══
def test_t5_not_success_deny():
    d = _elig(_store(payment=_payment(status_code="PENDING")))
    assert d["decision"] == "DENY" and d["reason_code"] == "PAYMENT_NOT_SUCCESS"


def test_t6_t7_card_deny():
    for m in ("Card", "CardBilling"):
        d = _elig(_store(payment=_payment(pg_method=m)))
        assert d["decision"] == "DENY" and d["reason_code"] == "CARD_RECEIPT_IS_EVIDENCE"


def test_t8_directbank_taxinvoice_allow():
    d = _elig(_store(payment=_payment(pg_method="DirectBank", proof_type="TAX_INVOICE")))
    assert d["decision"] == "ALLOW" and d["reason_code"] == "ELIGIBLE"


def test_t9_directbank_cashreceipt_deny():
    d = _elig(_store(payment=_payment(pg_method="DirectBank", proof_type="CASH_RECEIPT")))
    assert d["decision"] == "DENY" and d["reason_code"] == "CASH_RECEIPT_SELECTED"


def test_t10_directbank_null_review():
    d = _elig(_store(payment=_payment(pg_method="DirectBank", proof_type=None)))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "LEGACY_PROOF_UNKNOWN"


def test_t11_directbank_none_review():
    d = _elig(_store(payment=_payment(pg_method="DirectBank", proof_type="NONE")))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "PROOF_NOT_SELECTED"


def test_t12_t13_t14_vbank_null_allow():
    for m in ("VBank", "VBANK", "Vbank"):
        d = _elig(_store(payment=_payment(pg_method=m, proof_type=None)))
        assert d["decision"] == "ALLOW" and d["reason_code"] == "ELIGIBLE"


def test_t15_vbank_cashreceipt_deny():
    d = _elig(_store(payment=_payment(pg_method="VBank", proof_type="CASH_RECEIPT")))
    assert d["decision"] == "DENY" and d["reason_code"] == "CASH_RECEIPT_SELECTED"


def test_vbank_cardreceipt_review_conflict():
    d = _elig(_store(payment=_payment(pg_method="VBank", proof_type="CARD_RECEIPT")))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "PROOF_CONFLICT"


def test_t16_unknown_review():
    d = _elig(_store(payment=_payment(pg_method="HPP")))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "UNKNOWN_PAYMENT_METHOD"


# ══ company completeness (T17~T19) ══
def test_t17_incomplete_company_deny_missing():
    d = _elig(_store(company=_company(business_number=None, representative_name=None)))
    assert d["decision"] == "DENY" and d["reason_code"] == "COMPANY_PROFILE_INCOMPLETE"
    assert "business_number" in d["missing_fields"] and "representative_name" in d["missing_fields"]


def test_t18_malformed_business_number_deny():
    d = _elig(_store(company=_company(business_number="123")))
    assert d["decision"] == "DENY" and "business_number" in d["missing_fields"]


def test_t19_complete_company_allow():
    d = _elig(_store())
    assert d["decision"] == "ALLOW" and d["company_complete"] is True and d["missing_fields"] == []


# ══ ledger 상호배타 (T20~T23) ══
def test_t20_existing_cashreceipt_issued_deny():
    d = _elig(_store(tax_invoices=[{"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": "ISSUED", "invoice_kind": "ORIGINAL"}]))
    assert d["decision"] == "DENY" and d["reason_code"] == "CASH_RECEIPT_EXISTS"
    assert d["existing_cash_receipt"] is True


def test_t21_existing_cashreceipt_cancelled_review():
    d = _elig(_store(tax_invoices=[{"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": "CANCELLED", "invoice_kind": "ORIGINAL"}]))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "CASH_RECEIPT_HISTORY_REVIEW"


def test_t22_existing_taxinvoice_issued_deny():
    d = _elig(_store(tax_invoices=[{"payment_id": "p1", "doc_type": "TAX_INVOICE", "status": "ISSUED", "invoice_kind": "ORIGINAL"}]))
    assert d["decision"] == "DENY" and d["reason_code"] == "TAX_INVOICE_ALREADY_EXISTS"
    assert d["existing_tax_invoice"] is True


def test_t23_existing_taxinvoice_failed_review():
    d = _elig(_store(tax_invoices=[{"payment_id": "p1", "doc_type": "TAX_INVOICE", "status": "FAILED", "invoice_kind": "ORIGINAL"}]))
    assert d["decision"] == "REVIEW_REQUIRED" and d["reason_code"] == "TAX_INVOICE_HISTORY_REVIEW"


# ══ request 생성/스냅샷 (T24~T30) ══
def test_t24_t25_t26_t27_snapshot_exact():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"),
                   company=_company(business_number="123-45-67890"))
    sb = FakeSupabase(store)
    row, created = svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    assert created is True
    assert row["supply_amount"] == 100000 and row["vat_amount"] == 10000 and row["total_amount"] == 110000  # T24
    assert row["invoicee_business_number"] == "1234567890"  # T25 숫자정규화
    assert row["supply_date"] is None  # T26
    assert row["requested_by"] == "u1"  # T27 public.users.id
    assert row["proof_type"] == "TAX_INVOICE" and row["status"] == "REQUESTED"


def test_t28_t29_source_accept():
    for s in ("MYPAGE", "SAAS"):
        store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
        sb = FakeSupabase(store)
        row, created = svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], s)
        assert created is True and row["source"] == s


def test_t30_source_auto_saas_rejected():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    sb = FakeSupabase(store)
    with pytest.raises(svc.MemberTaxError) as e:
        svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "AUTO_SAAS")
    assert e.value.status_code == 422


# ══ lifecycle / idempotency (T31~T38) ══
def _req(status, **kw):
    base = {"id": "r1", "payment_id": "p1", "company_id": "co1", "doc_type": "TAX_INVOICE",
            "status": status, "proof_type": "TAX_INVOICE", "source": "MYPAGE",
            "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000}
    base.update(kw); return base


def test_t31_t32_t33_existing_active_idempotent():
    for st in ("REQUESTED", "PROCESSING", "ISSUED"):
        store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"), requests=[_req(st)])
        sb = FakeSupabase(store)
        row, created = svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
        assert created is False and row["id"] == "r1"
        assert len(store["tax_invoice_requests"]) == 1  # INSERT 0


def test_t34_existing_cancelled_409_no_reopen():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"), requests=[_req("CANCELLED")])
    sb = FakeSupabase(store)
    with pytest.raises(svc.MemberTaxError) as e:
        svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    assert e.value.status_code == 409 and e.value.code == "REQUEST_CANCELLED"
    assert store["tax_invoice_requests"][0]["status"] == "CANCELLED"  # no reopen


def test_t35_failed_reuse_row_on_allow():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"),
                   requests=[_req("FAILED", failure_code="E1", failure_reason="x")])
    sb = FakeSupabase(store)
    row, created = svc.create_request(sb, {"id": "u2", "company_id": "co1"}, store["payments"][0], "SAAS")
    assert created is False  # same row UPDATE
    assert len(store["tax_invoice_requests"]) == 1
    assert store["tax_invoice_requests"][0]["status"] == "REQUESTED"
    assert store["tax_invoice_requests"][0]["failure_code"] is None
    assert store["tax_invoice_requests"][0]["requested_by"] == "u2"


def test_t36_review_required_still_not_eligible_unchanged():
    # DirectBank + NULL → REVIEW. 기존 REVIEW_REQUIRED row 유지, 409.
    store = _store(payment=_payment(pg_method="DirectBank", proof_type=None), requests=[_req("REVIEW_REQUIRED")])
    sb = FakeSupabase(store)
    with pytest.raises(svc.MemberTaxError) as e:
        svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    assert e.value.status_code == 409
    assert store["tax_invoice_requests"][0]["status"] == "REVIEW_REQUIRED"


class _DupInsertReqFake(FakeSupabase):
    """tax_invoice_requests insert 시 payment_doc_unique 예외(concurrent). 예외 전 기존 row 삽입."""
    def __init__(self, store, existing):
        super().__init__(store); self.existing = existing; self._done = False
    def table(self, name):
        q = super().table(name); orig = q.execute
        def exec2():
            if name == "tax_invoice_requests" and q._op == "insert" and not self._done:
                self._done = True
                self.store.setdefault("tax_invoice_requests", []).append(self.existing)
                raise Exception('duplicate key value violates unique constraint "tax_invoice_requests_payment_doc_unique"')
            return orig()
        q.execute = exec2
        return q


def test_t37_concurrent_unique_returns_existing():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    sb = _DupInsertReqFake(store, existing=_req("REQUESTED"))
    row, created = svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    assert created is False and row["id"] == "r1"


class _BoomInsertReqFake(FakeSupabase):
    def table(self, name):
        q = super().table(name); orig = q.execute
        def exec2():
            if name == "tax_invoice_requests" and q._op == "insert":
                raise Exception("db down")  # non-idempotency error
            return orig()
        q.execute = exec2
        return q


def test_t38_unrelated_db_error_500():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    sb = _BoomInsertReqFake(store)
    with pytest.raises(svc.MemberTaxError) as e:
        svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    assert e.value.status_code == 500 and e.value.code == "REQUEST_CREATE_FAILED"


# ══ no side-effect (T39~T42) ══
def test_t39_t40_t41_t42_no_side_effects():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    before_payment = dict(store["payments"][0])
    sb = FakeSupabase(store)
    svc.create_request(sb, {"id": "u1", "company_id": "co1"}, store["payments"][0], "MYPAGE")
    # T39 payments.proof_type 미변경 (payments UPDATE 없음)
    assert store["payments"][0] == before_payment
    ops = {(t, op) for (t, op) in sb.log}
    assert ("payments", "update") not in ops and ("payments", "insert") not in ops
    # T40 tax_invoices 미변경
    assert all(op == "select" for (t, op) in sb.log if t == "tax_invoices")
    # T41/T42 invoice_svc / Popbill 호출 없음(이 서비스가 import도 안 함) — 구조적 보장
    import services.tax_invoice_request_svc as s
    src = open(s.__file__, encoding="utf-8").read()
    assert "invoice_svc" not in src and "popbill" not in src.lower()


# ══ ownership (T1~T4) — service load_and_authorize ══
def test_t2_payment_not_found_404():
    sb = FakeSupabase({"payments": [], "companies": [_company()]})
    with pytest.raises(svc.MemberTaxError) as e:
        svc.load_and_authorize(sb, {"id": "u1", "company_id": "co1"}, "nope")
    assert e.value.status_code == 404


def test_t3_other_company_payment_404():
    sb = FakeSupabase(_store(payment=_payment(company_id="other")))
    with pytest.raises(svc.MemberTaxError) as e:
        svc.load_and_authorize(sb, {"id": "u1", "company_id": "co1"}, "p1")
    assert e.value.status_code == 404  # 비노출


def test_t4_company_less_user_403():
    sb = FakeSupabase(_store())
    with pytest.raises(svc.MemberTaxError) as e:
        svc.load_and_authorize(sb, {"id": "u1", "company_id": None}, "p1")
    assert e.value.status_code == 403 and e.value.code == "COMPANY_REQUIRED"


# ══ router 레벨 (T1 unauth / 201 / idempotent / 409) ══
def _client(current_user, store):
    app = FastAPI()
    app.include_router(mti.router)
    app.dependency_overrides[mti.get_current_user] = lambda: current_user
    mti.get_supabase = lambda: FakeSupabase(store)
    return TestClient(app)


@requires_client
def test_t1_unauth_eligibility_401():
    app = FastAPI(); app.include_router(mti.router)
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")
    app.dependency_overrides[mti.get_current_user] = _raise
    r = TestClient(app).get("/payments/p1/tax-invoice/eligibility")
    assert r.status_code == 401


@requires_client
def test_router_post_new_201_and_idempotent_200():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    c = _client({"id": "u1", "company_id": "co1"}, store)
    r1 = c.post("/payments/p1/tax-invoice/request", json={"source": "MYPAGE"})
    assert r1.status_code == 201
    r2 = c.post("/payments/p1/tax-invoice/request", json={"source": "MYPAGE"})
    assert r2.status_code == 200  # idempotent
    assert len(store["tax_invoice_requests"]) == 1


@requires_client
def test_router_post_deny_409_incomplete_company():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"),
                   company=_company(business_number=None))
    c = _client({"id": "u1", "company_id": "co1"}, store)
    r = c.post("/payments/p1/tax-invoice/request", json={"source": "MYPAGE"})
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["reason_code"] == "COMPANY_PROFILE_INCOMPLETE" and "business_number" in body["missing_fields"]
    assert store["tax_invoice_requests"] == []  # INSERT 0


@requires_client
def test_router_post_auto_saas_422():
    store = _store(payment=_payment(pg_method="VBank", proof_type="TAX_INVOICE"))
    c = _client({"id": "u1", "company_id": "co1"}, store)
    r = c.post("/payments/p1/tax-invoice/request", json={"source": "AUTO_SAAS"})
    assert r.status_code == 422
