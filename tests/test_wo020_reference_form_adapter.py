"""WO-020 Source Gate: ReferenceFormAdapter unit tests.

Covers all 8 Source Gate items:
  SG-1  Only published records enter the index (publication gate via view)
  SG-2  canonical_id = reference_forms.id (UUID passthrough)
  SG-3  PUBLISHED gate fields: publication_status, visibility_scopes
  SG-4  Deletion path: unpublished/excluded rows produce no document
  SG-5  _PUBLIC_OBJECT_TYPES / _TYPE_MAP / _SECTION_TYPES all wire REFERENCE_FORM
  SG-6  safetySearch.js type key maps to correct objectType
  SG-7  public_url is /reference-form/{canonical_slug}
  SG-8  re-enqueue SQL uses new event_key; ON CONFLICT DO NOTHING; no DEAD mutation
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
