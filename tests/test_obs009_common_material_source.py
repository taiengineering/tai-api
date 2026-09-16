"""WO-E2E-OBS009-COMMON-MATERIAL-SOURCE-IMPLEMENT-001.

M1–M12. Family-specific engines are forbidden.
Common Work Source / OBS007 / OBS008 / OBS009-A / welding / KSIC remain untouched.
"""
from __future__ import annotations

from types import SimpleNamespace

from services.material_source.builder import build_from_snapshots, write_manifests
from services.material_source.projector import (
    WORK_FAMILY_FACTS,
    project_factory_material_rows,
    project_material_row,
)
from services.material_source.registry import ALLOWED_CLASSIFICATION_CODES, registry_public
from services.material_source.store import (
    MaterialSourceLoadError,
    MaterialSourceValidationError,
    catalog_index,
    load_factory_material_rows_optional,
    lookup_master_exact,
    validate_factory_payload,
)


MANAGED = "MANAGED_HAZARDOUS_SUBSTANCE"
PERMIT = "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE"
SPECIAL = "SPECIAL_MANAGEMENT_SUBSTANCE"

BENZENE_KEY = "ISHL-RULE-APP12-G1-I046"
VINYL_KEY = "ISHL-ENF-ART88-0088001-P-H7"
NICKEL_KEY = "ISHL-RULE-APP12-G2-I003"
STODDARD_KEY = "ISHL-RULE-APP12-G1-I060"


def _row(**kwargs):
    base = {
        "material_name": "x",
        "material_category_code": None,
        "handling_mode_codes": None,
        "material_master_key": None,
        "is_active": True,
    }
    base.update(kwargs)
    return base


def _codes(items):
    return [i["classification_code"] for i in items]


# ── M1: broad hazardous forbidden ─────────────────────────────────────────
def test_M1_has_hazardous_material_does_not_classify():
    projected = project_factory_material_rows(
        [_row(material_name="ignored", has_hazardous_material=True)]
    )
    assert projected["material_classifications"] == []


# ── M2: narrow chemical field isolation ───────────────────────────────────
def test_M2_has_chemical_substance_does_not_classify():
    projected = project_factory_material_rows(
        [_row(material_name="ignored", has_chemical_substance=True)]
    )
    assert projected["material_classifications"] == []
    codes = {c["code"] for c in registry_public()["classifications"]}
    assert "has_chemical_substance" not in codes


# ── M3: managed exact ─────────────────────────────────────────────────────
def test_M3_managed_exact_does_not_invent_siblings():
    items = project_material_row(_row(material_master_key=STODDARD_KEY))
    assert _codes(items) == [MANAGED]
    assert PERMIT not in _codes(items)
    assert SPECIAL not in _codes(items)


# ── M4: permit exact ──────────────────────────────────────────────────────
def test_M4_permit_exact_only():
    items = project_material_row(_row(material_master_key=VINYL_KEY))
    assert _codes(items) == [PERMIT]
    assert MANAGED not in _codes(items)
    assert SPECIAL not in _codes(items)


# ── M5: special exact ─────────────────────────────────────────────────────
def test_M5_special_exact_only_with_managed_from_same_source():
    items = project_material_row(_row(material_master_key=BENZENE_KEY))
    assert set(_codes(items)) == {MANAGED, SPECIAL}
    assert PERMIT not in _codes(items)


# ── M6: multi-class ───────────────────────────────────────────────────────
def test_M6_multi_class_preserves_both():
    items = project_material_row(_row(material_master_key=BENZENE_KEY))
    assert len(items) == 2
    assert {i["classification_code"] for i in items} == {MANAGED, SPECIAL}


# ── M7: free-text only ────────────────────────────────────────────────────
def test_M7_free_text_without_master_key_is_absent():
    items = project_material_row(
        _row(material_name="벤젠", material_master_key=None)
    )
    assert items == []
    assert project_material_row(_row(material_name="벤젠", material_master_key="")) == []


# ── M8: inactive ──────────────────────────────────────────────────────────
def test_M8_inactive_emits_nothing():
    assert project_material_row(
        _row(material_master_key=BENZENE_KEY, is_active=False)
    ) == []


# ── M9: missing != false ──────────────────────────────────────────────────
def test_M9_missing_is_absent_not_false():
    projected = project_factory_material_rows([])
    assert projected == {"material_classifications": []}
    assert projected.get(MANAGED) is not False
    assert "has_chemical_substance" not in projected
    assert "has_hazardous_material" not in projected


# ── M10: family isolation ─────────────────────────────────────────────────
def test_M10_material_source_does_not_emit_work_facts():
    projected = project_factory_material_rows(
        [_row(material_master_key=BENZENE_KEY)]
    )
    for name in WORK_FAMILY_FACTS:
        assert name not in projected
        assert all(name not in item for item in projected["material_classifications"])
    assert "painting" not in projected
    assert "maintenance" not in projected
    assert "electrical" not in projected
    assert "confined-space" not in projected
    assert "welding" not in projected


# ── M11: DB failure fail-closed ───────────────────────────────────────────
class _OkQuery:
    def __init__(self, data, error=None):
        self._data = data
        self._error = error

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data, error=self._error)


class _BoomQuery:
    def table(self, name):
        raise RuntimeError("relation factory_materials does not exist")


def test_M11_query_failure_is_not_empty_source():
    try:
        load_factory_material_rows_optional(_BoomQuery(), "F1")
    except MaterialSourceLoadError as exc:
        assert exc.code == "MATERIAL_SOURCE_UNAVAILABLE"
        return
    raise AssertionError("query failure must not become []")


def test_M11_successful_empty_list_is_not_error():
    assert load_factory_material_rows_optional(_OkQuery([]), "F1") == []


def test_M11_non_list_payload_is_load_error():
    try:
        load_factory_material_rows_optional(_OkQuery({"rows": []}), "F1")
    except MaterialSourceLoadError:
        return
    raise AssertionError("non-list payload must not become []")


def test_M11_query_error_field_is_load_error():
    try:
        load_factory_material_rows_optional(_OkQuery([], error="permission denied"), "F1")
    except MaterialSourceLoadError:
        return
    raise AssertionError("res.error must not become []")


def test_M11_missing_factory_id_skips_query():
    class MustNotQuery:
        def table(self, name):
            raise AssertionError("no query without factory_id")

    assert load_factory_material_rows_optional(MustNotQuery(), None) == []
    assert load_factory_material_rows_optional(MustNotQuery(), "") == []


# ── M12: deterministic master ─────────────────────────────────────────────
def test_M12_same_authority_input_same_ids_and_checksum():
    a = build_from_snapshots()
    b = build_from_snapshots()
    assert [row["material_key"] for row in a["materials"]] == [
        row["material_key"] for row in b["materials"]
    ]
    assert a["classifications"] == b["classifications"]
    assert a["MATERIAL_MASTER_HASH"] == b["MATERIAL_MASTER_HASH"]
    assert a["CLASSIFICATION_HASH"] == b["CLASSIFICATION_HASH"]
    assert a["CATALOG_HASH"] == b["CATALOG_HASH"]
    written = write_manifests()
    assert written["CATALOG_HASH"] == a["CATALOG_HASH"]


def test_conditional_special_is_not_special_classification():
    items = project_material_row(_row(material_master_key=NICKEL_KEY))
    assert _codes(items) == [MANAGED]
    stoddard = project_material_row(_row(material_master_key=STODDARD_KEY))
    assert SPECIAL not in _codes(stoddard)


def test_registry_is_common_only():
    data = registry_public()
    codes = {item["code"] for item in data["classifications"]}
    assert codes == ALLOWED_CLASSIFICATION_CODES
    assert all(item["user_editable"] is False for item in data["classifications"])


def test_validate_rejects_unknown_master_key():
    try:
        validate_factory_payload(
            {"material_name": "벤젠", "material_master_key": "BENZENE"}
        )
    except MaterialSourceValidationError:
        return
    raise AssertionError("unknown material_master_key must be rejected")


def test_validate_accepts_null_master_key_free_text():
    row = validate_factory_payload(
        {"material_name": "벤젠", "material_master_key": None}
    )
    assert row["material_master_key"] is None
    assert row["material_name"] == "벤젠"


def test_exact_lookup_is_not_fuzzy():
    assert lookup_master_exact("벤젠X") == []
    hits = lookup_master_exact(BENZENE_KEY)
    assert len(hits) == 1
    assert hits[0]["material_key"] == BENZENE_KEY
    by_name = lookup_master_exact(hits[0]["display_name"])
    assert [row["material_key"] for row in by_name] == [BENZENE_KEY]


def test_material_key_is_not_material_name():
    idx = catalog_index()
    for row in idx["materials"]:
        assert row["material_key"] != row["display_name"]
        assert row["material_key"].startswith("ISHL-")


def test_authority_counts_match_named_source_rows():
    counts = catalog_index()["counts"]
    assert counts["MANAGED_COUNT"] == 181
    assert counts["PERMIT_REQUIRED_COUNT"] == 12
    assert counts["SPECIAL_MANAGEMENT_COUNT"] == 38
    assert counts["CONDITIONAL_SPECIAL_COUNT"] == 6
    assert counts["SKIPPED_COUNT"] == 7
    assert counts["MATERIAL_COUNT"] == 193


def test_sql_file_has_no_insert_and_no_family_tables():
    from pathlib import Path

    sql = Path("docs/sql/20260916_common_material_source.sql").read_text()
    lowered = sql.lower()
    assert "insert into" not in lowered
    assert "managed_hazardous" not in lowered or "managed_hazardous_substance" in lowered
    assert "create table if not exists public.material_legal_master" in lowered
    assert "create table if not exists public.material_legal_classifications" in lowered
    assert "material_master_key" in lowered
    assert "managed_materials" not in lowered
    assert "permit_materials" not in lowered
    assert "special_management_materials" not in lowered


def test_leg_runtime_not_extended_by_this_package():
    from clients.leg_runtime_client import _LEG_INPUT_FIELDS

    assert "MANAGED_HAZARDOUS_SUBSTANCE" not in _LEG_INPUT_FIELDS
    assert "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE" not in _LEG_INPUT_FIELDS
    assert "SPECIAL_MANAGEMENT_SUBSTANCE" not in _LEG_INPUT_FIELDS
    from pathlib import Path

    for rel in (
        "services/work_source/projector.py",
        "services/work_source/store.py",
        "clients/leg_runtime_client.py",
    ):
        text = Path(rel).read_text()
        assert "material_legal_master" not in text
        assert "MANAGED_HAZARDOUS_SUBSTANCE" not in text


def test_common_api_has_no_family_endpoints():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.material_source as MS
    from routers.auth import get_current_user

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    app.include_router(MS.router)
    client = TestClient(app)
    assert client.get("/material-source/registry").status_code == 200
    res = client.get("/material-source/materials", params={"q": BENZENE_KEY})
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["material_key"] == BENZENE_KEY
    assert {c["classification_code"] for c in body["data"]["items"][0]["classifications"]} == {
        MANAGED,
        SPECIAL,
    }
    assert client.get("/managed-hazardous-materials").status_code == 404
    assert client.get("/permit-materials").status_code == 404
    assert client.get("/special-management-materials").status_code == 404
