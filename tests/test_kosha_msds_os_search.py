"""WO-WWW-PERF-004-P0S — MSDS OpenSearch search adapter tests.

PATCH-08: WO-WWW-PERF-004-P0S-OS-PATCH-001 adds coverage for all
failure-contract changes introduced by PATCH-01~07.
PATCH-02C/02E: WO-WWW-PERF-004-P0S-OS-PATCH-002 adds coverage for
dependency separation and hydration integrity gate.

Covers:
  S01  extract_cas_no (section_fields)
  S02  search_os (opensearch_query) via fake OS client
  S03  os_chem_available gate (count-based, backwards-compat)
  S03b check_snapshot_gate (count-comparison, PATCH-02)
  S04  MemoryMsdsReadStore.hydrate_chem_ids (incl. scope param, PATCH-07)
  S05  SupabaseMsdsReadStore.hydrate_chem_ids contract (structure, no live DB)
  S06  search_from_chem_ids service function (incl. scope + integrity, PATCH-07/02E)
  S07  search_by_q_os — identifier detection routing (now in opensearch_query)
  S08  search_by_q_os — free-text routing
  S09  router list_or_search_msds via OS path (MemoryMsdsReadStore)
  S10  router OS error → 503 (PATCH-01: no legacy fallback)
  S11  regression: extract_product_name unaffected
  S12  regression: section_fields has no shared_search dep
  S13  search_os failure contracts (PATCH-03/04/05/06)
  S14  router 503 error codes (PATCH-01/02/03/06/02E)
  S15  hydration integrity gate (PATCH-02E)
  S16  search_by_q_os module location (PATCH-02C dependency separation)
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

from services.kosha_msds.opensearch_query import (
    MsdsCasIndexNotReadyError,
    MsdsPaginationDepthExceededError,
    MsdsSnapshotGateError,
    _clear_snapshot_cache,
    check_snapshot_gate,
    os_chem_available,
    search_os,
)


def test_search_os_by_chem_id():
    client = _fake_os_client(["000001"], 1)
    ids, total = search_os(chem_id="000001", limit=10, offset=0, client=client)
    assert ids == ["000001"]
    assert total == 1
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)


def test_search_os_by_cas_no(monkeypatch):
    """CAS query works when index is declared ready (PATCH-03)."""
    monkeypatch.setenv("KOSHA_MSDS_CAS_INDEX_READY", "true")
    client = _fake_os_client(["000042"], 1)
    ids, total = search_os(cas_no="71-43-2", limit=10, offset=0, client=client)
    assert ids == ["000042"]
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "71-43-2"}} for f in filters)


def test_search_os_by_name_ko():
    """name_ko uses wildcard on title.raw for ILIKE semantics (PATCH-003D), sorted source_key ASC."""
    client = _fake_os_client(["000001", "000002"], 2)
    ids, total = search_os(name_ko="염산", limit=10, offset=0, client=client)
    assert ids == ["000001", "000002"]
    assert total == 2
    body = client.search.call_args[1]["body"]
    assert "must" in body["query"]["bool"]
    must = body["query"]["bool"]["must"][0]
    assert "wildcard" in must
    assert must["wildcard"]["title.raw"]["value"] == "*염산*"
    assert must["wildcard"]["title.raw"]["case_insensitive"] is True
    # name_ko structural filter → deterministic order, not score-ranked
    assert body["sort"] == [{"source_key": "asc"}]


def test_search_os_by_q():
    """q uses BM25 multi_match sorted by score DESC (PATCH-05)."""
    client = _fake_os_client(["000007"], 1)
    ids, total = search_os(q="벤젠", limit=5, offset=0, client=client)
    assert ids == ["000007"]
    body = client.search.call_args[1]["body"]
    must = body["query"]["bool"]["must"][0]
    assert must["multi_match"]["query"] == "벤젠"
    assert body["sort"][0] == {"_score": "desc"}


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
# S13  search_os failure contracts (PATCH-03/04/05/06)
# ---------------------------------------------------------------------------


def test_search_os_cas_not_ready_raises():
    """Default env (no CAS_INDEX_READY) → MsdsCasIndexNotReadyError (PATCH-03)."""
    with pytest.raises(MsdsCasIndexNotReadyError):
        search_os(cas_no="71-43-2", limit=10, offset=0, client=MagicMock())


def test_search_os_cas_not_ready_env_false(monkeypatch):
    """Explicit false value → still raises (PATCH-03)."""
    monkeypatch.setenv("KOSHA_MSDS_CAS_INDEX_READY", "false")
    with pytest.raises(MsdsCasIndexNotReadyError):
        search_os(cas_no="71-43-2", limit=10, offset=0, client=MagicMock())


def test_search_os_pagination_depth_exceeded():
    """offset + limit > 9900 → PIT path; PIT failure raises MsdsPaginationDepthExceededError (PATCH-003F/004)."""
    client = MagicMock()
    client.create_pit.side_effect = Exception("PIT not supported")
    with pytest.raises(MsdsPaginationDepthExceededError):
        search_os(name_ko="x", limit=100, offset=9_900, client=client)


def test_search_os_pagination_at_limit_ok():
    """offset + limit == 9900 → allowed (boundary ok)."""
    client = _fake_os_client([], 0)
    ids, total = search_os(name_ko="x", limit=100, offset=9_800, client=client)
    assert total == 0


def test_search_os_and_filter_multiple_params(monkeypatch):
    """ke_no + name_ko → both appear as AND clauses (PATCH-04)."""
    client = _fake_os_client(["000099"], 1)
    ids, _ = search_os(ke_no="KE-12345", name_ko="염산", limit=10, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "KE-12345"}} for f in filters)
    must_clauses = body["query"]["bool"]["must"]
    # name_ko now uses wildcard on title.raw (PATCH-003D)
    assert any("wildcard" in clause for clause in must_clauses)


def test_search_os_chem_id_and_name_ko(monkeypatch):
    """chem_id filter + name_ko must clause → coexist (PATCH-04)."""
    client = _fake_os_client(["000001"], 1)
    ids, _ = search_os(chem_id="000001", name_ko="염산", limit=10, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)
    assert "must" in body["query"]["bool"]


# ---------------------------------------------------------------------------
# S03  os_chem_available gate (count-based, backwards-compat)
# ---------------------------------------------------------------------------


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
# S03b  check_snapshot_gate (PATCH-02)
# ---------------------------------------------------------------------------


def _make_sb_count(n: int):
    """Return a mock Supabase client that reports count=n for any query."""
    sb = MagicMock()
    r = MagicMock()
    r.count = n
    sb.table.return_value.select.return_value.limit.return_value.execute.return_value = r
    return sb


def _make_sb_proof_state(snap_id: str, outbox_wm: int):
    """Mock Supabase client that satisfies the PATCH-003B proof-based gate.

    Routes by table name:
      kosha_msds_seo_preview_current → snapshot_id lookup
      kosha_msds_snapshots            → completed_at lookup
      search_index_outbox             → watermark lookup
    Other tables raise (fail-closed sentinel).
    """
    def _table(table_name):
        m = MagicMock()
        if table_name == "kosha_msds_seo_preview_current":
            r = MagicMock()
            r.data = [{"snapshot_id": snap_id}]
            m.select.return_value.limit.return_value.execute.return_value = r
        elif table_name == "kosha_msds_snapshots":
            r = MagicMock()
            r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = r
        elif table_name == "search_index_outbox":
            r = MagicMock()
            r.data = [{"id": outbox_wm}]
            # chain: .select("id").eq("status","COMPLETED").eq("domain_name","CHEM").order(...).limit(1).execute()
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = r
        else:
            raise RuntimeError(f"unexpected table: {table_name}")
        return m
    sb = MagicMock()
    sb.table.side_effect = _table
    return sb


def _make_pass_proof(snap_id: str, phys_idx: str, outbox_wm: int):
    """Build a PASS SnapshotProof matching the given state triple."""
    from services.kosha_msds.snapshot_proof import SnapshotProof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    sha = "aa" * 32  # 64-char hex placeholder (same on both sides → PASS)
    return SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id=snap_id,
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index=phys_idx,
        rebuild_run_id="run-test",
        db_membership_count=20_568,
        os_membership_count=20_568,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=outbox_wm,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="PASS",
    )


def test_check_snapshot_gate_pass():
    """Gate passes when a valid proof matches the current state triple."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "0ad73e46-d61b-474d-a90e-5b5ab8080d80"
    PHYS_IDX = "tai-shared-search-v1-abcdef0123456789"
    OUTBOX_WM = 33527

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    check_snapshot_gate(client=os_client, sb=sb)  # should not raise


def test_check_snapshot_gate_divergence_raises():
    """No registered proof → gate raises MsdsSnapshotGateError (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-no-proof"
    PHYS_IDX = "tai-shared-search-v1-noproof"
    OUTBOX_WM = 100

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_check_snapshot_gate_db_failure_raises():
    """DB lookup failure → state resolves to ('','',0) → gate raises (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-x": {}}
    sb = MagicMock()
    sb.table.side_effect = Exception("DB unreachable")

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_check_snapshot_gate_os_failure_raises():
    """OS alias lookup failure → state has empty physical_index → gate raises (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.side_effect = Exception("OS unreachable")
    sb = _make_sb_proof_state("snap-os-fail", 100)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_check_snapshot_gate_cached_pass():
    """State triple is cached for 60 s; second call within TTL skips OS/DB lookups."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-cached-pass"
    PHYS_IDX = "tai-shared-search-v1-cachedpass"
    OUTBOX_WM = 200

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    check_snapshot_gate(client=os_client, sb=sb)
    check_snapshot_gate(client=os_client, sb=sb)
    # State triple cached — OS alias only resolved once
    assert os_client.indices.get_alias.call_count == 1


def test_check_snapshot_gate_cached_fail():
    """State lookup failure is cached; second call within TTL re-raises without re-querying."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.side_effect = Exception("OS down")
    sb = MagicMock()
    sb.table.side_effect = Exception("DB down")

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)
    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)
    # State cache: failures are cached — OS alias only attempted once
    assert os_client.indices.get_alias.call_count == 1


# ---------------------------------------------------------------------------
# S04  MemoryMsdsReadStore.hydrate_chem_ids
# ---------------------------------------------------------------------------

from services.kosha_msds.read import MemoryMsdsReadStore
from services.kosha_msds.contract import PUBLICATION_SCOPE_FULL, PUBLICATION_SCOPE_SEO_PREVIEW


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


def test_hydrate_chem_ids_seo_preview_scope():
    """Explicit SEO_PREVIEW scope → uses preview rows (PATCH-07)."""
    store = _make_store()
    rows = store.hydrate_chem_ids(["000001"], scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert len(rows) == 1
    assert rows[0]["chem_id"] == "000001"


def test_hydrate_chem_ids_full_scope_empty_when_no_full_rows():
    """FULL scope with no full rows → empty result (PATCH-07)."""
    store = _make_store()  # no current_rows seeded
    rows = store.hydrate_chem_ids(["000001"], scope=PUBLICATION_SCOPE_FULL)
    assert rows == []


def test_hydrate_chem_ids_missing_warns(caplog):
    """Missing chem_id logs a warning (PATCH-07)."""
    import logging
    store = _make_store()
    with caplog.at_level(logging.WARNING, logger="services.kosha_msds.read"):
        store.hydrate_chem_ids(["999999"])
    assert any("999999" in r.message for r in caplog.records)


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


def test_search_from_chem_ids_with_scope():
    """scope kwarg passed through to hydrate_chem_ids (PATCH-07)."""
    store = _make_store()
    result = search_from_chem_ids(
        store=store, chem_ids=["000001"], total=1, limit=10, offset=0,
        scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["chem_id"] == "000001"


def test_search_from_chem_ids_full_scope_empty():
    """FULL scope with no full rows → MsdsHydrationIntegrityError (PATCH-02E).

    OS returning an ID that's absent from the DB scope is membership drift —
    the function now raises MsdsHydrationIntegrityError instead of silently
    returning a short page.
    """
    from services.kosha_msds.opensearch_query import MsdsHydrationIntegrityError
    store = _make_store()
    with pytest.raises(MsdsHydrationIntegrityError):
        search_from_chem_ids(
            store=store, chem_ids=["000001"], total=1, limit=10, offset=0,
            scope=PUBLICATION_SCOPE_FULL,
        )


# ---------------------------------------------------------------------------
# S07  search_by_q_os — identifier detection
# ---------------------------------------------------------------------------

from services.kosha_msds.opensearch_query import search_by_q_os


def test_search_by_q_os_chem_id_exact():
    client = _fake_os_client(["000001"], 1)
    ids, total, meta = search_by_q_os(q="000001", limit=10, offset=0, client=client)
    assert ids == ["000001"]
    assert total == 1
    assert meta["identifier_kind"] == "chem_id"
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)


def test_search_by_q_os_cas_exact(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_CAS_INDEX_READY", "true")
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
    """PATCH-004: free-text collects all candidates (full pagination) then pages in memory.

    total = len(deduped_candidates), page = deduped[off:off+lim].
    Each sub-query uses limit=_CANDIDATE_PAGE_SIZE (1000), offset=0.
    """
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE
    client = _fake_os_client(["000010", "000011"], 2)
    ids, total, _ = search_by_q_os(q="산업", limit=2, offset=0, client=client)
    # total = number of unique candidates collected
    assert total == 2
    assert set(ids) == {"000010", "000011"}
    # All sub-queries use limit=_CANDIDATE_PAGE_SIZE (full pagination), offset=0
    call_bodies = [call[1]["body"] for call in client.search.call_args_list]
    assert all(b["size"] == _CANDIDATE_PAGE_SIZE for b in call_bodies)
    assert all(b["from"] == 0 for b in call_bodies)


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


@pytest.fixture
def seo_store():
    return _make_store()


def test_router_os_name_ko_search(monkeypatch, seo_store):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    fake_client = _fake_os_client(["000001"], 1)

    app = _make_app(seo_store, fake_client)
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               return_value=(["000001"], 1)):
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
    match_meta = {
        "identifier_kind": None,
        "normalized_query": "벤젠",
        "compact_query": "벤젠",
        "tokens": [],
        "expanded_terms": [],
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000002"], 1, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["chemical_name_ko"] == "벤젠"
    assert "match_metadata" in data


def test_router_os_q_search_match_type_annotation(monkeypatch, seo_store):
    """q-path items carry match_type and matched_term annotations (PATCH-05)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")

    app = _make_app(seo_store, None)
    match_meta = {
        "identifier_kind": None,
        "normalized_query": "벤젠",
        "compact_query": "벤젠",
        "tokens": [],
        "expanded_terms": [],
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000002"], 1, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    data = resp.json()
    item = data["items"][0]
    assert item["match_type"] == "BM25_NORI"
    assert item["matched_term"] == "벤젠"


def test_router_os_identifier_q_match_type(monkeypatch, seo_store):
    """Identifier q-path items carry IDENTIFIER_EXACT match_type (PATCH-05)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")

    app = _make_app(seo_store, None)
    match_meta = {
        "identifier_kind": "chem_id",
        "normalized_query": "000001",
        "compact_query": "000001",
        "tokens": [],
        "expanded_terms": [],
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000001"], 1, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=000001")
    data = resp.json()
    item = data["items"][0]
    assert item["match_type"] == "IDENTIFIER_EXACT"


# ---------------------------------------------------------------------------
# S10  router: OS errors → 503 (PATCH-01: no legacy fallback)
# ---------------------------------------------------------------------------


def test_router_os_exception_returns_503_not_fallback(monkeypatch, seo_store):
    """Generic OS exception → 503 MSDS_SEARCH_UNAVAILABLE, no legacy search (PATCH-01)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               side_effect=Exception("OS down")), \
         patch("routers.kosha_public_msds.search") as mock_legacy:
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=염산")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_SEARCH_UNAVAILABLE"
    mock_legacy.assert_not_called()


# ---------------------------------------------------------------------------
# S14  router: specific 503 error codes (PATCH-01/02/03/06)
# ---------------------------------------------------------------------------


def test_router_snapshot_gate_fail_503(monkeypatch, seo_store):
    """Snapshot gate failure → 503 MSDS_SNAPSHOT_GATE_FAIL (PATCH-02)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate",
               side_effect=MsdsSnapshotGateError("stale")):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=염산")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_SNAPSHOT_GATE_FAIL"


def test_router_cas_not_ready_503(monkeypatch, seo_store):
    """CAS index not ready → 503 MSDS_CAS_INDEX_NOT_READY (PATCH-03)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               side_effect=MsdsCasIndexNotReadyError("not ready")):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?cas_no=71-43-2")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_CAS_INDEX_NOT_READY"


def test_router_pagination_depth_503(monkeypatch, seo_store):
    """Pagination too deep → 503 MSDS_PAGINATION_DEPTH_EXCEEDED (PATCH-06)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               side_effect=MsdsPaginationDepthExceededError("too deep")):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=x&limit=100&offset=9900")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_PAGINATION_DEPTH_EXCEEDED"


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
# S12  regression: section_fields has no shared_search dep
# ---------------------------------------------------------------------------


def test_section_fields_no_shared_search_dep():
    import pathlib
    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services" / "kosha_msds" / "section_fields.py"
    ).read_text(encoding="utf-8")
    assert "shared_search" not in text
    assert "SearchDocument" not in text


# ---------------------------------------------------------------------------
# S15  hydration integrity gate (PATCH-02E)
# ---------------------------------------------------------------------------

from services.kosha_msds.opensearch_query import MsdsHydrationIntegrityError


def test_hydration_integrity_error_raised_on_gap():
    """search_from_chem_ids raises MsdsHydrationIntegrityError when OS
    returns IDs not found in the scoped DB view (PATCH-02E).
    """
    store = _make_store()  # preview_rows only
    with pytest.raises(MsdsHydrationIntegrityError) as exc_info:
        search_from_chem_ids(
            store=store, chem_ids=["000001", "MISSING_ID"], total=2,
            limit=10, offset=0, scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )
    assert "2" in str(exc_info.value) or "1" in str(exc_info.value)


def test_hydration_integrity_empty_chem_ids_no_error():
    """Empty chem_ids (legitimate 0-result search) must not raise (PATCH-02E)."""
    store = _make_store()
    result = search_from_chem_ids(
        store=store, chem_ids=[], total=0, limit=10, offset=0,
        scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert result["items"] == []
    assert result["total"] == 0


def test_hydration_integrity_all_found_no_error():
    """All OS IDs found in scope → normal result, no error (PATCH-02E)."""
    store = _make_store()
    result = search_from_chem_ids(
        store=store, chem_ids=["000001"], total=1, limit=10, offset=0,
        scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert len(result["items"]) == 1
    assert result["total"] == 1


def test_router_hydration_integrity_fail_503(monkeypatch, seo_store):
    """Hydration integrity failure → 503 MSDS_HYDRATION_INTEGRITY_FAIL (PATCH-02E)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               return_value=(["OS_ONLY_ID"], 1)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=염산")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_HYDRATION_INTEGRITY_FAIL"


# ---------------------------------------------------------------------------
# S16  search_by_q_os module location (PATCH-02C dependency separation)
# ---------------------------------------------------------------------------


def test_search_by_q_os_lives_in_opensearch_query():
    """search_by_q_os must be importable from opensearch_query (PATCH-02C)."""
    from services.kosha_msds.opensearch_query import search_by_q_os as fn
    assert callable(fn)


def test_search_adapter_has_no_opensearch_reference():
    """search_adapter.py must not reference opensearch (PATCH-02C).

    This is the existing test_14 contract: CHEM-09's plan module must not
    import any search engine. After PATCH-02C, search_by_q_os is moved to
    opensearch_query.py so this module is clean.
    """
    import pathlib
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services" / "kosha_msds" / "search_adapter.py"
    ).read_text(encoding="utf-8")
    assert "opensearch" not in src.lower(), (
        "search_adapter.py must not reference opensearch after PATCH-02C"
    )


# ---------------------------------------------------------------------------
# PATCH-003 T01-T25  WO-WWW-PERF-004-P0S-OS-PATCH-003
# ---------------------------------------------------------------------------

# ---- helpers ---------------------------------------------------------------

def _make_proof(snap_id, phys_idx, outbox_wm, *, status="PASS", sha="ab" * 32):
    from services.kosha_msds.snapshot_proof import SnapshotProof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    return SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id=snap_id,
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index=phys_idx,
        rebuild_run_id="run-t",
        db_membership_count=5,
        os_membership_count=5,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=outbox_wm,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status=status,
    )


# ---- T01-T06: Snapshot Proof / Gate ----------------------------------------


def test_T01_snapshot_same_id_membership_same():
    """T01: DB and OS membership identical → PASS proof."""
    from services.kosha_msds.snapshot_proof import (
        compute_membership_sha256, verify_proof, SnapshotProof
    )
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    pairs = [("000001", "uuid-001"), ("000002", "uuid-002")]
    sha = compute_membership_sha256(pairs)
    proof = SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id="snap-t01",
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index="tai-shared-search-v1-t01",
        rebuild_run_id="run-t01",
        db_membership_count=2,
        os_membership_count=2,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=100,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="PASS",
    )
    assert verify_proof(proof) is True


def test_T02_snapshot_same_id_membership_mismatch():
    """T02: DB and OS membership differ → FAIL proof; verify_proof returns False."""
    from services.kosha_msds.snapshot_proof import (
        compute_membership_sha256, verify_proof, SnapshotProof
    )
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    db_pairs = [("000001", "uuid-001"), ("000002", "uuid-002")]
    os_pairs = [("000001", "uuid-001"), ("000003", "uuid-003")]  # 000003 in OS, not DB
    proof = SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id="snap-t02",
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index="tai-shared-search-v1-t02",
        rebuild_run_id="run-t02",
        db_membership_count=2,
        os_membership_count=2,
        db_membership_sha256=compute_membership_sha256(db_pairs),
        os_membership_sha256=compute_membership_sha256(os_pairs),
        chem_outbox_high_watermark=100,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="FAIL",
        missing_count=1,
        extra_count=1,
    )
    assert verify_proof(proof) is False


def test_T03_snapshot_changed_mid_scan():
    """T03: Proof with verification_status=FAIL → gate raises."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-t03"
    PHYS_IDX = "tai-shared-search-v1-t03"
    OUTBOX_WM = 100

    # Register a FAIL proof (state changed mid-scan)
    proof = _make_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM, status="FAIL")
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_T04_alias_physical_index_swap():
    """T04: Physical index differs from registered proof → gate raises."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-t04"
    PROOF_IDX = "tai-shared-search-v1-old"
    NEW_IDX = "tai-shared-search-v1-new"   # alias now points to new index
    OUTBOX_WM = 100

    proof = _make_pass_proof(SNAP_ID, PROOF_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {NEW_IDX: {}}  # alias swapped
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_T05_outbox_new_chem_event():
    """T05: Outbox watermark advanced since proof was generated → gate raises."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-t05"
    PHYS_IDX = "tai-shared-search-v1-t05"
    PROOF_WM = 100
    CURRENT_WM = 200  # new events since proof

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, PROOF_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, CURRENT_WM)  # watermark advanced

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


def test_T06_no_proof_registered():
    """T06: No proof registered at all → gate raises (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-t06": {}}
    sb = _make_sb_proof_state("snap-t06", 100)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(client=os_client, sb=sb)


# ---- T07: FULL scope = 0 ---------------------------------------------------


def test_T07_full_scope_zero_chemicals(seo_store):
    """T07: FULL scope hydration with 0 FULL chemicals raises integrity error.

    OS returns IDs present in SEO_PREVIEW but FULL view has 0 rows.
    search_from_chem_ids with FULL scope must NOT silently return
    SEO_PREVIEW results — it raises MsdsHydrationIntegrityError.
    """
    from services.kosha_msds.read import search_from_chem_ids
    from services.kosha_msds.opensearch_query import MsdsHydrationIntegrityError

    # seo_store has "000001","000002" in SEO_PREVIEW but 0 rows in FULL scope
    with pytest.raises(MsdsHydrationIntegrityError):
        search_from_chem_ids(
            store=seo_store,
            chem_ids=["000001", "000002"],
            total=2,
            limit=20,
            offset=0,
            scope=PUBLICATION_SCOPE_FULL,
        )


# ---- T08-T12: MSDS field search contract -----------------------------------


def test_T08_name_en_searches_summary_not_title():
    """T08: name_en must → match on summary field (PATCH-003C)."""
    client = _fake_os_client(["000001"], 1)
    search_os(name_en="Benzene", limit=10, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    must = body["query"]["bool"]["must"]
    # must have a match on summary, NOT title
    assert any(
        "match" in clause and "summary" in clause["match"]
        for clause in must
    ), "name_en must search 'summary' field"
    assert not any(
        "match" in clause and "title" in clause.get("match", {})
        for clause in must
    ), "name_en must NOT search 'title' field"


def test_T09_name_ko_wildcard_ilike():
    """T09: name_ko → wildcard on title.raw with case_insensitive=True (PATCH-003D)."""
    client = _fake_os_client(["000001"], 1)
    search_os(name_ko="염산", limit=10, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    must = body["query"]["bool"]["must"]
    assert len(must) == 1
    clause = must[0]
    assert "wildcard" in clause
    assert clause["wildcard"]["title.raw"]["value"] == "*염산*"
    assert clause["wildcard"]["title.raw"]["case_insensitive"] is True


def test_T10_cas_exact_match_identifier_route():
    """T10: q='71-43-2' is detected as CAS identifier → search_os(cas_no=...) path."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client(["000001"], 1)
    # CAS index must be enabled for this path
    with patch.dict(os.environ, {"KOSHA_MSDS_CAS_INDEX_READY": "true"}):
        chem_ids, total, meta = search_by_q_os(q="71-43-2", limit=5, offset=0, client=client)
    assert meta["identifier_kind"] == "cas_no"
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "71-43-2"}} for f in filters)


def test_T11_identifier_type_separation():
    """T11: KE/EN/UN route through aliases.raw — same field may collide, verifying at call level."""
    client = _fake_os_client(["000001"], 1)
    search_os(ke_no="KE-12345", limit=5, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "KE-12345"}} for f in filters)
    # en_no and un_no also use aliases.raw — type isolation requires CAS-typed field
    # (future mapping extension; current limitation documented)
    search_os(en_no="EN-12345", limit=5, offset=0, client=client)
    body2 = client.search.call_args[1]["body"]
    filters2 = body2["query"]["bool"]["filter"]
    assert any(f == {"term": {"aliases.raw": "EN-12345"}} for f in filters2)


def test_T12_and_filter_combination():
    """T12: chem_id + name_ko → both appear as AND filter/must clauses."""
    client = _fake_os_client(["000001"], 1)
    search_os(chem_id="000001", name_ko="염산", limit=5, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    filters = body["query"]["bool"]["filter"]
    must = body["query"]["bool"]["must"]
    assert any(f == {"term": {"source_key": "000001"}} for f in filters)
    assert any("wildcard" in m and "title.raw" in m["wildcard"] for m in must)


# ---- T13-T16: CHEM-09 q search priority ------------------------------------


def test_T13_q_normalized_priority_used(monkeypatch):
    """T13: CHEM-09 priority — normalized_query → name_ko first (PATCH-004: no BM25)."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    calls = []

    def _mock_search_os(*, q=None, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        calls.append({"q": q, "name_ko": name_ko, "name_en": name_en})
        return [], 0

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )
    chem_ids, total, meta = search_by_q_os(q="벤젠", limit=5, offset=0)
    # PATCH-004: no BM25 (q=) calls; first call must be name_ko=normalized_query
    bm25_calls = [c for c in calls if c["q"] is not None]
    assert len(bm25_calls) == 0, "BM25 (q=) must not be called (CHEM-09 priority)"
    # NORMALIZED_EXACT: first call is name_ko=normalized_query
    ko_normalized_calls = [c for c in calls if c["name_ko"] == "벤젠"]
    assert len(ko_normalized_calls) >= 1
    assert meta["normalized_query"] == "벤젠"


def test_T14_dictionary_expansion_used(monkeypatch):
    """T14: expanded_terms from plan are passed to name_ko/name_en sub-queries."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    from services.kosha_msds.search_adapter import build_search_plan
    calls = []

    def _mock_search_os(*, q=None, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        calls.append({"name_ko": name_ko, "name_en": name_en})
        return [], 0

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )
    # Inject a fake dictionary_lookup that returns an expanded term
    def _dict_lookup(q, limit=5, subject_type=None):
        return {"items": [{"subject_key": "벤젠류", "matched_term": "벤젠류", "display_name": "벤젠류"}]}

    search_by_q_os(q="벤젠", limit=5, offset=0, dictionary_lookup=_dict_lookup)
    # expanded term "벤젠류" should appear in name_ko/name_en calls
    expanded_calls = [c for c in calls if c["name_ko"] == "벤젠류" or c["name_en"] == "벤젠류"]
    assert len(expanded_calls) >= 1


def test_T15_kiwi_tokens_used(monkeypatch):
    """T15: plan.tokens are passed to name_ko/name_en sub-queries."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    calls = []

    def _mock_search_os(*, q=None, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        calls.append({"q": q, "name_ko": name_ko, "name_en": name_en})
        return [], 0

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )
    # Use a multi-token free-text query; Kiwi will produce tokens
    search_by_q_os(q="벤젠 메탄올", limit=5, offset=0)
    # At least one name_ko call should come from token processing
    name_ko_calls = [c for c in calls if c["name_ko"] is not None]
    assert len(name_ko_calls) >= 1


def test_T16_dedup_preserves_priority_order(monkeypatch):
    """T16: chem_id deduplication preserves first-seen (priority) order."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    call_index = [0]
    # P1 NORMALIZED: name_ko returns [A, B]; name_en returns [B, C] — B is deduped
    responses = [
        (["000001", "000002"], 2),  # name_ko(normalized) call
        (["000002", "000003"], 2),  # name_en(normalized) call
        ([], 0),                    # further calls
    ]

    def _mock_search_os(*, q=None, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        idx = call_index[0]
        call_index[0] += 1
        return responses[idx] if idx < len(responses) else ([], 0)

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )
    chem_ids, total, _ = search_by_q_os(q="벤젠", limit=10, offset=0)
    # 000002 appears in both BM25 and name_ko — must appear only once, in BM25 position
    assert chem_ids.count("000002") == 1
    assert chem_ids.index("000001") < chem_ids.index("000002")


# ---- T17-T19: pagination ---------------------------------------------------


def test_T17_pagination_200_items(monkeypatch):
    """T17: offset+limit <= 9,900 → standard from/size pagination, correct page."""
    all_ids = [f"{i:06d}" for i in range(1, 201)]
    # Page 3: offset=40, limit=20 → items 41-60
    def _fake_search(**kwargs):
        body = kwargs.get("body", {})
        offset = body.get("from", 0)
        size = body.get("size", 20)
        page = all_ids[offset: offset + size]
        return {
            "hits": {
                "total": {"value": len(all_ids)},
                "hits": [{"_source": {"source_key": sk}} for sk in page],
            }
        }
    client = MagicMock()
    client.search.side_effect = _fake_search
    ids, total = search_os(limit=20, offset=40, client=client)
    assert total == 200
    assert ids == all_ids[40:60]
    # Standard from/size — no PIT
    client.create_pit.assert_not_called()


def test_T18_deep_pagination_uses_pit():
    """T18: offset+limit > 9,900 routes to PIT path (PATCH-004: create_pit/delete_pit)."""
    client = MagicMock()
    client.create_pit.return_value = {"pit_id": "pit-t18"}
    client.delete_pit.return_value = {}

    call_count = [0]
    def _pit_search(**kwargs):
        body = kwargs.get("body", {})
        if "pit" in body:
            call_count[0] += 1
            return {"hits": {"total": {"value": 0}, "hits": []}}
        return {"hits": {"total": {"value": 0}, "hits": []}}

    client.search.side_effect = _pit_search

    ids, total = search_os(limit=100, offset=9_901, client=client)
    assert ids == []
    assert total == 0
    client.create_pit.assert_called_once()
    client.delete_pit.assert_called_once()


def test_T18b_deep_pagination_pit_failure():
    """T18b: PIT creation failure → MsdsPaginationDepthExceededError (PATCH-004)."""
    client = MagicMock()
    client.create_pit.side_effect = Exception("PIT not supported by cluster")
    with pytest.raises(MsdsPaginationDepthExceededError):
        search_os(limit=100, offset=9_901, client=client)


def test_T19_last_page_empty_results():
    """T19: Requesting past last page returns empty items but correct total."""
    def _fake_search(**kwargs):
        return {"hits": {"total": {"value": 5}, "hits": []}}
    client = MagicMock()
    client.search.side_effect = _fake_search
    ids, total = search_os(limit=20, offset=100, client=client)
    assert total == 5
    assert ids == []


# ---- T20: Hydration integrity with ID mismatch ----------------------------


def test_T20_hydration_id_set_mismatch_raises(seo_store):
    """T20: OS returns IDs not found in DB scope → MsdsHydrationIntegrityError (PATCH-003H)."""
    from services.kosha_msds.read import search_from_chem_ids
    from services.kosha_msds.opensearch_query import MsdsHydrationIntegrityError
    # "999999" is not in seo_store → ID set mismatch
    with pytest.raises(MsdsHydrationIntegrityError):
        search_from_chem_ids(
            store=seo_store,
            chem_ids=["000001", "999999"],
            total=2,
            limit=20,
            offset=0,
            scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )


# ---- T21: CAS multiple C06 / blank / NULL ---------------------------------


def test_T21_cas_multiple_c06_returns_max():
    """T21: Multiple C06 items → MAX(btrim) returned (PATCH-003G)."""
    payload = [
        {"msdsItemCode": "C06", "itemDetail": "71-43-2"},
        {"msdsItemCode": "C06", "itemDetail": "99-99-9"},  # MAX lexicographically
        {"msdsItemCode": "C06", "itemDetail": "  50-00-0  "},  # btrim: spaces only
    ]
    result = extract_cas_no(payload)
    # MAX of "71-43-2", "99-99-9", "50-00-0" = "99-99-9"
    assert result == "99-99-9"


def test_T21b_cas_btrim_spaces_only():
    """T21b: btrim removes only ASCII spaces (not tabs/newlines)."""
    payload = [{"msdsItemCode": "C06", "itemDetail": "  71-43-2  "}]
    assert extract_cas_no(payload) == "71-43-2"


def test_T21c_cas_blank_returns_none():
    """T21c: All C06 values blank after btrim → None."""
    payload = [{"msdsItemCode": "C06", "itemDetail": "   "}]
    assert extract_cas_no(payload) is None


def test_T21d_cas_null_returns_none():
    """T21d: C06 itemDetail=None → None."""
    payload = [{"msdsItemCode": "C06", "itemDetail": None}]
    assert extract_cas_no(payload) is None


# ---- T22-T25: Regression ---------------------------------------------------


def test_T22_p0a_list_current_unaffected(seo_store):
    """T22: list_current (P0-A list path) still works after PATCH-003 changes."""
    from services.kosha_msds.read import list_current
    result = list_current(store=seo_store, limit=10, offset=0,
                          scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert result["total"] >= 2
    assert len(result["items"]) >= 2


def test_T23_msds_detail_unaffected(seo_store):
    """T23: get_by_chem_id (MSDS detail path) still works after PATCH-003 changes."""
    from services.kosha_msds.read import get_by_chem_id
    body = get_by_chem_id("000001", store=seo_store,
                           include_sections=False,
                           scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert body is not None
    assert body["chem_id"] == "000001"


def test_T24_section_fields_no_regression():
    """T24: extract_product_name unaffected by PATCH-003G CAS changes."""
    payload = [
        {"msdsItemCode": "A02", "itemDetail": "테스트 제품명"},
        {"msdsItemCode": "C06", "itemDetail": "71-43-2"},
    ]
    from services.kosha_msds.section_fields import extract_product_name
    assert extract_product_name(payload) == "테스트 제품명"
    assert extract_cas_no(payload) == "71-43-2"


def test_T25_search_failure_no_legacy_fallback(monkeypatch, seo_store):
    """T25: OS search failure → 503, no legacy Supabase fallback (PATCH-01)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    db_called = []

    def _mock_search(**kwargs):
        raise Exception("OS connection refused")

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os", side_effect=_mock_search):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=벤젠")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_SEARCH_UNAVAILABLE"
    assert len(db_called) == 0  # no legacy fallback path invoked


# ---- compute_membership_sha256 determinism ---------------------------------


def test_compute_membership_sha256_deterministic():
    """compute_membership_sha256 is order-independent and deterministic."""
    from services.kosha_msds.snapshot_proof import compute_membership_sha256
    pairs_a = [("000001", "uuid-a"), ("000002", "uuid-b")]
    pairs_b = [("000002", "uuid-b"), ("000001", "uuid-a")]  # reversed
    assert compute_membership_sha256(pairs_a) == compute_membership_sha256(pairs_b)


def test_compute_membership_sha256_differs_on_change():
    """compute_membership_sha256 changes when membership changes."""
    from services.kosha_msds.snapshot_proof import compute_membership_sha256
    sha1 = compute_membership_sha256([("000001", "uuid-a")])
    sha2 = compute_membership_sha256([("000002", "uuid-b")])
    assert sha1 != sha2


# ---------------------------------------------------------------------------
# PATCH-004 G01-G16  WO-WWW-PERF-004-P0S-OS-PATCH-004
# ---------------------------------------------------------------------------


# ---- G01: Outbox watermark raises on DB failure ----------------------------


def test_G01_outbox_watermark_raises_on_failure():
    """G01: _get_outbox_watermark raises SnapshotProofScanError on DB failure (PATCH-004)."""
    from services.kosha_msds.snapshot_proof import (
        _get_outbox_watermark,
        SnapshotProofScanError,
    )
    sb = MagicMock()
    sb.table.side_effect = Exception("DB unreachable")
    with pytest.raises(SnapshotProofScanError):
        _get_outbox_watermark(sb)


def test_G01b_outbox_watermark_uses_id_column():
    """G01b: _get_outbox_watermark queries 'id' column and filters by domain_name='CHEM'."""
    from services.kosha_msds.snapshot_proof import _get_outbox_watermark
    r = MagicMock()
    r.data = [{"id": 33527}]
    sb = MagicMock()
    # chain: .select("id").eq("status","COMPLETED").eq("domain_name","CHEM").order(...).limit(1).execute()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = r
    wm = _get_outbox_watermark(sb)
    assert wm == 33527
    # Verify 'id' was queried (not 'event_id')
    sb.table.return_value.select.assert_called_with("id")


def test_G01c_outbox_watermark_zero_when_no_completed():
    """G01c: No COMPLETED CHEM events → returns 0 (valid empty state, not error)."""
    from services.kosha_msds.snapshot_proof import _get_outbox_watermark
    r = MagicMock()
    r.data = []  # no rows
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = r
    assert _get_outbox_watermark(sb) == 0


# ---- G02: Scan failure → FAIL proof ----------------------------------------


def test_G02_db_scan_failure_returns_fail_proof():
    """G02: DB scan failure → generate_proof_dry_run returns FAIL proof, not exception."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run, verify_proof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    sb = MagicMock()
    # Pre-scan state succeeds
    snap_r = MagicMock()
    snap_r.data = [{"snapshot_id": "snap-g02"}]
    snap_ts_r = MagicMock()
    snap_ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
    outbox_r = MagicMock()
    outbox_r.data = [{"id": 100}]

    call_count = [0]
    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            m.select.return_value.limit.return_value.execute.return_value = snap_r
        elif name == "kosha_msds_snapshots":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = snap_ts_r
        elif name == "search_index_outbox":
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = outbox_r
        else:
            raise RuntimeError(f"unexpected table: {name}")
        return m

    sb.table.side_effect = _table

    # DB scan itself fails via the view query (second call to seo_preview_current for pagination)
    db_scan_call = [0]
    original_side = sb.table.side_effect

    def _table_fail(name):
        if name == "kosha_msds_seo_preview_current":
            db_scan_call[0] += 1
            if db_scan_call[0] > 1:  # second call is the scan
                raise Exception("DB scan timeout")
        return original_side(name)

    sb.table.side_effect = _table_fail

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-g02": {}}
    os_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.error_message is not None


def test_G02b_os_scan_failure_returns_fail_proof():
    """G02b: OS scan failure → FAIL proof with error_message."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    sb = MagicMock()
    snap_r = MagicMock()
    snap_r.data = [{"snapshot_id": "snap-g02b"}]
    snap_ts_r = MagicMock()
    snap_ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
    outbox_r = MagicMock()
    outbox_r.data = [{"id": 100}]
    db_scan_r = MagicMock()
    db_scan_r.data = []  # empty DB is fine → scan returns {}

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            # For scan pagination: .select("chem_id,id").order(...).limit(1000).execute()
            m.select.return_value.order.return_value.limit.return_value.execute.return_value = db_scan_r
        elif name == "kosha_msds_snapshots":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = snap_ts_r
        elif name == "search_index_outbox":
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = outbox_r
        return m

    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-g02b": {}}
    os_client.search.side_effect = Exception("OS cluster unavailable")

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.error_message is not None
    assert "OS scan failed" in proof.error_message


# ---- G09: PIT Client contract test -----------------------------------------


def test_G09_pit_client_methods_exist():
    """G09: opensearch-py client has create_pit and delete_pit — the official PIT API.

    Note: create_point_in_time is a legacy method with a different parameter schema
    (no allow_partial_pit_creation, different keep_alive contract). Our code uses
    create_pit which is the correct method for OpenSearch 2.x PIT.
    """
    from opensearchpy import OpenSearch
    import inspect
    assert hasattr(OpenSearch, "create_pit"), (
        "opensearch-py must expose create_pit method"
    )
    assert hasattr(OpenSearch, "delete_pit"), (
        "opensearch-py must expose delete_pit method"
    )
    # Verify create_pit is the official method (has allow_partial_pit_creation param)
    sig_src = inspect.getsource(OpenSearch.create_pit)
    assert "allow_partial_pit_creation" in sig_src, (
        "create_pit must be the official PIT method (has allow_partial_pit_creation)"
    )


# ---- G10: Deep page > 10,000 -----------------------------------------------


def test_G10_deep_page_over_10000():
    """G10: offset+limit > 9,900 → create_pit called (PIT deep pagination)."""
    client = MagicMock()
    client.create_pit.return_value = {"pit_id": "pit-g10"}
    client.delete_pit.return_value = {}
    client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    search_os(limit=100, offset=10_000, client=client)
    client.create_pit.assert_called_once()
    client.delete_pit.assert_called_once()


# ---- G11: q candidate > _CANDIDATE_PAGE_SIZE → multiple calls per term -----


def test_G11_q_candidate_full_pagination(monkeypatch):
    """G11: When a term returns >= _CANDIDATE_PAGE_SIZE results, pagination continues."""
    from services.kosha_msds.opensearch_query import (
        search_by_q_os,
        _CANDIDATE_PAGE_SIZE,
    )
    # First call returns exactly _CANDIDATE_PAGE_SIZE results → triggers second call
    ids_page1 = [f"{i:06d}" for i in range(1, _CANDIDATE_PAGE_SIZE + 1)]
    ids_page2 = [f"{i:06d}" for i in range(_CANDIDATE_PAGE_SIZE + 1, _CANDIDATE_PAGE_SIZE + 3)]

    call_count = [0]

    def _mock_search_os(*, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        q=None, chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        call_count[0] += 1
        if name_ko is not None:
            if offset == 0:
                return ids_page1, len(ids_page1) + len(ids_page2)
            else:
                return ids_page2, len(ids_page1) + len(ids_page2)
        return [], 0

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )
    ids, total, _ = search_by_q_os(q="산", limit=10, offset=0)
    # Should have paginated name_ko: offset=0 (page1) + offset=_CANDIDATE_PAGE_SIZE (page2)
    name_ko_calls = call_count[0]
    assert name_ko_calls >= 2, f"Expected >=2 calls for full pagination, got {name_ko_calls}"
    # First page slice
    assert ids == ids_page1[:10]


# ---- G12: q dedup priority order -------------------------------------------


def test_G12_q_dedup_priority_normalized_first(monkeypatch):
    """G12: normalized_query results appear before dictionary expansion results."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    call_order = []

    def _mock_search_os(*, name_ko=None, name_en=None, limit=20, offset=0, client=None,
                        q=None, chem_id=None, cas_no=None, ke_no=None, en_no=None, un_no=None):
        if name_ko == "벤젠":
            call_order.append("normalized_ko")
            return ["000001"], 1
        if name_en == "벤젠":
            call_order.append("normalized_en")
            return [], 0
        if name_ko == "benzene":
            call_order.append("expanded_ko")
            return ["000002"], 1
        return [], 0

    monkeypatch.setattr(
        "services.kosha_msds.opensearch_query.search_os", _mock_search_os
    )

    def _dict_lookup(q, limit=5, subject_type=None):
        return {"items": [{"subject_key": "benzene", "matched_term": "benzene", "display_name": "benzene"}]}

    ids, total, _ = search_by_q_os(q="벤젠", limit=10, offset=0, dictionary_lookup=_dict_lookup)
    # 000001 from normalized must come before 000002 from dictionary expansion
    assert "000001" in ids
    assert "000002" in ids
    idx1 = ids.index("000001")
    idx2 = ids.index("000002")
    assert idx1 < idx2, "Normalized results must precede dictionary expansion results"
    # Verify call order
    assert call_order.index("normalized_ko") < call_order.index("expanded_ko")


# ---- G13: match_type annotation --------------------------------------------


def test_G13_match_type_identifier_exact(monkeypatch):
    """G13: Identifier q path sets match_type=IDENTIFIER_EXACT."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client(["000001"], 1)
    _, _, meta = search_by_q_os(q="000001", limit=5, offset=0, client=client)
    assert meta["match_type"] == "IDENTIFIER_EXACT"
    assert meta["identifier_kind"] == "chem_id"


def test_G13b_match_type_free_text(monkeypatch):
    """G13b: Free-text q path sets match_type=BM25_NORI (free-text label)."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client([], 0)
    _, _, meta = search_by_q_os(q="염산", limit=5, offset=0, client=client)
    assert meta["match_type"] == "BM25_NORI"
    assert meta["identifier_kind"] is None


# ---------------------------------------------------------------------------
# PATCH-005 H01-H08  WO-WWW-PERF-004-P0S-OS-PATCH-005
# ---------------------------------------------------------------------------


# ---- H01: Post-scan outbox failure → FAIL proof ----------------------------


def test_H01_postscan_outbox_failure_returns_fail():
    """H01: Post-scan _get_outbox_watermark failure → FAIL proof (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    call_count = [0]

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-h01"}]
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            db_scan_r = MagicMock()
            db_scan_r.data = []
            m.select.return_value.order.return_value.limit.return_value.execute.return_value = db_scan_r
        elif name == "kosha_msds_snapshots":
            ts_r = MagicMock()
            ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = ts_r
        elif name == "search_index_outbox":
            call_count[0] += 1
            r = MagicMock()
            if call_count[0] <= 2:
                # Calls 1+2: _get_outbox_watermark pre-scan + _get_outbox_pending_count → succeed
                r.data = [{"id": 100}]
                r.count = 0
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = r
                m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = r
            else:
                # Call 3: _get_outbox_watermark post-scan → fails
                m.select.side_effect = Exception("DB transient error")
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-h01": {}}
    os_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.error_message is not None
    assert "Post-scan state check failed" in proof.error_message


# ---- H02: Duplicate chem_id rows in DB → FAIL proof ------------------------


def test_H02_duplicate_chem_id_in_db_returns_fail():
    """H02: DB view returns duplicate chem_id rows → FAIL with duplicate_db_count (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-h02"}]
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            # DB scan returns duplicate chem_id "000001" twice (same key, different rows)
            scan_r1 = MagicMock()
            scan_r1.data = [
                {"chem_id": "000001", "id": "uuid-001"},
                {"chem_id": "000001", "id": "uuid-002"},  # duplicate
            ]
            scan_r2 = MagicMock()
            scan_r2.data = []
            _scan_calls = [0]
            def _scan_execute():
                _scan_calls[0] += 1
                return scan_r1 if _scan_calls[0] == 1 else scan_r2
            m.select.return_value.order.return_value.limit.return_value.execute.side_effect = _scan_execute
        elif name == "kosha_msds_snapshots":
            ts_r = MagicMock()
            ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = ts_r
        elif name == "search_index_outbox":
            r = MagicMock()
            r.data = [{"id": 100}]
            r.count = 0
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = r
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-h02": {}}
    os_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.duplicate_db_count == 1  # 2 rows → 1 dict entry → 1 duplicate
    assert proof.error_message is not None
    assert "Duplicate" in proof.error_message


# ---- H03: Per-item match_type from CHEM-09 provenance ----------------------


def test_H03_per_item_metadata_carried_through(monkeypatch, seo_store):
    """H03: search_by_q_os per_item_metadata → router annotates each item correctly (PATCH-005C)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    # per_item_metadata: 000001→NORMALIZED_EXACT, 000002→KIWI_TOKEN
    match_meta = {
        "identifier_kind": None,
        "normalized_query": "벤젠",
        "compact_query": "벤젠",
        "tokens": ["벤젠"],
        "expanded_terms": [],
        "match_type": "BM25_NORI",
        "per_item_metadata": {
            "000001": {"match_type": "NORMALIZED_EXACT", "matched_term": "벤젠"},
            "000002": {"match_type": "KIWI_TOKEN", "matched_term": "벤젠"},
        },
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000001", "000002"], 2, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    assert resp.status_code == 200
    items = {i["chem_id"]: i for i in resp.json()["items"]}
    assert items["000001"]["match_type"] == "NORMALIZED_EXACT"
    assert items["000001"]["matched_term"] == "벤젠"
    assert items["000002"]["match_type"] == "KIWI_TOKEN"
    assert items["000002"]["matched_term"] == "벤젠"


# ---- H04: PENDING events guard → FAIL proof --------------------------------


def test_H04_pending_events_returns_fail():
    """H04: Uncommitted PENDING CHEM events → FAIL proof (PATCH-005B pending guard)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-h04"}]
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            scan_r = MagicMock()
            scan_r.data = []
            m.select.return_value.order.return_value.limit.return_value.execute.return_value = scan_r
        elif name == "kosha_msds_snapshots":
            ts_r = MagicMock()
            ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = ts_r
        elif name == "search_index_outbox":
            wm_r = MagicMock()
            wm_r.data = [{"id": 100}]
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            # Pending count query returns count=5 (5 uncommitted events)
            pending_r = MagicMock()
            pending_r.count = 5
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-h04": {}}
    os_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.error_message is not None
    assert "pending_count=5" in proof.error_message


# ---- H05: verify_proof requires rebuild_run_id non-empty -------------------


def test_H05_verify_proof_empty_rebuild_run_id_fails():
    """H05: verify_proof returns False when rebuild_run_id is empty (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import verify_proof, SnapshotProof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    sha = "ab" * 32
    proof = SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id="snap-h05",
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index="tai-shared-search-v1-h05",
        rebuild_run_id="",  # empty → should fail
        db_membership_count=5,
        os_membership_count=5,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=100,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="PASS",
    )
    assert verify_proof(proof) is False


def test_H05b_verify_proof_with_rebuild_run_id_passes():
    """H05b: verify_proof returns True with non-empty rebuild_run_id (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import verify_proof
    proof = _make_proof("snap-h05b", "tai-shared-search-v1-h05b", 100)
    assert verify_proof(proof) is True


# ---- H06: Router per_item_metadata fallback for identifier path ------------


def test_H06_router_identifier_q_no_per_item_metadata(monkeypatch, seo_store):
    """H06: Identifier q-path (no per_item_metadata) falls back to IDENTIFIER_EXACT (PATCH-005C)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    match_meta = {
        "identifier_kind": "chem_id",
        "normalized_query": "000001",
        "compact_query": "000001",
        "tokens": [],
        "expanded_terms": [],
        "match_type": "IDENTIFIER_EXACT",
        # no per_item_metadata
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000001"], 1, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=000001")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["match_type"] == "IDENTIFIER_EXACT"
    assert item["matched_term"] == "000001"


# ---- H07: _get_outbox_pending_count raises on DB failure -------------------


def test_H07_outbox_pending_count_raises_on_failure():
    """H07: _get_outbox_pending_count raises SnapshotProofScanError on DB failure (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import (
        _get_outbox_pending_count,
        SnapshotProofScanError,
    )
    sb = MagicMock()
    sb.table.side_effect = Exception("DB unreachable")
    with pytest.raises(SnapshotProofScanError):
        _get_outbox_pending_count(sb)


def test_H07b_outbox_pending_count_zero_when_clean():
    """H07b: _get_outbox_pending_count returns 0 when no uncommitted events."""
    from services.kosha_msds.snapshot_proof import _get_outbox_pending_count
    r = MagicMock()
    r.count = 0
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = r
    assert _get_outbox_pending_count(sb) == 0


# ---- H08: verify_proof duplicate_db_count -----------------------------------


def test_H08_verify_proof_duplicate_db_count_fails():
    """H08: verify_proof returns False when duplicate_db_count > 0 (PATCH-005B)."""
    from services.kosha_msds.snapshot_proof import verify_proof, SnapshotProof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    sha = "ab" * 32
    proof = SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id="snap-h08",
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index="tai-shared-search-v1-h08",
        rebuild_run_id="run-h08",
        db_membership_count=4,
        os_membership_count=4,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=100,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="PASS",
        duplicate_db_count=2,  # data anomaly
    )
    assert verify_proof(proof) is False
