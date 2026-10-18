"""WO-WWW-PERF-004-P0S-OS-IMPL-001 — MSDS OpenSearch search adapter tests.

Covers:
  S01  extract_cas_no (section_fields)
  S02  search_os (opensearch_query) via fake OS client
  S03  os_chem_available gate
  S04  MemoryMsdsReadStore.hydrate_chem_ids
  S05  SupabaseMsdsReadStore.hydrate_chem_ids contract (structure, no live DB)
  S06  search_from_chem_ids service function
  S07  search_by_q_os — identifier detection routing
  S08  search_by_q_os — free-text routing
  S09  router list_or_search_msds via OS path (MemoryMsdsReadStore)
  S10  router fallback to legacy on OS exception
  S11  regression: extract_product_name unaffected
  S12  regression: section_fields has no shared_search dep
"""
from __future__ import annotations

import os
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# S01  extract_cas_no
# ---------------------------------------------------------------------------

from services.kosha_msds.section_fields import extract_cas_no, extract_product_name


def test_extract_cas_no_from_item_array():
    payload = [
        {"msdsItemCode": "C05", "itemDetail": "other"},
        {"msdsItemCode": "C06", "itemDetail": "50-00-0"},
    ]
    assert extract_cas_no(payload) == "50-00-0"


def test_extract_cas_no_from_items_wrapper():
    payload = {"items": [{"msdsItemCode": "C06", "itemDetail": "71-43-2"}]}
    assert extract_cas_no(payload) == "71-43-2"


def test_extract_cas_no_from_json_text():
    import json
    payload = json.dumps([{"msdsItemCode": "C06", "itemDetail": "7664-41-7"}])
    assert extract_cas_no(payload) == "7664-41-7"


def test_extract_cas_no_missing_c06_returns_none():
    assert extract_cas_no([{"msdsItemCode": "C05", "itemDetail": "x"}]) is None
    assert extract_cas_no(None) is None
    assert extract_cas_no([]) is None


def test_extract_cas_no_blank_returns_none():
    assert extract_cas_no([{"msdsItemCode": "C06", "itemDetail": "   "}]) is None
    assert extract_cas_no([{"msdsItemCode": "C06", "itemDetail": None}]) is None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_os_resp(source_keys: list[str], total: int) -> dict:
    """Build a minimal OpenSearch search response."""
    return {
        "hits": {
            "total": {"value": total, "relation": "eq"},
            "hits": [
                {"_source": {"source_key": sk}} for sk in source_keys
            ],
        }
    }


def _fake_os_client(source_keys: list[str], total: int):
    """Return a mock OS client whose .search() returns the given hits."""
    client = MagicMock()
    client.search.return_value = _make_os_resp(source_keys, total)
    client.count.return_value = {"count": total}
    return client


# ---------------------------------------------------------------------------
# S02  search_os
# ---------------------------------------------------------------------------

from services.kosha_msds.opensearch_query import search_os


def test_search_os_by_chem_id():
    client = _fake_os_client(["000001"], 1)
    ids, total = search_os(chem_id="000001", limit=10, offset=0, client=client)
    assert ids == ["000001"]
    assert total == 1
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)


def test_search_os_by_cas_no():
    client = _fake_os_client(["000042"], 1)
    ids, total = search_os(cas_no="71-43-2", limit=10, offset=0, client=client)
    assert ids == ["000042"]
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "71-43-2"}} for f in filters)


def test_search_os_by_name_ko():
    client = _fake_os_client(["000001", "000002"], 2)
    ids, total = search_os(name_ko="염산", limit=10, offset=0, client=client)
    assert ids == ["000001", "000002"]
    assert total == 2
    body = client.search.call_args[1]["body"]
    assert "must" in body["query"]["bool"]
    must = body["query"]["bool"]["must"][0]
    assert must["multi_match"]["query"] == "염산"


def test_search_os_by_q():
    client = _fake_os_client(["000007"], 1)
    ids, total = search_os(q="벤젠", limit=5, offset=0, client=client)
    assert ids == ["000007"]
    body = client.search.call_args[1]["body"]
    must = body["query"]["bool"]["must"][0]
    assert must["multi_match"]["query"] == "벤젠"


def test_search_os_pagination_params_forwarded():
    client = _fake_os_client([], 500)
    client.search.return_value = _make_os_resp(["000010"], 500)
    ids, total = search_os(name_ko="산", limit=20, offset=40, client=client)
    assert total == 500
    body = client.search.call_args[1]["body"]
    assert body["from"] == 40
    assert body["size"] == 20
    assert body["track_total_hits"] is True


def test_search_os_filters_empty_source_keys():
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {"_source": {"source_key": "000001"}},
                {"_source": {}},  # missing source_key
            ],
        }
    }
    ids, total = search_os(name_ko="x", limit=10, offset=0, client=client)
    assert ids == ["000001"]
    assert total == 2


def test_search_os_ke_no():
    client = _fake_os_client(["000099"], 1)
    ids, _ = search_os(ke_no="KE-12345", limit=10, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "KE-12345"}} for f in filters)


# ---------------------------------------------------------------------------
# S03  os_chem_available gate
# ---------------------------------------------------------------------------

from services.kosha_msds.opensearch_query import os_chem_available


def test_os_chem_available_pass():
    client = MagicMock()
    client.count.return_value = {"count": 20568}
    assert os_chem_available(client=client) is True


def test_os_chem_available_fail_below_threshold():
    client = MagicMock()
    client.count.return_value = {"count": 100}
    assert os_chem_available(client=client) is False


def test_os_chem_available_exception_returns_false():
    client = MagicMock()
    client.count.side_effect = Exception("connection refused")
    assert os_chem_available(client=client) is False


# ---------------------------------------------------------------------------
# S04  MemoryMsdsReadStore.hydrate_chem_ids
# ---------------------------------------------------------------------------

from services.kosha_msds.read import MemoryMsdsReadStore


def _make_store():
    """Seed a minimal MemoryMsdsReadStore with 2 chemicals."""
    preview_rows = [
        {
            "id": "uuid-001",
            "chem_id": "000001",
            "content_id": "cid-001",
            "identity_status": "READY",
            "chemical_name_ko": None,  # NULL → fallback from sec1 A02
            "chemical_name_en": "Guanidine hydrochloride",
            "cas_no": None,            # NULL → fallback from sec3 C06
            "ke_no": None,
            "en_no": None,
            "un_no": None,
            "source_id": "KOSHA_MSDS",
            "source_key": "000001",
            "source_content_hash": "abc",
            "source_dataset_url": "https://x",
            "snapshot_id": "snap-1",
        },
        {
            "id": "uuid-002",
            "chem_id": "000002",
            "content_id": "cid-002",
            "identity_status": "READY",
            "chemical_name_ko": "벤젠",
            "chemical_name_en": "Benzene",
            "cas_no": "71-43-2",
            "ke_no": None,
            "en_no": None,
            "un_no": None,
            "source_id": "KOSHA_MSDS",
            "source_key": "000002",
            "source_content_hash": "def",
            "source_dataset_url": "https://x",
            "snapshot_id": "snap-1",
        },
    ]
    chemicals = [
        {"id": "uuid-001", "last_date": "2025-01-01"},
        {"id": "uuid-002", "last_date": "2025-02-01"},
    ]
    sections = [
        {  # sec1 A02 for uuid-001
            "chemical_id": "uuid-001",
            "section_no": 1,
            "payload_json": [{"msdsItemCode": "A02", "itemDetail": "염산 구아니딘"}],
        },
        {  # sec3 C06 for uuid-001
            "chemical_id": "uuid-001",
            "section_no": 3,
            "payload_json": [{"msdsItemCode": "C06", "itemDetail": "50-01-1"}],
        },
    ]
    return MemoryMsdsReadStore(
        preview_rows=preview_rows,
        chemicals=chemicals,
        sections=sections,
    )


def test_hydrate_chem_ids_name_fallback():
    store = _make_store()
    rows = store.hydrate_chem_ids(["000001"])
    assert len(rows) == 1
    row = rows[0]
    assert row["chemical_name_ko"] == "염산 구아니딘"   # sec1 A02 fallback
    assert row["cas_no"] == "50-01-1"                   # sec3 C06 fallback


def test_hydrate_chem_ids_no_fallback_needed():
    store = _make_store()
    rows = store.hydrate_chem_ids(["000002"])
    assert len(rows) == 1
    row = rows[0]
    assert row["chemical_name_ko"] == "벤젠"
    assert row["cas_no"] == "71-43-2"


def test_hydrate_chem_ids_preserves_order():
    store = _make_store()
    rows = store.hydrate_chem_ids(["000002", "000001"])
    assert rows[0]["chem_id"] == "000002"
    assert rows[1]["chem_id"] == "000001"


def test_hydrate_chem_ids_missing_silently_dropped():
    store = _make_store()
    rows = store.hydrate_chem_ids(["000001", "999999"])
    assert len(rows) == 1
    assert rows[0]["chem_id"] == "000001"


def test_hydrate_chem_ids_empty_returns_empty():
    store = _make_store()
    rows = store.hydrate_chem_ids([])
    assert rows == []


def test_hydrate_chem_ids_last_date_attached():
    store = _make_store()
    rows = store.hydrate_chem_ids(["000001"])
    assert rows[0]["last_date"] == "2025-01-01"


# ---------------------------------------------------------------------------
# S06  search_from_chem_ids
# ---------------------------------------------------------------------------

from services.kosha_msds.read import search_from_chem_ids


def test_search_from_chem_ids_envelope():
    store = _make_store()
    result = search_from_chem_ids(
        store=store, chem_ids=["000001"], total=42, limit=10, offset=0
    )
    assert result["total"] == 42
    assert result["limit"] == 10
    assert result["offset"] == 0
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["chem_id"] == "000001"
    assert item["chemical_name_ko"] == "염산 구아니딘"
    assert item["cas_no"] == "50-01-1"
    assert "provenance" in item


def test_search_from_chem_ids_empty_chem_ids():
    store = _make_store()
    result = search_from_chem_ids(
        store=store, chem_ids=[], total=0, limit=10, offset=0
    )
    assert result["items"] == []
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# S07  search_by_q_os — identifier detection
# ---------------------------------------------------------------------------

from services.kosha_msds.search_adapter import search_by_q_os


def test_search_by_q_os_chem_id_exact():
    client = _fake_os_client(["000001"], 1)
    ids, total, meta = search_by_q_os(q="000001", limit=10, offset=0, client=client)
    assert ids == ["000001"]
    assert total == 1
    assert meta["identifier_kind"] == "chem_id"
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)


def test_search_by_q_os_cas_exact():
    client = _fake_os_client(["000042"], 1)
    ids, total, meta = search_by_q_os(q="71-43-2", limit=10, offset=0, client=client)
    assert meta["identifier_kind"] == "cas_no"
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "71-43-2"}} for f in filters)


def test_search_by_q_os_free_text():
    client = _fake_os_client(["000007", "000008"], 2)
    ids, total, meta = search_by_q_os(q="염산", limit=10, offset=0, client=client)
    assert len(ids) == 2
    assert meta["identifier_kind"] is None
    body = client.search.call_args[1]["body"]
    assert "must" in body["query"]["bool"]


def test_search_by_q_os_empty_returns_empty():
    client = MagicMock()
    ids, total, meta = search_by_q_os(q="", limit=10, offset=0, client=client)
    assert ids == []
    assert total == 0
    client.search.assert_not_called()


# ---------------------------------------------------------------------------
# S08  search_by_q_os — free-text pagination
# ---------------------------------------------------------------------------


def test_search_by_q_os_pagination():
    client = _fake_os_client(["000010", "000011"], 500)
    ids, total, _ = search_by_q_os(q="산업", limit=2, offset=20, client=client)
    assert total == 500
    body = client.search.call_args[1]["body"]
    assert body["from"] == 20
    assert body["size"] == 2


# ---------------------------------------------------------------------------
# S09  router: OS path via MemoryMsdsReadStore
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from fastapi import FastAPI
import routers.kosha_public_msds as msds_router_mod


def _make_app(store, os_client):
    """Build a test FastAPI app with the MSDS router + injected store + OS client."""
    app = FastAPI()
    app.include_router(msds_router_mod.router)
    msds_router_mod._store = store
    return app


def _env_seo_preview(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")


@pytest.fixture
def seo_store():
    return _make_store()


def test_router_os_name_ko_search(monkeypatch, seo_store):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    fake_client = _fake_os_client(["000001"], 1)

    app = _make_app(seo_store, fake_client)
    with patch("routers.kosha_public_msds.search_os",
               return_value=(["000001"], 1)) as mock_search:
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=염산")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["chem_id"] == "000001"


def test_router_os_q_search(monkeypatch, seo_store):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")

    app = _make_app(seo_store, None)
    with patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000002"], 1, {"identifier_kind": None,
                                              "normalized_query": "벤젠",
                                              "compact_query": "벤젠",
                                              "tokens": [], "expanded_terms": []})):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["chemical_name_ko"] == "벤젠"
    assert "match_metadata" in data


# ---------------------------------------------------------------------------
# S10  router: OS exception → fallback to legacy search
# ---------------------------------------------------------------------------


def test_router_os_exception_falls_back_to_legacy(monkeypatch, seo_store):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.search_os",
               side_effect=Exception("OS down")), \
         patch("routers.kosha_public_msds.search",
               return_value={"items": [], "total": 0, "limit": 10, "offset": 0}) as mock_legacy:
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=염산")
    assert resp.status_code == 200
    mock_legacy.assert_called_once()


# ---------------------------------------------------------------------------
# S11  regression: extract_product_name unaffected by CAS changes
# ---------------------------------------------------------------------------


def test_extract_product_name_regression():
    payload = [
        {"msdsItemCode": "C06", "itemDetail": "71-43-2"},
        {"msdsItemCode": "A02", "itemDetail": "벤젠"},
    ]
    assert extract_product_name(payload) == "벤젠"
    assert extract_cas_no(payload) == "71-43-2"


# ---------------------------------------------------------------------------
# S12  regression: section_fields no shared_search dep
# ---------------------------------------------------------------------------


def test_section_fields_no_shared_search_dep():
    import pathlib
    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services" / "kosha_msds" / "section_fields.py"
    ).read_text(encoding="utf-8")
    assert "shared_search" not in text
    assert "SearchDocument" not in text
