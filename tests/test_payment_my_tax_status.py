"""FE-0-2: /payments/my 세금계산서 상태(tax_status) 파생 단위테스트.

_attach_tax_status 가 원장(tax_invoices.payment_id / tax_invoice_requests.payment_id)을
배치 조회해 각 결제행에 tax_status 를 부여하는지 검증.
파생 우선순위: MODIFIED(수정발급) > ISSUED(발행완료) > 최신 요청 상태 > NONE(미발급).
사실(원장) 조회이며 정책 판정 아님. 운영 DB/네트워크 불사용.
"""
import routers.payment_ops as pops


class _Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, store, table):
        self.store = store
        self.table = table
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
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Q(self.store, name)


def _items(store, monkeypatch):
    f = FakeSupabase(store)
    monkeypatch.setattr(pops, "get_supabase", lambda: f)
    out = pops.list_my_payments(
        status_code=None, product_type=None, page=1, size=50,
        current_user={"id": "u1", "company_id": "co1"},
    )
    return {r["id"]: r for r in out["data"]["items"]}


def _base_payments():
    # 모두 co1, created_at 구분
    return [
        {"id": "p_none", "company_id": "co1", "created_at": "2026-09-01"},
        {"id": "p_req", "company_id": "co1", "created_at": "2026-09-02"},
        {"id": "p_issued_req", "company_id": "co1", "created_at": "2026-09-03"},
        {"id": "p_issued_inv", "company_id": "co1", "created_at": "2026-09-04"},
        {"id": "p_mod", "company_id": "co1", "created_at": "2026-09-05"},
        {"id": "p_failed", "company_id": "co1", "created_at": "2026-09-06"},
    ]


def _store():
    return {
        "payments": _base_payments(),
        "tax_invoice_requests": [
            {"payment_id": "p_req", "status": "REQUESTED", "created_at": "2026-09-02T10:00:00"},
            {"payment_id": "p_issued_req", "status": "REQUESTED", "created_at": "2026-09-03T09:00:00"},
            {"payment_id": "p_issued_req", "status": "ISSUED", "created_at": "2026-09-03T11:00:00"},
            {"payment_id": "p_failed", "status": "FAILED", "created_at": "2026-09-06T10:00:00"},
        ],
        "tax_invoices": [
            {"payment_id": "p_issued_inv", "invoice_kind": "ORIGINAL", "status": "ISSUED"},
            {"payment_id": "p_mod", "invoice_kind": "ORIGINAL", "status": "ISSUED"},
            {"payment_id": "p_mod", "invoice_kind": "MODIFIED", "status": "ISSUED"},
        ],
    }


def test_none_when_no_request_or_invoice(monkeypatch):
    assert _items(_store(), monkeypatch)["p_none"]["tax_status"] == "NONE"


def test_requested(monkeypatch):
    assert _items(_store(), monkeypatch)["p_req"]["tax_status"] == "REQUESTED"


def test_issued_via_latest_request(monkeypatch):
    # 최신 요청이 ISSUED → 발행완료
    assert _items(_store(), monkeypatch)["p_issued_req"]["tax_status"] == "ISSUED"


def test_issued_via_invoice(monkeypatch):
    assert _items(_store(), monkeypatch)["p_issued_inv"]["tax_status"] == "ISSUED"


def test_modified_takes_priority(monkeypatch):
    # 원본 ISSUED + 수정 ISSUED 동시존재 → MODIFIED 우선
    assert _items(_store(), monkeypatch)["p_mod"]["tax_status"] == "MODIFIED"


def test_failed(monkeypatch):
    assert _items(_store(), monkeypatch)["p_failed"]["tax_status"] == "FAILED"


def test_envelope_and_all_rows_have_tax_status(monkeypatch):
    out_items = _items(_store(), monkeypatch)
    assert set(out_items.keys()) == {"p_none", "p_req", "p_issued_req", "p_issued_inv", "p_mod", "p_failed"}
    assert all("tax_status" in r for r in out_items.values())


def test_failsoft_when_tax_tables_missing(monkeypatch):
    # tax 테이블 조회가 없어도(빈 store) 결제목록은 정상, tax_status=NONE
    store = {"payments": _base_payments()}
    items = _items(store, monkeypatch)
    assert len(items) == 6
    assert all(r["tax_status"] == "NONE" for r in items.values())
