"""Local tests — LEG-GATE8-CANONICAL-LOSSLESS-MATERIALIZATION-IMPLEMENT-01.

production HTTP/DB 미사용. helper + nexas + build_facility 를 격리 검증한다.
run_diagnosis 전체(supabase 필요)는 실행하지 않고, inp 병합 스니펫을 그대로 재현해
end-to-end(입력 -> canonical input -> DiagnoseStep1Body.input -> build_facility) 를 확인한다.
"""
from __future__ import annotations

from typing import Any, Dict

from schemas.legal_engine import DiagnoseStep1Body
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.diagnosis_nexas_adapter import nexas_run_body_from_request
from services.canonical.materialization import canonical_applicability
from clients.leg_runtime_client import build_facility, _LEG_INPUT_FIELDS


def _simulate_run_diagnosis_inp(body: DiagnosisRunBody, tier_code: str = "FREE_DIAGNOSIS") -> Dict[str, Any]:
    """run_diagnosis 의 inp 구성 스니펫을 그대로 재현(문자 동일 로직)."""
    inp: dict = {"region": body.region or "", "anonymous_flow": True, "tier_code": tier_code}
    _available: dict = {f: getattr(body, f, None) for f in type(body).model_fields}
    _available.update(getattr(body, "form_data", None) or {})
    for _code, _val in canonical_applicability(_available).items():
        inp.setdefault(_code, _val)
    return inp


PASS = []
FAIL = []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append((name, detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  :: {detail}" if detail else ""))


# ─────────────────────────────────────────────────────────────────────────────
# helper unit
# ─────────────────────────────────────────────────────────────────────────────
def test_helper_vocab_allowlist():
    src = {
        "has_confined_space": True, "has_diving": True, "total_floor_area": 2800.0,
        "has_tower_crane": True,        # WIRING-SPECIFIC: now vocab -> must KEEP (specific 축)
        "has_chemical_substance": True, # NON-vocab (alias source, leg key=has_chemical) -> must drop
        "process_list": [{"x": 1}],     # NON-vocab (derivation source) -> must drop
        "random_field": 123,            # NON-vocab -> must drop
        "has_boiler": None,             # present-but-None -> must drop
        "construction_type": "  ",      # blank string -> must drop
    }
    out = canonical_applicability(src)
    check("helper.keeps_vocab_present", out.get("has_confined_space") is True and out.get("has_diving") is True and out.get("total_floor_area") == 2800.0)
    check("helper.keeps_wiring_specific(has_tower_crane)", out.get("has_tower_crane") is True)
    check("helper.drops_alias_source(has_chemical_substance)", "has_chemical_substance" not in out)
    check("helper.drops_derivation_source(process_list)", "process_list" not in out)
    check("helper.drops_nonvocab(random_field)", "random_field" not in out)
    check("helper.drops_none(has_boiler=None)", "has_boiler" not in out)
    check("helper.drops_blank(construction_type)", "construction_type" not in out)


# ─────────────────────────────────────────────────────────────────────────────
# T2 — PAID exact-field passthrough (end-to-end through nexas + build_facility)
# ─────────────────────────────────────────────────────────────────────────────
REP_FIELDS = [
    "has_confined_space", "has_diving", "has_blasting", "has_boiler",
    "has_high_pressure_gas", "has_gas", "has_chemical", "is_multi_use",
    "has_hazmat_storage", "has_emergency_gen", "has_emergency_broadcast",
    "has_water_tank", "total_floor_area",
]


def test_paid_exact_passthrough():
    # PAID raw request: rich form_data with the representative vocab fields present.
    form_data = {f: (2800.0 if f == "total_floor_area" else True) for f in REP_FIELDS}
    raw = {
        "auth_token": "t", "sector": "BUILDING", "tier": "PAID",
        "worker_count": 45, "region": "서울",
        "form_data": dict(form_data),
    }
    body = nexas_run_body_from_request(raw)
    # nexas must have preserved the non-declared vocab fields on body.form_data
    fd = getattr(body, "form_data", None) or {}
    for f in REP_FIELDS:
        check(f"nexas.preserved[{f}]", f in fd or getattr(body, f, None) is not None, f"fd={f in fd} attr={getattr(body,f,None)!r}")

    inp = _simulate_run_diagnosis_inp(body)
    step1 = DiagnoseStep1Body(sector="BUILDING", input=inp, worker_count=45, building_use_type="사무실")
    facility = build_facility(step1)

    for f in REP_FIELDS:
        expected = 2800.0 if f == "total_floor_area" else True
        check(f"e2e.facility_preserved[{f}]", facility.get(f) == expected, f"got={facility.get(f)!r}")


# ─────────────────────────────────────────────────────────────────────────────
# T4 — unknown / non-vocab field does NOT become an RTM facility field
# ─────────────────────────────────────────────────────────────────────────────
def test_negative_unknown_field():
    raw = {"auth_token": "t", "sector": "MANUFACTURING", "worker_count": 10,
           "form_data": {"totally_made_up": 1, "has_boiler": True}}
    body = nexas_run_body_from_request(raw)
    inp = _simulate_run_diagnosis_inp(body)
    step1 = DiagnoseStep1Body(sector="MANUFACTURING", input=inp, worker_count=10)
    facility = build_facility(step1)
    check("neg.unknown_not_in_facility", "totally_made_up" not in facility)
    check("neg.vocab_still_ok(has_boiler)", facility.get("has_boiler") is True)


# ─────────────────────────────────────────────────────────────────────────────
# T5 — WIRING SPECIFIC PASSTHROUGH, GENERIC ALIAS ABSENT
#   has_tower_crane -> specific 통과(≠ has_crane), has_asbestos_demo -> specific 통과(≠ has_asbestos)
# ─────────────────────────────────────────────────────────────────────────────
def test_negative_no_new_alias():
    raw = {"auth_token": "t", "sector": "CONSTRUCTION", "worker_count": 30,
           "form_data": {"has_tower_crane": True, "has_asbestos_demo": True}}
    body = nexas_run_body_from_request(raw)
    inp = _simulate_run_diagnosis_inp(body)
    step1 = DiagnoseStep1Body(sector="CONSTRUCTION", input=inp, construction_type="건축")
    facility = build_facility(step1)
    # SPECIFIC PASSTHROUGH YES — exact-name 보존
    check("wire.specific_present_tower_crane", facility.get("has_tower_crane") is True)
    check("wire.specific_present_asbestos_demo", facility.get("has_asbestos_demo") is True)
    # GENERIC ALIAS NO — generic 축은 파생/broadening 되지 않는다
    check("wire.no_generic_has_crane", facility.get("has_crane") is None)
    check("wire.no_generic_has_asbestos", facility.get("has_asbestos") is None)


# ─────────────────────────────────────────────────────────────────────────────
# T6 — NEW DERIVATION ABSENT (process_list/equipment_list !-> has_welding/forklift/...)
# ─────────────────────────────────────────────────────────────────────────────
def test_negative_no_derivation():
    raw = {"auth_token": "t", "sector": "MANUFACTURING", "worker_count": 20,
           "form_data": {"process_list": [{"name": "welding"}],
                         "equipment_list": [{"code": "forklift"}]}}
    body = nexas_run_body_from_request(raw)
    inp = _simulate_run_diagnosis_inp(body)
    step1 = DiagnoseStep1Body(sector="MANUFACTURING", input=inp, worker_count=20)
    facility = build_facility(step1)
    for f in ("has_welding", "has_forklift", "has_conveyor", "has_press"):
        check(f"neg.no_derivation[{f}]", facility.get(f) is None)


# ─────────────────────────────────────────────────────────────────────────────
# T3 — FREE regression: FREE-like step1_body -> build_facility has NO has_*
#   (FREE path code is untouched; this proves facility projection is unchanged.)
# ─────────────────────────────────────────────────────────────────────────────
def test_free_regression_projection():
    # FREE _build_step1_body(BUILDING) shape: input has NO has_*, presets set attrs.
    inp = {"region": "서울", "site_kind": "building", "scale": "medium", "anonymous_flow": True}
    step1 = DiagnoseStep1Body(
        sector="BUILDING", input=inp, building_use_type="사무실",
        floor_area=2800.0, total_floor_area=2800.0, worker_count=45,
        employee_count=45, floor_count=5,
    )
    facility = build_facility(step1)
    has_star = [k for k in facility if k.startswith("has_") or k.startswith("is_")]
    check("free.no_has_star_in_facility", has_star == [], f"unexpected={has_star}")
    check("free.context_preserved", facility.get("worker_count") == 45 and facility.get("total_floor_area") == 2800.0 and facility.get("building_use_type") == "사무실")


# ─────────────────────────────────────────────────────────────────────────────
# T7 — build_facility existing behavior unchanged (approved aliases still work)
# ─────────────────────────────────────────────────────────────────────────────
def test_build_facility_existing_aliases():
    # approved alias: has_chemical <- has_chemical_substance ; has_high_place_work <- has_high_work
    step1 = DiagnoseStep1Body(sector="MANUFACTURING", input={}, has_chemical_substance=True, has_high_work=True)
    facility = build_facility(step1)
    check("t7.approved_alias_has_chemical", facility.get("has_chemical") is True)
    check("t7.approved_alias_has_high_place_work", facility.get("has_high_place_work") is True)


if __name__ == "__main__":
    print("=" * 70)
    print("PAID BEFORE/AFTER materialization examples")
    print("=" * 70)
    for sector, fd in [
        ("BUILDING", {"has_gas": True, "has_water_tank": True, "is_multi_use": True}),
        ("CONSTRUCTION", {"has_confined_space": True, "has_diving": True, "has_blasting": True}),
        ("MANUFACTURING", {"has_boiler": True, "has_high_pressure_gas": True}),
    ]:
        body = nexas_run_body_from_request({"auth_token": "t", "sector": sector, "worker_count": 30, "form_data": dict(fd)})
        inp = _simulate_run_diagnosis_inp(body)
        step1 = DiagnoseStep1Body(sector=sector, input=inp, construction_type="건축", worker_count=30, building_use_type="사무실")
        after = build_facility(step1)
        # BEFORE: run_diagnosis inp had NO has_* (region/anon/tier only) -> facility has_* would be empty for these
        before_inp = {"region": "", "anonymous_flow": True, "tier_code": "X"}
        before_step1 = DiagnoseStep1Body(sector=sector, input=before_inp, construction_type="건축", worker_count=30, building_use_type="사무실")
        before = build_facility(before_step1)
        rich_keys = sorted(fd.keys())
        print(f"[{sector}] input applicability={rich_keys}")
        print(f"    BEFORE facility has_* = {sorted(k for k in before if k.startswith(('has_','is_')))}")
        print(f"    AFTER  facility has_* = {sorted(k for k in after if k.startswith(('has_','is_')))}")

    print("=" * 70)
    for fn in [
        test_helper_vocab_allowlist, test_paid_exact_passthrough,
        test_negative_unknown_field, test_negative_no_new_alias,
        test_negative_no_derivation, test_free_regression_projection,
        test_build_facility_existing_aliases,
    ]:
        print("-" * 70)
        print(fn.__name__)
        fn()
    print("=" * 70)
    print(f"TOTAL: PASS={len(PASS)}  FAIL={len(FAIL)}")
    if FAIL:
        for n, d in FAIL:
            print("  FAILED:", n, d)
        raise SystemExit(1)
    print("ALL PASS")
