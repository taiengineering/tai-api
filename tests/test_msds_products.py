"""WO-MSDS-02 chemical_products / identifiers 단위·통합 테스트.

FakeSupabase 격리 — 운영 DB/네트워크 불사용.
Tenant 격리(BOLA), Duplicate Candidate, Identifier 생명주기 검증.
"""
from __future__ import annotations

import uuid

import pytest

import routers.msds_products as mp
from services import msds_product_svc as svc

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")

# ─── FakeSupabase ─────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store
        self.table_name = table
        self.log = log
        self._op = None
        self._payload = None
        self._filters = []
        self._cols = "*"
        self._limit_n = None
        self._range_start = None
        self._range_end = None
        self._order_col = None
        self._order_desc = False
        self._count_mode = None

    def select(self, cols="*", *a, **k):
        self._op = "select"
        self._cols = cols or "*"
        self._count_mode = k.get("count")
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, c, v):
        self._filters.append(("eq", c, v))
        return self

    def ilike(self, c, pattern):
        self._filters.append(("ilike", c, pattern))
        return self

    def in_(self, c, vals):
        self._filters.append(("in", c, list(vals)))
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def order(self, col, desc=False, **k):
        self._order_col = col
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._range_start = start
        self._range_end = end
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq":
                if isinstance(v, bool) or isinstance(rv, bool):
                    if bool(rv) != bool(v):
                        return False
                elif str(rv) != str(v):
                    return False
            elif op == "ilike":
                # pattern: %text%
                pat = v.replace("%", "").lower()
                if rv is None or pat not in str(rv).lower():
                    return False
            elif op == "in":
                if rv not in v and str(rv) not in [str(x) for x in v]:
                    return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip().split(":")[0] for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys if k}

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        self.log.append((self.table_name, self._op))

        if self._op == "select":
            matched = [self._project(r) for r in rows if self._match(r)]
            if self._order_col:
                matched.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
            if self._range_start is not None:
                matched = matched[self._range_start:self._range_end + 1]
            elif self._limit_n is not None:
                matched = matched[:self._limit_n]
            cnt = len([r for r in rows if self._match(r)]) if self._count_mode == "exact" else None
            return _Result(matched, count=cnt)

        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it)
                it.setdefault("id", str(uuid.uuid4()))
                rows.append(it)
                out.append(dict(it))
            return _Result(out)

        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            return _Result([dict(r) for r in matched])

        if self._op == "delete":
            keep = [r for r in rows if not self._match(r)]
            removed = [r for r in rows if self._match(r)]
            self.store[self.table_name] = keep
            return _Result([dict(r) for r in removed])

        return _Result([])


class FakeSB:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)


# ─── Fixture helpers ──────────────────────────────────────────────────────────

CO_A = "company-a"
CO_B = "company-b"
U_A = "user-a"
U_B = "user-b"

CALLER_A = {"id": U_A, "company_id": CO_A, "role_code": "010"}
CALLER_B = {"id": U_B, "company_id": CO_B, "role_code": "010"}
NO_CO = {"id": "user-nocompany", "company_id": None, "role_code": "010"}


def _client(current_user, store=None):
    app = FastAPI()
    app.include_router(mp.router)
    app.dependency_overrides[mp.get_current_user] = lambda: current_user
    fake = FakeSB(store or {})
    mp.get_supabase = lambda: fake
    c = TestClient(app)
    c._fake = fake
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# CP — Product service 단위 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp01_create_product():
    sb = FakeSB()
    product, cands = svc.create_product(sb, CALLER_A, "ABC 세척제")
    assert product["product_name"] == "ABC 세척제"
    assert product["company_id"] == CO_A
    assert product["identity_status"] == "DRAFT"
    assert product["status_code"] == "ACTIVE"
    assert product["created_source"] == "MANUAL"
    assert cands == []


def test_cp02_manufacturer_nullable():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "XYZ 절삭유", manufacturer_name=None)
    assert product["manufacturer_name"] is None
    assert product["manufacturer_normalized"] is None


def test_cp03_normalization_deterministic():
    assert svc.normalize_product_name("  ABC 세척제  ") == "abc 세척제"
    assert svc.normalize_product_name("ABC  세척제") == "abc 세척제"
    assert svc.normalize_manufacturer("  ABC Chemical  ") == "abc chemical"
    assert svc.normalize_manufacturer(None) is None
    assert svc.normalize_identifier("  0012345  ") == "0012345"
    assert svc.normalize_identifier("00123") == "00123"


def test_cp04_invalid_identity_status_reject():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "Test Product")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.update_product(sb, CALLER_A, product["id"], {"identity_status": "INVALID_STATE"})
    assert exc.value.status_code == 400


def test_cp05_invalid_status_code_reject():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "Test Product")
    with pytest.raises(svc.MsdsProductError):
        svc.update_product(sb, CALLER_A, product["id"], {"status_code": "DELETED"})


def test_cp06_invalid_created_source_reject():
    sb = FakeSB()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.create_product(sb, CALLER_A, "Test", created_source="UNKNOWN_SOURCE")
    assert exc.value.status_code == 400


def test_cp07_company_scope_required():
    sb = FakeSB()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.create_product(sb, NO_CO, "Test")
    assert exc.value.status_code == 403
    assert exc.value.code == "NO_COMPANY"


def test_cp08_inactive_lifecycle():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "세척제")
    assert product["status_code"] == "ACTIVE"
    inactive = svc.deactivate_product(sb, CALLER_A, product["id"])
    assert inactive["status_code"] == "INACTIVE"
    active = svc.reactivate_product(sb, CALLER_A, product["id"])
    assert active["status_code"] == "ACTIVE"


def test_cp09_deactivate_idempotent():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "세척제")
    r1 = svc.deactivate_product(sb, CALLER_A, product["id"])
    r2 = svc.deactivate_product(sb, CALLER_A, product["id"])
    assert r1["status_code"] == "INACTIVE"
    assert r2["status_code"] == "INACTIVE"


def test_cp10_product_not_found_404():
    sb = FakeSB()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, str(uuid.uuid4()))
    assert exc.value.status_code == 404


def test_cp11_update_normalizes_name():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "Old Name")
    updated = svc.update_product(sb, CALLER_A, product["id"], {"product_name": "  New Name  "})
    assert updated["product_name"] == "New Name"
    assert updated["product_name_normalized"] == "new name"


def test_cp12_identity_status_transition():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "테스트")
    assert product["identity_status"] == "DRAFT"
    confirmed = svc.update_product(sb, CALLER_A, product["id"], {"identity_status": "CONFIRMED"})
    assert confirmed["identity_status"] == "CONFIRMED"
    review = svc.update_product(sb, CALLER_A, product["id"], {"identity_status": "REVIEW_REQUIRED"})
    assert review["identity_status"] == "REVIEW_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# ID — Identifier 단위 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_id01_identifier_add():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품A")
    ident = svc.add_identifier(sb, CALLER_A, product["id"], {
        "identifier_type": "BARCODE",
        "identifier_value": "1234567890",
    })
    assert ident["identifier_type"] == "BARCODE"
    assert ident["identifier_value"] == "1234567890"
    assert ident["is_active"] is True


def test_id02_multiple_identifiers_per_product():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품B")
    svc.add_identifier(sb, CALLER_A, product["id"], {"identifier_type": "BARCODE", "identifier_value": "111"})
    svc.add_identifier(sb, CALLER_A, product["id"], {"identifier_type": "GTIN", "identifier_value": "222"})
    items = svc.list_identifiers(sb, CALLER_A, product["id"])
    assert len(items) == 2


def test_id03_same_product_active_exact_identifier_duplicate_contract():
    # DB 레벨: uidx_cpi_active_unique (chemical_product_id, identifier_type, identifier_normalized WHERE is_active=true)
    # FakeSB는 UNIQUE INDEX를 enforce하지 않으나, duplicate 방지 계약은 migration DDL에 존재함.
    # 이 테스트는 FakeSB에서 insert가 허용됨을 확인 (DB 격리 환경에서 정상)하며
    # 동일 제품+타입+코드의 identifier_normalized가 동일하게 처리됨을 검증.
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품C")
    svc.add_identifier(sb, CALLER_A, product["id"], {"identifier_type": "BARCODE", "identifier_value": "999"})
    ident2 = svc.add_identifier(sb, CALLER_A, product["id"], {"identifier_type": "BARCODE", "identifier_value": "999"})
    # FakeSB에서는 중복 허용, 실제 DB에서는 UNIQUE INDEX가 constraint error 발생
    assert ident2["identifier_normalized"] == "999"  # normalization 동일 결과 확인


def test_id05_leading_zero_identifier_preserved():
    assert svc.normalize_identifier("00012345") == "00012345"
    assert svc.normalize_identifier("0000001") == "0000001"
    # numeric cast하지 않으므로 leading zero 유지
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "EAN 제품")
    ident = svc.add_identifier(sb, CALLER_A, product["id"], {
        "identifier_type": "EAN",
        "identifier_value": "00012345678905",
    })
    assert ident["identifier_normalized"] == "00012345678905"


def test_id06_identifier_deactivate():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품D")
    ident = svc.add_identifier(sb, CALLER_A, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "777"
    })
    result = svc.deactivate_identifier(sb, CALLER_A, product["id"], ident["id"])
    assert result["is_active"] is False


def test_id08_identifier_invalid_type_reject():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품E")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, product["id"], {
            "identifier_type": "INVALID_TYPE",
            "identifier_value": "123",
        })
    assert exc.value.status_code == 400


def test_id09_identifier_empty_value_reject():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "제품F")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, product["id"], {
            "identifier_type": "BARCODE",
            "identifier_value": "   ",
        })
    assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# DUP — Duplicate Candidate 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_dup01_exact_identifier_candidate():
    sb = FakeSB()
    product1, _ = svc.create_product(sb, CALLER_A, "제품X")
    svc.add_identifier(sb, CALLER_A, product1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "BARCODE-001"
    })
    _, candidates = svc.create_product(sb, CALLER_A, "제품X 복사", identifiers=[{
        "identifier_type": "BARCODE",
        "identifier_value": "BARCODE-001",
    }])
    assert any(c["reason"] == "EXACT_IDENTIFIER" for c in candidates)
    assert any(c["product_id"] == product1["id"] for c in candidates)


def test_dup02_normalized_name_manufacturer_candidate():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "ABC 세척제", manufacturer_name="ABC Chemical")
    _, candidates = svc.create_product(sb, CALLER_A, "abc 세척제", manufacturer_name="abc chemical")
    assert any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in candidates)


def test_dup03_same_name_different_manufacturer_not_exact():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "세척제 100", manufacturer_name="ABC Chemical")
    _, candidates = svc.create_product(sb, CALLER_A, "세척제 100", manufacturer_name="XYZ Chemical")
    # 제조사가 다르면 POSSIBLE_DUPLICATE_NAME_MFR 에 걸리지 않음
    assert not any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in candidates)


def test_dup04_manufacturer_null_no_false_positive():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "공통 제품명", manufacturer_name=None)
    _, candidates = svc.create_product(sb, CALLER_A, "공통 제품명", manufacturer_name=None)
    # manufacturer가 NULL이면 name+mfr 기반 중복 탐지 skip
    assert not any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in candidates)


def test_dup05_candidate_does_not_auto_merge():
    sb = FakeSB()
    product1, _ = svc.create_product(sb, CALLER_A, "제품Y")
    svc.add_identifier(sb, CALLER_A, product1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "SAME-CODE"
    })
    product2, candidates = svc.create_product(sb, CALLER_A, "제품Y 복사", identifiers=[{
        "identifier_type": "BARCODE", "identifier_value": "SAME-CODE",
    }])
    # 두 product가 모두 존재해야 함 (자동 merge 금지)
    p1 = sb.table("chemical_products").select("*").eq("id", product1["id"]).execute()
    p2 = sb.table("chemical_products").select("*").eq("id", product2["id"]).execute()
    assert len(p1.data) == 1
    assert len(p2.data) == 1
    assert candidates


# ═══════════════════════════════════════════════════════════════════════════════
# TEN — Tenant Isolation (BOLA) 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_ten01_company_a_list_cannot_see_company_b():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "A사 제품")
    svc.create_product(sb, CALLER_B, "B사 제품")
    result = svc.list_products(sb, CALLER_A)
    assert all(i["company_id"] == CO_A for i in result["items"])
    assert all(i["company_id"] != CO_B for i in result["items"])


def test_ten02_company_a_get_b_product_inaccessible():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, product_b["id"])
    assert exc.value.status_code == 404


def test_ten03_company_a_patch_b_product_inaccessible():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.update_product(sb, CALLER_A, product_b["id"], {"product_name": "탈취 시도"})
    assert exc.value.status_code == 404


def test_ten04_company_a_deactivate_b_product_inaccessible():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.deactivate_product(sb, CALLER_A, product_b["id"])
    assert exc.value.status_code == 404


def test_ten05_company_a_add_identifier_to_b_product_inaccessible():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, product_b["id"], {
            "identifier_type": "BARCODE", "identifier_value": "hack"
        })
    assert exc.value.status_code == 404


def test_ten06_company_a_deactivate_identifier_on_b_product_inaccessible():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    ident_b = svc.add_identifier(sb, CALLER_B, product_b["id"], {
        "identifier_type": "BARCODE", "identifier_value": "bcode"
    })
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.deactivate_identifier(sb, CALLER_A, product_b["id"], ident_b["id"])
    assert exc.value.status_code == 404


def test_ten07_identifier_list_scoped_to_company():
    sb = FakeSB()
    product_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_identifiers(sb, CALLER_A, product_b["id"])
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Router 레벨 테스트
# ═══════════════════════════════════════════════════════════════════════════════

@requires_client
def test_router_create_product_201():
    c = _client(CALLER_A)
    r = c.post("/me/msds/products", json={"product_name": "ABC 세척제"})
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "success"
    assert d["data"]["product_name"] == "ABC 세척제"
    assert "duplicate_candidates" in d


@requires_client
def test_router_list_products_200():
    store = {}
    c = _client(CALLER_A, store)
    c.post("/me/msds/products", json={"product_name": "제품1"})
    c.post("/me/msds/products", json={"product_name": "제품2"})
    r = c.get("/me/msds/products")
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= 2


@requires_client
def test_router_get_product_200():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post("/me/msds/products", json={"product_name": "세척제"})
    pid = created.json()["data"]["id"]
    r = c.get(f"/me/msds/products/{pid}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == pid


@requires_client
def test_router_patch_product():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post("/me/msds/products", json={"product_name": "Old"})
    pid = created.json()["data"]["id"]
    r = c.patch(f"/me/msds/products/{pid}", json={"product_name": "New"})
    assert r.status_code == 200
    assert r.json()["data"]["product_name"] == "New"


@requires_client
def test_router_deactivate_reactivate():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post("/me/msds/products", json={"product_name": "Cycle"})
    pid = created.json()["data"]["id"]
    r1 = c.post(f"/me/msds/products/{pid}/deactivate")
    assert r1.status_code == 200
    assert r1.json()["data"]["status_code"] == "INACTIVE"
    r2 = c.post(f"/me/msds/products/{pid}/reactivate")
    assert r2.status_code == 200
    assert r2.json()["data"]["status_code"] == "ACTIVE"


@requires_client
def test_router_add_get_deactivate_identifier():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post("/me/msds/products", json={"product_name": "바코드 제품"})
    pid = created.json()["data"]["id"]

    r_add = c.post(f"/me/msds/products/{pid}/identifiers", json={
        "identifier_type": "BARCODE",
        "identifier_value": "9876543210",
    })
    assert r_add.status_code == 201
    iid = r_add.json()["data"]["id"]

    r_list = c.get(f"/me/msds/products/{pid}/identifiers")
    assert r_list.status_code == 200
    assert r_list.json()["data"]["total"] == 1

    r_del = c.delete(f"/me/msds/products/{pid}/identifiers/{iid}")
    assert r_del.status_code == 200
    assert r_del.json()["data"]["is_active"] is False


@requires_client
def test_router_forbidden_body_fields_422():
    c = _client(CALLER_A)
    r = c.post("/me/msds/products", json={"product_name": "X", "company_id": "hack"})
    assert r.status_code == 422


@requires_client
def test_router_no_company_403():
    c = _client(NO_CO)
    r = c.post("/me/msds/products", json={"product_name": "X"})
    assert r.status_code == 403


@requires_client
def test_router_cross_company_get_404():
    store = {}
    c_a = _client(CALLER_A, store)
    c_b = _client(CALLER_B, store)
    created = c_b.post("/me/msds/products", json={"product_name": "B사 전용"})
    pid = created.json()["data"]["id"]
    r = c_a.get(f"/me/msds/products/{pid}")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Forbidden Area Guard — factory_materials / material_legal_master 불변
# ═══════════════════════════════════════════════════════════════════════════════

def test_forbidden_factory_materials_not_touched():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "테스트")
    touched = {t for (t, _) in sb.log}
    assert "factory_materials" not in touched
    assert "material_legal_master" not in touched


def test_forbidden_msds_ref_not_touched():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "테스트")
    touched = {t for (t, _) in sb.log}
    for table in touched:
        assert not table.startswith("msds_ref")


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH — q 검색 테스트 (PATCH-001)
# ═══════════════════════════════════════════════════════════════════════════════

def test_search01_product_name_search():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "ABC 세척제", manufacturer_name="XYZ Chemical")
    svc.create_product(sb, CALLER_A, "전혀 다른 제품")
    result = svc.list_products(sb, CALLER_A, q="abc 세척")
    assert len(result["items"]) == 1
    assert result["items"][0]["product_name"] == "ABC 세척제"


def test_search02_manufacturer_search():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "제품1", manufacturer_name="ABC Chemical")
    svc.create_product(sb, CALLER_A, "제품2", manufacturer_name="XYZ Corp")
    result = svc.list_products(sb, CALLER_A, q="abc chem")
    assert len(result["items"]) == 1
    assert result["items"][0]["product_name"] == "제품1"


def test_search03_identifier_search():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "바코드 제품")
    svc.add_identifier(sb, CALLER_A, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "BARCODE-99999"
    })
    svc.create_product(sb, CALLER_A, "다른 제품")
    result = svc.list_products(sb, CALLER_A, q="99999")
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == product["id"]


def test_search04_no_match():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "ABC 세척제")
    result = svc.list_products(sb, CALLER_A, q="전혀없는검색어xyz123")
    assert result["items"] == []
    assert result["total"] == 0


def test_search05_cross_company_product_not_visible():
    sb = FakeSB()
    svc.create_product(sb, CALLER_B, "B사 세척제")
    result = svc.list_products(sb, CALLER_A, q="세척제")
    assert result["items"] == []
    assert result["total"] == 0


def test_search06_cross_company_identifier_not_visible():
    sb = FakeSB()
    prod_b, _ = svc.create_product(sb, CALLER_B, "B사 제품")
    svc.add_identifier(sb, CALLER_B, prod_b["id"], {
        "identifier_type": "BARCODE", "identifier_value": "SHARED-CODE"
    })
    result = svc.list_products(sb, CALLER_A, q="SHARED-CODE")
    assert result["items"] == []


def test_search07_filtered_total_correct():
    sb = FakeSB()
    svc.create_product(sb, CALLER_A, "세척제 A")
    svc.create_product(sb, CALLER_A, "세척제 B")
    svc.create_product(sb, CALLER_A, "절삭유 C")
    result = svc.list_products(sb, CALLER_A, q="세척제")
    assert result["total"] == 2
    assert len(result["items"]) == 2


def test_search08_pagination_after_filtering():
    sb = FakeSB()
    for i in range(5):
        svc.create_product(sb, CALLER_A, f"세척제 {i:02d}")
    svc.create_product(sb, CALLER_A, "절삭유")
    result = svc.list_products(sb, CALLER_A, q="세척제", limit=2, offset=0)
    assert result["total"] == 5
    assert len(result["items"]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# PROV — Provenance (created_source) 보호 테스트 (PATCH-001)
# ═══════════════════════════════════════════════════════════════════════════════

def test_prov03_normal_product_create_source_manual():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "Test Product")
    assert product["created_source"] == "MANUAL"


def test_prov04_normal_identifier_create_source_manual():
    sb = FakeSB()
    product, _ = svc.create_product(sb, CALLER_A, "Test Product")
    ident = svc.add_identifier(sb, CALLER_A, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "TESTCODE"
    })
    assert ident["created_source"] == "MANUAL"


@requires_client
def test_prov01_post_product_with_created_source_422():
    c = _client(CALLER_A)
    r = c.post("/me/msds/products", json={
        "product_name": "Test",
        "created_source": "PDF"
    })
    assert r.status_code == 422


@requires_client
def test_prov02_post_identifier_with_created_source_422():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post("/me/msds/products", json={"product_name": "Test"})
    pid = created.json()["data"]["id"]
    r = c.post(f"/me/msds/products/{pid}/identifiers", json={
        "identifier_type": "BARCODE",
        "identifier_value": "CODE123",
        "created_source": "PHOTO"
    })
    assert r.status_code == 422


@requires_client
def test_prov05_product_created_source_server_owned_manual():
    store = {}
    c = _client(CALLER_A, store)
    r = c.post("/me/msds/products", json={"product_name": "Manual Product"})
    assert r.status_code == 201
    assert r.json()["data"]["created_source"] == "MANUAL"
