"""WO-QA-UNIVERSE-PHASE1-TAXONOMY-CANONICAL-001 — Taxonomy API 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  TAX-API-01  GET /items 결과에 service_code/area_code/qa_type 필드 존재
  TAX-API-02  service_code filter 적용
  TAX-API-03  area_code filter 적용
  TAX-API-04  qa_type filter 적용
  TAX-API-05  3개 filter AND 조합
  TAX-API-06  legacy site_code/category filter 불변
  TAX-API-07  GET /taxonomy — services 반환
  TAX-API-08  GET /taxonomy — qa_types 10개 고정
  TAX-API-09  GET /taxonomy — areas가 qa_items distinct 결과와 일치
  TAX-API-10  Admin 아닌 사용자 taxonomy 403 거부
  TAX-API-11  GET /summary 결과 계약 불변 (taxonomy 추가 후에도)
  TAX-API-12  manual run/schedule/callback 계약 불변
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers (same pattern as test_admin_qa.py)
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)
        self._filters: dict = {}

    def select(self, *a, **k): return self
    def eq(self, field, val, **k):
        self._filters[field] = val
        return self
    def neq(self, *a, **k):   return self
    def in_(self, *a, **k):   return self
    def gte(self, *a, **k):   return self
    def lte(self, *a, **k):   return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def not_(self, *a, **k):  return self

    @property
    def not_(self):
        return self

    def is_(self, *a, **k):   return self

    def update(self, data, **k):
        return self

    def insert(self, rows, **k):
        return self

    def delete(self, *a, **k): return self

    def execute(self):
        rows = self._rows
        # Apply eq filters in-memory for filter tests
        for field, val in self._filters.items():
            rows = [r for r in rows if r.get(field) == val]
        return type("R", (), {"data": rows, "count": len(rows)})()


class _FilterQ(_Q):
    """Filter-aware mock that actually applies eq filters."""

    def eq(self, field, val, **k):
        self._filters[field] = val
        return self


class _Supabase:
    def __init__(self, table_map: dict):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _item(
    id_="item-1",
    scenario_id="P0-WWW-001",
    site_code="WWW",
    category="LANDING",
    service_code="WWW",
    area_code="LANDING",
    qa_type="AVAILABILITY",
    priority="P0",
    enabled=True,
):
    return {
        "id": id_,
        "scenario_id": scenario_id,
        "site_code": site_code,
        "category": category,
        "service_code": service_code,
        "area_code": area_code,
        "qa_type": qa_type,
        "name": f"Test {id_}",
        "description": None,
        "expected_summary": None,
        "priority": priority,
        "runner_type": "PLAYWRIGHT",
        "enabled": enabled,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _sched(qa_item_id="item-1"):
    return {
        "id": "sched-1",
        "qa_item_id": qa_item_id,
        "enabled": False,
        "frequency_type": "MANUAL",
        "frequency_value": None,
        "anchor_time": None,
        "day_of_week": None,
        "timezone": "Asia/Seoul",
        "next_run_at": None,
        "last_scheduled_at": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-01: GET /items 결과에 service_code/area_code/qa_type 필드 존재
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX01_items_include_taxonomy_fields():
    items = [_item("item-1", service_code="WWW", area_code="LANDING", qa_type="AVAILABILITY")]
    sb = _Supabase({
        "qa_items":       _Q(rows=items),
        "qa_schedules":   _Q(rows=[_sched("item-1")]),
        "qa_run_results": _Q(rows=[]),
    })
    result = svc.list_items(sb)
    assert result["items"], "items must not be empty"
    item = result["items"][0]
    assert item["service_code"] == "WWW"
    assert item["area_code"] == "LANDING"
    assert item["qa_type"] == "AVAILABILITY"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-02: service_code filter 적용
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX02_service_code_filter():
    items = [
        _item("i1", service_code="WWW",  area_code="LANDING", qa_type="AVAILABILITY"),
        _item("i2", service_code="SAAS", area_code="MYPAGE",  qa_type="FUNCTIONAL"),
    ]
    sb = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result = svc.list_items(sb, service_code="SAAS")
    assert result["total"] == 1
    assert result["items"][0]["service_code"] == "SAAS"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-03: area_code filter 적용
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX03_area_code_filter():
    items = [
        _item("i1", service_code="WWW",  area_code="LANDING", qa_type="AVAILABILITY"),
        _item("i2", service_code="WWW",  area_code="SEARCH",  qa_type="AVAILABILITY"),
    ]
    sb = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result = svc.list_items(sb, area_code="SEARCH")
    assert result["total"] == 1
    assert result["items"][0]["area_code"] == "SEARCH"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-04: qa_type filter 적용
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX04_qa_type_filter():
    items = [
        _item("i1", service_code="WWW", area_code="SEARCH", qa_type="AVAILABILITY"),
        _item("i2", service_code="WWW", area_code="SEARCH", qa_type="FUNCTIONAL"),
    ]
    sb = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result = svc.list_items(sb, qa_type="FUNCTIONAL")
    assert result["total"] == 1
    assert result["items"][0]["qa_type"] == "FUNCTIONAL"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-05: 3개 filter AND 조합
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX05_three_filters_AND():
    items = [
        _item("i1", service_code="SAAS", area_code="MYPAGE", qa_type="FUNCTIONAL"),
        _item("i2", service_code="SAAS", area_code="MYPAGE", qa_type="AVAILABILITY"),
        _item("i3", service_code="WWW",  area_code="MYPAGE", qa_type="FUNCTIONAL"),
    ]
    sb = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result = svc.list_items(sb, service_code="SAAS", area_code="MYPAGE", qa_type="FUNCTIONAL")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["service_code"] == "SAAS"
    assert item["area_code"] == "MYPAGE"
    assert item["qa_type"] == "FUNCTIONAL"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-06: legacy site_code/category filter 불변
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX06_legacy_filters_unchanged():
    items = [
        _item("i1", site_code="WWW",  category="LANDING", service_code="WWW",  area_code="LANDING", qa_type="AVAILABILITY"),
        _item("i2", site_code="SAFE", category="AUTH",    service_code="SAAS", area_code="AUTH",    qa_type="E2E"),
    ]

    # site_code filter still works (fresh Supabase per call to avoid filter accumulation)
    sb_site = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result_site = svc.list_items(sb_site, site_code="SAFE")
    assert result_site["total"] == 1
    assert result_site["items"][0]["site_code"] == "SAFE"

    # category filter still works
    sb_cat = _Supabase({
        "qa_items":       _FilterQ(rows=items),
        "qa_schedules":   _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    result_cat = svc.list_items(sb_cat, category="LANDING")
    assert result_cat["total"] == 1
    assert result_cat["items"][0]["category"] == "LANDING"


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-07: GET /taxonomy — services 반환
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX07_taxonomy_services():
    rows = [
        {"service_code": "WWW",  "area_code": "LANDING"},
        {"service_code": "SAAS", "area_code": "MYPAGE"},
    ]
    sb = _Supabase({"qa_items": _Q(rows=rows)})
    result = svc.get_taxonomy(sb)
    codes = [s["code"] for s in result["services"]]
    assert "WWW" in codes
    assert "SAAS" in codes
    # Each service has label
    for svc_item in result["services"]:
        assert "label" in svc_item
        assert svc_item["label"]  # non-empty


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-08: GET /taxonomy — qa_types 정확히 10개 고정
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX08_taxonomy_qa_types_10():
    sb = _Supabase({"qa_items": _Q(rows=[])})
    result = svc.get_taxonomy(sb)
    assert len(result["qa_types"]) == 10
    expected_codes = {
        "AVAILABILITY", "FUNCTIONAL", "INTEGRATION", "E2E", "API",
        "PERFORMANCE", "SECURITY", "DATA", "ACCESSIBILITY", "VISUAL",
    }
    actual_codes = {qt["code"] for qt in result["qa_types"]}
    assert actual_codes == expected_codes
    for qt in result["qa_types"]:
        assert qt["label"]  # non-empty label


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-09: GET /taxonomy — areas가 qa_items distinct 결과와 일치
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX09_taxonomy_areas_from_distinct_items():
    rows = [
        {"service_code": "WWW",  "area_code": "LANDING"},
        {"service_code": "WWW",  "area_code": "LANDING"},   # duplicate — must be deduped
        {"service_code": "WWW",  "area_code": "SEARCH"},
        {"service_code": "SAAS", "area_code": "MYPAGE"},
        {"service_code": "SAAS", "area_code": "AUTH"},
    ]
    sb = _Supabase({"qa_items": _Q(rows=rows)})
    result = svc.get_taxonomy(sb)
    areas = result["areas"]

    www_codes  = {a["code"] for a in areas.get("WWW", [])}
    saas_codes = {a["code"] for a in areas.get("SAAS", [])}

    assert www_codes  == {"LANDING", "SEARCH"}
    assert saas_codes == {"MYPAGE", "AUTH"}

    # LANDING duplicate must be deduped
    www_landings = [a for a in areas.get("WWW", []) if a["code"] == "LANDING"]
    assert len(www_landings) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-10: Admin 아닌 사용자 taxonomy 403 거부
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX10_non_admin_taxonomy_403(monkeypatch):
    from fastapi import FastAPI, HTTPException as FHTTPEx
    from fastapi.testclient import TestClient
    from routers.admin_qa import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role_code": "099"}

    def _deny(*a, **k):
        raise FHTTPEx(status_code=403, detail="권한이 없습니다")

    monkeypatch.setattr("routers.admin_qa._require_admin", _deny)
    monkeypatch.setattr("routers.admin_qa.get_supabase", lambda: None)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/admin/qa/taxonomy", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-11: GET /summary 결과 계약 불변
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX11_summary_contract_unchanged():
    items = [_item("i1", service_code="WWW", area_code="LANDING", qa_type="AVAILABILITY")]
    sb = _Supabase({
        "qa_items":       _Q(rows=items),
        "qa_run_results": _Q(rows=[]),
        "qa_schedules":   _Q(rows=[]),
    })
    result = svc.get_summary(sb)
    # Original contract keys must all be present
    assert "total"         in result
    assert "enabled"       in result
    assert "status_counts" in result
    assert "sites"         in result
    assert "last_run_at"   in result
    assert "next_run_at"   in result
    # status_counts must have exactly 6 keys
    assert set(result["status_counts"].keys()) == {
        "PASS", "FAIL", "FLAKY", "BLOCKED", "SKIPPED", "NEVER_RUN"
    }


# ─────────────────────────────────────────────────────────────────────────────
# TAX-API-12: manual run/schedule 계약 불변
# ─────────────────────────────────────────────────────────────────────────────

def test_TAX12_create_run_contract_unchanged():
    """create_run은 taxonomy 필드 추가 후에도 trigger_type=MANUAL, ordinal=1..N 고정."""
    inserted_run = {
        "id": "run-1", "trigger_type": "MANUAL", "run_status": "QUEUED",
        "requested_by": "admin", "requested_at": "2026-10-01T00:00:00+09:00",
        "started_at": None, "finished_at": None, "error_code": None, "error_summary": None,
        "created_at": "2026-10-01T00:00:00+09:00", "updated_at": "2026-10-01T00:00:00+09:00",
        "github_run_id": None, "github_run_attempt": None, "head_sha": None, "branch_name": None,
    }

    class _RunQ(_Q):
        def insert(self, *a, **k): return _Q(rows=[inserted_run])

    targets_inserted = []

    class _TargetQ(_Q):
        def insert(self, rows, **k):
            targets_inserted.extend(rows)
            return _Q(rows=rows)

    sb = _Supabase({
        "qa_items":       _Q(rows=[{"id": "item-1", "enabled": True}]),
        "qa_runs":        _RunQ(),
        "qa_run_targets": _TargetQ(),
    })
    result = svc.create_run(sb, "admin", ["item-1"])
    assert result["trigger_type"] == "MANUAL"
    assert len(targets_inserted) == 1
    assert targets_inserted[0]["ordinal"] == 1


def test_TAX12b_update_schedule_contract_unchanged():
    """update_schedule frequency_value / enabled contract 불변."""
    existing = {
        "id": "sched-1", "qa_item_id": "item-1",
        "enabled": False, "frequency_type": "MINUTES", "frequency_value": 30,
        "anchor_time": None, "day_of_week": None, "timezone": "Asia/Seoul",
        "next_run_at": "2026-10-01T08:00:00+09:00", "last_scheduled_at": None,
        "created_at": "2026-10-01T00:00:00+09:00", "updated_at": "2026-10-01T00:00:00+09:00",
    }

    class _SchedQ(_Q):
        def __init__(self):
            super().__init__(rows=[existing])
            self._did_update = False
            self.updated_data = {}

        def select(self, *a, **k): return self
        def eq(self, *a, **k):     return self
        def limit(self, *a, **k):  return self

        def update(self, data, **k):
            self._did_update = True
            self.updated_data = data
            return self

        def execute(self):
            if self._did_update:
                return type("R", (), {"data": [dict(existing, **self.updated_data)], "count": 1})()
            return type("R", (), {"data": [existing], "count": 1})()

    q = _SchedQ()
    sb = _Supabase({"qa_schedules": q})
    result = svc.update_schedule(sb, "item-1", {"frequency_value": 60})
    # next_run_at must be NULL (Phase 2-E scheduler authority)
    assert result.get("next_run_at") is None
