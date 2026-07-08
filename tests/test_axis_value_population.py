"""WO-ENG-004 — Axis Value Population tests.

Confirms the builder now PRODUCES the 3 axes whose sources were confirmed in
WO-ENG-003 but previously not consumed by the builder:
  voltage_level    <- transformer_capacity_kva
  storage_capacity <- gas_capacity_m3 / gas_capacity_kg(+density) / water_tank_ton
  equipment_type   <- equipment_list -> has_* flags (default catalog map)

No FIELD_MAP/engine/runtime change; no wiring; 11 axes unchanged.
"""

from __future__ import annotations

from services.axis_value_builder import (
    build_voltage_level, build_storage_capacity, build_equipment_type,
    build_all, DEFAULT_EQUIPMENT_FLAG_MAP,
)


# --- voltage_level ----------------------------------------------------------
def test_voltage_from_transformer():
    r = build_voltage_level({"transformer_capacity_kva": 1500})
    assert r.value == 1500 and r.method == "FALLBACK"
    assert r.sources_used == ["transformer_capacity_kva"]


def test_voltage_direct_priority():
    r = build_voltage_level({"voltage_level": 22900, "transformer_capacity_kva": 1500})
    assert r.value == 22900 and r.method == "DIRECT"


def test_voltage_gap_when_neither():
    assert build_voltage_level({}).method == "GAP"


# --- storage_capacity -------------------------------------------------------
def test_storage_priority():
    assert build_storage_capacity({"gas_capacity_m3": 30}).value == 30       # m3 first
    assert build_storage_capacity({"gas_capacity_kg": 100,
                                   "gas_density_kg_m3": 2.0}).value == 50.0   # kg/density
    assert build_storage_capacity({"water_tank_ton": 40}).value == 40        # water ton~=m3
    # kg without density and no water tank -> gap
    assert build_storage_capacity({"gas_capacity_kg": 100}).method == "GAP"


# --- equipment_type ---------------------------------------------------------
def test_equipment_list_first():
    r = build_equipment_type({"equipment_list": [{"type": "press"}],
                              "has_boiler": True})
    assert "press" in r.value  # list-derived present


def test_equipment_flag_fallback_default():
    r = build_equipment_type({"has_boiler": True, "has_gas": True})
    assert set(r.value) == {"boiler", "gas_facility"}


def test_default_flag_map_grounded():
    # keys are real catalog has_* equipment/hazard flags
    assert "has_boiler" in DEFAULT_EQUIPMENT_FLAG_MAP
    assert "has_high_pressure_gas" in DEFAULT_EQUIPMENT_FLAG_MAP


# --- coverage re-measure ----------------------------------------------------
def test_three_axes_now_produced():
    # an input carrying the confirmed sources -> all 3 axes produced
    ci = {"transformer_capacity_kva": 1500, "water_tank_ton": 40,
          "equipment_list": [{"type": "press"}]}
    out = build_all(ci)
    assert out["voltage_level"].value == 1500
    assert out["storage_capacity"].value == 40
    assert out["equipment_type"].value == ["press"]


def _main() -> None:
    axes3 = ["voltage_level", "storage_capacity", "equipment_type"]
    # before: sources absent -> all GAP; after: sources present -> produced
    without = {"sector": "M", "worker_count": 10}
    withsrc = {"transformer_capacity_kva": 1500, "gas_capacity_m3": 30,
               "equipment_list": [{"type": "press"}], "has_boiler": True}
    b = build_all(without)
    a = build_all(withsrc)
    print("axis                 no-source        with-source")
    print("-" * 52)
    for ax in axes3:
        print("%-20s %-16s %s" % (ax, b[ax].method, f"{a[ax].method}={a[ax].value}"))
    fns = [f for f in globals() if f.startswith("test_")]
    for f in fns:
        globals()[f]()
    print("-" * 52)
    print(f"{len(fns)}/{len(fns)} population tests PASS")


if __name__ == "__main__":
    _main()
