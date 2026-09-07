"""WP-A · Payment buyer bootstrap 3-case 단위테스트.

WO-SAFE-COMPANY-ACCESS-001. SaaS 성공만 대상.

케이스 (F01~F08 표본):
  F01 case A : 회사 관리 capability ACTIVE 0 + buyer 가 010(대표이사) → role 유지 + ACTIVE
  F02 case A : buyer 가 011(안전보건책임자) → role 유지 + ACTIVE
  F03 case B : capability ACTIVE 0 + buyer 가 non-capability role → 002 + ACTIVE
  F04 case C : 이미 관리 capability ACTIVE 존재 → buyer 자동 승격 없음(NOOP)
  F05 mismatch : buyer.company_id != payment.company_id → NOOP + warning
  F06 idempotent : 반복 후처리 시 role churn 0 (이미 정상 상태)
  F07 non-SaaS : DIAGNOSIS 결제 등은 bootstrap 대상 아님 (NOOP)
  F08 INV : 신규 코드에 총원 제한 카운터 신설 없음
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import payment_post_process as pp
from services import company_user_svc as cus


# ── FakeSupabase (in-memory) ────────────────────────────────────────
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._count_exact = False
        self._range = None; self._order = None; self._limit = None
    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def neq(self, c, v): self._filters.append(("neq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def ilike(self, c, pattern): self._filters.append(("ilike", c, pattern)); return self
    def limit(self, n): return self
    def order(self, col, *, desc=False, **k): return self
    def range(self, s, e): return self
    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and str(rv) != str(v): return False
            if op == "neq" and str(rv) == str(v): return False
            if op == "in" and rv not in v: return False
            if op == "ilike":
                pat = str(v).lower(); s = str(rv or "").lower()
                if pat.startswith("%") and pat.endswith("%"):
                    if pat.strip("%") not in s: return False
                elif pat.endswith("%"):
                    if not s.startswith(pat.rstrip("%")): return False
        return True
    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            matched = [r for r in rows if self._match(r)]
            return _Result([dict(r) for r in matched])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched: r.update(self._payload)
            return _Result([dict(r) for r in matched])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []
    def table(self, name): return _Query(self.store, name, self.log)


# ── Fixtures ────────────────────────────────────────────────────────
_DEFAULT_ROLES = [
    {"role_code": "002", "role_name": "회사관리자", "is_active": True},
    {"role_code": "010", "role_name": "대표이사", "is_active": True},
    {"role_code": "011", "role_name": "안전보건관리책임자", "is_active": True},
    {"role_code": "020", "role_name": "일반사용자", "is_active": True},
]
_DEFAULT_SCOPES = [
    {"role_code": "002", "scope_type": "COMPANY"},
    {"role_code": "010", "scope_type": "COMPANY"},
    {"role_code": "011", "scope_type": "COMPANY"},
    {"role_code": "020", "scope_type": "FACTORY"},
]
_DEFAULT_MENU_PERMS = [
    {"role_code": rc, "menu_code": "worker-list",
     "can_list": True, "can_read": True, "can_create": True,
     "can_update": True, "can_delete": True}
    for rc in ("002", "010", "011")
] + [
    {"role_code": "020", "menu_code": "worker-list",
     "can_list": True, "can_read": True, "can_create": False,
     "can_update": False, "can_delete": False}
]


def _base_store(users=None):
    return {
        "users": list(users or []),
        "roles": list(_DEFAULT_ROLES),
        "role_data_scope": list(_DEFAULT_SCOPES),
        "role_menu_permissions": list(_DEFAULT_MENU_PERMS),
    }


def _saas_payment(user_id, company_id, product_type="SAAS_INDUSTRY"):
    """SAAS_PRODUCT_TYPES 에 등록된 값 사용."""
    return {"id": "PAY-1", "user_id": user_id, "company_id": company_id,
            "product_type": product_type, "status_code": "PAID",
            "plan_code": "INDUSTRY_PRO"}


# ════════════════════════════════════════════════════════════════════
# F01 · F02 : case A (capability 0 + buyer 가 010/011)
# ════════════════════════════════════════════════════════════════════
def test_F01_case_A_010_role_preserved_and_activated():
    buyer = {"id": "U-CEO", "company_id": "C-A", "role_code": "010",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-CEO", "C-A")
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-CEO"][0]
    assert u["role_code"] == "010"                                   # 보존
    assert u["status_code"] == "ACTIVE"
    assert u["is_active"] is True


def test_F02_case_A_011_role_preserved_and_activated():
    buyer = {"id": "U-SHM", "company_id": "C-A", "role_code": "011",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-SHM", "C-A")
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-SHM"][0]
    assert u["role_code"] == "011"
    assert u["status_code"] == "ACTIVE" and u["is_active"] is True


# ════════════════════════════════════════════════════════════════════
# F03 : case B (capability 0 + non-capability role → 002)
# ════════════════════════════════════════════════════════════════════
def test_F03_case_B_non_capability_becomes_002():
    buyer = {"id": "U-U", "company_id": "C-A", "role_code": "020",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-U", "C-A")
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-U"][0]
    assert u["role_code"] == "002"
    assert u["status_code"] == "ACTIVE" and u["is_active"] is True


# ════════════════════════════════════════════════════════════════════
# F04 : case C (이미 관리 capability ACTIVE 존재 → NOOP)
# ════════════════════════════════════════════════════════════════════
def test_F04_case_C_existing_admin_noop_on_buyer():
    existing_admin = {"id": "U-ADM", "company_id": "C-A", "role_code": "002",
                       "status_code": "ACTIVE", "is_active": True}
    buyer = {"id": "U-U2", "company_id": "C-A", "role_code": "020",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[existing_admin, buyer]))
    pay = _saas_payment("U-U2", "C-A")
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-U2"][0]
    # 자동 승격 없음
    assert u["role_code"] == "020"
    assert u["status_code"] == "PENDING"


# ════════════════════════════════════════════════════════════════════
# F05 : mismatch NOOP
# ════════════════════════════════════════════════════════════════════
def test_F05_mismatch_buyer_company_id_noop():
    buyer = {"id": "U-U", "company_id": "C-OTHER", "role_code": "020",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-U", "C-A")
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-U"][0]
    assert u["role_code"] == "020"
    assert u["status_code"] == "PENDING"


# ════════════════════════════════════════════════════════════════════
# F06 : idempotent (반복 후처리 role churn 0)
# ════════════════════════════════════════════════════════════════════
def test_F06_idempotent_no_role_churn_on_repeat():
    buyer = {"id": "U-U3", "company_id": "C-A", "role_code": "002",
             "status_code": "ACTIVE", "is_active": True}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-U3", "C-A")
    # 이미 002/ACTIVE 상태 → 두 번째 실행 시 update 발생하지 않아야 함
    pp._bootstrap_buyer_company_admin(sb, pay)
    updates_1 = sum(1 for t, op in sb.log if t == "users" and op == "update")
    pp._bootstrap_buyer_company_admin(sb, pay)
    updates_2 = sum(1 for t, op in sb.log if t == "users" and op == "update")
    assert updates_1 == updates_2                                    # 추가 update 0


# ════════════════════════════════════════════════════════════════════
# F07 : non-SaaS 는 bootstrap 대상 아님
# ════════════════════════════════════════════════════════════════════
def test_F07_non_saas_payment_no_bootstrap():
    buyer = {"id": "U-D", "company_id": "C-A", "role_code": "020",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-D", "C-A", product_type="DIAGNOSIS")     # non-SaaS
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-D"][0]
    assert u["role_code"] == "020"                                   # 변경 없음
    assert u["status_code"] == "PENDING"


# ── PATCH-2 BLOCKER-2D : bootstrap predicate 분리 ────────────────
def test_P2_2D_saas_renewal_with_contract_id_enters_bootstrap():
    """SaaS renewal (contract_id 있음) 도 bootstrap 대상.
    _is_saas_payment 판정으로 진입 · case B 로 002 승격되어야 함."""
    buyer = {"id": "U-R", "company_id": "C-A", "role_code": "020",
             "status_code": "PENDING", "is_active": False}
    sb = FakeSupabase(_base_store(users=[buyer]))
    pay = _saas_payment("U-R", "C-A", product_type="SAAS_INDUSTRY")
    pay["contract_id"] = "CT-EXISTING"                                # renewal · 기존 계약
    pay["payment_type"] = "RENEWAL"
    pp._bootstrap_buyer_company_admin(sb, pay)
    u = [x for x in sb.store["users"] if x["id"] == "U-R"][0]
    # renewal 이라도 bootstrap 실행 → capability 0 + non-capability → 002 승격 (case B)
    assert u["role_code"] == "002"
    assert u["status_code"] == "ACTIVE" and u["is_active"] is True


def test_P2_2D_is_saas_payment_predicate_contract_id_agnostic():
    """_is_saas_payment 는 contract_id 유무와 무관하게 SaaS + company_id 만 확인."""
    assert pp._is_saas_payment({"product_type": "SAAS_INDUSTRY", "company_id": "C-A"}) is True
    assert pp._is_saas_payment({"product_type": "SAAS_INDUSTRY", "company_id": "C-A",
                                 "contract_id": "CT-1"}) is True                  # renewal
    assert pp._is_saas_payment({"product_type": "DIAGNOSIS", "company_id": "C-A"}) is False
    assert pp._is_saas_payment({"product_type": "SAAS_INDUSTRY"}) is False        # company_id 없음
    assert pp._is_saas_payment({}) is False


def test_P2_2D_INV_bootstrap_uses_new_predicate_not_auto_contract():
    """소스에서 bootstrap 이 _is_saas_payment 사용 · _should_auto_contract 미사용."""
    import inspect
    src = inspect.getsource(pp._bootstrap_buyer_company_admin)
    assert "_is_saas_payment(pay)" in src, \
        "PATCH-2 BLOCKER-2D: _bootstrap_buyer_company_admin 은 _is_saas_payment 를 사용해야 한다"
    assert "_should_auto_contract" not in src, \
        "PATCH-2 BLOCKER-2D: bootstrap 이 _should_auto_contract 를 재사용하면 안 된다 (renewal 누락)"


# ════════════════════════════════════════════════════════════════════
# INV : 신규 코드에 총원 제한 카운터 부재 (unlimited invariant)
# ════════════════════════════════════════════════════════════════════
def test_F08_INV_no_seat_or_user_count_gate_in_bootstrap():
    import inspect
    src = inspect.getsource(pp._bootstrap_buyer_company_admin)
    for tok in ("max_user_count", "seat_limit", "user_gate", "seat_gate", "user_quota"):
        assert tok not in src, f"bootstrap 에 unlimited 위반 토큰 '{tok}' 발견"
