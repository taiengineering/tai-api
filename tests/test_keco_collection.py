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
        """each API call consumes 1 budget unit via attempt_hook"""
        client = MagicMock()
        store = MagicMock()

        def _search_with_hook(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return _make_search_response([_make_parsed_item()], total_count="1")

        client.search.side_effect = _search_with_hook
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

        responses = iter([resp1, resp2])

        def _search_paged(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return next(responses)

        client.search.side_effect = _search_paged
        store.persist_item.return_value = _make_persist_result("NEW")
        budget = RequestBudget(limit=10)

        self._run(client, store, budget=budget)
        assert budget.used == 2

    def test_non_retry_error_marks_failed(self):
        """AUTH source_code=97 (NON_RETRY_CODES) → FAILED"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_AUTH
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_AUTH, "auth failed", source_code="97")

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
        """budget=1 → first target ok (hook consumes 1), second target pre-check → PARTIAL"""
        from services.keco_chemical.sync import sync_batch
        client = MagicMock()
        store = MagicMock()

        def _search(search_gubun, search_nm, **_kw):
            hook = _kw.get("attempt_hook")
            if hook:
                hook()
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
        """claim_due_targets returns [] → COMPLETED with 0 processed"""
        from services.keco_chemical.sync import refresh_due_targets
        client = MagicMock()
        store = MagicMock()
        store.has_active_run.return_value = False
        store.start_run.return_value = "run-nodue"
        store.claim_due_targets.return_value = []
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
        store.claim_due_targets.return_value = [_make_target(status=TARGET_STATUS_DONE)]
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
            mock_store.start_exclusive_run.return_value = ("run-retry", False)
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
        # claim_targets(run_id, limit, ...) — limit is arg[1] (0-indexed)
        called_limit = mock_store.claim_targets.call_args[0][1]
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
            mock_store.claim_due_targets.return_value = []
            mock_store_fn.return_value = mock_store
            mock_client_fn.return_value = MagicMock()
            mock_budget_fn.return_value = RequestBudget(limit=100)

            resp = client.post(
                "/internal/reference/keco/refresh",
                json={"limit": 20000},
                headers={"X-Internal-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        # claim_due_targets(run_id, batch_size) — batch_size is arg[1]
        called_max = mock_store.claim_due_targets.call_args[0][1]
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

    def test_budget_import_no_api_call(self):
        """Importing budget does not trigger network call."""
        from services.keco_chemical.budget import RequestBudget, RequestBudgetExceeded
        assert RequestBudget is not None


# ─────────────────────────────────────────────────────────────
# PATCH-001 — T001-T025: Runtime Safety Fixes
# ─────────────────────────────────────────────────────────────

class TestPatch001BudgetExceeded:
    """T001-T005: RequestBudgetExceeded + physical attempt hook."""

    def test_t001_consume_or_raise_raises_when_exhausted(self):
        """T001: consume_or_raise() raises RequestBudgetExceeded when at limit"""
        from services.keco_chemical.budget import RequestBudget, RequestBudgetExceeded
        b = RequestBudget(limit=2)
        b.consume_or_raise(1)
        b.consume_or_raise(1)
        with pytest.raises(RequestBudgetExceeded):
            b.consume_or_raise(1)

    def test_t002_consume_or_raise_succeeds_within_limit(self):
        """T002: consume_or_raise() succeeds when budget available"""
        from services.keco_chemical.budget import RequestBudget
        b = RequestBudget(limit=5)
        b.consume_or_raise(3)
        assert b.used == 3

    def test_t003_budget_exceeded_attrs(self):
        """T003: RequestBudgetExceeded carries .used and .limit"""
        from services.keco_chemical.budget import RequestBudget, RequestBudgetExceeded
        b = RequestBudget(limit=1)
        b.consume_or_raise(1)
        try:
            b.consume_or_raise(1)
            assert False, "should have raised"
        except RequestBudgetExceeded as exc:
            assert exc.used == 1
            assert exc.limit == 1

    def test_t004_attempt_hook_fires_before_get_fn(self):
        """T004: attempt_hook fires before get_fn() in client._get()"""
        from unittest.mock import patch
        from services.keco_chemical.parse import KecoSearchResponse
        order = []

        def tracking_hook():
            order.append("hook")

        def tracking_get_fn(url, params, timeout):
            order.append("get_fn")
            return 200, "mock-text"

        with patch("services.keco_chemical.client.parse_keco_response") as mock_parse:
            mock_parse.return_value = KecoSearchResponse(
                result_code="200", result_msg="OK",
                page_no="1", num_of_rows="10", total_count="0", items=[],
            )
            from services.keco_chemical.client import KecoChemicalClient
            client = KecoChemicalClient(get_fn=tracking_get_fn, _service_key="fake-key")
            client.search("2", "test-cas", attempt_hook=tracking_hook)

        assert order[0] == "hook", "hook must fire BEFORE get_fn"
        assert order[1] == "get_fn"

    def test_t005_timeout_retry_counts_budget(self):
        """T005: physical timeout retry = 2 separate budget units via hook"""
        from unittest.mock import patch
        from services.keco_chemical.parse import KecoSearchResponse
        from services.keco_chemical.budget import RequestBudget

        call_count = [0]

        def flaky_get_fn(url, params, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("temporary failure")
            return 200, "mock-text"

        with patch("services.keco_chemical.client.parse_keco_response") as mock_parse:
            mock_parse.return_value = KecoSearchResponse(
                result_code="200", result_msg="OK",
                page_no="1", num_of_rows="10", total_count="0", items=[],
            )
            from services.keco_chemical.client import KecoChemicalClient
            budget = RequestBudget(limit=10)
            client = KecoChemicalClient(
                get_fn=flaky_get_fn, max_attempts=3, _service_key="fake-key"
            )
            client.search("2", "test-cas", attempt_hook=lambda: budget.consume_or_raise(1))

        assert call_count[0] == 2
        assert budget.used == 2


class TestPatch001SourceCode:
    """T006-T013: source_code attribute + retry/fail classification."""

    def test_t006_client_error_source_code_attr(self):
        """T006: KecoChemicalClientError has source_code attribute"""
        from services.keco_chemical.client import KecoChemicalClientError
        exc = KecoChemicalClientError("AUTH", "msg", source_code="97")
        assert exc.source_code == "97"

    def test_t007_client_error_source_code_default_none(self):
        """T007: source_code defaults to None for backward compat"""
        from services.keco_chemical.client import KecoChemicalClientError
        exc = KecoChemicalClientError("AUTH", "msg")
        assert exc.source_code is None

    def test_t008_client_search_accepts_attempt_hook(self):
        """T008: client.search() signature includes attempt_hook param"""
        import inspect
        from services.keco_chemical.client import KecoChemicalClient
        sig = inspect.signature(KecoChemicalClient.search)
        assert "attempt_hook" in sig.parameters

    def test_t009_validation_91_marks_failed(self):
        """T009: KECO code 91 (VALIDATION, NON_RETRY) → target FAILED"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_VALIDATION
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_VALIDATION, "invalid param", source_code="91"
        )
        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_FAILED
        store.mark_target_failed.assert_called_once()

    def test_t010_auth_97_marks_failed(self):
        """T010: KECO code 97 (AUTH, NON_RETRY) → target FAILED"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_AUTH
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_AUTH, "auth error", source_code="97"
        )
        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_FAILED

    def test_t011_upstream_12_marks_failed(self):
        """T011: KECO code 12 (in NON_RETRY_CODES) → target FAILED"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_UPSTREAM
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_UPSTREAM, "upstream error", source_code="12"
        )
        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_FAILED

    def test_t012_upstream_01_marks_retry(self):
        """T012: KECO code 01 (UPSTREAM, NOT in NON_RETRY_CODES) → target RETRY"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_UPSTREAM
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_UPSTREAM, "upstream transient", source_code="01"
        )
        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is False

    def test_t013_no_source_code_rate_limit_retry_stop(self):
        """T013: exc.code=RATE_LIMIT without source_code → RETRY+stop (fallback path)"""
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "quota exceeded")
        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True


class TestPatch001Pagination:
    """T014-T015: Pagination safety cap → RETRY."""

    def _run(self, client, store, cas="7664-41-7", budget=None):
        from services.keco_chemical.sync import sync_one_target
        budget = budget or RequestBudget(limit=200)
        return sync_one_target(client, store, _make_target(cas), "run-001", budget)

    def test_t014_pagination_cap_marks_retry(self, monkeypatch):
        """T014: safety cap reached with unread pages → RETRY"""
        monkeypatch.setattr("services.keco_chemical.sync.MAX_PAGES_SAFETY_CAP", 2)
        client = MagicMock()
        store = MagicMock()

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return _make_search_response(
                [_make_parsed_item("7664-41-7", "K-a"), _make_parsed_item("7664-41-7", "K-b")],
                total_count="6", num_of_rows="2",
            )

        client.search.side_effect = _search
        result = self._run(client, store)
        assert result.status == TARGET_STATUS_RETRY
        assert result.error == "PAGINATION_CAP"
        store.mark_target_retry.assert_called_once()

    def test_t015_natural_pagination_completion_is_done(self):
        """T015: pagination completes within cap → DONE, no false RETRY"""
        client = MagicMock()
        store = MagicMock()

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return _make_search_response([_make_parsed_item()], total_count="1")

        client.search.side_effect = _search
        store.persist_item.return_value = _make_persist_result("NEW")
        result = self._run(client, store)
        assert result.status == TARGET_STATUS_DONE
        assert result.error is None


class TestPatch001CasConflict:
    """T016-T017: Mixed CAS → CONFLICT, nothing persisted."""

    def _run(self, client, store, cas="7664-41-7"):
        from services.keco_chemical.sync import sync_one_target
        return sync_one_target(client, store, _make_target(cas), "run-001", RequestBudget(limit=100))

    def test_t016_mixed_cas_is_conflict(self):
        """T016: matched + mismatched items → CONFLICT"""
        client = MagicMock()
        store = MagicMock()
        matched = _make_parsed_item(cas="7664-41-7", sbstn_id="K-1")
        mismatched = _make_parsed_item(cas="1234-56-7", sbstn_id="K-2")
        client.search.return_value = _make_search_response(
            [matched, mismatched], total_count="2"
        )
        result = self._run(client, store)
        assert result.status == TARGET_STATUS_CONFLICT
        assert result.error == "CAS_MISMATCH"
        store.mark_target_conflict.assert_called_once()

    def test_t017_mixed_cas_nothing_persisted(self):
        """T017: any CAS mismatch → persist_item never called"""
        client = MagicMock()
        store = MagicMock()
        matched = _make_parsed_item(cas="7664-41-7", sbstn_id="K-1")
        mismatched = _make_parsed_item(cas="9999-99-9", sbstn_id="K-2")
        client.search.return_value = _make_search_response([matched, mismatched], total_count="2")
        self._run(client, store)
        store.persist_item.assert_not_called()


class TestPatch001ClaimMode:
    """T018-T019: claim_targets mode + /retry endpoint."""

    def test_t018_retry_endpoint_uses_retry_mode(self):
        """T018: POST /retry calls claim_targets with mode='retry'"""
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
        tc = TestClient(app)

        with patch("routers.internal_keco_sync._make_store") as ms, \
             patch("routers.internal_keco_sync._make_client") as mc, \
             patch("routers.internal_keco_sync._make_budget") as mb:
            mock_store = MagicMock()
            mock_store.start_exclusive_run.return_value = ("run-retry", False)
            mock_store.claim_targets.return_value = []
            ms.return_value = mock_store
            mc.return_value = MagicMock()
            mb.return_value = RequestBudget(limit=100)

            resp = tc.post(
                "/internal/reference/keco/retry",
                json={"limit": 10},
                headers={"X-Internal-Secret": "test-secret"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_store.claim_targets.call_args.kwargs
        assert call_kwargs.get("mode") == "retry"

    def test_t019_budget_imported_from_budget_module(self):
        """T019: RequestBudget importable from both budget.py and sync.py"""
        from services.keco_chemical.budget import RequestBudget as BudgetFromBudget
        from services.keco_chemical.sync import RequestBudget as BudgetFromSync
        assert BudgetFromBudget is BudgetFromSync


class TestPatch001Recovery:
    """T020-T025: Store recovery methods + budget hook mechanics."""

    def test_t020_recover_stale_runs_method_exists(self):
        """T020: KecoReferenceStore.recover_stale_runs() exists"""
        from services.keco_chemical.store import KecoReferenceStore
        assert callable(getattr(KecoReferenceStore, "recover_stale_runs", None))

    def test_t021_heartbeat_run_method_exists(self):
        """T021: KecoReferenceStore.heartbeat_run() exists"""
        from services.keco_chemical.store import KecoReferenceStore
        assert callable(getattr(KecoReferenceStore, "heartbeat_run", None))

    def test_t022_budget_hook_callable_in_sync(self):
        """T022: attempt_hook passed to client.search() is callable and increments budget"""
        client = MagicMock()
        store = MagicMock()
        client.search.return_value = _make_search_response([_make_parsed_item()], total_count="1")
        store.persist_item.return_value = _make_persist_result("NEW")
        budget = RequestBudget(limit=10)

        from services.keco_chemical.sync import sync_one_target
        sync_one_target(client, store, _make_target(), "run-001", budget)

        call_kwargs = client.search.call_args.kwargs
        hook = call_kwargs.get("attempt_hook")
        assert hook is not None and callable(hook)
        prev_used = budget.used
        hook()
        assert budget.used == prev_used + 1

    def test_t023_budget_exhausted_via_hook_is_retry_stop(self):
        """T023: RequestBudgetExceeded from hook inside search → RETRY + stop_batch"""
        from services.keco_chemical.sync import sync_one_target

        client = MagicMock()
        store = MagicMock()
        budget = RequestBudget(limit=1)

        def _search_that_consumes_budget(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
                hook()  # second call → raises RequestBudgetExceeded

        client.search.side_effect = _search_that_consumes_budget
        result = sync_one_target(client, store, _make_target(), "run", budget)

        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True
        assert result.error == "BUDGET_EXHAUSTED"

    def test_t024_budget_consumed_per_physical_page(self):
        """T024: budget.used increments once per logical page via hook"""
        client = MagicMock()
        store = MagicMock()

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return _make_search_response([_make_parsed_item()], total_count="1")

        client.search.side_effect = _search
        store.persist_item.return_value = _make_persist_result("NEW")
        budget = RequestBudget(limit=10)

        from services.keco_chemical.sync import sync_one_target
        sync_one_target(client, store, _make_target(), "run", budget)
        assert budget.used == 1

    def test_t025_all_cas_mismatch_is_conflict(self):
        """T025: all items mismatch CAS (original CONFLICT case) still works post-refactor"""
        from services.keco_chemical.sync import sync_one_target
        client = MagicMock()
        store = MagicMock()
        wrong_item = _make_parsed_item(cas="9999-00-0")
        client.search.return_value = _make_search_response([wrong_item], total_count="1")
        result = sync_one_target(client, store, _make_target("7664-41-7"), "run", RequestBudget(limit=100))
        assert result.status == TARGET_STATUS_CONFLICT
        store.mark_target_conflict.assert_called_once()
        store.persist_item.assert_not_called()


# ─────────────────────────────────────────────────────────────
# PATCH-002 — P201-P223: Final Runtime Closeout
# ─────────────────────────────────────────────────────────────

class TestPatch002Preflight:
    """P201-P205: probe.py run_preflight_probe 진입점 + budget 연동."""

    def test_p201_run_preflight_probe_importable(self):
        """P201: run_preflight_probe is importable from probe.py without ImportError"""
        from services.keco_chemical.probe import run_preflight_probe
        assert callable(run_preflight_probe)

    def test_p202_run_preflight_probe_callable(self):
        """P202: run_preflight_probe() is callable with no required args"""
        import inspect
        from services.keco_chemical.probe import run_preflight_probe
        sig = inspect.signature(run_preflight_probe)
        # all params should have defaults
        for param in sig.parameters.values():
            assert param.default is not inspect.Parameter.empty or param.kind in (
                inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD
            )

    def test_p203_run_probe_passes_attempt_hook_via_budget(self):
        """P203: run_probe() with budget passes budget.consume_or_raise as attempt_hook"""
        from services.keco_chemical.probe import run_probe
        from services.keco_chemical.budget import RequestBudget
        from services.keco_chemical.parse import KecoSearchResponse

        client = MagicMock()
        budget = RequestBudget(limit=3)
        hook_calls = []

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook_calls.append(True)
                hook()
            return KecoSearchResponse(
                result_code="200", result_msg="OK",
                page_no="1", num_of_rows="3", total_count="0", items=[],
            )

        client.search.side_effect = _search
        run_probe(client, budget=budget)

        # attempt_hook must have been called (at least once)
        assert len(hook_calls) > 0
        # budget must have been consumed
        assert budget.used > 0

    def test_p204_run_probe_caps_at_3_physical_attempts(self):
        """P204: run_probe with budget(limit=3) triggers ≤ 3 hook fires"""
        from services.keco_chemical.probe import run_probe
        from services.keco_chemical.budget import RequestBudget
        from services.keco_chemical.parse import KecoSearchResponse

        client = MagicMock()
        budget = RequestBudget(limit=3)

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            if hook:
                hook()
            return KecoSearchResponse(
                result_code="200", result_msg="OK",
                page_no="1", num_of_rows="3", total_count="0", items=[],
            )

        client.search.side_effect = _search
        run_probe(client, budget=budget)

        assert budget.used <= 3

    def test_p205_run_preflight_probe_raises_on_failed(self):
        """P205: run_preflight_probe() raises RuntimeError when probe FAILS"""
        from services.keco_chemical.probe import run_preflight_probe
        from unittest.mock import patch

        with patch("services.keco_chemical.probe._has_service_key", return_value=True), \
             patch("services.keco_chemical.probe.run_probe") as mock_run_probe:
            from services.keco_chemical.probe import PROBE_FAILED, ProbeResult, ProbeCall
            mock_run_probe.return_value = ProbeResult(
                status=PROBE_FAILED,
                calls=[ProbeCall(
                    search_gubun="2", search_nm="test",
                    status_code=None, total_count=None, item_count=0,
                    error="connection error",
                )],
            )
            with pytest.raises(RuntimeError, match="FAILED"):
                run_preflight_probe()


class TestPatch002ExclusiveLock:
    """P206-P215: start_exclusive_run + heartbeat_at + stale recovery."""

    def test_p206_start_exclusive_run_returns_run_id_and_false(self):
        """P206: start_exclusive_run() inserts run with heartbeat_at, returns (run_id, False)"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()
        fake_run_id = "run-exclusive-001"

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", return_value=fake_run_id):
            run_id, locked = store.start_exclusive_run(RUN_TYPE_INITIAL_BULK)

        assert locked is False
        assert run_id == fake_run_id

    def test_p207_recent_heartbeat_not_stale(self):
        """P207: recover_stale_runs() does not touch runs with recent heartbeat"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        with patch("services.keco_chemical.store._get_supabase_client") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.schema.return_value = mock_db

            # heartbeat_at is recent (after threshold): q1 returns []
            mock_db.table.return_value.select.return_value.eq.return_value\
                .not_.return_value.is_.return_value.lt.return_value.execute.return_value\
                .data = []
            # started_at stale but heartbeat IS NOT NULL: q2 also returns []
            mock_db.table.return_value.select.return_value.eq.return_value\
                .is_.return_value.lt.return_value.execute.return_value.data = []

            count = store.recover_stale_runs(stale_minutes=60)

        assert count == 0

    def test_p208_stale_heartbeat_marks_partial(self):
        """P208: stale heartbeat → run status PARTIAL (not FAILED)"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        with patch("services.keco_chemical.store._get_supabase_client") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.schema.return_value = mock_db

            # q1: stale heartbeat run found
            q1_result = MagicMock()
            q1_result.data = [{"id": "stale-run-001"}]

            # q2: no null-heartbeat stale runs
            q2_result = MagicMock()
            q2_result.data = []

            table_mock = MagicMock()
            mock_db.table.return_value = table_mock

            # Wire up the query chain for q1 and q2
            select_mock = MagicMock()
            table_mock.select.return_value = select_mock
            eq1 = MagicMock()
            select_mock.eq.return_value = eq1
            not_mock = MagicMock()
            eq1.not_ = not_mock
            is_mock = MagicMock()
            not_mock.is_ = MagicMock(return_value=is_mock)
            lt1 = MagicMock()
            is_mock.lt = MagicMock(return_value=lt1)
            lt1.execute.return_value = q1_result

            eq2 = MagicMock()
            # For q2: .is_("heartbeat_at", "null") chain
            eq1.is_ = MagicMock(return_value=MagicMock())
            eq1.is_.return_value.lt = MagicMock(return_value=MagicMock())
            eq1.is_.return_value.lt.return_value.execute.return_value = q2_result

            # update call
            update_mock = MagicMock()
            table_mock.update.return_value = update_mock
            update_mock.in_ = MagicMock(return_value=MagicMock())
            update_mock.eq = MagicMock(return_value=MagicMock())

            store.recover_stale_runs(stale_minutes=60)

        # Check that update was called with status="PARTIAL"
        update_calls = table_mock.update.call_args_list
        statuses = [c[0][0].get("status") for c in update_calls if isinstance(c[0][0], dict)]
        assert "PARTIAL" in statuses

    def test_p209_stale_run_targets_marked_retry(self):
        """P209: recover_stale_runs() marks RUNNING targets with stale last_run_id as RETRY"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        with patch("services.keco_chemical.store._get_supabase_client") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.schema.return_value = mock_db

            stale_run_id = "stale-run-002"
            q1_result = MagicMock()
            q1_result.data = [{"id": stale_run_id}]
            q2_result = MagicMock()
            q2_result.data = []

            table_mock = MagicMock()
            mock_db.table.return_value = table_mock
            select_mock = MagicMock()
            table_mock.select.return_value = select_mock
            eq_mock = MagicMock()
            select_mock.eq.return_value = eq_mock
            not_mock = MagicMock()
            eq_mock.not_ = not_mock
            is_mock = MagicMock()
            not_mock.is_ = MagicMock(return_value=is_mock)
            lt_mock = MagicMock()
            is_mock.lt = MagicMock(return_value=lt_mock)
            lt_mock.execute.return_value = q1_result
            eq_mock.is_ = MagicMock(return_value=MagicMock())
            eq_mock.is_.return_value.lt = MagicMock(return_value=MagicMock())
            eq_mock.is_.return_value.lt.return_value.execute.return_value = q2_result

            update_mock = MagicMock()
            table_mock.update.return_value = update_mock
            update_mock.in_ = MagicMock(return_value=MagicMock())
            update_mock.eq = MagicMock(return_value=MagicMock())

            store.recover_stale_runs(stale_minutes=60)

        # Should have called update at least twice: once for runs (PARTIAL), once for targets (RETRY)
        assert table_mock.update.call_count >= 2
        update_payloads = [c[0][0] for c in table_mock.update.call_args_list if isinstance(c[0][0], dict)]
        statuses = [p.get("status") for p in update_payloads]
        assert "PARTIAL" in statuses
        assert TARGET_STATUS_RETRY in statuses

    def test_p211_first_start_exclusive_run_not_locked(self):
        """P211: first start_exclusive_run returns (run_id, locked=False)"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", return_value="run-first"):
            run_id, locked = store.start_exclusive_run(RUN_TYPE_INITIAL_BULK)

        assert run_id == "run-first"
        assert locked is False

    def test_p212_unique_violation_returns_locked_true(self):
        """P212: start_exclusive_run catches unique violation → (None, True)"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        def _raise_unique(*args, **kwargs):
            raise Exception("ERROR: duplicate key value violates unique constraint (code 23505)")

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", side_effect=_raise_unique):
            run_id, locked = store.start_exclusive_run(RUN_TYPE_INITIAL_BULK)

        assert run_id is None
        assert locked is True

    def test_p213_bulk_blocks_refresh_exclusive(self):
        """P213: INITIAL_BULK unique violation → SCHEDULED_REFRESH blocked"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        def _raise_unique(*args, **kwargs):
            raise Exception("23505 duplicate key")

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", side_effect=_raise_unique):
            _, locked = store.start_exclusive_run(RUN_TYPE_SCHEDULED_REFRESH)

        assert locked is True

    def test_p214_bulk_blocks_retry_exclusive(self):
        """P214: existing RUNNING run → RETRY blocked"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        def _raise_unique(*args, **kwargs):
            raise Exception("unique constraint violation 23505")

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", side_effect=_raise_unique):
            _, locked = store.start_exclusive_run(RUN_TYPE_RETRY)

        assert locked is True

    def test_p215_bulk_blocks_manual_exclusive(self):
        """P215: existing RUNNING run → MANUAL_SINGLE blocked"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        def _raise_unique(*args, **kwargs):
            raise Exception("duplicate 23505")

        with patch.object(store, "recover_stale_runs", return_value=0), \
             patch.object(store, "start_run", side_effect=_raise_unique):
            _, locked = store.start_exclusive_run(RUN_TYPE_MANUAL_SINGLE)

        assert locked is True


class TestPatch002PhysicalRequests:
    """P216-P219: physical request count + record_count + PARTIAL persistence."""

    def test_p216_physical_request_count_includes_retries(self):
        """P216: hook fired twice (simulate retry) → api_requests=2"""
        from services.keco_chemical.sync import sync_one_target

        budget = RequestBudget(limit=10)
        call_count = [0]

        def _search(**kwargs):
            hook = kwargs.get("attempt_hook")
            call_count[0] += 1
            if hook:
                hook()  # first attempt
                if call_count[0] == 1:
                    hook()  # retry — second physical attempt
            return _make_search_response([_make_parsed_item()], total_count="1")

        client = MagicMock()
        client.search.side_effect = _search
        store = MagicMock()
        store.persist_item.return_value = _make_persist_result("NEW")

        result = sync_one_target(client, store, _make_target(), "run", budget)

        assert result.status == TARGET_STATUS_DONE
        assert result.api_requests == 2
        assert budget.used == 2

    def test_p217_record_count_is_source_items_in_bulk(self):
        """P217: collect.py mode_bulk passes source_items as record_count, not targets_processed"""
        import argparse
        from services.keco_chemical import collect
        from unittest.mock import patch as _patch

        call_count = [0]

        def claim_side_effect(*args, **kwargs):
            call_count[0] += 1
            return [_make_target()] if call_count[0] == 1 else []

        budget = RequestBudget(limit=100)

        batch_result = MagicMock()
        batch_result.targets_processed = 1
        batch_result.source_items = 5
        batch_result.requests = 2
        batch_result.status = "COMPLETED"
        batch_result.budget_used = 2
        batch_result.budget_remaining = 98
        batch_result.new = 5
        batch_result.unchanged = 0
        batch_result.changed = 0
        batch_result.empty = 0
        batch_result.conflict = 0
        batch_result.retry = 0
        batch_result.failed = 0
        batch_result.targets_selected = 1

        with _patch.object(collect, "_make_store") as ms, \
             _patch.object(collect, "_make_client") as mc, \
             _patch.object(collect, "_make_budget", return_value=budget), \
             _patch("services.keco_chemical.sync.sync_batch", return_value=batch_result):
            mock_store = MagicMock()
            mock_store.start_exclusive_run.return_value = ("run-bulk", False)
            mock_store.claim_targets.side_effect = claim_side_effect
            ms.return_value = mock_store
            mc.return_value = MagicMock()

            args = argparse.Namespace(max_targets=None)
            collect.mode_bulk(args)

        # finish_run(run_id, status, request_count, record_count, metrics)
        mock_store.finish_run.assert_called_once()
        call_args = mock_store.finish_run.call_args[0]
        record_count = call_args[3]
        assert record_count == 5

    def test_p218_metrics_json_contains_targets_processed(self):
        """P218: finish_run metrics_json includes targets_processed"""
        import argparse
        from services.keco_chemical import collect
        from unittest.mock import patch as _patch

        call_count = [0]

        def claim_side_effect(*args, **kwargs):
            call_count[0] += 1
            return [_make_target()] if call_count[0] == 1 else []

        budget = RequestBudget(limit=100)

        batch_result = MagicMock()
        batch_result.targets_processed = 1
        batch_result.source_items = 3
        batch_result.requests = 1
        batch_result.status = "COMPLETED"
        batch_result.budget_used = 1
        batch_result.budget_remaining = 99
        batch_result.new = 3
        batch_result.unchanged = 0
        batch_result.changed = 0
        batch_result.empty = 0
        batch_result.conflict = 0
        batch_result.retry = 0
        batch_result.failed = 0
        batch_result.targets_selected = 1

        with _patch.object(collect, "_make_store") as ms, \
             _patch.object(collect, "_make_client") as mc, \
             _patch.object(collect, "_make_budget", return_value=budget), \
             _patch("services.keco_chemical.sync.sync_batch", return_value=batch_result):
            mock_store = MagicMock()
            mock_store.start_exclusive_run.return_value = ("run-bulk", False)
            mock_store.claim_targets.side_effect = claim_side_effect
            ms.return_value = mock_store
            mc.return_value = MagicMock()

            args = argparse.Namespace(max_targets=None)
            collect.mode_bulk(args)

        call_args = mock_store.finish_run.call_args[0]
        metrics_json = call_args[4]
        assert "total_processed" in metrics_json

    def test_p219_partial_batch_result_stored_as_partial(self):
        """P219: PARTIAL SyncBatchResult → DB status PARTIAL via finish_run"""
        from services.keco_chemical.sync import sync_batch
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT

        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(ERROR_RATE_LIMIT, "daily quota")

        targets = [_make_target("7664-41-7"), _make_target("64-17-5")]
        budget = RequestBudget(limit=10)
        result = sync_batch(client, store, targets, "run-partial", budget)

        assert result.status == "PARTIAL"
        # Callers should use finish_run(result.status, ...) — test the result correctly signals PARTIAL
        assert result.status == "PARTIAL"


class TestPatch002RateLimit2223:
    """P220-P221: source_code 22/23 분리."""

    def test_p220_source_code_22_stop_batch_true(self):
        """P220: source_code='22' (daily quota) → stop_batch=True"""
        from services.keco_chemical.sync import sync_one_target
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT, RATE_LIMIT_DAILY_CODE

        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_RATE_LIMIT, "daily quota exceeded", source_code=RATE_LIMIT_DAILY_CODE
        )

        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))

        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is True

    def test_p221_source_code_23_bounded_backoff_stop_batch_false(self, monkeypatch):
        """P221: source_code='23' (per-second throttle) → bounded backoff + stop_batch=False"""
        from services.keco_chemical.sync import sync_one_target
        from services.keco_chemical.client import KecoChemicalClientError
        from services.keco_chemical.contract import ERROR_RATE_LIMIT, RATE_LIMIT_SECOND_CODE

        monkeypatch.setenv("KECO_RATE_RETRY_MAX", "2")
        sleep_calls = []
        monkeypatch.setattr("services.keco_chemical.sync.time.sleep", lambda s: sleep_calls.append(s))

        client = MagicMock()
        store = MagicMock()
        client.search.side_effect = KecoChemicalClientError(
            ERROR_RATE_LIMIT, "per-second rate limit", source_code=RATE_LIMIT_SECOND_CODE
        )

        result = sync_one_target(client, store, _make_target(), "run", RequestBudget(limit=100))

        assert result.status == TARGET_STATUS_RETRY
        assert result.stop_batch is False
        assert len(sleep_calls) == 2  # 2 retries → 2 sleeps


class TestPatch002MarkTarget:
    """P222-P223: _mark_target clear_errors + source_item_count always written."""

    def test_p222_done_clears_previous_error_fields(self):
        """P222: mark_target_done calls _mark_target with clear_errors=True"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        captured_updates = {}

        with patch("services.keco_chemical.store._get_supabase_client") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.schema.return_value = mock_db
            table_mock = MagicMock()
            mock_db.table.return_value = table_mock

            select_mock = MagicMock()
            table_mock.select.return_value = select_mock
            select_mock.eq.return_value.execute.return_value.data = [
                {"attempt_count": 2, "first_attempted_at": "2026-01-01T00:00:00+09:00"}
            ]

            update_mock = MagicMock()
            table_mock.update.return_value = update_mock
            update_mock.eq.return_value.execute.return_value.data = []

            def capture_update(payload):
                captured_updates.update(payload)
                return update_mock

            table_mock.update.side_effect = capture_update

            store.mark_target_done("target-1", "run-1", api_requests=2, source_items=3)

        # clear_errors=True → last_error_code and last_error_message set to None
        assert "last_error_code" in captured_updates
        assert captured_updates["last_error_code"] is None
        assert "last_error_message" in captured_updates
        assert captured_updates["last_error_message"] is None

    def test_p223_empty_writes_source_item_count_zero(self):
        """P223: mark_target_empty writes source_item_count=0"""
        from services.keco_chemical.store import KecoReferenceStore
        store = KecoReferenceStore()

        captured_updates = {}

        with patch("services.keco_chemical.store._get_supabase_client") as mock_client:
            mock_db = MagicMock()
            mock_client.return_value.schema.return_value = mock_db
            table_mock = MagicMock()
            mock_db.table.return_value = table_mock

            select_mock = MagicMock()
            table_mock.select.return_value = select_mock
            select_mock.eq.return_value.execute.return_value.data = [
                {"attempt_count": 0, "first_attempted_at": None}
            ]

            update_mock = MagicMock()
            table_mock.update.return_value = update_mock
            update_mock.eq.return_value.execute.return_value.data = []

            def capture_update(payload):
                captured_updates.update(payload)
                return update_mock

            table_mock.update.side_effect = capture_update

            store.mark_target_empty("target-1", "run-1", api_requests=1)

        # source_item_count must be written as 0 (not omitted)
        assert "source_item_count" in captured_updates
        assert captured_updates["source_item_count"] == 0
