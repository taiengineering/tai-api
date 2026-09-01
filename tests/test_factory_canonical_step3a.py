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

def test_fields_present():
    for f in C7: assert f in FactoryCreate.model_fields and f in FactoryUpdate.model_fields
    assert "completion_year" in FactoryUpdate.model_fields and "completion_year" in FactoryCreate.model_fields
    assert "building_structure_code" in FactoryCreate.model_fields and "building_structure_code" in FactoryUpdate.model_fields
    assert "building_structure_name" in FactoryCreate.model_fields and "building_structure_name" in FactoryUpdate.model_fields
    assert CANONICAL_NULL_CLEAR_FIELDS == set(C7)
    assert "building_composition_codes" not in FactoryCreate.model_fields
    assert "building_composition_codes" not in FactoryUpdate.model_fields
    assert "regulatory_designation_codes" not in FactoryCreate.model_fields
    assert "regulatory_designation_codes" not in FactoryUpdate.model_fields
    assert "company_id" not in FactoryUpdate.model_fields

def test_F3A_01(): assert _cre(work_height_m=3.5).dict(exclude_none=True)["work_height_m"]==3.5
def test_F3A_02(): assert _cre(has_truck_loading_unloading=False).dict(exclude_none=True)["has_truck_loading_unloading"] is False
def test_F3A_03(): assert _cre(manual_handling_weight_kg=0).dict(exclude_none=True)["manual_handling_weight_kg"]==0
def test_F3A_04(): assert _cre(business_activity_types=[]).dict(exclude_none=True)["business_activity_types"]==[]
def test_F3A_05():
    d=_cre().dict(exclude_none=True)
    for f in C7: assert f not in d
    assert "building_structure_code" not in d and "completion_year" not in d

def test_F3A_06():
    provided=FactoryUpdate(work_height_m=5.0).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"work_height_m":5.0}
def test_F3A_07():
    provided=FactoryUpdate(**{"work_height_m":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"work_height_m":None}
def test_F3A_08():
    provided=FactoryUpdate(**{"has_truck_loading_unloading":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"has_truck_loading_unloading":None}
def test_F3A_09():
    provided=FactoryUpdate(**{"business_activity_types":None}).dict(exclude_unset=True)
    assert _build_factory_update(provided)=={"business_activity_types":None}
def test_F3A_10():
    assert _build_factory_update(FactoryUpdate(has_manual_heavy_handling=False).dict(exclude_unset=True))=={"has_manual_heavy_handling":False}
def test_F3A_11():
    assert _build_factory_update(FactoryUpdate(work_height_m=0).dict(exclude_unset=True))=={"work_height_m":0}
def test_F3A_12():
    assert _build_factory_update(FactoryUpdate(hazardous_work_environments=[]).dict(exclude_unset=True))=={"hazardous_work_environments":[]}
def test_F3A_legacy_none_skip():
    upd=_build_factory_update(FactoryUpdate(**{"name":None,"work_height_m":None}).dict(exclude_unset=True))
    assert "name" not in upd and upd["work_height_m"] is None
def test_F3A_abc():
    assert _build_factory_update(FactoryUpdate(work_height_m=9.0).dict(exclude_unset=True))=={"work_height_m":9.0}

def test_F3A_13():
    for f in ["work_height_m","truck_loading_height_m","manual_handling_weight_kg"]:
        with pytest.raises(ValidationError): FactoryUpdate(**{f:-1})
def test_F3A_14():
    with pytest.raises(ValidationError): FactoryUpdate(work_height_m="12")
def test_F3A_15():
    with pytest.raises(ValidationError): FactoryUpdate(work_height_m=True)
def test_F3A_16():
    for bad in ["true","false",0,1]:
        with pytest.raises(ValidationError): FactoryUpdate(has_truck_loading_unloading=bad)
def test_F3A_17():
    for bad in [[1],[True],[{"a":1}],[["x"]]]:
        with pytest.raises(ValidationError): FactoryUpdate(business_activity_types=bad)
def test_F3A_18():
    for bad in [[""],["  "],["ok",""]]:
        with pytest.raises(ValidationError): FactoryUpdate(hazardous_work_environments=bad)
def test_F3A_array_ok():
    assert FactoryUpdate(business_activity_types=["A","B"]).business_activity_types==["A","B"]
    assert FactoryUpdate(business_activity_types=[]).business_activity_types==[]
    assert FactoryUpdate(business_activity_types=None).business_activity_types is None
def test_F3A_num_ok():
    assert FactoryUpdate(work_height_m=0).work_height_m==0
    assert FactoryUpdate(work_height_m=3).work_height_m==3
    assert FactoryUpdate(truck_loading_height_m=2.5).truck_loading_height_m==2.5

def test_F3A_19():
    assert _build_factory_update(FactoryUpdate(completion_year=2020).dict(exclude_unset=True))=={"completion_year":2020}
def test_F3A_20_21():
    assert _cre(building_structure_code="RC1",building_structure_name="철근콘크리트").dict(exclude_none=True)["building_structure_code"]=="RC1"
    assert _build_factory_update(FactoryUpdate(building_structure_code="S",building_structure_name="철골").dict(exclude_unset=True))=={"building_structure_code":"S","building_structure_name":"철골"}

def test_F3A_26_27():
    c=FactoryCreate(company_id="C1",name="F",building_composition_codes=["x"],regulatory_designation_codes=["y"])
    d=c.dict(exclude_none=True)
    assert "building_composition_codes" not in d and "regulatory_designation_codes" not in d
    u=_build_factory_update(FactoryUpdate(**{"building_composition_codes":["x"],"regulatory_designation_codes":["y"]}).dict(exclude_unset=True))
    assert "building_composition_codes" not in u and "regulatory_designation_codes" not in u

def test_F3A_28():
    from routers.factories import router
    paths={r.path for r in router.routes}
    assert not any("legal-diagnosis" in p for p in paths)
    assert "/factories/{factory_id}" in paths and "/factories/{factory_id}/legal" in paths
