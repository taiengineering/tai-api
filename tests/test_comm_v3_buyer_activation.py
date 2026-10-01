"""WO-COMM-V3-BUYER-ACTIVATION-001 — Commercial V3 buyer activation tests.

BA01-BA08  : trusted V3 predicate (_is_commercial_v3_saas_payment)
BA09-BA12  : activation policy (bootstrap Cases A/B/C for V3)
BA13-BA18  : isolation (mismatch, DIAGNOSIS, generic SAAS, legacy, idempotency, payment status)
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION
from services import payment_post_process as pp


# ── FakeSupabase (reuse pattern from test_payment_company_admin_bootstrap) ──

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []

    def select(self, cols="*", *a, **k):
        self._op = "select"; return self

    def insert(self, row):
        self._op = "insert"; self._payload = row; return self

    def update(self, patch):
        self._op = "update"; self._payload = patch; return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def neq(self, c, v): self._filters.append(("neq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and str(rv) != str(v): return False
            if op == "neq" and str(rv) == str(v): return False
            if op == "in" and rv not in v: return False
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


# ── Shared role/capability fixtures ──────────────────────────────────

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


def _base_store(users=None, quotes=None):
    return {
        "users": list(users or []),
        "quotes": list(quotes or []),
        "roles": list(_DEFAULT_ROLES),
        "role_data_scope": list(_DEFAULT_SCOPES),
        "role_menu_permissions": list(_DEFAULT_MENU_PERMS),
    }


def _v3_quote(quote_id="Q-V3", company_id="CO-001"):
    return {
        "id": quote_id,
        "company_id": company_id,
        "source": "member_auto",
        "service_type": "SAAS",
        "items": [{"quote_schema_version": SAAS_QUOTE_SCHEMA_VERSION}],
    }


def _v3_payment(user_id="U-001", company_id="CO-001", quote_id="Q-V3", status_code="PAID"):
    return {
        "id": "PAY-V3",
        "user_id": user_id,
        "company_id": company_id,
        "product_type": "SAAS",
        "status_code": status_code,
        "quote_id": quote_id,
    }


def _pending_buyer(user_id="U-001", company_id="CO-001", role_code="020"):
    return {"id": user_id, "company_id": company_id,
            "role_code": role_code, "status_code": "PENDING", "is_active": False}


def _active_admin(user_id="ADM-001", company_id="CO-001"):
    return {"id": user_id, "company_id": company_id,
            "role_code": "002", "status_code": "ACTIVE", "is_active": True}


# ═══════════════════════════════════════════════════════════════════════════════
# BA01-BA08: Trusted V3 predicate
# ═══════════════════════════════════════════════════════════════════════════════

def test_BA01_valid_saas_quote_v2_returns_true():
    """product_type=SAAS + valid SAAS_QUOTE_V2 quote → True."""
    q = _v3_quote()
    pay = _v3_payment()
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is True


def test_BA02_missing_quote_id_returns_false():
    """product_type=SAAS + quote_id missing → False."""
    pay = _v3_payment(quote_id=None)
    pay.pop("quote_id", None)
    sb = FakeSupabase(_base_store())
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


def test_BA03_quote_company_mismatch_returns_false():
    """quote.company_id != pay.company_id → False."""
    q = _v3_quote(company_id="CO-OTHER")
    pay = _v3_payment(company_id="CO-001")
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


def test_BA04_quote_source_not_member_auto_returns_false():
    """quote.source != member_auto → False."""
    q = _v3_quote()
    q["source"] = "admin_manual"
    pay = _v3_payment()
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


def test_BA05_quote_service_type_not_saas_returns_false():
    """quote.service_type != SAAS → False."""
    q = _v3_quote()
    q["service_type"] = "COMPLIANCE"
    pay = _v3_payment()
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


def test_BA06_quote_items_malformed_returns_false():
    """quote.items not list of 1 → False."""
    q = _v3_quote()
    q["items"] = []  # empty
    pay = _v3_payment()
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False

    q2 = _v3_quote(quote_id="Q-2")
    q2["items"] = "not-a-list"
    pay2 = _v3_payment(quote_id="Q-2")
    sb2 = FakeSupabase(_base_store(quotes=[q2]))
    assert pp._is_commercial_v3_saas_payment(sb2, pay2) is False


def test_BA07_quote_schema_not_saas_quote_v2_returns_false():
    """items[0].quote_schema_version != SAAS_QUOTE_V2 → False."""
    q = _v3_quote()
    q["items"] = [{"quote_schema_version": "SAAS_QUOTE_V1"}]
    pay = _v3_payment()
    sb = FakeSupabase(_base_store(quotes=[q]))
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


def test_BA08_lookup_exception_returns_false():
    """DB lookup exception → fail closed (False)."""
    pay = _v3_payment()
    sb = MagicMock()
    sb.table.side_effect = Exception("db error")
    assert pp._is_commercial_v3_saas_payment(sb, pay) is False


# ═══════════════════════════════════════════════════════════════════════════════
# BA09-BA12: Activation policy
# ═══════════════════════════════════════════════════════════════════════════════

def test_BA09_existing_admin_v3_buyer_gets_activated():
    """active_admin > 0 + V3 PENDING buyer → buyer becomes ACTIVE, role unchanged."""
    admin = _active_admin()
    buyer = _pending_buyer(role_code="020")
    q = _v3_quote()
    store = _base_store(users=[admin, buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment()
    pp._bootstrap_buyer_company_admin(sb, pay)
    updated = next(u for u in store["users"] if u["id"] == "U-001")
    assert updated["status_code"] == "ACTIVE"
    assert updated["is_active"] is True
    assert updated["role_code"] == "020"  # role preserved


def test_BA10_v3_already_active_buyer_no_churn():
    """active_admin > 0 + V3 buyer already ACTIVE → no DB update."""
    admin = _active_admin()
    buyer = {"id": "U-001", "company_id": "CO-001",
             "role_code": "020", "status_code": "ACTIVE", "is_active": True}
    q = _v3_quote()
    store = _base_store(users=[admin, buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment()
    pp._bootstrap_buyer_company_admin(sb, pay)
    # Verify no users update was logged
    user_updates = [op for tbl, op in sb.log if tbl == "users" and op == "update"]
    assert len(user_updates) == 0


def test_BA11_no_admin_v3_buyer_with_capability_case_a():
    """no active admin + V3 buyer with 010 role → role preserved + ACTIVE (Case A)."""
    buyer = _pending_buyer(role_code="010")
    q = _v3_quote()
    store = _base_store(users=[buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment()
    pp._bootstrap_buyer_company_admin(sb, pay)
    updated = next(u for u in store["users"] if u["id"] == "U-001")
    assert updated["status_code"] == "ACTIVE"
    assert updated["is_active"] is True
    assert updated["role_code"] == "010"  # Case A: role preserved


def test_BA12_no_admin_v3_non_admin_buyer_case_b():
    """no active admin + V3 non-admin buyer → role=002 + ACTIVE (Case B)."""
    buyer = _pending_buyer(role_code="020")
    q = _v3_quote()
    store = _base_store(users=[buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment()
    pp._bootstrap_buyer_company_admin(sb, pay)
    updated = next(u for u in store["users"] if u["id"] == "U-001")
    assert updated["status_code"] == "ACTIVE"
    assert updated["is_active"] is True
    assert updated["role_code"] == "002"  # Case B: promoted


# ═══════════════════════════════════════════════════════════════════════════════
# BA13-BA18: Isolation
# ═══════════════════════════════════════════════════════════════════════════════

def test_BA13_buyer_company_id_mismatch_noop():
    """buyer.company_id != pay.company_id → NOOP, buyer unchanged."""
    buyer = {"id": "U-001", "company_id": "CO-OTHER",
             "role_code": "020", "status_code": "PENDING", "is_active": False}
    q = _v3_quote(company_id="CO-001")
    store = _base_store(users=[buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment(user_id="U-001", company_id="CO-001")
    pp._bootstrap_buyer_company_admin(sb, pay)
    unchanged = next(u for u in store["users"] if u["id"] == "U-001")
    assert unchanged["status_code"] == "PENDING"
    assert unchanged["is_active"] is False


def test_BA14_diagnosis_payment_noop():
    """DIAGNOSIS product_type → NOOP, no activation."""
    buyer = _pending_buyer()
    store = _base_store(users=[buyer])
    sb = FakeSupabase(store)
    pay = {"id": "PAY-DIAG", "user_id": "U-001", "company_id": "CO-001",
           "product_type": "DIAGNOSIS", "status_code": "PAID"}
    pp._bootstrap_buyer_company_admin(sb, pay)
    unchanged = next(u for u in store["users"] if u["id"] == "U-001")
    assert unchanged["status_code"] == "PENDING"


def test_BA15_generic_saas_without_trusted_v3_quote_noop():
    """product_type=SAAS but no quote_id → _is_commercial_v3 returns False → NOOP."""
    buyer = _pending_buyer()
    store = _base_store(users=[buyer])
    sb = FakeSupabase(store)
    pay = {"id": "PAY-X", "user_id": "U-001", "company_id": "CO-001",
           "product_type": "SAAS", "status_code": "PAID"}  # no quote_id
    pp._bootstrap_buyer_company_admin(sb, pay)
    unchanged = next(u for u in store["users"] if u["id"] == "U-001")
    assert unchanged["status_code"] == "PENDING"


def test_BA16_legacy_saas_case_c_unchanged():
    """Legacy SaaS (SAAS_INDUSTRY) Case C behavior: active admin → NOOP."""
    from services.payment_helpers import SAAS_PRODUCT_TYPES
    admin = _active_admin()
    buyer = _pending_buyer()
    store = _base_store(users=[admin, buyer])
    sb = FakeSupabase(store)
    pay = {"id": "PAY-LEG", "user_id": "U-001", "company_id": "CO-001",
           "product_type": "SAAS_INDUSTRY", "status_code": "PAID",
           "plan_code": "INDUSTRY_PRO"}
    assert "SAAS_INDUSTRY" in SAAS_PRODUCT_TYPES
    pp._bootstrap_buyer_company_admin(sb, pay)
    unchanged = next(u for u in store["users"] if u["id"] == "U-001")
    # Legacy Case C: buyer should NOT be activated
    assert unchanged["status_code"] == "PENDING"


def test_BA17_renewal_repeated_post_process_idempotent():
    """Already ACTIVE V3 buyer + repeated bootstrap → no role churn, no update."""
    admin = _active_admin()
    buyer = {"id": "U-001", "company_id": "CO-001",
             "role_code": "010", "status_code": "ACTIVE", "is_active": True}
    q = _v3_quote()
    store = _base_store(users=[admin, buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment()
    # Call twice (simulates renewal re-entry)
    pp._bootstrap_buyer_company_admin(sb, pay)
    pp._bootstrap_buyer_company_admin(sb, pay)
    updates = [op for tbl, op in sb.log if tbl == "users" and op == "update"]
    assert len(updates) == 0
    final = next(u for u in store["users"] if u["id"] == "U-001")
    assert final["role_code"] == "010"  # no role churn


def test_BA18_pending_payment_via_on_payment_success_sync_no_activation():
    """on_payment_success_sync with status_code=PENDING → no bootstrap called."""
    buyer = _pending_buyer()
    q = _v3_quote()
    store = _base_store(users=[buyer], quotes=[q])
    sb = FakeSupabase(store)
    pay = _v3_payment(status_code="PENDING")
    pay["id"] = "PAY-PEND"

    # Patch get_supabase to return our FakeSupabase
    # and short-circuit after the status check (payment not in PAID_STATUS_CODES)
    with patch("services.payment_post_process.get_supabase", return_value=sb), \
         patch.object(sb, "table", wraps=sb.table) as mock_table:
        # Insert payment into store so it is found
        store["payments"] = [pay]
        pp.on_payment_success_sync("PAY-PEND")

    # buyer should not have been activated
    unchanged = next(u for u in store["users"] if u["id"] == "U-001")
    assert unchanged["status_code"] == "PENDING"
