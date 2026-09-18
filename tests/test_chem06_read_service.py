"""WO-CHEM-06 MSDS canonical read service tests.

MemoryMsdsReadStore-only. No live Supabase. No DB. No public router.
Verifies §17 items 1..15.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.kosha_msds import read


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _current_row(
    chem_id: str,
    *,
    id: str,
    content_id: str,
    chemical_name_ko: str | None = None,
    chemical_name_en: str | None = None,
    cas_no: str | None = None,
    ke_no: str | None = None,
    en_no: str | None = None,
    un_no: str | None = None,
    identity_status: str = "READY",
    snapshot_id: str = "snap-1",
) -> dict:
    return {
        "id": id,
        "content_id": content_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": identity_status,
        "chemical_name_ko": chemical_name_ko,
        "chemical_name_en": chemical_name_en,
        "cas_no": cas_no,
        "ke_no": ke_no,
        "en_no": en_no,
        "un_no": un_no,
        "source_content_hash": "sha-" + chem_id,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": snapshot_id,
    }


def _section_row(
    chemical_id: str,
    section_no: int,
    *,
    items=(),
    section_hash: str | None = None,
    result_code: str = "00",
    result_message: str = "NORMAL SERVICE.",
    fetched_at: str = "2026-09-18T00:00:00Z",
) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": list(items),
        "section_hash": section_hash or f"secH-{chemical_id}-{section_no}",
        "result_code": result_code,
        "result_message": result_message,
        "fetched_at": fetched_at,
    }


def _store_with_two_currents() -> read.MemoryMsdsReadStore:
    current_rows = [
        _current_row("001008", id="uu-001008", content_id="CHEM:001008-uu",
                     chemical_name_ko="벤젠", chemical_name_en="Benzene",
                     cas_no="71-43-2"),
        _current_row("097377", id="uu-097377", content_id="CHEM:097377-uu",
                     chemical_name_ko="에탄올", chemical_name_en="Ethanol",
                     cas_no="64-17-5"),
    ]
    chemicals = [
        {"id": "uu-001008", "last_date": "2024-01-15"},
        {"id": "uu-097377", "last_date": "2024-05-10"},
    ]
    sections = []
    for chem_id_uuid in ("uu-001008", "uu-097377"):
        for n in range(1, 17):
            sections.append(_section_row(chem_id_uuid, n, items=[{
                "msdsItemCode": f"C{n:02d}",
                "msdsItemNameKor": f"항목{n}",
                "itemDetail": "내용",
                "ordrIdx": "1",
                "lev": "1",
            }]))
    return read.MemoryMsdsReadStore(
        current_rows=current_rows,
        chemicals=chemicals,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# §17 items 1..15
# ---------------------------------------------------------------------------


def test_01_get_by_chem_id_current_record_pass():
    store = _store_with_two_currents()
    out = read.get_by_chem_id("001008", store=store)
    assert out is not None
    assert out["chem_id"] == "001008"
    assert out["content_id"] == "CHEM:001008-uu"
    assert out["chemical_name_ko"] == "벤젠"
    assert out["chemical_name_en"] == "Benzene"
    assert out["cas_no"] == "71-43-2"
    assert out["last_date"] == "2024-01-15"
    assert out["identity_status"] == "READY"
    assert out["provenance"]["source_id"] == "KOSHA_MSDS"
    assert out["provenance"]["source_key"] == "001008"
    assert out["provenance"]["snapshot_id"] == "snap-1"
    assert len(out["sections"]) == 16
    assert {s["section_no"] for s in out["sections"]} == set(range(1, 17))


def test_02_non_current_chemical_not_found():
    store = _store_with_two_currents()
    # A chemId that is NOT in the current view — even though sections could
    # exist for it elsewhere, the service must return None.
    assert read.get_by_chem_id("999999", store=store) is None


def test_03_list_current_empty_returns_empty_envelope():
    empty = read.MemoryMsdsReadStore()
    out = read.list_current(store=empty)
    assert out == {"items": [], "total": 0, "limit": read.DEFAULT_LIMIT, "offset": 0}


def test_04_list_current_deterministic_chem_id_order():
    # Seed rows in reverse chem_id order; assert result is sorted ASC.
    rows = [
        _current_row("097377", id="uu-097377", content_id="CHEM:097377-uu"),
        _current_row("001008", id="uu-001008", content_id="CHEM:001008-uu"),
        _current_row("012345", id="uu-012345", content_id="CHEM:012345-uu"),
    ]
    store = read.MemoryMsdsReadStore(current_rows=rows)
    out = read.list_current(store=store)
    assert [item["chem_id"] for item in out["items"]] == ["001008", "012345", "097377"]
    assert out["total"] == 3


def test_05_pagination_limit_offset():
    rows = [
        _current_row(f"00{i:04d}", id=f"uu-{i}", content_id=f"CHEM:uu-{i}")
        for i in range(1, 11)
    ]
    store = read.MemoryMsdsReadStore(current_rows=rows)
    page1 = read.list_current(store=store, limit=3, offset=0)
    page2 = read.list_current(store=store, limit=3, offset=3)
    page3 = read.list_current(store=store, limit=3, offset=6)
    assert [i["chem_id"] for i in page1["items"]] == ["000001", "000002", "000003"]
    assert [i["chem_id"] for i in page2["items"]] == ["000004", "000005", "000006"]
    assert [i["chem_id"] for i in page3["items"]] == ["000007", "000008", "000009"]
    # Bad inputs get clamped, not accepted.
    weird = read.list_current(store=store, limit=-5, offset=-99)
    assert weird["limit"] == read.DEFAULT_LIMIT
    assert weird["offset"] == 0
    # Absurdly large limit is capped, not honored.
    huge = read.list_current(store=store, limit=10_000, offset=0)
    assert huge["limit"] == read.MAX_LIMIT


def test_06_exact_chem_id_search():
    store = _store_with_two_currents()
    out = read.search(store=store, chem_id="097377")
    assert out["total"] == 1
    assert out["items"][0]["chem_id"] == "097377"


def test_07_exact_cas_search():
    store = _store_with_two_currents()
    out = read.search(store=store, cas_no="64-17-5")
    assert out["total"] == 1
    assert out["items"][0]["chem_id"] == "097377"


def test_08_korean_name_partial_search():
    store = _store_with_two_currents()
    out = read.search(store=store, name_ko="벤")
    assert out["total"] == 1
    assert out["items"][0]["chem_id"] == "001008"
    # Case-insensitive against the Korean field is a no-op but must not error.
    out_upper = read.search(store=store, name_ko="벤")
    assert out_upper["items"][0]["chem_id"] == "001008"


def test_09_english_name_partial_search_case_insensitive():
    store = _store_with_two_currents()
    lower = read.search(store=store, name_en="benz")
    upper = read.search(store=store, name_en="BENZ")
    assert lower["total"] == 1
    assert upper["total"] == 1
    assert lower["items"][0]["chem_id"] == "001008"
    assert upper["items"][0]["chem_id"] == "001008"


def test_10_section_1_to_16_allowed():
    store = _store_with_two_currents()
    for n in range(1, 17):
        out = read.get_section("001008", n, store=store)
        assert out is not None
        assert out["section_no"] == n
        assert out["result_code"] == "00"


def test_11_section_out_of_range_rejected():
    store = _store_with_two_currents()
    for bad in (0, 17, -1, 100):
        with pytest.raises(read.SectionNoOutOfRange):
            read.get_section("001008", bad, store=store)


def test_12_non_current_chemical_section_hidden():
    """Even if the store's sections table contains a row for a chemical
    that is NOT in the current view, the service must NOT return it."""
    # Seed a chemical whose sections exist but whose current-view membership does not.
    current_rows = [
        _current_row("001008", id="uu-001008", content_id="CHEM:001008-uu"),
    ]
    sections = [
        _section_row("uu-001008", 5),          # current -> visible
        _section_row("uu-999999", 5),          # non-current -> must be hidden
    ]
    store = read.MemoryMsdsReadStore(
        current_rows=current_rows, sections=sections
    )
    assert read.get_section("001008", 5, store=store) is not None
    assert read.get_section("999999", 5, store=store) is None


def test_13_section_payload_returned_correctly():
    store = _store_with_two_currents()
    out = read.get_section("001008", 3, store=store)
    assert out is not None
    assert out["section_no"] == 3
    assert isinstance(out["payload_json"], list)
    assert out["payload_json"][0]["msdsItemCode"] == "C03"
    assert out["section_hash"] == "secH-uu-001008-3"
    assert out["fetched_at"] == "2026-09-18T00:00:00Z"


def test_14_no_kosha_safety_materials_dependency():
    """The read service module must not import from the safety-materials domain."""
    source = Path(read.__file__).read_text(encoding="utf-8")
    assert "kosha_safety_materials" not in source, \
        "services/kosha_msds/read.py must not import from kosha_safety_materials"


def test_15_no_db_mutation_methods_on_stores():
    """Neither store exposes insert / update / delete / upsert / rpc / execute-sql methods."""
    forbidden = ("insert", "update", "delete", "upsert", "rpc", "execute_sql")
    for cls in (read.MemoryMsdsReadStore, read.SupabaseMsdsReadStore):
        names = {n for n in dir(cls) if not n.startswith("_")}
        for f in forbidden:
            assert f not in names, f"{cls.__name__} exposes {f}() — expected read-only"


# ---------------------------------------------------------------------------
# Extra: contract shape sanity
# ---------------------------------------------------------------------------


def test_16_list_omits_sections_get_by_id_includes_sections():
    """list_current returns the identity envelope only. get_by_chem_id returns sections."""
    store = _store_with_two_currents()
    listed = read.list_current(store=store)
    for item in listed["items"]:
        assert "sections" not in item
    detailed = read.get_by_chem_id("001008", store=store)
    assert detailed and "sections" in detailed
    detailed_no_secs = read.get_by_chem_id("001008", store=store, include_sections=False)
    assert detailed_no_secs and "sections" not in detailed_no_secs


def test_17_provenance_included_but_snapshot_only_from_view():
    """Provenance in the contract is the view's own columns — no internal
    snapshot state, no raw DB PK exposure beyond content_id."""
    store = _store_with_two_currents()
    out = read.get_by_chem_id("001008", store=store)
    prov = out["provenance"]
    assert set(prov.keys()) == {
        "source_id", "source_key", "source_content_hash",
        "source_dataset_url", "snapshot_id",
    }
    # id (raw uuid PK) must not leak into the contract.
    assert "id" not in out
    assert "id" not in prov
