"""STEP3A factory canonical API — model strict boundary + sparse PATCH merge tests."""
import pytest
from pydantic import ValidationError
from routers.factories import (
    FactoryCreate, FactoryUpdate, CANONICAL_NULL_CLEAR_FIELDS, _build_factory_update,
)

C7 = ["work_height_m","has_truck_loading_unloading","truck_loading_height_m",
      "has_manual_heavy_handling","manual_handling_weight_kg",
      "business_activity_types","hazardous_work_environments"]

def _cre(**kw):
    base={"company_id":"C1","name":"F"}; base.update(kw); return FactoryCreate(**base)

# F3A write field set = 7 (+structure/completion in models)
def test_fields_present():
    for f in C7: assert f in FactoryCreate.model_fields and f in FactoryUpdate.model_fields
    assert "completion_year" in FactoryUpdate.model_fields and "completion_year" in FactoryCreate.model_fields
    assert "building_structure_code" in FactoryCreate.model_fields and "building_structure_code" in FactoryUpdate.model_fields
    assert "building_structure_name" in FactoryCreate.model_fields and "building_structure_name" in FactoryUpdate.model_fields
    assert set(C7) <= CANONICAL_NULL_CLEAR_FIELDS  # STEP3B: superset(9); 7 still null-clearable
    assert "company_id" not in FactoryUpdate.model_fields  # F3A-25

# F3A-01 create work_height_m
def test_F3A_01(): assert _cre(work_height_m=3.5).dict(exclude_none=True)["work_height_m"]==3.5
# F3A-02 create false preserved
def test_F3A_02(): assert _cre(has_truck_loading_unloading=False).dict(exclude_none=True)["has_truck_loading_unloading"] is False
# F3A-03 create numeric 0 preserved
def test_F3A_03(): assert _cre(manual_handling_weight_kg=0).dict(exclude_none=True)["manual_handling_weight_kg"]==0
# F3A-04 create [] preserved
def test_F3A_04(): assert _cre(business_activity_types=[]).dict(exclude_none=True)["business_activity_types"]==[]
# F3A-05 omitted canonical absent from INSERT payload
def test_F3A_05():
    d=_cre().dict(exclude_none=True)
    for f in C7: assert f not in d
    assert "building_structure_code" not in d and "completion_year" not in d

# F3A-06 PATCH omitted preserves existing (not in update_data)
def test_F3A_06():
    provided=FactoryUpdate(work_height_m=5.0).dict(exclude_unset=True)
    upd=_build_factory_update(provided)
    assert upd=={"work_height_m":5.0}  # ksic 등 omitted 없음
# F3A-07 PATCH explicit NULL clears numeric
def test_F3A_07():
    provided=FactoryUpdate(**{"work_height_m":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"work_height_m":None}
# F3A-08 PATCH explicit NULL clears boolean
def test_F3A_08():
    provided=FactoryUpdate(**{"has_truck_loading_unloading":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"has_truck_loading_unloading":None}
# F3A-09 PATCH explicit NULL clears array
def test_F3A_09():
    provided=FactoryUpdate(**{"business_activity_types":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"business_activity_types":None}
# F3A-10 PATCH false preserved
def test_F3A_10():
    assert _build_factory_update(FactoryUpdate(has_manual_heavy_handling=False).dict(exclude_unset=True))=={"has_manual_heavy_handling":False}
# F3A-11 PATCH 0 preserved
def test_F3A_11():
    assert _build_factory_update(FactoryUpdate(work_height_m=0).dict(exclude_unset=True))=={"work_height_m":0}
# F3A-12 PATCH [] preserved
def test_F3A_12():
    assert _build_factory_update(FactoryUpdate(hazardous_work_environments=[]).dict(exclude_unset=True))=={"hazardous_work_environments":[]}
# legacy field explicit None still skipped (historical)
def test_F3A_legacy_none_skip():
    upd=_build_factory_update(FactoryUpdate(**{"name":None,"work_height_m":None}).dict(exclude_unset=True))
    assert "name" not in upd and upd["work_height_m"] is None
# A/B/C regression: update only B
def test_F3A_abc():
    upd=_build_factory_update(FactoryUpdate(work_height_m=9.0).dict(exclude_unset=True))
    assert upd=={"work_height_m":9.0}

# F3A-13 negative numeric rejected
def test_F3A_13():
    for f in ["work_height_m","truck_loading_height_m","manual_handling_weight_kg"]:
        with pytest.raises(ValidationError): FactoryUpdate(**{f:-1})
# F3A-14 numeric string rejected
def test_F3A_14():
    with pytest.raises(ValidationError): FactoryUpdate(work_height_m="12")
# F3A-15 boolean-as-number rejected for numeric
def test_F3A_15():
    with pytest.raises(ValidationError): FactoryUpdate(work_height_m=True)
# F3A-16 string boolean rejected
def test_F3A_16():
    for bad in ["true","false",0,1]:
        with pytest.raises(ValidationError): FactoryUpdate(has_truck_loading_unloading=bad)
# F3A-17 array non-string rejected
def test_F3A_17():
    for bad in [[1],[True],[{"a":1}],[["x"]]]:
        with pytest.raises(ValidationError): FactoryUpdate(business_activity_types=bad)
# F3A-18 array empty-string item rejected
def test_F3A_18():
    for bad in [[""],["  "],["ok",""]]:
        with pytest.raises(ValidationError): FactoryUpdate(hazardous_work_environments=bad)
# valid arrays accepted
def test_F3A_array_ok():
    assert FactoryUpdate(business_activity_types=["A","B"]).business_activity_types==["A","B"]
    assert FactoryUpdate(business_activity_types=[]).business_activity_types==[]
    assert FactoryUpdate(business_activity_types=None).business_activity_types is None
# numeric int and float both ok, >=0
def test_F3A_num_ok():
    assert FactoryUpdate(work_height_m=0).work_height_m==0
    assert FactoryUpdate(work_height_m=3).work_height_m==3
    assert FactoryUpdate(truck_loading_height_m=2.5).truck_loading_height_m==2.5

# F3A-19 completion_year PATCH supported
def test_F3A_19():
    assert _build_factory_update(FactoryUpdate(completion_year=2020).dict(exclude_unset=True))=={"completion_year":2020}
# F3A-20/21 structure code/name create+update
def test_F3A_20_21():
    assert _cre(building_structure_code="RC1",building_structure_name="철근콘크리트").dict(exclude_none=True)["building_structure_code"]=="RC1"
    assert _build_factory_update(FactoryUpdate(building_structure_code="S",building_structure_name="철골").dict(exclude_unset=True))=={"building_structure_code":"S","building_structure_name":"철골"}

# F3A-26/27 building_composition_codes / regulatory_designation_codes → STEP3B 에서 쓰기 노출로 대체
def test_F3A_26_27_superseded_by_step3b():
    # STEP3B exposes these two for write (type/shape·vocab covered in step3b tests).
    assert "building_composition_codes" in FactoryCreate.model_fields
    assert "regulatory_designation_codes" in FactoryUpdate.model_fields

# F3A-28 no /legal-diagnosis/profile route regression
def test_F3A_28():
    from routers.factories import router
    paths={r.path for r in router.routes}
    assert not any("legal-diagnosis" in p for p in paths)
    assert "/factories/{factory_id}" in paths and "/factories/{factory_id}/legal" in paths
