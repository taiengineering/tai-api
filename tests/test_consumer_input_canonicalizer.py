"""WO-ENG-002 — Consumer Input Canonicalization tests.

Alias-only unification checks + Coverage Before/After through the committed
Axis Value Builder (builder unchanged). pytest-discoverable; __main__ prints
the before/after coverage table. No FIELD_MAP/engine/builder modification.
"""

from __future__ import annotations

from services.consumer_input_canonicalizer import (
    canonicalize, ALIASES, CANONICAL_SCHEMA, alias_table,
)
from services.axis_value_builder import build_all, _FAC

# --- representative REAL samples (from VAL-002) ------------------------------
ANON = [  # anonymous_diagnosis_results.input_data
    {"sector": "MANUFACTURING", "worker_count": 120, "floor_area": 4166.95},
    {"scale": "large", "sector": "MANUFACTURING", "workers": 300},  # variant
]
REQ = [  # public_diagnosis_requests.facility_data
    {"building_use": "업무시설", "worker_count": 50, "total_floor_area": 3000, "electric_kw": 75},
    {"worker_count": 70, "contract_eok": 78, "construction_type": "건축"},
    {"ksic_code": "C28", "worker_count": 280, "total_floor_area": 12500},
    {"has_gas": True, "worker_count": 50, "subcon_workers": 10, "floor_area": 500},
]


# --- alias unification ------------------------------------------------------
def test_worker_alias():
    assert canonicalize({"workers": 300})["worker_count"] == 300
    assert canonicalize({"worker_count": 5})["worker_count"] == 5


def test_area_alias_priority():
    # total_floor_area preferred; floor_area folded
    out = canonicalize({"total_floor_area": 3000, "floor_area": 99})
    assert out["total_floor_area"] == 3000 and "floor_area" not in out
    assert canonicalize({"floor_area": 500})["total_floor_area"] == 500


def test_electric_alias():
    assert canonicalize({"electric_kw": 75})["electric_capacity"] == 75


def test_building_use_alias():
    assert canonicalize({"building_use": "업무시설"})["building_use_type"] == "업무시설"


def test_amount_alias():
    assert canonicalize({"contract_eok": 78})["project_amount"] == 78


def test_ksic_alias():
    assert canonicalize({"ksic_code": "C28"})["ksic_major"] == "C28"


def test_list_aliases():
    assert canonicalize({"equipment_data": [{"type": "x"}]})["equipment_list"] == [{"type": "x"}]
    assert canonicalize({"process_data": [1, 2]})["process_list"] == [1, 2]


def test_passthrough_non_alias():
    out = canonicalize({"has_gas": True, "sector": "M", "worker_count": 1})
    assert out["has_gas"] is True and out["sector"] == "M"


def test_no_new_meaning():
    # value copied verbatim, no conversion
    assert canonicalize({"contract_eok": 78})["project_amount"] == 78  # not *1e8 here


def test_schema_matches_aliases():
    assert set(CANONICAL_SCHEMA) == set(ALIASES)


# --- coverage before/after --------------------------------------------------
def _coverage(samples):
    axes = list(_FAC.keys())
    filled = {a: 0 for a in axes}
    for ci in samples:
        for axis, av in build_all(ci).items():
            if av.value is not None:
                filled[axis] += 1
    return filled


def test_coverage_increases_after_canonicalization():
    all_samples = ANON + REQ
    before = _coverage(all_samples)
    after = _coverage([canonicalize(s) for s in all_samples])
    before_total = sum(before.values())
    after_total = sum(after.values())
    assert after_total > before_total  # coverage strictly increases


def _main() -> None:
    all_samples = ANON + REQ
    n = len(all_samples)
    before = _coverage(all_samples)
    after = _coverage([canonicalize(s) for s in all_samples])
    print("Alias Mapping Table:")
    for row in alias_table():
        print(f"  {row['canonical']:18} <- {row['aliases']}")
    print(f"\nCoverage Before / After (real samples N={n}):")
    print("%-20s %-10s %-10s %s" % ("axis", "before", "after", "delta"))
    print("-" * 52)
    for a in _FAC:
        d = after[a] - before[a]
        print("%-20s %-10s %-10s %s" % (a, f"{before[a]}/{n}", f"{after[a]}/{n}",
                                        f"+{d}" if d else ""))
    print("-" * 52)
    print(f"total filled: {sum(before.values())} -> {sum(after.values())}")
    fns = [f for f in globals() if f.startswith("test_")]
    for f in fns:
        globals()[f]()
    print(f"{len(fns)}/{len(fns)} tests PASS")


if __name__ == "__main__":
    _main()
