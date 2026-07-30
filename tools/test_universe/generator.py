#!/usr/bin/env python3
"""Universe Generator (Stage 2a) — WO-E2E-DATASET-002.

Repository(Seed + Universe) -> Allowed Matrix -> Signature-preserving Case 생성.
- SoT: docs/canonical/test-universe/REGISTRY_representative-seed-set_v1.md (Seed)
       docs/canonical/test-universe/STANDARD_test-universe_v1.md (Universe/Contract)
- Signature 는 실제 계약 field_code(LEG 66 + Compiler 5) 에만 앵커. GAP 미포함.
- expected/golden/risk/claim 없음 (범위 밖).
- 결정성: 동일 입력 -> 동일 fingerprint/case_id. Dedup by fingerprint.

Dry Run:  python3 generator.py            (JSON/메모리, DB write 없음)
DB INSERT 는 별도(운영자 승인 + DDL 적용 후).
"""
import hashlib, json

COMPILER = ["site_kind", "scale", "workers", "region", "sector"]

# LEG 실제 field_code (test-universe-v1 실측, 66필드)
REAL_LEG = set("""boiler_capacity_kw building_use_type gas_capacity_kg has_asbestos_demo has_blasting
has_boiler has_chemical has_chemical_substance has_diving has_emergency_broadcast has_emergency_gen
has_fire_hydrant has_gas has_high_pressure_gas has_safety_manager has_smoke_control has_sprinkler
has_tower_crane has_water_tank is_energy_intensive is_multi_use ksic_major total_floor_area worker_count
construction_type has_asbestos has_biological_agent has_casting has_central_hvac has_concrete_work
has_confined_space has_conveyor has_cooling_tower has_crane has_demolition has_dust_work has_electric_work
has_elevator has_excavation has_forklift has_gondola has_grinding has_hazardous_material has_hazmat_storage
has_heat_treatment has_high_place_work has_high_pressure_work has_injection has_machinery has_mech_parking
has_noise_work has_oil_storage has_painting has_pile_work has_plating has_press has_pressure_vessel
has_radiation has_rolling has_scaffold has_septic_tank has_steel_frame has_subcontractor has_temp_electric
has_welding is_complex_building""".split())

UNIVERSAL = ["worker_count", "ksic_major", "building_use_type", "total_floor_area", "has_safety_manager"]

# Representative Seed (REGISTRY v1) : signature = 실제 field_code 만
SEEDS = {
 "REP-MFG-MACHINERY-01": dict(sector="제조", industry="일반기계",
   sig=["has_machinery", "has_press", "has_welding", "has_crane", "has_forklift", "has_grinding"]),
 "REP-MFG-AUTO-01": dict(sector="제조", industry="자동차",
   sig=["has_machinery", "has_press", "has_painting", "has_welding", "has_conveyor", "has_forklift"]),
 "REP-MFG-CHEM-01": dict(sector="제조", industry="화학",
   sig=["has_chemical", "has_chemical_substance", "has_hazardous_material", "has_hazmat_storage", "has_high_pressure_gas", "has_gas", "has_pressure_vessel", "gas_capacity_kg"]),
 "REP-MFG-FOOD-01": dict(sector="제조", industry="식품",
   sig=["has_boiler", "boiler_capacity_kw", "has_cooling_tower", "has_confined_space", "has_chemical", "has_conveyor", "has_forklift"]),
 "REP-MFG-STEEL-01": dict(sector="제조", industry="철강",
   sig=["has_casting", "has_rolling", "has_heat_treatment", "has_crane", "has_tower_crane", "has_dust_work", "has_noise_work", "has_machinery"]),
 "REP-MFG-SHIP-01": dict(sector="제조", industry="조선",
   sig=["has_welding", "has_painting", "has_crane", "has_tower_crane", "has_confined_space", "has_high_place_work", "has_scaffold"]),
 "REP-MFG-SEMI-01": dict(sector="제조", industry="반도체",
   sig=["has_chemical", "has_chemical_substance", "has_hazardous_material", "has_high_pressure_gas", "has_gas", "has_radiation", "has_central_hvac"]),
 "REP-BLD-HOSPITAL-01": dict(sector="건축물", industry="병원",
   sig=["building_use_type", "has_boiler", "has_emergency_gen", "has_sprinkler", "has_smoke_control", "has_biological_agent", "has_central_hvac", "has_water_tank", "is_multi_use"]),
 "REP-BLD-SCHOOL-01": dict(sector="건축물", industry="학교",
   sig=["building_use_type", "has_boiler", "has_sprinkler", "has_fire_hydrant", "has_elevator"]),
 "REP-BLD-APT-01": dict(sector="건축물", industry="공동주택",
   sig=["building_use_type", "has_elevator", "has_mech_parking", "has_sprinkler", "has_septic_tank", "has_water_tank", "is_complex_building"]),
 "REP-BLD-LOGISTICS-01": dict(sector="건축물", industry="물류센터",
   sig=["building_use_type", "has_forklift", "has_conveyor", "has_sprinkler", "total_floor_area"]),
 "REP-BLD-HOTEL-01": dict(sector="건축물", industry="호텔",
   sig=["building_use_type", "is_multi_use", "has_boiler", "has_sprinkler", "has_smoke_control", "has_emergency_broadcast", "has_central_hvac", "has_elevator"]),
 "REP-CON-BUILDING-01": dict(sector="건설", industry="건축",
   sig=["construction_type", "has_scaffold", "has_steel_frame", "has_concrete_work", "has_temp_electric", "has_tower_crane", "has_high_place_work", "has_welding"]),
 "REP-CON-CIVIL-01": dict(sector="건설", industry="토목",
   sig=["construction_type", "has_excavation", "has_pile_work", "has_blasting", "has_concrete_work", "has_temp_electric", "has_scaffold"]),
 "REP-CON-PLANT-01": dict(sector="건설", industry="플랜트",
   sig=["construction_type", "has_welding", "has_pressure_vessel", "has_confined_space", "has_high_place_work", "has_scaffold", "has_crane", "has_electric_work"]),
 "REP-CON-RAILWAY-01": dict(sector="건설", industry="철도",
   sig=["construction_type", "has_excavation", "has_blasting", "has_pile_work", "has_electric_work", "has_temp_electric"]),
}

# Allowed Matrix (Stage 2a 발산축): scale x 공사유무
SCALES = ["small", "medium", "large"]
WORKER_BAND = {"small": 15, "medium": 50, "large": 300}
FLOOR = {"small": 3000, "medium": 15000, "large": 60000}


def project_axis(sector):
    return [True] if sector == "건설" else [False, True]


def site_kind(sector):
    return {"제조": "factory", "건축물": "building", "건설": "construction"}[sector]


def build_contract(seed, scale, has_project):
    leg = {}
    for f in seed["sig"]:
        if f not in REAL_LEG:
            continue  # GAP 은 signature 에서 이미 제외됨 (방어)
        if f.startswith("has_") or f.startswith("is_"):
            leg[f] = True
        elif f == "boiler_capacity_kw":
            leg[f] = 500
        elif f == "gas_capacity_kg":
            leg[f] = 1000
        elif f == "total_floor_area":
            leg[f] = FLOOR[scale]
        elif f in ("building_use_type", "construction_type"):
            leg[f] = seed["industry"]
    # universal baseline
    leg["worker_count"] = WORKER_BAND[scale]
    leg["ksic_major"] = seed["industry"]
    leg["total_floor_area"] = leg.get("total_floor_area", FLOOR[scale])
    leg["has_safety_manager"] = WORKER_BAND[scale] >= 50
    if seed["sector"] != "건설":
        leg["building_use_type"] = leg.get("building_use_type", seed["industry"])
        if has_project:
            leg["has_temp_electric"] = True  # 개보수 공사 파생
    else:
        leg["construction_type"] = leg.get("construction_type", "신축")
    compiler = {"site_kind": site_kind(seed["sector"]), "scale": scale,
                "workers": WORKER_BAND[scale], "region": "서울", "sector": seed["industry"]}
    return compiler, leg


def gen():
    cases, fps = [], set()
    for rid, seed in SEEDS.items():
        sig_real = [f for f in seed["sig"] if f in REAL_LEG]
        for scale in SCALES:
            for hp in project_axis(seed["sector"]):
                compiler, leg = build_contract(seed, scale, hp)
                assert set(sig_real).issubset(set(leg.keys())), (rid, set(sig_real) - set(leg.keys()))
                fp = hashlib.sha1(json.dumps({"c": compiler, "l": leg}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
                if fp in fps:
                    continue
                fps.add(fp)
                cases.append(dict(case_id="CASE-" + fp, representative_id=rid,
                    sector=seed["sector"], industry=seed["industry"], company_type=scale,
                    objects={}, contract={"compiler": compiler, "leg": leg},
                    signature=sig_real, fingerprint=fp, universe_version="test-universe-v1"))
    return cases


if __name__ == "__main__":
    cases = gen()
    fps = [c["fingerprint"] for c in cases]
    print("total:", len(cases), "| unique fp:", len(set(fps)), "| dedup ok:", len(fps) == len(set(fps)))
    print(json.dumps(cases[0], ensure_ascii=False, indent=2))
