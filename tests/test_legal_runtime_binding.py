"""RT-LEG-01~06: Runtime integration tests for LEGAL binding.

RT-LEG-01: opensearch_rebuild._build_legal_supabase_client raises EnvironmentError when env missing
RT-LEG-02: f2_census._build_legal_supabase_client raises EnvironmentError when env missing
RT-LEG-03: process_queue() LEGAL event + no legal_client → failed=1, completed=0
RT-LEG-04: LegalBindingUnavailable exported; iter_documents and object_reindex_payload both raise it
RT-LEG-05: build_production_adapters with legal_client routes LEGAL queries to legal_client only
RT-LEG-06: process_queue() LEGAL event + legal_client + KC stub → UPSERT, search_text complete
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── RT-LEG-01 ─────────────────────────────────────────────────────────────────

def test_rt_leg_01_rebuild_missing_leg_env_raises(monkeypatch):
    """opensearch_rebuild._build_legal_supabase_client raises EnvironmentError when LEG env absent."""
    monkeypatch.delenv("LEG_DB_URL", raising=False)
    monkeypatch.delenv("LEG_DB_KEY", raising=False)

    from tools.shared_search.opensearch_rebuild import _build_legal_supabase_client
    with pytest.raises(EnvironmentError, match="LEGAL_BINDING_UNAVAILABLE"):
        _build_legal_supabase_client()


def test_rt_leg_01b_rebuild_partial_leg_env_raises(monkeypatch):
    """Only LEG_DB_URL set (key missing) → EnvironmentError."""
    monkeypatch.setenv("LEG_DB_URL", "https://fake.supabase.co")
    monkeypatch.delenv("LEG_DB_KEY", raising=False)

    from tools.shared_search.opensearch_rebuild import _build_legal_supabase_client
    with pytest.raises(EnvironmentError, match="LEGAL_BINDING_UNAVAILABLE"):
        _build_legal_supabase_client()


# ── RT-LEG-02 ─────────────────────────────────────────────────────────────────

def test_rt_leg_02_census_missing_leg_env_raises(monkeypatch):
    """f2_census._build_legal_supabase_client raises EnvironmentError when LEG env absent."""
    monkeypatch.delenv("LEG_DB_URL", raising=False)
    monkeypatch.delenv("LEG_DB_KEY", raising=False)

    from tools.shared_search.f2_census import _build_legal_supabase_client
    with pytest.raises(EnvironmentError, match="LEGAL_BINDING_UNAVAILABLE"):
        _build_legal_supabase_client()


# ── RT-LEG-03 ─────────────────────────────────────────────────────────────────

def _make_sb_with_event(domain_name="LEGAL", object_type="LEGAL", canonical_id="art-001"):
    """Mock supabase that passes fence check, returns one event, and accepts fail RPC."""
    sb = MagicMock()

    event = {
        "id": 99,
        "domain_name": domain_name,
        "object_type": object_type,
        "canonical_id": canonical_id,
        "attempt_no": 1,
    }

    def table_side(name):
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.limit.return_value = tbl
        fence_result = MagicMock()
        fence_result.data = [{"rebuild_active": False}]
        tbl.execute.return_value = fence_result
        return tbl

    sb.table.side_effect = table_side

    def rpc_side(name, params):
        rpc_obj = MagicMock()
        if name == "claim_search_index_events":
            result = MagicMock()
            result.data = [event]
            rpc_obj.execute.return_value = result
        elif name == "complete_search_index_event":
            result = MagicMock()
            result.data = True
            rpc_obj.execute.return_value = result
        else:
            rpc_obj.execute.return_value = MagicMock(data=None)
        return rpc_obj

    sb.rpc.side_effect = rpc_side
    return sb


def test_rt_leg_03_legal_event_no_client_fails_event():
    """process_queue() with LEGAL event and no legal_client → failed=1, completed=0."""
    from services.shared_search.incremental import process_queue

    sb = _make_sb_with_event()
    os_mock = MagicMock()
    os_mock.indices.get_alias.return_value = {"tai-search-v1": {}}

    obs = process_queue(
        supabase_client=sb,
        os_client=os_mock,
        worker_id="test-worker",
        # legal_client omitted → LEGAL adapter is fail-closed
    )

    assert obs["failed"] == 1, f"Expected 1 failure, got {obs}"
    assert obs["completed"] == 0, f"Expected 0 completions, got {obs}"
    os_mock.delete.assert_not_called()


# ── RT-LEG-04 ─────────────────────────────────────────────────────────────────

def test_rt_leg_04_unavailable_exported_and_iter_raises():
    """LegalBindingUnavailable is exported from production_bindings and raised by iter_documents."""
    from services.shared_search.production_bindings import (
        LegalBindingUnavailable,
        _make_legal_adapter,
    )

    adapter = _make_legal_adapter(MagicMock())  # legal_client=None
    with pytest.raises(LegalBindingUnavailable):
        list(adapter.iter_documents())


def test_rt_leg_04b_unavailable_raised_by_object_reindex_payload():
    """LegalBindingUnavailable raised by object_reindex_payload when legal_client is None."""
    from services.shared_search.production_bindings import (
        LegalBindingUnavailable,
        _make_legal_adapter,
    )

    adapter = _make_legal_adapter(MagicMock())  # legal_client=None
    with pytest.raises(LegalBindingUnavailable):
        adapter.object_reindex_payload("some-uuid")


# ── RT-LEG-05 ─────────────────────────────────────────────────────────────────

def _make_chainable(data):
    result = MagicMock()
    result.data = data
    q = MagicMock()
    for m in ("select", "eq", "in_", "neq", "order", "range", "limit", "gt"):
        getattr(q, m).return_value = q
    q.execute.return_value = result
    return q


def test_rt_leg_05_build_production_adapters_routes_legal_to_legal_client():
    """build_production_adapters with legal_client: LEGAL uses legal_client, not app_client."""
    from services.shared_search.production_bindings import build_production_adapters

    legal_client = MagicMock()
    legal_client.table.return_value = _make_chainable([])

    app_client = MagicMock()
    app_client.table.return_value = _make_chainable([])

    adapters = build_production_adapters(app_client, legal_client=legal_client)
    legal_adapter = next(a for a in adapters if a.domain_name == "LEGAL")
    list(legal_adapter.iter_documents())

    called_on_legal = {c.args[0] for c in legal_client.table.call_args_list}
    called_on_app = {c.args[0] for c in app_client.table.call_args_list}

    assert "law_master" in called_on_legal, (
        "LEGAL adapter must use legal_client for law_master"
    )
    for law_table in ("law_master", "law_article", "law_attachment"):
        assert law_table not in called_on_app, (
            f"app_client must NOT be used for {law_table}"
        )


# ── RT-LEG-06 ─────────────────────────────────────────────────────────────────

_KC_STUB = (
    '「전기용품 안전기준(KC 62619)」의 자세한 내용은 상단 메뉴 "<img id="40425753">'
    '자세한 내용</img>" 버튼을 이용하십시오.'
)


def _make_kc_legal_client_for_rt():
    """Mock leg-prod client with a KC stub article + 45983-char attachment.

    Uses MagicMock with side_effect so the adapter's _fetch_by_id and
    _fetch_legal_attachments_batch both see the right data.
    """
    masters = [
        {"id": "m-kc", "law_name": "전기용품안전관리법",
         "is_active": True, "current_version_id": "ver-kc"}
    ]
    articles = [{
        "id": "art-kc-rt",
        "law_id": "m-kc",
        "law_version_id": "ver-kc",
        "article_no": 1,
        "article_sub_no": None,
        "article_title": "「KC 62619」의 자세한 내용은",
        "article_text": _KC_STUB,
        "is_deleted_in_version": False,
        "enforcement_date": "2023-01-01",
        "updated_at": "2023-01-01T00:00:00",
        "record_kind": "law_article",
    }]
    att_meta = [{
        "id": "att-kc-rt",
        "law_version_id": "ver-kc",
        "attachment_title": "KC 62619 Ed 2.0",
        "attachment_no": 1,
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
    }]
    att_text = [{"id": "att-kc-rt", "attachment_text": "가" * 45983}]

    def _chainable_q_rt(data):
        result = MagicMock()
        result.data = data
        q = MagicMock()
        for m in ("select", "eq", "in_", "neq", "order", "range", "limit", "gt"):
            getattr(q, m).return_value = q
        q.execute.return_value = result
        return q

    def table_side(name):
        tbl = MagicMock()
        if name == "law_master":
            tbl.select.return_value = _chainable_q_rt(masters)
        elif name == "law_article":
            tbl.select.return_value = _chainable_q_rt(articles)
        elif name == "law_attachment":
            def sel_side(cols):
                if "attachment_text" in cols:
                    return _chainable_q_rt(att_text)
                return _chainable_q_rt(att_meta)
            tbl.select.side_effect = sel_side
        else:
            tbl.select.return_value = _chainable_q_rt([])
        return tbl

    client = MagicMock()
    client.table.side_effect = table_side
    return client


def test_rt_leg_06_incremental_positive_kc_attachment():
    """process_queue() LEGAL event + legal_client + KC stub → UPSERT with full attachment body."""
    from opensearchpy import NotFoundError
    from services.shared_search.incremental import process_queue

    legal_client = _make_kc_legal_client_for_rt()
    sb = _make_sb_with_event(
        domain_name="LEGAL",
        object_type="LEGAL",
        canonical_id="art-kc-rt",
    )

    indexed_body: dict = {}

    os_mock = MagicMock()
    os_mock.indices.get_alias.return_value = {"tai-search-v1": {}}
    os_mock.get.side_effect = NotFoundError(404, "not found", {})

    def _index_side(**kwargs):
        indexed_body.update(kwargs.get("body") or {})
        return {"result": "created"}

    os_mock.index.side_effect = _index_side

    obs = process_queue(
        supabase_client=sb,
        os_client=os_mock,
        legal_client=legal_client,
        worker_id="test-worker-rt06",
    )

    assert obs["failed"] == 0, f"Expected 0 failures, got {obs}"
    assert obs["completed"] == 1, f"Expected 1 completion, got {obs}"
    os_mock.delete.assert_not_called()
    os_mock.index.assert_called_once()

    search_text = indexed_body.get("search_text", "")
    assert len(search_text) > 1000, (
        f"search_text must contain 45k attachment body, got {len(search_text)} chars"
    )
    assert "상단 메뉴" not in search_text, "stub navigation phrase must not appear in search_text"
    assert "버튼을 이용하십시오" not in search_text, "stub button phrase must not appear in search_text"
