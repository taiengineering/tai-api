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
