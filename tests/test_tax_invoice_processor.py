"""BACKEND-3 issuance guard + processor 단위테스트 (SIMPLE, FakeSupabase + popbill mock).

invoice_svc: get_supabase/invoice_live/_popbill_conf/_popbill_issue_tax|cash 를 monkeypatch.
processor: sb 주입 + invoice_svc.issue_tax_invoice/invoice_live monkeypatch.
운영 DB/네트워크/실 popbill 불사용. split_supply_vat 부재는 AST import 검사만 사용.
"""
import ast
import uuid
from pathlib import Path

import pytest

import services.invoice_svc as inv
import services.tax_invoice_processor_svc as proc

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


# ── FakeSupabase ──
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
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
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


class MockTax:
    """popbill seam mock — registIssue 호출수/인자 기록."""
    def __init__(self, fail=False):
        self.calls = []; self.fail = fail
    def issue_tax(self, conf, **kw):
        self.calls.append(kw)
        if self.fail:
            raise Exception("popbill down")
        return {"nts": "NTS-123", "code": 1, "message": "ok"}
    def issue_cash(self, conf, **kw):
        self.calls.append(kw); return {"nts": "CR-123", "code": 1, "message": "ok"}


def _payment(**kw):
    base = {"id": "p1", "status_code": "SUCCESS", "company_id": "co1", "product_type": "DIAGNOSIS",
            "pg_method": "DirectBank", "proof_type": "TAX_INVOICE",
            "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000, "paid_at": "2026-09-01T00:00:00Z"}
    base.update(kw); return base


def _invoicee():
    return {"corpNum": "1234567890", "corpName": "TAI", "ceoName": "심태왕", "email": "a@b.c"}


def _setup_inv(monkeypatch, store, fail=False):
    fake = FakeSupabase(store)
    mock = MockTax(fail=fail)
    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: True)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {"corp_num": "7233901422", "corp_name": "TAI",
        "ceo_name": "심태왕", "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True})
    monkeypatch.setattr(inv, "_popbill_issue_tax", lambda conf, **kw: mock.issue_tax(conf, **kw))
    monkeypatch.setattr(inv, "_popbill_issue_cash", lambda conf, **kw: mock.issue_cash(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc", type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return fake, mock


@pytest.fixture
def inv_env(monkeypatch):
    store = {"payments": [_payment()], "tax_invoices": []}
    fake, mock = _setup_inv(monkeypatch, store)
    return store, fake, mock


# ══ 1. split_supply_vat import 부재 (AST only) ══
def test_no_split_supply_vat_import():
    src = Path(inv.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name)
    assert "split_supply_vat" not in imported


# ══ 2. issuance guard ══
def test_card_tax_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": "Card", "proof_type": "TAX_INVOICE"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "CARD_RECEIPT_IS_EVIDENCE" and mock.calls == []


def test_directbank_taxinvoice_allow(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": "DirectBank", "proof_type": "TAX_INVOICE"})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["status"] == "ISSUED" and len(mock.calls) == 1


def test_vbank_taxinvoice_allow(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": "VBank", "proof_type": None})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["status"] == "ISSUED"


def test_cash_receipt_selected_tax_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": "DirectBank", "proof_type": "CASH_RECEIPT"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "CASH_RECEIPT_SELECTED" and mock.calls == []


def test_existing_cash_ledger_tax_deny(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": "ISSUED", "invoice_kind": "ORIGINAL"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "CASH_RECEIPT_EXISTS" and mock.calls == []


# ══ 3. 금액/supply_date ══
def test_stored_amounts_exact(inv_env):
    store, fake, mock = inv_env
    inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert mock.calls[0]["supply"] == 100000 and mock.calls[0]["tax"] == 10000 and mock.calls[0]["total"] == 110000


def test_amount_mismatch_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"supply_amount": 100000, "vat_amount": 10000, "total_amount": 999999})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "PAYMENT_AMOUNT_INCONSISTENT" and mock.calls == []


def test_supply_date_exact(inv_env):
    store, fake, mock = inv_env
    inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert mock.calls[0]["write_date"] == "20260905"


def test_supply_date_missing_deny(inv_env):
    store, fake, mock = inv_env
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), None)
    assert e.value.code == "SUPPLY_DATE_REQUIRED" and mock.calls == []


# ══ 4. ledger lifecycle ══
def test_first_issue_original(inv_env):
    store, fake, mock = inv_env
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    row = store["tax_invoices"][0]
    assert row["invoice_kind"] == "ORIGINAL" and row["status"] == "ISSUED" and res["invoice_id"] == row["id"]


def test_popbill_failure_marks_failed(monkeypatch):
    store = {"payments": [_payment()], "tax_invoices": []}
    fake, mock = _setup_inv(monkeypatch, store, fail=True)
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "ISSUE_FAILED"
    assert store["tax_invoices"][0]["status"] == "FAILED"
    assert len(mock.calls) == 1


def test_failed_retry_same_mgt_key_no_new_row(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "FAILED"})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["invoice_id"] == "inv1"
    assert store["tax_invoices"][0]["mgt_key"] == "TX-p1"
    assert len(store["tax_invoices"]) == 1
    assert store["tax_invoices"][0]["status"] == "ISSUED"


def test_existing_issued_no_reissue(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "ISSUED", "nts_confirm_num": "N9"})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["invoice_id"] == "inv1" and res["nts_confirm_num"] == "N9" and mock.calls == []


# ══ 5. gate (invoice_svc) ══
def test_gate_off_no_mutation(inv_env, monkeypatch):
    store, fake, mock = inv_env
    monkeypatch.setattr(inv, "invoice_live", lambda: False)
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.status_code == 423
    assert store["tax_invoices"] == [] and mock.calls == []


# ══ 6. processor (SIMPLE) ══
def _req(status="REQUESTED", **kw):
    base = {"id": "r1", "payment_id": "p1", "company_id": "co1", "status": status, "doc_type": "TAX_INVOICE",
            "invoicee_business_number": "1234567890", "invoicee_company_name": "TAI",
            "invoicee_representative_name": "심태왕", "invoicee_email": "a@b.c"}
    base.update(kw); return base


def _pstore(req=None):
    return {"tax_invoice_requests": [req or _req()]}


def test_processor_gate_off_423_no_mutation(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: False)
    store = _pstore(); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.status_code == 423
    assert store["tax_invoice_requests"][0]["status"] == "REQUESTED"


def test_processor_requested_to_issued(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice",
                        lambda pid, invoicee, sd, created_by=None: {"invoice_id": "inv9", "nts_confirm_num": "N", "status": "ISSUED"})
    store = _pstore(); sb = FakeSupabase(store)
    row, outcome = proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert outcome == "ISSUED"
    assert store["tax_invoice_requests"][0]["status"] == "ISSUED"
    assert store["tax_invoice_requests"][0]["tax_invoice_id"] == "inv9"


def test_processor_failure_marks_failed(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    def _boom(pid, invoicee, sd, created_by=None):
        raise inv.InvoiceError(400, "popbill down", "ISSUE_FAILED")
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", _boom)
    store = _pstore(); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError):
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert store["tax_invoice_requests"][0]["status"] == "FAILED"


def test_processor_cancelled_no_issue(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    store = _pstore(req=_req(status="CANCELLED")); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.status_code == 409 and called["n"] == 0


def test_processor_issued_idempotent(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    store = _pstore(req=_req(status="ISSUED", tax_invoice_id="inv1")); sb = FakeSupabase(store)
    row, outcome = proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert outcome == "ISSUED" and called["n"] == 0


def test_processor_missing_supply_date_no_mutation(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", None, "admin")
    assert e.value.code == "SUPPLY_DATE_REQUIRED"
    assert store["tax_invoice_requests"][0]["status"] == "REQUESTED"


def test_processor_invoicee_incomplete(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(req=_req(invoicee_business_number=None)); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.code == "INVOICEE_INCOMPLETE"


# ══ 7. security role 001 ══
def _client_role(role):
    app = FastAPI(); app.include_router(pl.router)
    app.dependency_overrides[_gcu] = lambda: {"id": "u1", "role_code": role, "company_id": "co1"}
    return TestClient(app)


@requires_client
def test_non_admin_403():
    c = _client_role("012")
    assert c.post("/payments/ops/gate/activate", json={"channel": "INVOICE_LIVE", "confirm": True}).status_code == 403
    assert c.post("/payments/p1/invoice/tax", json={"corpNum": "1", "corpName": "a", "ceoName": "b", "supply_date": "2026-09-05"}).status_code == 403
    assert c.post("/payments/p1/invoice/cash", json={"trade_usage": "지출증빙용", "identity_num": "1"}).status_code == 403
    assert c.post("/payments/tax-invoice-requests/r1/process", json={"supply_date": "2026-09-05"}).status_code == 403


@requires_client
def test_admin_direct_tax_requires_supply_date():
    c = _client_role("001")
    r = c.post("/payments/p1/invoice/tax", json={"corpNum": "1", "corpName": "a", "ceoName": "b"})
    assert r.status_code == 422
