"""FE-0: /payments/my proof_type projection 단위테스트 (A1~A8).

list_my_payments 가 payments 테이블을 proof_type 포함 투영으로 조회하고,
company ownership(토큰 company_id)을 유지하며, envelope가 변하지 않음을 검증.
운영 DB/네트워크 불사용. get_supabase 를 monkeypatch.
"""
import routers.payment_ops as pops


class _Res:
    def __init__(self, data, count):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self._filters = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, *a, **k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = [
            r for r in self.store.get(self.table, [])
            if all(str(r.get(c)) == str(v) for c, v in self._filters)
        ]
        count = len(rows)
        rng = getattr(self, "_range", None)
        if rng:
            rows = rows[rng[0]:rng[1] + 1]
        return _Res(rows, count)


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Q(self.store, name)


def _seed():
    return {
        "payments": [
            {"id": "p1", "company_id": "co1", "proof_type": "CARD_RECEIPT", "created_at": "2026-09-01"},
            {"id": "p2", "company_id": "co1", "proof_type": "TAX_INVOICE", "created_at": "2026-09-02"},
            {"id": "p3", "company_id": "co1", "proof_type": "CASH_RECEIPT", "created_at": "2026-09-03"},
            {"id": "p4", "company_id": "co1", "proof_type": "NONE", "created_at": "2026-09-04"},
            {"id": "p5", "company_id": "co1", "proof_type": None, "created_at": "2026-09-05"},
            {"id": "x1", "company_id": "co2", "proof_type": "TAX_INVOICE", "created_at": "2026-09-06"},
        ]
    }


def _call(monkeypatch, company_id="co1"):
    f = FakeSupabase(_seed())
    monkeypatch.setattr(pops, "get_supabase", lambda: f)
    out = pops.list_my_payments(
        status_code=None, product_type=None, page=1, size=50,
        current_user={"id": "u1", "company_id": company_id},
    )
    return out["data"]


def _items(data):
    return data["items"]


# A1 자기회사 row만 반환
def test_a1_own_company_only(monkeypatch):
    data = _call(monkeypatch)
    ids = {r["id"] for r in _items(data)}
    assert ids == {"p1", "p2", "p3", "p4", "p5"}
    assert "x1" not in ids


# A2 proof_type 포함
def test_a2_proof_type_present(monkeypatch):
    data = _call(monkeypatch)
    assert all("proof_type" in r for r in _items(data))


def _by_id(data):
    return {r["id"]: r for r in _items(data)}


# A3 CARD_RECEIPT exact
def test_a3_card_receipt_exact(monkeypatch):
    assert _by_id(_call(monkeypatch))["p1"]["proof_type"] == "CARD_RECEIPT"


# A4 TAX_INVOICE exact
def test_a4_tax_invoice_exact(monkeypatch):
    assert _by_id(_call(monkeypatch))["p2"]["proof_type"] == "TAX_INVOICE"


# A5 CASH_RECEIPT exact
def test_a5_cash_receipt_exact(monkeypatch):
    assert _by_id(_call(monkeypatch))["p3"]["proof_type"] == "CASH_RECEIPT"


# A6 NONE exact
def test_a6_none_exact(monkeypatch):
    assert _by_id(_call(monkeypatch))["p4"]["proof_type"] == "NONE"


# A7 NULL 그대로 null
def test_a7_null_stays_null(monkeypatch):
    assert _by_id(_call(monkeypatch))["p5"]["proof_type"] is None


# A8 토큰 company_id 기준 scope — 다른 회사로 바꾸면 그 회사만
def test_a8_scope_from_token(monkeypatch):
    data = _call(monkeypatch, company_id="co2")
    ids = {r["id"] for r in _items(data)}
    assert ids == {"x1"}
    # co1 데이터 누출 없음
    assert "p1" not in ids


# envelope 보존
def test_envelope_preserved(monkeypatch):
    data = _call(monkeypatch)
    assert set(data.keys()) == {"items", "total", "page", "size", "total_pages"}
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["size"] == 50
    assert data["total_pages"] == 1
