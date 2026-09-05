"""BACKEND-1 /me/company 단위테스트 (FakeSupabase 격리).

service(sb 주입) + router(FastAPI TestClient + dependency_overrides + get_supabase monkeypatch).
운영 DB/네트워크 불사용. tax_invoice_requests/payments 미변경 검증 포함.
"""
import uuid

import pytest

import routers.member_company as mc
from services import member_company_svc as svc

# TestClient(httpx) 가 없는 환경에서도 service 단위테스트는 돌아가도록 router 테스트만 조건부 skip.
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401  (TestClient 의존)
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


class _PgErr(Exception):
    """PostgREST/psycopg 유사 예외(code/message/details/hint 속성 보유)."""
    def __init__(self, message="", code=None, details="", hint=""):
        self.code = code
        self.message = message
        self.details = details
        self.hint = hint
        super().__init__(message)


# ── FakeSupabase (in-memory, chainable, column projection 지원) ──────────────
class _Result:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if data is not None else 0


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

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys}

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            return _Result([self._project(r) for r in rows if self._match(r)])
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


class _RaiseInsertFake(FakeSupabase):
    """companies insert 에서 주어진 예외를 던진다(그 외 정상). user 는 unbound 유지."""
    def __init__(self, store, exc):
        super().__init__(store); self.exc = exc

    def table(self, name):
        q = super().table(name)
        orig = q.execute

        def exec2():
            if name == "companies" and q._op == "insert":
                raise self.exc
            return orig()
        q.execute = exec2
        return q


def _company(cid, **kw):
    base = {"id": cid, "name": "회사", "business_number": None}
    base.update(kw); return base


def _client(current_user, store):
    app = FastAPI()
    app.include_router(mc.router)
    app.dependency_overrides[mc.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    mc.get_supabase = lambda: fake  # 라우터 모듈 레벨 이름 대체
    c = TestClient(app)
    c._fake = fake
    return c


# ══ service 단위 ══
def test_t9_normalize_hyphen():
    assert svc.normalize_business_number("123-45-67890") == "1234567890"
    assert svc.normalize_business_number(" 123 45 67890 ") == "1234567890"
    assert svc.normalize_business_number(None) is None
    assert svc.normalize_business_number("") is None


def test_t10_normalize_malformed():
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.normalize_business_number("123")
    assert e.value.status_code == 400


def test_t11_t12_t13_duplicate_variants_block_create_no_autoclaim():
    for existing in ("1234567890", "123-45-67890"):
        store = {"companies": [_company("c-old", business_number=existing)], "users": [{"id": "u1", "company_id": None}]}
        sb = FakeSupabase(store)
        with pytest.raises(svc.MemberCompanyError) as e:
            svc.upsert_member_company(sb, {"id": "u1", "company_id": None},
                                      {"name": "새회사", "business_number": "123-45-67890"})
        assert e.value.status_code == 409
        assert store["users"][0]["company_id"] is None  # 자동 claim 안 됨


def test_t8_company_less_create_and_bind():
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = FakeSupabase(store)
    out = svc.upsert_member_company(sb, {"id": "u1", "company_id": None},
                                    {"name": "TAI", "business_number": "123-45-67890"})
    assert len(store["companies"]) == 1
    assert store["users"][0]["company_id"] == out["id"]
    assert store["companies"][0]["business_number"] == "1234567890"


class _RaceFake(FakeSupabase):
    """companies INSERT 직후 concurrent 가 user 를 winner(c-win) 에 bind 했다고 가정(1회)."""
    def __init__(self, store):
        super().__init__(store); self._flipped = False

    def table(self, name):
        q = super().table(name)
        orig = q.execute

        def exec2():
            res = orig()
            if name == "companies" and q._op == "insert" and not self._flipped:
                self._flipped = True
                for u in self.store.get("users", []):
                    if u["id"] == "u1":
                        u["company_id"] = "c-win"
            return res
        q.execute = exec2
        return q


def test_t14_true_bind_race_loser_compensation():
    # 시간순: user NULL -> loser company INSERT -> concurrent winner bind -> conditional bind 0 row
    #          -> loser 보상삭제 -> winner 재조회 -> winner 반환(loser payload 미적용)
    store = {
        "companies": [_company("c-win", name="WINNER", business_number="1111111111")],
        "users": [{"id": "u1", "company_id": None}],
    }
    sb = _RaceFake(store)
    out = svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "LOSER"})
    assert [c["id"] for c in store["companies"]] == ["c-win"]  # orphan 0
    assert store["users"][0]["company_id"] == "c-win"
    assert out["id"] == "c-win"
    assert out["name"] == "WINNER"  # winner 필드 loser payload 미적용
    assert [c for c in store["companies"] if c["id"] == "c-win"][0]["name"] == "WINNER"


class _BoomFake(FakeSupabase):
    """특정 (table, op) 에서 code 없는 일반 오류(비-중복) 발생."""
    def __init__(self, store, boom):
        super().__init__(store); self.boom = boom  # set of (table, op)

    def table(self, name):
        q = super().table(name)
        orig = q.execute

        def exec2():
            if (name, q._op) in self.boom:
                raise Exception("db down")  # code/constraint 없음
            return orig()
        q.execute = exec2
        return q


def test_p1_1_nonduplicate_insert_error_is_500_not_409():
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = _BoomFake(store, boom={("companies", "insert")})
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 500
    assert e.value.code == "COMPANY_CREATE_FAILED"
    assert e.value.code != "BUSINESS_NUMBER_ALREADY_EXISTS"


class _DupInsertFake(FakeSupabase):
    """companies insert 에서 bn-constraint 예외. flip=True 면 예외 전 user 를 winner bind."""
    def __init__(self, store, flip=False):
        super().__init__(store); self.flip = flip; self._done = False

    def table(self, name):
        q = super().table(name)
        orig = q.execute

        def exec2():
            if name == "companies" and q._op == "insert" and not self._done:
                self._done = True
                if self.flip:
                    for u in self.store.get("users", []):
                        if u["id"] == "u1":
                            u["company_id"] = "c-win"
                raise Exception('duplicate key value violates unique constraint "companies_business_number_unique"')
            return orig()
        q.execute = exec2
        return q


def test_p1_2a_duplicate_insert_unbound_is_409():
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = _DupInsertFake(store, flip=False)
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 409
    assert e.value.code == "BUSINESS_NUMBER_ALREADY_EXISTS"


def test_p1_2b_duplicate_insert_but_bound_returns_winner():
    store = {
        "companies": [_company("c-win", name="WINNER")],
        "users": [{"id": "u1", "company_id": None}],
    }
    sb = _DupInsertFake(store, flip=True)
    out = svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "LOSER"})
    assert out["id"] == "c-win"
    assert out["name"] == "WINNER"  # loser payload 미적용


def test_p2_1_business_number_23505_is_409():
    # helper 직접: constraint name / (23505+business_number)
    assert svc._is_business_number_unique_violation(
        _PgErr(code="23505", message='duplicate key ... "companies_business_number_unique"')) is True
    assert svc._is_business_number_unique_violation(
        _PgErr(code="23505", details="Key (business_number)=(1234567890) already exists")) is True
    # service 경유 -> 409
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = _RaiseInsertFake(store, _PgErr(code="23505", details="Key (business_number)=(x) already exists"))
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 409 and e.value.code == "BUSINESS_NUMBER_ALREADY_EXISTS"


def test_p2_2_company_code_or_bare_23505_is_500_not_409():
    # helper 직접: company_code UNIQUE / bare 23505 = False
    assert svc._is_business_number_unique_violation(
        _PgErr(code="23505", message='duplicate key ... "companies_company_code_unique"')) is False
    assert svc._is_business_number_unique_violation(_PgErr(code="23505")) is False
    # service 경유: company_code 23505 -> 500 (409 아님)
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = _RaiseInsertFake(store, _PgErr(code="23505", message='duplicate key ... "companies_company_code_unique"'))
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 500 and e.value.code == "COMPANY_CREATE_FAILED"
    assert e.value.code != "BUSINESS_NUMBER_ALREADY_EXISTS"


def test_t15_t16_bind_exception_and_compensation_fail():
    # T15: bind update 예외 -> 회사 보상삭제 성공 -> 500 COMPANY_BIND_FAILED, orphan 0
    store = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb = _BoomFake(store, boom={("users", "update")})
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e.value.status_code == 500
    assert store["companies"] == []
    # T16: bind 예외 + 보상삭제도 실패 -> COMPANY_BIND_COMPENSATION_FAILED
    store2 = {"companies": [], "users": [{"id": "u1", "company_id": None}]}
    sb2 = _BoomFake(store2, boom={("users", "update"), ("companies", "delete")})
    with pytest.raises(svc.MemberCompanyError) as e2:
        svc.upsert_member_company(sb2, {"id": "u1", "company_id": None}, {"name": "X"})
    assert e2.value.code == "COMPANY_BIND_COMPENSATION_FAILED"


def test_t17_t18_existing_update_conflict_and_isolation():
    store = {"companies": [_company("c1", business_number="1111111111"),
                            _company("c2", business_number="2222222222")],
             "users": [{"id": "u1", "company_id": "c1"}]}
    sb = FakeSupabase(store)
    with pytest.raises(svc.MemberCompanyError) as e:
        svc.upsert_member_company(sb, {"id": "u1", "company_id": "c1"}, {"business_number": "222-22-22222"})
    assert e.value.status_code == 409
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


# ══ router 레벨 ══
@requires_client
def test_t3_get_company_less_returns_null():
    c = _client({"id": "u1", "company_id": None, "role_code": "010"}, {"companies": [], "users": []})
    r = c.get("/me/company")
    assert r.status_code == 200 and r.json()["data"] is None


@requires_client
def test_t2_t19_get_bound_returns_only_legal_fields():
    store = {"companies": [_company(
        "c1", name="내회사", business_number="1234567890", representative_name="홍길동",
        contact_email="a@b.c", contact_phone="010", zipcode="06236", address_road="테헤란로",
        address_detail="3층", business_type="정보통신업", business_category="응용SW",
        status_code="ACTIVE", company_code="CO-1", is_active=True, created_by="admin",
    )]}
    c = _client({"id": "u1", "company_id": "c1", "role_code": "010"}, store)
    r = c.get("/me/company")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == set(svc.VIEW_FIELDS)
    for leaked in ("status_code", "company_code", "is_active", "created_by"):
        assert leaked not in data
    assert data["id"] == "c1" and data["name"] == "내회사"


@requires_client
def test_t1_unauth_get_401():
    app = FastAPI(); app.include_router(mc.router)
    def _raise():
        raise HTTPException(status_code=401, detail="no auth")
    app.dependency_overrides[mc.get_current_user] = _raise
    r = TestClient(app).get("/me/company")
    assert r.status_code == 401


@requires_client
def test_t6_put_disallowed_role_403():
    c = _client({"id": "u1", "company_id": "c1", "role_code": "099"}, {"companies": [_company("c1")]})
    r = c.put("/me/company", json={"name": "X"})
    assert r.status_code == 403


@requires_client
def test_t5_put_allowed_role_updates():
    store = {"companies": [_company("c1", name="old")]}
    c = _client({"id": "u1", "company_id": "c1", "role_code": "001"}, store)
    r = c.put("/me/company", json={"name": "new"})
    assert r.status_code == 200
    assert [x for x in store["companies"] if x["id"] == "c1"][0]["name"] == "new"


@requires_client
def test_t7_t4_reject_id_injection():
    c = _client({"id": "u1", "company_id": "c1", "role_code": "001"}, {"companies": [_company("c1")]})
    for bad in ({"name": "X", "company_id": "c-other"}, {"name": "X", "user_id": "u-other"}):
        r = c.put("/me/company", json=bad)
        assert r.status_code == 422
