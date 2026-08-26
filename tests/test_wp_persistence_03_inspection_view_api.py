"""WP-PERSISTENCE-03 STEP-2 — inspection view endpoint tests.

FastAPI TestClient 대신 handler direct invocation + static contract 검증(환경상 full app
부팅/의존성 제약 회피). auth ordering(guard before composer) 은 spy 로 반드시 증명한다.

pytest 호환 + self-runner. 실 라우터(routers/inspection_view.py)를 그대로 import 해 검증한다.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect as _inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.inspection_view as V  # 실제 라우터 deliverable
from fastapi import HTTPException
from services.inspection_view_composer import InspectionViewComposeError

# STEP-1 SEALED composer 파일 sha256 (unchanged 증명용)
SEALED_COMPOSER_SHA = "4a8f38fbd1a297a360a80825314e888f6a0e3a7f6c2d20f38f9c1910497969d5"
SEALED_COMPOSER_TEST_SHA = "36fab4373baa13a6fa48deb6c478740de24d5e959ec4bfd0d1fbe202346ad858"

POS_INSP = "3f9cf36f-5bbc-4dad-9ba6-e71643020e9a"
NEG_INSP = "217f0c15-56d5-48a4-88ef-8027e0a06057"

_INTERNAL_LEAK = "dc79ac3c-388c-42dc-b029-3dd9bda54a47 table=safety_inspections schema_state=leak"


class _SB:
    """sentinel supabase instance (identity 확인용)."""


def _run(inspection_id, current=None):
    return asyncio.run(V.get_inspection_view(inspection_id, current=current or {"id": "u1"}))


class _Patch:
    """router 모듈의 get_supabase / guard / composer 를 임시 교체."""

    def __init__(self, *, sb=None, guard=None, composer=None):
        self.sb = sb if sb is not None else _SB()
        self.guard = guard
        self.composer = composer
        self._orig = {}

    def __enter__(self):
        self._orig = {"g": V.get_supabase, "e": V._ensure_inspection_own, "c": V.compose_inspection_view}
        V.get_supabase = lambda: self.sb
        if self.guard is not None:
            V._ensure_inspection_own = self.guard
        if self.composer is not None:
            V.compose_inspection_view = self.composer
        return self

    def __exit__(self, *a):
        V.get_supabase = self._orig["g"]
        V._ensure_inspection_own = self._orig["e"]
        V.compose_inspection_view = self._orig["c"]
        return False


def _vm():
    return {
        "inspection_id": POS_INSP,
        "inspection_set_id": "7fee7518-0e77-445c-b822-d5178d069b3c",
        "schema_id": "dc79ac3c-388c-42dc-b029-3dd9bda54a47",
        "form_code": "GEN-INSPECT-RESULT-001",
        "schema_version": 1,
        "fields": {"inspection_subject": None, "inspected_at": "2026-05-14T00:00:00",
                   "inspection_title": "소방시설공사업법 점검", "inspector_display": None,
                   "inspection_results": []},
        "completeness": {"is_complete": False, "missing_required_fields": ["inspection_subject", "inspection_results"]},
    }


# ── T01–T02 route / dependency ───────────────────────────────────────────────
def test_T01_route_path_exact():
    routes = {(r["method"], r["full_path"]) for r in V.router.routes}
    assert ("GET", "/inspection/{inspection_id}/view") in routes


def test_T02_get_current_user_dependency_present():
    sig = _inspect.signature(V.get_inspection_view)
    dep = sig.parameters["current"].default
    assert getattr(dep, "dependency", None) is V.get_current_user


# ── T03–T07 auth ordering / same instances ───────────────────────────────────
def test_T03_guard_before_composer_order():
    order = []
    guard = lambda sb, iid, cur: order.append("guard")
    def comp(iid, supabase=None):
        order.append("composer"); return _vm()
    with _Patch(guard=guard, composer=comp):
        _run(POS_INSP)
    assert order == ["guard", "composer"]


def test_T04_guard_success_composer_once():
    calls = {"c": 0}
    def comp(iid, supabase=None):
        calls["c"] += 1; return _vm()
    with _Patch(guard=lambda sb, iid, cur: None, composer=comp):
        _run(POS_INSP)
    assert calls["c"] == 1


def test_T05_guard_receives_inspection_id():
    seen = {}
    def guard(sb, iid, cur): seen["iid"] = iid
    with _Patch(guard=guard, composer=lambda iid, supabase=None: _vm()):
        _run(POS_INSP)
    assert seen["iid"] == POS_INSP


def test_T06_guard_receives_same_supabase():
    sb = _SB(); seen = {}
    def guard(s, iid, cur): seen["sb"] = s
    with _Patch(sb=sb, guard=guard, composer=lambda iid, supabase=None: _vm()):
        _run(POS_INSP)
    assert seen["sb"] is sb


def test_T07_composer_receives_same_supabase():
    sb = _SB(); seen = {}
    def comp(iid, supabase=None): seen["sb"] = supabase; return _vm()
    with _Patch(sb=sb, guard=lambda s, iid, cur: None, composer=comp):
        _run(POS_INSP)
    assert seen["sb"] is sb


# ── T08–T09 unauthorized → composer not called ───────────────────────────────
def test_T08_guard_404_composer_not_called():
    calls = {"c": 0}
    def guard(sb, iid, cur):
        raise HTTPException(status_code=404, detail="not found")
    def comp(iid, supabase=None):
        calls["c"] += 1; return _vm()
    with _Patch(guard=guard, composer=comp):
        try:
            _run(POS_INSP); raise AssertionError("expected HTTPException")
        except HTTPException as e:
            assert e.status_code == 404
    assert calls["c"] == 0


def test_T09_cross_company_unowned_404_composer_not_called():
    calls = {"c": 0}
    def guard(sb, iid, cur):
        raise HTTPException(status_code=404, detail="hidden")  # 미소유 legacy row → 존재 은닉
    with _Patch(guard=guard, composer=lambda iid, supabase=None: calls.__setitem__("c", calls["c"] + 1)):
        try:
            _run(NEG_INSP)
        except HTTPException as e:
            assert e.status_code == 404
    assert calls["c"] == 0


# ── T10–T12 success passthrough ──────────────────────────────────────────────
def test_T10_success_exact_passthrough():
    vm = _vm()
    with _Patch(guard=lambda s, i, c: None, composer=lambda iid, supabase=None: vm):
        result = _run(POS_INSP)
    assert result is vm  # 그대로 반환 (복사/가공 없음)


def test_T11_success_no_extra_wrapper():
    with _Patch(guard=lambda s, i, c: None, composer=lambda iid, supabase=None: _vm()):
        result = _run(POS_INSP)
    for bad in ("success", "data", "result", "status", "payload"):
        assert bad not in result


def test_T12_success_top_level_keys_exactly_7():
    with _Patch(guard=lambda s, i, c: None, composer=lambda iid, supabase=None: _vm()):
        result = _run(POS_INSP)
    assert set(result.keys()) == {
        "inspection_id", "inspection_set_id", "schema_id", "form_code",
        "schema_version", "fields", "completeness",
    }


# ── T13–T22 domain error → HTTP mapping ──────────────────────────────────────
def _raise_code(code):
    def comp(iid, supabase=None):
        raise InspectionViewComposeError(code, _INTERNAL_LEAK)
    return comp


def _expect_http(code, status):
    with _Patch(guard=lambda s, i, c: None, composer=_raise_code(code)):
        try:
            _run(POS_INSP); raise AssertionError(f"expected HTTPException for {code}")
        except HTTPException as e:
            assert e.status_code == status, f"{code}: got {e.status_code}, want {status}"
            assert isinstance(e.detail, dict) and e.detail.get("code") == code
            return e


def test_T13_inspection_not_found_404():
    _expect_http("INSPECTION_NOT_FOUND", 404)


def test_T14_inspection_set_unresolved_409():
    _expect_http("INSPECTION_SET_UNRESOLVED", 409)


def test_T15_mixed_inspection_set_source_409():
    _expect_http("MIXED_INSPECTION_SET_SOURCE", 409)


def test_T16_bridge_not_found_409():
    _expect_http("BRIDGE_NOT_FOUND", 409)


def test_T17_presentation_schema_not_mapped_409():
    _expect_http("PRESENTATION_SCHEMA_NOT_MAPPED", 409)


def test_T18_schema_not_found_409():
    _expect_http("SCHEMA_NOT_FOUND", 409)


def test_T19_schema_not_approved_409():
    _expect_http("SCHEMA_NOT_APPROVED", 409)


def test_T20_unsupported_presentation_schema_409():
    _expect_http("UNSUPPORTED_PRESENTATION_SCHEMA", 409)


def test_T21_result_item_unresolved_409():
    _expect_http("RESULT_ITEM_UNRESOLVED", 409)


def test_T22_source_integrity_error_409():
    _expect_http("SOURCE_INTEGRITY_ERROR", 409)


# ── T23–T25 leak / generic ───────────────────────────────────────────────────
def test_T23_public_error_no_exc_detail():
    e = _expect_http("SOURCE_INTEGRITY_ERROR", 409)
    assert _INTERNAL_LEAK not in str(e.detail)


def test_T24_public_error_no_internal_table_schema_text():
    e = _expect_http("BRIDGE_NOT_FOUND", 409)
    blob = str(e.detail)
    assert "safety_inspections" not in blob
    assert "dc79ac3c-388c-42dc-b029-3dd9bda54a47" not in blob
    assert "schema_state" not in blob


def test_T25_generic_exception_not_converted():
    def comp(iid, supabase=None):
        raise ValueError("boom-unexpected")
    with _Patch(guard=lambda s, i, c: None, composer=comp):
        try:
            _run(POS_INSP); raise AssertionError("expected ValueError to propagate")
        except HTTPException:
            raise AssertionError("generic exception must NOT be converted to HTTPException")
        except ValueError as e:
            assert "boom-unexpected" in str(e)


# ── T26–T27 registry ─────────────────────────────────────────────────────────
def _registry_modules():
    import router_registry.inspection as reg
    import importlib
    importlib.reload(reg)
    return [r["module"] for r in reg.ROUTERS]


def test_T26_registry_includes_inspection_view_once():
    mods = _registry_modules()
    assert mods.count("routers.inspection_view") == 1


def test_T27_registry_preserves_existing_entries():
    mods = _registry_modules()
    for expected in [
        "routers.inspection_sets", "routers.inspection_set_items", "routers.inspection_schedule",
        "routers.inspection_checklist", "routers.inspection_setup", "routers.work_schedules",
        "routers.schedule_engine", "routers.schedule_pipeline", "routers.overdue_checker",
        "routers.safety_template", "routers.corrective_actions", "routers.factory_process_v3",
        "routers.legal_status_api",
    ]:
        assert expected in mods, f"registry lost {expected}"


# ── T28 no-write in router ───────────────────────────────────────────────────
def test_T28_router_no_write_methods():
    src = _inspect.getsource(V)
    for bad in (".insert(", ".update(", ".delete(", ".upsert(", ".rpc("):
        assert bad not in src, f"forbidden write call {bad} in router"


# ── T29–T30 composer files unchanged (SEALED) ────────────────────────────────
def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_T29_composer_source_sha_unchanged():
    import services.inspection_view_composer as comp
    assert _sha256(comp.__file__) == SEALED_COMPOSER_SHA


def test_T30_composer_test_sha_unchanged():
    path = os.path.join(os.path.dirname(__file__), "test_wp_persistence_03_composer.py")
    assert _sha256(path) == SEALED_COMPOSER_TEST_SHA


# ── self-runner ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
