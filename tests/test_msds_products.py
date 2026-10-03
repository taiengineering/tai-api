"""WO-MSDS-02-PATCH-004 chemical_products / identifiers 단위·통합 테스트.

FakeSupabase 격리 — 운영 DB/네트워크 불사용.
Canonical Scope: factory_id (factories.id). company_id 는 factory 귀속 검증용.
Authorization: role_data_scope tier 기반 (ALL/COMPANY/FACTORY/TEAM/ASSIGNED).
Site 격리(동일회사 다른 시설), Tenant 격리(BOLA), Duplicate Candidate, Identifier 생명주기 검증.
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


# ─── Fixture 상수 ─────────────────────────────────────────────────────────────

CO_A = "company-a"
CO_B = "company-b"
FAC_A1 = "factory-a1"   # Company A, Site 1
FAC_A2 = "factory-a2"   # Company A, Site 2
FAC_B  = "factory-b1"   # Company B

CALLER_A  = {"id": "user-a", "company_id": CO_A, "role_code": "010"}
CALLER_B  = {"id": "user-b", "company_id": CO_B, "role_code": "010"}
NO_CO     = {"id": "user-nocompany", "company_id": None, "role_code": "010"}

# ─── AUTH fixtures ─────────────────────────────────────────────────────────────
# role_code 매핑 (role_data_scope 테이블과 동기)
ROLE_COMPANY    = "010"
ROLE_FACTORY    = "012"
ROLE_TEAM       = "013"
ROLE_ASSIGNED   = "020"
ROLE_ALL        = "099"
ROLE_PLATFORM   = "090"   # PLATFORM scope → fail-closed
ROLE_NULL_SCOPE = "888"   # role_data_scope row exists but scope_type=None → fail-closed

AUTH_COMPANY_A      = {"id": "auth-co-a",      "company_id": CO_A, "role_code": ROLE_COMPANY}
AUTH_FACTORY_A1     = {"id": "auth-fac-a1",    "company_id": CO_A, "role_code": ROLE_FACTORY,  "factory_id": FAC_A1}
AUTH_FACTORY_A2     = {"id": "auth-fac-a2",    "company_id": CO_A, "role_code": ROLE_FACTORY,  "factory_id": FAC_A2}
AUTH_FACTORY_NOFID  = {"id": "auth-fac-nofid", "company_id": CO_A, "role_code": ROLE_FACTORY}  # factory_id 미배정
AUTH_TEAM_A1        = {"id": "auth-team-a1",   "company_id": CO_A, "role_code": ROLE_TEAM,     "factory_id": FAC_A1}
AUTH_TEAM_NOFID     = {"id": "auth-team-nofid","company_id": CO_A, "role_code": ROLE_TEAM}     # factory_id 미배정
AUTH_ALL            = {"id": "auth-all",        "role_code": ROLE_ALL}  # 플랫폼 관리자 (company_id 없어도 됨)
AUTH_ASSIGNED_A1    = {"id": "auth-asgn-a1",   "company_id": CO_A, "role_code": ROLE_ASSIGNED, "factory_id": FAC_A1}
AUTH_ASSIGNED_NOFID = {"id": "auth-asgn-nofid","company_id": CO_A, "role_code": ROLE_ASSIGNED}  # factory_id 미배정 → DENY
AUTH_PLATFORM       = {"id": "auth-platform",  "company_id": CO_A, "role_code": ROLE_PLATFORM}
AUTH_UNKNOWN_ROLE   = {"id": "auth-unknown",   "company_id": CO_A, "role_code": "999"}            # role_data_scope 미존재, factory_id 없음
AUTH_UNKNOWN_WITH_FID = {"id": "auth-unk-fid", "company_id": CO_A, "role_code": "999",  "factory_id": FAC_A1}  # 미정의 role + factory_id 있음
AUTH_NULL_SCOPE     = {"id": "auth-null-sc",   "company_id": CO_A, "role_code": ROLE_NULL_SCOPE, "factory_id": FAC_A1}  # scope_type=None

_FACTORIES = [
    {"id": FAC_A1, "company_id": CO_A, "name": "A사 1공장"},
    {"id": FAC_A2, "company_id": CO_A, "name": "A사 2공장"},
    {"id": FAC_B,  "company_id": CO_B, "name": "B사 공장"},
]

_ROLE_DATA_SCOPE = [
    {"role_code": ROLE_COMPANY,    "scope_type": "COMPANY"},
    {"role_code": ROLE_FACTORY,    "scope_type": "FACTORY"},
    {"role_code": ROLE_TEAM,       "scope_type": "TEAM"},
    {"role_code": ROLE_ASSIGNED,   "scope_type": "ASSIGNED"},
    {"role_code": ROLE_ALL,        "scope_type": "ALL"},
    {"role_code": ROLE_PLATFORM,   "scope_type": "PLATFORM"},
    {"role_code": ROLE_NULL_SCOPE, "scope_type": None},   # AUTH19: row exists but scope_type null
]


def _make_sb(extra=None):
    store = {"factories": list(_FACTORIES), "role_data_scope": list(_ROLE_DATA_SCOPE)}
    if extra:
        store.update(extra)
    return FakeSB(store)


def _client(current_user, store=None):
    if store is None:
        store = {"factories": list(_FACTORIES), "role_data_scope": list(_ROLE_DATA_SCOPE)}
    else:
        if "factories" not in store:
            store["factories"] = list(_FACTORIES)
        if "role_data_scope" not in store:
            store["role_data_scope"] = list(_ROLE_DATA_SCOPE)
    app = FastAPI()
    app.include_router(mp.router)
    app.dependency_overrides[mp.get_current_user] = lambda: current_user
    fake = FakeSB(store)
    mp.get_supabase = lambda: fake
    c = TestClient(app)
    c._fake = fake
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# CP — Product service 단위 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp01_create_product():
    sb = _make_sb()
    product, cands = svc.create_product(sb, CALLER_A, FAC_A1, "ABC 세척제")
    assert product["product_name"] == "ABC 세척제"
    assert product["factory_id"] == FAC_A1
    assert product["identity_status"] == "DRAFT"
    assert product["status_code"] == "ACTIVE"
    assert product["created_source"] == "MANUAL"
    assert cands == []


def test_cp02_manufacturer_nullable():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "XYZ 절삭유", manufacturer_name=None)
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
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "Test Product")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {"identity_status": "INVALID_STATE"})
    assert exc.value.status_code == 400


def test_cp05_invalid_status_code_reject():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "Test Product")
    with pytest.raises(svc.MsdsProductError):
        svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {"status_code": "DELETED"})


def test_cp06_invalid_created_source_reject():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.create_product(sb, CALLER_A, FAC_A1, "Test", created_source="UNKNOWN_SOURCE")
    assert exc.value.status_code == 400


def test_cp07_no_company_403():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.create_product(sb, NO_CO, FAC_A1, "Test")
    assert exc.value.status_code == 403
    assert exc.value.code == "NO_COMPANY"


def test_cp08_inactive_lifecycle():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "세척제")
    assert product["status_code"] == "ACTIVE"
    inactive = svc.deactivate_product(sb, CALLER_A, FAC_A1, product["id"])
    assert inactive["status_code"] == "INACTIVE"
    active = svc.reactivate_product(sb, CALLER_A, FAC_A1, product["id"])
    assert active["status_code"] == "ACTIVE"


def test_cp09_deactivate_idempotent():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "세척제")
    r1 = svc.deactivate_product(sb, CALLER_A, FAC_A1, product["id"])
    r2 = svc.deactivate_product(sb, CALLER_A, FAC_A1, product["id"])
    assert r1["status_code"] == "INACTIVE"
    assert r2["status_code"] == "INACTIVE"


def test_cp10_product_not_found_404():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, FAC_A1, str(uuid.uuid4()))
    assert exc.value.status_code == 404


def test_cp11_update_normalizes_name():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "Old Name")
    updated = svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {"product_name": "  New Name  "})
    assert updated["product_name"] == "New Name"
    assert updated["product_name_normalized"] == "new name"


def test_cp12_identity_status_transition():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "테스트")
    assert product["identity_status"] == "DRAFT"
    confirmed = svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {"identity_status": "CONFIRMED"})
    assert confirmed["identity_status"] == "CONFIRMED"
    review = svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {"identity_status": "REVIEW_REQUIRED"})
    assert review["identity_status"] == "REVIEW_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# ID — Identifier 단위 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_id01_identifier_add():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품A")
    ident = svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
        "identifier_type": "BARCODE",
        "identifier_value": "1234567890",
    })
    assert ident["identifier_type"] == "BARCODE"
    assert ident["identifier_value"] == "1234567890"
    assert ident["is_active"] is True
    assert ident["factory_id"] == FAC_A1


def test_id02_multiple_identifiers_per_product():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품B")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {"identifier_type": "BARCODE", "identifier_value": "111"})
    svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {"identifier_type": "GTIN", "identifier_value": "222"})
    items = svc.list_identifiers(sb, CALLER_A, FAC_A1, product["id"])
    assert len(items) == 2


def test_id03_same_product_active_exact_identifier_duplicate_contract():
    # uidx_cpi_active_unique: FakeSB 미적용, 실 DB에서 UNIQUE INDEX가 차단함
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품C")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {"identifier_type": "BARCODE", "identifier_value": "999"})
    ident2 = svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {"identifier_type": "BARCODE", "identifier_value": "999"})
    assert ident2["identifier_normalized"] == "999"


def test_id05_leading_zero_identifier_preserved():
    assert svc.normalize_identifier("00012345") == "00012345"
    assert svc.normalize_identifier("0000001") == "0000001"
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "EAN 제품")
    ident = svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
        "identifier_type": "EAN",
        "identifier_value": "00012345678905",
    })
    assert ident["identifier_normalized"] == "00012345678905"


def test_id06_identifier_deactivate():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품D")
    ident = svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "777"
    })
    result = svc.deactivate_identifier(sb, CALLER_A, FAC_A1, product["id"], ident["id"])
    assert result["is_active"] is False


def test_id08_identifier_invalid_type_reject():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품E")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
            "identifier_type": "INVALID_TYPE",
            "identifier_value": "123",
        })
    assert exc.value.status_code == 400


def test_id09_identifier_empty_value_reject():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품F")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
            "identifier_type": "BARCODE",
            "identifier_value": "   ",
        })
    assert exc.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# DUP — Duplicate Candidate (factory 기준)
# ═══════════════════════════════════════════════════════════════════════════════

def test_dup01_exact_identifier_same_site():
    sb = _make_sb()
    product1, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품X")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "BARCODE-001"
    })
    _, candidates = svc.create_product(sb, CALLER_A, FAC_A1, "제품X 복사", identifiers=[{
        "identifier_type": "BARCODE",
        "identifier_value": "BARCODE-001",
    }])
    assert any(c["reason"] == "EXACT_IDENTIFIER" for c in candidates)
    assert any(c["product_id"] == product1["id"] for c in candidates)


def test_dup02_different_site_same_identifier_no_candidate():
    """동일 회사 다른 시설의 동일 Barcode = duplicate 아님."""
    sb = _make_sb()
    product_a1, _ = svc.create_product(sb, CALLER_A, FAC_A1, "A1 제품")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product_a1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "SHARED-BC"
    })
    _, candidates = svc.create_product(sb, CALLER_A, FAC_A2, "A2 제품", identifiers=[{
        "identifier_type": "BARCODE",
        "identifier_value": "SHARED-BC",
    }])
    assert not any(c["reason"] == "EXACT_IDENTIFIER" for c in candidates)


def test_dup03_name_manufacturer_same_site():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "ABC 세척제", manufacturer_name="ABC Chemical")
    _, candidates = svc.create_product(sb, CALLER_A, FAC_A1, "abc 세척제", manufacturer_name="abc chemical")
    assert any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in candidates)


def test_dup04_manufacturer_null_no_false_positive():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "공통 제품명", manufacturer_name=None)
    _, candidates = svc.create_product(sb, CALLER_A, FAC_A1, "공통 제품명", manufacturer_name=None)
    assert not any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in candidates)


def test_dup05_candidate_does_not_auto_merge():
    sb = _make_sb()
    product1, _ = svc.create_product(sb, CALLER_A, FAC_A1, "제품Y")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "SAME-CODE"
    })
    product2, candidates = svc.create_product(sb, CALLER_A, FAC_A1, "제품Y 복사", identifiers=[{
        "identifier_type": "BARCODE", "identifier_value": "SAME-CODE",
    }])
    p1 = sb.table("chemical_products").select("*").eq("id", product1["id"]).execute()
    p2 = sb.table("chemical_products").select("*").eq("id", product2["id"]).execute()
    assert len(p1.data) == 1
    assert len(p2.data) == 1
    assert candidates


# ═══════════════════════════════════════════════════════════════════════════════
# SITE — 시설 격리 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_site01_create_product_at_site():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "A1 세척제")
    assert product["factory_id"] == FAC_A1


def test_site02_site_a1_list_only_site_a1():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "A1 제품")
    svc.create_product(sb, CALLER_A, FAC_A2, "A2 제품")
    result = svc.list_products(sb, CALLER_A, FAC_A1)
    assert all(i["factory_id"] == FAC_A1 for i in result["items"])
    assert len(result["items"]) == 1


def test_site03_same_company_site_a2_not_in_site_a1_list():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A2, "A2 제품")
    result = svc.list_products(sb, CALLER_A, FAC_A1)
    assert result["items"] == []
    assert result["total"] == 0


def test_site04_same_product_name_may_exist_in_a1_and_a2():
    """동일 회사 시설 A1/A2에 동일 이름 제품이 각각 존재 가능."""
    sb = _make_sb()
    p_a1, _ = svc.create_product(sb, CALLER_A, FAC_A1, "ABC 세척제", manufacturer_name="ABC Chemical")
    p_a2, cands = svc.create_product(sb, CALLER_A, FAC_A2, "ABC 세척제", manufacturer_name="ABC Chemical")
    assert p_a1["id"] != p_a2["id"]
    assert not any(c["reason"] == "POSSIBLE_DUPLICATE_NAME_MFR" for c in cands)


def test_site05_same_barcode_may_exist_in_a1_and_a2():
    """동일 Barcode가 A1/A2에 각각 존재 가능."""
    sb = _make_sb()
    p_a1, _ = svc.create_product(sb, CALLER_A, FAC_A1, "A1 제품")
    svc.add_identifier(sb, CALLER_A, FAC_A1, p_a1["id"], {
        "identifier_type": "BARCODE", "identifier_value": "SHARED-BC"
    })
    p_a2, cands = svc.create_product(sb, CALLER_A, FAC_A2, "A2 제품", identifiers=[
        {"identifier_type": "BARCODE", "identifier_value": "SHARED-BC"}
    ])
    assert not any(c["reason"] == "EXACT_IDENTIFIER" for c in cands)


def test_site06_cross_company_factory_inaccessible():
    """Company A 사용자가 Company B 공장에 접근 불가."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, CALLER_A, FAC_B)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_site07_cross_company_product_inaccessible():
    """Company A 사용자가 Company B 공장의 제품에 접근 불가."""
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, FAC_B, product_b["id"])
    assert exc.value.status_code == 404


def test_site08_factory_id_immutable_in_patch():
    """update_product 에서 factory_id 변경 시도는 무시됨."""
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "테스트 제품")
    updated = svc.update_product(sb, CALLER_A, FAC_A1, product["id"], {
        "factory_id": FAC_A2,
        "product_name": "New Name",
    })
    assert updated["factory_id"] == FAC_A1
    assert updated["product_name"] == "New Name"


# ═══════════════════════════════════════════════════════════════════════════════
# TEN — Tenant Isolation (BOLA) 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_ten01_company_a_list_cannot_see_company_b():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "A사 제품")
    svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    result = svc.list_products(sb, CALLER_A, FAC_A1)
    assert all(i["factory_id"] == FAC_A1 for i in result["items"])


def test_ten02_company_a_get_b_product_inaccessible():
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, FAC_A1, product_b["id"])
    assert exc.value.status_code == 404


def test_ten03_company_a_patch_b_product_inaccessible():
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.update_product(sb, CALLER_A, FAC_A1, product_b["id"], {"product_name": "탈취 시도"})
    assert exc.value.status_code == 404


def test_ten04_company_a_deactivate_b_product_inaccessible():
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.deactivate_product(sb, CALLER_A, FAC_A1, product_b["id"])
    assert exc.value.status_code == 404


def test_ten05_company_a_add_identifier_to_b_product_inaccessible():
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.add_identifier(sb, CALLER_A, FAC_A1, product_b["id"], {
            "identifier_type": "BARCODE", "identifier_value": "hack"
        })
    assert exc.value.status_code == 404


def test_ten06_company_a_deactivate_identifier_on_b_product_inaccessible():
    sb = _make_sb()
    product_b, _ = svc.create_product(sb, CALLER_B, FAC_B, "B사 제품")
    ident_b = svc.add_identifier(sb, CALLER_B, FAC_B, product_b["id"], {
        "identifier_type": "BARCODE", "identifier_value": "bcode"
    })
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.deactivate_identifier(sb, CALLER_A, FAC_A1, product_b["id"], ident_b["id"])
    assert exc.value.status_code == 404


def test_ten07_same_company_cross_site_product_inaccessible_by_product_id():
    """동일 회사 내 Site A1 사용자가 Site A2 product_id 로 접근 불가."""
    sb = _make_sb()
    product_a2, _ = svc.create_product(sb, CALLER_A, FAC_A2, "A2 제품")
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.get_product(sb, CALLER_A, FAC_A1, product_a2["id"])
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Router 레벨 테스트
# ═══════════════════════════════════════════════════════════════════════════════

@requires_client
def test_router_create_product_201():
    c = _client(CALLER_A)
    r = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "ABC 세척제"})
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "success"
    assert d["data"]["product_name"] == "ABC 세척제"
    assert d["data"]["factory_id"] == FAC_A1
    assert "duplicate_candidates" in d


@requires_client
def test_router_list_products_200():
    store = {}
    c = _client(CALLER_A, store)
    c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "제품1"})
    c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "제품2"})
    r = c.get(f"/me/msds/factories/{FAC_A1}/products")
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= 2


@requires_client
def test_router_get_product_200():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "세척제"})
    pid = created.json()["data"]["id"]
    r = c.get(f"/me/msds/factories/{FAC_A1}/products/{pid}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == pid


@requires_client
def test_router_patch_product():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "Old"})
    pid = created.json()["data"]["id"]
    r = c.patch(f"/me/msds/factories/{FAC_A1}/products/{pid}", json={"product_name": "New"})
    assert r.status_code == 200
    assert r.json()["data"]["product_name"] == "New"


@requires_client
def test_router_deactivate_reactivate():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "Cycle"})
    pid = created.json()["data"]["id"]
    r1 = c.post(f"/me/msds/factories/{FAC_A1}/products/{pid}/deactivate")
    assert r1.status_code == 200
    assert r1.json()["data"]["status_code"] == "INACTIVE"
    r2 = c.post(f"/me/msds/factories/{FAC_A1}/products/{pid}/reactivate")
    assert r2.status_code == 200
    assert r2.json()["data"]["status_code"] == "ACTIVE"


@requires_client
def test_router_add_get_deactivate_identifier():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "바코드 제품"})
    pid = created.json()["data"]["id"]

    r_add = c.post(f"/me/msds/factories/{FAC_A1}/products/{pid}/identifiers", json={
        "identifier_type": "BARCODE",
        "identifier_value": "9876543210",
    })
    assert r_add.status_code == 201
    iid = r_add.json()["data"]["id"]

    r_list = c.get(f"/me/msds/factories/{FAC_A1}/products/{pid}/identifiers")
    assert r_list.status_code == 200
    assert r_list.json()["data"]["total"] == 1

    r_del = c.delete(f"/me/msds/factories/{FAC_A1}/products/{pid}/identifiers/{iid}")
    assert r_del.status_code == 200
    assert r_del.json()["data"]["is_active"] is False


@requires_client
def test_router_forbidden_body_fields_422():
    c = _client(CALLER_A)
    r = c.post(f"/me/msds/factories/{FAC_A1}/products", json={
        "product_name": "X", "company_id": "hack"
    })
    assert r.status_code == 422


@requires_client
def test_router_no_company_403():
    c = _client(NO_CO)
    r = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "X"})
    assert r.status_code == 403


@requires_client
def test_router_cross_factory_get_404():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "A1 전용"})
    pid = created.json()["data"]["id"]
    # FAC_A2 로 같은 product_id 접근 — 404
    r = c.get(f"/me/msds/factories/{FAC_A2}/products/{pid}")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Forbidden Area Guard — factory_materials / material_legal_master 불변
# ═══════════════════════════════════════════════════════════════════════════════

def test_forbidden_factory_materials_not_touched():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "테스트")
    touched = {t for (t, _) in sb.log}
    assert "factory_materials" not in touched
    assert "material_legal_master" not in touched


def test_forbidden_msds_ref_not_touched():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "테스트")
    touched = {t for (t, _) in sb.log}
    for table in touched:
        assert not table.startswith("msds_ref")


# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH — q 검색 (factory-scoped)
# ═══════════════════════════════════════════════════════════════════════════════

def test_search01_product_name_search():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "ABC 세척제", manufacturer_name="XYZ Chemical")
    svc.create_product(sb, CALLER_A, FAC_A1, "전혀 다른 제품")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="abc 세척")
    assert len(result["items"]) == 1
    assert result["items"][0]["product_name"] == "ABC 세척제"


def test_search02_manufacturer_search():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "제품1", manufacturer_name="ABC Chemical")
    svc.create_product(sb, CALLER_A, FAC_A1, "제품2", manufacturer_name="XYZ Corp")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="abc chem")
    assert len(result["items"]) == 1
    assert result["items"][0]["product_name"] == "제품1"


def test_search03_identifier_search():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "바코드 제품")
    svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "BARCODE-99999"
    })
    svc.create_product(sb, CALLER_A, FAC_A1, "다른 제품")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="99999")
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == product["id"]


def test_search04_no_match():
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A1, "ABC 세척제")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="전혀없는검색어xyz123")
    assert result["items"] == []
    assert result["total"] == 0


def test_search05_different_site_excluded_same_company():
    """동일 회사 다른 시설 제품은 검색에서 제외."""
    sb = _make_sb()
    svc.create_product(sb, CALLER_A, FAC_A2, "A2 세척제")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="세척제")
    assert result["items"] == []
    assert result["total"] == 0


def test_search06_cross_company_excluded():
    sb = _make_sb()
    svc.create_product(sb, CALLER_B, FAC_B, "B사 세척제")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="세척제")
    assert result["items"] == []


def test_search07_pagination_after_filtering():
    sb = _make_sb()
    for i in range(5):
        svc.create_product(sb, CALLER_A, FAC_A1, f"세척제 {i:02d}")
    svc.create_product(sb, CALLER_A, FAC_A1, "절삭유")
    result = svc.list_products(sb, CALLER_A, FAC_A1, q="세척제", limit=2, offset=0)
    assert result["total"] == 5
    assert len(result["items"]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# PROV — Provenance (created_source) 보호 테스트
# ═══════════════════════════════════════════════════════════════════════════════

def test_prov03_normal_product_create_source_manual():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "Test Product")
    assert product["created_source"] == "MANUAL"


def test_prov04_normal_identifier_create_source_manual():
    sb = _make_sb()
    product, _ = svc.create_product(sb, CALLER_A, FAC_A1, "Test Product")
    ident = svc.add_identifier(sb, CALLER_A, FAC_A1, product["id"], {
        "identifier_type": "BARCODE", "identifier_value": "TESTCODE"
    })
    assert ident["created_source"] == "MANUAL"


@requires_client
def test_prov01_post_product_with_created_source_422():
    c = _client(CALLER_A)
    r = c.post(f"/me/msds/factories/{FAC_A1}/products", json={
        "product_name": "Test",
        "created_source": "PDF"
    })
    assert r.status_code == 422


@requires_client
def test_prov02_post_identifier_with_created_source_422():
    store = {}
    c = _client(CALLER_A, store)
    created = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "Test"})
    pid = created.json()["data"]["id"]
    r = c.post(f"/me/msds/factories/{FAC_A1}/products/{pid}/identifiers", json={
        "identifier_type": "BARCODE",
        "identifier_value": "CODE123",
        "created_source": "PHOTO"
    })
    assert r.status_code == 422


@requires_client
def test_prov05_product_created_source_server_owned_manual():
    store = {}
    c = _client(CALLER_A, store)
    r = c.post(f"/me/msds/factories/{FAC_A1}/products", json={"product_name": "Manual Product"})
    assert r.status_code == 201
    assert r.json()["data"]["created_source"] == "MANUAL"


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH — role_data_scope tier 기반 Factory 접근 권한
# ═══════════════════════════════════════════════════════════════════════════════

def test_auth01_company_scope_can_access_site_a1():
    sb = _make_sb()
    result = svc.list_products(sb, AUTH_COMPANY_A, FAC_A1)
    assert "items" in result


def test_auth02_company_scope_can_access_site_a2():
    sb = _make_sb()
    result = svc.list_products(sb, AUTH_COMPANY_A, FAC_A2)
    assert "items" in result


def test_auth03_company_scope_cannot_access_other_company_site():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_COMPANY_A, FAC_B)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth04_factory_scope_can_access_own_factory():
    sb = _make_sb()
    result = svc.list_products(sb, AUTH_FACTORY_A1, FAC_A1)
    assert "items" in result


def test_auth05_factory_scope_cannot_access_same_company_other_factory():
    """핵심 회귀: FACTORY 사용자가 같은 회사 다른 시설에 접근 불가."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_FACTORY_A1, FAC_A2)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth06_factory_scope_cannot_access_other_company_factory():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_FACTORY_A1, FAC_B)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth07_factory_scope_with_no_factory_id_fail_closed():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_FACTORY_NOFID, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth08_team_scope_can_access_own_factory():
    sb = _make_sb()
    result = svc.list_products(sb, AUTH_TEAM_A1, FAC_A1)
    assert "items" in result


def test_auth09_team_scope_cannot_access_same_company_other_factory():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_TEAM_A1, FAC_A2)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth10_team_scope_with_no_factory_id_fail_closed():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_TEAM_NOFID, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth11_unknown_role_code_no_factory_id_fail_closed():
    """미정의 role_code + factory_id 없음 → fail-closed."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_UNKNOWN_ROLE, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth12_platform_scope_fail_closed():
    """PLATFORM scope_type → fail-closed (PLATFORM은 화학제품 관리 tier 아님)."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_PLATFORM, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth13_assigned_own_factory_allow():
    sb = _make_sb()
    result = svc.list_products(sb, AUTH_ASSIGNED_A1, FAC_A1)
    assert "items" in result


def test_auth14_assigned_same_company_other_factory_deny():
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_ASSIGNED_A1, FAC_A2)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth15_assigned_no_factory_id_fail_closed():
    """PATCH-005 핵심: ASSIGNED + factory_id 미배정 → DENY (company fallback 금지).
    factory_id scoped resource에서 company fallback은 같은 회사 전 시설 노출이므로 불허."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_ASSIGNED_NOFID, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth16_undefined_role_no_factory_id_fail_closed():
    """미정의 role + factory_id 없음 → strict DB 조회 실패 → fail-closed."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_UNKNOWN_ROLE, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth17_undefined_role_with_factory_id_fail_closed():
    """PATCH-005 핵심: 미정의 role + factory_id 있음 → TEAM fallback 불허 → fail-closed.
    _resolve_scope_strict()의 strict DB 조회로만 tier를 결정하므로
    role_data_scope에 없는 role_code는 factory_id가 있어도 DENY."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_UNKNOWN_WITH_FID, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth18_scope_lookup_exception_fail_closed():
    """role_data_scope 조회 시 예외 발생 → fail-closed."""
    class _ExceptionSB(FakeSB):
        def table(self, name):
            if name == "role_data_scope":
                class _Raiser:
                    def select(self, *a, **k): return self
                    def eq(self, *a, **k): return self
                    def limit(self, *a, **k): return self
                    def execute(self): raise RuntimeError("simulated DB error")
                return _Raiser()
            return super().table(name)

    sb = _ExceptionSB({"factories": list(_FACTORIES)})
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_FACTORY_A1, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth19_null_scope_type_fail_closed():
    """role_data_scope row 존재하지만 scope_type=None → fail-closed."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_NULL_SCOPE, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth20_platform_scope_fail_closed_repeat():
    """PLATFORM → fail-closed (AUTH12 동일, WO 번호 유지를 위한 alias)."""
    sb = _make_sb()
    with pytest.raises(svc.MsdsProductError) as exc:
        svc.list_products(sb, AUTH_PLATFORM, FAC_A1)
    assert exc.value.status_code == 404
    assert exc.value.code == "FACTORY_NOT_FOUND"


def test_auth_all_scope_can_access_any_factory():
    """ALL(플랫폼 관리자) — company_id 없어도 factory 존재하면 허용."""
    sb = _make_sb()
    result_a1 = svc.list_products(sb, AUTH_ALL, FAC_A1)
    result_b  = svc.list_products(sb, AUTH_ALL, FAC_B)
    assert "items" in result_a1
    assert "items" in result_b
