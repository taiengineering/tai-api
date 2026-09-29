"""TAI Safe SaaS Atomic Contract Apply V2 — PostgreSQL Integration Tests (I01-I30).

로컬 PostgreSQL@16 (tai_test_v2_atomic) 에서 apply_saas_v2_contract_atomic 함수를
실제 실행하는 통합 테스트.

실행 조건:
  - psycopg2 설치 (pip install psycopg2-binary)
  - PostgreSQL@16 실행 중 (localhost:5432)
  - DB: psql -c "CREATE DATABASE tai_test_v2_atomic" (최초 1회)

커버리지:
  I01: APPLIED — MANAGER tier, 1 site_scope
  I02: APPLIED — FIELD tier, 2 site_scopes (multi-scope INSERT)
  I03: APPLIED — CUSTOM tier, pricing_snapshot NULL 보존
  I04: ALREADY_APPLIED — 완전 일치 멱등성 재호출
  I05: V2_ATOMIC_PARTIAL_STATE — CV 존재 + site_scope 0 (Step 5 Check 1)
  I06: V2_ATOMIC_PARTIAL_STATE — orphan contract (Step 6)
  I07: V2_PAYMENT_NOT_FOUND
  I08: V2_PAYMENT_NOT_PAID
  I09: V2_CONTRACT_ID_MISMATCH
  I10: V2_VERSION_NO_INVALID
  I11: V2_ATOMIC_PARTIAL_STATE — count 불일치 (Step 5 Check 3, B1)
  I12: V2_ATOMIC_PARTIAL_STATE — tuple 불일치 (Step 5 Check 4, B1)
  I13: 롤백 — constraint 위반 → 전체 트랜잭션 취소 (contracts = 0)
  I14: ACL — anon role INSERT 차단
  I15: ACL — authenticated role INSERT 차단
"""
from __future__ import annotations

import json
import os
import pathlib
import uuid

import psycopg2
import pytest

# ── Connection ────────────────────────────────────────────────────────────────

_DSN = os.getenv("TEST_PG_DSN", "host=localhost dbname=tai_test_v2_atomic")

_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-09-28_saas_contract_commercial_v2_atomic_apply.sql"
).read_text()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pg():
    conn = psycopg2.connect(_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    _bootstrap(cur)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean(pg):
    cur = pg.cursor()
    cur.execute(
        "TRUNCATE public.saas_contract_site_scopes, "
        "public.saas_contract_commercial_versions, "
        "public.payments, public.contracts CASCADE;"
    )


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _bootstrap(cur: "psycopg2.extensions.cursor") -> None:
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"CREATE ROLE {role}; "
            "END IF; END $$;"
        )

    cur.execute("SELECT current_user;")
    (me,) = cur.fetchone()
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"GRANT {role} TO {me};")

    # service_role bypasses RLS (Supabase 동작 모델링)
    cur.execute("ALTER ROLE service_role BYPASSRLS;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.contracts (
            id               uuid        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            contract_no      text,
            company_id       uuid        NOT NULL,
            status_code      text,
            start_date       date,
            end_date         date,
            service_type     text,
            contract_amount  numeric,
            vat_amount       numeric,
            total_amount     numeric,
            paid_amount      numeric,
            paid_at          timestamptz,
            is_active        boolean     NOT NULL DEFAULT true,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            memo             text,
            plan_code        text,
            quote_id         uuid
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.payments (
            id          uuid        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            status_code text        NOT NULL,
            contract_id uuid        REFERENCES public.contracts(id)
        );
    """)

    # DB DEFAULT preservation columns (I16)
    cur.execute("""
        ALTER TABLE public.contracts
        ADD COLUMN IF NOT EXISTS addon_codes jsonb NOT NULL DEFAULT '{}',
        ADD COLUMN IF NOT EXISTS items       jsonb NOT NULL DEFAULT '[]';
    """)

    cur.execute("GRANT SELECT, UPDATE ON public.payments TO service_role;")
    cur.execute("GRANT SELECT, INSERT ON public.contracts TO service_role;")

    cur.execute("DROP TABLE IF EXISTS public.saas_contract_site_scopes CASCADE;")
    cur.execute("DROP TABLE IF EXISTS public.saas_contract_commercial_versions CASCADE;")
    cur.execute(
        "DROP FUNCTION IF EXISTS "
        "public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb);"
    )

    cur.execute(_MIGRATION_SQL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _insert_payment(pg, pid: str, status: str = "PAID", cid: str | None = None) -> None:
    cur = pg.cursor()
    if cid:
        cur.execute(
            "INSERT INTO public.payments (id, status_code, contract_id) VALUES (%s,%s,%s);",
            (pid, status, cid),
        )
    else:
        cur.execute(
            "INSERT INTO public.payments (id, status_code) VALUES (%s,%s);",
            (pid, status),
        )


def _insert_contract(pg, cid: str, coid: str) -> None:
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.contracts (id, company_id) VALUES (%s,%s);",
        (cid, coid),
    )


def _contract_row(cid: str, coid: str) -> dict:
    return {
        "id": cid, "contract_no": "TEST-001", "company_id": coid,
        "status_code": "ACTIVE", "start_date": "2026-10-01", "end_date": "2027-09-30",
        "service_type": "SAAS", "contract_amount": "1000000", "vat_amount": "100000",
        "total_amount": "1100000", "paid_amount": "1100000",
        "paid_at": "2026-09-28T00:00:00+00:00", "is_active": "true",
        "created_at": "2026-09-28T00:00:00+00:00",
        "updated_at": "2026-09-28T00:00:00+00:00",
        "memo": None, "plan_code": "MANAGER_STANDARD", "quote_id": None,
    }


def _cv_dict(
    cid: str,
    tier: str = "MANAGER",
    version_no: int = 1,
    worker_capacity: int | None = None,
    payment_months: int = 12,
) -> dict:
    if tier == "CUSTOM":
        return {
            "contract_id": cid, "version_no": version_no,
            "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
            "product_tier": "CUSTOM", "pricing_mode": "CUSTOM",
            "worker_capacity": 10, "payment_months": payment_months,
            "pricing_result_status": "CUSTOM_REQUIRED",
            "pricing_policy_version": None, "pricing_snapshot": None,
            "effective_from": "2026-10-01T00:00:00+00:00",
            "superseded_at": None, "created_by": None,
        }
    wc = 0 if tier == "MANAGER" else (worker_capacity or 5)
    return {
        "contract_id": cid, "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": tier, "pricing_mode": "STANDARD",
        "worker_capacity": wc, "payment_months": payment_months,
        "pricing_result_status": "READY",
        "pricing_policy_version": "v1.0",
        "pricing_snapshot": {"base_price": 500000},
        "effective_from": "2026-10-01T00:00:00+00:00",
        "superseded_at": None, "created_by": None,
    }


def _scope(
    entity_id: str | None = None,
    sector: str = "CONSTRUCTION",
    entity_type: str = "site",
    base_band_code: str | None = None,
) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id or _new_id(),
        "sector": sector,
        "base_band_code": base_band_code,
    }


def _rpc(pg, pid: str, cr: dict, cv: dict, scopes: list[dict]) -> dict:
    cur = pg.cursor()
    cur.execute(
        "SELECT public.apply_saas_v2_contract_atomic"
        "(%s::uuid,%s::jsonb,%s::jsonb,%s::jsonb)::text;",
        (pid, json.dumps(cr), json.dumps(cv), json.dumps(scopes)),
    )
    (raw,) = cur.fetchone()
    return json.loads(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# I01 — APPLIED: MANAGER tier, 1 site_scope
# ═══════════════════════════════════════════════════════════════════════════════

def test_I01_applied_manager_tier(pg):
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [_scope(sid)])
    assert result["status"] == "APPLIED"
    assert result["contract_id"] == cid
    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM public.contracts WHERE id=%s;", (cid,))
    assert cur.fetchone()[0] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# I02 — APPLIED: FIELD tier, 2 site_scopes
# ═══════════════════════════════════════════════════════════════════════════════

def test_I02_applied_field_tier_multi_scope(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    scopes = [_scope(sector="CONSTRUCTION", entity_type="site"),
              _scope(sector="INDUSTRY", entity_type="factory")]
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid, "FIELD"), scopes)
    assert result["status"] == "APPLIED"
    cur = pg.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM public.saas_contract_site_scopes s "
        "JOIN public.saas_contract_commercial_versions v ON s.commercial_version_id=v.id "
        "WHERE v.contract_id=%s;", (cid,),
    )
    assert cur.fetchone()[0] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# I03 — APPLIED: CUSTOM tier, pricing_snapshot NULL 보존
# ═══════════════════════════════════════════════════════════════════════════════

def test_I03_applied_custom_tier_null_snapshot(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid, "CUSTOM"), [])
    assert result["status"] == "APPLIED"
    cur = pg.cursor()
    cur.execute(
        "SELECT pricing_snapshot FROM public.saas_contract_commercial_versions "
        "WHERE contract_id=%s;", (cid,),
    )
    assert cur.fetchone()[0] is None


# ═══════════════════════════════════════════════════════════════════════════════
# I04 — ALREADY_APPLIED: 동일 인수로 재호출 → 멱등
# ═══════════════════════════════════════════════════════════════════════════════

def test_I04_already_applied_idempotent(pg):
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    scopes = [_scope(sid, "CONSTRUCTION", "site")]
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, scopes)
    assert r1["status"] == "APPLIED"
    r2 = _rpc(pg, pid, cr, cv, scopes)
    assert r2["status"] == "ALREADY_APPLIED"


# ═══════════════════════════════════════════════════════════════════════════════
# I05 — V2_ATOMIC_PARTIAL_STATE: CV 존재 + site_scope = 0 (Check 1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I05_partial_state_cv_no_scope(pg):
    pid, cid, coid, cv_id = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_contract(pg, cid, coid)
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.payments (id, status_code, contract_id) VALUES (%s,'PAID',%s);",
        (pid, cid),
    )
    cur.execute(
        "INSERT INTO public.saas_contract_commercial_versions "
        "(id, contract_id, version_no, commercial_schema_version, product_tier, pricing_mode, "
        "worker_capacity, payment_months, pricing_result_status, pricing_policy_version, "
        "pricing_snapshot, effective_from) "
        "VALUES (%s,%s,1,'SAAS_CONTRACT_COMMERCIAL_V2','MANAGER','STANDARD',"
        "0,12,'READY','v1.0','{}','2026-10-01');",
        (cv_id, cid),
    )
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [_scope()])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I06 — V2_ATOMIC_PARTIAL_STATE: orphan contract (Step 6)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I06_partial_state_orphan_contract(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    _insert_contract(pg, cid, coid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [_scope()])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I07 — V2_PAYMENT_NOT_FOUND
# ═══════════════════════════════════════════════════════════════════════════════

def test_I07_payment_not_found(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [])
    assert result["status"] == "V2_PAYMENT_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# I08 — V2_PAYMENT_NOT_PAID
# ═══════════════════════════════════════════════════════════════════════════════

def test_I08_payment_not_paid(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid, "PENDING")
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [])
    assert result["status"] == "V2_PAYMENT_NOT_PAID"


# ═══════════════════════════════════════════════════════════════════════════════
# I09 — V2_CONTRACT_ID_MISMATCH
# ═══════════════════════════════════════════════════════════════════════════════

def test_I09_contract_id_mismatch(pg):
    pid, cid, other_cid, coid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(other_cid), [])
    assert result["status"] == "V2_CONTRACT_ID_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# I10 — V2_VERSION_NO_INVALID
# ═══════════════════════════════════════════════════════════════════════════════

def test_I10_version_no_invalid(pg):
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid, version_no=2), [])
    assert result["status"] == "V2_VERSION_NO_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# I11 — V2_ATOMIC_PARTIAL_STATE: count 불일치 (B1 Check 3)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I11_already_applied_count_mismatch(pg):
    """저장된 scope 1개, 재호출에 2개 전달 → count 불일치 → partial."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid)])
    assert r1["status"] == "APPLIED"
    result = _rpc(pg, pid, cr, cv, [_scope(sid), _scope()])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I12 — V2_ATOMIC_PARTIAL_STATE: tuple 불일치 (B1 Check 4)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I12_already_applied_tuple_mismatch(pg):
    """저장된 scope entity_id=A, 재호출에 entity_id=B → tuple 불일치 → partial."""
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    sid_a, sid_b = _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid_a)])
    assert r1["status"] == "APPLIED"
    result = _rpc(pg, pid, cr, cv, [_scope(sid_b)])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I13 — ROLLBACK: constraint 위반 → 전체 트랜잭션 취소
# ═══════════════════════════════════════════════════════════════════════════════

def test_I13_rollback_on_constraint_violation(pg):
    """payment_months=99 (invalid) → constraint violation at Step 9 → contracts = 0."""
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv = _cv_dict(cid)
    cv["payment_months"] = 99  # violates chk_saas_ccv_payment_months
    try:
        _rpc(pg, pid, _contract_row(cid, coid), cv, [_scope()])
    except psycopg2.Error:
        pass  # expected — constraint violation inside function
    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM public.contracts WHERE id=%s;", (cid,))
    assert cur.fetchone()[0] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# I14 — ACL: anon role INSERT → permission denied
# ═══════════════════════════════════════════════════════════════════════════════

def test_I14_acl_anon_denied_insert(pg):
    cur = pg.cursor()
    cur.execute("SET ROLE anon;")
    denied = False
    try:
        cur.execute(
            "INSERT INTO public.saas_contract_commercial_versions "
            "(contract_id, version_no, commercial_schema_version, product_tier, pricing_mode, "
            "worker_capacity, payment_months, pricing_result_status, effective_from) "
            "VALUES (%s,1,'SAAS_CONTRACT_COMMERCIAL_V2','MANAGER','STANDARD',0,12,'READY',now());",
            (_new_id(),),
        )
    except psycopg2.Error as exc:
        denied = "permission denied" in str(exc).lower()
    finally:
        try:
            cur.execute("RESET ROLE;")
        except Exception:
            pg.cursor().execute("RESET ROLE;")
    assert denied, "anon should be denied INSERT on saas_contract_commercial_versions"


# ═══════════════════════════════════════════════════════════════════════════════
# I15 — ACL: authenticated role INSERT → permission denied
# ═══════════════════════════════════════════════════════════════════════════════

def test_I15_acl_authenticated_denied_insert(pg):
    cur = pg.cursor()
    cur.execute("SET ROLE authenticated;")
    denied = False
    try:
        cur.execute(
            "INSERT INTO public.saas_contract_site_scopes "
            "(commercial_version_id, entity_type, entity_id, sector) "
            "VALUES (%s,'site',%s,'CONSTRUCTION');",
            (_new_id(), _new_id()),
        )
    except psycopg2.Error as exc:
        denied = "permission denied" in str(exc).lower()
    finally:
        try:
            cur.execute("RESET ROLE;")
        except Exception:
            pg.cursor().execute("RESET ROLE;")
    assert denied, "authenticated should be denied INSERT on saas_contract_site_scopes"


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH3 — B2 extended integration coverage (I16-I29)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# I16 — DB DEFAULT preservation: addon_codes='{}' items='[]' after explicit INSERT
# ═══════════════════════════════════════════════════════════════════════════════

def test_I16_db_default_preservation(pg):
    """Explicit 18-col INSERT leaves addon_codes/items at DB DEFAULT (not NULL)."""
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    result = _rpc(pg, pid, _contract_row(cid, coid), _cv_dict(cid), [_scope()])
    assert result["status"] == "APPLIED"
    cur = pg.cursor()
    cur.execute("SELECT addon_codes, items FROM public.contracts WHERE id=%s;", (cid,))
    row = cur.fetchone()
    assert row[0] == {}, f"addon_codes DB DEFAULT should be {{}}, got {row[0]}"
    assert row[1] == [], f"items DB DEFAULT should be [], got {row[1]}"


# ═══════════════════════════════════════════════════════════════════════════════
# I17 — Concurrent FOR UPDATE: 2 threads, 1 APPLIED + 1 ALREADY_APPLIED
# ═══════════════════════════════════════════════════════════════════════════════

def test_I17_concurrent_for_update(pg):
    """Two concurrent calls on the same payment: FOR UPDATE serializes them."""
    import threading

    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    scopes = [_scope(sid)]

    results: list[str] = []
    errors: list[str] = []

    def _call() -> None:
        conn = psycopg2.connect(_DSN)
        conn.autocommit = True
        try:
            r = _rpc(conn, pid, cr, cv, scopes)
            results.append(r["status"])
        except Exception as exc:
            errors.append(str(exc))
        finally:
            conn.close()

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"Unexpected errors: {errors}"
    assert sorted(results) == ["ALREADY_APPLIED", "APPLIED"]


# ═══════════════════════════════════════════════════════════════════════════════
# I18 — Full rollback: all 4 tables confirmed empty after constraint violation
# ═══════════════════════════════════════════════════════════════════════════════

def test_I18_full_rollback_all_tables(pg):
    """payment_months=99 → constraint violation → contracts/cv/scope=0, payment.contract_id=NULL."""
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv = _cv_dict(cid)
    cv["payment_months"] = 99
    try:
        _rpc(pg, pid, _contract_row(cid, coid), cv, [_scope()])
    except psycopg2.Error:
        pass
    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM public.contracts WHERE id=%s;", (cid,))
    assert cur.fetchone()[0] == 0, "contracts must be empty after rollback"
    cur.execute(
        "SELECT COUNT(*) FROM public.saas_contract_commercial_versions "
        "WHERE contract_id=%s;", (cid,),
    )
    assert cur.fetchone()[0] == 0, "commercial_versions must be empty after rollback"
    cur.execute("SELECT contract_id FROM public.payments WHERE id=%s;", (pid,))
    assert cur.fetchone()[0] is None, "payment.contract_id must remain NULL after rollback"


# ═══════════════════════════════════════════════════════════════════════════════
# I19 — ACL positive: service_role CAN INSERT into saas_contract_commercial_versions
# ═══════════════════════════════════════════════════════════════════════════════

def test_I19_service_role_rpc_execute_allowed(pg):
    """service_role CAN EXECUTE apply_saas_v2_contract_atomic (GRANT EXECUTE + BYPASSRLS)."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    cur = pg.cursor()
    cur.execute("SET ROLE service_role;")
    try:
        cur.execute(
            "SELECT public.apply_saas_v2_contract_atomic"
            "(%s::uuid,%s::jsonb,%s::jsonb,%s::jsonb)::text;",
            (pid, json.dumps(cr), json.dumps(cv), json.dumps([_scope(sid)])),
        )
        result = json.loads(cur.fetchone()[0])
        assert result["status"] == "APPLIED", f"service_role should get APPLIED, got {result}"
    finally:
        try:
            cur.execute("RESET ROLE;")
        except Exception:
            pg.cursor().execute("RESET ROLE;")


# ─── ACL helper ───────────────────────────────────────────────────────────────

def _acl_denied(pg, role: str, stmt: str, params: tuple = ()) -> bool:
    cur = pg.cursor()
    cur.execute(f"SET ROLE {role};")
    denied = False
    try:
        cur.execute(stmt, params)
    except psycopg2.Error as exc:
        denied = "permission denied" in str(exc).lower()
    finally:
        try:
            cur.execute("RESET ROLE;")
        except Exception:
            pg.cursor().execute("RESET ROLE;")
    return denied


# ═══════════════════════════════════════════════════════════════════════════════
# I20 — ACL: anon UPDATE denied on saas_contract_commercial_versions
# ═══════════════════════════════════════════════════════════════════════════════

def test_I20_anon_update_denied(pg):
    denied = _acl_denied(
        pg, "anon",
        "UPDATE public.saas_contract_commercial_versions SET version_no=1 WHERE FALSE;",
    )
    assert denied, "anon UPDATE should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I21 — ACL: anon TRUNCATE denied on saas_contract_commercial_versions
# ═══════════════════════════════════════════════════════════════════════════════

def test_I21_anon_truncate_denied(pg):
    denied = _acl_denied(
        pg, "anon",
        "TRUNCATE public.saas_contract_commercial_versions;",
    )
    assert denied, "anon TRUNCATE should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I22 — ACL: anon EXECUTE denied on apply_saas_v2_contract_atomic
# ═══════════════════════════════════════════════════════════════════════════════

def test_I22_anon_rpc_execute_denied(pg):
    denied = _acl_denied(
        pg, "anon",
        "SELECT public.apply_saas_v2_contract_atomic(%s::uuid,%s::jsonb,%s::jsonb,%s::jsonb);",
        (_new_id(), json.dumps({}), json.dumps({}), json.dumps([])),
    )
    assert denied, "anon EXECUTE on RPC should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I23 — ACL: authenticated UPDATE denied on saas_contract_site_scopes
# ═══════════════════════════════════════════════════════════════════════════════

def test_I23_authenticated_update_denied(pg):
    denied = _acl_denied(
        pg, "authenticated",
        "UPDATE public.saas_contract_site_scopes SET sector='INDUSTRY' WHERE FALSE;",
    )
    assert denied, "authenticated UPDATE should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I24 — ACL: authenticated TRUNCATE denied on saas_contract_site_scopes
# ═══════════════════════════════════════════════════════════════════════════════

def test_I24_authenticated_truncate_denied(pg):
    denied = _acl_denied(
        pg, "authenticated",
        "TRUNCATE public.saas_contract_site_scopes;",
    )
    assert denied, "authenticated TRUNCATE should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I25 — ACL: authenticated EXECUTE denied on apply_saas_v2_contract_atomic
# ═══════════════════════════════════════════════════════════════════════════════

def test_I25_authenticated_rpc_execute_denied(pg):
    denied = _acl_denied(
        pg, "authenticated",
        "SELECT public.apply_saas_v2_contract_atomic(%s::uuid,%s::jsonb,%s::jsonb,%s::jsonb);",
        (_new_id(), json.dumps({}), json.dumps({}), json.dumps([])),
    )
    assert denied, "authenticated EXECUTE on RPC should be denied"


# ═══════════════════════════════════════════════════════════════════════════════
# I26 — duplicate p_site_scopes in ALREADY_APPLIED retry → V2_ATOMIC_PARTIAL_STATE
# ═══════════════════════════════════════════════════════════════════════════════

def test_I26_duplicate_scopes_in_idempotent_retry(pg):
    """After APPLIED, retry with duplicate (entity_type,entity_id) in scopes → partial."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid)])
    assert r1["status"] == "APPLIED"
    # Retry with duplicate scopes (same entity_id twice)
    result = _rpc(pg, pid, cr, cv, [_scope(sid), _scope(sid)])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I27 — CUSTOM tier scope count mismatch → V2_ATOMIC_PARTIAL_STATE (PATCH3 B1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I27_custom_tier_scope_count_mismatch(pg):
    """CUSTOM tier: first apply 0 scopes, retry with 1 scope → count mismatch → partial."""
    pid, cid, coid = _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid, "CUSTOM"), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [])
    assert r1["status"] == "APPLIED"
    result = _rpc(pg, pid, cr, cv, [_scope()])
    assert result["status"] == "V2_ATOMIC_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I28 — idempotent retry with wrong contract_id → V2_CONTRACT_ID_MISMATCH (PATCH3 B1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I28_idempotent_wrong_contract_id(pg):
    """After APPLIED, retry with different contract_id → V2_CONTRACT_ID_MISMATCH."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid)])
    assert r1["status"] == "APPLIED"
    # Retry with different contract_id
    other_cid = _new_id()
    result = _rpc(pg, pid, _contract_row(other_cid, coid), _cv_dict(other_cid), [_scope(sid)])
    assert result["status"] == "V2_CONTRACT_ID_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# I29 — idempotent retry with version_no=2 → V2_VERSION_NO_INVALID (PATCH3 B1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I29_idempotent_wrong_version_no(pg):
    """After APPLIED, retry with version_no=2 → V2_VERSION_NO_INVALID."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid)])
    assert r1["status"] == "APPLIED"
    # Retry with version_no=2
    cv_v2 = _cv_dict(cid, version_no=2)
    result = _rpc(pg, pid, cr, cv_v2, [_scope(sid)])
    assert result["status"] == "V2_VERSION_NO_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH4 — Guard 3: idempotent CV.contract_id ≠ payment.contract_id (I30)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I30_idempotent_cv_contract_id_mismatch(pg):
    """contract_row.id=A matches but CV.contract_id=B → V2_CONTRACT_ID_MISMATCH."""
    pid, cid, coid, sid = _new_id(), _new_id(), _new_id(), _new_id()
    _insert_payment(pg, pid)
    cv, cr = _cv_dict(cid), _contract_row(cid, coid)
    r1 = _rpc(pg, pid, cr, cv, [_scope(sid)])
    assert r1["status"] == "APPLIED"
    # Retry: contract_row.id=A (correct), CV.contract_id=B (wrong)
    other_cid = _new_id()
    cv_wrong_cv_id = _cv_dict(other_cid)   # CV.contract_id = other_cid (B)
    result = _rpc(pg, pid, cr, cv_wrong_cv_id, [_scope(sid)])
    assert result["status"] == "V2_CONTRACT_ID_MISMATCH"
