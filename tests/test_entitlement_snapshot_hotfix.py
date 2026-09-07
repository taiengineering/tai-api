"""WP-A ENTITLEMENT HOTFIX — _entitlement_snapshot subscriptions 컬럼 정정.

WO-SAFE-COMPANY-ACCESS-001. 근본원인 : subscriptions 테이블에는 start_date 컬럼이
없고 started_at 만 있다. 이전 select 는 없는 컬럼을 요청해 PostgREST 오류 → except
로 흡수되어 contract 조회에 도달하지 못했고, 결과적으로 유효 SaaS 계약이 있어도
무조건 active=false 였다.

이 테스트 파일은 :
  1) 소스 계약 (subscription select 에 start_date 부재 · started_at 존재)
  2) 소스 계약 (contract 블록 start_date 유지 · contracts 실 컬럼)
  3) 행위 계약 (유효 SaaS contract 만 있는 회사 → active=true · source=contract)
  4) 행위 계약 (유효 SaaS subscription → active=true · source=subscription · start_date=started_at)
을 검증한다. 운영 DB/네트워크 불사용.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.company_users as cu


# ── FakeSupabase (경량 · ilike prefix% 지원) ────────────────────────
class _Result:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, store, table):
        self.store = store; self.table = table
        self._op = "select"; self._filters = []; self._cols = "*"; self._limit = None
    def select(self, cols="*", *a, **k):
        self._cols = cols; return self
    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def ilike(self, c, pattern): self._filters.append(("ilike", c, pattern)); return self
    def limit(self, n): self._limit = n; return self
    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq" and str(rv) != str(v): return False
            if op == "ilike":
                pat = str(v).lower(); s = str(rv or "").lower()
                if pat.endswith("%") and not pat.startswith("%"):
                    if not s.startswith(pat.rstrip("%")): return False
                elif pat.startswith("%") and pat.endswith("%"):
                    if pat.strip("%") not in s: return False
                elif s != pat: return False
        return True
    def _project(self, row):
        if not self._cols or self._cols == "*": return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        # 없는 컬럼 select 는 KeyError · PostgREST 흉내
        for k in keys:
            if k not in row:
                raise KeyError(f"column {k} does not exist on {self.table}")
        return {k: row.get(k) for k in keys}
    def execute(self):
        rows = self.store.setdefault(self.table, [])
        matched = [r for r in rows if self._match(r)]
        if self._limit is not None: matched = matched[:self._limit]
        # 실 postgrest 처럼 없는 컬럼 요청 시 예외
        return _Result([self._project(r) for r in matched])


class FakeSupabase:
    def __init__(self, store): self.store = store
    def table(self, name): return _Query(self.store, name)


# ── 1 · 2 · 소스 계약 (컬럼명 grep) ──────────────────────────────────
def test_HF_source_subscription_select_has_started_at_not_start_date():
    """subscription select 에 없는 컬럼 start_date 재발 방지 · 실 컬럼 started_at 사용."""
    import inspect
    src = inspect.getsource(cu._entitlement_snapshot)
    # subscription select 문자열만 추출
    sub_start = src.index('sb.table("subscriptions")')
    sub_end = src.index("for row in sub", sub_start)
    sub_block = src[sub_start:sub_end]
    assert "start_date" not in sub_block, \
        "subscription select 에 없는 컬럼 start_date 가 다시 들어갔다"
    assert "started_at" in sub_block, \
        "subscription select 는 실 컬럼 started_at 를 사용해야 한다"


def test_HF_source_contract_block_still_uses_start_date():
    """contract 블록의 start_date 는 유지 (contracts 테이블 실 컬럼)."""
    import inspect
    src = inspect.getsource(cu._entitlement_snapshot)
    con_start = src.index('sb.table("contracts")')
    con_end = src.index("return {", con_start + 1)
    con_block = src[con_start:con_end]
    assert "start_date" in con_block, \
        "contract 블록 select 에 start_date 가 있어야 한다 (contracts 실 컬럼)"


# ── 3 · 유효 SaaS contract 만 있는 회사 → active=true · source=contract
def test_HF_active_contract_returns_true_source_contract():
    """subscriptions 는 없고 valid ACTIVE SaaS contract 있을 때 active=true."""
    store = {
        "subscriptions": [],
        "contracts": [{
            "id": "CT-A", "company_id": "C-A",
            "service_type": "SAAS_INDUSTRY",
            "plan_code": "PRO", "start_date": "2026-01-01",
            "end_date": "2030-12-31", "is_active": True,
        }],
    }
    sb = FakeSupabase(store)
    ent = cu._entitlement_snapshot(sb, "C-A")
    assert ent["active"] is True
    assert ent["source"] == "contract"
    assert ent["plan_code"] == "PRO"
    assert ent["start_date"] == "2026-01-01"
    assert ent["end_date"] == "2030-12-31"


# ── 4 · 유효 SaaS subscription → active=true · start_date=started_at
def test_HF_active_subscription_start_date_from_started_at():
    """subscription 이 활성이면 subscription 경로가 우선 · 응답 start_date 는 started_at 매핑."""
    store = {
        "subscriptions": [{
            "id": "SUB-A", "company_id": "C-A", "status": "ACTIVE",
            "product_type": "SAAS_INDUSTRY", "plan_code": "PRO",
            "started_at": "2026-02-01T00:00:00+00:00", "ended_at": None,
        }],
        "contracts": [],
    }
    sb = FakeSupabase(store)
    ent = cu._entitlement_snapshot(sb, "C-A")
    assert ent["active"] is True
    assert ent["source"] == "subscription"
    assert ent["plan_code"] == "PRO"
    assert ent["start_date"] == "2026-02-01T00:00:00+00:00"  # started_at 매핑
    assert ent["end_date"] is None


def test_HF_regression_no_entitlement_still_returns_false():
    """SaaS 없는 회사 → active=false (fail-safe 유지)."""
    store = {"subscriptions": [], "contracts": []}
    sb = FakeSupabase(store)
    ent = cu._entitlement_snapshot(sb, "C-A")
    assert ent["active"] is False
    assert ent["source"] is None


def test_HF_previously_missing_column_would_raise_now_works():
    """FakeSupabase 는 없는 컬럼 select 시 KeyError 로 실 postgrest 를 흉내.
    HOTFIX 로 없는 컬럼 요청이 사라졌으니 contract 경로까지 예외 없이 도달해야 한다.
    (이전 코드였다면 이 픽스처에서 subscription select 가 raise → except → active=false 로
    contract 유효성이 무시됐다.)"""
    store = {
        "subscriptions": [{
            "id": "SUB-1", "company_id": "C-A", "status": "ACTIVE",
            "product_type": "SAAS_INDUSTRY", "plan_code": "PRO",
            "started_at": "2026-01-01T00:00:00+00:00", "ended_at": None,
        }],
        "contracts": [{
            "id": "CT-1", "company_id": "C-A",
            "service_type": "SAAS_INDUSTRY", "plan_code": "STD",
            "start_date": "2025-01-01", "end_date": "2030-12-31", "is_active": True,
        }],
    }
    sb = FakeSupabase(store)
    ent = cu._entitlement_snapshot(sb, "C-A")
    # 이전 버그가 없다면 subscription 경로가 먼저 반환
    assert ent["active"] is True
    assert ent["source"] == "subscription"
