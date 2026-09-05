"""BACKEND-4 환불→수정세금계산서 단위테스트 (FakeSupabase + popbill mock).

process_refund_tax_adjustment: inv.get_supabase/invoice_live/_popbill_conf/_popbill_issue_modified_tax monkeypatch.
운영 DB/네트워크/실 popbill 불사용. companies fake는 운영 SoT(name/contact_email/address_*)와 일치.
"""
import uuid

import pytest

import services.invoice_svc as inv

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    import routers.payment_ledger as pl
    from routers.auth import get_current_user as _gcu
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


class _Result:
    def __init__(self, data):
        self.data = data; self.count = len(data) if data is not None else 0


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []; self._cols = "*"
    def select(self, cols="*", *a, **k): self._op = "select"; self._cols = cols or "*"; return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self
    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v): return False
            if op == "in" and row.get(c) not in v: return False
        return True
    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            cols = None if self._cols == "*" else [c.strip() for c in self._cols.split(",") if c.strip()]
            out = []
            for r in rows:
                if not self._match(r): continue
                out.append(dict(r) if cols is None else {k: r.get(k) for k in cols})
            return _Result(out)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                if self.table == "tax_invoices":
                    for r in rows:
                        if r.get("doc_type") == it.get("doc_type") and r.get("mgt_key") == it.get("mgt_key"):
                            raise Exception('duplicate key value violates unique constraint "tax_invoices_doc_type_mgt_key"')
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched: r.update(self._payload)
            return _Result([dict(r) for r in matched])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}; self.log = []
    def table(self, name):
        return _Query(self.store, name, self.log)


class MockMod:
    def __init__(self, fail=False):
        self.calls = []; self.fail = fail
    def issue(self, conf, **kw):
        self.calls.append(kw)
        if self.fail:
            raise Exception("popbill correction down")
        return {"nts": "MOD-NTS", "code": 1, "message": "ok"}


def _payment(**kw):
    base = {"id": "p1", "status_code": "CANCELLED", "company_id": "co1", "product_type": "DIAGNOSIS",
            "total_amount": 110000}
    base.update(kw); return base


def _original(**kw):
    base = {"id": "orig1", "payment_id": "p1", "company_id": "co1", "doc_type": "TAX_INVOICE",
            "invoice_kind": "ORIGINAL", "status": "ISSUED", "nts_confirm_num": "NTS-ORIG",
            "mgt_key": "TX-p1", "supply_cost": 100000, "tax": 10000, "total_amount": 110000}
    base.update(kw); return base


def _refund(**kw):
    base = {"id": "rf1", "payment_id": "p1", "refund_type": "FULL", "amount": 110000, "status": "DONE",
            "reason_text": "고객 변심", "created_at": "2026-09-03T05:00:00+00:00", "cumulative_refunded": 110000}
    base.update(kw); return base


def _company(**kw):
    # 운영 SoT: companies.name (company_name 아님), contact_email, address_road/address_detail
    base = {"id": "co1", "business_number": "1234567890", "name": "고객사", "representative_name": "홍길동",
            "contact_email": "co@x.c", "address": "서울", "address_road": "서울로 1", "address_detail": "3층",
            "business_type": "제조", "business_category": "전자"}
    base.update(kw); return base


def _issued_request(**kw):
    base = {"id": "req1", "payment_id": "p1", "doc_type": "TAX_INVOICE", "status": "ISSUED",
            "invoicee_business_number": "1234567890", "invoicee_company_name": "스냅샷사",
            "invoicee_representative_name": "스냅대표", "invoicee_email": "s@x.c",
            "invoicee_address": "부산", "invoicee_business_type": "서비스", "invoicee_business_category": "SW"}
    base.update(kw); return base


def _setup(monkeypatch, store, fail=False, live=True):
    fake = FakeSupabase(store)
    mock = MockMod(fail=fail)
    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: live)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {"corp_num": "7233901422", "corp_name": "TAI",
        "ceo_name": "심태왕", "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True})
    monkeypatch.setattr(inv, "_popbill_issue_modified_tax", lambda conf, **kw: mock.issue(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc", type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return fake, mock


# A1 refund status != DONE
def test_a1_refund_not_done_no_modified(monkeypatch):
    store = {"refunds": [_refund(status="REQUESTED")], "payments": [_payment()], "tax_invoices": [_original()]}
    fake, mock = _setup(monkeypatch, store)
    with pytest.raises(inv.InvoiceError) as e:
        inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert e.value.code == "REFUND_NOT_DONE" and mock.calls == []


# A2 DONE + original 없음 → request CANCELLED, popbill 0
def test_a2_no_original_cancels_request(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [],
            "tax_invoice_requests": [{"id": "req1", "payment_id": "p1", "doc_type": "TAX_INVOICE", "status": "REQUESTED"}]}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["outcome"] == "REQUEST_CANCELLED" and mock.calls == []
    r = store["tax_invoice_requests"][0]
    assert r["status"] == "CANCELLED" and r["failure_code"] == "REFUNDED_BEFORE_ISSUE"


# A3 첫 환불 전액 → code 4, original 금액 exact negative
def test_a3_full_oneshot_code4(monkeypatch):
    store = {"refunds": [_refund(amount=110000, cumulative_refunded=110000)], "payments": [_payment()],
            "tax_invoices": [_original()], "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["modify_code"] == 4
    kw = mock.calls[0]
    assert kw["supply"] == -100000 and kw["vat"] == -10000 and kw["total"] == -110000


# A4 부분환불 → code 2, refund.amount exact negative
def test_a4_partial_code2(monkeypatch):
    store = {"refunds": [_refund(refund_type="PARTIAL", amount=55000, cumulative_refunded=55000)],
            "payments": [_payment()], "tax_invoices": [_original()], "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["modify_code"] == 2
    kw = mock.calls[0]
    assert kw["total"] == -55000
    assert abs(kw["supply"]) + abs(kw["vat"]) == 55000


# A5 부분환불 후 remaining FULL → code 2 (NOT 4)
def test_a5_partial_then_full_code2(monkeypatch):
    store = {"refunds": [_refund(refund_type="FULL", amount=55000, cumulative_refunded=110000)],
            "payments": [_payment()], "tax_invoices": [_original()], "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["modify_code"] == 2 and mock.calls[0]["total"] == -55000


# A6 orgNTSConfirmNum exact
def test_a6_org_nts_exact(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original(nts_confirm_num="NTS-XYZ")],
            "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert mock.calls[0]["org_nts"] == "NTS-XYZ"


# A7 reason date = refund.created_at KST date
def test_a7_reason_date_kst(monkeypatch):
    # 2026-09-03T20:00:00Z → KST 2026-09-04
    store = {"refunds": [_refund(created_at="2026-09-03T20:00:00+00:00")], "payments": [_payment()],
            "tax_invoices": [_original()], "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert mock.calls[0]["write_date"] == "20260904"


# A8 동일 refund ISSUED → popbill 0
def test_a8_existing_modified_issued(monkeypatch):
    existing_mod = {"id": "mod1", "payment_id": "p1", "doc_type": "TAX_INVOICE", "invoice_kind": "MODIFIED",
                    "parent_invoice_id": "orig1", "refund_ref": "rf1", "mgt_key": "MT-rf1", "status": "ISSUED"}
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original(), existing_mod],
            "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["outcome"] == "ISSUED" and res["modified_invoice_id"] == "mod1" and mock.calls == []


# A9 FAILED retry → same row, same mgt_key
def test_a9_failed_retry_same_row(monkeypatch):
    existing_mod = {"id": "mod1", "payment_id": "p1", "doc_type": "TAX_INVOICE", "invoice_kind": "MODIFIED",
                    "parent_invoice_id": "orig1", "refund_ref": "rf1", "mgt_key": "MT-rf1", "status": "FAILED"}
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original(), existing_mod],
            "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    res = inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert res["modified_invoice_id"] == "mod1"
    mods = [r for r in store["tax_invoices"] if r.get("invoice_kind") == "MODIFIED"]
    assert len(mods) == 1 and mods[0]["mgt_key"] == "MT-rf1" and mods[0]["status"] == "ISSUED"


# A10 INVOICE_LIVE OFF → 423, popbill 0, modified mutation 0
def test_a10_gate_off_no_mutation(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original()],
            "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store, live=False)
    with pytest.raises(inv.InvoiceError) as e:
        inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert e.value.status_code == 423
    assert mock.calls == []
    assert [r for r in store["tax_invoices"] if r.get("invoice_kind") == "MODIFIED"] == []


# A11 Popbill correction failure → modified FAILED (refund 무관 유지)
def test_a11_popbill_failure_modified_failed(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original()],
            "companies": [_company()], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store, fail=True)
    with pytest.raises(inv.InvoiceError) as e:
        inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert e.value.code == "MODIFIED_ISSUE_FAILED"
    mods = [r for r in store["tax_invoices"] if r.get("invoice_kind") == "MODIFIED"]
    assert len(mods) == 1 and mods[0]["status"] == "FAILED"
    assert store["refunds"][0]["status"] == "DONE"


# A11b refund_svc 훅은 fail-soft (예외 삼킴)
def test_a11b_refund_hook_failsoft(monkeypatch):
    import services.refund_svc as rf
    def _boom(refund_id, created_by=None):
        raise inv.InvoiceError(400, "boom", "MODIFIED_ISSUE_FAILED")
    monkeypatch.setattr("services.invoice_svc.process_refund_tax_adjustment", _boom)
    monkeypatch.setattr(rf, "audit_svc", type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    rf._tax_adjustment_hook("rf1", "admin")  # 예외 전파 없어야 함


# B4-P1-1 request snapshot 없음 + companies.name 있음 → invoicee corpName = companies.name
def test_b4p1_1_company_fallback_uses_name(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original()],
            "companies": [_company(name="네임회사")], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    inv.process_refund_tax_adjustment("rf1", created_by="admin")
    iv = mock.calls[0]["invoicee"]
    assert iv["corpName"] == "네임회사"          # companies.name 사용
    assert iv["email"] == "co@x.c"               # contact_email 사용
    assert iv["addr"] == "서울로 1 3층"           # address_road + address_detail


# invoicee snapshot 우선순위: request ISSUED snapshot 사용
def test_invoicee_from_request_snapshot(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original()],
            "companies": [_company()], "tax_invoice_requests": [_issued_request()]}
    fake, mock = _setup(monkeypatch, store)
    inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert mock.calls[0]["invoicee"]["corpNum"] == "1234567890"
    assert mock.calls[0]["invoicee"]["corpName"] == "스냅샷사"  # request snapshot 우선


# invoicee 결여 → MODIFIED_INVOICEE_INCOMPLETE
def test_invoicee_incomplete(monkeypatch):
    store = {"refunds": [_refund()], "payments": [_payment()], "tax_invoices": [_original(company_id="none")],
            "companies": [], "tax_invoice_requests": []}
    fake, mock = _setup(monkeypatch, store)
    with pytest.raises(inv.InvoiceError) as e:
        inv.process_refund_tax_adjustment("rf1", created_by="admin")
    assert e.value.code == "MODIFIED_INVOICEE_INCOMPLETE" and mock.calls == []


# A12 non-admin retry endpoint → 403
def _client_role(role):
    app = FastAPI(); app.include_router(pl.router)
    app.dependency_overrides[_gcu] = lambda: {"id": "u1", "role_code": role, "company_id": "co1"}
    return TestClient(app)


@requires_client
def test_a12_non_admin_retry_403():
    c = _client_role("012")
    assert c.post("/payments/refunds/rf1/tax-adjustment").status_code == 403
