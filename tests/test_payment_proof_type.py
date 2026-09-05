"""PROOF-TYPE-WRITER 단위테스트 (P1~P16).

결제 생성/승인 시 payments.proof_type 기록만 검증. 운영 DB/네트워크/popbill 불사용.
서비스 get_supabase / 빌링 API seam 을 monkeypatch.

PATCH-1: P2 를 실제 운영 CardBilling writer
  routers.payment_billing._charge_subscription_once() 기준으로 교체(첫결제/반복결제).
"""
import uuid

import pytest

import services.payment_svc as psvc
from schemas.payment import DiagnosisVbankPrepareBody, PrepareBody, VbankPrepareBody

try:
    from pydantic import ValidationError
except Exception:  # noqa: BLE001
    ValidationError = Exception


class _R:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, store, ops, table):
        self.store = store; self.ops = ops; self.table = table
        self._op = None; self._payload = None; self._filters = []
    def select(self, *a, **k): self._op = "select"; return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append((c, v)); return self
    def order(self, *a, **k): return self
    def limit(self, n): return self
    def execute(self):
        self.ops.append((self.table, self._op, self._payload, dict(self._filters)))
        if self._op == "select":
            rows = self.store.get(self.table, [])
            out = [r for r in rows if all(str(r.get(c)) == str(v) for c, v in self._filters)]
            return _R([dict(r) for r in out])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                self.store.setdefault(self.table, []).append(it); out.append(dict(it))
            return _R(out)
        if self._op == "update":
            rows = self.store.get(self.table, [])
            matched = [r for r in rows if all(str(r.get(c)) == str(v) for c, v in self._filters)]
            for r in matched:
                r.update(self._payload)
            return _R([dict(r) for r in matched])
        return _R([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.ops = []
    def table(self, name):
        return _Q(self.store, self.ops, name)


def _inserts(fake, table):
    return [p for (t, op, p, f) in fake.ops if t == table and op == "insert"]


def _updates(fake, table):
    return [p for (t, op, p, f) in fake.ops if t == table and op == "update"]


def _tables_touched(fake, op=None):
    return {t for (t, o, p, f) in fake.ops if op is None or o == op}


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    monkeypatch.setattr(psvc, "get_supabase", lambda: f)
    return f


# P1 Card success -> CARD_RECEIPT
def test_p1_card_success_card_receipt(fake):
    payment = {"id": "p1", "contract_id": None, "product_type": "DIAGNOSIS", "period_months": None}
    psvc.process_card_success(payment, {"tid": "t", "applNum": "a"}, "Card",
                              order_id="o1", goodname="g", price="1000", with_redirect_qs=False)
    ups = _updates(fake, "payments")
    assert ups and ups[0].get("proof_type") == "CARD_RECEIPT"
    assert "tax_invoices" not in _tables_touched(fake)
    assert "tax_invoice_requests" not in _tables_touched(fake)


# P2 실제 운영 CardBilling writer = routers.payment_billing._charge_subscription_once
def _billing_charge_row(monkeypatch, is_recurring):
    import routers.payment_billing as rpb
    f = FakeSupabase()
    monkeypatch.setattr(rpb, "_load_billing_iniapi_key", lambda: "k")
    monkeypatch.setattr(rpb, "_load_client_ip", lambda: "1.1.1.1")
    monkeypatch.setattr(rpb, "_call_billing_charge_api",
                        lambda **kw: {"resultCode": "00", "tid": "t", "payAuthCode": "a"})
    subscription = {"id": "s1", "user_id": "u1", "company_id": "co1",
                    "product_type": "SAAS_INDUSTRY", "plan_code": "IND",
                    "plan_name": "TAI Safe", "amount": 149000,
                    "supply_amount": 135455, "vat_amount": 13545}
    billing_key_row = {"id": "k1", "bill_key": "BK", "mid": "MID"}
    rpb._charge_subscription_once(f, subscription=subscription,
                                  billing_key_row=billing_key_row,
                                  charge_cycle=1, is_recurring=is_recurring)
    ins = _inserts(f, "payments")
    assert ins
    return ins[0]


def test_p2_billing_writer_first_charge(monkeypatch):
    row = _billing_charge_row(monkeypatch, is_recurring=False)
    assert row.get("pg_method") == "CardBilling"
    assert row.get("proof_type") == "CARD_RECEIPT"


def test_p2_billing_writer_recurring(monkeypatch):
    row = _billing_charge_row(monkeypatch, is_recurring=True)
    assert row.get("pg_method") == "CardBilling"
    assert row.get("proof_type") == "CARD_RECEIPT"


def _prepare_row(fake, body):
    psvc.run_inicis_prepare(body)
    ins = _inserts(fake, "payments")
    assert ins
    return ins[0]


# P3 DirectBank + TAX_INVOICE
def test_p3_directbank_tax_invoice(fake):
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=100000,
                       goodname="g", payment_type="DirectBank", proof_type="TAX_INVOICE")
    assert _prepare_row(fake, body).get("proof_type") == "TAX_INVOICE"


def test_p3_directbank_success_preserves(fake):
    payment = {"id": "p1", "contract_id": None, "product_type": "DIAGNOSIS", "period_months": None}
    psvc.process_card_success(payment, {"tid": "t"}, "DirectBank",
                              order_id="o", goodname="g", price="1", with_redirect_qs=False)
    ups = _updates(fake, "payments")
    assert ups and "proof_type" not in ups[0]


# P4 DirectBank + CASH_RECEIPT
def test_p4_directbank_cash_receipt(fake):
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=100000,
                       goodname="g", payment_type="DirectBank", proof_type="CASH_RECEIPT")
    assert _prepare_row(fake, body).get("proof_type") == "CASH_RECEIPT"


# P5 DirectBank legacy NULL
def test_p5_directbank_legacy_null(fake):
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=100000,
                       goodname="g", payment_type="DirectBank")
    assert "proof_type" not in _prepare_row(fake, body)


def _vbank_row(fake, proof):
    body = VbankPrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=100000,
                           goodname="g", proof_type=proof)
    psvc.create_vbank_record(body, "signkey")
    ins = _inserts(fake, "payments")
    assert ins
    return ins[0]


# P6/P7/P8 VBank
def test_p6_vbank_tax_invoice(fake):
    assert _vbank_row(fake, "TAX_INVOICE").get("proof_type") == "TAX_INVOICE"


def test_p7_vbank_cash_receipt(fake):
    assert _vbank_row(fake, "CASH_RECEIPT").get("proof_type") == "CASH_RECEIPT"


def test_p8_vbank_none(fake):
    assert _vbank_row(fake, "NONE").get("proof_type") == "NONE"


def _diag_proxy_proof(monkeypatch, body):
    import routers.payment as rp
    captured = {}
    def _fake_create(proxy, sign_key):
        captured["proof_type"] = proxy.proof_type
        return {"status": "success", "data": {"payment_id": "pX"}}
    monkeypatch.setattr(rp, "create_vbank_record", _fake_create)
    monkeypatch.setattr(rp, "load_sign_key", lambda: "sk")
    f = FakeSupabase()
    monkeypatch.setattr(rp, "get_supabase", lambda: f)
    rp.diagnosis_vbank_prepare(body)
    return captured.get("proof_type"), f


# P9/P10/P11 Diagnosis legacy proof_type priority
def test_p9_diag_legacy_invoice_requested_true(monkeypatch):
    body = DiagnosisVbankPrepareBody(amount=100000, invoice_requested=True)
    proof, f = _diag_proxy_proof(monkeypatch, body)
    assert proof == "TAX_INVOICE"
    assert "diagnosis_purchases" not in _tables_touched(f)


def test_p10_diag_legacy_invoice_requested_false(monkeypatch):
    body = DiagnosisVbankPrepareBody(amount=100000, invoice_requested=False)
    proof, f = _diag_proxy_proof(monkeypatch, body)
    assert proof == "NONE"


def test_p11_diag_explicit_over_legacy(monkeypatch):
    body = DiagnosisVbankPrepareBody(amount=100000, invoice_requested=True, proof_type="CASH_RECEIPT")
    proof, f = _diag_proxy_proof(monkeypatch, body)
    assert proof == "CASH_RECEIPT"


# P12/P13 validation 422
def test_p12_client_card_receipt_rejected():
    with pytest.raises(ValidationError):
        PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=1,
                    goodname="g", proof_type="CARD_RECEIPT")


def test_p13_invalid_proof_type_rejected():
    with pytest.raises(ValidationError):
        VbankPrepareBody(product_type="DIAGNOSIS", amount=1, goodname="g", proof_type="FOO")


# P14 process_vbank_deposit -> proof_type mutation 0
def test_p14_vbank_deposit_no_proof_mutation(fake):
    fake.store["payments"] = [{"id": "p1", "status_code": "PENDING", "user_id": None,
                               "company_id": None, "total_amount": 11000, "product_type": "DIAGNOSIS",
                               "matching_contract_id": None, "inicis_order_id": "oid1"}]
    psvc.process_vbank_deposit("oid1", "00", "입금자", {"raw": 1})
    ups = _updates(fake, "payments")
    assert ups
    assert all("proof_type" not in u for u in ups)


# P16 prepare 경로 invoice 테이블 미접촉
def test_p16_prepare_no_invoice_tables(fake):
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=100000,
                       goodname="g", proof_type="TAX_INVOICE")
    psvc.run_inicis_prepare(body)
    touched = _tables_touched(fake)
    assert "tax_invoices" not in touched and "tax_invoice_requests" not in touched
