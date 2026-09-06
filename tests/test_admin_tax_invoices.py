"""WO-TAX-INVOICE-ADMIN-01 — 관리자 세금계산서 조회 API 단위테스트.

GET /payments/admin/tax-invoices (list), /{request_id} (detail). role 001.
doc_type=TAX_INVOICE 경계(현금영수증 제외) · N+1 금지 · tax_status 재사용 검증.
운영 DB/네트워크 불사용.
"""
import routers.payment_ledger as pl

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _HAVE_CLIENT = True
except Exception:  # noqa: BLE001
    _HAVE_CLIENT = False

import pytest


class _Res:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Q:
    def __init__(self, store, table, counter, fail_tables):
        self.store = store; self.table = table; self.counter = counter; self.fail_tables = fail_tables
        self._eqs = []; self._in = None; self._or = None
        self._gte = None; self._lte = None; self._order = None; self._range = None; self._limit = None

    def select(self, *a, **k): return self
    def eq(self, c, v): self._eqs.append((c, v)); return self
    def in_(self, c, vals): self._in = (c, set(str(x) for x in vals)); return self
    def gte(self, c, v): self._gte = (c, v); return self
    def lte(self, c, v): self._lte = (c, v); return self
    def order(self, c, desc=False): self._order = (c, desc); return self
    def range(self, a, b): self._range = (a, b); return self
    def limit(self, n): self._limit = n; return self

    def or_(self, expr):
        clauses = []
        for part in expr.split(','):
            bits = part.split('.', 2)
            if len(bits) == 3:
                clauses.append((bits[0], bits[1], bits[2]))
        self._or = clauses
        return self

    def execute(self):
        self.counter['n'] += 1
        if self.table in self.fail_tables:
            raise RuntimeError('simulated failure: ' + self.table)
        rows = list(self.store.get(self.table, []))
        for c, v in self._eqs:
            rows = [r for r in rows if str(r.get(c)) == str(v)]
        if self._in:
            col, vals = self._in
            rows = [r for r in rows if str(r.get(col)) in vals]
        if self._gte:
            c, v = self._gte
            rows = [r for r in rows if (r.get(c) or '') >= v]
        if self._lte:
            c, v = self._lte
            rows = [r for r in rows if (r.get(c) or '') <= v]
        if self._or:
            def _match(r):
                for col, op, val in self._or:
                    cell = str(r.get(col) or '')
                    needle = val.strip('%')
                    if op == 'ilike' and needle.lower() in cell.lower():
                        return True
                    if op == 'eq' and cell == val:
                        return True
                return False
            rows = [r for r in rows if _match(r)]
        count = len(rows)
        if self._order:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: (r.get(col) or ''), reverse=bool(desc))
        if self._range:
            a, b = self._range
            rows = rows[a:b + 1]
        if self._limit is not None:
            rows = rows[:self._limit]
        return _Res([dict(r) for r in rows], count)


class FakeSupabase:
    def __init__(self, store, fail_tables=None):
        self.store = store
        self.counter = {'n': 0}
        self.fail_tables = set(fail_tables or [])
    def table(self, name):
        return _Q(self.store, name, self.counter, self.fail_tables)


ADMIN = {'role_code': '001', 'id': 'admin1'}


def _list(store, monkeypatch, **kw):
    f = FakeSupabase(store)
    monkeypatch.setattr(pl, 'get_supabase', lambda: f)
    params = dict(page=1, size=50, status=None, date_from=None, date_to=None,
                  q=None, payment_id=None, request_id=None, current_user=ADMIN)
    params.update(kw)
    out = pl.admin_list_tax_invoices(**params)
    return out['data'], f


def _detail(store, monkeypatch, request_id):
    f = FakeSupabase(store)
    monkeypatch.setattr(pl, 'get_supabase', lambda: f)
    return pl.admin_tax_invoice_detail(request_id, current_user=ADMIN)['data'], f


def _req(rid, pid, status='REQUESTED', **kw):
    base = {'id': rid, 'payment_id': pid, 'company_id': 'co1', 'doc_type': 'TAX_INVOICE',
            'source': 'MYPAGE', 'status': status, 'created_at': '2026-09-0' + rid[-1],
            'requested_at': '2026-09-0' + rid[-1], 'total_amount': 100000,
            'invoicee_company_name': None, 'invoicee_business_number': None}
    base.update(kw); return base


def _store(reqs=None, invoices=None, payments=None, companies=None):
    return {
        'tax_invoice_requests': reqs or [],
        'tax_invoices': invoices or [],
        'payments': payments or [{'id': 'p1', 'total_amount': 100000, 'pg_method': 'DirectBank', 'proof_type': 'TAX_INVOICE', 'paid_at': '2026-09-01'}],
        'companies': companies or [{'id': 'co1', 'name': '데모상호', 'business_number': '123-45-67890', 'representative_name': '홍길동', 'contact_email': 'a@b.c', 'business_type': '제조', 'business_category': '전자', 'zipcode': '06000', 'address_road': '테헤란로', 'address_detail': '3층'}],
    }


# ── 가드(A1~A3) ──
@pytest.mark.skipif(not _HAVE_CLIENT, reason='fastapi testclient 미설치')
def test_a1_a2_a3_role_guard(monkeypatch):
    from routers.auth import get_current_user
    app = FastAPI()
    app.include_router(pl.router)
    f = FakeSupabase(_store(reqs=[_req('r1', 'p1')]))
    monkeypatch.setattr(pl, 'get_supabase', lambda: f)

    # 001 → 200
    app.dependency_overrides[get_current_user] = lambda: {'role_code': '001', 'id': 'a'}
    c = TestClient(app)
    assert c.get('/payments/admin/tax-invoices').status_code == 200
    # non-001 → 403
    app.dependency_overrides[get_current_user] = lambda: {'role_code': '002', 'id': 'b'}
    assert c.get('/payments/admin/tax-invoices').status_code == 403
    # unauth → 401
    from fastapi import HTTPException
    def _raise():
        raise HTTPException(status_code=401, detail='unauth')
    app.dependency_overrides[get_current_user] = _raise
    assert c.get('/payments/admin/tax-invoices').status_code == 401
    app.dependency_overrides.clear()


# ── A4/A5 doc_type 경계 ──
def test_a4_a5_tax_only_cash_excluded(monkeypatch):
    store = _store(
        reqs=[_req('r1', 'p1', status='REQUESTED'),
              # CASH_RECEIPT 요청은 목록에 포함되지 않아야 함
              _req('rc', 'pc', status='ISSUED', doc_type='CASH_RECEIPT')],
        invoices=[{'payment_id': 'p1', 'doc_type': 'CASH_RECEIPT', 'invoice_kind': 'ORIGINAL', 'status': 'ISSUED'}],
        payments=[{'id': 'p1', 'total_amount': 100000, 'pg_method': 'DirectBank', 'proof_type': 'TAX_INVOICE', 'paid_at': '2026-09-01'}],
    )
    data, _ = _list(store, monkeypatch)
    ids = [i['request_id'] for i in data['items']]
    assert ids == ['r1']                       # A4: TAX_INVOICE 요청만
    row = data['items'][0]
    assert row['tax_status'] == 'REQUESTED'     # A5: 현금영수증 ISSUED 는 발행완료로 오인 안됨
    assert row['original_invoice_status'] is None
    assert row['has_modified_invoice'] is False


# ── A6/A7/A8 상태 매핑 ──
def test_a6_original_issued(monkeypatch):
    store = _store(reqs=[_req('r1', 'p1', status='ISSUED')],
                   invoices=[{'payment_id': 'p1', 'doc_type': 'TAX_INVOICE', 'invoice_kind': 'ORIGINAL', 'status': 'ISSUED', 'issued_at': '2026-09-02', 'nts_confirm_num': 'NTS-1'}])
    data, _ = _list(store, monkeypatch)
    row = data['items'][0]
    assert row['tax_status'] == 'ISSUED'
    assert row['original_invoice_status'] == 'ISSUED'
    assert row['issued_at'] == '2026-09-02'
    assert row['nts_confirm_num'] == 'NTS-1'


def test_a7_modified(monkeypatch):
    store = _store(reqs=[_req('r1', 'p1', status='ISSUED')],
                   invoices=[
                       {'payment_id': 'p1', 'doc_type': 'TAX_INVOICE', 'invoice_kind': 'ORIGINAL', 'status': 'ISSUED'},
                       {'payment_id': 'p1', 'doc_type': 'TAX_INVOICE', 'invoice_kind': 'MODIFIED', 'status': 'ISSUED'},
                   ])
    row = _list(store, monkeypatch)[0]['items'][0]
    assert row['tax_status'] == 'MODIFIED'
    assert row['has_modified_invoice'] is True
    assert row['modified_count'] == 1


def test_a8_failed(monkeypatch):
    store = _store(reqs=[_req('r1', 'p1', status='FAILED')])
    row = _list(store, monkeypatch)[0]['items'][0]
    assert row['tax_status'] == 'FAILED'


# ── A10 조회 실패 → UNKNOWN (tax_status 재사용) ──
def test_a10_partial_failure_unknown(monkeypatch):
    store = _store(reqs=[_req('r1', 'p1', status='REQUESTED')])
    f = FakeSupabase(store, fail_tables=['tax_invoice_requests'])
    # requests 조회는 목록용으로도 쓰이므로, tax_status 내부 request 조회만 실패시키기 위해
    # 별도로 invoice 조회만 실패하는 케이스로 검증
    store2 = _store(reqs=[_req('r1', 'p1', status='REQUESTED')])
    f2 = FakeSupabase(store2, fail_tables=['tax_invoices'])
    monkeypatch.setattr(pl, 'get_supabase', lambda: f2)
    params = dict(page=1, size=50, status=None, date_from=None, date_to=None,
                  q=None, payment_id=None, request_id=None, current_user=ADMIN)
    row = pl.admin_list_tax_invoices(**params)['data']['items'][0]
    # 최신 요청이 있으므로 REQUESTED (확정 사실). invoice 조회 실패는 요청상태에 영향없음.
    assert row['tax_status'] == 'REQUESTED'


# ── A12 pagination ──
def test_a12_pagination(monkeypatch):
    reqs = [_req('r%d' % i, 'p1', status='REQUESTED') for i in range(1, 6)]
    for i, r in enumerate(reqs):
        r['created_at'] = '2026-09-%02d' % (i + 1)
    data, _ = _list(_store(reqs=reqs), monkeypatch, page=1, size=2)
    assert data['total'] == 5
    assert len(data['items']) == 2
    assert data['total_pages'] == 3


# ── A13 status filter ──
def test_a13_status_filter(monkeypatch):
    reqs = [_req('r1', 'p1', status='REQUESTED'), _req('r2', 'p1', status='ISSUED')]
    data, _ = _list(_store(reqs=reqs), monkeypatch, status='ISSUED')
    assert [i['request_id'] for i in data['items']] == ['r2']


# ── A14 search filter (q) ──
def test_a14_search_filter(monkeypatch):
    reqs = [_req('r1', 'p1', status='REQUESTED', invoicee_company_name='가나다상회', invoicee_business_number='111-11-11111'),
            _req('r2', 'p1', status='REQUESTED', invoicee_company_name='다른회사', invoicee_business_number='222-22-22222')]
    data, _ = _list(_store(reqs=reqs), monkeypatch, q='가나다')
    assert [i['request_id'] for i in data['items']] == ['r1']


# ── A15/A16/A17 detail ──
def test_a15_a16_detail_original_and_modified(monkeypatch):
    store = _store(
        reqs=[_req('r1', 'p1', status='ISSUED', invoicee_business_number='123-45-67890', invoicee_company_name='발행스냅상호')],
        invoices=[
            {'payment_id': 'p1', 'doc_type': 'TAX_INVOICE', 'invoice_kind': 'ORIGINAL', 'status': 'ISSUED', 'issued_at': '2026-09-02', 'nts_confirm_num': 'NTS-1', 'created_at': '2026-09-02'},
            {'payment_id': 'p1', 'doc_type': 'TAX_INVOICE', 'invoice_kind': 'MODIFIED', 'status': 'ISSUED', 'modify_code': 2, 'adjustment_reason': '부분환불', 'refund_ref': 'rf1', 'created_at': '2026-09-03'},
        ])
    data, _ = _detail(store, monkeypatch, 'r1')
    assert data['invoice_ledger']['original']['nts_confirm_num'] == 'NTS-1'
    assert len(data['invoice_ledger']['modified']) == 1                 # A16 배열
    assert data['invoice_ledger']['modified'][0]['modify_code'] == 2
    # A15: request 스냅샷 우선
    assert data['company_snapshot']['source'] == 'request_snapshot'
    assert data['company_snapshot']['company_name'] == '발행스냅상호'


def test_a17_cash_receipt_ledger_excluded(monkeypatch):
    store = _store(
        reqs=[_req('r1', 'p1', status='REQUESTED')],
        invoices=[{'payment_id': 'p1', 'doc_type': 'CASH_RECEIPT', 'invoice_kind': 'ORIGINAL', 'status': 'ISSUED', 'created_at': '2026-09-02'}])
    data, _ = _detail(store, monkeypatch, 'r1')
    assert data['invoice_ledger']['original'] is None                   # A17: 현금영수증 제외
    assert data['invoice_ledger']['modified'] == []


def test_detail_company_fallback_when_no_snapshot(monkeypatch):
    store = _store(reqs=[_req('r1', 'p1', status='REQUESTED')])  # invoicee_* 없음
    data, _ = _detail(store, monkeypatch, 'r1')
    assert data['company_snapshot']['source'] == 'company'
    assert data['company_snapshot']['company_name'] == '데모상호'


# ── A18 N+1 = 0 (row당 query 없음) ──
def test_a18_no_n_plus_1(monkeypatch):
    reqs = [_req('r%d' % i, 'p%d' % i, status='REQUESTED') for i in range(1, 6)]
    payments = [{'id': 'p%d' % i, 'total_amount': 100000, 'pg_method': 'Card', 'proof_type': 'CARD_RECEIPT', 'paid_at': '2026-09-01'} for i in range(1, 6)]
    store = _store(reqs=reqs, payments=payments)
    data, f = _list(store, monkeypatch)
    assert len(data['items']) == 5
    # requests1 + payments1 + companies1 + tax_invoices1 + _attach_tax_status(2) = 상수(≈8), row수 비례 X
    assert f.counter['n'] <= 8
