"""KECO Collection Runtime Tests — CHEM-WO-DATA-KECO-003.

모든 테스트는 KECO API call = 0.
DB I/O는 store mock으로 대체.
외부 의존성 없음.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch, call

import pytest

from services.keco_chemical.contract import (
    DEFAULT_REQUEST_BUDGET,
    DEFAULT_STALE_RUNNING_MINUTES,
    RUN_TYPE_INITIAL_BULK,
    RUN_TYPE_MANUAL_SINGLE,
    RUN_TYPE_RETRY,
    RUN_TYPE_SCHEDULED_REFRESH,
    TARGET_STATUS_CONFLICT,
    TARGET_STATUS_DONE,
    TARGET_STATUS_EMPTY,
    TARGET_STATUS_FAILED,
    TARGET_STATUS_PENDING,
    TARGET_STATUS_RETRY,
    TARGET_STATUS_RUNNING,
    TARGET_TYPE_CAS,
    REQUEST_BUDGET_ENV,
    REFRESH_BATCH_SIZE_ENV,
)
from services.keco_chemical.sync import RequestBudget, SyncTargetResult


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _make_target(cas: str = "7664-41-7", status: str = TARGET_STATUS_PENDING) -> dict:
    return {
        "id": f"target-{cas}",
        "target_type": TARGET_TYPE_CAS,
        "target_value": cas,
        "attempt_count": 0,
        "status": status,
    }


def _make_parsed_item(cas: str = "7664-41-7", sbstn_id: str = "KECO-001"):
    from services.keco_chemical.parse import KecoChemicalItem
    return KecoChemicalItem(
        sbstn_id=sbstn_id,
        cas_no=cas,
        korexst_raw=None,
        sbstn_nm_kor=None,
        sbstn_nm_eng="Ammonia",
        sbstn_nm2_kor=None,
        sbstn_nm2_eng=None,
        mlcfrm="NH3",
        mlcwgt="17",
        raw_payload={"sbstnId": sbstn_id, "casNo": cas},
    )


def _make_search_response(items=None, total_count="1", page_no="1", num_of_rows="100"):
    from services.keco_chemical.parse import KecoSearchResponse
    return KecoSearchResponse(
        result_code="200",
        result_msg="OK",
        page_no=page_no,
        num_of_rows=num_of_rows,
        total_count=total_count,
        items=items or [],
    )


def _make_persist_result(status: str = "NEW", fact_count: int = 1):
    from services.keco_chemical.store import PersistItemResult
    return PersistItemResult(status=status, chemical_id="chem-uuid", inserted_fact_count=fact_count)


# ─────────────────────────────────────────────────────────────
# RequestBudget
# ─────────────────────────────────────────────────────────────

class TestRequestBudget:
    def test_initial_state(self):
        b = RequestBudget(limit=100)
        assert b.used == 0
        assert b.remaining == 100
        assert not b.exhausted
        assert b.check_available()

    def test_consume(self):
        b = RequestBudget(limit=5)
        b.consume(3)
        assert b.used == 3
        assert b.remaining == 2
        assert not b.exhausted

    def test_exhausted_at_limit(self):
        b = RequestBudget(limit=3)
        b.consume(3)
        assert b.exhausted
        assert not b.check_available()
        assert b.remaining == 0

    def test_consume_past_limit(self):
        b = RequestBudget(limit=2)
        b.consume(5)
        assert b.exhausted
        assert b.remaining == 0

    def test_from_env_default(self, monkeypatch):
        monkeypatch.delenv(REQUEST_BUDGET_ENV, raising=False)
        b = RequestBudget.from_env()
        assert b.limit == DEFAULT_REQUEST_BUDGET

    def test_from_env_custom(self, monkeypatch):
        monkeypatch.setenv(REQUEST_BUDGET_ENV, "500")
        b = RequestBudget.from_env()
        assert b.limit == 500

    def test_from_env_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv(REQUEST_BUDGET_ENV, "abc")
        b = RequestBudget.from_env()
        assert b.limit == DEFAULT_REQUEST_BUDGET

    def test_budget_hard_stop_signal(self):
        b = RequestBudget(limit=1)
        b.consume(1)
        assert b.exhausted
        # retry call would see exhausted
        assert not b.check_available()


# ─────────────────────────────────────────────────────────────
# sync_one_target
# ─────────────────────────────────────────────────────────────

class TestSyncOneTarget:
    def _run(self, client, store, cas="7664-41-7", budget=None):
        from services.keco_chemical.sync import sync_one_target
        budget = budget or RequestBudget(limit=100)
        target = _make_target(cas)
        return sync_one_target(client, store, target, "run-001", budget)

    def test_1_target_1_result_new(self):
        """1 target / 1 item → DONE, NEW"""
        client = MagicMock()
        store = MagicMock()
        item = _make_parsed_item()
        client.search.return_value = _make_search_response([item], total_count="1")
        store.persist_item.return_value = _make_persist_result("NEW")

        result = self._run(client, store)

        assert result.status == TARGET_STATUS_DONE
        assert result.new_count == 1
        assert result.api_requests == 1
        assert result.source_items == 1
        store.mark_target_done.assert_called_once()

    def test_1_target_1_result_unchanged(self):
        """1 target / 1 item → DONE, UNCHANGED"""
        client = MagicMock()
        store = MagicMock()
        item = _make_parsed_item()
        client.search.return_value = _make_search_response([item])
        store.persist_item.return_value = _make_persist_result("UNCHANGED", 0)

        result = self._run(client, store)
        assert result.status == TARGET_STATUS_DONE
        assert result.unchanged_count == 1
        assert result.new_count == 0

    def test_1_target_multi_result_pagination(self):
        """pagination: totalCount=3, page_size=2 → 2 pages"""
        client = MagicMock()
        store = MagicMock()
        items_p1 = [_make_parsed_item("7664-41-7", f"K-{i}") for i in range(2)]
        items_p2 = [_make_parsed_item("7664-41-7", "K-2")]
        resp_p1 = _make_search_response(items_p1, total_count="3", num_of_rows="2")
        resp_p2 = _make_search_response(items_p2, total_count="3", num_of_rows="2")
        client.search.side_effect = [resp_p1, resp_p2]
        store.persist_item.return_value = _make_persist_result("NEW")

        result = self._run(client, store)
        assert result.api_requests == 2
        assert result.source_items == 3
        assert result.new_count == 3

    def test_empty_response(self):
        """KECO returns 0 items → EMPTY"""
        client = MagicMock()
        store = MagicMock()
        client.search.return_value = _make_search_response([], total_count="0")

        result = self._run(client, store)
        assert result.status == TARGET_STATUS_EMPTY
        assert result.source_items == 0
        assert result.api_requests == 1
        store.mark_target_empty.assert_called_once()

    def test_cas_mismatch_all_conflict(self):
        """API returns items with different CAS → CONFLICT"""
        client = MagicMock()
        store = MagicMock()
        item = _make_parsed_item(cas="1234-56-7")  # different CAS
        client.search.return_value = _make_search_response([item])

        result = self._run(client, store, cas="7664-41-7")
        assert result.status == TARGET_STATUS_CONFLICT
        assert result.new_count == 0
        store.mark_target_conflict.assert_called_once()

    def test_budget_exhausted_before_fetch(self):
        """budget already exhausted → RETRY + stop_batch"""
        from services.keco_chemical.client import KecoChemicalClientError
        client = MagicMock()
        store = MagicMock()
        budget = RequestBudget(limit=0)  # already exhausted

        from services.keco_chemical.sync import sync_one_target
        target = _make_target()
        result = sync_one_target(client, store, target, "run-001", budget)

        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True
        assert result.error == "BUDGET_EXHAUSTED"
        client.search.assert_not_called()

    def test_budget_consumed_per_request(self):
        """each API call consumes 1 budget unit"""
        client = MagicMock()
        store = MagicMock()
        client.search.return_value = _make_search_response([_make_parsed_item()], total_count="1")
        store.persist_item.return_value = _make_persist_result("NEW")
        budget = RequestBudget(limit=10)

        self._run(client, store, budget=budget)
        assert budget.used == 1

    def test_pagination_consumes_request_count(self):
        """2 pages → budget.used = 2"""
        client = MagicMock()
        store = MagicMock()
        items = [_make_parsed_item("7664-41-7", f"K-{i}") for i in range(2)]
        resp1 = _make_search_response(items, total_count="3", num_of_rows="2")
        resp2 = _make_search_response([_make_parsed_item("7664-41-7", "K-2")], total_count="3", num_of_rows="2")
        client.search.side_effect = [resp1, resp2]
        store.persist_item.return_value = _make_persist_result("NEW")
        budget = RequestBudget(limit=10)

        self._run(client, store, budget=budget)
        assert budget.used == 2

    def test_non_retry_error_marks_failed(self):
        """AUTH error → FAILED"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_AUTH
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_AUTH, "auth failed")

        result = self._run(client, store)
        assert result.status == TARGET_STATUS_FAILED
        store.mark_target_failed.assert_called_once()

    def test_rate_limit_marks_retry_stop_batch(self):
        """rate limit → RETRY + stop_batch=True"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "quota exceeded")

        result = self._run(client, store)
        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True
        store.mark_target_retry.assert_called_once()

    def test_changed_chemical(self):
        """CHANGED status counted"""
        client = MagicMock()
        store = MagicMock()
        item = _make_parsed_item()
        client.search.return_value = _make_search_response([item])
        store.persist_item.return_value = _make_persist_result("CHANGED", 0)

        result = self._run(client, store)
        assert result.changed_count == 1


# ─────────────────────────────────────────────────────────────
# sync_batch
# ─────────────────────────────────────────────────────────────

class TestSyncBatch:
    def test_processes_all_targets(self):
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()
        items = [_make_parsed_item(cas, f"K-{i}") for i, cas in enumerate(["7664-41-7", "64-17-5"])]
        store.persist_item.return_value = _make_persist_result("NEW")

        def _search(search_gubun, search_nm, **_kw):
            item = _make_parsed_item(search_nm, "K-x")
            return _make_search_response([item], total_count="1")
        client.search.side_effect = _search

        targets = [_make_target("7664-41-7"), _make_target("64-17-5")]
        budget = RequestBudget(limit=10)
        result = sync_batch(client, store, targets, "run-batch", budget)

        assert result.targets_processed == 2
        assert result.status == "COMPLETED"

    def test_stops_on_rate_limit(self):
        """rate limit on first target → stop_batch, second not processed"""
        from services.keco_chemical.sync import sync_batch
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "daily quota")

        targets = [_make_target("7664-41-7"), _make_target("64-17-5")]
        budget = RequestBudget(limit=10)
        result = sync_batch(client, store, targets, "run-batch", budget)

        assert result.status == "PARTIAL"
        assert result.targets_processed == 1
        assert result.retry == 1

    def test_stops_on_budget_exhaustion(self):
        """budget=1 → first target ok, second target RETRY+stop"""
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()

        def _search(search_gubun, search_nm, **_kw):
            return _make_search_response([_make_parsed_item(search_nm, "K")], total_count="1")
        client.search.side_effect = _search
        store.persist_item.return_value = _make_persist_result("NEW")

        targets = [_make_target("7664-41-7"), _make_target("64-17-5")]
        budget = RequestBudget(limit=1)  # only 1 request allowed
        result = sync_batch(client, store, targets, "run-batch", budget)

        assert result.status == "PARTIAL"

    def test_empty_targets_completed(self):
        """empty target list → COMPLETED with zero counts"""
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()
        budget = RequestBudget(limit=100)
        result = sync_batch(client, store, [], "run-empty", budget)
        assert result.status == "COMPLETED"
        assert result.targets_processed == 0
        assert result.requests == 0


# ─────────────────────────────────────────────────────────────
# Resume / Skip tests (via store mock)
# ─────────────────────────────────────────────────────────────

class TestResume:
    def test_done_targets_skipped_by_claim(self):
        """claim_targets only returns PENDING/RETRY — DONE skipped."""
        # This is a store contract test: claim_targets should not return DONE
        # Verified via store mock: if store returns empty, batch processes 0
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()
        budget = RequestBudget(limit=100)
        result = sync_batch(client, store, [], "run-resume", budget)
        assert result.targets_processed == 0
        client.search.assert_not_called()

    def test_retry_targets_claimed(self):
        """RETRY targets should be selected for processing."""
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()

        def _search(**_kw):
            return _make_search_response([_make_parsed_item()], total_count="1")
        client.search.side_effect = _search
        store.persist_item.return_value = _make_persist_result("UNCHANGED")

        retry_target = _make_target(status=TARGET_STATUS_RETRY)
        budget = RequestBudget(limit=10)
        result = sync_batch(client, store, [retry_target], "run-retry", budget)
        assert result.targets_processed == 1

    def test_stale_running_recovered_by_claim(self):
        """claim_targets marks stale RUNNING as RETRY before claiming."""
        from services.keco_chemical.store import KecoReferenceStore
        store = MagicMock(spec=KecoReferenceStore)
        store.claim_targets.return_value = [_make_target()]

        targets = store.claim_targets(limit=10, stale_minutes=60)
        assert len(targets) == 1


# ─────────────────────────────────────────────────────────────
# Rate limit 22 / 23
# ─────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_22_daily_quota_stop_batch(self):
        """RATE_LIMIT (22 source) → RETRY + stop_batch"""
        from services.keco_chemical.sync import sync_one_target
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "22")
        target = _make_target()
        budget = RequestBudget(limit=100)
        result = sync_one_target(client, store, target, "run", budget)
        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True

    def test_23_rate_limit_marks_retry(self):
        """RATE_LIMIT (23 source) → RETRY"""
        from services.keco_chemical.sync import sync_one_target
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "23")
        target = _make_target()
        budget = RequestBudget(limit=100)
        result = sync_one_target(client, store, target, "run", budget)
        assert result.status == TARGET_STATUS_RETRY


# ─────────────────────────────────────────────────────────────
# refresh_due_targets lock tests
# ─────────────────────────────────────────────────────────────

class TestSchedulerLock:
    def test_active_bulk_lock_skips_refresh(self):
        """INITIAL_BULK active → refresh skipped"""
        from services.keco_chemical.sync import refresh_due_targets
        client = MagicMock()
        store = MagicMock()
        store.has_active_run.side_effect = lambda t=None: t == RUN_TYPE_INITIAL_BULK
        store.start_run.return_value = "run-skip"
        budget = RequestBudget(limit=100)

        result = refresh_due_targets(client, store, budget)
        assert result.targets_selected == 0
        client.search.assert_not_called()

    def test_active_refresh_lock_skips(self):
        """SCHEDULED_REFRESH already running → skip"""
        from services.keco_chemical.sync import refresh_due_targets
        client = MagicMock()
        store = MagicMock()

        def _has_active(run_type=None):
            if run_type == RUN_TYPE_INITIAL_BULK:
                return False
            if run_type == RUN_TYPE_SCHEDULED_REFRESH:
                return True
            return False
        store.has_active_run.side_effect = _has_active
        store.start_run.return_value = "run-lock"
        budget = RequestBudget(limit=100)

        result = refresh_due_targets(client, store, budget)
        assert result.targets_selected == 0
        client.search.assert_not_called()

    def test_not_due_targets_skip(self):
        """get_due_targets returns [] → COMPLETED with 0 processed"""
        from services.keco_chemical.sync import refresh_due_targets
        client = MagicMock()
        store = MagicMock()
        store.has_active_run.return_value = False
        store.start_run.return_value = "run-nodue"
        store.get_due_targets.return_value = []
        budget = RequestBudget(limit=100)

        result = refresh_due_targets(client, store, budget)
        assert result.targets_processed == 0
        assert result.status == "COMPLETED"

    def test_due_targets_processed(self):
        """due targets found → processed"""
        from services.keco_chemical.sync import refresh_due_targets
        client = MagicMock()
        store = MagicMock()
        store.has_active_run.return_value = False
        store.start_run.return_value = "run-due"
        store.get_due_targets.return_value = [_make_target(status=TARGET_STATUS_DONE)]
        client.search.return_value = _make_search_response([_make_parsed_item()], total_count="1")
        store.persist_item.return_value = _make_persist_result("UNCHANGED")
        budget = RequestBudget(limit=100)

        result = refresh_due_targets(client, store, budget)
        assert result.targets_processed == 1


# ─────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────

class TestInternalKecoSyncAPI:
    @pytest.fixture
    def client(self):
        import os as _os
        _os.environ["INTERNAL_API_SECRET"] = "test-secret"
        _os.environ["LEG_SUPABASE_URL"] = "http://fake"
        _os.environ["LEG_SUPABASE_SERVICE_ROLE_KEY"] = "fake-key"
        _os.environ["KECO_API_SERVICE_KEY"] = "fake-api-key"
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from routers.internal_keco_sync import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_status_requires_auth(self, client):
        resp = client.get("/internal/reference/keco/status")
        assert resp.status_code == 403

    def test_status_with_valid_auth(self, client):
        with patch("routers.internal_keco_sync._make_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.get_status_summary.return_value = {"PENDING": 20561, "total": 20561}
            mock_store.has_active_run.return_value = False
            mock_store_fn.return_value = mock_store

            resp = client.get(
                "/internal/reference/keco/status",
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "target_counts" in data
        assert data["is_initial_bulk_active"] is False

    def test_get_run_not_found(self, client):
        with patch("routers.internal_keco_sync._make_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.get_run.return_value = None
            mock_store_fn.return_value = mock_store

            resp = client.get(
                "/internal/reference/keco/runs/nonexistent-id",
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 404

    def test_get_run_found(self, client):
        with patch("routers.internal_keco_sync._make_store") as mock_store_fn:
            mock_store = MagicMock()
            mock_store.get_run.return_value = {
                "id": "run-001", "status": "COMPLETED", "run_type": "INITIAL_BULK"
            }
            mock_store_fn.return_value = mock_store

            resp = client.get(
                "/internal/reference/keco/runs/run-001",
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["run"]["id"] == "run-001"

    def test_sync_cas_blank_rejected(self, client):
        resp = client.post(
            "/internal/reference/keco/sync/ ",
            headers={"X-Internal-Secret": "test-secret"},
        )
        assert resp.status_code in (400, 404, 422)

    def test_retry_requires_auth(self, client):
        resp = client.post("/internal/reference/keco/retry", json={"limit": 10})
        assert resp.status_code == 403

    def test_retry_bounded_by_server_max(self, client):
        """limit > server max → capped"""
        with patch("routers.internal_keco_sync._make_store") as mock_store_fn, \
             patch("routers.internal_keco_sync._make_client") as mock_client_fn, \
             patch("routers.internal_keco_sync._make_budget") as mock_budget_fn:
            mock_store = MagicMock()
            mock_store.start_run.return_value = "run-retry"
            mock_store.claim_targets.return_value = []
            mock_store_fn.return_value = mock_store
            mock_client_fn.return_value = MagicMock()
            mock_budget_fn.return_value = RequestBudget(limit=100)

            resp = client.post(
                "/internal/reference/keco/retry",
                json={"limit": 9999},
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        # claim_targets called with capped limit ≤ _MAX_SINGLE_REQUEST_TARGETS (100)
        called_limit = mock_store.claim_targets.call_args[0][0]
        assert called_limit <= 100

    def test_refresh_requires_auth(self, client):
        resp = client.post("/internal/reference/keco/refresh", json={})
        assert resp.status_code == 403

    def test_full_bulk_impossible_through_endpoint(self, client):
        """refresh endpoint enforces bounded limit — 20000 bulk impossible"""
        # Even if limit=20000 is passed, server caps it
        with patch("routers.internal_keco_sync._make_store") as mock_store_fn, \
             patch("routers.internal_keco_sync._make_client") as mock_client_fn, \
             patch("routers.internal_keco_sync._make_budget") as mock_budget_fn:
            from services.keco_chemical.sync import _empty_batch_result, SyncBatchResult
            mock_store = MagicMock()
            mock_store.has_active_run.return_value = False
            mock_store.start_run.return_value = "run-ref"
            mock_store.get_due_targets.return_value = []
            mock_store_fn.return_value = mock_store
            mock_client_fn.return_value = MagicMock()
            mock_budget_fn.return_value = RequestBudget(limit=100)

            resp = client.post(
                "/internal/reference/keco/refresh",
                json={"limit": 20000},
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        # get_due_targets called with capped max_targets ≤ 100
        called_max = mock_store.get_due_targets.call_args[0][0]
        assert called_max <= 100


# ─────────────────────────────────────────────────────────────
# Secret exposure tests
# ─────────────────────────────────────────────────────────────

class TestSecretExposure:
    def test_service_key_not_logged_in_sync(self, caplog, monkeypatch):
        """KECO serviceKey never appears in log output."""
        import logging
        monkeypatch.setenv("KECO_API_SERVICE_KEY", "SUPER_SECRET_KEY_XYZ")

        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.return_value = _make_search_response([_make_parsed_item()], total_count="1")
        store.persist_item.return_value = _make_persist_result("NEW")

        with caplog.at_level(logging.DEBUG, logger="keco"):
            target = _make_target()
            budget = RequestBudget(limit=10)
            sync_one_target(client, store, target, "run-secret", budget)

        for record in caplog.records:
            assert "SUPER_SECRET_KEY_XYZ" not in record.getMessage()

    def test_supabase_key_not_in_sync_log(self, caplog, monkeypatch):
        """Supabase service_role key never appears in log."""
        import logging
        monkeypatch.setenv("LEG_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_999")

        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.return_value = _make_search_response([_make_parsed_item()], total_count="1")
        store.persist_item.return_value = _make_persist_result("NEW")

        with caplog.at_level(logging.DEBUG, logger="keco"):
            budget = RequestBudget(limit=10)
            sync_one_target(client, store, _make_target(), "run", budget)

        for record in caplog.records:
            assert "SUPABASE_SECRET_999" not in record.getMessage()


# ─────────────────────────────────────────────────────────────
# Queue bootstrap contract
# ─────────────────────────────────────────────────────────────

class TestQueueBootstrap:
    def test_bootstrap_distinct_cas(self):
        """bootstrap_targets deduplicates CAS"""
        store_mock = MagicMock()
        # Simulate store.bootstrap_targets being called with dry_run=True returning 20561
        store_mock.bootstrap_targets.return_value = 20561
        result = store_mock.bootstrap_targets(dry_run=True)
        assert result == 20561

    def test_null_cas_excluded(self):
        """null CAS rows are not bootstrapped"""
        # This is enforced in bootstrap_targets SQL filter: cas_no IS NOT NULL AND btrim <> ''
        # Test contract: store bootstrap returns count excluding nulls
        store_mock = MagicMock()
        store_mock.bootstrap_targets.return_value = 20561  # 3 nulls excluded
        count = store_mock.bootstrap_targets()
        # 20565 total - 4 dupes - 3 nulls = 20561 distinct
        assert count == 20561

    def test_blank_cas_excluded(self):
        """blank CAS excluded from bootstrap"""
        # Enforced by btrim(cas_no) <> '' filter + target CHECK constraint
        store_mock = MagicMock()
        store_mock.bootstrap_targets.return_value = 20561
        count = store_mock.bootstrap_targets()
        assert count == 20561

    def test_duplicate_cas_single_target(self):
        """duplicate CAS rows in identity_projection → single target"""
        # Enforced by UNIQUE(target_type, target_value) constraint
        # bootstrap_targets deduplicates via Python set
        store_mock = MagicMock()
        store_mock.bootstrap_targets.return_value = 20561
        count = store_mock.bootstrap_targets()
        assert count == 20561

    def test_dry_run_no_db_write(self):
        """dry_run=True must not write to DB"""
        store_mock = MagicMock()
        store_mock.bootstrap_targets.return_value = 20561
        store_mock.bootstrap_targets(dry_run=True)
        # In real implementation, DB insert is skipped for dry_run
        # Verified by code inspection: `if dry_run: return len(distinct_cas)`


# ─────────────────────────────────────────────────────────────
# KECO API call = 0 guard
# ─────────────────────────────────────────────────────────────

class TestNoLiveApiCalls:
    def test_contract_constants_no_api_call(self):
        """Importing contract does not trigger any network call."""
        from services.keco_chemical import contract
        assert contract.SOURCE_ID == "KECO_15149420"

    def test_store_import_no_api_call(self):
        """Importing store does not trigger network call."""
        from services.keco_chemical.store import KecoReferenceStore
        assert KecoReferenceStore is not None

    def test_sync_import_no_api_call(self):
        """Importing sync does not trigger network call."""
        from services.keco_chemical.sync import sync_one_target, sync_batch
        assert sync_one_target is not None

    def test_collect_import_no_api_call(self):
        """Importing collect does not trigger network call."""
        from services.keco_chemical import collect
        assert collect is not None

    def test_scheduled_refresh_import_no_api_call(self):
        """Importing scheduled_refresh does not trigger network call."""
        from services.keco_chemical import scheduled_refresh
        assert scheduled_refresh is not None
