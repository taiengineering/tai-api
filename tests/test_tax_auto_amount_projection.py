"""WO-TAX-INVOICE-AUTO-01 STEP 5 — admin payment_ledger 3분할 금액 투영.

계약:
  admin list  → items[i].supply_amount + vat_amount + total_amount (기존 total 유지)
  admin detail → payment.supply_amount + vat_amount + total_amount (기존 amount 하위호환 유지)
  값 SoT: request snapshot 우선, payments fallback. 재계산 0(total/1.1 등 프론트 계산 금지).

QA 목업 값(499,000 / 49,900 / 548,900) 이 3분할 필드로 그대로 노출되는지 검증.
"""
from __future__ import annotations

import uuid

import pytest

import routers.payment_ledger as pl


# ── FakeSupabase (payment_ledger admin 라우터는 many-column select 지원 필요) ──
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []; self._cols = "*"
        self._count_exact = False; self._range = None; self._order = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        if k.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def gte(self, c, v): self._filters.append(("gte", c, v)); return self
    def lte(self, c, v): self._filters.append(("lte", c, v)); return self
    def limit(self, n): self._limit = n; return self
    def order(self, col, *, desc=False, **k): self._order = (col, desc); return self
    def range(self, s, e): self._range = (s, e); return self
    def or_(self, expr): return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
                return False
            if op == "gte" and (row.get(c) is None or str(row.get(c)) < str(v)):
                return False
            if op == "lte" and (row.get(c) is None or str(row.get(c)) > str(v)):
                return False
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
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            if self._order:
                col, desc = self._order
                matched = sorted(matched, key=lambda r: (r.get(col) or ""), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e + 1]
            elif self._limit is not None:
                matched = matched[:self._limit]
            return _Result([self._project(r) for r in matched],
                           count=total if self._count_exact else None)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
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


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    from routers.auth import get_current_user
    from routers.matching_deps import _require_admin
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


ADMIN_USER = {"id": "u-admin", "company_id": "co-tai", "role_code": "001",
              "factory_id": None, "team_id": None}


def _qa_mock_store():
    """QA 목업 형태: total 548,900원 (499,000 supply + 49,900 vat)."""
    payment = {
        "id": "pay-qa", "company_id": "co-1",
        "supply_amount": 499000, "vat_amount": 49900, "total_amount": 548900,
        "pg_method": "DirectBank", "proof_type": "TAX_INVOICE",
        "paid_at": "2026-09-06T00:00:00Z", "product_type": "SAAS_INDUSTRIAL",
    }
    request = {
        "id": "req-qa", "payment_id": "pay-qa", "company_id": "co-1",
        "source": "AUTO_PAYMENT", "status": "ISSUED", "doc_type": "TAX_INVOICE",
        "requested_at": "2026-09-06T00:00:00Z", "created_at": "2026-09-06T00:00:00Z",
        "invoicee_company_name": "테스트 주식회사", "invoicee_business_number": "1234567890",
        "proof_type": "TAX_INVOICE",
        "supply_amount": 499000, "vat_amount": 49900, "total_amount": 548900,
        "supply_date": "2026-09-06",
    }
    return {
        "payments": [payment],
        "companies": [{"id": "co-1", "name": "테스트 주식회사", "business_number": "1234567890"}],
        "tax_invoice_requests": [request],
        "tax_invoices": [],  # 원장 조회는 fail-safe (empty ok)
    }


def _client(store, monkeypatch):
    fake = FakeSupabase(store)
    monkeypatch.setattr(pl, "get_supabase", lambda: fake)
    # _attach_tax_status 내부에서도 get_supabase 를 참조하므로 payment_ops 도 patch
    from routers import payment_ops
    monkeypatch.setattr(payment_ops, "get_supabase", lambda: fake)
    app = FastAPI()
    app.include_router(pl.router)
    app.dependency_overrides[_require_admin] = lambda: ADMIN_USER
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    return TestClient(app)


# ═════════════════════════════════════════════════════════════════════
# A1  admin list: 3분할 필드 노출 (기존 total_amount 유지)
# ═════════════════════════════════════════════════════════════════════
@requires_client
def test_A1_admin_list_projects_supply_vat_total(monkeypatch):
    c = _client(_qa_mock_store(), monkeypatch)
    r = c.get("/payments/admin/tax-invoices")
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert len(items) == 1
    it = items[0]
    # 기존 total_amount 유지 (하위 호환)
    assert it["total_amount"] == 548900
    # 신규 3분할 필드
    assert it["supply_amount"] == 499000
    assert it["vat_amount"] == 49900
    # 재계산 0 검증: total - supply = vat, supply + vat = total
    assert it["supply_amount"] + it["vat_amount"] == it["total_amount"]


# ═════════════════════════════════════════════════════════════════════
# A2  admin detail: payment 섹션 3분할 필드 (기존 amount 하위호환 유지)
# ═════════════════════════════════════════════════════════════════════
@requires_client
def test_A2_admin_detail_payment_3part(monkeypatch):
    c = _client(_qa_mock_store(), monkeypatch)
    r = c.get("/payments/admin/tax-invoices/req-qa")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    pay = data["payment"]
    # 기존 필드 유지 (하위 호환)
    assert pay["amount"] == 548900
    # 신규 3분할 필드
    assert pay["supply_amount"] == 499000
    assert pay["vat_amount"] == 49900
    assert pay["total_amount"] == 548900


# ═════════════════════════════════════════════════════════════════════
# A3  fallback: request snapshot 값이 null 이면 payments SoT 로 폴백
# ═════════════════════════════════════════════════════════════════════
@requires_client
def test_A3_fallback_from_payments_when_snapshot_null(monkeypatch):
    store = _qa_mock_store()
    # request snapshot 을 null 로 (구 데이터 시뮬레이션)
    store["tax_invoice_requests"][0]["supply_amount"] = None
    store["tax_invoice_requests"][0]["vat_amount"] = None
    store["tax_invoice_requests"][0]["total_amount"] = None
    c = _client(store, monkeypatch)
    r = c.get("/payments/admin/tax-invoices")
    it = r.json()["data"]["items"][0]
    # payments SoT 로 폴백
    assert it["supply_amount"] == 499000
    assert it["vat_amount"] == 49900
    assert it["total_amount"] == 548900


# ═════════════════════════════════════════════════════════════════════
# A4  회귀: 서버 코드에 프론트/서버 재계산 힌트 없음 (AST 로 실제 코드만 검사)
#         docstring 언급은 허용 — 실제 재계산 표현식만 금지.
# ═════════════════════════════════════════════════════════════════════
def test_A4_no_server_side_amount_recompute():
    import ast
    import inspect
    src = inspect.getsource(pl)
    tree = ast.parse(src)
    # 실제 코드에서 total_amount / 1.1 형태 BinOp 검색
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Mult)):
            # left/right 조합 확인
            left = ast.unparse(node.left) if hasattr(ast, "unparse") else ""
            right = ast.unparse(node.right) if hasattr(ast, "unparse") else ""
            expr = f"{left}{'/' if isinstance(node.op, ast.Div) else '*'}{right}"
            forbidden = ("total_amount/1.1", "total_amount * 10", "total_amount/11")
            for pat in forbidden:
                assert pat.replace(" ", "") not in expr.replace(" ", ""), (
                    f"서버측 금액 재계산 금지: {expr}"
                )
    # 3분할은 반드시 request/payments SoT 에서 유래
    assert "supply_amount" in src
    assert "vat_amount" in src
