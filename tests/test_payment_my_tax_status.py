"""FE-0-2 PATCH-1: /payments/my 세금계산서 상태(tax_status) 파생 단위테스트.

doc_type=TAX_INVOICE 경계 + UNKNOWN(조회 실패) 보정 검증.
파생 우선순위: MODIFIED > ISSUED > 최신 TAX_INVOICE 요청 상태 > (둘 다 조회 OK → NONE) > UNKNOWN.
사실(원장) 조회이며 정책 판정 아님. 운영 DB/네트워크 불사용.
"""
import routers.payment_ops as pops


class _Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, store, table, fail_tables):
        self.store = store
        self.table = table
        self.fail_tables = fail_tables
        self._eqs = []
        self._in = None
        self._order = None
        self._range = None

    def select(self, *a, **k):
        return self

    def eq(self, c, v):
        self._eqs.append((c, v))
        return self

    def in_(self, c, vals):
        self._in = (c, set(str(x) for x in vals))
        return self

    def order(self, c, desc=False):
        self._order = (c, desc)
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    def execute(self):
        if self.table in self.fail_tables:
            raise RuntimeError("simulated lookup failure: " + self.table)
        rows = list(self.store.get(self.table, []))
        for c, v in self._eqs:
            rows = [r for r in rows if str(r.get(c)) == str(v)]
        if self._in:
            col, vals = self._in
            rows = [r for r in rows if str(r.get(col)) in vals]
        count = len(rows)
        if self._order:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: (r.get(col) or ''), reverse=bool(desc))
        if self._range:
            a, b = self._range
            rows = rows[a:b + 1]
        return _Res([dict(r) for r in rows], count)


class FakeSupabase:
    def __init__(self, store, fail_tables=None):
        self.store = store
        self.fail_tables = set(fail_tables or [])

    def table(self, name):
        return _Q(self.store, name, self.fail_tables)


def _items(store, monkeypatch, fail_tables=None):
    f = FakeSupabase(store, fail_tables=fail_tables)
    monkeypatch.setattr(pops, "get_supabase", lambda: f)
    out = pops.list_my_payments(
        status_code=None, product_type=None, page=1, size=50,
        current_user={"id": "u1", "company_id": "co1"},
    )
    return {r["id"]: r for r in out["data"]["items"]}


def _pay(pid):
    return {"id": pid, "company_id": "co1", "created_at": "2026-09-01"}


# T1 CASH_RECEIPT ORIGINAL ISSUED only → NONE (현금영수증은 tax_status 에 참여 안함)
def test_t1_cash_receipt_not_issued(monkeypatch):
    store = {
        "payments": [_pay("pc")],
        "tax_invoices": [{"payment_id": "pc", "doc_type": "CASH_RECEIPT", "invoice_kind": "ORIGINAL", "status": "ISSUED"}],
    }
    assert _items(store, monkeypatch)["pc"]["tax_status"] == "NONE"


# T2 CASH_RECEIPT ISSUED + TAX request REQUESTED → REQUESTED
def test_t2_cash_ignored_request_wins(monkeypatch):
    store = {
        "payments": [_pay("pc2")],
        "tax_invoices": [{"payment_id": "pc2", "doc_type": "CASH_RECEIPT", "invoice_kind": "ORIGINAL", "status": "ISSUED"}],
        "tax_invoice_requests": [{"payment_id": "pc2", "doc_type": "TAX_INVOICE", "status": "REQUESTED", "created_at": "2026-09-02T10:00:00"}],
    }
    assert _items(store, monkeypatch)["pc2"]["tax_status"] == "REQUESTED"


# T3 TAX_INVOICE ORIGINAL ISSUED → ISSUED
def test_t3_tax_original_issued(monkeypatch):
    store = {
        "payments": [_pay("p3")],
        "tax_invoices": [{"payment_id": "p3", "doc_type": "TAX_INVOICE", "invoice_kind": "ORIGINAL", "status": "ISSUED"}],
    }
    assert _items(store, monkeypatch)["p3"]["tax_status"] == "ISSUED"


# T4 TAX_INVOICE MODIFIED ISSUED → MODIFIED (원본 ISSUED 동시존재에도 수정 우선)
def test_t4_tax_modified_priority(monkeypatch):
    store = {
        "payments": [_pay("p4")],
        "tax_invoices": [
            {"payment_id": "p4", "doc_type": "TAX_INVOICE", "invoice_kind": "ORIGINAL", "status": "ISSUED"},
            {"payment_id": "p4", "doc_type": "TAX_INVOICE", "invoice_kind": "MODIFIED", "status": "ISSUED"},
        ],
    }
    assert _items(store, monkeypatch)["p4"]["tax_status"] == "MODIFIED"


# T5 invoice lookup 실패 + request 없음 → UNKNOWN (NONE 아님)
def test_t5_unknown_on_invoice_failure(monkeypatch):
    store = {"payments": [_pay("p5")]}
    assert _items(store, monkeypatch, fail_tables=["tax_invoices"])["p5"]["tax_status"] == "UNKNOWN"


# T6 request lookup 실패 + invoice 없음 → UNKNOWN
def test_t6_unknown_on_request_failure(monkeypatch):
    store = {"payments": [_pay("p6")]}
    assert _items(store, monkeypatch, fail_tables=["tax_invoice_requests"])["p6"]["tax_status"] == "UNKNOWN"


# T7 invoice ORIGINAL ISSUED + request lookup 실패 → ISSUED (확정 사실은 부분실패에도 사용)
def test_t7_issued_survives_partial_failure(monkeypatch):
    store = {
        "payments": [_pay("p7")],
        "tax_invoices": [{"payment_id": "p7", "doc_type": "TAX_INVOICE", "invoice_kind": "ORIGINAL", "status": "ISSUED"}],
    }
    assert _items(store, monkeypatch, fail_tables=["tax_invoice_requests"])["p7"]["tax_status"] == "ISSUED"


# T8 둘 다 조회 성공 + 기록 없음 → NONE
def test_t8_none_when_both_ok_no_record(monkeypatch):
    store = {"payments": [_pay("p8")]}
    assert _items(store, monkeypatch)["p8"]["tax_status"] == "NONE"


# FAILED 요청 → FAILED
def test_failed_request(monkeypatch):
    store = {
        "payments": [_pay("pf")],
        "tax_invoice_requests": [{"payment_id": "pf", "doc_type": "TAX_INVOICE", "status": "FAILED", "created_at": "2026-09-02T10:00:00"}],
    }
    assert _items(store, monkeypatch)["pf"]["tax_status"] == "FAILED"


# 최신 요청 ISSUED → ISSUED
def test_latest_request_issued(monkeypatch):
    store = {
        "payments": [_pay("pi")],
        "tax_invoice_requests": [
            {"payment_id": "pi", "doc_type": "TAX_INVOICE", "status": "REQUESTED", "created_at": "2026-09-02T09:00:00"},
            {"payment_id": "pi", "doc_type": "TAX_INVOICE", "status": "ISSUED", "created_at": "2026-09-02T11:00:00"},
        ],
    }
    assert _items(store, monkeypatch)["pi"]["tax_status"] == "ISSUED"


def test_all_rows_have_tax_status(monkeypatch):
    store = {"payments": [_pay("a"), _pay("b")]}
    items = _items(store, monkeypatch)
    assert all("tax_status" in r for r in items.values())
