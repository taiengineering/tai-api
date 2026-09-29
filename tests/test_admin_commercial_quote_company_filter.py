"""AQ-COMP-01~05: GET /admin/quotes company_id filter — WO-ADM-COMM-01-PATCH-001.

검증 :
  AQ-COMP-01  company_id=A → A 견적만 반환
  AQ-COMP-02  company_id 없음 → ADMIN_SOURCES 전체 (기존 계약 불변)
  AQ-COMP-03  company_id + source/status 조합 정상
  AQ-COMP-04  non-admin 403 + write=0 회귀
  AQ-COMP-05  DB mutation=0 (SELECT only)
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import admin_quote_svc as svc


# ── FakeSupabase (기존 test_admin_quotes.py 동일 패턴) ───────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._count_exact = False
        self._range = None; self._order = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        if k.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def limit(self, n): self._limit = n; return self
    def order(self, col, *, desc=False, **k): self._order = (col, desc); return self
    def range(self, s, e): self._range = (s, e); return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
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
            projected = [self._project(r) for r in matched]
            return _Result(projected, count=total if self._count_exact else None)
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


def _base_store(quotes=None):
    return {
        "quotes": list(quotes or []),
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "002", "scope_type": "COMPANY"},
        ],
        "companies": [{"id": "C-A", "name": "A사"}, {"id": "C-B", "name": "B사"}],
        "factories": [],
    }


def _q(company_id: str, source: str = "admin_manual", status: str = "ISSUED",
       extra=None) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "source": source,
        "status_code": status,
        "created_at": "2026-09-30T00:00:00+09:00",
        "updated_at": "2026-09-30T00:00:00+09:00",
        "quote_no": f"QN-{company_id}-{source[:2].upper()}",
        "company_name": f"{company_id} 회사",
        "contact_name": "담당자",
        "items": [],
        "supply_amount": 0,
        "vat_amount": 0,
        "total_amount": 0,
    }
    if extra:
        row.update(extra)
    return row


# ── AQ-COMP-01: company_id=A → A 견적만 ─────────────────────────────

def test_AQ_COMP_01_company_id_filter_returns_only_target_company():
    qa = _q("C-A", source="admin_manual")
    qb = _q("C-B", source="admin_manual")
    store = _base_store([qa, qb])
    fake = FakeSupabase(store)

    result = svc.list_admin_quotes(fake, page=1, page_size=20, company_id="C-A")

    ids = [r["company_id"] for r in result["items"]]
    assert all(i == "C-A" for i in ids), f"C-B 견적이 섞임: {ids}"
    assert result["total"] == 1


# ── AQ-COMP-02: company_id 없음 → 기존 전체 admin list ──────────────

def test_AQ_COMP_02_no_company_id_returns_all_admin_sources():
    qa = _q("C-A", source="admin_manual")
    qb = _q("C-B", source="member_auto")
    qc = _q("C-A", source="member_custom")
    # legacy survey_web — ADMIN_SOURCES 미포함, 목록에 나타나면 안 됨
    qleg = _q("C-A", source="survey_web")
    store = _base_store([qa, qb, qc, qleg])
    fake = FakeSupabase(store)

    result = svc.list_admin_quotes(fake, page=1, page_size=20)

    sources = {r["source"] for r in result["items"]}
    assert "survey_web" not in sources, "legacy survey_web 노출됨"
    assert result["total"] == 3


# ── AQ-COMP-03: company_id + source/status 조합 ──────────────────────

def test_AQ_COMP_03_company_id_combined_with_source_and_status():
    # C-A admin_manual ISSUED
    q1 = _q("C-A", source="admin_manual", status="ISSUED")
    # C-A admin_manual REQUESTED
    q2 = _q("C-A", source="admin_manual", status="REQUESTED")
    # C-A member_auto ISSUED
    q3 = _q("C-A", source="member_auto", status="ISSUED")
    # C-B admin_manual ISSUED
    q4 = _q("C-B", source="admin_manual", status="ISSUED")
    store = _base_store([q1, q2, q3, q4])
    fake = FakeSupabase(store)

    result = svc.list_admin_quotes(
        fake, page=1, page_size=20,
        company_id="C-A", source="admin_manual", status_code="ISSUED",
    )

    assert result["total"] == 1
    assert result["items"][0]["company_id"] == "C-A"
    assert result["items"][0]["source"] == "admin_manual"
    assert result["items"][0]["status_code"] == "ISSUED"


# ── AQ-COMP-04: non-admin 403 회귀 (router 레벨) ─────────────────────

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


@requires_client
def test_AQ_COMP_04_non_admin_403():
    import routers.admin_quotes as aq

    app = FastAPI()
    app.include_router(aq.router)

    non_admin_user = {"id": "user-X", "company_id": "C-X", "role_code": "002",
                      "factory_id": None, "team_id": None}
    fake_supabase = FakeSupabase(_base_store())
    app.dependency_overrides[aq.get_current_user] = lambda: non_admin_user
    aq.get_supabase = lambda: fake_supabase

    client = TestClient(app)
    r = client.get("/admin/quotes?company_id=C-A")

    assert r.status_code == 403
    writes = [(t, op) for t, op in fake_supabase.log if op in ("insert", "update")]
    assert writes == [], f"403 이후 write 발생: {writes}"


# ── AQ-COMP-05: DB mutation = 0 ─────────────────────────────────────

def test_AQ_COMP_05_db_mutation_zero():
    qa = _q("C-A")
    fake = FakeSupabase(_base_store([qa]))

    svc.list_admin_quotes(fake, page=1, page_size=20, company_id="C-A")

    writes = [(t, op) for t, op in fake.log if op in ("insert", "update")]
    assert writes == [], f"뮤테이션 발생: {writes}"
