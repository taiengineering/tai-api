"""WO-WWW-PERF-004-P0S-QUERY-OPT-023: MSDS OpenSearch query tests.

Verifies:
  P01 — search_by_q_os produces exactly 1 OS call per invocation.
  P02 — Priority ordering: NE > DE > KW in match_type attribution.
  P03 — NORMALIZED_EXACT hit is recognised from named queries.
  P04 — DICTIONARY_EXPANSION hit is recognised.
  P05 — KIWI_TOKEN default when matched_queries is empty.
  P06 — Pagination: from/size are forwarded to the OS query.
  P07 — track_total_hits=True is present in every DSL.
  P08 — total is extracted correctly from OS response.
  P09 — source_key absent in _source → hit silently dropped.
  P10 — OpenSearchUnavailable bubbles up on OS client exception.
  P11 — batch_current_by_chem_ids integrates correctly (in-memory store).
  P12 — search_by_q with os_search injected: exactly 1 OS call per page.
  P13 — search_by_q with os_search=None falls back to N×M Supabase path.
  P14 — English name query hits aliases field path.
  P15 — Public visibility filter is present in every DSL.
  P16 — Object-type filter is present in every DSL.
  P17 — Clause count capped at _MAX_CLAUSES.
  P18 — Empty plan (no normalized_query, no tokens) → match_none DSL.
  P19 — search_adapter.py source does not contain banned search-engine strings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.kosha_msds import read, search_adapter as A
from services.kosha_msds.opensearch_query import (
    _MAX_CLAUSES,
    _PFX_DE,
    _PFX_KW,
    _PFX_NE,
    _build_dsl,
    _best_match,
    search_by_q_os,
)
from services.shared_search.opensearch_client import OpenSearchUnavailable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(normalized="염산", expanded=(), tokens=()):
    """Build a minimal SearchPlan-like object."""
    return A.SearchPlan(
        original_query=normalized,
        normalized_query=normalized,
        compact_query=normalized,
        identifier_kind=None,
        identifier_value=None,
        tokens=tuple(tokens),
        expanded_terms=tuple(expanded),
        is_empty=False,
    )


def _cur(chem_id: str, *, ko: str = "", en: str = "") -> dict:
    return {
        "id": f"uu-{chem_id}",
        "content_id": f"CHEM:{chem_id}",
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": ko,
        "chemical_name_en": en,
        "cas_no": None,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "source_content_hash": f"sha-{chem_id}",
        "source_dataset_url": "https://example.com",
        "snapshot_id": "snap-1",
    }


def _store(*chem_ids_ko: tuple) -> read.MemoryMsdsReadStore:
    """Build a MemoryMsdsReadStore from (chem_id, ko_name) pairs."""
    rows = [_cur(cid, ko=ko) for cid, ko in chem_ids_ko]
    return read.MemoryMsdsReadStore(current_rows=rows)


def _mock_os_client(hits: list[dict], total: int = None) -> MagicMock:
    """Return an OS client mock that returns the given hits on .search()."""
    if total is None:
        total = len(hits)
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "total": {"value": total, "relation": "eq"},
            "hits": hits,
        }
    }
    return client


def _os_hit(source_key: str, matched_queries: list[str] = None) -> dict:
    return {
        "_source": {"source_key": source_key, "object_type": "CHEM"},
        "matched_queries": matched_queries or [],
    }


# ---------------------------------------------------------------------------
# P01 — exactly 1 OS call per search_by_q_os invocation
# ---------------------------------------------------------------------------

def test_P01_single_os_call_per_invocation():
    plan = _plan("염산")
    client = _mock_os_client([_os_hit("000001")])
    search_by_q_os(plan, limit=20, offset=0, _client=client)
    assert client.search.call_count == 1, "expected exactly 1 OS call"


# ---------------------------------------------------------------------------
# P02 — NE > DE > KW priority in named-query attribution
# ---------------------------------------------------------------------------

def test_P02_ne_wins_over_de_and_kw():
    mqs = [f"{_PFX_KW}:염", f"{_PFX_DE}:hcl", f"{_PFX_NE}:염산"]
    mt, term = _best_match(mqs, "default")
    assert mt == A.MATCH_NORMALIZED_EXACT
    assert term == "염산"


def test_P02_de_wins_over_kw():
    mqs = [f"{_PFX_KW}:염", f"{_PFX_DE}:hcl"]
    mt, term = _best_match(mqs, "default")
    assert mt == A.MATCH_DICTIONARY
    assert term == "hcl"


def test_P02_kw_is_default():
    mt, term = _best_match([], "fallback")
    assert mt == A.MATCH_KIWI_TOKEN
    assert term == "fallback"


# ---------------------------------------------------------------------------
# P03 — NORMALIZED_EXACT hit recognised
# ---------------------------------------------------------------------------

def test_P03_normalized_exact_recognised():
    plan = _plan("염산")
    client = _mock_os_client([
        _os_hit("000001", matched_queries=[f"{_PFX_NE}:염산"]),
    ])
    result = search_by_q_os(plan, _client=client)
    assert result["hits"][0]["match_type"] == A.MATCH_NORMALIZED_EXACT
    assert result["hits"][0]["matched_term"] == "염산"


# ---------------------------------------------------------------------------
# P04 — DICTIONARY_EXPANSION hit recognised
# ---------------------------------------------------------------------------

def test_P04_dictionary_expansion_recognised():
    plan = _plan("벤젠", expanded=("benzene",))
    client = _mock_os_client([
        _os_hit("001008", matched_queries=[f"{_PFX_DE}:benzene"]),
    ])
    result = search_by_q_os(plan, _client=client)
    assert result["hits"][0]["match_type"] == A.MATCH_DICTIONARY


# ---------------------------------------------------------------------------
# P05 — KIWI_TOKEN is default when matched_queries empty
# ---------------------------------------------------------------------------

def test_P05_kiwi_token_default():
    plan = _plan("벤젠", tokens=("벤",))
    client = _mock_os_client([_os_hit("001008", matched_queries=[])])
    result = search_by_q_os(plan, _client=client)
    assert result["hits"][0]["match_type"] == A.MATCH_KIWI_TOKEN


# ---------------------------------------------------------------------------
# P06 — from/size forwarded correctly
# ---------------------------------------------------------------------------

def test_P06_pagination_forwarded():
    plan = _plan("벤젠")
    client = _mock_os_client([])
    search_by_q_os(plan, limit=10, offset=30, _client=client)
    body = client.search.call_args[1]["body"]
    assert body["from"] == 30
    assert body["size"] == 10


# ---------------------------------------------------------------------------
# P07 — track_total_hits=True present
# ---------------------------------------------------------------------------

def test_P07_track_total_hits_present():
    plan = _plan("염산")
    dsl = _build_dsl(plan, from_=0, size=20)
    assert dsl.get("track_total_hits") is True


def test_P07_track_total_hits_present_match_none():
    empty = _plan("", expanded=(), tokens=())
    empty = A.SearchPlan(
        original_query="", normalized_query="", compact_query="",
        identifier_kind=None, identifier_value=None,
        tokens=(), expanded_terms=(), is_empty=True,
    )
    dsl = _build_dsl(empty, from_=0, size=20)
    assert dsl.get("track_total_hits") is True


# ---------------------------------------------------------------------------
# P08 — total extracted from OS response
# ---------------------------------------------------------------------------

def test_P08_total_extraction():
    plan = _plan("벤젠")
    client = _mock_os_client(
        [_os_hit("001008"), _os_hit("001009")],
        total=42,
    )
    result = search_by_q_os(plan, _client=client)
    assert result["total"] == 42
    assert len(result["hits"]) == 2


# ---------------------------------------------------------------------------
# P09 — source_key absent → hit dropped
# ---------------------------------------------------------------------------

def test_P09_missing_source_key_dropped():
    plan = _plan("벤젠")
    client = _mock_os_client([
        {"_source": {"object_type": "CHEM"}, "matched_queries": []},  # no source_key
        _os_hit("001008"),
    ])
    result = search_by_q_os(plan, _client=client)
    assert len(result["hits"]) == 1
    assert result["hits"][0]["chem_id"] == "001008"


# ---------------------------------------------------------------------------
# P10 — OpenSearchUnavailable propagates
# ---------------------------------------------------------------------------

def test_P10_unavailable_propagates():
    plan = _plan("벤젠")
    client = MagicMock()
    client.search.side_effect = OpenSearchUnavailable("OS down")
    with pytest.raises(OpenSearchUnavailable):
        search_by_q_os(plan, _client=client)


def test_P10_generic_exception_wrapped():
    plan = _plan("벤젠")
    client = MagicMock()
    client.search.side_effect = ConnectionError("timeout")
    with pytest.raises(OpenSearchUnavailable):
        search_by_q_os(plan, _client=client)


# ---------------------------------------------------------------------------
# P11 — batch_current_by_chem_ids integration
# ---------------------------------------------------------------------------

def test_P11_batch_hydration_in_memory():
    st = _store(("001008", "벤젠"), ("097377", "메탄올"), ("012345", "수산화나트륨"))
    result = read.batch_current_by_chem_ids(store=st, chem_ids=["001008", "012345"])
    assert set(result.keys()) == {"001008", "012345"}
    assert result["001008"]["chemical_name_ko"] == "벤젠"
    assert result["012345"]["chemical_name_ko"] == "수산화나트륨"


def test_P11_batch_missing_chem_id_omitted():
    st = _store(("001008", "벤젠"))
    result = read.batch_current_by_chem_ids(store=st, chem_ids=["001008", "999999"])
    assert "999999" not in result
    assert "001008" in result


def test_P11_batch_empty_list():
    st = _store(("001008", "벤젠"))
    result = read.batch_current_by_chem_ids(store=st, chem_ids=[])
    assert result == {}


# ---------------------------------------------------------------------------
# P12 — search_by_q with os_search=<fn>: exactly 1 OS call per page
# ---------------------------------------------------------------------------

def test_P12_search_by_q_os_single_call():
    st = _store(("001008", "벤젠"), ("097377", "메탄올"))
    call_count = {"n": 0}

    def fake_os(plan, *, limit, offset, scope):
        call_count["n"] += 1
        return {
            "hits": [
                {"chem_id": "001008", "match_type": A.MATCH_NORMALIZED_EXACT, "matched_term": "벤젠"},
            ],
            "total": 1,
        }

    result = A.search_by_q(q="벤젠", store=st, limit=20, offset=0, os_search=fake_os)
    assert call_count["n"] == 1, f"expected 1 OS call, got {call_count['n']}"
    assert result["total"] == 1
    assert result["items"][0]["chem_id"] == "001008"
    assert result["items"][0]["match_type"] == A.MATCH_NORMALIZED_EXACT


FREE_SEARCH_OS_CALLS_AFTER = 1  # contract: 1 OS call per free-text page search


def test_P12_os_call_count_contract():
    st = _store(("001008", "벤젠"))
    calls = []

    def counting_os(plan, *, limit, offset, scope):
        calls.append({"limit": limit, "offset": offset})
        return {"hits": [{"chem_id": "001008", "match_type": A.MATCH_NORMALIZED_EXACT, "matched_term": "벤젠"}], "total": 1}

    A.search_by_q(q="염산", store=st, limit=20, offset=0, os_search=counting_os)
    assert len(calls) == FREE_SEARCH_OS_CALLS_AFTER, (
        f"WO-023 contract: exactly {FREE_SEARCH_OS_CALLS_AFTER} OS call(s) per page, got {len(calls)}"
    )


# ---------------------------------------------------------------------------
# P13 — os_search=None falls back to N×M Supabase path (regression)
# ---------------------------------------------------------------------------

def test_P13_fallback_without_os():
    st = _store(("001008", "벤젠"), ("097377", "메탄올"))
    result = A.search_by_q(
        q="벤젠",
        store=st,
        limit=20,
        offset=0,
        os_search=None,  # legacy path
        dictionary_lookup=lambda q, **_: {"items": [], "active_tiers": []},
    )
    assert result["total"] >= 1
    chem_ids = [i["chem_id"] for i in result["items"]]
    assert "001008" in chem_ids


# ---------------------------------------------------------------------------
# P14 — English name hits aliases field (DSL structure check)
# ---------------------------------------------------------------------------

def test_P14_aliases_field_in_dsl():
    plan = _plan("benzene")
    dsl = _build_dsl(plan, from_=0, size=20)
    body_str = str(dsl)
    assert "aliases" in body_str, "aliases field should appear in DSL"
    assert "title" in body_str, "title field should appear in DSL"


# ---------------------------------------------------------------------------
# P15 — PUBLIC visibility filter present
# ---------------------------------------------------------------------------

def test_P15_visibility_filter_present():
    plan = _plan("염산")
    dsl = _build_dsl(plan, from_=0, size=20)
    filters = dsl["query"]["bool"]["filter"]
    visibility = [f for f in filters if "visibility_scopes" in str(f)]
    assert visibility, "visibility_scopes filter must be in DSL"
    assert "PUBLIC" in str(visibility)


# ---------------------------------------------------------------------------
# P16 — object_type filter present
# ---------------------------------------------------------------------------

def test_P16_object_type_filter_present():
    plan = _plan("염산")
    dsl = _build_dsl(plan, from_=0, size=20)
    filters = dsl["query"]["bool"]["filter"]
    ot_filters = [f for f in filters if "object_type" in str(f)]
    assert ot_filters, "object_type filter must be in DSL"
    assert "CHEM" in str(ot_filters)


# ---------------------------------------------------------------------------
# P17 — clause count capped
# ---------------------------------------------------------------------------

def test_P17_clause_count_capped():
    many_tokens = tuple(f"token{i}" for i in range(_MAX_CLAUSES + 10))
    plan = _plan("염산", tokens=many_tokens)
    dsl = _build_dsl(plan, from_=0, size=20)
    clauses = dsl["query"]["bool"]["must"][0]["dis_max"]["queries"]
    assert len(clauses) <= _MAX_CLAUSES, f"clauses {len(clauses)} exceed cap {_MAX_CLAUSES}"


# ---------------------------------------------------------------------------
# P18 — empty plan → match_none DSL
# ---------------------------------------------------------------------------

def test_P18_empty_plan_match_none():
    empty_plan = A.SearchPlan(
        original_query="", normalized_query="", compact_query="",
        identifier_kind=None, identifier_value=None,
        tokens=(), expanded_terms=(), is_empty=True,
    )
    dsl = _build_dsl(empty_plan, from_=0, size=20)
    assert "match_none" in str(dsl), "empty plan must produce match_none DSL"


# ---------------------------------------------------------------------------
# P19 — search_adapter.py does not contain banned search-engine strings
# ---------------------------------------------------------------------------

def test_P19_adapter_no_banned_strings():
    src = Path(A.__file__).read_text(encoding="utf-8").lower()
    for banned in ("elasticsearch", "opensearch", "meilisearch", "typesense", "solr"):
        assert banned not in src, f"search_adapter.py must not reference {banned}"
