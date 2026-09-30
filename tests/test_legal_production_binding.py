"""BIND-LEG-01~04: Search production binding tests for LEGAL adapter.

BIND-LEG-01: _make_legal_adapter uses legal_client for law queries, not app_client
BIND-LEG-02: _fetch_legal_attachments_batch returns attachment text for bounded candidates
BIND-LEG-03: legal_client=None → fail-closed (0 documents, app_client not touched for law data)
BIND-LEG-04: build_production_adapters passes legal_client only to LEGAL adapter
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.shared_search.production_bindings import (
    _fetch_legal_attachments_batch,
    _make_legal_adapter,
    build_production_adapters,
)

KC_STUB = (
    '「전기용품 안전기준(KC 62619)」의 자세한 내용은 상단 메뉴 "<img id="40425753">'
    '자세한 내용</img>" 버튼을 이용하십시오.'
)


def _chainable_q(data):
    """Mock query builder that chains all calls and returns data on .execute()."""
    result = MagicMock()
    result.data = data
    q = MagicMock()
    for m in ("select", "eq", "in_", "neq", "order", "range", "limit", "gt"):
        getattr(q, m).return_value = q
    q.execute.return_value = result
    return q


def _make_empty_client():
    """Client that returns empty data for every table query."""
    q = _chainable_q([])
    client = MagicMock()
    client.table.return_value = q
    return client


def _make_kc_legal_client():
    """Mock leg-prod client returning 1 KC stub article + 1 clean attachment."""
    masters = [
        {"id": "m-kc", "law_name": "전기용품안전관리법",
         "is_active": True, "current_version_id": "ver-kc"}
    ]
    articles = [{
        "id": "art-kc-uuid",
        "law_id": "m-kc",
        "law_version_id": "ver-kc",
        "article_no": 1,
        "article_sub_no": None,
        "article_title": "「KC 62619」의 자세한 내용은",
        "article_text": KC_STUB,
        "is_deleted_in_version": False,
        "enforcement_date": "2023-01-01",
        "updated_at": "2023-01-01T00:00:00",
    }]
    att_meta = [{
        "id": "att-001",
        "law_version_id": "ver-kc",
        "attachment_title": "KC 62619 Ed 2.0",
        "attachment_no": 1,
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
    }]
    att_text = [{"id": "att-001", "attachment_text": "가" * 45983}]

    def table_side(name):
        tbl = MagicMock()
        if name == "law_master":
            tbl.select.return_value = _chainable_q(masters)
        elif name == "law_article":
            tbl.select.return_value = _chainable_q(articles)
        elif name == "law_attachment":
            def sel_side(cols):
                # Phase B text select contains "attachment_text"
                if "attachment_text" in cols:
                    return _chainable_q(att_text)
                return _chainable_q(att_meta)
            tbl.select.side_effect = sel_side
        else:
            tbl.select.return_value = _chainable_q([])
        return tbl

    client = MagicMock()
    client.table.side_effect = table_side
    return client


# ── BIND-LEG-01 ──────────────────────────────────────────────────────────────

def test_bind_leg_01_legal_adapter_uses_legal_client():
    """legal_client must be queried for law_master; app_client must not be."""
    legal_client = _make_empty_client()
    app_client = _make_empty_client()

    adapter = _make_legal_adapter(app_client, legal_client=legal_client)
    list(adapter.iter_documents())

    called_on_legal = {call.args[0] for call in legal_client.table.call_args_list}
    called_on_app = {call.args[0] for call in app_client.table.call_args_list}

    assert "law_master" in called_on_legal, (
        "legal_client must be used for law_master"
    )
    for law_table in ("law_master", "law_article", "law_attachment"):
        assert law_table not in called_on_app, (
            f"app_client must NOT query {law_table}; LEGAL uses legal_client only"
        )


# ── BIND-LEG-02 ──────────────────────────────────────────────────────────────

def test_bind_leg_02_fetch_attachments_batch_returns_text_for_clean_candidates():
    """_fetch_legal_attachments_batch: Phase A+B returns attachment with text populated."""
    att_meta = [{
        "id": "att-001",
        "law_version_id": "ver-abc",
        "attachment_title": "KC 62619 Ed 2.0",
        "attachment_no": 1,
        "download_status": "SUCCESS",
        "extraction_verdict": "CLEAN",
    }]
    att_text = [{"id": "att-001", "attachment_text": "가" * 45983}]

    def table_side(name):
        assert name == "law_attachment"
        tbl = MagicMock()
        def sel_side(cols):
            if "attachment_text" in cols:
                return _chainable_q(att_text)
            return _chainable_q(att_meta)
        tbl.select.side_effect = sel_side
        return tbl

    legal_client = MagicMock()
    legal_client.table.side_effect = table_side

    result = _fetch_legal_attachments_batch(legal_client, ["ver-abc"])

    assert "ver-abc" in result
    rows = result["ver-abc"]
    assert len(rows) == 1
    assert rows[0]["id"] == "att-001"
    assert rows[0].get("attachment_text") == "가" * 45983, (
        "Phase B must populate attachment_text for SUCCESS+CLEAN candidates"
    )


def test_bind_leg_02b_kc_stub_search_text_includes_attachment_body():
    """KC stub article wired through production binding → search_text has 45k chars."""
    legal_client = _make_kc_legal_client()
    app_client = _make_empty_client()

    adapter = _make_legal_adapter(app_client, legal_client=legal_client)
    docs = list(adapter.iter_documents())

    assert len(docs) == 1
    doc = docs[0]
    assert len(doc["search_text"]) > 1000, (
        "search_text must include the resolved 45k-char attachment body"
    )
    assert "상단 메뉴" not in doc["search_text"]
    assert "버튼을 이용하십시오" not in doc["search_text"]


# ── BIND-LEG-03 ──────────────────────────────────────────────────────────────

def test_bind_leg_03_no_legal_client_yields_zero_documents():
    """Without legal_client, adapter is fail-closed: yields 0 documents."""
    app_client = _make_empty_client()

    adapter = _make_legal_adapter(app_client)  # legal_client omitted
    docs = list(adapter.iter_documents())

    assert docs == [], "Fail-closed: no legal_client → 0 documents"


def test_bind_leg_03b_no_legal_client_does_not_query_app_client_for_law_data():
    """Fail-closed mode must not fall through to app_client for law queries."""
    app_client = _make_empty_client()

    adapter = _make_legal_adapter(app_client)
    list(adapter.iter_documents())

    called_on_app = {call.args[0] for call in app_client.table.call_args_list}
    for law_table in ("law_master", "law_article", "law_attachment"):
        assert law_table not in called_on_app, (
            f"app_client must NOT be queried for {law_table} in fail-closed mode"
        )


# ── BIND-LEG-04 ──────────────────────────────────────────────────────────────

def test_bind_leg_04_build_production_adapters_routes_legal_to_legal_client():
    """build_production_adapters with legal_client: LEGAL uses legal_client, others use app_client."""
    legal_client = _make_empty_client()
    app_client = _make_empty_client()

    adapters = build_production_adapters(app_client, legal_client=legal_client)

    # Trigger all adapters; empty results are fine — we care about call routing
    for adapter in adapters:
        try:
            list(adapter.iter_documents())
        except Exception:
            pass

    called_on_legal = {call.args[0] for call in legal_client.table.call_args_list}
    called_on_app = {call.args[0] for call in app_client.table.call_args_list}

    # law_master must be queried via legal_client
    assert "law_master" in called_on_legal, (
        "LEGAL adapter must query law_master via legal_client"
    )
    # non-LEGAL tables must not route to legal_client
    non_legal_tables = {
        "kosha_guide_current", "csi_accident_current",
        "safe_help_content", "industrial_accident_precedents",
    }
    for table in non_legal_tables:
        assert table not in called_on_legal, (
            f"{table} must use app_client, not legal_client"
        )
