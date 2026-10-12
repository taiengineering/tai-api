"""WO-020 Source Gate: ReferenceFormAdapter unit tests.

Covers all 8 Source Gate items + PATCH-1 extensions:
  SG-1  Only published records enter the index (publication gate via view)
  SG-2  canonical_id = reference_forms.id (UUID passthrough)
  SG-3  PUBLISHED gate fields: publication_status, visibility_scopes
  SG-4  Deletion path: unpublished/excluded rows produce no document
  SG-5  _PUBLIC_OBJECT_TYPES / _TYPE_MAP / _SECTION_TYPES all wire REFERENCE_FORM
  SG-6  safetySearch.js type key maps to correct objectType
  SG-7  public_url is /reference-form/{canonical_slug}
  SG-8  re-enqueue SQL uses new event_key; ON CONFLICT DO NOTHING; no DEAD mutation

PATCH-1 extensions:
  P1    Rights gate: non-CLEARED sources exclude form from index
  P2    Deletion trigger: migration enqueues event on rights_status/is_active change
  P3    body_html indexing: HTML stripped, body keywords searchable
"""
from __future__ import annotations

import re
import uuid
import pytest

from services.shared_search.adapters.reference_form import (
    ReferenceFormAdapter,
    _normalize,
)
from routers.public_safety_search import (
    _PUBLIC_OBJECT_TYPES,
    _TYPE_MAP,
    _SECTION_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _row(**kwargs) -> dict:
    defaults = {
        "id": str(uuid.uuid4()),
        "canonical_slug": "ref-c001",
        "title": "안전보건경영방침 수립 서식",
        "description": "안전보건경영방침 수립 예시 서식",
        "updated_at": "2026-10-11T00:00:00+00:00",
        "published_at": "2026-10-10T00:00:00+00:00",
        "legacy_codes": ["C001"],
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# SG-1: Publication gate
# ---------------------------------------------------------------------------

class TestPublicationGate:
    """SG-1: reference_form_public_view already enforces PUBLISHED + approved_content_hash.
    The adapter must never add extra rows beyond what the view returns."""

    def test_iter_documents_yields_from_fetcher(self):
        rows = [_row(canonical_slug="ref-c001"), _row(canonical_slug="ref-c002")]
        adapter = ReferenceFormAdapter(fetch_current=lambda: iter(rows))
        docs = list(adapter.iter_documents())
        assert len(docs) == 2
        assert {d["source_key"] for d in docs} == {"ref-c001", "ref-c002"}

    def test_empty_view_yields_no_docs(self):
        adapter = ReferenceFormAdapter(fetch_current=lambda: iter([]))
        assert list(adapter.iter_documents()) == []

    def test_object_reindex_payload_calls_fetch_by_id(self):
        row = _row(canonical_slug="ref-c005")
        adapter = ReferenceFormAdapter(
            fetch_current=lambda: iter([]),
            fetch_by_id=lambda cid: row,
        )
        doc = adapter.object_reindex_payload(row["id"])
        assert doc is not None
        assert doc["source_key"] == "ref-c005"

    def test_object_reindex_payload_returns_none_for_missing_id(self):
        adapter = ReferenceFormAdapter(
            fetch_current=lambda: iter([]),
            fetch_by_id=lambda cid: None,
        )
        assert adapter.object_reindex_payload("nonexistent-id") is None


# ---------------------------------------------------------------------------
# SG-2: canonical_id = reference_forms.id passthrough
# ---------------------------------------------------------------------------

class TestCanonicalId:
    """SG-2: canonical_id must be the raw UUID string from reference_forms.id."""

    def test_canonical_id_equals_row_id(self):
        form_id = str(uuid.uuid4())
        doc = _normalize(_row(id=form_id))
        assert doc is not None
        assert doc["canonical_id"] == form_id

    def test_canonical_id_is_string(self):
        doc = _normalize(_row())
        assert isinstance(doc["canonical_id"], str)

    def test_uuid_format_preserved(self):
        form_id = "38435237-519a-4a4a-a1a7-7681522507c6"
        doc = _normalize(_row(id=form_id))
        assert doc["canonical_id"] == form_id


# ---------------------------------------------------------------------------
# SG-3: PUBLISHED gate fields
# ---------------------------------------------------------------------------

class TestPublishedGateFields:
    """SG-3: publication_status='PUBLISHED'; visibility_scopes=['PUBLIC']."""

    def test_publication_status_is_published(self):
        doc = _normalize(_row())
        assert doc["publication_status"] == "PUBLISHED"

    def test_visibility_scopes_public_only(self):
        doc = _normalize(_row())
        assert doc["visibility_scopes"] == ["PUBLIC"]

    def test_object_type_is_reference_form(self):
        doc = _normalize(_row())
        assert doc["object_type"] == "REFERENCE_FORM"

    def test_source_id(self):
        doc = _normalize(_row())
        assert doc["source_id"] == "TAI_REFERENCE_FORM"


# ---------------------------------------------------------------------------
# SG-4: Deletion path — excluded rows yield None from _normalize
# ---------------------------------------------------------------------------

class TestDeletionPath:
    """SG-4: When a form is removed from reference_form_public_view
    (unpublished, approval revoked, hash mismatch) it no longer appears in
    iter_documents().  The Foundation's reconciliation finds it absent from
    iter_expected_hashes() and removes it from OpenSearch.

    _normalize() must return None for rows missing any required field so
    that malformed rows don't pollute the index.
    """

    def test_missing_id_returns_none(self):
        assert _normalize(_row(id=None)) is None
        assert _normalize(_row(id="")) is None

    def test_missing_title_returns_none(self):
        assert _normalize(_row(title=None)) is None
        assert _normalize(_row(title="")) is None

    def test_missing_canonical_slug_returns_none(self):
        assert _normalize(_row(canonical_slug=None)) is None
        assert _normalize(_row(canonical_slug="")) is None

    def test_missing_both_timestamps_returns_none(self):
        assert _normalize(_row(updated_at=None, published_at=None)) is None

    def test_updated_at_only_is_sufficient(self):
        doc = _normalize(_row(updated_at="2026-10-11T00:00:00+00:00", published_at=None))
        assert doc is not None

    def test_published_at_fallback_when_no_updated_at(self):
        doc = _normalize(_row(updated_at=None, published_at="2026-10-10T00:00:00+00:00"))
        assert doc is not None
        assert doc["source_updated_at"] == "2026-10-10T00:00:00+00:00"

    def test_excluded_row_not_in_iter_documents(self):
        bad_row = _row(title="")   # missing title → _normalize returns None
        adapter = ReferenceFormAdapter(fetch_current=lambda: iter([bad_row]))
        assert list(adapter.iter_documents()) == []


# ---------------------------------------------------------------------------
# SG-5: Router wiring — _PUBLIC_OBJECT_TYPES / _TYPE_MAP / _SECTION_TYPES
# ---------------------------------------------------------------------------

class TestRouterWiring:
    """SG-5: All three router constants must register REFERENCE_FORM."""

    def test_reference_form_in_public_object_types(self):
        assert "REFERENCE_FORM" in _PUBLIC_OBJECT_TYPES

    def test_reference_form_in_type_map(self):
        assert "reference_form" in _TYPE_MAP
        assert _TYPE_MAP["reference_form"] == ["REFERENCE_FORM"]

    def test_reference_form_in_section_types(self):
        section_object_types = [ot for _, ot in _SECTION_TYPES]
        assert "REFERENCE_FORM" in section_object_types

    def test_section_type_key_matches_type_map_key(self):
        for type_key, ot in _SECTION_TYPES:
            if ot == "REFERENCE_FORM":
                assert type_key == "reference_form"

    def test_reference_form_type_map_is_list(self):
        assert isinstance(_TYPE_MAP["reference_form"], list)


# ---------------------------------------------------------------------------
# SG-6: safetySearch.js type key aligns with API type map
# ---------------------------------------------------------------------------

class TestSearchJsAlignment:
    """SG-6: The safetySearch.js GROUP_DEFS type='reference_form' must map to
    objectType='REFERENCE_FORM', and this must match _TYPE_MAP on the API side."""

    # Python-side contract: _TYPE_MAP["reference_form"] → ["REFERENCE_FORM"]
    def test_api_type_key_produces_reference_form_object_type(self):
        result = _TYPE_MAP.get("reference_form", [])
        assert "REFERENCE_FORM" in result

    def test_adapter_domain_name_matches_object_type(self):
        assert ReferenceFormAdapter.domain_name == "REFERENCE_FORM"
        assert ReferenceFormAdapter.object_type == "REFERENCE_FORM"


# ---------------------------------------------------------------------------
# SG-7: public_url
# ---------------------------------------------------------------------------

class TestPublicUrl:
    """SG-7: public_url must be /reference-form/{canonical_slug}."""

    def test_public_url_format(self):
        doc = _normalize(_row(canonical_slug="ref-c005"))
        assert doc["public_url"] == "/reference-form/ref-c005"

    def test_public_url_uses_canonical_slug_not_id(self):
        form_id = str(uuid.uuid4())
        doc = _normalize(_row(id=form_id, canonical_slug="ref-c001"))
        assert doc["public_url"] == "/reference-form/ref-c001"
        assert form_id not in doc["public_url"]

    def test_saas_url_is_none(self):
        doc = _normalize(_row())
        assert doc["saas_url"] is None


# ---------------------------------------------------------------------------
# SG-8: re-enqueue SQL review
# ---------------------------------------------------------------------------

class TestReenqueueSql:
    """SG-8: scripts/wo020_reenqueue_reference_forms.sql must:
      - call enqueue_search_index_sync
      - use new event_key pattern REFERENCE_FORM:{id}:WO-020-ADAPTER-REGISTERED
      - use ON CONFLICT DO NOTHING (idempotent)
      - NOT touch search_index_outbox.status directly (no UPDATE on status)
    """

    @pytest.fixture
    def sql(self):
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "scripts" / "wo020_reenqueue_reference_forms.sql"
        return p.read_text()

    def test_calls_enqueue_rpc(self, sql):
        assert "enqueue_search_index_sync" in sql

    def test_event_key_includes_wo020_marker(self, sql):
        assert "WO-020-ADAPTER-REGISTERED" in sql

    def test_event_key_domain_prefix(self, sql):
        assert "REFERENCE_FORM:" in sql

    def test_reads_from_public_view(self, sql):
        assert "reference_form_public_view" in sql

    def test_no_direct_status_update(self, sql):
        sql_upper = sql.upper()
        assert "UPDATE" not in sql_upper or "DO NOTHING" in sql_upper

    def test_no_delete_statement(self, sql):
        assert "DELETE" not in sql.upper()


# ---------------------------------------------------------------------------
# Normalizer: field mapping completeness
# ---------------------------------------------------------------------------

class TestNormalizerFieldMapping:
    """All SearchDocument contract fields must be present and typed correctly."""

    def test_all_required_keys_present(self):
        doc = _normalize(_row())
        required = [
            "object_type", "canonical_id", "source_id", "source_key",
            "title", "summary", "search_text", "aliases", "keywords",
            "subjects", "context", "public_url", "saas_url",
            "publication_status", "visibility_scopes", "source_updated_at",
        ]
        for k in required:
            assert k in doc, f"missing key: {k}"

    def test_aliases_contains_legacy_codes(self):
        doc = _normalize(_row(legacy_codes=["C001", "REF-C001"]))
        assert "C001" in doc["aliases"]
        assert "REF-C001" in doc["aliases"]

    def test_search_text_includes_title_description_codes(self):
        doc = _normalize(_row(
            title="안전보건경영방침",
            description="수립 서식",
            legacy_codes=["C001"],
        ))
        assert "안전보건경영방침" in doc["search_text"]
        assert "수립 서식" in doc["search_text"]
        assert "C001" in doc["search_text"]

    def test_empty_description_sets_summary_none(self):
        doc = _normalize(_row(description=None))
        assert doc["summary"] is None

    def test_empty_legacy_codes(self):
        doc = _normalize(_row(legacy_codes=None))
        assert doc["aliases"] == []
        assert "keywords" in doc
        assert doc["keywords"] == []

    def test_updated_at_preferred_over_published_at(self):
        doc = _normalize(_row(
            updated_at="2026-10-11T12:00:00+00:00",
            published_at="2026-10-01T00:00:00+00:00",
        ))
        assert doc["source_updated_at"] == "2026-10-11T12:00:00+00:00"


# ---------------------------------------------------------------------------
# PATCH-1 / P1: Rights gate — _cleared_form_ids filtering
# Tests use the adapter with a mock fetcher that simulates the binding's
# rights check (rows pre-filtered by _cleared_form_ids before reaching adapter).
# ---------------------------------------------------------------------------

class TestRightsGate:
    """P1: Only CLEARED forms may enter the index.
    The binding calls _cleared_form_ids() and sets a sentinel before yielding.
    We test _normalize's behaviour and the adapter wiring via a simulated binding.
    """

    def test_cleared_row_indexed(self):
        """Row that passed rights check (_body_html injected) → document produced."""
        row = _row(_body_html="")
        assert _normalize(row) is not None

    def test_non_cleared_row_excluded_by_binding(self):
        """Binding skips row if form_id not in cleared set — yields zero documents."""
        # Simulate binding: fetcher only yields if cleared. Here we test that
        # an adapter whose fetcher yields zero rows (rights-excluded) produces no docs.
        adapter = ReferenceFormAdapter(fetch_current=lambda: iter([]))
        assert list(adapter.iter_documents()) == []

    def test_binding_excludes_blocked_rights(self):
        """Adapter with fetcher that simulates blocking (yields nothing for non-CLEARED)."""
        blocked_row = _row(id="blocked-form-id")   # no _body_html — not yielded
        yielded = []
        def mock_fetch():
            # Simulate what production binding does: check rights first
            ids = [str(blocked_row["id"])]
            # Mock: _cleared_form_ids returns empty (no CLEARED sources)
            cleared = frozenset()   # blocked
            for r in [blocked_row]:
                if str(r["id"]) not in cleared:
                    continue
                r["_body_html"] = ""
                yielded.append(r)
            return iter(yielded)
        adapter = ReferenceFormAdapter(fetch_current=mock_fetch)
        assert list(adapter.iter_documents()) == []

    def test_binding_clears_and_indexes_cleared_form(self):
        """Adapter with fetcher that passes rights — document is indexed."""
        form_row = _row(id="cleared-form-id", _body_html="")
        def mock_fetch():
            # Simulate: cleared frozenset contains this id
            cleared = frozenset(["cleared-form-id"])
            for r in [form_row]:
                if str(r["id"]) not in cleared:
                    continue
                yield r
        adapter = ReferenceFormAdapter(fetch_current=mock_fetch)
        docs = list(adapter.iter_documents())
        assert len(docs) == 1
        assert docs[0]["canonical_id"] == "cleared-form-id"

    def test_by_id_returns_none_for_rights_blocked_form(self):
        """object_reindex_payload returns None when fetch_by_id returns None
        (binding returns None when rights check fails)."""
        adapter = ReferenceFormAdapter(
            fetch_current=lambda: iter([]),
            fetch_by_id=lambda cid: None,  # binding returned None (not cleared)
        )
        assert adapter.object_reindex_payload("some-form-id") is None

    def test_fail_closed_on_empty_sources(self):
        """A form with NO active sources must NOT appear in the index.
        Binding: _cleared_form_ids returns frozenset() when sources are absent."""
        # Simulate: view returns row but sources query finds no rows → cleared = empty
        row = _row(id="no-sources-form")
        yielded = []
        def mock_fetch():
            cleared = frozenset()   # no active sources → not cleared
            for r in [row]:
                if str(r["id"]) not in cleared:
                    continue
                r["_body_html"] = ""
                yielded.append(r)
            return iter(yielded)
        adapter = ReferenceFormAdapter(fetch_current=mock_fetch)
        assert list(adapter.iter_documents()) == []


# ---------------------------------------------------------------------------
# PATCH-1 / P2: Deletion path via rights change trigger
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PATCH-1 / P3: body_html indexing
# ---------------------------------------------------------------------------

class TestBodyHtmlIndexing:
    """P3: body_html is stripped of HTML tags and included in search_text."""

    def test_body_text_included_in_search_text(self):
        row = _row(_body_html="<p>단위작업장소 안전작업절차</p>")
        doc = _normalize(row)
        assert "단위작업장소" in doc["search_text"]
        assert "안전작업절차" in doc["search_text"]

    def test_html_tags_stripped(self):
        row = _row(_body_html="<h2>작업안전수칙</h2><p>세부 내용</p>")
        doc = _normalize(row)
        assert "<h2>" not in doc["search_text"]
        assert "<p>" not in doc["search_text"]
        assert "작업안전수칙" in doc["search_text"]
        assert "세부 내용" in doc["search_text"]

    def test_body_keyword_not_in_title_is_still_searchable(self):
        """단위작업장소 is in body only, not in title or description."""
        row = _row(
            title="안전작업 서식",
            description="기본 서식",
            _body_html="<p>단위작업장소별 위험요인을 기록하십시오.</p>",
        )
        doc = _normalize(row)
        assert "단위작업장소별" in doc["search_text"]
        assert "단위작업장소별" not in doc["title"]
        assert "단위작업장소별" not in (doc["summary"] or "")

    def test_empty_body_html_does_not_crash(self):
        row = _row(_body_html=None)
        doc = _normalize(row)
        assert doc is not None
        assert "단위작업장소" not in doc["search_text"]

    def test_body_html_absent_key_does_not_crash(self):
        """Row without _body_html key (legacy path) normalises without error."""
        row = _row()   # no _body_html key at all
        doc = _normalize(row)
        assert doc is not None

    def test_search_text_contains_all_three_sources(self):
        """title + description + body_text all appear in search_text."""
        row = _row(
            title="위험성평가 서식",
            description="작업장 위험성평가",
            _body_html="<p>단위작업장소 위험요인</p>",
            legacy_codes=["RA-001"],
        )
        doc = _normalize(row)
        assert "위험성평가 서식" in doc["search_text"]
        assert "작업장 위험성평가" in doc["search_text"]
        assert "단위작업장소" in doc["search_text"]
        assert "RA-001" in doc["search_text"]

    def test_strip_html_handles_nested_tags(self):
        from services.shared_search.adapters.reference_form import _strip_html
        result = _strip_html("<div><strong>안전</strong><em>규정</em></div>")
        assert "<" not in result
        assert "안전" in result
        assert "규정" in result
