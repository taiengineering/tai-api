"""TAI Safe Pricing V2 — Renewal Atomic Apply PostgreSQL Integration Tests (I01-I25).

실제 isolated PostgreSQL에서 apply_saas_v2_renewal_atomic 함수를 실행하는 통합 테스트.

실행 조건:
  - psycopg2 설치 (pip install psycopg2-binary)
  - PostgreSQL@16 실행 중 (localhost:5432)
  - DB: psql -c "CREATE DATABASE tai_test_v2_renewal_atomic" (최초 1회)
  - 환경변수: TEST_PG_RENEWAL_DSN 또는 기본값 localhost

커버리지:
  I01: APPLIED — MANAGER tier, 1 site_scope
  I02: old CV.superseded_at = boundary after apply
  I03: new CV.effective_from = boundary after apply
  I04: new CV.version_no = old.version_no + 1
  I05: scopes exact (entity_type/entity_id/sector/base_band_code)
  I06: contract.end_date = original_end + term_months
  I07: contract 허용 필드 업데이트 (paid_amount, paid_at, updated_at)
  I08: contract 금지 필드 불변 (start_date, contract_no, contract_amount 등)
  I09: 동일 인수 재호출 → ALREADY_APPLIED
  I10: 재호출 시 end_date 두 번 연장 없음
  I11: old superseded_at set, new CV 없음 → V2_RENEWAL_PARTIAL_STATE
  I12: new CV exists, old.superseded_at mismatch → V2_RENEWAL_PARTIAL_STATE
  I13: scope 부족 → V2_RENEWAL_PARTIAL_STATE
  I14: scope 초과 → V2_RENEWAL_PARTIAL_STATE
  I15: new CV payload 불일치 → V2_RENEWAL_PARTIAL_STATE
  I16: contract.end_date 불일치 → V2_RENEWAL_PARTIAL_STATE
  I17: boundary mismatch → V2_RENEWAL_BOUNDARY_MISMATCH
  I18: version_no mismatch → V2_RENEWAL_VERSION_MISMATCH
  I19: constraint 실패 → 전체 롤백 (old CV superseded_at = NULL, new CV = 0)
  I20: 동시 2호출 동일 payment → APPLIED + ALREADY_APPLIED, end_date 1회만 연장
  I21: service_role RPC 허용
  I22: anon/authenticated RPC 차단 + superseded_at UPDATE 차단
  I23: Jan 31 + 1 month boundary
  I24: leap-year Feb 28/29 month arithmetic
  I25: 서로 다른 payment 동시 renewal 동일 contract → 두 번째 fail-closed

Production DB 사용 절대 금지.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid

import psycopg2
import pytest

# ── Connection ────────────────────────────────────────────────────────────────

_DSN = os.getenv(
    "TEST_PG_RENEWAL_DSN",
    "host=localhost dbname=tai_test_v2_renewal_atomic",
)

_OBJ10C_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-09-28_saas_contract_commercial_v2_atomic_apply.sql"
).read_text()

_B2_MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql"
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

    cur.execute("ALTER ROLE service_role BYPASSRLS;")

    # Full contracts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.contracts (
            id               uuid        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            contract_no      text,
            company_id       uuid        NOT NULL,
            status_code      text        NOT NULL DEFAULT 'ACTIVE',
            start_date       date,
            end_date         date,
            service_type     text        NOT NULL DEFAULT 'SAAS',
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

    # Full payments table (includes all B2-required columns)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.payments (
            id              uuid        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            status_code     text        NOT NULL,
            contract_id     uuid        REFERENCES public.contracts(id),
            product_type    text,
            payment_type    text,
            plan_code       text,
            quote_id        uuid,
            period_months   integer,
            supply_amount   numeric,
            vat_amount      numeric,
            total_amount    numeric,
            company_id      uuid,
            user_id         uuid,
            paid_at         timestamptz
        );
    """)

    cur.execute("GRANT SELECT, UPDATE ON public.payments TO service_role;")
    cur.execute("GRANT SELECT, INSERT, UPDATE ON public.contracts TO service_role;")

    # Remove OBJ10-C tables/function if exists, then re-apply
    cur.execute("DROP TABLE IF EXISTS public.saas_contract_site_scopes CASCADE;")
    cur.execute("DROP TABLE IF EXISTS public.saas_contract_commercial_versions CASCADE;")
    cur.execute(
        "DROP FUNCTION IF EXISTS "
        "public.apply_saas_v2_contract_atomic(uuid, jsonb, jsonb, jsonb);"
    )
    cur.execute(
        "DROP FUNCTION IF EXISTS "
        "public.apply_saas_v2_renewal_atomic(uuid, uuid, uuid, integer, jsonb, jsonb);"
    )

    cur.execute(_OBJ10C_MIGRATION_SQL)
    cur.execute(_B2_MIGRATION_SQL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _snap(supply: int = 200_000, vat: int = 20_000, total: int = 220_000,
          term: int = 12, worker_capacity: int = 5) -> dict:
    site_id = _new_id()
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "2026.09",
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "sites": [{
            "entity_type": "factory",
            "entity_id": site_id,
            "sector": "INDUSTRY",
            "base_band_code": "B1",
            "base_amount": supply,
            "is_primary": True,
            "applied_rate_bps": 0,
            "final_site_amount": supply,
        }],
        "worker": {"capacity": worker_capacity, "amount": 0, "brackets": []},
        "term_months": term,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1_000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _insert_payment(
    pg, pid: str, cid: str, qid: str, company_id: str,
    status: str = "PAID",
    supply: int = 200_000, vat: int = 20_000, total: int = 220_000,
    term: int = 12,
    paid_at: str = "2026-12-31T15:00:00+00:00",
) -> None:
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO public.payments
           (id, status_code, product_type, payment_type, plan_code,
            contract_id, quote_id, period_months,
            supply_amount, vat_amount, total_amount,
            company_id, paid_at)
           VALUES (%s,%s,'SAAS','RENEWAL',NULL,
                   %s,%s,%s,
                   %s,%s,%s,
                   %s,%s);""",
        (pid, status, cid, qid, term, supply, vat, total, company_id, paid_at),
    )


def _insert_contract(
    pg, cid: str, company_id: str,
    end_date: str = "2027-01-01",
    service_type: str = "SAAS",
    status_code: str = "ACTIVE",
    contract_no: str = "TEST-RN-001",
    contract_amount: int = 200_000,
    vat_amount: int = 20_000,
    total_amount: int = 220_000,
) -> None:
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO public.contracts
           (id, company_id, status_code, service_type,
            start_date, end_date, is_active,
            contract_no, contract_amount, vat_amount, total_amount)
           VALUES (%s,%s,%s,%s,
                   '2026-01-01',%s,TRUE,
                   %s,%s,%s,%s);""",
        (cid, company_id, status_code, service_type,
         end_date, contract_no, contract_amount, vat_amount, total_amount),
    )


def _insert_old_cv(
    pg, cid: str, version_no: int = 1,
    effective_from: str = "2026-01-01T00:00:00+00:00",
    superseded_at: str | None = None,
    term_months: int = 12,
    snap: dict | None = None,
    product_tier: str = "FIELD",
    pricing_mode: str = "STANDARD",
    worker_capacity: int = 5,
) -> str:
    """Returns inserted CV id."""
    cv_id = _new_id()
    if snap is None:
        snap = _snap()
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO public.saas_contract_commercial_versions
           (id, contract_id, version_no, commercial_schema_version,
            product_tier, pricing_mode, worker_capacity, term_months,
            pricing_result_status, pricing_policy_version, pricing_snapshot,
            effective_from, superseded_at)
           VALUES (%s,%s,%s,'SAAS_CONTRACT_COMMERCIAL_V2',
                   %s,%s,%s,%s,
                   'READY','2026.09',%s,
                   %s,%s);""",
        (cv_id, cid, version_no, product_tier, pricing_mode,
         worker_capacity, term_months,
         json.dumps(snap),
         effective_from, superseded_at),
    )
    return cv_id


def _new_cv_payload(
    cid: str, version_no: int,
    effective_from_kst: str,
    term_months: int = 12,
    product_tier: str = "FIELD",
    pricing_mode: str = "STANDARD",
    worker_capacity: int = 5,
    supply: int = 200_000, vat: int = 20_000, total: int = 220_000,
    created_by: str | None = None,
) -> dict:
    snap = _snap(supply, vat, total, term_months, worker_capacity)
    snap["product_tier"] = product_tier
    snap["pricing_mode"] = pricing_mode
    return {
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "contract_id": cid,
        "version_no": version_no,
        "product_tier": product_tier,
        "pricing_mode": pricing_mode,
        "worker_capacity": worker_capacity,
        "term_months": term_months,
        "pricing_result_status": "READY",
        "pricing_policy_version": "2026.09",
        "pricing_snapshot": snap,
        "effective_from": effective_from_kst,
        "superseded_at": None,
        "created_by": created_by,
    }


def _scope(entity_id: str | None = None, sector: str = "INDUSTRY",
           entity_type: str = "factory", base_band_code: str | None = "B1") -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id or _new_id(),
        "sector": sector,
        "base_band_code": base_band_code,
    }


def _rpc(
    pg,
    pid: str, cid: str, qid: str, current_ver_no: int,
    new_cv: dict, scopes: list[dict],
) -> dict:
    cur = pg.cursor()
    cur.execute(
        "SELECT public.apply_saas_v2_renewal_atomic"
        "(%s::uuid,%s::uuid,%s::uuid,%s::integer,%s::jsonb,%s::jsonb)::text;",
        (pid, cid, qid, current_ver_no, json.dumps(new_cv), json.dumps(scopes)),
    )
    (raw,) = cur.fetchone()
    return json.loads(raw)


def _kst_boundary(end_date_str: str) -> str:
    """'YYYY-MM-DD' → 'YYYY-MM-DDT00:00:00+09:00'."""
    return f"{end_date_str}T00:00:00+09:00"


# ═══════════════════════════════════════════════════════════════════════════════
# I01: APPLIED — FIELD tier, 1 site_scope
# ═══════════════════════════════════════════════════════════════════════════════

def test_I01_applied_field_tier(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    sid = _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    scopes = [_scope(sid)]
    new_cv = _new_cv_payload(cid, 2, boundary)

    result = _rpc(pg, pid, cid, qid, 1, new_cv, scopes)
    assert result["status"] == "APPLIED"
    assert result["contract_id"] == cid


# ═══════════════════════════════════════════════════════════════════════════════
# I02: old CV.superseded_at = boundary
# ═══════════════════════════════════════════════════════════════════════════════

def test_I02_old_cv_superseded_at_equals_boundary(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    old_cv_id = _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute(
        "SELECT superseded_at AT TIME ZONE 'Asia/Seoul' "
        "FROM public.saas_contract_commercial_versions WHERE id=%s;",
        (old_cv_id,),
    )
    sup = cur.fetchone()[0]
    assert sup is not None
    assert sup.year == 2027 and sup.month == 1 and sup.day == 1
    assert sup.hour == 0 and sup.minute == 0


# ═══════════════════════════════════════════════════════════════════════════════
# I03: new CV.effective_from = boundary
# ═══════════════════════════════════════════════════════════════════════════════

def test_I03_new_cv_effective_from_equals_boundary(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute(
        "SELECT effective_from AT TIME ZONE 'Asia/Seoul' "
        "FROM public.saas_contract_commercial_versions WHERE version_no=2 AND contract_id=%s;",
        (cid,),
    )
    eff = cur.fetchone()[0]
    assert eff.year == 2027 and eff.month == 1 and eff.day == 1
    assert eff.hour == 0 and eff.minute == 0


# ═══════════════════════════════════════════════════════════════════════════════
# I04: new CV.version_no = old.version_no + 1
# ═══════════════════════════════════════════════════════════════════════════════

def test_I04_new_cv_version_no(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=3)  # non-1 version
    new_cv = _new_cv_payload(cid, 4, boundary)

    result = _rpc(pg, pid, cid, qid, 3, new_cv, [_scope()])
    assert result["status"] == "APPLIED"

    cur = pg.cursor()
    cur.execute(
        "SELECT version_no FROM public.saas_contract_commercial_versions "
        "WHERE contract_id=%s AND superseded_at IS NULL;",
        (cid,),
    )
    assert cur.fetchone()[0] == 4


# ═══════════════════════════════════════════════════════════════════════════════
# I05: scopes exact
# ═══════════════════════════════════════════════════════════════════════════════

def test_I05_scopes_exact(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    s1, s2 = _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)
    snap = _snap(worker_capacity=3)
    snap["sites"] = [
        {"entity_type": "factory", "entity_id": s1, "sector": "INDUSTRY",
         "base_band_code": "B2", "base_amount": 100_000, "is_primary": True,
         "applied_rate_bps": 0, "final_site_amount": 100_000},
        {"entity_type": "factory", "entity_id": s2, "sector": "BUILDING",
         "base_band_code": None, "base_amount": 100_000, "is_primary": False,
         "applied_rate_bps": 0, "final_site_amount": 100_000},
    ]

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    scopes = [
        _scope(s1, "INDUSTRY", "factory", "B2"),
        _scope(s2, "BUILDING", "factory", None),
    ]
    new_cv = _new_cv_payload(cid, 2, boundary)
    new_cv["pricing_snapshot"] = snap

    _rpc(pg, pid, cid, qid, 1, new_cv, scopes)

    cur = pg.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM public.saas_contract_site_scopes s "
        "JOIN public.saas_contract_commercial_versions v ON s.commercial_version_id=v.id "
        "WHERE v.contract_id=%s AND v.version_no=2;",
        (cid,),
    )
    assert cur.fetchone()[0] == 2

    cur.execute(
        "SELECT base_band_code FROM public.saas_contract_site_scopes s "
        "JOIN public.saas_contract_commercial_versions v ON s.commercial_version_id=v.id "
        "WHERE v.contract_id=%s AND s.entity_id=%s::uuid;",
        (cid, s2),
    )
    assert cur.fetchone()[0] is None  # NULL-safe


# ═══════════════════════════════════════════════════════════════════════════════
# I06: contract.end_date = original_end + term_months
# ═══════════════════════════════════════════════════════════════════════════════

def test_I06_contract_end_date_extended(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, term=12)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=12)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute("SELECT end_date FROM public.contracts WHERE id=%s;", (cid,))
    new_end = cur.fetchone()[0]
    # 2027-01-01 + 12 months = 2028-01-01
    assert new_end.year == 2028 and new_end.month == 1 and new_end.day == 1


# ═══════════════════════════════════════════════════════════════════════════════
# I07: contract compatibility fields updated
# ═══════════════════════════════════════════════════════════════════════════════

def test_I07_contract_compatibility_fields_updated(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date, total_amount=220_000)
    _insert_payment(pg, pid, cid, qid, co,
                    supply=200_000, vat=20_000, total=220_000,
                    paid_at="2026-12-31T15:00:00+00:00")
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute(
        "SELECT paid_amount, status_code, is_active FROM public.contracts WHERE id=%s;",
        (cid,),
    )
    row = cur.fetchone()
    assert row[0] == 220_000   # paid_amount = payment.total_amount
    assert row[1] == "ACTIVE"
    assert row[2] is True


# ═══════════════════════════════════════════════════════════════════════════════
# I08: contract forbidden fields unchanged
# ═══════════════════════════════════════════════════════════════════════════════

def test_I08_contract_forbidden_fields_unchanged(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date,
                     contract_no="FIXED-NO", contract_amount=999_000)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute(
        "SELECT contract_no, contract_amount, start_date FROM public.contracts WHERE id=%s;",
        (cid,),
    )
    row = cur.fetchone()
    assert row[0] == "FIXED-NO"   # contract_no 불변
    assert row[1] == 999_000       # contract_amount 불변
    assert str(row[2]) == "2026-01-01"  # start_date 불변


# ═══════════════════════════════════════════════════════════════════════════════
# I09: 동일 인수 재호출 → ALREADY_APPLIED
# ═══════════════════════════════════════════════════════════════════════════════

def test_I09_already_applied_on_retry(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)
    scopes = [_scope()]

    r1 = _rpc(pg, pid, cid, qid, 1, new_cv, scopes)
    assert r1["status"] == "APPLIED"

    r2 = _rpc(pg, pid, cid, qid, 1, new_cv, scopes)
    assert r2["status"] == "ALREADY_APPLIED"


# ═══════════════════════════════════════════════════════════════════════════════
# I10: 재호출 시 end_date 두 번 연장 없음
# ═══════════════════════════════════════════════════════════════════════════════

def test_I10_retry_does_not_extend_end_date_twice(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, term=12)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=12)
    scopes = [_scope()]

    _rpc(pg, pid, cid, qid, 1, new_cv, scopes)  # 1st: APPLIED
    _rpc(pg, pid, cid, qid, 1, new_cv, scopes)  # 2nd: ALREADY_APPLIED

    cur = pg.cursor()
    cur.execute("SELECT end_date FROM public.contracts WHERE id=%s;", (cid,))
    end = cur.fetchone()[0]
    # Should be 2028-01-01, NOT 2029-01-01 (no double extension)
    assert end.year == 2028 and end.month == 1 and end.day == 1


# ═══════════════════════════════════════════════════════════════════════════════
# I11: old superseded_at set, new CV 없음 → PARTIAL (P1)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I11_old_only_partial_state(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    # Insert old CV with superseded_at already set (simulates partial state)
    _insert_old_cv(pg, cid, version_no=1, superseded_at=boundary)
    new_cv = _new_cv_payload(cid, 2, boundary)

    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I12: new CV exists, old.superseded_at mismatch → PARTIAL (P2)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I12_old_superseded_at_mismatch_partial(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)
    other_boundary = "2027-02-01T00:00:00+09:00"

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    # Old CV has different superseded_at
    _insert_old_cv(pg, cid, version_no=1, superseded_at=other_boundary)
    # New CV already exists with correct boundary
    _insert_old_cv(pg, cid, version_no=2,
                   effective_from=boundary, superseded_at=None)
    new_cv = _new_cv_payload(cid, 2, boundary)

    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I13: scope 부족 → PARTIAL (P3)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I13_missing_scope_partial(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    s1, s2 = _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1, superseded_at=boundary)
    new_cv_id = _insert_old_cv(pg, cid, version_no=2,
                                effective_from=boundary, superseded_at=None)

    # Only insert 1 of 2 expected scopes
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO public.saas_contract_site_scopes "
        "(commercial_version_id, entity_type, entity_id, sector) "
        "VALUES (%s,'factory',%s::uuid,'INDUSTRY');",
        (new_cv_id, s1),
    )

    # incoming expects 2 scopes
    new_cv = _new_cv_payload(cid, 2, boundary)
    result = _rpc(pg, pid, cid, qid, 1, new_cv,
                  [_scope(s1), _scope(s2)])
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I14: scope 초과 → PARTIAL (P4)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I14_extra_scope_partial(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    s1, s2 = _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1, superseded_at=boundary)
    new_cv_id = _insert_old_cv(pg, cid, version_no=2,
                                effective_from=boundary, superseded_at=None)

    # Insert 2 stored scopes but incoming expects only 1
    cur = pg.cursor()
    for sid in (s1, s2):
        cur.execute(
            "INSERT INTO public.saas_contract_site_scopes "
            "(commercial_version_id, entity_type, entity_id, sector) "
            "VALUES (%s,'factory',%s::uuid,'INDUSTRY');",
            (new_cv_id, sid),
        )

    new_cv = _new_cv_payload(cid, 2, boundary)
    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope(s1)])  # only 1
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I15: new CV payload 불일치 → PARTIAL (P7)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I15_new_cv_payload_mismatch_partial(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, supply=200_000, vat=20_000, total=220_000)
    _insert_old_cv(pg, cid, version_no=1, superseded_at=boundary)
    # Stored new CV with term_months=12
    _insert_old_cv(pg, cid, version_no=2,
                   effective_from=boundary, superseded_at=None, term_months=12)

    # Incoming new CV with different term_months → mismatch
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=6)
    new_cv["pricing_snapshot"]["prepaid_supply_amount"] = 200_000
    new_cv["pricing_snapshot"]["vat_amount"] = 20_000
    new_cv["pricing_snapshot"]["total_amount"] = 220_000
    new_cv["pricing_snapshot"]["term_months"] = 6

    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I16: contract.end_date 불일치 → PARTIAL (P6)
# ═══════════════════════════════════════════════════════════════════════════════

def test_I16_contract_end_date_mismatch_partial(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    # Set contract end_date to a WRONG value (not original_end + term_months)
    _insert_contract(pg, cid, co, end_date="2027-06-01")  # wrong end_date
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1, superseded_at=boundary)
    _insert_old_cv(pg, cid, version_no=2, effective_from=boundary, superseded_at=None)

    # Insert 1 matching scope
    cur = pg.cursor()
    cur.execute(
        "SELECT id FROM public.saas_contract_commercial_versions "
        "WHERE contract_id=%s AND version_no=2;", (cid,),
    )
    new_cv_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO public.saas_contract_site_scopes "
        "(commercial_version_id, entity_type, entity_id, sector, base_band_code) "
        "VALUES (%s,'factory',%s::uuid,'INDUSTRY','B1');",
        (new_cv_id, _new_id()),
    )

    new_cv = _new_cv_payload(cid, 2, boundary, term_months=12)
    scopes_in_db_s = _new_id()
    # We need the scope to match — use the scope already in DB
    cur.execute(
        "SELECT entity_id, sector, base_band_code "
        "FROM public.saas_contract_site_scopes WHERE commercial_version_id=%s;",
        (new_cv_id,),
    )
    row = cur.fetchone()
    scopes = [{"entity_type": "factory", "entity_id": str(row[0]),
               "sector": row[1], "base_band_code": row[2]}]

    result = _rpc(pg, pid, cid, qid, 1, new_cv, scopes)
    assert result["status"] == "V2_RENEWAL_PARTIAL_STATE"


# ═══════════════════════════════════════════════════════════════════════════════
# I17: boundary mismatch → V2_RENEWAL_BOUNDARY_MISMATCH
# ═══════════════════════════════════════════════════════════════════════════════

def test_I17_boundary_mismatch(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    # Wrong boundary (Feb 1, not Jan 1)
    wrong_boundary = "2027-02-01T00:00:00+09:00"
    new_cv = _new_cv_payload(cid, 2, wrong_boundary)

    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])
    assert result["status"] == "V2_RENEWAL_BOUNDARY_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# I18: version_no mismatch → V2_RENEWAL_VERSION_MISMATCH
# ═══════════════════════════════════════════════════════════════════════════════

def test_I18_version_mismatch(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    # new CV claims version_no=5 instead of 2
    new_cv = _new_cv_payload(cid, 5, boundary)

    result = _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])
    assert result["status"] == "V2_RENEWAL_VERSION_MISMATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# I19: constraint 실패 → 전체 롤백 검증
# ═══════════════════════════════════════════════════════════════════════════════

def test_I19_rollback_on_constraint_failure(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    old_cv_id = _insert_old_cv(pg, cid, version_no=1)

    # new CV with invalid tier+mode (MANAGER+CUSTOM violates chk_saas_ccv_tier_mode_combo)
    invalid_cv = _new_cv_payload(cid, 2, boundary)
    invalid_cv["product_tier"] = "MANAGER"
    invalid_cv["pricing_mode"] = "CUSTOM"

    try:
        _rpc(pg, pid, cid, qid, 1, invalid_cv, [_scope()])
    except Exception:
        pass  # expected DB error

    # Rollback assertions: old CV superseded_at must be NULL, new CV must not exist
    cur = pg.cursor()
    cur.execute(
        "SELECT superseded_at FROM public.saas_contract_commercial_versions WHERE id=%s;",
        (old_cv_id,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] is None, "old CV.superseded_at must be NULL after rollback"

    cur.execute(
        "SELECT COUNT(*) FROM public.saas_contract_commercial_versions "
        "WHERE contract_id=%s AND version_no=2;",
        (cid,),
    )
    assert cur.fetchone()[0] == 0, "new CV must not exist after rollback"

    cur.execute(
        "SELECT end_date FROM public.contracts WHERE id=%s;",
        (cid,),
    )
    assert str(cur.fetchone()[0]) == "2027-01-01", "contract end_date must be unchanged"


# ═══════════════════════════════════════════════════════════════════════════════
# I20: 동시 2호출 동일 payment → APPLIED + ALREADY_APPLIED, end_date 1회만 연장
# ═══════════════════════════════════════════════════════════════════════════════

def test_I20_concurrent_same_payment(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, term=12)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=12)
    scopes = [_scope()]

    results = []

    def call():
        conn2 = psycopg2.connect(_DSN)
        conn2.autocommit = True
        cur2 = conn2.cursor()
        try:
            cur2.execute(
                "SELECT public.apply_saas_v2_renewal_atomic"
                "(%s::uuid,%s::uuid,%s::uuid,%s::integer,%s::jsonb,%s::jsonb)::text;",
                (pid, cid, qid, 1, json.dumps(new_cv), json.dumps(scopes)),
            )
            (raw,) = cur2.fetchone()
            results.append(json.loads(raw)["status"])
        except Exception as e:
            results.append(f"ERROR:{e}")
        finally:
            conn2.close()

    t1 = threading.Thread(target=call)
    t2 = threading.Thread(target=call)
    t1.start(); t2.start()
    t1.join(); t2.join()

    statuses = sorted(results)
    assert statuses == ["ALREADY_APPLIED", "APPLIED"], f"Expected APPLIED+ALREADY_APPLIED, got {results}"

    # end_date extended exactly once (2028-01-01, not 2029-01-01)
    cur = pg.cursor()
    cur.execute("SELECT end_date FROM public.contracts WHERE id=%s;", (cid,))
    end = cur.fetchone()[0]
    assert end.year == 2028 and end.month == 1 and end.day == 1


# ═══════════════════════════════════════════════════════════════════════════════
# I21: service_role RPC 허용
# ═══════════════════════════════════════════════════════════════════════════════

def test_I21_service_role_rpc_allowed(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    cur = pg.cursor()
    cur.execute("SET ROLE service_role;")
    try:
        cur.execute(
            "SELECT public.apply_saas_v2_renewal_atomic"
            "(%s::uuid,%s::uuid,%s::uuid,%s::integer,%s::jsonb,%s::jsonb)::text;",
            (pid, cid, qid, 1, json.dumps(new_cv), json.dumps([_scope()])),
        )
        (raw,) = cur.fetchone()
        result = json.loads(raw)
        assert result["status"] == "APPLIED"
    finally:
        cur.execute("RESET ROLE;")


# ═══════════════════════════════════════════════════════════════════════════════
# I22: anon/authenticated RPC 차단 + superseded_at UPDATE 차단
# ═══════════════════════════════════════════════════════════════════════════════

def test_I22_anon_rpc_and_update_denied(pg):
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co)
    old_cv_id = _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary)

    for role in ("anon", "authenticated"):
        cur = pg.cursor()
        cur.execute(f"SET ROLE {role};")
        try:
            # RPC call must be denied
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "SELECT public.apply_saas_v2_renewal_atomic"
                    "(%s::uuid,%s::uuid,%s::uuid,%s::integer,%s::jsonb,%s::jsonb)::text;",
                    (pid, cid, qid, 1, json.dumps(new_cv), json.dumps([_scope()])),
                )
        finally:
            cur.execute("RESET ROLE;")
            pg.rollback()

    # Direct UPDATE superseded_at denied for anon
    cur = pg.cursor()
    cur.execute("SET ROLE anon;")
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(
                "UPDATE public.saas_contract_commercial_versions "
                "SET superseded_at = now() WHERE id=%s;",
                (old_cv_id,),
            )
    finally:
        cur.execute("RESET ROLE;")
        pg.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# I23: Jan 31 + 1 month boundary → Feb 28/29
# ═══════════════════════════════════════════════════════════════════════════════

def test_I23_jan31_plus_1month_boundary(pg):
    """Jan 31 + 1 month = Feb 28 (2027, non-leap)."""
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-31"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, term=1)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=1)
    snap = new_cv["pricing_snapshot"]
    snap["term_months"] = 1

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute("SELECT end_date FROM public.contracts WHERE id=%s;", (cid,))
    end = cur.fetchone()[0]
    # 2027-01-31 + 1 month = 2027-02-28 (PostgreSQL month arithmetic)
    assert end.year == 2027 and end.month == 2 and end.day == 28


# ═══════════════════════════════════════════════════════════════════════════════
# I24: leap-year Feb 28 + 1 month → Mar 28
# ═══════════════════════════════════════════════════════════════════════════════

def test_I24_leap_year_month_arithmetic(pg):
    """2028-02-29 + 12 months = 2029-02-28 (non-leap)."""
    pid, cid, qid, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2028-02-29"  # leap year
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid, cid, qid, co, term=12)
    _insert_old_cv(pg, cid, version_no=1)
    new_cv = _new_cv_payload(cid, 2, boundary, term_months=12)

    _rpc(pg, pid, cid, qid, 1, new_cv, [_scope()])

    cur = pg.cursor()
    cur.execute("SELECT end_date FROM public.contracts WHERE id=%s;", (cid,))
    end = cur.fetchone()[0]
    # 2028-02-29 + 12 months = 2029-02-28 (non-leap year, no Feb 29)
    assert end.year == 2029 and end.month == 2 and end.day == 28


# ═══════════════════════════════════════════════════════════════════════════════
# I25: 서로 다른 payment, 동일 contract → 두 번째 fail-closed
# ═══════════════════════════════════════════════════════════════════════════════

def test_I25_different_payments_same_contract_fail_closed(pg):
    """두 다른 payment가 동일 contract를 갱신하려 할 때 두 번째는 fail-closed."""
    pid1, pid2 = _new_id(), _new_id()
    cid, qid1, qid2, co = _new_id(), _new_id(), _new_id(), _new_id()
    end_date = "2027-01-01"
    boundary = _kst_boundary(end_date)

    _insert_contract(pg, cid, co, end_date=end_date)
    _insert_payment(pg, pid1, cid, qid1, co, term=12)
    _insert_payment(pg, pid2, cid, qid2, co, term=12)
    _insert_old_cv(pg, cid, version_no=1)

    new_cv1 = _new_cv_payload(cid, 2, boundary, term_months=12)
    new_cv2 = _new_cv_payload(cid, 2, boundary, term_months=12)

    r1 = _rpc(pg, pid1, cid, qid1, 1, new_cv1, [_scope()])
    assert r1["status"] == "APPLIED"

    # Second payment tries same contract/version → fails (version 2 already exists,
    # and old CV is no longer in PRE-APPLY state)
    r2 = _rpc(pg, pid2, cid, qid2, 1, new_cv2, [_scope()])
    # Either PARTIAL (old superseded mismatch) or the function returns an error
    assert r2["status"] != "APPLIED", (
        f"Second payment should not re-apply renewal: {r2}"
    )
