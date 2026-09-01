"""WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 STEP4 — BUILDING 36 assembler 검증.

FakeSB 로 factories 단일 row 만 제공하고 실 함수 assemble_building_marketing_contract 를 호출한다.
factories 외 테이블 조회 시 예외(사용 금지 입증). DB WRITE 0.
"""
import pytest

from services.safe_building_canonical_assembler import (
    assemble_building_marketing_contract,
    TARGET_FIELDS,
)

FID = "fac-1"
E5 = ["building_use_type","main_structure","is_multi_use","is_energy_intensive","building_grade"]


class _Res:
    def __init__(self, data): self.data = data
class _Q:
    def __init__(self, table, sb): self.table=table; self.sb=sb; self._f={}
    def select(self, *a, **k): return self
    def eq(self, c, v): self._f[c]=v; return self
    def limit(self, n): return self
    def execute(self):
        self.sb.reads.append(self.table)
        rows=self.sb.data.get(self.table, [])
        out=[r for r in rows if all(r.get(k)==v for k,v in self._f.items())]
        return _Res([dict(r) for r in out])
class _Tbl:
    def __init__(self, table, sb): self.table=table; self.sb=sb
    def select(self, *a, **k): return _Q(self.table, self.sb).select(*a, **k)
    def insert(self,*a,**k): raise AssertionError(f"WRITE insert {self.table}")
    def update(self,*a,**k): raise AssertionError(f"WRITE update {self.table}")
    def delete(self,*a,**k): raise AssertionError(f"WRITE delete {self.table}")
    def upsert(self,*a,**k): raise AssertionError(f"WRITE upsert {self.table}")
class FakeSB:
    def __init__(self, factories=None):
        self.data={"factories": factories if factories is not None else []}
        self.reads=[]
    def table(self, n):
        if n!="factories": raise AssertionError(f"FORBIDDEN table: {n}")
        return _Tbl(n, self)

def _fac(**kw):
    base={"id":FID}; base.update(kw); return base
def _asm(**kw):
    sb=FakeSB(factories=[_fac(**kw)] if kw or True else [])
    return assemble_building_marketing_contract(sb, FID), sb
def _asm_row(row):
    sb=FakeSB(factories=[row]); return assemble_building_marketing_contract(sb, FID), sb

# ── denominator ──
def test_B4_01_key_36():
    r,_=_asm(); assert len(r["values"])==36
def test_B4_02_03_missing_extra():
    r,_=_asm()
    assert set(r["values"].keys())==set(TARGET_FIELDS)
    assert list(r["values"].keys())==TARGET_FIELDS
def test_B4_04_contract_version():
    r,_=_asm(); assert r["contract_version"]=="MKT_BLD_PAID_CONTRACT_V1"
def test_B4_05_sector():
    r,_=_asm(); assert r["sector"]=="BUILDING" and r["factory_id"]==FID
def test_has_chemical_substance_not_a_target():
    r,_=_asm(); assert "has_chemical_substance" not in r["values"]

# ── address ──
def test_B4_06_road_priority():
    r,_=_asm(address_road="도로명1", address_jibun="지번1")
    assert r["values"]["address"]=="도로명1"
def test_B4_07_jibun_fallback():
    r,_=_asm(address_jibun="지번1")
    assert r["values"]["address"]=="지번1"
def test_B4_08_detail_join():
    r,_=_asm(address_road="도로명1", address_detail="101호")
    assert r["values"]["address"]=="도로명1 101호"
def test_B4_09_blank_road_jibun_fallback():
    r,_=_asm(address_road="   ", address_jibun="지번1")
    assert r["values"]["address"]=="지번1"
def test_B4_10_no_address_null():
    r,_=_asm()
    assert r["values"]["address"] is None
    assert "address" not in r["unresolved_fields"]
def test_B4_11_12_no_sido_no_site_address():
    r,_=_asm(address_sido="서울", address_sigungu="강남", address_dong="역삼", site_address="LEAK주소")
    assert r["values"]["address"] is None  # base(road/jibun) 없음 → NULL, sido/site_address 미사용
    for v in r["values"].values():
        assert v != "LEAK주소"

# ── DIRECT / TRANSFORM ──
def test_B4_13_14_15_16_17_rename():
    r,_=_asm(building_area=1500.5, underground_floor_count=2, completion_year=2010, employee_count=50, electrical_capacity_kw=300)
    v=r["values"]
    assert v["total_floor_area"]==1500.5 and v["basement_count"]==2 and v["built_year"]==2010
    assert v["worker_count"]==50 and v["electric_capacity"]==300
    assert r["provenance"]["total_floor_area"]["mode"]=="TRANSFORM"
def test_B4_18_sprinkler_false():
    r,_=_asm(has_sprinkler=False); assert r["values"]["has_sprinkler"] is False
def test_B4_19_gas_false():
    r,_=_asm(has_gas=False); assert r["values"]["has_gas"] is False
def test_B4_20_21_has_chemical_alias():
    r,_=_asm(has_chemical_substance=True)
    assert r["values"]["has_chemical"] is True
    assert "has_chemical_substance" not in r["values"]
    assert r["provenance"]["has_chemical"]["source"]=="factories.has_chemical_substance"
def test_B4_22_23_24_25_zero_preserved():
    r,_=_asm(work_height_m=0, manual_handling_weight_kg=0, gas_capacity_kg=0, water_tank_ton=0)
    v=r["values"]
    assert v["work_height_m"]==0 and v["manual_handling_weight_kg"]==0 and v["gas_capacity_kg"]==0 and v["water_tank_ton"]==0
def test_B4_26_empty_array_preserved():
    r,_=_asm(multi_use_type=[])
    assert r["values"]["multi_use_type"]==[]
    assert "multi_use_type" not in r["unresolved_fields"]

# ── E5 ──
def test_B4_27_33_e5():
    r,_=_asm()
    e5_un=[f for f in E5 if f in r["unresolved_fields"]]
    assert len(e5_un)==5
    assert [f for f in E5 if r["values"][f] is not None]==[]
def test_B4_28_building_use_type_unresolved():
    r,_=_asm(building_use_code="공장")
    assert r["values"]["building_use_type"] is None and "building_use_type" in r["unresolved_fields"]
def test_B4_29_main_structure_unresolved():
    r,_=_asm(building_structure_code="RC", building_structure_name="철근콘크리트")
    assert r["values"]["main_structure"] is None and "main_structure" in r["unresolved_fields"]
def test_B4_30_is_multi_use_unresolved():
    for val in (True, False):
        r,_=_asm(is_multi_use=val)
        assert r["values"]["is_multi_use"] is None and "is_multi_use" in r["unresolved_fields"]
def test_B4_31_is_energy_intensive_unresolved():
    r,_=_asm(annual_energy_toe=5000)
    assert r["values"]["is_energy_intensive"] is None and "is_energy_intensive" in r["unresolved_fields"]
def test_B4_32_building_grade_unresolved():
    r,_=_asm(building_grade=3)
    assert r["values"]["building_grade"] is None and "building_grade" in r["unresolved_fields"]

# ── no-derivation ──
def test_B4_34_gas_no_derivation():
    r,_=_asm(gas_capacity_m3=100)  # has_gas 미제공
    assert r["values"]["has_gas"] is None
def test_B4_35_hazmat_no_derivation():
    r,_=_asm(is_hazardous_material=True, hazardous_material=True, hazardous_material_type="유류")
    assert r["values"]["has_hazmat_storage"] is None
def test_B4_36_fire_required_no_derivation():
    r,_=_asm(fire_facility_required=True)
    for f in ["has_sprinkler","has_fire_hydrant","has_emergency_broadcast","has_emergency_gen","has_smoke_control"]:
        assert r["values"][f] is None
def test_B4_37_water_tank_no_derivation():
    r,_=_asm(water_tank_ton=50)  # has_water_tank 미제공
    assert r["values"]["has_water_tank"] is None
def test_B4_38_multi_use_type_no_is_multi_use_derivation():
    r,_=_asm(multi_use_type=["노래방"])
    assert r["values"]["is_multi_use"] is None
def test_B4_39_energy_high_no_derivation():
    r,_=_asm(annual_energy_toe=999999)
    assert r["values"]["is_energy_intensive"] is None

# ── multi_use_type structure ──
def test_B4_40_null_pass():
    r,_=_asm(); assert r["values"]["multi_use_type"] is None
def test_B4_41_empty_pass():
    r,_=_asm(multi_use_type=[]); assert r["values"]["multi_use_type"]==[]
def test_B4_42_arbitrary_pass():
    r,_=_asm(multi_use_type=["노래방","임의업종Z"]); assert r["values"]["multi_use_type"]==["노래방","임의업종Z"]
def test_B4_43_non_list_unresolved():
    r,_=_asm(multi_use_type="노래방")
    assert r["values"]["multi_use_type"] is None and "multi_use_type" in r["unresolved_fields"]
def test_B4_44_non_string_item_unresolved():
    r,_=_asm(multi_use_type=[1])
    assert r["values"]["multi_use_type"] is None and "multi_use_type" in r["unresolved_fields"]
def test_B4_45_blank_item_unresolved():
    r,_=_asm(multi_use_type=["  "])
    assert r["values"]["multi_use_type"] is None and "multi_use_type" in r["unresolved_fields"]

# ── DB scope ──
def test_B4_47_48_read_set_and_write():
    r,sb=_asm(has_gas=True)
    assert set(sb.reads)=={"factories"}
def test_B4_49_50_51_52_no_other_tables():
    r,sb=_asm()
    for t in ("buildings","facility_profiles","system_codes","diagnosis_input_fields"):
        assert t not in sb.reads

# ── provenance ──
def test_B4_53_provenance_keys_36():
    r,_=_asm(); assert set(r["provenance"].keys())==set(TARGET_FIELDS)
def test_B4_54_mode_domain():
    r,_=_asm()
    for f,p in r["provenance"].items():
        assert p["mode"] in ("DIRECT","TRANSFORM","UNRESOLVED")
def test_B4_55_e5_provenance_unresolved():
    r,_=_asm()
    for f in E5: assert r["provenance"][f]["mode"]=="UNRESOLVED"
def test_B4_56_has_chemical_source():
    r,_=_asm(); assert r["provenance"]["has_chemical"]["source"]=="factories.has_chemical_substance"
def test_B4_57_address_source():
    r,_=_asm(); assert r["provenance"]["address"]["source"]=="factories.address_road/address_jibun/address_detail"

# ── factory row missing ──
def test_missing_factory_row_36_keys():
    sb=FakeSB(factories=[])
    r=assemble_building_marketing_contract(sb, FID)
    assert len(r["values"])==36
    for f in E5: assert f in r["unresolved_fields"]
    assert r["values"]["has_gas"] is None and r["values"]["address"] is None

def test_unresolved_sorted_dedupe():
    r,_=_asm()
    assert r["unresolved_fields"]==sorted(set(r["unresolved_fields"]))
