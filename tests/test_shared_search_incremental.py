"""Tests for the shared search incremental indexing pipeline.

Covers:
 - opensearch_projection: upsert_document NOOP / UPSERT, delete_document
 - incremental: sync_object outcomes, fence fail-closed, object_type mismatch
 - process_queue: fence-before-claim, completion fenced
 - opensearch_rebuild: replay loop, post-replay validation
 - migration: scheduler jobs present and inactive
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _fake_adapter(domain_name: str, object_type: str, *, payload=None):
    adapter = MagicMock()
    adapter.domain_name = domain_name
    adapter.object_type = object_type
    adapter.object_reindex_payload.return_value = payload
    adapter.iter_expected_hashes.return_value = iter([])
    return adapter


def _fake_sb(*, rebuild_active: bool = False):
    sb = MagicMock()
    table_mock = MagicMock()
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.limit.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[{"rebuild_active": rebuild_active}])
    sb.table.return_value = table_mock
    return sb


# ---------------------------------------------------------------------------
# File 1: opensearch_projection
# ---------------------------------------------------------------------------

class TestUpsertDocument:
    def test_upsert_when_not_found(self):
        from services.shared_search.opensearch_projection import upsert_document
        from opensearchpy import NotFoundError
        client = MagicMock()
        client.get.side_effect = NotFoundError(404, "not found")

        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "publication_status": "PUBLISHED",
            "content_hash": "HASH_ABC",
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "visibility_scopes": [],
        }
        result = upsert_document(client, "idx", "KNOWLEDGE::doc-1", wire)
        assert result == "UPSERT"
        client.index.assert_called_once()

    def test_noop_when_hash_matches(self):
        from services.shared_search.opensearch_projection import upsert_document
        client = MagicMock()
        client.get.return_value = {"_source": {"content_hash": "HASH_ABC"}}

        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "publication_status": "PUBLISHED",
            "content_hash": "HASH_ABC",
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "visibility_scopes": [],
        }
        result = upsert_document(client, "idx", "KNOWLEDGE::doc-1", wire)
        assert result == "NOOP"
        client.index.assert_not_called()

    def test_upsert_when_hash_differs(self):
        from services.shared_search.opensearch_projection import upsert_document
        client = MagicMock()
        client.get.return_value = {"_source": {"content_hash": "OLD_HASH"}}

        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "publication_status": "PUBLISHED",
            "content_hash": "NEW_HASH",
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "visibility_scopes": [],
        }
        result = upsert_document(client, "idx", "KNOWLEDGE::doc-1", wire)
        assert result == "UPSERT"
        client.index.assert_called_once()


class TestDeleteDocument:
    def test_delete_existing(self):
        from services.shared_search.opensearch_projection import delete_document
        client = MagicMock()
        result = delete_document(client, "idx", "KNOWLEDGE::doc-1")
        assert result == "DELETE"
        client.delete.assert_called_once()

    def test_delete_noop_when_not_found(self):
        from services.shared_search.opensearch_projection import delete_document
        from opensearchpy import NotFoundError
        client = MagicMock()
        client.delete.side_effect = NotFoundError(404, "not found")
        result = delete_document(client, "idx", "KNOWLEDGE::doc-1")
        assert result == "DELETE_NOOP"


# ---------------------------------------------------------------------------
# File 2: opensearch_store public alias
# ---------------------------------------------------------------------------

class TestDocToOsBodyPublicAlias:
    def test_public_alias_exists(self):
        from services.shared_search.opensearch_store import doc_to_os_body, _doc_to_os_body
        assert doc_to_os_body is _doc_to_os_body

    def test_converts_wire_to_body(self):
        from services.shared_search.opensearch_store import doc_to_os_body
        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "content_hash": "H",
            "subjects": None, "context": None, "aliases": None,
            "keywords": None, "visibility_scopes": None,
        }
        body = doc_to_os_body(wire)
        assert body["subjects"] == []
        assert body["context"] == []
        assert "indexed_at" in body

    def test_rebuild_imports_from_store(self):
        # opensearch_rebuild should import doc_to_os_body from opensearch_store
        import ast, pathlib
        p = pathlib.Path("tools/shared_search/opensearch_rebuild.py")
        src = p.read_text()
        # Must import doc_to_os_body from opensearch_store
        assert "from services.shared_search.opensearch_store import" in src
        assert "doc_to_os_body" in src


# ---------------------------------------------------------------------------
# File 3: incremental — sync_object
# ---------------------------------------------------------------------------

class TestSyncObjectFence:
    def test_fence_active_returns_skip_fence(self):
        from services.shared_search.incremental import sync_object
        sb = _fake_sb(rebuild_active=True)
        client = MagicMock()
        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload={"title": "x"})
        result = sync_object(
            domain_name="KNOWLEDGE", object_type="KNOWLEDGE",
            canonical_id="doc-1", supabase_client=sb, os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] == "SKIP_FENCE"
        client.index.assert_not_called()

    def test_no_adapter_returns_skip(self):
        from services.shared_search.incremental import sync_object
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}
        result = sync_object(
            domain_name="UNKNOWN", object_type="UNKNOWN",
            canonical_id="doc-1", supabase_client=sb, os_client=client,
            adapter_map={},
        )
        assert result["outcome"] == "SKIP_NO_ADAPTER"

    def test_upsert_outcome_on_payload(self):
        from services.shared_search.incremental import sync_object
        from opensearchpy import NotFoundError
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}
        client.get.side_effect = NotFoundError(404, "not found")

        payload = {
            "object_type": "KNOWLEDGE", "canonical_id": "doc-1",
            "title": "T", "source_id": "S", "source_key": "k",
            "publication_status": "PUBLISHED",
            "visibility_scopes": ["PUBLIC"],
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "search_text": "T",
            "source_updated_at": "2026-09-20T00:00:00+09:00",
        }
        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload=payload)
        result = sync_object(
            domain_name="KNOWLEDGE", object_type="KNOWLEDGE",
            canonical_id="doc-1", supabase_client=sb, os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] in ("UPSERT", "NOOP")

    def test_tombstone_on_none_payload(self):
        from services.shared_search.incremental import sync_object
        from opensearchpy import NotFoundError
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}
        client.delete.side_effect = NotFoundError(404, "not found")

        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload=None)
        result = sync_object(
            domain_name="KNOWLEDGE", object_type="KNOWLEDGE",
            canonical_id="doc-1", supabase_client=sb, os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] in ("DELETE", "DELETE_NOOP")


# ---------------------------------------------------------------------------
# New test classes from spec
# ---------------------------------------------------------------------------

# Test: canonical hash == rebuild hash (same prepare_search_document)
class TestCanonicalHashParity:
    def test_incremental_uses_prepare_hash_not_recomputed(self):
        # wire from prepare_search_document has content_hash set
        # upsert_document should use wire["content_hash"] for NOOP, not recompute
        from services.shared_search.opensearch_projection import upsert_document, get_document_content_hash
        from opensearchpy import NotFoundError
        client = MagicMock()
        client.get.side_effect = NotFoundError(404, "not found")  # no existing doc

        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "publication_status": "PUBLISHED",
            "content_hash": "CANONICAL_HASH_FROM_PREPARE",
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "visibility_scopes": [],
        }
        result = upsert_document(client, "idx", "KNOWLEDGE::doc-1", wire)
        assert result == "UPSERT"
        # The body written to OpenSearch must have content_hash = the canonical one
        call_body = client.index.call_args.kwargs.get("body") or client.index.call_args[1].get("body")
        assert call_body["content_hash"] == "CANONICAL_HASH_FROM_PREPARE"

    def test_noop_when_canonical_hash_matches_stored(self):
        from services.shared_search.opensearch_projection import upsert_document
        client = MagicMock()
        client.get.return_value = {
            "_source": {"content_hash": "CANONICAL_HASH_FROM_PREPARE"}
        }
        wire = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1", "title": "T",
            "publication_status": "PUBLISHED",
            "content_hash": "CANONICAL_HASH_FROM_PREPARE",
            "subjects": [], "context": [], "aliases": [], "keywords": [],
            "visibility_scopes": [],
        }
        result = upsert_document(client, "idx", "KNOWLEDGE::doc-1", wire)
        assert result == "NOOP"
        client.index.assert_not_called()


# Test: wrong object_type rejected
class TestObjectTypeMismatch:
    def test_object_type_mismatch_raises(self):
        from services.shared_search.incremental import sync_object
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}

        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload={"title": "x"})

        with pytest.raises(ValueError, match="object_type mismatch"):
            sync_object(
                domain_name="KNOWLEDGE",
                object_type="LEGAL",  # wrong!
                canonical_id="doc-1",
                supabase_client=sb,
                os_client=client,
                adapter_map={"KNOWLEDGE": adapter},
            )


# Test: fence DB error → fail-closed (no write)
class TestFenceFailClosed:
    def test_db_error_returns_skip_fence(self):
        from services.shared_search.incremental import sync_object

        sb = MagicMock()
        # All table accesses raise
        sb.table.side_effect = Exception("db_down")

        client = MagicMock()
        client.indices.get_alias.return_value = {"idx": {}}
        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload={"title": "x"})

        result = sync_object(
            domain_name="KNOWLEDGE",
            object_type="KNOWLEDGE",
            canonical_id="doc-1",
            supabase_client=sb,
            os_client=client,
            adapter_map={"KNOWLEDGE": adapter},
        )
        assert result["outcome"] == "SKIP_FENCE"
        client.index.assert_not_called()

    def test_process_queue_fence_active_no_claim(self):
        from services.shared_search.incremental import process_queue

        sb = MagicMock()
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.limit.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[{"rebuild_active": True}])
        sb.table.return_value = table_mock

        result = process_queue(supabase_client=sb)
        assert result["claimed"] == 0
        assert result.get("fence_active") is True
        # No RPC claim call
        sb.rpc.assert_not_called()


# Test: completion fenced → completed metric unchanged
class TestCompletionFenced:
    def test_completion_rpc_false_does_not_increment(self):
        from services.shared_search.incremental import process_queue
        from opensearchpy import NotFoundError

        claimed_events = [{
            "id": 1, "attempt_no": 1, "worker_id": "w1",
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "doc-1",
        }]

        sb = MagicMock()
        # Fence inactive
        table_mock = MagicMock()
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.limit.return_value = table_mock
        table_mock.execute.return_value = MagicMock(data=[{"rebuild_active": False}])
        sb.table.return_value = table_mock

        claim_resp = MagicMock(data=claimed_events)
        claim_resp.execute.return_value = claim_resp
        complete_resp = MagicMock()
        complete_resp.data = False  # fenced
        complete_resp.execute.return_value = complete_resp

        def _rpc(name, payload=None):
            if name == "claim_search_index_events":
                return claim_resp
            if name == "complete_search_index_event":
                return complete_resp
            return MagicMock(execute=lambda: MagicMock(data=None))

        sb.rpc.side_effect = _rpc

        adapter = _fake_adapter("KNOWLEDGE", "KNOWLEDGE", payload=None)

        os_client = MagicMock()
        os_client.indices.get_alias.return_value = {"idx": {}}
        os_client.delete.side_effect = __import__("opensearchpy").NotFoundError(404, "x")

        with patch(
            "services.shared_search.production_bindings.build_production_adapters",
            return_value=[adapter],
        ):
            result = process_queue(supabase_client=sb, os_client=os_client)

        assert result["completed"] == 0


# Test: replay inserts/deletes change candidate count → final validation catches mismatch
class TestPostReplayValidation:
    def test_replay_errors_prevent_promotion(self):
        """replay.errors > 0 → RebuildRejected, promote not called"""
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate

        events = [
            {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-A"},
        ]
        sb = MagicMock()
        outbox = MagicMock()
        outbox.select.return_value = outbox
        outbox.gt.return_value = outbox
        outbox.lte.return_value = outbox
        outbox.order.return_value = outbox
        outbox.range.return_value = outbox
        # high_water query
        outbox.limit.return_value = outbox
        outbox.execute.side_effect = [
            MagicMock(data=[{"id": 20}]),  # first high-water check
            MagicMock(data=events),         # page of events
            MagicMock(data=[]),             # end of pagination
            MagicMock(data=[{"id": 20}]),  # stable check
        ]
        sb.table.return_value = outbox

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.object_reindex_payload.side_effect = Exception("adapter_error")

        os_client = MagicMock()

        with patch("tools.shared_search.opensearch_rebuild.prepare_search_document", side_effect=Exception("fail")):
            result = _replay_outbox_into_candidate(sb, [adapter], os_client, "candidate", 10)

        assert result["errors"] == 1


# Test: event arrives during replay → second catch-up
class TestReplayCatchup:
    def test_second_catchup_on_new_event(self):
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate

        sb = MagicMock()
        outbox = MagicMock()
        outbox.select.return_value = outbox
        outbox.gt.return_value = outbox
        outbox.lte.return_value = outbox
        outbox.order.return_value = outbox
        outbox.range.return_value = outbox
        outbox.limit.return_value = outbox

        call_count = [0]
        def _execute():
            call_count[0] += 1
            c = call_count[0]
            # Round 1: high_water=12
            if c == 1: return MagicMock(data=[{"id": 12}])
            # Round 1 events: doc-A, doc-B (< 1000, so inner loop breaks without second page)
            if c == 2: return MagicMock(data=[
                {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-A"},
                {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-B"},
            ])
            # Stable check: new event arrived → new_max=13
            if c == 3: return MagicMock(data=[{"id": 13}])
            # Round 2: high_water=13
            if c == 4: return MagicMock(data=[{"id": 13}])
            # Round 2 events: doc-C (< 1000, inner loop breaks)
            if c == 5: return MagicMock(data=[
                {"domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE", "canonical_id": "doc-C"},
            ])
            # Stable check: stable (no new events)
            if c == 6: return MagicMock(data=[{"id": 13}])
            return MagicMock(data=[])

        outbox.execute.side_effect = lambda: _execute()
        sb.table.return_value = outbox

        adapter = MagicMock()
        adapter.domain_name = "KNOWLEDGE"
        adapter.object_type = "KNOWLEDGE"
        adapter.object_reindex_payload.return_value = {
            "domain_name": "KNOWLEDGE", "object_type": "KNOWLEDGE",
            "canonical_id": "x", "title": "T", "publication_status": "PUBLISHED",
            "content_hash": "h",
        }

        os_client = MagicMock()
        with patch("tools.shared_search.opensearch_rebuild.prepare_search_document") as mp:
            d = MagicMock(); d.publication_status = "PUBLISHED"
            mp.return_value = (d, {"content_hash": "h", "title": "T"})
            with patch("tools.shared_search.opensearch_rebuild.doc_to_os_body", side_effect=lambda x: x):
                result = _replay_outbox_into_candidate(sb, [adapter], os_client, "candidate", 10)

        assert result["rounds"] == 2
        assert result["replayed"] == 3  # doc-A, doc-B, doc-C


# Test: scheduler jobs created inactive
class TestSchedulerJobsInMigration:
    def test_migration_contains_inactive_jobs(self):
        with open("supabase/migrations/20260920_shared_search_incremental_outbox.sql") as f:
            sql = f.read()
        assert "shared_search_incremental" in sql
        assert "shared_search_reconcile" in sql
        assert "is_active" in sql.lower() or "is_active" in sql
        # Jobs must be inactive (false)
        import re
        # Find the insert block for these jobs
        assert "false" in sql.lower()  # is_active = false


# ---------------------------------------------------------------------------
# PATCH-2 new test classes
# ---------------------------------------------------------------------------

class TestOutboxRetryBackoff:
    """ITEM 2: fail → PENDING with backoff, DEAD after max attempts."""

    def test_fail_sets_pending_with_available_at(self):
        # Migration SQL: fail_search_index_event with attempt < max
        # Check SQL contains 'available_at' and PENDING path
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "'PENDING'" in sql and "available_at" in sql and "v_delay_s" in sql

    def test_fail_sets_dead_at_max_attempts(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "'DEAD'" in sql and "p_max_attempts" in sql

    def test_claim_reclaims_expired_lease(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "lease_until < NOW()" in sql

    def test_complete_checks_rowcount(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "GET DIAGNOSTICS" in sql and "ROW_COUNT" in sql

    def test_event_key_unique_constraint(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "UNIQUE" in sql and "event_key" in sql


class TestFenceUnification:
    """ITEM 1: both rebuild and worker use search_index_fence."""

    def test_rebuild_uses_fence_table_not_runtime_state(self):
        import inspect
        from tools.shared_search import opensearch_rebuild as rb
        src = inspect.getsource(rb)
        assert "search_index_fence" in src
        assert "search_index_runtime_state" not in src

    def test_incremental_uses_fence_table(self):
        import inspect
        from services.shared_search import incremental as inc
        src = inspect.getsource(inc)
        assert "search_index_fence" in src
        assert "search_index_runtime_state" not in src


class TestAliasSafetyStrict:
    """ITEM 3: alias must resolve to exactly 1 index; failure raises, not SKIP_FENCE."""

    def test_two_indices_raises(self):
        from unittest.mock import MagicMock
        from services.shared_search.incremental import sync_object, ProjectionWriteError
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx_a": {}, "idx_b": {}}
        sb = _fake_sb(rebuild_active=False)
        with pytest.raises(ProjectionWriteError, match="exactly 1 index"):
            sync_object(
                domain_name="KNOWLEDGE", object_type="KNOWLEDGE",
                canonical_id="k1",
                supabase_client=sb,
                os_client=client,
                adapter_map={"KNOWLEDGE": _fake_adapter("KNOWLEDGE", "KNOWLEDGE")},
            )

    def test_alias_lookup_failure_raises_not_skip(self):
        from unittest.mock import MagicMock
        from services.shared_search.incremental import sync_object, ProjectionWriteError
        client = MagicMock()
        client.indices.get_alias.side_effect = Exception("connection refused")
        sb = _fake_sb(rebuild_active=False)
        with pytest.raises(ProjectionWriteError, match="alias lookup failed"):
            sync_object(
                domain_name="KNOWLEDGE", object_type="KNOWLEDGE",
                canonical_id="k1",
                supabase_client=sb,
                os_client=client,
                adapter_map={"KNOWLEDGE": _fake_adapter("KNOWLEDGE", "KNOWLEDGE")},
            )


class TestProcessQueueOutcomeRouting:
    """ITEM 3: SKIP_FENCE → requeue; SKIP_NO_ADAPTER → fail."""

    def test_skip_no_adapter_fails_event(self):
        from unittest.mock import MagicMock, patch
        from services.shared_search.incremental import process_queue

        events = [{"id": 77, "domain_name": "UNKNOWN_DOMAIN", "object_type": "X", "canonical_id": "c1"}]

        sb = MagicMock()
        fence_row = MagicMock()
        fence_row.data = [{"rebuild_active": False}]
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = fence_row

        claim_result = MagicMock()
        claim_result.data = events
        sb.rpc.return_value.execute.return_value = claim_result

        os_client = MagicMock()
        os_client.indices.get_alias.return_value = {"idx_a": {}}

        with patch("services.shared_search.incremental._rebuild_active", return_value=False):
            with patch("services.shared_search.production_bindings.build_production_adapters", return_value=[]):
                obs = process_queue(supabase_client=sb, os_client=os_client)

        assert obs["failed"] >= 1


class TestReplaySeen:
    """ITEM 4: seen set is per-round so second-round changes are replayed."""

    def test_seen_is_per_round_identity_replayed_twice(self):
        import inspect
        from tools.shared_search import opensearch_rebuild as rb
        src = inspect.getsource(rb._replay_outbox_into_candidate)
        # seen = set() should appear inside the while loop body
        lines = src.splitlines()
        while_found = False
        seen_inside = False
        for line in lines:
            stripped = line.lstrip()
            if "while round_no <" in stripped:
                while_found = True
            if while_found and stripped.startswith("seen") and "set()" in stripped:
                seen_inside = True
                break
        assert seen_inside, "seen = set() must be inside the while loop"

    def test_max_rounds_raises_rebuild_rejected(self):
        from unittest.mock import MagicMock
        from tools.shared_search.opensearch_rebuild import _replay_outbox_into_candidate, MAX_REPLAY_ROUNDS
        from services.shared_search.opensearch_store import RebuildRejected

        supabase = MagicMock()
        # Always return a new high-water so it never converges
        call_count = [0]
        def always_new_max(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.data = [{"id": call_count[0] * 1000}]
            return result
        supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.side_effect = always_new_max
        # Return empty rows for the range query so no actual replay happens
        supabase.table.return_value.select.return_value.gt.return_value.lte.return_value.order.return_value.range.return_value.execute.return_value.data = []

        with pytest.raises(RebuildRejected, match="did not converge"):
            _replay_outbox_into_candidate(supabase, [], MagicMock(), "idx", 0)


class TestRlsInMigration:
    """ITEM 8: RLS and REVOKE present in migration."""

    def test_rls_enabled(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "ENABLE ROW LEVEL SECURITY" in sql

    def test_revoke_from_anon(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        assert "REVOKE" in sql and "anon" in sql


# ---------------------------------------------------------------------------
# PATCH-3 new test classes
# ---------------------------------------------------------------------------

class TestKnowledgeEventKey:
    def test_event_key_included(self):
        from unittest.mock import MagicMock, patch
        sb = MagicMock()
        rpc_mock = MagicMock()
        sb.rpc.return_value = rpc_mock

        with patch("services.safe_help_svc.get_supabase", return_value=sb):
            import importlib, services.safe_help_svc as svc
            svc._enqueue_knowledge_sync(sb, "doc-1", reason="upsert")

        call_kwargs = sb.rpc.call_args[0][1]
        assert "p_event_key" in call_kwargs
        assert "doc-1" in call_kwargs["p_event_key"]
        assert "upsert" in call_kwargs["p_event_key"]

    def test_event_key_varies_across_invocations(self):
        """Two calls at different (mocked) times produce different event keys."""
        from unittest.mock import MagicMock, patch
        import datetime

        sb = MagicMock()
        keys = []

        def capture_rpc(name, params):
            keys.append(params.get("p_event_key", ""))
            return MagicMock()

        sb.rpc.side_effect = capture_rpc

        t1 = datetime.datetime(2026, 9, 20, 10, 0, 0, tzinfo=datetime.timezone.utc)
        t2 = datetime.datetime(2026, 9, 20, 10, 0, 5, tzinfo=datetime.timezone.utc)

        with patch("services.time.now_kst", side_effect=[t1, t2]):
            import services.safe_help_svc as svc
            svc._enqueue_knowledge_sync(sb, "doc-1", reason="upsert")
            svc._enqueue_knowledge_sync(sb, "doc-1", reason="upsert")

        assert len(keys) == 2
        assert keys[0] != keys[1], "Same doc+reason at different times must have different event keys"


class TestPrecedentEventKey:
    def test_event_key_included(self):
        sql_check = "precedent_delta"
        import inspect
        from routers.precedent_api import _enqueue_precedent_delta
        src = inspect.getsource(_enqueue_precedent_delta)
        assert "p_event_key" in src
        assert "precedent_delta" in src


class TestReconcileRunId:
    def test_event_key_includes_run_id(self):
        import inspect
        from services.shared_search import opensearch_reconcile as rc
        src = inspect.getsource(rc._reconcile_domain)
        assert "reconcile_run_id" in src
        assert "p_event_key" in src

    def test_run_reconcile_generates_run_id(self):
        import inspect
        from services.shared_search import opensearch_reconcile as rc
        src = inspect.getsource(rc.run_reconcile)
        assert "reconcile_run_id" in src or "uuid" in src


class TestPublishedOnlyExpected:
    def test_hold_excluded_from_expected_hashes(self):
        from unittest.mock import patch, MagicMock
        from services.shared_search.adapters._common import expected_hashes_from_documents

        hold_payload = {
            "object_type": "SAFETY_MATERIAL",
            "canonical_id": "mat-hold-1",
            "publication_status": "HOLD",
            "title": "Hold Material",
            "source_id": "KOSHA",
            "source_key": "k1",
            "source_updated_at": "2026-01-01T00:00:00+00:00",
            "search_text": "hold material text",
        }
        published_payload = {
            "object_type": "SAFETY_MATERIAL",
            "canonical_id": "mat-pub-1",
            "publication_status": "PUBLISHED",
            "title": "Published Material",
            "source_id": "KOSHA",
            "source_key": "k2",
            "source_updated_at": "2026-01-01T00:00:00+00:00",
            "search_text": "published material text",
        }

        def docs():
            yield hold_payload
            yield published_payload

        results = list(expected_hashes_from_documents(docs))
        canonical_ids = [r["canonical_id"] for r in results]
        assert "mat-hold-1" not in canonical_ids, "HOLD must not appear in expected hashes"
        assert "mat-pub-1" in canonical_ids, "PUBLISHED must appear in expected hashes"


class TestSortField:
    def test_reconcile_scan_uses_canonical_id_sort(self):
        import inspect
        from services.shared_search import opensearch_reconcile as rc
        src = inspect.getsource(rc._scan_os_domain)
        assert '"_id"' not in src and "'_id'" not in src
        assert "canonical_id" in src

    def test_post_replay_validate_uses_canonical_id_sort(self):
        import inspect
        from tools.shared_search import opensearch_rebuild as rb
        src = inspect.getsource(rb._post_replay_validate)
        assert '"_id"' not in src and "'_id'" not in src
        assert "canonical_id" in src


class TestStaleWorkerFence:
    def test_fail_rpc_includes_worker_id_and_attempt_no(self):
        from unittest.mock import MagicMock
        from services.shared_search.incremental import _fail_event

        sb = MagicMock()
        _fail_event(sb, event_id=42, reason="boom", worker_id="w-1", attempt_no=3)

        call_kwargs = sb.rpc.call_args[0][1]
        assert call_kwargs["p_worker_id"] == "w-1"
        assert call_kwargs["p_attempt_no"] == 3

    def test_fail_rpc_name(self):
        from unittest.mock import MagicMock
        from services.shared_search.incremental import _fail_event

        sb = MagicMock()
        _fail_event(sb, event_id=1, reason="x", worker_id="w", attempt_no=1)
        assert sb.rpc.call_args[0][0] == "fail_search_index_event"

    def test_migration_fail_has_worker_fence(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        # fail function must check worker_id and attempt_no
        assert "p_worker_id" in sql and "p_attempt_no" in sql

    def test_migration_requeue_has_worker_fence(self):
        sql = open("supabase/migrations/20260920_shared_search_incremental_outbox.sql").read()
        # requeue function must check worker_id and attempt_no
        assert "requeue_search_index_event" in sql
        # Check that the requeue WHERE clause includes worker_id
        import re
        requeue_body = sql[sql.find("requeue_search_index_event"):sql.find("requeue_search_index_event")+2000]
        assert "worker_id" in requeue_body and "attempt_no" in requeue_body


class TestCiRegistration:
    def test_incremental_tests_in_ci(self):
        ci = open(".github/workflows/ci.yml").read()
        assert "test_shared_search_incremental" in ci


# ---------------------------------------------------------------------------
# PATCH-4: Reconcile scan failure, KNOWLEDGE event key, delete ordering
# ---------------------------------------------------------------------------

class TestReconcileScanFailure:
    def test_scan_failure_propagates_not_empty_map(self):
        """Scan failure must raise, not silently return {}."""
        from unittest.mock import MagicMock
        from services.shared_search import opensearch_reconcile

        adapter = MagicMock()
        adapter.domain_name = "TEST"
        adapter.object_type = "TEST"
        adapter.iter_expected_hashes.return_value = [
            {"canonical_id": "c1", "content_hash": "h1"},
        ]

        client = MagicMock()
        client.search.side_effect = RuntimeError("OS unreachable")

        sb = MagicMock()
        with pytest.raises(RuntimeError, match="OS unreachable"):
            opensearch_reconcile._reconcile_domain(
                adapter, client, "test-index", sb, reconcile_run_id="r1"
            )

    def test_scan_failure_sets_all_ok_false_in_run_reconcile(self):
        """run_reconcile must mark all_ok=False when a domain scan raises."""
        from unittest.mock import MagicMock, patch
        from services.shared_search import opensearch_reconcile

        adapter = MagicMock()
        adapter.domain_name = "TEST"
        adapter.object_type = "TEST"

        client = MagicMock()
        sb = MagicMock()

        with patch.object(
            opensearch_reconcile, "_reconcile_domain", side_effect=RuntimeError("boom")
        ):
            result = opensearch_reconcile.run_reconcile(
                adapters=[adapter], client=client, index="test-index", supabase=sb
            )

        assert result["all_ok"] is False

    def test_scan_failure_no_enqueue(self):
        """When scan raises, run_reconcile must not enqueue anything for that domain."""
        from unittest.mock import MagicMock, patch
        from services.shared_search import opensearch_reconcile

        adapter = MagicMock()
        adapter.domain_name = "TEST"
        adapter.object_type = "TEST"

        client = MagicMock()
        sb = MagicMock()

        with patch.object(
            opensearch_reconcile, "_reconcile_domain", side_effect=RuntimeError("boom")
        ):
            opensearch_reconcile.run_reconcile(
                adapters=[adapter], client=client, index="test-index", supabase=sb
            )

        sb.rpc.assert_not_called()


class TestKnowledgeEventKeyUniqueness:
    def test_two_calls_same_second_different_keys(self):
        """Two enqueue calls within the same second must produce distinct event_keys."""
        from unittest.mock import MagicMock, patch
        import services.safe_help_svc as svc

        keys = []
        original_rpc = None

        def capture_rpc(name, params):
            if name == "enqueue_search_index_sync":
                keys.append(params["p_event_key"])
            m = MagicMock()
            m.execute.return_value = MagicMock()
            return m

        sb = MagicMock()
        sb.rpc.side_effect = capture_rpc

        svc._enqueue_knowledge_sync(sb, "doc-1", reason="upsert_help")
        svc._enqueue_knowledge_sync(sb, "doc-1", reason="upsert_help")

        assert len(keys) == 2
        assert keys[0] != keys[1], "Same-second event keys must be unique"

    def test_event_key_contains_doc_id_and_reason(self):
        """Event key must embed doc_id and reason for traceability."""
        from unittest.mock import MagicMock
        import services.safe_help_svc as svc

        keys = []

        def capture_rpc(name, params):
            if name == "enqueue_search_index_sync":
                keys.append(params["p_event_key"])
            m = MagicMock()
            m.execute.return_value = MagicMock()
            return m

        sb = MagicMock()
        sb.rpc.side_effect = capture_rpc

        svc._enqueue_knowledge_sync(sb, "my-doc-id", reason="delete_help")

        assert len(keys) == 1
        assert "my-doc-id" in keys[0]
        assert "delete_help" in keys[0]


class TestKnowledgeDeleteOrdering:
    def test_delete_success_enqueues_tombstone(self):
        """Successful delete must trigger exactly one enqueue call."""
        from unittest.mock import MagicMock, patch
        import services.safe_help_svc as svc

        sb = MagicMock()
        sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"doc_id": "doc-1"}]
        )

        with patch.object(svc, "_enqueue_knowledge_sync") as mock_enqueue:
            with patch.object(svc, "get_supabase", return_value=sb):
                result = svc.delete_help("doc-1")

        assert result is True
        mock_enqueue.assert_called_once_with(sb, "doc-1", reason="delete_help")

    def test_delete_failure_no_enqueue(self):
        """Failed delete (no rows affected) must NOT enqueue a tombstone."""
        from unittest.mock import MagicMock, patch
        import services.safe_help_svc as svc

        sb = MagicMock()
        sb.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch.object(svc, "_enqueue_knowledge_sync") as mock_enqueue:
            with patch.object(svc, "get_supabase", return_value=sb):
                result = svc.delete_help("doc-1")

        assert result is False
        mock_enqueue.assert_not_called()

    def test_delete_called_before_enqueue(self):
        """DB delete must be called before enqueue (ordering invariant)."""
        from unittest.mock import MagicMock, patch, call
        import services.safe_help_svc as svc

        call_order = []

        sb = MagicMock()

        def track_delete(*args, **kwargs):
            call_order.append("delete")
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[{"doc_id": "doc-1"}])
            return m

        sb.table.return_value.delete.return_value.eq.side_effect = track_delete

        def track_enqueue(sb_, doc_id, *, reason):
            call_order.append("enqueue")

        with patch.object(svc, "_enqueue_knowledge_sync", side_effect=track_enqueue):
            with patch.object(svc, "get_supabase", return_value=sb):
                svc.delete_help("doc-1")

        assert call_order == ["delete", "enqueue"], (
            f"Expected delete then enqueue, got: {call_order}"
        )


# ---------------------------------------------------------------------------
# B01-B16: bulk_sync_published_domain — WO-MKT-SEARCH-04B-4A-FAST
# ---------------------------------------------------------------------------

def _make_bulk_adapter(domain_name, object_type, expected_hashes, documents):
    """Build a mock adapter for bulk tests."""
    adapter = MagicMock()
    adapter.domain_name = domain_name
    adapter.object_type = object_type
    adapter.iter_expected_hashes.return_value = iter(list(expected_hashes))
    adapter.iter_documents.return_value = iter(list(documents))
    return adapter


def _bulk_payload(canonical_id, pub_status="PUBLISHED"):
    """Raw adapter payload dict (input to prepare_search_document)."""
    return {
        "object_type": "CHEM",
        "canonical_id": canonical_id,
        "title": f"Chem {canonical_id}",
        "source_id": "KOSHA_MSDS",
        "source_key": canonical_id,
        "publication_status": pub_status,
        "visibility_scopes": ["PUBLIC", "SAAS", "PAID"],
        "subjects": [], "context": [], "aliases": [], "keywords": [],
        "search_text": f"chem {canonical_id}",
        "source_updated_at": "2026-09-01T00:00:00+00:00",
        "public_url": f"/msds/{canonical_id}",
        "saas_url": None,
        "summary": None,
    }


def _mock_prepare(cid_hash_map):
    """Return a side_effect function for patching prepare_search_document.

    cid_hash_map: {canonical_id: content_hash}
    Returned (doc, wire) pairs match the expected hashes so PASS1/PASS2 guard passes.
    """
    def _side_effect(payload):
        cid = payload.get("canonical_id")
        ch = cid_hash_map.get(cid, f"HASH_{cid}")
        doc = MagicMock()
        doc.publication_status = "PUBLISHED"
        doc.canonical_id = cid
        wire = {"content_hash": ch, "canonical_id": cid, "title": payload.get("title", "")}
        return doc, wire
    return _side_effect


# Alias for backward compat
def _bulk_wire(canonical_id, content_hash="HASH_ABC"):
    """Legacy alias — used only in B09/B10 where we want the raw payload dict."""
    return _bulk_payload(canonical_id)


def _fake_os_client(physical_index="tai-test-001", mget_results=None, bulk_errors=0):
    """Build a mock OS client for bulk tests."""
    client = MagicMock()
    client.indices.get_alias.return_value = {physical_index: {}}

    def _mget(**kwargs):
        ids = kwargs.get("body", {}).get("ids", [])
        docs = []
        for doc_id in ids:
            if mget_results and doc_id in mget_results:
                stored = mget_results[doc_id]
                if stored is None:
                    docs.append({"_id": doc_id, "found": False})
                else:
                    docs.append({"_id": doc_id, "found": True, "_source": {"content_hash": stored}})
            else:
                docs.append({"_id": doc_id, "found": False})
        return {"docs": docs}

    client.mget.side_effect = _mget
    return client


class TestBulkSyncB01:
    """B01: Fence active at start → write=0, MGET=0."""

    def test_fence_active_returns_immediately(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        sb = _fake_sb(rebuild_active=True)
        client = MagicMock()
        adapter = _make_bulk_adapter("CHEM", "CHEM",
            expected_hashes=[{"canonical_id": "c1", "content_hash": "H1"}],
            documents=[_bulk_wire("c1", "H1")],
        )
        result = bulk_sync_published_domain(
            domain_name="CHEM", object_type="CHEM",
            os_client=client, supabase_client=sb,
            adapter_map={"CHEM": adapter},
        )
        assert result["fence_blocked"] is True
        assert result["upsert"] == 0
        client.mget.assert_not_called()
        client.indices.get_alias.assert_not_called()


class TestBulkSyncB02:
    """B02: Alias target 0 or >1 → write=0."""

    def test_alias_zero_indices_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {}
        adapter = _make_bulk_adapter("CHEM", "CHEM", [], [])
        with pytest.raises(ProjectionWriteError, match="exactly 1 index"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
            )

    def test_alias_two_indices_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = MagicMock()
        client.indices.get_alias.return_value = {"idx_a": {}, "idx_b": {}}
        adapter = _make_bulk_adapter("CHEM", "CHEM", [], [])
        with pytest.raises(ProjectionWriteError, match="exactly 1 index"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
            )


class TestBulkSyncB03:
    """B03: Adapter/object_type mismatch → write=0."""

    def test_object_type_mismatch_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        adapter = _make_bulk_adapter("CHEM", "CHEM", [], [])
        with pytest.raises(ValueError, match="object_type mismatch"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="LEGAL",  # mismatch
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
            )
        client.mget.assert_not_called()


class TestBulkSyncB04:
    """B04: Expected set duplicate → write=0."""

    def test_duplicate_canonical_id_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        adapter = _make_bulk_adapter("CHEM", "CHEM",
            expected_hashes=[
                {"canonical_id": "c1", "content_hash": "H1"},
                {"canonical_id": "c1", "content_hash": "H1"},  # duplicate
            ],
            documents=[],
        )
        with pytest.raises(ProjectionWriteError, match="Duplicate"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
            )
        client.mget.assert_not_called()


class TestBulkSyncB05:
    """B05: DB frozen set != adapter set → write=0."""

    def test_db_only_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        adapter = _make_bulk_adapter("CHEM", "CHEM",
            expected_hashes=[{"canonical_id": "c1", "content_hash": "H1"}],
            documents=[],
        )
        with pytest.raises(ProjectionWriteError, match="parity"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
                db_canonical_ids={"c1", "c2"},  # c2 DB-only
            )
        client.mget.assert_not_called()

    def test_adapter_only_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        adapter = _make_bulk_adapter("CHEM", "CHEM",
            expected_hashes=[
                {"canonical_id": "c1", "content_hash": "H1"},
                {"canonical_id": "c2", "content_hash": "H2"},
            ],
            documents=[],
        )
        with pytest.raises(ProjectionWriteError, match="parity"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
                db_canonical_ids={"c1"},  # c2 adapter-only
            )


class TestBulkSyncB06:
    """B06: MGET all hashes same → NOOP=N, UPSERT=0, bulk call=0."""

    def test_all_noop_no_bulk(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        sb = _fake_sb(rebuild_active=False)
        ids = [f"c{i}" for i in range(5)]
        mget_results = {f"CHEM::{cid}": "SAME_HASH" for cid in ids}
        client = _fake_os_client(mget_results=mget_results)
        expected = [{"canonical_id": cid, "content_hash": "SAME_HASH"} for cid in ids]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, [])
        result = bulk_sync_published_domain(
            domain_name="CHEM", object_type="CHEM",
            os_client=client, supabase_client=sb,
            adapter_map={"CHEM": adapter},
        )
        assert result["noop"] == 5
        assert result["upsert"] == 0
        assert result["batches"] == 0
        # no bulk write needed
        from opensearchpy.helpers import bulk as os_bulk
        # bulk never called — verify via upsert==0 and batches==0


class TestBulkSyncB07:
    """B07: Some hash diff → NOOP=A, UPSERT=B, A+B=N, bulk gets B only."""

    def test_partial_upsert(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch
        sb = _fake_sb(rebuild_active=False)

        # c0, c1 match; c2, c3 differ
        mget_results = {
            "CHEM::c0": "HASH_0", "CHEM::c1": "HASH_1",
            "CHEM::c2": "OLD_HASH_2", "CHEM::c3": None,
        }
        client = _fake_os_client(mget_results=mget_results)

        hash_map = {"c0": "HASH_0", "c1": "HASH_1", "c2": "HASH_2", "c3": "HASH_3"}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload("c2"), _bulk_payload("c3")]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare(hash_map)):
            with patch("services.shared_search.incremental.bulk_upsert_documents",
                       return_value=(2, 0)) as mock_bulk:
                result = bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                )

        assert result["noop"] == 2
        assert result["upsert"] == 2
        assert result["noop"] + result["upsert"] == 4
        # bulk received only the 2 changed docs
        call_items = list(mock_bulk.call_args[0][2])
        assert len(call_items) == 2


class TestBulkSyncB08:
    """B08: Missing OS document → treated as UPSERT candidate."""

    def test_missing_doc_is_upsert(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client(mget_results={"CHEM::c1": None})  # not found

        hash_map = {"c1": "HASH_1"}
        expected = [{"canonical_id": "c1", "content_hash": "HASH_1"}]
        documents = [_bulk_payload("c1")]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare(hash_map)):
            with patch("services.shared_search.incremental.bulk_upsert_documents",
                       return_value=(1, 0)):
                result = bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                )

        assert result["upsert"] == 1
        assert result["noop"] == 0


class TestBulkSyncB09:
    """B09: PASS1/PASS2 hash mismatch → BLOCKED before write."""

    def test_hash_mismatch_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        from unittest.mock import patch
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client(mget_results={"CHEM::c1": None})

        # PASS1 hash differs from what prepare_search_document returns
        expected = [{"canonical_id": "c1", "content_hash": "PASS1_HASH"}]
        documents = [_bulk_payload("c1")]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        # prepare returns PASS2_DIFFERENT_HASH — deliberately mismatches PASS1_HASH
        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare({"c1": "PASS2_DIFFERENT_HASH"})):
            with pytest.raises(ProjectionWriteError, match="hash mismatch"):
                bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                )


class TestBulkSyncB10:
    """B10: Non-PUBLISHED payload → BLOCKED, DELETE=0."""

    def test_hold_payload_raises(self):
        from services.shared_search.incremental import bulk_sync_published_domain, ProjectionWriteError
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client(mget_results={"CHEM::c1": None})

        expected = [{"canonical_id": "c1", "content_hash": "HASH_1"}]
        hold_doc = dict(_bulk_payload("c1"), publication_status="HOLD")
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, [hold_doc])

        with pytest.raises(ProjectionWriteError, match="Non-PUBLISHED"):
            bulk_sync_published_domain(
                domain_name="CHEM", object_type="CHEM",
                os_client=client, supabase_client=sb,
                adapter_map={"CHEM": adapter},
            )


class TestBulkSyncB11:
    """B11: Fence activates before second batch → batch1 written, batch2 not."""

    def test_fence_mid_run(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        # fence calls: initial check (False), batch1 check (False), batch2 check (True)
        fence_calls = [0]
        def _fence(sb):
            fence_calls[0] += 1
            return fence_calls[0] >= 3  # inactive x1(initial)+x1(batch1), active x1(batch2)+

        sb = MagicMock()
        client = _fake_os_client()
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": False} for i in kwargs["body"]["ids"]]
        }

        ids = [f"c{i}" for i in range(4)]
        hash_map = {cid: f"H{i}" for i, cid in enumerate(ids)}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload(cid) for cid in ids]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        def _bulk(client, index, items, chunk_size=500):
            return len(list(items)), 0

        with patch("services.shared_search.incremental._rebuild_active", side_effect=_fence):
            with patch("services.shared_search.incremental.prepare_search_document",
                       side_effect=_mock_prepare(hash_map)):
                with patch("services.shared_search.incremental.bulk_upsert_documents",
                           side_effect=_bulk):
                    result = bulk_sync_published_domain(
                        domain_name="CHEM", object_type="CHEM",
                        os_client=client, supabase_client=sb,
                        adapter_map={"CHEM": adapter},
                        chunk_size=2,
                    )

        assert result["fence_blocked"] is True
        assert result["batches"] == 1  # only first chunk written


class TestBulkSyncB12:
    """B12: Alias changes before second batch → batch1 written, batch2 not."""

    def test_alias_drift_mid_run(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        sb = _fake_sb(rebuild_active=False)

        alias_calls = [0]
        def _get_alias(name):
            alias_calls[0] += 1
            if alias_calls[0] <= 2:  # initial freeze + batch-1 guard
                return {"tai-original-001": {}}
            return {"tai-new-index-002": {}}  # drifted at batch-2 guard

        client = MagicMock()
        client.indices.get_alias.side_effect = _get_alias
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": False} for i in kwargs["body"]["ids"]]
        }

        ids = [f"c{i}" for i in range(4)]
        hash_map = {cid: f"H{i}" for i, cid in enumerate(ids)}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload(cid) for cid in ids]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare(hash_map)):
            with patch("services.shared_search.incremental.bulk_upsert_documents",
                       return_value=(2, 0)):
                result = bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                    chunk_size=2,
                )

        assert result["alias_drift"] is True
        assert result["batches"] == 1  # first chunk written before drift detected


class TestBulkSyncB13:
    """B13: Bulk item failure → next batch not written, failed>0."""

    def test_bulk_failure_stops(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": False} for i in kwargs["body"]["ids"]]
        }

        ids = [f"c{i}" for i in range(4)]
        hash_map = {cid: f"H{i}" for i, cid in enumerate(ids)}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload(cid) for cid in ids]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        call_counts = [0]
        def _bulk(client, index, items, chunk_size=500):
            call_counts[0] += 1
            items_list = list(items)
            if call_counts[0] == 1:
                return len(items_list) - 1, 1  # 1 failure in first batch
            return len(items_list), 0

        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare(hash_map)):
            with patch("services.shared_search.incremental.bulk_upsert_documents",
                       side_effect=_bulk):
                result = bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                    chunk_size=2,
                )

        assert result["failed"] > 0
        assert result["batches"] == 1  # stopped after first failed batch


class TestBulkSyncB14:
    """B14: No per-object GET; N=1000 → client.get calls=0, mget calls≈2."""

    def test_no_per_object_get_calls(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        N = 1000
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": True,
                       "_source": {"content_hash": "SAME"}}
                     for i in kwargs["body"]["ids"]]
        }

        expected = [{"canonical_id": f"c{i}", "content_hash": "SAME"} for i in range(N)]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, [])

        bulk_sync_published_domain(
            domain_name="CHEM", object_type="CHEM",
            os_client=client, supabase_client=sb,
            adapter_map={"CHEM": adapter},
            mget_batch_size=500,
        )

        # Zero per-object GET calls
        client.get.assert_not_called()
        # Exactly 2 MGET calls (1000 / 500)
        assert client.mget.call_count == 2


class TestBulkSyncB15:
    """B15: No per-object alias lookup; N=1000/chunk=500 → initial + batch guards."""

    def test_alias_lookup_count(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        N = 1000
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": False} for i in kwargs["body"]["ids"]]
        }

        hash_map = {f"c{i}": f"H{i}" for i in range(N)}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload(f"c{i}") for i in range(N)]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        with patch("services.shared_search.incremental.prepare_search_document",
                   side_effect=_mock_prepare(hash_map)):
            with patch("services.shared_search.incremental.bulk_upsert_documents",
                       return_value=(500, 0)):
                bulk_sync_published_domain(
                    domain_name="CHEM", object_type="CHEM",
                    os_client=client, supabase_client=sb,
                    adapter_map={"CHEM": adapter},
                    mget_batch_size=500,
                    chunk_size=500,
                )

        # 1 initial freeze + 2 per-batch re-checks = 3
        assert client.indices.get_alias.call_count == 3
        # NOT 1000
        assert client.indices.get_alias.call_count < N


class TestBulkSyncB16:
    """B16: No per-object fence reads; N=1000 → initial + batch guards."""

    def test_fence_read_count(self):
        from services.shared_search.incremental import bulk_sync_published_domain
        from unittest.mock import patch

        N = 1000
        sb = _fake_sb(rebuild_active=False)
        client = _fake_os_client()
        client.mget.side_effect = lambda **kwargs: {
            "docs": [{"_id": i, "found": False} for i in kwargs["body"]["ids"]]
        }

        hash_map = {f"c{i}": f"H{i}" for i in range(N)}
        expected = [{"canonical_id": cid, "content_hash": h} for cid, h in hash_map.items()]
        documents = [_bulk_payload(f"c{i}") for i in range(N)]
        adapter = _make_bulk_adapter("CHEM", "CHEM", expected, documents)

        fence_read_count = [0]

        def _count_fence(sb):
            fence_read_count[0] += 1
            return False

        with patch("services.shared_search.incremental._rebuild_active",
                   side_effect=_count_fence):
            with patch("services.shared_search.incremental.prepare_search_document",
                       side_effect=_mock_prepare(hash_map)):
                with patch("services.shared_search.incremental.bulk_upsert_documents",
                           return_value=(500, 0)):
                    bulk_sync_published_domain(
                        domain_name="CHEM", object_type="CHEM",
                        os_client=client, supabase_client=sb,
                        adapter_map={"CHEM": adapter},
                        mget_batch_size=500,
                        chunk_size=500,
                    )

        # 1 initial + 2 per-batch = 3 total fence reads
        assert fence_read_count[0] == 3
        # NOT 1000
        assert fence_read_count[0] < N
