"""WO-CHEM-07 dormant public MSDS router tests.

Uses FastAPI TestClient with an isolated app that mounts ONLY the
kosha_public_msds router. Neither router_registry nor the production
app is touched. The router's own get_store() is monkey-patched to a
MemoryMsdsReadStore so no Supabase network I/O happens.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import kosha_public_msds as router_mod
from services.kosha_msds import read


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
) -> dict:
    return {
        "id": id,
        "content_id": content_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": chemical_name_ko,
        "chemical_name_en": chemical_name_en,
        "cas_no": cas_no,
        "ke_no": ke_no,
        "en_no": en_no,
        "un_no": un_no,
        "source_content_hash": "sha-" + chem_id,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": "snap-1",
    }


def _section_row(chemical_id: str, section_no: int) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": [{
            "msdsItemCode": f"C{section_no:02d}",
            "msdsItemNameKor": f"항목{section_no}",
            "itemDetail": "내용",
            "ordrIdx": "1",
            "lev": "1",
        }],
        "section_hash": f"secH-{chemical_id}-{section_no}",
        "result_code": "00",
        "result_message": "NORMAL SERVICE.",
        "fetched_at": "2026-09-18T00:00:00Z",
    }


def _make_store_two_currents() -> read.MemoryMsdsReadStore:
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
    for uid in ("uu-001008", "uu-097377"):
        for n in range(1, 17):
            sections.append(_section_row(uid, n))
    return read.MemoryMsdsReadStore(
        current_rows=current_rows,
        chemicals=chemicals,
        sections=sections,
    )


@pytest.fixture
def client(monkeypatch):
    store = _make_store_two_currents()
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_empty(monkeypatch):
    store = read.MemoryMsdsReadStore()  # empty current view
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# §24 items 1..18
# ---------------------------------------------------------------------------


def test_01_get_list_200(client):
    r = client.get("/public/kosha/msds")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [i["chem_id"] for i in body["items"]] == ["001008", "097377"]


def test_02_empty_list_returns_empty(client_empty):
    r = client_empty.get("/public/kosha/msds")
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "total": 0, "limit": read.DEFAULT_LIMIT, "offset": 0}


def test_03_list_pagination_passthrough(client):
    r = client.get("/public/kosha/msds?limit=1&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["total"] == 2
    assert [i["chem_id"] for i in body["items"]] == ["097377"]


def test_04_chem_id_exact_filter(client):
    r = client.get("/public/kosha/msds?chem_id=001008")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "001008"


def test_05_cas_filter(client):
    r = client.get("/public/kosha/msds?cas_no=64-17-5")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "097377"


def test_06_korean_name_filter(client):
    r = client.get("/public/kosha/msds?name_ko=벤")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "001008"


def test_07_english_name_filter(client):
    r = client.get("/public/kosha/msds?name_en=Ethanol")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "097377"


def test_08_detail_found_200(client):
    r = client.get("/public/kosha/msds/001008")
    assert r.status_code == 200
    body = r.json()
    assert body["chem_id"] == "001008"
    assert body["content_id"] == "CHEM:001008-uu"
    assert body["last_date"] == "2024-01-15"


def test_09_detail_non_current_404(client):
    r = client.get("/public/kosha/msds/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "MSDS_CHEMICAL_NOT_FOUND"


def test_10_detail_includes_16_sections(client):
    r = client.get("/public/kosha/msds/001008")
    assert r.status_code == 200
    sections = r.json()["sections"]
    assert len(sections) == 16
    assert {s["section_no"] for s in sections} == set(range(1, 17))


def test_11_section_found_200(client):
    r = client.get("/public/kosha/msds/001008/sections/3")
    assert r.status_code == 200
    body = r.json()
    assert body["section_no"] == 3
    assert body["result_code"] == "00"
    assert body["section_hash"] == "secH-uu-001008-3"


def test_12_section_not_found_returns_404_for_non_current(client):
    # 999999 is not in current view; section fetch must 404 (not 200).
    r = client.get("/public/kosha/msds/999999/sections/3")
    assert r.status_code == 404
    assert r.json()["detail"] == "MSDS_SECTION_NOT_FOUND"


def test_13_section_zero_rejected(client):
    r = client.get("/public/kosha/msds/001008/sections/0")
    # FastAPI Path(ge=1, le=16) returns 422 with a validation error.
    assert r.status_code == 422


def test_14_section_17_rejected(client):
    r = client.get("/public/kosha/msds/001008/sections/17")
    assert r.status_code == 422


def test_15_internal_pk_not_exposed(client):
    r_detail = client.get("/public/kosha/msds/001008")
    r_list = client.get("/public/kosha/msds")
    body_detail = r_detail.json()
    body_list = r_list.json()
    # No 'id' key at the top level of the detail envelope.
    assert "id" not in body_detail
    # No 'id' key inside provenance.
    assert "id" not in body_detail["provenance"]
    # No section-row 'id' leaked.
    for sec in body_detail["sections"]:
        assert "id" not in sec
        assert "chemical_id" not in sec
    # Same for list items.
    for item in body_list["items"]:
        assert "id" not in item
        assert "id" not in item["provenance"]


def test_16_no_kosha_safety_materials_dependency():
    """The router must not import from services/kosha_safety_materials."""
    src = Path(router_mod.__file__).read_text(encoding="utf-8")
    assert "kosha_safety_materials" not in src


def test_17_router_delegates_to_chem06_service_no_direct_bypass():
    """The router must not issue direct DB queries; only CHEM-06 service calls."""
    src = Path(router_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        ".table(",       # Supabase-style direct table access
        ".insert(",
        ".update(",
        ".delete(",
        ".upsert(",
        ".rpc(",
        "execute_sql",
        "SELECT ",       # Raw SQL
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    )
    for token in forbidden:
        assert token not in src, f"router should not contain {token!r}"


def test_18_router_not_registered_in_public_registry():
    """WO §16: this router MUST NOT be registered in router_registry."""
    registry_path = Path(__file__).resolve().parent.parent / "router_registry" / "public.py"
    src = registry_path.read_text(encoding="utf-8")
    assert "kosha_public_msds" not in src, (
        "routers/kosha_public_msds.py must NOT be registered under "
        "WO-CHEM-07-MSDS-PUBLIC-ROUTER-001 (dormant router)"
    )


# ---------------------------------------------------------------------------
# Extra: OpenAPI shape sanity
# ---------------------------------------------------------------------------


def test_19_openapi_prefix_is_public_kosha_msds(client):
    """The router registers under /public/kosha/msds (not the /materials domain)."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/public/kosha/msds" in paths
    assert "/public/kosha/msds/{chem_id}" in paths
    assert "/public/kosha/msds/{chem_id}/sections/{section_no}" in paths
    # The safety-materials domain paths must NOT leak into this isolated app.
    assert "/public/kosha/materials" not in paths


def test_20_router_isolated_when_not_registered():
    """Import parity: importing routers.kosha_public_msds does not
    register it into any global app. router_registry/public.py drives
    what the production app mounts (verified separately by test_18)."""
    import routers.kosha_public_msds as m
    # The module exposes a router object but does not run any startup.
    assert hasattr(m, "router")
    # And that router carries the expected prefix.
    assert m.router.prefix == "/public/kosha/msds"
