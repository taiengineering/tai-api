"""WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 STEP4 — CONSTRUCTION 27 assembler 검증.

FakeSB 로 construction_sites/construction_site_processes/construction_works/subcontractors 만
제공하고 실 함수 assemble_construction_marketing_contract 를 호출한다. factories/equipment/
material/system_codes/diagnosis_input_fields 조회 시 예외(사용 금지 입증). DB WRITE 0.
"""
import pytest

from services.safe_construction_canonical_assembler import (
    assemble_construction_marketing_contract,
    TARGET_FIELDS,
    E15_FIELDS,
)

SID = "site-1"
ALLOWED_TABLES = {"construction_sites", "construction_site_processes", "construction_works", "subcontractors"}


class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, table, sb):
        self.table = table
        self.sb = sb
        self._f = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._f[col] = val
        return self

    def limit(self, n):
        return self

    def execute(self):
        self.sb.reads.append(self.table)
        rows = self.sb.data.get(self.table, [])
        out = [r for r in rows if all(r.get(k) == v for k, v in self._f.items())]
        return _Res([dict(r) for r in out])


class _Tbl:
    def __init__(self, table, sb):
        self.table = table
        self.sb = sb

    def select(self, *a, **k):
        return _Q(self.table, self.sb).select(*a, **k)

    # any write path → fail loudly (DB WRITE 0)
    def insert(self, *a, **k):
        raise AssertionError(f"WRITE insert on {self.table}")

    def update(self, *a, **k):
        raise AssertionError(f"WRITE update on {self.table}")

    def delete(self, *a, **k):
        raise AssertionError(f"WRITE delete on {self.table}")

    def upsert(self, *a, **k):
        raise AssertionError(f"WRITE upsert on {self.table}")


class FakeSB:
    def __init__(self, sites=None, processes=None, works=None, subs=None):
        self.data = {
            "construction_sites": sites or [],
            "construction_site_processes": processes or [],
            "construction_works": works or [],
            "subcontractors": subs or [],
        }
        self.reads = []

    def table(self, name):
        if name not in ALLOWED_TABLES:
            raise AssertionError(f"FORBIDDEN table access: {name}")
        return _Tbl(name, self)


def _site(**kw):
    base = {"id": SID, "is_active": True, "contract_amount": None, "site_address": None, "site_type": None}
    base.update(kw)
    return base


def _asm(**kw):
    sb = FakeSB(**kw)
    return assemble_construction_marketing_contract(sb, SID), sb


# ── denominator ──
def test_C4_01_key_27():
    r, _ = _asm(sites=[_site()])
    assert len(r["values"]) == 27


def test_C4_02_03_missing_extra_0():
    r, _ = _asm(sites=[_site()])
    assert set(r["values"].keys()) == set(TARGET_FIELDS)
    assert list(r["values"].keys()) == TARGET_FIELDS  # order frozen


# ── site ──
def test_C4_04_project_amount():
    r, _ = _asm(sites=[_site(contract_amount=150)])
    assert r["values"]["project_amount"] == 150
    assert r["provenance"]["project_amount"]["mode"] == "DIRECT"


def test_C4_05_project_address():
    r, _ = _asm(sites=[_site(site_address="서울시 강남구")])
    assert r["values"]["project_address"] == "서울시 강남구"


def test_C4_06_building():
    r, _ = _asm(sites=[_site(site_type="BUILDING")])
    assert r["values"]["construction_type"] == "건축"


def test_C4_07_civil():
    r, _ = _asm(sites=[_site(site_type="CIVIL")])
    assert r["values"]["construction_type"] == "토목"


def test_C4_08_specialty():
    r, _ = _asm(sites=[_site(site_type="SPECIALTY")])
    assert r["values"]["construction_type"] == "공통"


def test_C4_09_unknown_type_null_unresolved():
    r, _ = _asm(sites=[_site(site_type="WEIRD")])
    assert r["values"]["construction_type"] is None
    assert "construction_type" in r["unresolved_fields"]


def test_type_null_is_null_not_unresolved():
    r, _ = _asm(sites=[_site(site_type=None)])
    assert r["values"]["construction_type"] is None
    assert "construction_type" not in r["unresolved_fields"]


def test_C4_10_worker_count_always_unresolved():
    r, _ = _asm(sites=[_site(total_workers=99, direct_workers=50)])
    assert r["values"]["worker_count"] is None
    assert "worker_count" in r["unresolved_fields"]
    assert r["provenance"]["worker_count"]["mode"] == "UNRESOLVED"


def test_C4_11_total_workers_no_leak():
    r, _ = _asm(sites=[_site(total_workers=99)])
    assert 99 not in [r["values"][f] for f in r["values"]]


# ── subcontractor ──
def test_C4_12_zero_active():
    r, _ = _asm(sites=[_site()], subs=[{"id": "x", "site_id": SID, "is_active": False, "work_type": "철근", "company_name": "A"}])
    assert r["values"]["has_subcontractor"] is False
    assert r["values"]["subcontractor_count"] == 0
    assert r["values"]["subcontractor"] is None


def test_C4_13_14_active_has_count():
    subs = [
        {"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "철근", "worker_count": 5, "has_safety_manager": True},
        {"id": "s2", "site_id": SID, "is_active": True, "company_name": "B", "work_type": "형틀", "worker_count": 0, "has_safety_manager": False},
    ]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["has_subcontractor"] is True
    assert r["values"]["subcontractor_count"] == 2


def test_C4_15_16_17_18_row_shape():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A건설", "work_type": "철근콘크리트", "worker_count": 0, "has_safety_manager": True}]
    r, _ = _asm(sites=[_site()], subs=subs)
    row = r["values"]["subcontractor"][0]
    assert set(row.keys()) == {"company_name", "work_scope", "worker_count", "safety_manager"}
    assert row["company_name"] == "A건설"
    assert row["work_scope"] == "철근콘크리트"
    assert row["worker_count"] == 0  # preserved


def test_C4_19_20_21_safety_labels():
    subs = [
        {"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": 1, "has_safety_manager": True},
        {"id": "s2", "site_id": SID, "is_active": True, "company_name": "B", "work_type": "b", "worker_count": 1, "has_safety_manager": False},
        {"id": "s3", "site_id": SID, "is_active": True, "company_name": "C", "work_type": "c", "worker_count": 1, "has_safety_manager": None},
    ]
    r, _ = _asm(sites=[_site()], subs=subs)
    labels = [row["safety_manager"] for row in r["values"]["subcontractor"]]
    assert labels == ["있음", "없음", "모름"]


def test_C4_22_missing_work_type_whole_null_unresolved():
    subs = [
        {"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "철근", "worker_count": 1, "has_safety_manager": True},
        {"id": "s2", "site_id": SID, "is_active": True, "company_name": "B", "work_type": None, "worker_count": 1, "has_safety_manager": True},
    ]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert "subcontractor" in r["unresolved_fields"]
    # has/count 는 여전히 resolved
    assert r["values"]["has_subcontractor"] is True
    assert r["values"]["subcontractor_count"] == 2


# ── process ──
def test_C4_23_24_active_name():
    procs = [
        {"id": "p1", "site_id": SID, "is_active": True, "process_name": "터파기"},
        {"id": "p2", "site_id": SID, "is_active": False, "process_name": "철근"},
    ]
    r, _ = _asm(sites=[_site()], processes=procs)
    pl = r["values"]["process_list"]
    assert len(pl) == 1 and pl[0]["name"] == "터파기"


def test_C4_25_26_27_hazard_join_split_dedupe():
    procs = [{"id": "p1", "site_id": SID, "is_active": True, "process_name": "굴착"}]
    works = [
        {"id": "w1", "site_id": SID, "is_active": True, "process_id": "p1", "hazard_codes": "추락, 협착"},
        {"id": "w2", "site_id": SID, "is_active": True, "process_id": "p1", "hazard_codes": "협착,충돌"},
    ]
    r, _ = _asm(sites=[_site()], processes=procs, works=works)
    haz = r["values"]["process_list"][0]["hazard_codes"]
    assert haz == ["추락", "협착", "충돌"]  # split+trim+dedupe deterministic


def test_C4_28_allowed_pass():
    procs = [{"id": "p1", "site_id": SID, "is_active": True, "process_name": "x"}]
    works = [{"id": "w1", "site_id": SID, "is_active": True, "process_id": "p1", "hazard_codes": "전도,추락,협착,충돌,화재,폭발,감전,질식,절단,기타"}]
    r, _ = _asm(sites=[_site()], processes=procs, works=works)
    assert r["values"]["process_list"] is not None
    assert "process_list" not in r["unresolved_fields"]


def test_C4_29_30_unknown_token_null_unresolved_not_dropped():
    procs = [{"id": "p1", "site_id": SID, "is_active": True, "process_name": "x"}]
    works = [{"id": "w1", "site_id": SID, "is_active": True, "process_id": "p1", "hazard_codes": "추락,붕괴"}]
    r, _ = _asm(sites=[_site()], processes=procs, works=works)
    assert r["values"]["process_list"] is None
    assert "process_list" in r["unresolved_fields"]  # 조용히 드롭 0


def test_C4_31_zero_process_null_not_unresolved():
    r, _ = _asm(sites=[_site()], processes=[])
    assert r["values"]["process_list"] is None
    assert "process_list" not in r["unresolved_fields"]


# ── C5 numeric ──
def _w(**kw):
    base = {"id": "w", "site_id": SID, "is_active": True, "process_id": None}
    base.update(kw)
    return base


def test_C4_32_numeric_none():
    r, _ = _asm(sites=[_site()], works=[_w(id="w1")])
    assert r["values"]["work_height_m"] is None
    assert "work_height_m" not in r["unresolved_fields"]


def test_C4_33_numeric_one_distinct():
    r, _ = _asm(sites=[_site()], works=[_w(id="w1", work_height_m=3.5)])
    assert r["values"]["work_height_m"] == 3.5


def test_C4_34_numeric_zero_preserved():
    r, _ = _asm(sites=[_site()], works=[_w(id="w1", manual_handling_weight_kg=0)])
    assert r["values"]["manual_handling_weight_kg"] == 0


def test_C4_35_numeric_duplicate_same():
    works = [_w(id="w1", work_height_m=3.5), _w(id="w2", work_height_m=3.5)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["work_height_m"] == 3.5


def test_C4_36_37_conflict_null_unresolved_no_max():
    works = [_w(id="w1", work_height_m=3.0), _w(id="w2", work_height_m=9.0)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["work_height_m"] is None  # NOT 9.0 (no MAX)
    assert "work_height_m" in r["unresolved_fields"]


# ── C5 boolean ──
def test_C4_38_any_true():
    works = [_w(id="w1", has_truck_loading_unloading=None), _w(id="w2", has_truck_loading_unloading=True)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["has_truck_loading_unloading"] is True


def test_C4_39_all_false():
    works = [_w(id="w1", has_manual_heavy_handling=False), _w(id="w2", has_manual_heavy_handling=False)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["has_manual_heavy_handling"] is False


def test_C4_40_false_null_mix_unresolved():
    works = [_w(id="w1", has_truck_loading_unloading=False), _w(id="w2", has_truck_loading_unloading=None)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["has_truck_loading_unloading"] is None
    assert "has_truck_loading_unloading" in r["unresolved_fields"]


def test_C4_41_null_only_unresolved():
    works = [_w(id="w1", has_truck_loading_unloading=None)]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["has_truck_loading_unloading"] is None
    assert "has_truck_loading_unloading" in r["unresolved_fields"]


def test_C4_42_zero_work_null():
    r, _ = _asm(sites=[_site()], works=[])
    assert r["values"]["has_truck_loading_unloading"] is None
    assert "has_truck_loading_unloading" not in r["unresolved_fields"]


# ── E15 ──
def test_C4_43_44_e15_count_and_nonnull_zero():
    assert len(E15_FIELDS) == 15
    r, _ = _asm(sites=[_site()])
    non_null = [f for f in E15_FIELDS if r["values"][f] is not None]
    assert non_null == []
    for f in E15_FIELDS:
        assert f in r["unresolved_fields"]


def test_C4_45_special_work_type_derive_zero():
    # special_work_type 가 있어도 has_excavation 등 파생 0
    works = [_w(id="w1", special_work_type="굴착"), _w(id="w2", special_work_type="밀폐공간")]
    r, _ = _asm(sites=[_site()], works=works)
    assert r["values"]["has_excavation"] is None
    assert r["values"]["has_confined_space"] is None


def test_C4_46_47_48_no_factories_equipment_material():
    # FakeSB.table() raises on forbidden tables → any such access fails the run.
    r, sb = _asm(sites=[_site()])
    assert "factories" not in sb.reads
    assert "equipment_assets" not in sb.reads
    assert "factory_materials" not in sb.reads


# ── mutation / read-set ──
def test_C4_49_db_write_zero():
    # FakeSB write paths raise; a clean run proves no write attempted.
    r, _ = _asm(sites=[_site()], subs=[{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": 1, "has_safety_manager": True}])
    assert r["sector"] == "CONSTRUCTION"


def test_C4_50_51_52_read_set_exact_4():
    r, sb = _asm(
        sites=[_site()],
        processes=[{"id": "p1", "site_id": SID, "is_active": True, "process_name": "x"}],
        works=[_w(id="w1", process_id="p1", hazard_codes="추락")],
        subs=[{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": 1, "has_safety_manager": True}],
    )
    assert set(sb.reads) == ALLOWED_TABLES
    assert "factories" not in sb.reads
    assert "diagnosis_input_fields" not in sb.reads


def test_contract_envelope():
    r, _ = _asm(sites=[_site()])
    assert r["contract_version"] == "MKT_CST_PAID_CONTRACT_V1"
    assert r["sector"] == "CONSTRUCTION"
    assert r["site_id"] == SID
    assert r["unresolved_fields"] == sorted(set(r["unresolved_fields"]))  # sorted+dedupe


# ── STEP4-PATCH-1: required row completeness ──
def test_C4_P1_01_sub_company_name_null():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": None, "work_type": "철근", "worker_count": 3, "has_safety_manager": True}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert "subcontractor" in r["unresolved_fields"]
    assert r["values"]["has_subcontractor"] is True and r["values"]["subcontractor_count"] == 1


def test_C4_P1_02_sub_company_name_blank():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "   ", "work_type": "철근", "worker_count": 3, "has_safety_manager": True}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert "subcontractor" in r["unresolved_fields"]


def test_C4_P1_03_sub_worker_count_null():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "철근", "worker_count": None, "has_safety_manager": False}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert "subcontractor" in r["unresolved_fields"]


def test_C4_P1_04_sub_worker_count_zero_valid():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "철근", "worker_count": 0, "has_safety_manager": None}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is not None
    assert r["values"]["subcontractor"][0]["worker_count"] == 0
    assert r["values"]["subcontractor"][0]["safety_manager"] == "모름"
    assert "subcontractor" not in r["unresolved_fields"]


def test_C4_P1_05_process_name_null():
    procs = [{"id": "p1", "site_id": SID, "is_active": True, "process_name": None}]
    r, _ = _asm(sites=[_site()], processes=procs)
    assert r["values"]["process_list"] is None
    assert "process_list" in r["unresolved_fields"]


def test_C4_P1_06_process_name_blank():
    procs = [{"id": "p1", "site_id": SID, "is_active": True, "process_name": "  "}]
    r, _ = _asm(sites=[_site()], processes=procs)
    assert r["values"]["process_list"] is None
    assert "process_list" in r["unresolved_fields"]


def test_C4_P1_07_one_bad_process_among_valid():
    procs = [
        {"id": "p1", "site_id": SID, "is_active": True, "process_name": "터파기"},
        {"id": "p2", "site_id": SID, "is_active": True, "process_name": None},
    ]
    r, _ = _asm(sites=[_site()], processes=procs)
    assert r["values"]["process_list"] is None  # whole field unresolved, not silently dropped
    assert "process_list" in r["unresolved_fields"]


def test_C4_P1_08_denominator_regression():
    r, _ = _asm(sites=[_site()])
    assert len(r["values"]) == 27 and list(r["values"].keys()) == TARGET_FIELDS


def test_C4_P1_09_e15_nonnull_zero():
    r, _ = _asm(sites=[_site()])
    assert [f for f in E15_FIELDS if r["values"][f] is not None] == []


def test_C4_P1_10_db_write_zero():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": 1, "has_safety_manager": True}]
    r, sb = _asm(sites=[_site()], subs=subs)
    assert set(sb.reads) <= ALLOWED_TABLES and r["sector"] == "CONSTRUCTION"


# ── STEP4-PATCH-2: subcontractor unresolved provenance accuracy ──
_WORK_TYPE_ONLY_FALSE = "subcontractors(work_type 결측 active row)"


def test_C4_P2_01_company_name_null_no_worktype_only_reason():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": None, "work_type": "철근", "worker_count": 3, "has_safety_manager": True}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert r["provenance"]["subcontractor"]["mode"] == "UNRESOLVED"
    assert r["provenance"]["subcontractor"]["source"] != _WORK_TYPE_ONLY_FALSE


def test_C4_P2_02_worker_count_null_no_worktype_only_reason():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "철근", "worker_count": None, "has_safety_manager": False}]
    r, _ = _asm(sites=[_site()], subs=subs)
    assert r["values"]["subcontractor"] is None
    assert r["provenance"]["subcontractor"]["source"] != _WORK_TYPE_ONLY_FALSE


def test_C4_P2_03_generic_required_field_reason():
    # 실패 원인 세 종류 모두 동일한 정확 포괄 provenance
    for subs in (
        [{"id": "s1", "site_id": SID, "is_active": True, "company_name": None, "work_type": "a", "worker_count": 1, "has_safety_manager": True}],
        [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": None, "worker_count": 1, "has_safety_manager": True}],
        [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": None, "has_safety_manager": True}],
    ):
        r, _ = _asm(sites=[_site()], subs=subs)
        src = r["provenance"]["subcontractor"]["source"]
        assert "required" in src and "결측" in src
        assert src != _WORK_TYPE_ONLY_FALSE


def test_C4_P2_04_denominator_regression():
    r, _ = _asm(sites=[_site()])
    assert len(r["values"]) == 27 and list(r["values"].keys()) == TARGET_FIELDS


def test_C4_P2_05_db_write_zero():
    subs = [{"id": "s1", "site_id": SID, "is_active": True, "company_name": "A", "work_type": "a", "worker_count": 1, "has_safety_manager": True}]
    r, sb = _asm(sites=[_site()], subs=subs)
    assert set(sb.reads) <= ALLOWED_TABLES and r["sector"] == "CONSTRUCTION"
