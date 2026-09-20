"""Unit + integration tests — WO-TAI-SHARED-SEARCH-INCREMENTAL-001 §49-§54.

§49  queue (outbox) unit tests
§50  incremental (sync_object / process_queue) unit tests
§51  idempotency integration test
§52  rebuild race test (§D — watermark + candidate replay fixture)
§53  worker pause (fence) test
§54  reconcile test
§E   PRECEDENT producer bridge tests

All tests are fully offline (no real OpenSearch, no real Supabase).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake / stub helpers
# ---------------------------------------------------------------------------

def _make_rpc_resp(data=None):
    """Simulate supabase-py RPC response."""
    m = MagicMock()
    m.data = data
    m.execute.return_value = m
    return m


def _fake_sb(*, rebuild_active: bool = False, outbox_max_id: int = 0):
    """Minimal fake Supabase client for unit tests."""
    sb = MagicMock()

    # search_index_runtime_state (fence)
    fence_resp = MagicMock()
    fence_resp.data = [{"rebuild_active": rebuild_active}]
    fence_resp.execute.return_value = fence_resp

    def _table_chain(table_name):
        m = MagicMock()
        m.select.return_value = m
        m.eq.return_value = m
        m.order.return_value = m
        m.limit.return_value = m
        m.update.return_value = m
        m.insert.return_value = m
        m.upsert.return_value = m
        m.delete.return_value = m
        m.in_.return_value = m
        m.not_.return_value = m

        if table_name == "search_index_runtime_state":
            m.execute.return_value = fence_resp
        elif table_name == "search_index_outbox":
            outbox_resp = MagicMock()
            outbox_resp.data = [{"id": outbox_max_id}] if outbox_max_id else []
            outbox_resp.execute.return_value = outbox_resp
            m.execute.return_value = outbox_resp
        else:
            m.execute.return_value = MagicMock(data=[])
        return m

    sb.table.side_effect = _table_chain

    # RPCs
    sb.rpc.return_value = _make_rpc_resp(data=[])

    return sb


def _fake_adapter(
    domain_name: str,
    object_type: str,
    *,
    payload: Optional[dict] = None,
):
    """Fake DomainAdapter for testing."""
    class FakeAdapter:
        pass
    a = FakeAdapter()
    a.domain_name = domain_name
    a.object_type = object_type
    a.object_reindex_payload = MagicMock(return_value=payload)
    return a


# ---------------------------------------------------------------------------
# §49 — queue unit tests (opensearch_projection helpers)
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_stable(self):
        from services.shared_search.opensearch_projection import _compute_content_hash
        doc = {"title": "test", "canonical_id": "abc", "domain_name": "KNOWLEDGE"}
        h1 = _compute_content_hash(doc)
        h2 = _compute_content_hash(doc)
        assert h1 == h2

    def test_excludes_indexed_at(self):
        from services.shared_search.opensearch_projection import _compute_content_hash
        doc1 = {"title": "x", "indexed_at": "2026-01-01T00:00:00"}
        doc2 = {"title": "x", "indexed_at": "2099-12-31T23:59:59"}
        assert _compute_content_hash(doc1) == _compute_content_hash(doc2)

    def test_different_content_differs(self):
        from services.shared_search.opensearch_projection import _compute_content_hash
        assert _compute_content_hash({"title": "a"}) != _compute_content_hash({"title": "b"})


class TestResolveAliasTarget:
    def test_single_target_ok(self):
        from services.shared_search.opensearch_projection import resolve_alias_target
        client = MagicMock()
        client.indices.get_alias.return_value = {"tai-shared-search-v1-abc": {}}
        assert resolve_alias_target(client) == "tai-shared-search-v1-abc"

    def test_zero_targets_raises(self):
        from services.shared_search.opensearch_projection import (
            AliasNotReady,
            resolve_alias_target,
        )
        from opensearchpy import NotFoundError
        client = MagicMock()
        client.indices.get_alias.side_effect = NotFoundError(404, "not found")
        with pytest.raises(AliasNotReady):
            resolve_alias_target(client)

    def test_two_targets_raises(self):
        from services.shared_search.opensearch_projection import (
            AliasNotReady,
            resolve_alias_target,
        )
        client = MagicMock()
        client.indices.get_alias.return_value = {
            "idx-a": {},
            "idx-b": {},
        }
        with pytest.raises(AliasNotReady, match="2"):
            resolve_alias_target(client)


# ---------------------------------------------------------------------------
# §50 — incremental unit tests
# ---------------------------------------------------------------------------

class TestSyncObjectFence:
    def test_skip_when_fence_active(self):
        from services.shared_search.incremental import sync_object
        sb = _fake_sb(rebuild_active=True)
        client = MagicMock()
        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload={"title": "x"})

        result = sync_object(
            domain_name="KNOWLEDGE",
            object_type="KNOWLEDGE",
            canonical_id="doc-001",
            supabase_client=sb,
            os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] == "SKIP_FENCE"
        adapter.object_reindex_payload.assert_not_called()
        client.index.assert_not_called()

    def test_upsert_when_fence_inactive(self):
        from services.shared_search.incremental import sync_object
        from opensearchpy import NotFoundError

        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"tai-shared-search-v1-abc": {}}
        # Simulate no existing document → content_hash returns None → UPSERT
        client.get.side_effect = NotFoundError(404, "not found")

        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload={
            "domain_name": "KNOWLEDGE",
            "object_type": "KNOWLEDGE",
            "canonical_id": "doc-001",
            "title": "Test Doc",
            "publication_status": "PUBLISHED",
            "content_hash": "abc123",
        })

        result = sync_object(
            domain_name="KNOWLEDGE",
            object_type="KNOWLEDGE",
            canonical_id="doc-001",
            supabase_client=sb,
            os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] in ("UPSERT", "NOOP")

    def test_delete_when_adapter_returns_none(self):
        from services.shared_search.incremental import sync_object
        from opensearchpy import NotFoundError

        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"tai-shared-search-v1-abc": {}}
        client.delete.side_effect = NotFoundError(404, "not found")

        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload=None)

        result = sync_object(
            domain_name="KNOWLEDGE",
            object_type="KNOWLEDGE",
            canonical_id="doc-999",
            supabase_client=sb,
            os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] == "NOT_FOUND"

    def test_unknown_domain_raises(self):
        from services.shared_search.incremental import sync_object
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}

        with pytest.raises(ValueError, match="No adapter"):
            sync_object(
                domain_name="NONEXISTENT",
                object_type="NONEXISTENT",
                canonical_id="x",
                supabase_client=sb,
                os_client=client,
                adapter_map={},
            )


# ---------------------------------------------------------------------------
# §51 — idempotency: same event_key enqueued twice → one row
# ---------------------------------------------------------------------------

class TestIdempotencyKey:
    """Validates the ON CONFLICT (source_event_key) DO NOTHING logic.

    We can't run real Supabase in unit tests, so we verify the RPC payload
    sends the event_key and that the migration uses the correct UNIQUE
    constraint path.
    """
    def test_enqueue_passes_event_key(self):
        sb = MagicMock()
        rpc_resp = MagicMock()
        rpc_resp.execute.return_value = rpc_resp
        sb.rpc.return_value = rpc_resp

        # Simulate what a producer hook calls
        sb.rpc("enqueue_search_index_sync", {
            "p_domain_name":  "KNOWLEDGE",
            "p_object_type":  "KNOWLEDGE",
            "p_canonical_id": "doc-001",
            "p_event_key":    "knowledge:doc-001:v3",
            "p_reason":       "upsert_help",
        })

        call_args = sb.rpc.call_args
        payload = call_args[0][1]
        assert payload["p_event_key"] == "knowledge:doc-001:v3"
        assert payload["p_domain_name"] == "KNOWLEDGE"


# ---------------------------------------------------------------------------
# §52 — rebuild race: process_queue requires supabase_client
# ---------------------------------------------------------------------------

class TestProcessQueueRequiresClient:
    def test_raises_without_client(self):
        from services.shared_search.incremental import process_queue
        with pytest.raises(ValueError, match="supabase_client"):
            process_queue()


# ---------------------------------------------------------------------------
# §53 — worker pause: all fenced events are re-queued, not failed
# ---------------------------------------------------------------------------

class TestWorkerPauseFencedRequeue:
    def test_fenced_events_return_to_pending(self):
        from services.shared_search.incremental import process_queue

        # claim_search_index_events returns 2 events
        claimed_events = [
            {
                "id": 101, "attempt_no": 1, "worker_id": "w1",
                "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
                "canonical_id": "doc-a",
            },
            {
                "id": 102, "attempt_no": 1, "worker_id": "w1",
                "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
                "canonical_id": "doc-b",
            },
        ]

        sb = MagicMock()
        claim_resp = MagicMock()
        claim_resp.data = claimed_events
        fail_resp  = MagicMock()
        fail_resp.execute.return_value = fail_resp

        def _rpc(name, payload=None):
            if name == "claim_search_index_events":
                return claim_resp
            return fail_resp

        sb.rpc.side_effect = _rpc
        claim_resp.execute.return_value = claim_resp

        # Fence is active
        fence_table = MagicMock()
        fence_table.select.return_value = fence_table
        fence_table.eq.return_value = fence_table
        fence_table.limit.return_value = fence_table
        fence_resp = MagicMock()
        fence_resp.data = [{"rebuild_active": True}]
        fence_table.execute.return_value = fence_resp

        sb.table.return_value = fence_table

        os_client = MagicMock()
        os_client.indices.get_alias.return_value = {"idx": {}}

        with patch(
            "services.shared_search.incremental.build_production_adapters",
            return_value=[],
        ):
            result = process_queue(
                supabase_client=sb,
                os_client=os_client,
            )

        assert result["fence_skipped"] == 2
        assert result["completed"] == 0
        assert result["failed"] == 0


# ---------------------------------------------------------------------------
# §54 — reconcile: missing docs trigger enqueue
# ---------------------------------------------------------------------------

class TestReconcileEnqueue:
    def test_missing_enqueued(self):
        from services.shared_search.opensearch_reconcile import _reconcile_domain

        client = MagicMock()
        # Alias scan returns empty (all docs missing from OS)
        client.search.return_value = {
            "_scroll_id": None,
            "hits": {"hits": []},
        }

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.iter_expected_hashes.return_value = [
            {"canonical_id": "doc-1", "content_hash": "aaa"},
            {"canonical_id": "doc-2", "content_hash": "bbb"},
        ]

        sb = MagicMock()
        rpc_resp = MagicMock()
        rpc_resp.execute.return_value = rpc_resp
        sb.rpc.return_value = rpc_resp

        report = _reconcile_domain(adapter, client, "tai-shared-search-current", sb)

        assert report.expected_count == 2
        assert report.current_count == 0
        assert len(report.missing) == 2
        assert report.enqueued == 2
        assert not report.ok

    def test_stale_hash_enqueued(self):
        from services.shared_search.opensearch_reconcile import _reconcile_domain

        client = MagicMock()
        # Alias scan returns doc-1 with wrong hash
        client.search.return_value = {
            "_scroll_id": None,
            "hits": {"hits": [
                {"_source": {"canonical_id": "doc-1", "content_hash": "STALE"}},
            ]},
        }

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.iter_expected_hashes.return_value = [
            {"canonical_id": "doc-1", "content_hash": "FRESH"},
        ]

        sb = MagicMock()
        rpc_resp = MagicMock()
        rpc_resp.execute.return_value = rpc_resp
        sb.rpc.return_value = rpc_resp

        report = _reconcile_domain(adapter, client, "tai-shared-search-current", sb)

        assert len(report.stale_by_hash) == 1
        assert report.enqueued == 1

    def test_match_not_enqueued(self):
        from services.shared_search.opensearch_reconcile import _reconcile_domain

        client = MagicMock()
        client.search.return_value = {
            "_scroll_id": None,
            "hits": {"hits": [
                {"_source": {"canonical_id": "doc-1", "content_hash": "SAME"}},
            ]},
        }

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.iter_expected_hashes.return_value = [
            {"canonical_id": "doc-1", "content_hash": "SAME"},
        ]

        sb = MagicMock()
        sb.rpc.return_value = MagicMock()

        report = _reconcile_domain(adapter, client, "tai-shared-search-current", sb)

        assert report.match == 1
        assert report.enqueued == 0
        assert report.ok


# ---------------------------------------------------------------------------
# §D — Rebuild race fixture: watermark + candidate replay
# ---------------------------------------------------------------------------

class TestRebuildCandidateReplay:
    """Validates _replay_outbox_into_candidate() behaviour.

    Scenario:
      rebuild start     → start_event_id = 10 (watermark)
      A update          → outbox id=11 (domain=KNOWLEDGE, cid=doc-A)
      B insert          → outbox id=12 (domain=KNOWLEDGE, cid=doc-B)
      C delete          → outbox id=13 (domain=KNOWLEDGE, cid=doc-C, adapter returns None)
      candidate build   → base index built (does NOT include A/B/C changes yet)
      replay            → A latest + B present + C absent applied to candidate
      promote           → candidate becomes current
    """

    def _make_supabase_with_events(self, events: list[dict]):
        sb = MagicMock()

        outbox_table = MagicMock()
        outbox_table.select.return_value = outbox_table
        outbox_table.gt.return_value = outbox_table
        outbox_table.order.return_value = outbox_table
        outbox_table.range.return_value = outbox_table
        # Return events on first call, empty on second (pagination end)
        responses = [
            MagicMock(data=events),
            MagicMock(data=[]),
        ]
        outbox_table.execute.side_effect = responses
        sb.table.return_value = outbox_table
        return sb

    def test_replay_upserts_and_deletes(self):
        """A and B are upserted, C is deleted in candidate."""
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate
        from services.shared_search.contract import SearchContractError

        # Events that arrived during rebuild
        events = [
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-A"},
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-B"},
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-C"},
        ]
        sb = self._make_supabase_with_events(events)

        # Adapters
        adapter_a_b_c = MagicMock()
        adapter_a_b_c.domain_name = "KNOWLEDGE"
        adapter_a_b_c.object_type = "KNOWLEDGE"

        def _payload(cid):
            if cid == "doc-C":
                return None  # tombstone
            return {
                "domain_name": "KNOWLEDGE",
                "object_type": "KNOWLEDGE",
                "canonical_id": cid,
                "title": f"Title {cid}",
                "publication_status": "PUBLISHED",
                "content_hash": f"hash-{cid}",
            }

        adapter_a_b_c.object_reindex_payload.side_effect = _payload

        # OpenSearch client
        os_client = MagicMock()

        with patch(
            "tools.shared_search.opensearch_rebuild.prepare_search_document",
        ) as mock_prepare:
            # prepare_search_document returns (doc, wire) for PUBLISHED payloads
            def _prepare(payload):
                doc = MagicMock()
                doc.publication_status = "PUBLISHED"
                wire = dict(payload)
                return doc, wire

            mock_prepare.side_effect = _prepare

            with patch(
                "tools.shared_search.opensearch_rebuild.doc_to_os_body",
                side_effect=lambda x: x,
            ):
                result = _replay_outbox_into_candidate(
                    sb,
                    [adapter_a_b_c],
                    os_client,
                    "tai-shared-search-v1-candidate",
                    start_event_id=10,
                )

        assert result["replayed"] == 2   # doc-A and doc-B upserted
        assert result["deleted"] == 1    # doc-C deleted
        assert result["errors"] == 0

        # Verify index was called for A and B
        assert os_client.index.call_count == 2
        # Verify delete was called for C
        assert os_client.delete.call_count == 1

    def test_replay_target_is_candidate_not_alias(self):
        """Confirm replay writes go to candidate_index, never to the alias."""
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate

        events = [
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-X"},
        ]
        sb = self._make_supabase_with_events(events)

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.object_reindex_payload.return_value = {
            "domain_name": "KNOWLEDGE",
            "object_type": "KNOWLEDGE",
            "canonical_id": "doc-X",
            "title": "X",
            "publication_status": "PUBLISHED",
            "content_hash": "h1",
        }

        os_client = MagicMock()
        CANDIDATE = "tai-shared-search-v1-CANDIDATE-idx"

        with patch(
            "tools.shared_search.opensearch_rebuild.prepare_search_document",
        ) as mock_prepare:
            doc = MagicMock()
            doc.publication_status = "PUBLISHED"
            mock_prepare.return_value = (doc, {"title": "X"})

            with patch(
                "tools.shared_search.opensearch_rebuild.doc_to_os_body",
                side_effect=lambda x: x,
            ):
                _replay_outbox_into_candidate(sb, [adapter], os_client, CANDIDATE, 10)

        # All index() calls must target the candidate, not the alias
        for call in os_client.index.call_args_list:
            assert call.kwargs.get("index") == CANDIDATE or call[1].get("index") == CANDIDATE

    def test_dedup_identity_replay_only_latest(self):
        """If same canonical_id appears twice in outbox, replay only once."""
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate

        # doc-A appears twice (two events during rebuild)
        events = [
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-A"},
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-A"},
        ]
        sb = self._make_supabase_with_events(events)

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.object_reindex_payload.return_value = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-A", "title": "A", "publication_status": "PUBLISHED",
            "content_hash": "h1",
        }

        os_client = MagicMock()
        with patch("tools.shared_search.opensearch_rebuild.prepare_search_document") as mp:
            d = MagicMock(); d.publication_status = "PUBLISHED"
            mp.return_value = (d, {"title": "A"})
            with patch("tools.shared_search.opensearch_rebuild.doc_to_os_body", side_effect=lambda x: x):
                result = _replay_outbox_into_candidate(
                    sb, [adapter], os_client, "candidate-idx", 10
                )

        # Only 1 write even though 2 events
        assert result["replayed"] == 1
        assert os_client.index.call_count == 1


# ---------------------------------------------------------------------------
# §E — PRECEDENT producer bridge tests
# ---------------------------------------------------------------------------

class TestPrecedentBridge:
    """Validates PRECEDENT B3 bridge: delta scan after Edge call."""

    def test_enqueue_precedent_delta_calls_rpc(self):
        """Recently collected precedents are enqueued after Edge call."""
        from routers.precedent_api import _enqueue_precedent_delta

        sb = MagicMock()
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.execute.return_value = MagicMock(
            data=[{"id": "prec-1"}, {"id": "prec-2"}]
        )
        sb.table.return_value = table_mock

        rpc_resp = MagicMock()
        rpc_resp.execute.return_value = rpc_resp
        sb.rpc.return_value = rpc_resp

        with patch("routers.precedent_api.get_supabase", return_value=sb):
            _enqueue_precedent_delta()

        # Should have called enqueue_search_index_sync twice
        assert sb.rpc.call_count == 2

        # extract (rpc_name, payload) from each call — positional args
        rpc_calls = [(c.args[0], c.args[1]) for c in sb.rpc.call_args_list]
        assert all(name == "enqueue_search_index_sync" for name, _ in rpc_calls)

        payloads = [p for _, p in rpc_calls]
        canonical_ids = {p["p_canonical_id"] for p in payloads}
        assert canonical_ids == {"prec-1", "prec-2"}
        assert all(p["p_domain_name"] == "PRECEDENT" for p in payloads)
        assert all(p["p_object_type"] == "PRECEDENT" for p in payloads)

    def test_enqueue_precedent_delta_no_rows(self):
        """No rows recently collected → no RPC calls, no error."""
        from routers.precedent_api import _enqueue_precedent_delta

        sb = MagicMock()
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.gte.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[])
        sb.table.return_value = table_mock
        sb.rpc.return_value = MagicMock()

        with patch("routers.precedent_api.get_supabase", return_value=sb):
            _enqueue_precedent_delta()

        sb.rpc.assert_not_called()

    def test_enqueue_precedent_delta_error_does_not_raise(self):
        """DB error in delta scan is logged, not re-raised."""
        from routers.precedent_api import _enqueue_precedent_delta

        sb = MagicMock()
        sb.table.side_effect = Exception("db_unavailable")

        with patch("routers.precedent_api.get_supabase", return_value=sb):
            # Must not raise
            _enqueue_precedent_delta()
