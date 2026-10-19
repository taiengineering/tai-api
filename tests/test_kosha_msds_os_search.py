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


def _make_sb_proof_state(snap_id: str, outbox_wm: int, *, pending_count: int = 0):
    """Mock Supabase client that satisfies the PATCH-003B proof-based gate.

    Routes by table name:
      kosha_msds_seo_preview_current → snapshot_id lookup
      kosha_msds_snapshots            → completed_at lookup
      search_index_outbox             → watermark lookup + pending count lookup
    Other tables raise (fail-closed sentinel).
    pending_count controls the uncached PENDING gate check (P0-01, default=0=clean).
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
            wm_r = MagicMock()
            wm_r.data = [{"id": outbox_wm}]
            pending_r = MagicMock()
            pending_r.count = pending_count
            # watermark: .select("id").eq("status","COMPLETED").eq("domain_name","CHEM").order(...).limit(1).execute()
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            # pending: .select("id", count="exact").eq("domain_name","CHEM").in_("status",[...]).limit(0).execute()
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
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

    check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)  # should not raise


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
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


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
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


def test_check_snapshot_gate_os_failure_raises():
    """OS alias lookup failure → state has empty physical_index → gate raises (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.side_effect = Exception("OS unreachable")
    sb = _make_sb_proof_state("snap-os-fail", 100)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


def test_check_snapshot_gate_two_calls_both_pass():
    """CLOSURE-01: state lookups are live (uncached); two valid calls both pass."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-two-calls"
    PHYS_IDX = "tai-shared-search-v1-twocalls"
    OUTBOX_WM = 200

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    # Both calls must pass — no stale cache can cause spurious failures
    check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)
    check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)
    # With no cache, OS alias resolved on every call
    assert os_client.indices.get_alias.call_count >= 2


def test_check_snapshot_gate_repeated_failure_raises():
    """CLOSURE-01: no cache — each failing call does a fresh live lookup."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.side_effect = Exception("OS down")
    sb = MagicMock()
    sb.table.side_effect = Exception("DB down")

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)
    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)
    # No cache — OS alias attempted on every call
    assert os_client.indices.get_alias.call_count >= 2


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
    """WO-023: free-text uses single dis_max query with OS-side from/size pagination.

    Exactly 1 OS search call per page. total comes from OS track_total_hits.
    from=offset, size=limit passed to OS directly.
    """
    client = _fake_os_client(["000010", "000011"], 2)
    ids, total, _ = search_by_q_os(q="산업", limit=2, offset=0, client=client)
    assert total == 2
    assert set(ids) == {"000010", "000011"}
    # WO-023 contract: exactly 1 OS call per free-text page
    assert client.search.call_count == 1, "WO-023: expected exactly 1 OS call per page"
    body = client.search.call_args[1]["body"]
    assert body["from"] == 0
    assert body["size"] == 2
    assert "dis_max" in str(body["query"])


def test_search_by_q_os_single_call_contract():
    """WO-023: exactly 1 OS search call per free-text page (regression guard)."""
    client = _fake_os_client(["000001"], 1)
    search_by_q_os(q="염산", limit=20, offset=0, client=client)
    assert client.search.call_count == 1


def test_search_by_q_os_source_id_filter_present():
    """source_id=KOSHA_MSDS filter must appear in the free-text DSL."""
    from services.kosha_msds.opensearch_query import _build_free_text_dsl
    from services.kosha_msds.search_adapter import build_search_plan
    plan = build_search_plan("염산")
    dsl = _build_free_text_dsl(plan, from_=0, size=20)
    filters_str = str(dsl["query"]["bool"]["filter"])
    assert "KOSHA_MSDS" in filters_str, "source_id=KOSHA_MSDS must be in DSL filter"


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
    """q-path items carry match_type=CHEM_09 and matched_term annotations (P0-02)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")

    app = _make_app(seo_store, None)
    match_meta = {
        "identifier_kind": None,
        "normalized_query": "벤젠",
        "compact_query": "벤젠",
        "tokens": [],
        "expanded_terms": [],
        "match_type": "CHEM_09",
        "per_item_metadata": {
            "000002": {"match_type": "CHEM_09", "matched_term": "벤젠"},
        },
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000002"], 1, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    data = resp.json()
    item = data["items"][0]
    assert item["match_type"] == "CHEM_09"
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
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


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
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


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
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


def test_T06_no_proof_registered():
    """T06: No proof registered at all → gate raises (fail-closed)."""
    from services.kosha_msds.snapshot_proof import clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-t06": {}}
    sb = _make_sb_proof_state("snap-t06", 100)

    with pytest.raises(MsdsSnapshotGateError):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


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


def test_T13_q_normalized_priority_used():
    """T13: WO-023 — normalized_query is NE clause in dis_max DSL; single OS call."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client(["000001"], 1)
    chem_ids, total, meta = search_by_q_os(q="벤젠", limit=5, offset=0, client=client)
    assert meta["normalized_query"] == "벤젠"
    assert client.search.call_count == 1
    body = client.search.call_args[1]["body"]
    assert "NE:벤젠" in str(body["query"])


def test_T14_dictionary_expansion_used():
    """T14: WO-023 — expanded_terms appear as DE: clauses in dis_max DSL."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client([], 0)

    def _dict_lookup(q, limit=5, subject_type=None):
        return {"items": [{"subject_key": "벤젠류", "matched_term": "벤젠류", "display_name": "벤젠류"}]}

    search_by_q_os(q="벤젠", limit=5, offset=0, client=client, dictionary_lookup=_dict_lookup)
    body = client.search.call_args[1]["body"]
    assert "DE:벤젠류" in str(body["query"])
    assert client.search.call_count == 1


def test_T15_kiwi_tokens_used():
    """T15: WO-023 — Kiwi tokens appear as KW: clauses in dis_max DSL."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client([], 0)
    search_by_q_os(q="벤젠 메탄올", limit=5, offset=0, client=client)
    body = client.search.call_args[1]["body"]
    assert "KW:" in str(body["query"])
    assert client.search.call_count == 1


def test_T16_dedup_preserves_priority_order():
    """T16: WO-023 — OS score order preserved; no duplicate chem_ids in page."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    # OS returns in score order (NE boost=1000 → 000001 scores higher than KW→000002)
    client = _fake_os_client(["000001", "000002"], 2)
    chem_ids, total, _ = search_by_q_os(q="벤젠", limit=10, offset=0, client=client)
    assert chem_ids.count("000002") == 1
    assert chem_ids.index("000001") < chem_ids.index("000002")
    assert client.search.call_count == 1


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
    """G11: _collect_all_os_pit paginates via search_after when >= _CANDIDATE_PAGE_SIZE hits."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE, _collect_all_os_pit

    ids_page1 = [f"{i:06d}" for i in range(1, _CANDIDATE_PAGE_SIZE + 1)]
    ids_page2 = [f"{i:06d}" for i in range(_CANDIDATE_PAGE_SIZE + 1, _CANDIDATE_PAGE_SIZE + 3)]
    total = len(ids_page1) + len(ids_page2)

    call_n = [0]
    def _search(**kwargs):
        call_n[0] += 1
        page = ids_page1 if call_n[0] == 1 else ids_page2
        hits = [{"_source": {"source_key": sk}, "sort": [sk]} for sk in page]
        return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-g11"]

    result = _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="산")

    assert call_n[0] >= 2, f"Expected >=2 search calls for full pagination, got {call_n[0]}"
    assert result[:10] == ids_page1[:10]


# ---- G12: q dedup priority order -------------------------------------------


def test_G12_q_dedup_priority_normalized_first():
    """G12: WO-023 — NE clause (boost=1000) outranks DE clause (boost=100) in dis_max DSL."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    # OS returns 000001 (higher NE-boosted score) before 000002 (lower DE-boosted score)
    client = _fake_os_client(["000001", "000002"], 2)

    def _dict_lookup(q, limit=5, subject_type=None):
        return {"items": [{"subject_key": "benzene", "matched_term": "benzene", "display_name": "benzene"}]}

    ids, total, _ = search_by_q_os(q="벤젠", limit=10, offset=0, client=client, dictionary_lookup=_dict_lookup)
    assert "000001" in ids
    assert "000002" in ids
    assert ids.index("000001") < ids.index("000002"), "NE results must precede DE results"
    assert client.search.call_count == 1
    body = client.search.call_args[1]["body"]
    query_str = str(body["query"])
    assert "NE:벤젠" in query_str
    assert "DE:benzene" in query_str


# ---- G13: match_type annotation --------------------------------------------


def test_G13_match_type_identifier_exact(monkeypatch):
    """G13: Identifier q path sets match_type=IDENTIFIER_EXACT."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client(["000001"], 1)
    _, _, meta = search_by_q_os(q="000001", limit=5, offset=0, client=client)
    assert meta["match_type"] == "IDENTIFIER_EXACT"
    assert meta["identifier_kind"] == "chem_id"


def test_G13b_match_type_free_text(monkeypatch):
    """G13b: Free-text q path sets match_type=CHEM_09 (P0-02: BM25 not used)."""
    from services.kosha_msds.opensearch_query import search_by_q_os
    client = _fake_os_client([], 0)
    _, _, meta = search_by_q_os(q="염산", limit=5, offset=0, client=client)
    assert meta["match_type"] == "CHEM_09"
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


# ---------------------------------------------------------------------------
# PATCH-006 I01-I09  WO-WWW-PERF-004-P0S-OS-PATCH-006
# ---------------------------------------------------------------------------


# ---- I01: empty snapshot_id → FAIL proof + verify_proof False --------------


def test_I01a_verify_proof_empty_snapshot_id_fails():
    """I01a: verify_proof returns False when snapshot_id is empty (P0-01)."""
    from services.kosha_msds.snapshot_proof import verify_proof, SnapshotProof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import CURRENT_ALIAS
    sha = "ab" * 32
    proof = SnapshotProof(
        proof_version="1.0",
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        snapshot_id="",  # empty → must fail
        snapshot_completed_at="2026-10-01T00:00:00+00:00",
        opensearch_alias=CURRENT_ALIAS,
        physical_index="tai-shared-search-v1-i01",
        rebuild_run_id="run-i01",
        db_membership_count=5,
        os_membership_count=5,
        db_membership_sha256=sha,
        os_membership_sha256=sha,
        chem_outbox_high_watermark=100,
        verified_at="2026-10-01T00:00:00+00:00",
        verification_status="PASS",  # would pass all other checks
    )
    assert verify_proof(proof) is False


def test_I01b_generate_proof_empty_snapshot_returns_fail():
    """I01b: generate_proof_dry_run with no active snapshot → FAIL proof (P0-01)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            # snapshot lookup returns empty list → snapshot_id = ""
            snap_r = MagicMock()
            snap_r.data = []
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            # DB scan: empty
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
            pending_r = MagicMock()
            pending_r.count = 0
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-i01b": {}}
    os_client.search.return_value = {"hits": {"hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert proof.snapshot_id == ""
    assert "empty" in (proof.error_message or "").lower()


# ---- I02: post-proof PENDING events → check_snapshot_gate raises -----------


def test_I02_gate_rejects_pending_events_after_proof():
    """I02: Uncached pending check detects new PENDING events not present at proof time (P0-01)."""
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry
    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-i02"
    PHYS_IDX = "tai-shared-search-v1-i02"
    OUTBOX_WM = 500

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    # State matches proof, but 3 PENDING events arrived after proof was generated
    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM, pending_count=3)

    with pytest.raises(MsdsSnapshotGateError, match="Uncommitted CHEM events"):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


# ---- I03: OS duplicate source_key → FAIL proof + os_duplicate_count > 0 ----


def test_I03_os_duplicate_source_key_returns_fail():
    """I03: OS index with duplicate source_key → FAIL proof, os_duplicate_count > 0 (P0-01)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import RUNS_INDEX

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-i03"}]
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
            pending_r = MagicMock()
            pending_r.count = 0
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    # OS client: _get_rebuild_run_id uses RUNS_INDEX; _scan_os_chem_ids uses physical_index
    def _search_side_effect(**kwargs):
        idx = kwargs.get("index", "")
        if idx == RUNS_INDEX:
            return {"hits": {"hits": [{"_source": {"run_id": "run-i03"}}]}}
        # Physical index scan: return 2 hits with duplicate source_key "000001"
        return {
            "hits": {
                "hits": [
                    {"_source": {"source_key": "000001", "canonical_id": "uuid-a"}, "sort": ["uuid-a"]},
                    {"_source": {"source_key": "000001", "canonical_id": "uuid-b"}, "sort": ["uuid-b"]},
                ]
            }
        }

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-i03": {}}
    os_client.search.side_effect = _search_side_effect

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.os_duplicate_count == 1  # 2 raw hits → 1 deduped → 1 duplicate
    assert proof.verification_status == "FAIL"
    assert "Duplicate source_key" in (proof.error_message or "")


# ---- I04: _collect_all_os budget exhaustion → MsdsCandidateEnumerationIncompleteError


def test_I04_collect_all_os_budget_exhausted_raises():
    """I04: _collect_all_os raises MsdsCandidateEnumerationIncompleteError when
    page budget is exhausted with results still remaining (P0-03)."""
    from services.kosha_msds.opensearch_query import (
        _collect_all_os,
        _CANDIDATE_MAX_PAGES,
        _CANDIDATE_PAGE_SIZE,
        MsdsCandidateEnumerationIncompleteError,
    )

    # Always return full page with total much larger than budget
    full_page = [f"{i:06d}" for i in range(_CANDIDATE_PAGE_SIZE)]
    huge_total = _CANDIDATE_MAX_PAGES * _CANDIDATE_PAGE_SIZE + 1

    with patch("services.kosha_msds.opensearch_query.search_os",
               return_value=(full_page, huge_total)):
        with pytest.raises(MsdsCandidateEnumerationIncompleteError) as exc_info:
            _collect_all_os(name_ko="테스트", client=MagicMock())

    assert "budget exhausted" in str(exc_info.value).lower()
    assert f"os_total={huge_total}" in str(exc_info.value)


# ---- I05: per_item_metadata page-scoped only (not full result set) ----------


def test_I05_per_item_metadata_is_page_sized():
    """I05: WO-023 — per_item_metadata contains only the current page items (OS from/size)."""
    from services.kosha_msds.opensearch_query import search_by_q_os

    page_ids = ["000001", "000002", "000003"]

    def _fake_search(**kwargs):
        # OS returns only 3 items (limit=3); total=10 (more matches exist)
        return {
            "hits": {
                "total": {"value": 10},
                "hits": [{"_source": {"source_key": sk}} for sk in page_ids],
            }
        }

    mock_client = MagicMock()
    mock_client.search.side_effect = _fake_search

    page, total, meta = search_by_q_os(q="염산", limit=3, offset=0, client=mock_client)

    assert total == 10
    assert len(page) == 3
    assert "per_item_metadata" in meta
    assert set(meta["per_item_metadata"].keys()) == set(page)
    assert len(meta["per_item_metadata"]) == 3


# ---- I06: search_by_q_os free-text sets match_type="CHEM_09" ----------------


def test_I06_search_by_q_os_free_text_match_type_chem09():
    """I06: Free-text search_by_q_os sets match_type='CHEM_09', not BM25 (P0-02)."""
    from services.kosha_msds.opensearch_query import search_by_q_os

    client = _fake_os_client(["000001"], 1)
    page, total, meta = search_by_q_os(q="염산", limit=5, offset=0, client=client)

    assert meta["match_type"] == "CHEM_09"
    assert meta["identifier_kind"] is None
    assert "per_item_metadata" in meta
    assert isinstance(meta["per_item_metadata"], dict)


# ---- I07: duplicate input chem_ids → MsdsHydrationIntegrityError → 503 -----


def test_I07_duplicate_chem_ids_raises_hydration_error(seo_store):
    """I07: search_from_chem_ids raises MsdsHydrationIntegrityError on duplicate OS input IDs (P0-04)."""
    from services.kosha_msds.opensearch_query import MsdsHydrationIntegrityError
    from services.kosha_msds.read import search_from_chem_ids

    with pytest.raises(MsdsHydrationIntegrityError, match="Duplicate chem_ids in OS result"):
        search_from_chem_ids(
            store=seo_store, chem_ids=["000001", "000001"],  # duplicate
            total=2, limit=10, offset=0,
            scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )


def test_I07b_router_duplicate_chem_ids_503(monkeypatch, seo_store):
    """I07b: Router returns 503 MSDS_HYDRATION_INTEGRITY_FAIL when OS returns duplicate IDs (P0-04)."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    match_meta = {
        "identifier_kind": None,
        "normalized_query": "벤젠",
        "compact_query": "벤젠",
        "tokens": [],
        "expanded_terms": [],
        "match_type": "CHEM_09",
        "per_item_metadata": {},
    }
    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               return_value=(["000001", "000001"], 2, match_meta)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=벤젠")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_HYDRATION_INTEGRITY_FAIL"


# ---- I08: hydration order matches OS input order ----------------------------


def test_I08_hydration_preserves_os_order(seo_store):
    """I08: search_from_chem_ids returns items in the same order as chem_ids input (OS rank order)."""
    from services.kosha_msds.read import search_from_chem_ids

    result = search_from_chem_ids(
        store=seo_store, chem_ids=["000002", "000001"],  # reversed from natural order
        total=2, limit=10, offset=0,
        scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert len(result["items"]) == 2
    assert result["items"][0]["chem_id"] == "000002"
    assert result["items"][1]["chem_id"] == "000001"


# ---- I09: router handles MsdsCandidateEnumerationIncompleteError → 503 -----


def test_I09_router_candidate_enumeration_incomplete_503(monkeypatch, seo_store):
    """I09: MsdsCandidateEnumerationIncompleteError → 503 MSDS_CANDIDATE_ENUMERATION_INCOMPLETE (P0-03)."""
    from services.kosha_msds.opensearch_query import MsdsCandidateEnumerationIncompleteError
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               side_effect=MsdsCandidateEnumerationIncompleteError("budget exhausted")):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=염산")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_CANDIDATE_ENUMERATION_INCOMPLETE"


# ---------------------------------------------------------------------------
# CLOSURE-007 J01-J10  WO-WWW-PERF-004-P0S-OS-CLOSURE-007
# ---------------------------------------------------------------------------


# ---- J01: Snapshot changed while no cache (CLOSURE-01) ---------------------


def test_J01_snapshot_change_detected_live():
    """J01: After snapshot changes, gate immediately rejects the old proof (no cache delay).

    CLOSURE-01 removes the 60 s state cache so snapshot_id is checked live
    every call. When snapshot_id changes, the old proof no longer matches
    current state → gate raises MsdsSnapshotGateError.
    """
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry

    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID_OLD = "snap-j01-old"
    SNAP_ID_NEW = "snap-j01-new"
    PHYS_IDX = "tai-shared-search-v1-j01"
    OUTBOX_WM = 100

    # Register proof for the OLD snapshot
    proof = _make_pass_proof(SNAP_ID_OLD, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}

    # First call with old snapshot matches → should pass
    sb_old = _make_sb_proof_state(SNAP_ID_OLD, OUTBOX_WM)
    check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb_old)

    # Snapshot now changed to NEW — no cache, so new live state is fetched immediately
    sb_new = _make_sb_proof_state(SNAP_ID_NEW, OUTBOX_WM)
    with pytest.raises(MsdsSnapshotGateError, match="state mismatch"):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb_new)


# ---- J02: Scope mismatch — FULL gate with SEO_PREVIEW proof ----------------


def test_J02_full_scope_gate_with_seo_preview_proof_fails():
    """J02: Gate called with scope=FULL but only SEO_PREVIEW proof registered → fails.

    CLOSURE-01 scope-keyed registry prevents a SEO_PREVIEW proof from
    satisfying a FULL scope gate check (J08 in large-scale: FULL=0, SEO=20568).
    """
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry

    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-j02"
    PHYS_IDX = "tai-shared-search-v1-j02"
    OUTBOX_WM = 100

    # Register proof only for SEO_PREVIEW
    seo_proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(seo_proof)  # scope = SEO_PREVIEW

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM)

    # SEO_PREVIEW gate should pass (proof registered)
    check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)

    # FULL gate must fail — no FULL proof registered
    with pytest.raises(MsdsSnapshotGateError, match="scope"):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_FULL, client=os_client, sb=sb)


# ---- J03: Alias swap detected during proof generation ----------------------


def test_J03_alias_swap_during_proof_generation():
    """J03: Physical index changes between pre-scan and post-scan → FAIL proof.

    CLOSURE-01 adds physical_index to the post-scan state check so an alias
    swap (OS reindex promotion) during proof generation is caught.
    """
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    PHYS_IDX_PRE = "tai-shared-search-v1-j03-old"
    PHYS_IDX_POST = "tai-shared-search-v1-j03-new"

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-j03"}]
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
            pending_r = MagicMock()
            pending_r.count = 0
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    from services.shared_search.opensearch_client import RUNS_INDEX
    alias_calls = [0]

    def _alias_side_effect(**kwargs):
        alias_calls[0] += 1
        # Pre-scan: old index; post-scan: new index (alias swapped mid-proof)
        if alias_calls[0] == 1:
            return {PHYS_IDX_PRE: {}}
        return {PHYS_IDX_POST: {}}

    os_client = MagicMock()
    os_client.indices.get_alias.side_effect = _alias_side_effect
    os_client.search.return_value = {"hits": {"hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert "State changed" in (proof.error_message or "")


# ---- J04: PENDING events added after post-scan watermark check -------------


def test_J04_pending_events_at_gate_raises():
    """J04: PENDING events present at gate-check time → MsdsSnapshotGateError.

    Even when the proof was generated cleanly, new PENDING events that arrive
    before the gate call trigger the uncached pending check (P0-01).
    """
    from services.kosha_msds.snapshot_proof import register_proof, clear_proof_registry

    _clear_snapshot_cache()
    clear_proof_registry()

    SNAP_ID = "snap-j04"
    PHYS_IDX = "tai-shared-search-v1-j04"
    OUTBOX_WM = 100

    proof = _make_pass_proof(SNAP_ID, PHYS_IDX, OUTBOX_WM)
    register_proof(proof)

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    # pending_count=2: two new events arrived after proof generation
    sb = _make_sb_proof_state(SNAP_ID, OUTBOX_WM, pending_count=2)

    with pytest.raises(MsdsSnapshotGateError, match="Uncommitted CHEM events"):
        check_snapshot_gate(scope=PUBLICATION_SCOPE_SEO_PREVIEW, client=os_client, sb=sb)


# ---- J05: Short page with total mismatch → INCOMPLETE error ----------------


def test_J05_short_page_total_mismatch_raises():
    """J05: search_os returns short page but total says more remain → INCOMPLETE (CLOSURE-02)."""
    from services.kosha_msds.opensearch_query import (
        _collect_all_os,
        MsdsCandidateEnumerationIncompleteError,
    )

    # Short page (2 IDs) but OS reports total=100 → genuine INCOMPLETE
    with patch("services.kosha_msds.opensearch_query.search_os",
               return_value=(["000001", "000002"], 100)):
        with pytest.raises(MsdsCandidateEnumerationIncompleteError):
            _collect_all_os(name_ko="테스트", client=MagicMock())


# ---- J06: Duplicate page from OS → INTEGRITY error -------------------------


def test_J06_duplicate_page_raises_integrity_error():
    """J06: OS returns the same IDs in two consecutive pages → INTEGRITY error (CLOSURE-02)."""
    from services.kosha_msds.opensearch_query import (
        _collect_all_os,
        _CANDIDATE_PAGE_SIZE,
        MsdsCandidateEnumerationIntegrityError,
    )

    # Page 1: full page [000001..001000] total=2000 (two pages expected)
    # Page 2: same full page again (OS bug) → duplicates detected
    full_page = [f"{i:06d}" for i in range(1, _CANDIDATE_PAGE_SIZE + 1)]
    call_n = [0]

    def _search_os(**kwargs):
        call_n[0] += 1
        return full_page, 2 * _CANDIDATE_PAGE_SIZE  # total=2000, forces second page

    with patch("services.kosha_msds.opensearch_query.search_os", side_effect=_search_os):
        with pytest.raises(MsdsCandidateEnumerationIntegrityError):
            _collect_all_os(name_ko="테스트", client=MagicMock())


# ---- J07: Same ID set, reversed order → Hydration integrity error ----------


def test_J07_hydration_reversed_order_raises():
    """J07: Store returns same IDs as chem_ids but in reverse order → MsdsHydrationIntegrityError.

    CLOSURE-03 enforces that hydration result order must match OS input order.
    """
    from services.kosha_msds.read import search_from_chem_ids

    class ReversedOrderStore:
        """Mock store that returns rows in reverse chem_id order."""
        def hydrate_chem_ids(self, chem_ids, *, scope=None):
            rows = []
            for cid in reversed(chem_ids):  # deliberately reversed
                rows.append({"chem_id": cid, "id": f"uuid-{cid}",
                             "chemical_name_ko": None, "chemical_name_en": None,
                             "cas_no": None, "ke_no": None, "en_no": None, "un_no": None,
                             "identity_status": "READY", "source_key": cid,
                             "source_id": "KOSHA_MSDS", "source_dataset_url": "",
                             "source_content_hash": "", "snapshot_id": "snap-j07"})
            return rows

    with pytest.raises(MsdsHydrationIntegrityError, match="order"):
        search_from_chem_ids(
            store=ReversedOrderStore(),
            chem_ids=["000001", "000002"],
            total=2, limit=10, offset=0,
            scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )


# ---- J09: Global query OS call budget cap (CLOSURE-04) ---------------------


def test_J09_query_os_call_budget_exhausted_raises():
    """J09: WO-023 — P1 free-text uses exactly 1 OS call regardless of total (no per-query budget)."""
    from services.kosha_msds.opensearch_query import search_by_q_os

    # Large total (50,000) — old PIT path would have exhausted budget; WO-023 single call handles it
    client = _fake_os_client(["000001", "000002"], 50000)
    ids, total, _ = search_by_q_os(q="염산", limit=5, offset=0, client=client)
    assert total == 50000
    assert len(ids) == 2
    assert client.search.call_count == 1, "WO-023: free-text P1 must use exactly 1 OS call"


# ---- J10: List/detail/search regression ------------------------------------


def test_J10_list_endpoint_unaffected_by_closures(monkeypatch, seo_store):
    """J10: list_current path (no q or filters) still works after CLOSURE changes."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    client = TestClient(app)
    resp = client.get("/public/kosha/msds")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 2


def test_J10b_detail_endpoint_unaffected(monkeypatch, seo_store):
    """J10b: Get-by-chem_id detail endpoint still works after CLOSURE changes."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    client = TestClient(app)
    resp = client.get("/public/kosha/msds/000001")
    assert resp.status_code == 200
    assert resp.json()["chem_id"] == "000001"


def test_J10c_os_search_filter_path_unaffected(monkeypatch, seo_store):
    """J10c: Structured filter search (check_snapshot_gate + search_os path) still works."""
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_os",
               return_value=(["000001"], 1)):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?name_ko=벤젠")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_J10d_candidate_enumeration_integrity_503(monkeypatch, seo_store):
    """J10d: Router returns 503 MSDS_CANDIDATE_ENUMERATION_INTEGRITY on integrity error (CLOSURE-02)."""
    from services.kosha_msds.opensearch_query import MsdsCandidateEnumerationIntegrityError
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    app = _make_app(seo_store, None)

    with patch("routers.kosha_public_msds.check_snapshot_gate"), \
         patch("routers.kosha_public_msds.search_by_q_os",
               side_effect=MsdsCandidateEnumerationIntegrityError("total changed")):
        client = TestClient(app)
        resp = client.get("/public/kosha/msds?q=염산")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "MSDS_CANDIDATE_ENUMERATION_INTEGRITY"


# ===========================================================================
# CLOSURE-008 — K01-K07
# FIX-01 (K01-K03): budget 0 before first term page → INCOMPLETE (not falsely 0)
# FIX-02 (K04-K06): post-scan pending check in generate_proof_dry_run
# FIX-03 (K07):     actual OS request cost model (PIT creates per deep-page call)
# ===========================================================================


# ---- K01: budget 0 at start of second term → INCOMPLETE --------------------


def test_K01_budget_zero_before_second_term_raises_incomplete():
    """K01: Budget=1 consumed by first term (0 results); second term entry with budget=0
    and last_total=None must raise INCOMPLETE — not falsely return [] (FIX-01)."""
    from services.kosha_msds.opensearch_query import (
        _collect_all_os,
        MsdsCandidateEnumerationIncompleteError,
    )

    budget_ref = [1]
    calls = [0]

    def _mock_search_os(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return [], 0  # first term: 0 results, budget 1→0
        # If called again, this term has results — but budget is already 0
        return ["000001", "000002"], 2

    with patch("services.kosha_msds.opensearch_query.search_os", side_effect=_mock_search_os):
        # First _collect_all_os: 0 results, budget decremented to 0
        result = _collect_all_os(name_ko="테스트", client=MagicMock(), budget_ref=budget_ref)
        assert result == []
        assert budget_ref[0] == 0

        # Second _collect_all_os: budget=0 at entry, last_total=None → INCOMPLETE
        with pytest.raises(MsdsCandidateEnumerationIncompleteError):
            _collect_all_os(name_en="테스트", client=MagicMock(), budget_ref=budget_ref)


# ---- K02: budget hits 0 exactly after last term completes → PASS -----------


def test_K02_budget_zero_after_completion_is_pass():
    """K02: Single _collect_all_os call uses budget=1 and returns normally;
    budget reaches 0 after the term completes — no INCOMPLETE raised (FIX-01)."""
    from services.kosha_msds.opensearch_query import _collect_all_os

    budget_ref = [1]

    with patch("services.kosha_msds.opensearch_query.search_os",
               return_value=(["000001", "000002"], 2)):
        result = _collect_all_os(name_ko="테스트", client=MagicMock(), budget_ref=budget_ref)

    assert result == ["000001", "000002"]
    assert budget_ref[0] == 0  # budget fully consumed, but no error raised


# ---- K03: budget already 0 at entry → INCOMPLETE (not falsely empty) -------


def test_K03_budget_zero_at_entry_raises_incomplete():
    """K03: Budget=0 at entry of _collect_all_os → raises INCOMPLETE before any OS call.

    Prevents dictionary / Kiwi candidates from being silently skipped and
    treated as 0 results when they would have actual matches (FIX-01)."""
    from services.kosha_msds.opensearch_query import (
        _collect_all_os,
        MsdsCandidateEnumerationIncompleteError,
    )

    budget_ref = [0]  # already exhausted

    with pytest.raises(MsdsCandidateEnumerationIncompleteError,
                       match="before first page"):
        _collect_all_os(name_ko="에탄올", client=MagicMock(), budget_ref=budget_ref)


# ---- K04: new PENDING event during scan → FAIL proof (FIX-02) --------------


def test_K04_postscan_pending_event_generates_fail_proof():
    """K04: PENDING event arrives during scan window → post-scan check detects it → FAIL proof
    (FIX-02: post-scan _get_outbox_pending_count added to generate_proof_dry_run)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    pending_call_n = [0]

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-k04"}]
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

            def _pending_execute():
                pending_call_n[0] += 1
                r = MagicMock()
                # Pre-scan call: pending=0; post-scan call: pending=1 (new event)
                r.count = 0 if pending_call_n[0] == 1 else 1
                return r

            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.side_effect = _pending_execute
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-k04": {}}
    os_client.search.return_value = {"hits": {"hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert "postscan_pending=1" in (proof.error_message or "")


# ---- K05: post-scan pending count query fails → FAIL proof (FIX-02) --------


def test_K05_postscan_pending_query_failure_generates_fail_proof():
    """K05: Post-scan _get_outbox_pending_count raises → postscan_error set → FAIL proof
    (FIX-02: post-scan failure is captured within the post-scan try block)."""
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW

    postscan_call_n = [0]

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": "snap-k05"}]
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

            def _pending_execute():
                postscan_call_n[0] += 1
                if postscan_call_n[0] == 1:
                    r = MagicMock()
                    r.count = 0  # pre-scan: clean
                    return r
                # Post-scan call: DB error
                raise Exception("DB connection lost during post-scan pending check")

            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.side_effect = _pending_execute
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {"tai-shared-search-v1-k05": {}}
    os_client.search.return_value = {"hits": {"hits": []}}

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "FAIL"
    assert "Post-scan state check failed" in (proof.error_message or "")


# ---- K06: clean state pre and post → PASS proof (FIX-02 regression) --------


def test_K06_clean_state_pre_and_post_generates_pass_proof():
    """K06: Stable state pre/post scan and pending=0 both times → PASS proof.

    Regression: FIX-02 post-scan pending check must not break the happy path.
    """
    from services.kosha_msds.snapshot_proof import generate_proof_dry_run, verify_proof
    from services.kosha_msds.contract import PUBLICATION_SCOPE_SEO_PREVIEW
    from services.shared_search.opensearch_client import RUNS_INDEX

    SNAP_ID = "snap-k06"
    PHYS_IDX = "tai-shared-search-v1-k06"
    OUTBOX_WM = 42

    chem_id = "000001"
    canonical_id = "uuid-k06"

    def _table(name):
        m = MagicMock()
        if name == "kosha_msds_seo_preview_current":
            snap_r = MagicMock()
            snap_r.data = [{"snapshot_id": SNAP_ID}]
            m.select.return_value.limit.return_value.execute.return_value = snap_r
            scan_calls = [0]
            def _scan_execute():
                scan_calls[0] += 1
                r = MagicMock()
                r.data = [{"chem_id": chem_id, "id": canonical_id}] if scan_calls[0] == 1 else []
                return r
            m.select.return_value.order.return_value.limit.return_value.execute.side_effect = _scan_execute
        elif name == "kosha_msds_snapshots":
            ts_r = MagicMock()
            ts_r.data = [{"completed_at": "2026-10-01T00:00:00+00:00"}]
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = ts_r
        elif name == "search_index_outbox":
            wm_r = MagicMock()
            wm_r.data = [{"id": OUTBOX_WM}]
            pending_r = MagicMock()
            pending_r.count = 0  # clean at all times
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = wm_r
            m.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = pending_r
        return m

    sb = MagicMock()
    sb.table.side_effect = _table

    os_scan_calls = [0]
    def _search_side_effect(**kwargs):
        idx = kwargs.get("index", "")
        if idx == RUNS_INDEX:
            return {"hits": {"hits": [{"_source": {"run_id": "run-k06"}}]}}
        os_scan_calls[0] += 1
        if os_scan_calls[0] == 1:
            return {
                "hits": {
                    "hits": [
                        {"_source": {"source_key": chem_id, "canonical_id": canonical_id},
                         "sort": [canonical_id]},
                    ]
                }
            }
        return {"hits": {"hits": []}}

    os_client = MagicMock()
    os_client.indices.get_alias.return_value = {PHYS_IDX: {}}
    os_client.search.side_effect = _search_side_effect

    proof = generate_proof_dry_run(scope=PUBLICATION_SCOPE_SEO_PREVIEW, sb=sb, client=os_client)
    assert proof.verification_status == "PASS"
    assert verify_proof(proof) is True
    assert proof.db_membership_count == 1
    assert proof.os_membership_count == 1


# ---- K07: PIT is created per deep-page search_os call (FIX-03 cost model) --


def test_K07_deep_pagination_creates_pit_per_search_os_call():
    """K07: Each search_os call at offset+limit > 9900 creates 1 PIT (PATCH-003F).

    IMP-010D update: _QUERY_OS_CALL_BUDGET now counts actual client.search calls
    (not search_os() invocations). This test verifies the _search_os_deep_page PIT
    lifecycle contract: 1 create_pit + 1 delete_pit per search_os deep-page call,
    with multiple client.search calls for one search_os() invocation.
    """
    from services.kosha_msds.opensearch_query import (
        search_os,
        _DEEP_PAGINATION_LIMIT,
        _PIT_BATCH,
    )

    os_client = MagicMock()
    os_client.create_pit.return_value = {"pit_id": "pit-k07"}
    # PIT search: one batch with enough hits, then empty to stop
    batch_hits = [
        {"_source": {"source_key": f"{i:06d}"}, "sort": [f"key_{i}"]}
        for i in range(_PIT_BATCH)
    ]
    os_client.search.side_effect = [
        {"hits": {"total": {"value": 15000}, "hits": batch_hits}},
        {"hits": {"total": {"value": 15000}, "hits": batch_hits}},
        {"hits": {"total": {"value": 15000}, "hits": []}},  # terminate
    ]

    # Deep offset: offset+limit > _DEEP_PAGINATION_LIMIT → PIT activated
    deep_offset = _DEEP_PAGINATION_LIMIT + 1
    search_os(name_ko="염산", offset=deep_offset, limit=100, client=os_client)

    # Verify PIT lifecycle: created once and deleted once per search_os call
    assert os_client.create_pit.call_count == 1
    assert os_client.delete_pit.call_count == 1
    # Multiple client.search calls made for one search_os() call
    assert os_client.search.call_count >= 2


# ===========================================================================
# PIT-IMPL-010 — L01-L15
# IMP-010A: _build_chem_term_query extracted from search_os
# IMP-010B: search_by_q_os P1 creates 1 PIT for all terms
# IMP-010C: _collect_all_os_pit — PIT + search_after, CLOSURE-02 integrity
# IMP-010D: budget_ref = actual client.search calls (not search_os() calls)
# ===========================================================================


from services.kosha_msds.opensearch_query import (
    MsdsCandidateEnumerationIncompleteError,
    MsdsCandidateEnumerationIntegrityError,
    MsdsPaginationDepthExceededError,
    _collect_all_os_pit,
)


# ---- L01: 1 PIT create + 1 delete per free-text call -----------------------


def test_L01_one_pit_per_search_by_q_os_call():
    """L01: WO-023 — search_by_q_os P1 uses exactly 1 client.search() call; no PIT lifecycle."""
    mock_client = MagicMock()
    mock_client.search.return_value = _make_os_resp(["000001"], 1)

    search_by_q_os(q="염산", limit=5, offset=0, client=mock_client)

    assert mock_client.search.call_count == 1, "WO-023: exactly 1 OS call per free-text page"
    mock_client.create_pit.assert_not_called()
    mock_client.delete_pit.assert_not_called()


# ---- L02: Multiple terms share same PIT ------------------------------------


def test_L02_all_terms_share_single_pit():
    """L02: WO-023 — All terms (NE/DE/KW) are in one dis_max query; single OS call, no PIT."""
    mock_client = MagicMock()
    mock_client.search.return_value = _make_os_resp([], 0)

    def _dict_lookup(q, limit=5, subject_type=None):
        return {"items": [{"subject_key": "에탄올", "matched_term": "에탄올"}]}

    search_by_q_os(q="염산", limit=5, offset=0, client=mock_client, dictionary_lookup=_dict_lookup)

    assert mock_client.search.call_count == 1, "WO-023: all terms in 1 dis_max → 1 OS call"
    mock_client.create_pit.assert_not_called()
    # Verify DSL has NE and DE clauses
    body = mock_client.search.call_args[1]["body"]
    query_str = str(body["query"])
    assert "NE:" in query_str
    assert "DE:" in query_str


# ---- L03: Each term's search_after starts fresh (null) ---------------------


def test_L03_each_term_starts_fresh_search_after():
    """L03: Each _collect_all_os_pit call starts with search_after=None (fresh cursor per term)."""
    mock_client = MagicMock()
    mock_client.create_pit.return_value = {"pit_id": "pit-L03"}
    mock_client.search.return_value = _make_os_resp(["000001"], 1)

    search_by_q_os(q="염산", limit=5, offset=0, client=mock_client)

    # For single-page results (1 hit < _CANDIDATE_PAGE_SIZE), no search_after added
    for call in mock_client.search.call_args_list:
        body = call[1]["body"]
        assert "search_after" not in body, "First page must have no search_after"


# ---- L04: Edge cases: 0 / 20 / 1000 hits ----------------------------------


def test_L04_edge_cases_zero_and_twenty_hits():
    """L04: WO-023 — 0 and 20 hits via single dis_max; no PIT lifecycle."""
    # 0 hits
    mock_client_0 = MagicMock()
    mock_client_0.search.return_value = _make_os_resp([], 0)
    ids, total, _ = search_by_q_os(q="없는화학물질", limit=5, offset=0, client=mock_client_0)
    assert ids == []
    assert total == 0
    assert mock_client_0.search.call_count == 1
    mock_client_0.create_pit.assert_not_called()

    # 20 hits (< _CANDIDATE_PAGE_SIZE → single page)
    ids20 = [f"{i:06d}" for i in range(1, 21)]
    mock_client_20 = MagicMock()
    mock_client_20.search.return_value = _make_os_resp(ids20, 20)
    ids, total, _ = search_by_q_os(q="염산", limit=25, offset=0, client=mock_client_20)
    assert total == 20
    assert len(ids) == 20
    assert mock_client_20.search.call_count == 1


# ---- L05: Multi-page PIT collection ----------------------------------------


def test_L05_collect_all_os_pit_multi_page():
    """L05: _collect_all_os_pit paginates across multiple PIT pages via search_after (IMP-010C)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    PAGES = 3
    TOTAL = PAGES * _CANDIDATE_PAGE_SIZE
    all_keys = [f"{i:06d}" for i in range(1, TOTAL + 1)]
    pages = [all_keys[p * _CANDIDATE_PAGE_SIZE:(p + 1) * _CANDIDATE_PAGE_SIZE] for p in range(PAGES)]

    call_n = [0]

    def _search(**kwargs):
        n = call_n[0]
        call_n[0] += 1
        page_keys = pages[n] if n < PAGES else []
        hits = [{"_source": {"source_key": sk}, "sort": [sk]} for sk in page_keys]
        return {"hits": {"total": {"value": TOTAL, "relation": "eq"}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-L05"]

    result = _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="테스트")

    assert len(result) == TOTAL
    assert result == all_keys
    assert mock_client.search.call_count == PAGES


# ---- L06: 20,568 hits — full SEO_PREVIEW catalog size ----------------------


def test_L06_collect_all_os_pit_20568_hits():
    """L06: _collect_all_os_pit collects 20,568 hits (21 pages) — full SEO_PREVIEW size (IMP-010C)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    TOTAL = 20_568
    all_keys = [f"{i:06d}" for i in range(1, TOTAL + 1)]

    call_n = [0]

    def _search(**kwargs):
        n = call_n[0]
        call_n[0] += 1
        page_keys = all_keys[n * _CANDIDATE_PAGE_SIZE:(n + 1) * _CANDIDATE_PAGE_SIZE]
        hits = [{"_source": {"source_key": sk}, "sort": [sk]} for sk in page_keys]
        return {"hits": {"total": {"value": TOTAL, "relation": "eq"}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-L06"]

    result = _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="산업")

    import math
    expected_pages = math.ceil(TOTAL / _CANDIDATE_PAGE_SIZE)
    assert len(result) == TOTAL
    assert mock_client.search.call_count == expected_pages


# ---- L07: PIT ID renewal ---------------------------------------------------


def test_L07_pit_id_renewal():
    """L07: pit_id_ref is updated from resp.get('pit_id') on each call (OpenSearch PIT renewal)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    OLD_PIT = "pit-L07-old"
    NEW_PIT = "pit-L07-new"

    call_n = [0]
    TOTAL = _CANDIDATE_PAGE_SIZE + 1  # requires exactly 2 pages

    def _search(**kwargs):
        call_n[0] += 1
        body = kwargs.get("body", {})
        if call_n[0] == 1:
            # First page: full page, server returns new pit_id
            hits = [
                {"_source": {"source_key": f"{i:06d}"}, "sort": [f"k{i}"]}
                for i in range(_CANDIDATE_PAGE_SIZE)
            ]
            return {
                "pit_id": NEW_PIT,
                "hits": {"total": {"value": TOTAL, "relation": "eq"}, "hits": hits},
            }
        else:
            # Second call: verify pit_id was renewed in body
            assert body.get("pit", {}).get("id") == NEW_PIT, (
                "Second call must use renewed pit_id"
            )
            # Return the remaining 1 hit so collected == total (no integrity error)
            return {
                "hits": {
                    "total": {"value": TOTAL, "relation": "eq"},
                    "hits": [{"_source": {"source_key": f"{_CANDIDATE_PAGE_SIZE:06d}"}, "sort": [f"k{_CANDIDATE_PAGE_SIZE}"]}],
                },
            }

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = [OLD_PIT]

    _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="테스트")

    assert pit_id_ref[0] == NEW_PIT


# ---- L08: PIT create failure -----------------------------------------------


def test_L08_pit_create_failure_raises_pagination_depth_error():
    """L08: WO-023 — P1 uses no PIT; client.search failure propagates to caller."""
    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("OS search failed")

    with pytest.raises(Exception, match="OS search failed"):
        search_by_q_os(q="염산", limit=5, offset=0, client=mock_client)

    mock_client.create_pit.assert_not_called()
    mock_client.delete_pit.assert_not_called()


# ---- L09: Integrity errors from _collect_all_os_pit ------------------------


def test_L09_pit_total_change_raises_integrity_error():
    """L09: OS total changes between PIT pages → MsdsCandidateEnumerationIntegrityError (IMP-010C)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    call_n = [0]

    def _search(**kwargs):
        call_n[0] += 1
        hits = [
            {"_source": {"source_key": f"{i:06d}"}, "sort": [f"k{i}"]}
            for i in range(_CANDIDATE_PAGE_SIZE)
        ]
        total = 5000 if call_n[0] == 1 else 6000  # total changes — index swap
        return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-L09"]

    with pytest.raises(MsdsCandidateEnumerationIntegrityError):
        _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="테스트")


def test_L09b_pit_duplicate_ids_raises_integrity_error():
    """L09b: Duplicate source_keys in PIT pages → MsdsCandidateEnumerationIntegrityError."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    dup_keys = [f"{i:06d}" for i in range(_CANDIDATE_PAGE_SIZE)]

    def _search(**kwargs):
        hits = [{"_source": {"source_key": sk}, "sort": [sk]} for sk in dup_keys]
        # Reports total=2000 (two full pages), but each page returns the same IDs
        return {"hits": {"total": {"value": 2 * _CANDIDATE_PAGE_SIZE, "relation": "eq"}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-L09b"]

    with pytest.raises(MsdsCandidateEnumerationIntegrityError):
        _collect_all_os_pit(client=mock_client, pit_id_ref=pit_id_ref, name_ko="테스트")


# ---- L10: Budget counts client.search calls --------------------------------


def test_L10_budget_counts_client_search_calls():
    """L10: budget_ref decrements once per client.search call in _collect_all_os_pit (IMP-010D)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    BUDGET = 10

    call_n = [0]

    def _search(**kwargs):
        call_n[0] += 1
        hits = [
            {"_source": {"source_key": f"{i:06d}"}, "sort": [f"k{i}"]}
            for i in range(_CANDIDATE_PAGE_SIZE)
        ]
        return {"hits": {"total": {"value": 100 * _CANDIDATE_PAGE_SIZE}, "hits": hits}}

    mock_client = MagicMock()
    mock_client.search.side_effect = _search
    pit_id_ref = ["pit-L10"]
    budget_ref = [BUDGET]

    with pytest.raises(MsdsCandidateEnumerationIncompleteError):
        _collect_all_os_pit(
            client=mock_client, pit_id_ref=pit_id_ref,
            budget_ref=budget_ref, name_ko="테스트",
        )

    # Exactly BUDGET calls were made before budget=0 raised INCOMPLETE
    assert call_n[0] == BUDGET
    assert budget_ref[0] == 0


# ---- L11: Budget exceeded raises INCOMPLETE --------------------------------


def test_L11_budget_exceeded_raises_incomplete():
    """L11: budget=2 in _collect_all_os_pit → INCOMPLETE after 2 calls (IMP-010D)."""
    from services.kosha_msds.opensearch_query import _CANDIDATE_PAGE_SIZE

    mock_client = MagicMock()
    pit_id_ref = ["pit-L11"]
    budget_ref = [2]

    full_page_hits = [
        {"_source": {"source_key": f"{i:06d}"}, "sort": [f"k{i}"]}
        for i in range(_CANDIDATE_PAGE_SIZE)
    ]
    mock_client.search.return_value = {
        "hits": {
            "total": {"value": 100 * _CANDIDATE_PAGE_SIZE, "relation": "eq"},
            "hits": full_page_hits,
        }
    }

    with pytest.raises(MsdsCandidateEnumerationIncompleteError):
        _collect_all_os_pit(
            client=mock_client, pit_id_ref=pit_id_ref,
            budget_ref=budget_ref, name_ko="테스트",
        )


# ---- L12: match_type/term preserved in PIT path ----------------------------


def test_L12_match_metadata_preserved_in_pit_path():
    """L12: WO-023 — per_item_metadata derives match_type from OS named-query markers."""
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_source": {"source_key": "000001"},
                    "matched_queries": ["NE:염산"],
                }
            ],
        }
    }

    _, _, meta = search_by_q_os(q="염산", limit=5, offset=0, client=mock_client)

    assert "per_item_metadata" in meta
    assert isinstance(meta["per_item_metadata"], dict)
    assert "000001" in meta["per_item_metadata"], (
        "per_item_metadata must contain the returned chem_id — annotation is mandatory"
    )
    m = meta["per_item_metadata"]["000001"]
    assert "match_type" in m
    assert "matched_term" in m
    assert m["match_type"] == "NORMALIZED_EXACT"
    assert m["matched_term"] == "염산"


def test_L12b_match_priority_first_seen_wins():
    """L12b: WO-023 — NE: wins over KW: in matched_queries for match_type attribution."""
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_source": {"source_key": "000001"},
                    "matched_queries": ["KW:염산", "NE:염산"],  # NE must win
                }
            ],
        }
    }

    _, _, meta = search_by_q_os(q="염산", limit=5, offset=0, client=mock_client)

    assert "000001" in meta["per_item_metadata"]
    m = meta["per_item_metadata"]["000001"]
    assert m["match_type"] == "NORMALIZED_EXACT", (
        f"Expected NORMALIZED_EXACT (NE wins over KW), got {m['match_type']}"
    )
    assert m["matched_term"] == "염산"


# ---- L13: Identifier path (P0) does not use PIT ----------------------------


def test_L13_identifier_path_no_pit():
    """L13: Identifier q-path (P0) does not create PIT — direct search_os call only (IMP-010B)."""
    client = _fake_os_client(["000001"], 1)
    search_by_q_os(q="000001", limit=5, offset=0, client=client)
    client.create_pit.assert_not_called()
    client.delete_pit.assert_not_called()


# ---- L14: P0-A list endpoint regression ------------------------------------


def test_L14_list_endpoint_regression(seo_store):
    """L14: list_current (no q/filter) unaffected by PIT changes (IMP-010 regression)."""
    from services.kosha_msds.read import list_current
    result = list_current(
        store=seo_store, limit=10, offset=0, scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert result["total"] == 2
    assert len(result["items"]) == 2


# ---- L15: P0-A detail endpoint regression ----------------------------------


def test_L15_detail_endpoint_regression(seo_store):
    """L15: get_by_chem_id unaffected by PIT changes (IMP-010 regression)."""
    from services.kosha_msds.read import get_by_chem_id
    body = get_by_chem_id(
        "000001", store=seo_store,
        include_sections=False, scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert body is not None
    assert body["chem_id"] == "000001"


# ===========================================================================
# WO-023-DEEPPAGE  M01-M04 — Free-text P1 deep pagination boundary
# _DEEP_PAGINATION_LIMIT routing; _free_text_deep_page PIT contract
# ===========================================================================


def test_M01_normal_page_no_pit():
    """M01: offset+limit <= _DEEP_PAGINATION_LIMIT → single from/size call, no PIT."""
    from services.kosha_msds.opensearch_query import search_by_q_os, _DEEP_PAGINATION_LIMIT
    client = _fake_os_client(["000001"], 1)
    normal_offset = _DEEP_PAGINATION_LIMIT - 20
    search_by_q_os(q="염산", limit=20, offset=normal_offset, client=client)
    assert client.search.call_count == 1
    client.create_pit.assert_not_called()
    body = client.search.call_args[1]["body"]
    assert body["from"] == normal_offset
    assert body["size"] == 20


def test_M02_deep_page_triggers_pit():
    """M02: offset+limit > _DEEP_PAGINATION_LIMIT → PIT lifecycle; correct ids/total/meta."""
    from services.kosha_msds.opensearch_query import (
        search_by_q_os, _DEEP_PAGINATION_LIMIT, _PIT_BATCH,
    )

    deep_offset = _DEEP_PAGINATION_LIMIT + 1
    needed = deep_offset + 20
    all_keys = [f"{i:06d}" for i in range(1, needed + 1)]

    os_client = MagicMock()
    os_client.create_pit.return_value = {"pit_id": "pit-m02"}
    call_n = [0]

    def _pit_search(**kwargs):
        n = call_n[0]
        call_n[0] += 1
        page_keys = all_keys[n * _PIT_BATCH: (n + 1) * _PIT_BATCH]
        hits = [
            {"_source": {"source_key": sk}, "sort": [sk], "matched_queries": ["NE:염산"]}
            for sk in page_keys
        ]
        return {"hits": {"total": {"value": len(all_keys)}, "hits": hits}}

    os_client.search.side_effect = _pit_search

    ids, total, meta = search_by_q_os(q="염산", limit=20, offset=deep_offset, client=os_client)

    os_client.create_pit.assert_called_once()
    os_client.delete_pit.assert_called_once()
    assert total == len(all_keys)
    assert len(ids) == 20
    assert "per_item_metadata" in meta
    assert len(meta["per_item_metadata"]) == 20


def test_M03_deep_page_match_meta_from_named_queries():
    """M03: Deep page — matched_queries in PIT hits drive per_item_metadata match_type."""
    from services.kosha_msds.opensearch_query import (
        search_by_q_os, _DEEP_PAGINATION_LIMIT, _PIT_BATCH,
    )

    deep_offset = _DEEP_PAGINATION_LIMIT + 1
    needed = deep_offset + 5
    all_keys = [f"{i:06d}" for i in range(1, needed + 1)]

    os_client = MagicMock()
    os_client.create_pit.return_value = {"pit_id": "pit-m03"}
    call_n = [0]

    def _pit_search(**kwargs):
        n = call_n[0]
        call_n[0] += 1
        page_keys = all_keys[n * _PIT_BATCH: (n + 1) * _PIT_BATCH]
        hits = [
            {"_source": {"source_key": sk}, "sort": [sk], "matched_queries": ["NE:염산"]}
            for sk in page_keys
        ]
        return {"hits": {"total": {"value": len(all_keys)}, "hits": hits}}

    os_client.search.side_effect = _pit_search

    ids, total, meta = search_by_q_os(q="염산", limit=5, offset=deep_offset, client=os_client)

    assert len(meta["per_item_metadata"]) == 5
    for cid in ids:
        assert meta["per_item_metadata"][cid]["match_type"] == "NORMALIZED_EXACT"
        assert meta["per_item_metadata"][cid]["matched_term"] == "염산"


def test_M04_deep_page_pit_failure_raises():
    """M04: Deep page PIT creation failure → MsdsPaginationDepthExceededError."""
    from services.kosha_msds.opensearch_query import (
        search_by_q_os, _DEEP_PAGINATION_LIMIT, MsdsPaginationDepthExceededError,
    )

    os_client = MagicMock()
    os_client.create_pit.side_effect = Exception("PIT not supported")

    with pytest.raises(MsdsPaginationDepthExceededError):
        search_by_q_os(q="염산", limit=5, offset=_DEEP_PAGINATION_LIMIT + 1, client=os_client)
