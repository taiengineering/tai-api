"""BACKEND-1 /me/company 단위테스트 (FakeSupabase 격리).

service(sb 주입) + router(FastAPI TestClient + dependency_overrides + get_supabase monkeypatch).
운영 DB/네트워크 불사용. tax_invoice_requests/payments 미변경 검증 포함.
"""
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.member_company as mc
from services import member_company_svc as svc


# ── FakeSupabase (in-memory, chainable) ───────────────────────────────────
class _Result:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if data is not None else 0


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []

    def select(self, *a, **k): self._op = "select"; return self
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
            return _Result([dict(r) for r in rows if self._match(r)])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                if self.table == "companies" and it.get("business_number"):
                    for r in rows:
                        if r.get("business_number") == it["business_number"]:
                            raise Exception('duplicate key value violates unique constraint "companies_business_number_unique"')
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched: r.update(self._payload)
            return _Result([dict(r) for r in matched])
        if self._op == "delete":
            keep = [r for r in rows if not self._match(r)]
            removed = [r for r in rows if self._match(r)]
            self.store[self.table] = keep
            return _Result([dict(r) for r in removed])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)


def _client(current_user, store):
    app = FastAPI()
    app.include_router(mc.router)
    app.dependency_overrides[mc.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    mc.get_supabase = lambda: fake  # noqa: 라우터 모듈 레벨 이름 대체
    c = TestClient(app)
    c._fake = fake
    return c


def _company(cid, **kw):
    base = {"id": cid, "name": "회사", "business_number": None}
    base.update(kw); return base


# ── service 단위 (T9/T10/T11/T12/T13/T8/T14/T15/T16/T17/T18/T20/T21) ──
def test_t9_normalize_hyphen():
    assert svc.normalize_business_number("123-45-67890") == "1234567890"
    assert svc.normalize_business_number(" 123 45 67890 ") == "1234567890"
    assert svc.normalize_business_number(None) is None
    assert svc.normalize_business_number("") is None


def test_t10_normalize_malformed():
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.normalize_business_number("123")
    assert e.value.status_code == 400


def test_t11_t12_duplicate_variants_block_create():
    for existing in ("1234567890", "123-45-67890"):
        store = {"companies": [_company("c-old", business_number=existing)], "users": [{"id": "u1", "company_id": None}]}
        sb = FakeSupabase(store)
        with pytest.raises(svc.MemberCompanyError) as e:
            svc.upsert_member_company(sb, {"id": "u1", "company_id": None},
                                      {"name": "새회사", "business_number": "123-45-67890"})
        assert e.value.status_code == 409  # T13: 자동 claim 아님
        # 기존 회사 소유권 자동 연결 안 됨
        assert store["users"][0]["company_id"] is None


def test_t8_company_less_create_and_bind():
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = FakeSupabase(store)
    out = svc.upsert_member_company(sb, {"id": "u1", "company_id": None},
                                    {"name": "TAI", "business_number": "123-45-67890"})
    assert len(store["companies"]) == 1
    assert store["users"][0]["company_id"] == out["id"]
    assert store["companies"][0]["business_number"] == "1234567890"


def test_t14_bind_race_loser_compensation():
    # bind 대상(company_id IS NULL) 없음 -> update 0 row -> 방금 만든 회사 보상삭제 + winner 반환
    store = {"companies": [_company("c-win")], "users": [{"id": "u1", "company_id": "c-win"}]}
    sb = FakeSupabase(store)
    # current_user 는 아직 company_id NULL 로 진입했다고 가정하되, DB엔 이미 c-win bind됨(race)
    out = svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "loser입력"})
    assert out["id"] == "c-win"  # winner 반환
    # orphan 0: 생성됐던 회사는 보상삭제되어 c-win 만 남음
    assert [c["id"] for c in store["companies"]] == ["c-win"]


def test_t15_t16_bind_exception_and_compensation_fail():
    # bind update 에서 예외 -> 회사 보상삭제 시도. 보상삭제도 실패하면 500 명시.
    class BoomOnUserUpdate(FakeSupabase):
        def __init__(self, store, fail_delete=False):
            super().__init__(store); self.fail_delete = fail_delete
        def table(self, name):
            q = super().table(name)
            orig_exec = q.execute
            def exec2():
                if name == "users" and q._op == "update":
                    raise Exception("bind boom")
                if name == "companies" and q._op == "delete" and self.fail_delete:
                    raise Exception("delete boom")
                return orig_exec()
            q.execute = exec2
            return q
    # T15: 보상삭제 성공 -> 원 오류(COMPANY_BIND_FAILED 500)
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = BoomOnUserUpdate(store)
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 500
    assert store["companies"] == []  # 보상삭제로 orphan 0
    # T16: 보상삭제도 실패 -> COMPANY_BIND_COMPENSATION_FAILED 500
    store2 = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb2 = BoomOnUserUpdate(store2, fail_delete=True)
    with pytest.raises(svc.MemberCompanyError) as e2:
        svc.upsert_member_company(sb2, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e2.value.code == "COMPANY_BIND_COMPENSATION_FAILED"


def test_t17_t18_existing_update_conflict_and_isolation():
    store = {"companies": [_company("c1", business_number="1111111111"),
                            _company("c2", business_number="2222222222")],
             "users": [{"id": "u1", "company_id": "c1"}]}
    sb = FakeSupabase(store)
    # T17: 타사(c2) 사업자번호로 변경 시도 -> 409
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": "c1"}, {"business_number": "222-22-22222"})
    assert e.value.status_code == 409
    # T18: 정상 자기회사 수정 -> c2 불변
    svc.upsert_member_company(sb, {"id": "u1", "company_id": "c1"}, {"name": "새이름"})
    c2 = [c for c in store["companies"] if c["id"] == "c2"][0]
    assert c2["name"] == "회사" and c2["business_number"] == "2222222222"


def test_t20_t21_no_payment_or_tax_mutation():
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = FakeSupabase(store)
    svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "TAI"})
    touched = {t for (t, _op) in sb.log}
    assert "payments" not in touched
    assert "tax_invoice_requests" not in touched


# ── router 레벨 (T1/T2/T3/T4/T5/T6/T7) ──
def test_t3_get_company_less_returns_null():
    c = _client({"id": "u1", "company_id": None, "role_code": "010"}, {"companies": [], "users": []})
    r = c.get("/me/company")
    assert r.status_code == 200 and r.json()["data"] is None


def test_t2_get_bound_returns_own():
    store = {"companies": [_company("c1", name="내회사", business_number="1234567890")]}
    c = _client({"id": "u1", "company_id": "c1", "role_code": "010"}, store)
    r = c.get("/me/company")
    assert r.status_code == 200 and r.json()["data"]["id"] == "c1" and r.json()["data"]["name"] == "내회사"


def test_t1_unauth_get_401():
    app = FastAPI(); app.include_router(mc.router)
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")
    app.dependency_overrides[mc.get_current_user] = _raise
    r = TestClient(app).get("/me/company")
    assert r.status_code == 401


def test_t6_put_disallowed_role_403():
    c = _client({"id": "u1", "company_id": "c1", "role_code": "099"}, {"companies": [_company("c1")]})
    r = c.put("/me/company", json={"name": "X"})
    assert r.status_code == 403


def test_t5_put_allowed_role_updates():
    store = {"companies": [_company("c1", name="old")]}
    c = _client({"id": "u1", "company_id": "c1", "role_code": "001"}, store)
    r = c.put("/me/company", json={"name": "new"})
    assert r.status_code == 200
    assert [x for x in store["companies"] if x["id"] == "c1"][0]["name"] == "new"


def test_t7_t4_reject_id_injection():
    # company_id/user_id 주입 -> extra=forbid 422 (ownership 은 토큰만)
    c = _client({"id": "u1", "company_id": "c1", "role_code": "001"}, {"companies": [_company("c1")]})
    for bad in ({"name": "X", "company_id": "c-other"}, {"name": "X", "user_id": "u-other"}):
        r = c.put("/me/company", json=bad)
        assert r.status_code == 422
