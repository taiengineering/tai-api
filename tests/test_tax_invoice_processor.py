"""BACKEND-3 issuance guard + processor 단위테스트 (FakeSupabase + popbill mock).

invoice_svc: get_supabase/invoice_live/_popbill_conf/_popbill_issue_tax|cash 를 monkeypatch.
processor: sb 주입 + invoice_svc.issue_tax_invoice/invoice_live monkeypatch.
운영 DB/네트워크/실 popbill 불사용.
"""
import uuid

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
        if self._op == "delete":
            keep = [r for r in rows if not self._match(r)]; rem = [r for r in rows if self._match(r)]
            self.store[self.table] = keep; return _Result([dict(r) for r in rem])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}; self.log = []
    def table(self, name):
        return _Query(self.store, name, self.log)


class MockTax:
    """popbill seam mock — registIssue 호출수/인자 기록."""
    def __init__(self):
        self.calls = []
    def issue_tax(self, conf, **kw):
        self.calls.append(kw); return {"nts": "NTS-123", "code": 1, "message": "ok"}
    def issue_cash(self, conf, **kw):
        self.calls.append(kw); return {"nts": "CR-123", "code": 1, "message": "ok"}


def _payment(**kw):
    base = {"id": "p1", "status_code": "SUCCESS", "company_id": "co1", "product_type": "DIAGNOSIS",
            "pg_method": "DirectBank", "proof_type": "TAX_INVOICE",
            "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000, "paid_at": "2026-09-01T00:00:00Z"}
    base.update(kw); return base


def _invoicee():
    return {"corpNum": "1234567890", "corpName": "TAI", "ceoName": "심태왕", "email": "a@b.c"}


@pytest.fixture
def inv_env(monkeypatch):
    """invoice_svc 를 FakeSupabase + gate ON + popbill mock 으로 설정."""
    store = {"payments": [_payment()], "tax_invoices": []}
    fake = FakeSupabase(store)
    mock = MockTax()
    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: True)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {"corp_num": "7233901422", "corp_name": "TAI",
        "ceo_name": "심태왕", "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True})
    monkeypatch.setattr(inv, "_popbill_issue_tax", lambda conf, **kw: mock.issue_tax(conf, **kw))
    monkeypatch.setattr(inv, "_popbill_issue_cash", lambda conf, **kw: mock.issue_cash(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc", type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return store, fake, mock


# ══ 금액/supply_date (T19~T25) ══
def test_t19_stored_amounts_exact(inv_env):
    store, fake, mock = inv_env
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05", created_by="admin")
    assert res["status"] == "ISSUED"
    assert mock.calls[0]["supply"] == 100000 and mock.calls[0]["tax"] == 10000 and mock.calls[0]["total"] == 110000


def test_t20_split_supply_vat_removed():
    import ast
    from pathlib import Path
    src = Path(inv.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend("{}.{}".format(module, a.name) for a in node.names)
            imports.extend(a.name for a in node.names)
    assert "split_supply_vat" not in imports
    assert "split_supply_vat" not in src.replace("split_supply_vat_removed", "")  # 호출도 없음


def test_t21_amount_mismatch_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"supply_amount": 100000, "vat_amount": 10000, "total_amount": 999999})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "PAYMENT_AMOUNT_INCONSISTENT"
    assert mock.calls == []


def test_t22_t23_supply_date_used_exact(inv_env):
    store, fake, mock = inv_env
    inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert mock.calls[0]["write_date"] == "20260905"  # writeDate + purchaseDT 공통


def test_t24_missing_supply_date_deny(inv_env):
    store, fake, mock = inv_env
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), None)
    assert e.value.code == "SUPPLY_DATE_REQUIRED"
    assert mock.calls == []


def test_t25_no_now_substitution_in_source():
    from pathlib import Path
    src = Path(inv.__file__).read_text(encoding="utf-8")
    # 세금계산서 write_date 에 now 자동대체 없음: writeDate= 는 _fmt_supply_date 결과만
    assert 'write_date = now_kst().strftime("%Y%m%d")' not in src


# ══ issuance guard (T5~T18) ══
@pytest.mark.parametrize("pg,proof,ok", [
    ("DirectBank", "TAX_INVOICE", True),   # T8
    ("VBank", None, True),                  # T9
    ("Card", "TAX_INVOICE", False),         # T6
    ("CardBilling", "TAX_INVOICE", False),  # T6
    ("DirectBank", None, False),            # T7
    ("HPP", "TAX_INVOICE", False),          # T10
    ("VBank", "CASH_RECEIPT", False),       # T11
])
def test_t5_t11_tax_guard(inv_env, pg, proof, ok):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": pg, "proof_type": proof})
    if ok:
        res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
        assert res["status"] == "ISSUED"
    else:
        with pytest.raises(inv.InvoiceError):
            inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
        assert mock.calls == []


def test_t5_not_success_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0]["status_code"] = "PENDING"
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "PAYMENT_NOT_SUCCESS" and mock.calls == []


@pytest.mark.parametrize("cr_status", ["PENDING", "ISSUED", "FAILED"])
def test_t12_t13_cash_exists_deny(inv_env, cr_status):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": cr_status, "invoice_kind": "ORIGINAL"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "CASH_RECEIPT_EXISTS" and mock.calls == []


def test_t14_cash_cancelled_review(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": "CANCELLED", "invoice_kind": "ORIGINAL"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "CASH_RECEIPT_HISTORY_REVIEW" and mock.calls == []


# cash guard (T15~T18)
def test_t15_cash_proof_taxinvoice_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0]["proof_type"] = "TAX_INVOICE"
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_cash_receipt("p1", "지출증빙용", "1234567890")
    assert e.value.code == "PROOF_NOT_CASH_RECEIPT" and mock.calls == []


def test_t16_cash_existing_taxinvoice_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0]["proof_type"] = "CASH_RECEIPT"
    store["tax_invoices"].append({"payment_id": "p1", "doc_type": "TAX_INVOICE", "status": "ISSUED", "invoice_kind": "ORIGINAL"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_cash_receipt("p1", "지출증빙용", "1234567890")
    assert e.value.code == "TAX_INVOICE_EXISTS" and mock.calls == []


def test_t17_cash_proof_cashreceipt_allow(inv_env):
    store, fake, mock = inv_env
    store["payments"][0]["proof_type"] = "CASH_RECEIPT"
    res = inv.issue_cash_receipt("p1", "지출증빙용", "1234567890")
    assert res["status"] == "ISSUED" and len(mock.calls) == 1


def test_t18_cash_card_deny(inv_env):
    store, fake, mock = inv_env
    store["payments"][0].update({"pg_method": "Card", "proof_type": "CASH_RECEIPT"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_cash_receipt("p1", "지출증빙용", "1234567890")
    assert e.value.code == "CARD_RECEIPT_IS_EVIDENCE" and mock.calls == []


# ══ ledger lifecycle (T26~T32) ══
def test_t26_first_issue_original(inv_env):
    store, fake, mock = inv_env
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    row = store["tax_invoices"][0]
    assert row["invoice_kind"] == "ORIGINAL" and row["status"] == "ISSUED" and res["invoice_id"] == row["id"]


def test_t27_t28_t29_failed_retry_same_row(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "FAILED"})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["invoice_id"] == "inv1"                    # T27 same id
    assert store["tax_invoices"][0]["mgt_key"] == "TX-p1"  # T28 same mgt_key
    assert len(store["tax_invoices"]) == 1                 # T29 no new INSERT
    assert store["tax_invoices"][0]["status"] == "ISSUED"


def test_t30_pending_no_popbill(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "PENDING"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "INVOICE_ALREADY_PROCESSING" and mock.calls == []


def test_t31_issued_idempotent_no_popbill(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "ISSUED", "nts_confirm_num": "N9"})
    res = inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert res["invoice_id"] == "inv1" and res["nts_confirm_num"] == "N9" and mock.calls == []


def test_t32_cancelled_no_new_original(inv_env):
    store, fake, mock = inv_env
    store["tax_invoices"].append({"id": "inv1", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "mgt_key": "TX-p1", "status": "CANCELLED"})
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.code == "INVOICE_HISTORY_REVIEW"
    assert len(store["tax_invoices"]) == 1 and mock.calls == []


# ══ gate (T33~T35) ══
def test_t33_t34_t35_gate_off_no_mutation(inv_env, monkeypatch):
    store, fake, mock = inv_env
    monkeypatch.setattr(inv, "invoice_live", lambda: False)
    with pytest.raises(inv.InvoiceError) as e:
        inv.issue_tax_invoice("p1", _invoicee(), "2026-09-05")
    assert e.value.status_code == 423
    assert store["tax_invoices"] == []   # ledger mutation 0
    assert mock.calls == []              # popbill 0


# ══ processor (T33,T36~T45) ══
def _req(status="REQUESTED", **kw):
    base = {"id": "r1", "payment_id": "p1", "company_id": "co1", "status": status, "doc_type": "TAX_INVOICE",
            "supply_amount": 100000, "vat_amount": 10000, "total_amount": 110000,
            "invoicee_business_number": "1234567890", "invoicee_company_name": "TAI",
            "invoicee_representative_name": "심태왕", "invoicee_email": "a@b.c"}
    base.update(kw); return base


def _pstore(req=None, payment=None, tax_invoices=None):
    return {"tax_invoice_requests": [req or _req()], "payments": [payment or _payment()],
            "tax_invoices": list(tax_invoices or [])}


def test_processor_gate_off_423_no_mutation(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: False)
    store = _pstore(); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.status_code == 423
    assert store["tax_invoice_requests"][0]["status"] == "REQUESTED"  # mutation 0


def test_processor_success(monkeypatch):
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


@pytest.mark.parametrize("st,code", [("CANCELLED", 409), ("REVIEW_REQUIRED", 409), ("PROCESSING", 409)])
def test_processor_blocked_states(monkeypatch, st, code):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(req=_req(status=st)); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.status_code == code


def test_processor_issued_idempotent(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    called = {"n": 0}
    def _iss(*a, **k): called["n"] += 1; return {"invoice_id": "x"}
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", _iss)
    store = _pstore(req=_req(status="ISSUED", tax_invoice_id="inv1")); sb = FakeSupabase(store)
    row, outcome = proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert outcome == "ISSUED" and called["n"] == 0  # popbill 0


def test_processor_snapshot_drift_review(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    store = _pstore(payment=_payment(total_amount=110000, vat_amount=10000, supply_amount=100000),
                    req=_req(supply_amount=999999))  # drift
    sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.code == "PAYMENT_SNAPSHOT_DRIFT"
    assert store["tax_invoice_requests"][0]["status"] == "REVIEW_REQUIRED" and called["n"] == 0


def test_processor_invoicee_incomplete_review(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(req=_req(invoicee_business_number=None))
    sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.code == "REQUEST_SNAPSHOT_INCOMPLETE"
    assert store["tax_invoice_requests"][0]["status"] == "REVIEW_REQUIRED"


def test_processor_opposite_cash_review(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(tax_invoices=[{"payment_id": "p1", "doc_type": "CASH_RECEIPT", "status": "ISSUED"}])
    sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert e.value.code == "CASH_RECEIPT_APPEARED"
    assert store["tax_invoice_requests"][0]["status"] == "REVIEW_REQUIRED"


def test_processor_reconciliation(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr("services.invoice_svc.issue_tax_invoice", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    store = _pstore(tax_invoices=[{"id": "inv7", "payment_id": "p1", "doc_type": "TAX_INVOICE",
                                  "invoice_kind": "ORIGINAL", "status": "ISSUED"}])
    sb = FakeSupabase(store)
    row, outcome = proc.process_tax_invoice_request(sb, "r1", "2026-09-05", "admin")
    assert outcome == "RECONCILED" and called["n"] == 0
    assert store["tax_invoice_requests"][0]["tax_invoice_id"] == "inv7"
    assert store["tax_invoice_requests"][0]["status"] == "ISSUED"


def test_processor_missing_supply_date(monkeypatch):
    monkeypatch.setattr("services.invoice_svc.invoice_live", lambda: True)
    store = _pstore(); sb = FakeSupabase(store)
    with pytest.raises(proc.ProcessorError) as e:
        proc.process_tax_invoice_request(sb, "r1", None, "admin")
    assert e.value.code == "SUPPLY_DATE_REQUIRED"
    assert store["tax_invoice_requests"][0]["status"] == "REQUESTED"  # claim 전 차단


# ══ security role 001 (T1~T4) + admin bypass (T46) ══
@requires_client
def _client_role(role):
    app = FastAPI(); app.include_router(pl.router)
    app.dependency_overrides[_gcu] = lambda: {"id": "u1", "role_code": role, "company_id": "co1"}
    return TestClient(app)


@requires_client
def test_t1_t4_non_admin_403():
    c = _client_role("012")
    assert c.post("/payments/ops/gate/activate", json={"channel": "INVOICE_LIVE", "confirm": True}).status_code == 403
    assert c.post("/payments/p1/invoice/tax", json={"corpNum": "1", "corpName": "a", "ceoName": "b", "supply_date": "2026-09-05"}).status_code == 403
    assert c.post("/payments/p1/invoice/cash", json={"trade_usage": "지출증빙용", "identity_num": "1"}).status_code == 403
    assert c.post("/payments/tax-invoice-requests/r1/process", json={"supply_date": "2026-09-05"}).status_code == 403


@requires_client
def test_t46_admin_direct_tax_requires_supply_date():
    # role 001 이라도 supply_date 없으면 422(pydantic) — 옛 로직(now)로 우회 불가
    c = _client_role("001")
    r = c.post("/payments/p1/invoice/tax", json={"corpNum": "1", "corpName": "a", "ceoName": "b"})
    assert r.status_code == 422
