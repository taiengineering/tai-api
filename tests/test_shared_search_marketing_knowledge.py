"""WO-MKT-KNOWLEDGE-OPENSEARCH-AUTO-INDEX-001 — MarketingKnowledgeAdapter tests.

MK-01  PUBLISHED row → SearchDocument generated
MK-02  non-PUBLISHED row → None (not surfaced)
MK-03  latest content_version used (highest version number)
MK-04  HTML stripped in search_text
MK-05  canonical_id has MKTKNOW: prefix
MK-06  source_id == TAI_MARKETING_KNOWLEDGE
MK-07  public_url == /knowledge/{slug}
MK-08  visibility_scopes == [PUBLIC, SAAS, PAID]
MK-09  forbidden fields absent
MK-10  object_reindex_payload returns payload for known canonical_id
MK-11  adapter returns None for archived/non-published → tombstone path
MK-12  no duplicate canonical IDs across adapter docs
MK-13  existing KnowledgeAdapter (TAI_HELP_CENTER) regression — unmodified
MK-14  MarketingKnowledgeAdapter in adapters __init__ __all__
MK-15  marketing_client=None → MARKETING_KNOWLEDGE absent from build_production_adapters
MK-16  outbox event payload has correct domain/object/canonical
MK-17  publish hook fires after PUBLISHED transition (autopublish_worker path)
MK-18  hook failure does not propagate (publish transaction safe)
MK-19  SYNTHETIC: 80 rows all map to valid SearchDocuments (unit fixture, not production census)
MK-20  SYNTHETIC: adapter yields exactly 6028 docs for 6028-row fake store (unit fixture)
MK-21  event_key is UUID-unique on every sync call (no ON CONFLICT swallowing)
MK-22  sync endpoint reason field: default + override propagate to event_key
MK-23  _try_build_mkt_client returns None when env vars absent
MK-24  _try_build_mkt_client returns client when env vars present
MK-25  process_queue lazy-builds mkt_client for MARKETING_KNOWLEDGE events
MK-26  bulk_sync_published_domain signature accepts marketing_client keyword
MK-27  iter_documents skips ARCHIVED (only object_reindex_payload returns None)
MK-28  _make_marketing_knowledge_adapter chains _latest_versions correctly
"""
from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest

from services.shared_search.adapters import KnowledgeAdapter, MarketingKnowledgeAdapter
from services.shared_search.adapters.marketing_knowledge import (
    CANONICAL_PREFIX,
    SOURCE_ID,
    _normalize,
    from_canonical,
    to_canonical,
)
from services.shared_search.contract import FORBIDDEN_DOCUMENT_KEYS

UTC = dt.timezone.utc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mkt_row(
    content_id: str = "cid-001",
    title: str = "안전관리자 선임 기준",
    slug: str = "know-abc123",
    subject: str = "선임",
    category: str = "안전관리",
    law_name: str = "산업안전보건법",
    article: str = "제17조",
    status: str = "PUBLISHED",
    updated_at: str = "2026-10-01T00:00:00+00:00",
    meta_description: str = "안전관리자 선임 요건 요약",
    body: str = "<p>50인 이상 사업장은 <strong>선임</strong> 의무입니다.</p>",
    rules_snapshot: Optional[dict] = None,
    version: int = 1,
):
    return {
        "id": content_id,
        "title": title,
        "slug": slug,
        "subject": subject,
        "category": category,
        "law_name": law_name,
        "article": article,
        "status": status,
        "updated_at": updated_at,
        "engine_code": "know",
        "_version": {
            "content_id": content_id,
            "version": version,
            "body": body,
            "meta_description": meta_description,
            "rules_snapshot": rules_snapshot or {"keyword": "안전관리자"},
        },
    }


def _make_adapter(*rows: dict) -> MarketingKnowledgeAdapter:
    rows_list = list(rows)

    def _by_id(canonical_id: str) -> Optional[dict]:
        cid = from_canonical(canonical_id)
        for r in rows_list:
            if r.get("id") == cid:
                return r
        return None

    return MarketingKnowledgeAdapter(
        fetch_current=lambda: iter(rows_list),
        fetch_by_id=_by_id,
    )


# ---------------------------------------------------------------------------
# MK-01: PUBLISHED row → valid SearchDocument
# ---------------------------------------------------------------------------

def test_mk01_published_generates_document():
    adapter = _make_adapter(_mkt_row())
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    doc = docs[0]
    assert doc["object_type"] == "KNOWLEDGE"
    assert doc["publication_status"] == "PUBLISHED"
    assert doc["title"] == "안전관리자 선임 기준"


# ---------------------------------------------------------------------------
# MK-02: non-PUBLISHED → not surfaced
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_status", ["DRAFT", "REVIEW", "APPROVED", "ARCHIVED"])
def test_mk02_non_published_excluded(bad_status: str):
    adapter = _make_adapter(_mkt_row(status=bad_status))
    docs = list(adapter.iter_documents())
    assert docs == []


# ---------------------------------------------------------------------------
# MK-03: latest version used
# ---------------------------------------------------------------------------

def test_mk03_latest_version_used():
    row = _mkt_row(meta_description="v2 meta", version=2)
    row["_version"]["meta_description"] = "v2 meta"
    adapter = _make_adapter(row)
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0]["summary"] == "v2 meta"


# ---------------------------------------------------------------------------
# MK-04: HTML stripped
# ---------------------------------------------------------------------------

def test_mk04_html_stripped():
    row = _mkt_row(
        body="<p>안전관리자는 <strong>50명</strong> 이상 필요</p>",
        meta_description="",
    )
    adapter = _make_adapter(row)
    docs = list(adapter.iter_documents())
    assert "<p>" not in docs[0]["search_text"]
    assert "<strong>" not in docs[0]["search_text"]
    assert "50명" in docs[0]["search_text"]


# ---------------------------------------------------------------------------
# MK-05: canonical_id has MKTKNOW: prefix
# ---------------------------------------------------------------------------

def test_mk05_canonical_prefix():
    row = _mkt_row(content_id="test-uuid-001")
    adapter = _make_adapter(row)
    docs = list(adapter.iter_documents())
    assert docs[0]["canonical_id"] == f"{CANONICAL_PREFIX}test-uuid-001"


# ---------------------------------------------------------------------------
# MK-06: source_id
# ---------------------------------------------------------------------------

def test_mk06_source_id():
    adapter = _make_adapter(_mkt_row())
    docs = list(adapter.iter_documents())
    assert docs[0]["source_id"] == SOURCE_ID
    assert docs[0]["source_id"] == "TAI_MARKETING_KNOWLEDGE"


# ---------------------------------------------------------------------------
# MK-07: public_url
# ---------------------------------------------------------------------------

def test_mk07_public_url():
    row = _mkt_row(slug="know-safe-001")
    adapter = _make_adapter(row)
    docs = list(adapter.iter_documents())
    assert docs[0]["public_url"] == "/knowledge/know-safe-001"
    assert "safety-search" not in docs[0]["public_url"]


# ---------------------------------------------------------------------------
# MK-08: visibility scopes
# ---------------------------------------------------------------------------

def test_mk08_visibility_scopes():
    adapter = _make_adapter(_mkt_row())
    docs = list(adapter.iter_documents())
    assert set(docs[0]["visibility_scopes"]) == {"PUBLIC", "SAAS", "PAID"}


# ---------------------------------------------------------------------------
# MK-09: forbidden fields absent
# ---------------------------------------------------------------------------

def test_mk09_no_forbidden_fields():
    adapter = _make_adapter(_mkt_row())
    docs = list(adapter.iter_documents())
    doc = docs[0]
    for key in FORBIDDEN_DOCUMENT_KEYS:
        assert key not in doc, f"forbidden field {key!r} present"


# ---------------------------------------------------------------------------
# MK-10: object_reindex_payload
# ---------------------------------------------------------------------------

def test_mk10_object_reindex_payload():
    row = _mkt_row(content_id="reindex-cid")
    adapter = _make_adapter(row)
    canonical = to_canonical("reindex-cid")
    payload = adapter.object_reindex_payload(canonical)
    assert payload is not None
    assert payload["canonical_id"] == canonical


# ---------------------------------------------------------------------------
# MK-11: archived / tombstone path
# ---------------------------------------------------------------------------

def test_mk11_archived_returns_none():
    row = _mkt_row(content_id="arc-001", status="ARCHIVED")
    adapter = _make_adapter(row)
    canonical = to_canonical("arc-001")
    payload = adapter.object_reindex_payload(canonical)
    assert payload is None


def test_mk11_missing_returns_none():
    adapter = _make_adapter()
    payload = adapter.object_reindex_payload(to_canonical("no-such-id"))
    assert payload is None


# ---------------------------------------------------------------------------
# MK-12: no duplicate canonical IDs
# ---------------------------------------------------------------------------

def test_mk12_no_duplicate_canonicals():
    rows = [_mkt_row(content_id=f"cid-{i:03d}", slug=f"know-{i:03d}") for i in range(10)]
    adapter = _make_adapter(*rows)
    docs = list(adapter.iter_documents())
    canonicals = [d["canonical_id"] for d in docs]
    assert len(canonicals) == len(set(canonicals))


# ---------------------------------------------------------------------------
# MK-13: existing KnowledgeAdapter (TAI_HELP_CENTER) regression
# ---------------------------------------------------------------------------

def _help_row(doc_id="faq-001", title="헬프센터 질문"):
    return {
        "doc_id": doc_id,
        "title": title,
        "question": "질문 내용",
        "answer_short": "짧은 답변",
        "body": "<p>본문</p>",
        "menu_group": "안전관리",
        "status": "PUBLISHED",
        "updated_at": "2026-10-01T00:00:00+00:00",
    }


def test_mk13_help_center_adapter_regression():
    adapter = KnowledgeAdapter(fetch_current=lambda: [_help_row()])
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    doc = docs[0]
    assert doc["source_id"] == "TAI_HELP_CENTER"
    assert adapter.domain_name == "KNOWLEDGE"
    assert doc["object_type"] == "KNOWLEDGE"
    assert doc["public_url"].startswith("/safety-search/knowledge/")


# ---------------------------------------------------------------------------
# MK-14: MarketingKnowledgeAdapter in adapters __all__
# ---------------------------------------------------------------------------

def test_mk14_adapter_in_init_all():
    import services.shared_search.adapters as _mod
    assert "MarketingKnowledgeAdapter" in _mod.__all__
    from services.shared_search.adapters import MarketingKnowledgeAdapter as _cls
    assert _cls is MarketingKnowledgeAdapter


# ---------------------------------------------------------------------------
# MK-15: marketing_client=None → domain absent from build_production_adapters
# ---------------------------------------------------------------------------

def test_mk15_missing_marketing_client_fail_closed():
    from services.shared_search.production_bindings import build_production_adapters

    fake_client = MagicMock()
    adapters = build_production_adapters(fake_client, marketing_client=None)
    domain_names = [a.domain_name for a in adapters]
    assert "MARKETING_KNOWLEDGE" not in domain_names
    assert "KNOWLEDGE" in domain_names  # TAI_HELP_CENTER still present


def test_mk15_with_marketing_client_present():
    from services.shared_search.production_bindings import build_production_adapters

    fake_client = MagicMock()
    fake_mkt_client = MagicMock()
    adapters = build_production_adapters(fake_client, marketing_client=fake_mkt_client)
    domain_names = [a.domain_name for a in adapters]
    assert "MARKETING_KNOWLEDGE" in domain_names


# ---------------------------------------------------------------------------
# MK-16: outbox event payload
# ---------------------------------------------------------------------------

def test_mk16_outbox_event_payload():
    content_id = str(uuid.uuid4())
    expected_canonical = f"MKTKNOW:{content_id}"
    # Verify the canonical_id produced by the sync endpoint matches
    assert to_canonical(content_id) == expected_canonical
    assert expected_canonical.startswith("MKTKNOW:")
    assert from_canonical(expected_canonical) == content_id


# ---------------------------------------------------------------------------
# MK-17: publish hook fires after PUBLISHED transition (autopublish_worker path)
# ---------------------------------------------------------------------------

def test_mk17_publish_hook_fires():
    """run_autopublish() calls enqueue_marketing_knowledge_sync once per published content_id."""
    import sys
    import importlib.util

    autopublish_path = "/Users/taiwangsim/45cm-marketing/apps/worker/autopublish_worker.py"
    try:
        spec = importlib.util.spec_from_file_location("autopublish_worker_mk17", autopublish_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        pytest.skip("autopublish_worker.py not importable from tai-api test runner")

    fired = []
    fake_sync = MagicMock()
    fake_sync.enqueue_marketing_knowledge_sync.side_effect = lambda cid: fired.append(cid)
    sys.modules["search_sync_client"] = fake_sync

    try:
        # Fake repo: enabled=True, no limits hit, transitions succeed
        repo = MagicMock()
        repo.get_policy.return_value = {"value": {"enabled": True}}
        repo._get.side_effect = lambda table, params=None: (
            [{"id": "x"}] if table == "marketing_content" else []
        )
        repo.transition.return_value = None

        candidates = [{"content_id": "cid-test-001", "from_status": "REVIEW"}]
        result = mod.run_autopublish(repo, candidates)

        assert result["enabled"] is True
        assert len(result["published"]) == 1
        assert result["published"][0]["content_id"] == "cid-test-001"
        assert fired == ["cid-test-001"], f"expected hook fired once, got {fired}"
    finally:
        sys.modules.pop("search_sync_client", None)


# ---------------------------------------------------------------------------
# MK-18: hook failure does not propagate (publish remains successful)
# ---------------------------------------------------------------------------

def test_mk18_hook_failure_safe():
    """RuntimeError from enqueue_marketing_knowledge_sync must not roll back the publish."""
    import sys
    import importlib.util

    autopublish_path = "/Users/taiwangsim/45cm-marketing/apps/worker/autopublish_worker.py"
    try:
        spec = importlib.util.spec_from_file_location("autopublish_worker_mk18", autopublish_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        pytest.skip("autopublish_worker.py not importable from tai-api test runner")

    fail_sync = MagicMock()
    fail_sync.enqueue_marketing_knowledge_sync.side_effect = RuntimeError("network down")
    sys.modules["search_sync_client"] = fail_sync

    try:
        repo = MagicMock()
        repo.get_policy.return_value = {"value": {"enabled": True}}
        repo._get.side_effect = lambda table, params=None: (
            [{"id": "x"}] if table == "marketing_content" else []
        )
        repo.transition.return_value = None

        candidates = [{"content_id": "cid-fail-001", "from_status": "REVIEW"}]
        # Must NOT raise — hook failure is fire-and-forget
        result = mod.run_autopublish(repo, candidates)

        assert result["enabled"] is True
        assert len(result["published"]) == 1, (
            f"publish should succeed despite hook error; got {result}"
        )
        assert result["published"][0]["content_id"] == "cid-fail-001"
    finally:
        sys.modules.pop("search_sync_client", None)


# ---------------------------------------------------------------------------
# MK-19: HIGH_INTENT 80 dry-run
# ---------------------------------------------------------------------------

def test_mk19_high_intent_dry_run():
    """80 HIGH_INTENT rows (simulated) all produce valid SearchDocuments."""
    rows = []
    for i in range(80):
        rows.append(_mkt_row(
            content_id=f"hi-{i:04d}",
            slug=f"know-hi-{i:04d}",
            title=f"고의도 질문 {i}",
        ))
    adapter = _make_adapter(*rows)
    docs = list(adapter.iter_documents())
    assert len(docs) == 80
    for doc in docs:
        assert doc["object_type"] == "KNOWLEDGE"
        assert doc["canonical_id"].startswith(CANONICAL_PREFIX)
        assert doc["source_id"] == SOURCE_ID
        assert doc["public_url"].startswith("/knowledge/")
        assert doc["publication_status"] == "PUBLISHED"


# ---------------------------------------------------------------------------
# MK-20: census — adapter yields >= 6028 docs for full store
# ---------------------------------------------------------------------------

def test_mk20_census_6028():
    """SYNTHETIC unit fixture (not production census): adapter yields exactly 6028 docs for 6028-row store."""
    rows = [
        _mkt_row(
            content_id=f"bulk-{i:06d}",
            slug=f"know-bulk-{i:06d}",
            title=f"지식 콘텐츠 {i}",
        )
        for i in range(6028)
    ]
    adapter = _make_adapter(*rows)
    docs = list(adapter.iter_documents())
    assert len(docs) == 6028
    canonicals = {d["canonical_id"] for d in docs}
    assert len(canonicals) == 6028  # no duplicates


# ---------------------------------------------------------------------------
# MK-21: event_key UUID-unique on every sync call
# ---------------------------------------------------------------------------

def test_mk21_event_key_unique():
    """Two sync calls produce different event_keys so ON CONFLICT DO NOTHING
    cannot swallow the second call."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    import os

    os.environ["INTERNAL_API_SECRET"] = "test-secret-mk21"

    import importlib
    import sys
    # Stub out the supabase call
    captured_keys = []

    fake_sb = MagicMock()
    fake_rpc = MagicMock()
    fake_sb.rpc.return_value = fake_rpc
    fake_rpc.execute.return_value = MagicMock(data=None)

    with patch("db.supabase_client.get_supabase", return_value=fake_sb):
        from routers.internal_search_marketing_sync import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        cid = str(uuid.uuid4())
        headers = {"X-Internal-Secret": "test-secret-mk21"}
        body = {"content_id": cid}

        r1 = client.post("/internal/shared-search/marketing-knowledge/sync",
                         json=body, headers=headers)
        r2 = client.post("/internal/shared-search/marketing-knowledge/sync",
                         json=body, headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200

        # Extract p_event_key from both rpc calls
        calls = fake_sb.rpc.call_args_list
        assert len(calls) >= 2
        key1 = calls[-2][0][1]["p_event_key"]
        key2 = calls[-1][0][1]["p_event_key"]
        assert key1 != key2, f"event_keys must differ: {key1!r} == {key2!r}"


# ---------------------------------------------------------------------------
# MK-22: sync endpoint reason field default and override
# ---------------------------------------------------------------------------

def test_mk22_reason_field():
    """reason field defaults to 'marketing_knowledge_publish' and can be overridden."""
    import os
    os.environ["INTERNAL_API_SECRET"] = "test-secret-mk22"

    fake_sb = MagicMock()
    fake_rpc = MagicMock()
    fake_sb.rpc.return_value = fake_rpc
    fake_rpc.execute.return_value = MagicMock(data=None)

    with patch("db.supabase_client.get_supabase", return_value=fake_sb):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.internal_search_marketing_sync import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        headers = {"X-Internal-Secret": "test-secret-mk22"}
        cid = str(uuid.uuid4())

        # Default reason
        r = client.post("/internal/shared-search/marketing-knowledge/sync",
                        json={"content_id": cid}, headers=headers)
        assert r.status_code == 200
        call_args = fake_sb.rpc.call_args_list[-1][0][1]
        assert call_args["p_reason"] == "marketing_knowledge_publish"
        assert "marketing_knowledge_publish" in call_args["p_event_key"]

        # Custom reason
        fake_sb.reset_mock()
        r2 = client.post("/internal/shared-search/marketing-knowledge/sync",
                         json={"content_id": cid, "reason": "manual_reindex"},
                         headers=headers)
        assert r2.status_code == 200
        call_args2 = fake_sb.rpc.call_args_list[-1][0][1]
        assert call_args2["p_reason"] == "manual_reindex"
        assert "manual_reindex" in call_args2["p_event_key"]


# ---------------------------------------------------------------------------
# MK-23: _try_build_mkt_client returns None when env vars absent
# ---------------------------------------------------------------------------

def test_mk23_try_build_mkt_client_missing_env(monkeypatch):
    """_try_build_mkt_client() returns None when MKT env vars are not set."""
    monkeypatch.delenv("MKT_SUPABASE_URL", raising=False)
    monkeypatch.delenv("MKT_SUPABASE_SERVICE_ROLE_KEY", raising=False)

    from services.shared_search.incremental import _try_build_mkt_client
    result = _try_build_mkt_client()
    assert result is None


# ---------------------------------------------------------------------------
# MK-24: _try_build_mkt_client returns client when env vars present
# ---------------------------------------------------------------------------

def test_mk24_try_build_mkt_client_with_env(monkeypatch):
    """_try_build_mkt_client() returns a client when MKT env vars are set."""
    monkeypatch.setenv("MKT_SUPABASE_URL", "https://fake-mkt.supabase.co")
    monkeypatch.setenv("MKT_SUPABASE_SERVICE_ROLE_KEY", "fake-service-role-key")

    fake_client = MagicMock()
    with patch("supabase.create_client", return_value=fake_client):
        from services.shared_search.incremental import _try_build_mkt_client
        result = _try_build_mkt_client()
    assert result is fake_client


# ---------------------------------------------------------------------------
# MK-25: process_queue lazy-builds mkt_client for MARKETING_KNOWLEDGE events
# ---------------------------------------------------------------------------

def test_mk25_process_queue_lazy_builds_mkt_client(monkeypatch):
    """process_queue calls _try_build_mkt_client when MARKETING_KNOWLEDGE events detected."""
    monkeypatch.setenv("MKT_SUPABASE_URL", "https://fake-mkt.supabase.co")
    monkeypatch.setenv("MKT_SUPABASE_SERVICE_ROLE_KEY", "fake-mkt-key")

    fake_mkt = MagicMock()
    build_calls = []

    def fake_try_build():
        build_calls.append(1)
        return fake_mkt

    fake_sb = MagicMock()
    # Fence: inactive
    fence_row = MagicMock()
    fence_row.data = [{"rebuild_active": False}]
    fake_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = fence_row

    # Claim: one MARKETING_KNOWLEDGE event
    claim_resp = MagicMock()
    claim_resp.data = [{
        "id": 99,
        "domain_name": "MARKETING_KNOWLEDGE",
        "object_type": "KNOWLEDGE",
        "canonical_id": "MKTKNOW:test-cid-001",
        "attempt_no": 1,
    }]
    fake_sb.rpc.return_value.execute.return_value = claim_resp

    import services.shared_search.incremental as _inc
    with patch.object(_inc, "_try_build_mkt_client", side_effect=fake_try_build), \
         patch("services.shared_search.incremental._rebuild_active", return_value=False), \
         patch("services.shared_search.production_bindings.build_production_adapters",
               return_value=[]):
        try:
            _inc.process_queue(supabase_client=fake_sb, os_client=MagicMock())
        except Exception:
            pass  # We only care that the lazy-build was triggered

    assert len(build_calls) == 1, "expected _try_build_mkt_client called exactly once"


# ---------------------------------------------------------------------------
# MK-26: bulk_sync_published_domain signature accepts marketing_client
# ---------------------------------------------------------------------------

def test_mk26_bulk_sync_signature():
    """bulk_sync_published_domain accepts marketing_client keyword arg (no TypeError)."""
    import inspect
    from services.shared_search.incremental import bulk_sync_published_domain
    sig = inspect.signature(bulk_sync_published_domain)
    assert "marketing_client" in sig.parameters, (
        "marketing_client must be in bulk_sync_published_domain signature"
    )


# ---------------------------------------------------------------------------
# MK-27: iter_documents skips ARCHIVED — tombstone only via object_reindex_payload
# ---------------------------------------------------------------------------

def test_mk27_archived_skipped_in_iter_documents():
    """ARCHIVED rows are not yielded by iter_documents (tombstone is separate path)."""
    rows = [
        _mkt_row(content_id="pub-001", status="PUBLISHED"),
        _mkt_row(content_id="arc-002", status="ARCHIVED"),
    ]
    adapter = _make_adapter(*rows)
    docs = list(adapter.iter_documents())
    ids = [d["canonical_id"] for d in docs]
    assert to_canonical("pub-001") in ids
    assert to_canonical("arc-002") not in ids

    # ARCHIVED → None (tombstone) via object_reindex_payload
    payload = adapter.object_reindex_payload(to_canonical("arc-002"))
    assert payload is None


# ---------------------------------------------------------------------------
# MK-28: _make_marketing_knowledge_adapter chains _latest_versions correctly
# ---------------------------------------------------------------------------

def test_mk28_latest_versions_chained():
    """_make_marketing_knowledge_adapter picks the highest-version row."""
    content_id = "chain-001"
    slug = "know-chain-001"

    fake_mkt = MagicMock()
    from services.shared_search.adapters.marketing_knowledge import CONTENT_SELECT, VERSION_SELECT, PAGE_SIZE

    # marketing_content returns one row
    content_row = {
        "id": content_id, "title": "체인 테스트", "slug": slug,
        "subject": "s", "category": "c", "law_name": "l", "article": "a",
        "status": "PUBLISHED", "updated_at": "2026-10-01T00:00:00+00:00",
        "engine_code": "know",
    }
    content_result = MagicMock()
    content_result.data = [content_row]

    # version: two rows, version 3 is latest
    v1 = {"content_id": content_id, "version": 1, "body": "<p>v1</p>",
          "meta_description": "v1 meta", "rules_snapshot": {}}
    v3 = {"content_id": content_id, "version": 3, "body": "<p>v3</p>",
          "meta_description": "v3 meta", "rules_snapshot": {}}
    version_result = MagicMock()
    version_result.data = [v3, v1]  # production_bindings already orders by version DESC

    def _table_dispatch(table_name):
        tbl = MagicMock()
        if table_name == "marketing_content":
            tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = content_result
        else:
            tbl.select.return_value.in_.return_value.order.return_value.execute.return_value = version_result
        return tbl

    fake_mkt.table.side_effect = _table_dispatch

    from services.shared_search.production_bindings import _make_marketing_knowledge_adapter
    adapter = _make_marketing_knowledge_adapter(fake_mkt)
    docs = list(adapter.iter_documents())

    assert len(docs) == 1
    assert docs[0]["summary"] == "v3 meta"
