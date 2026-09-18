"""WO-CHEM-09 CHEM search adapter tests.

Fixture-only. Uses MemoryMsdsReadStore for the DB and a stubbed
dictionary_lookup for the terminology-dictionary path. §25 items
1..18 individually covered.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import kosha_public_msds as router_mod
from router_registry.public import ROUTERS as PUBLIC_ROUTERS
from services import safe_help_kiwi
from services.kosha_msds import read, search_adapter as A


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _cur(chem_id: str, *, id: str, content_id: str,
         ko: str | None = None, en: str | None = None,
         cas: str | None = None, ke: str | None = None,
         eno: str | None = None, un: str | None = None) -> dict:
    return {
        "id": id, "content_id": content_id,
        "source_id": "KOSHA_MSDS", "source_key": chem_id, "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": ko, "chemical_name_en": en,
        "cas_no": cas, "ke_no": ke, "en_no": eno, "un_no": un,
        "source_content_hash": "sha-" + chem_id,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": "snap-1",
    }


def _store() -> read.MemoryMsdsReadStore:
    rows = [
        _cur("001008", id="uu-1008", content_id="CHEM:1008",
             ko="벤젠", en="Benzene", cas="71-43-2"),
        _cur("097377", id="uu-9737", content_id="CHEM:9737",
             ko="메탄올", en="Methanol", cas="67-56-1"),
        _cur("012345", id="uu-1234", content_id="CHEM:1234",
             ko="수산화나트륨", en="Sodium hydroxide", cas="1310-73-2"),
    ]
    return read.MemoryMsdsReadStore(current_rows=rows)


def _stub_dict(mapping: dict[str, list[dict]]):
    """Return a callable that mimics services.search_query_svc.lookup."""
    def _fn(q, limit=5, subject_type=None):
        return {"items": mapping.get(q, [])[:limit], "active_tiers": []}
    return _fn


# ---------------------------------------------------------------------------
# §25 items 1..18
# ---------------------------------------------------------------------------


def test_01_chem_id_exact():
    out = A.search_by_q(q="001008", store=_store())
    assert out["total"] == 1
    assert out["items"][0]["chem_id"] == "001008"
    assert out["items"][0]["match_type"] == A.MATCH_IDENTIFIER_EXACT
    assert out["match_metadata"]["identifier_kind"] == A.IDENTIFIER_CHEM_ID


def test_02_cas_exact():
    out = A.search_by_q(q="71-43-2", store=_store())
    assert out["total"] == 1
    assert out["items"][0]["chem_id"] == "001008"
    assert out["match_metadata"]["identifier_kind"] == A.IDENTIFIER_CAS


def test_03_korean_canonical_exact():
    out = A.search_by_q(q="벤젠", store=_store(),
                        dictionary_lookup=_stub_dict({}))
    assert out["total"] >= 1
    hits = [i for i in out["items"] if i["chem_id"] == "001008"]
    assert hits
    assert hits[0]["match_type"] == A.MATCH_NORMALIZED_EXACT


def test_04_english_canonical_exact():
    out = A.search_by_q(q="Methanol", store=_store(),
                        dictionary_lookup=_stub_dict({}))
    assert out["total"] >= 1
    hits = [i for i in out["items"] if i["chem_id"] == "097377"]
    assert hits


def test_05_korean_partial():
    out = A.search_by_q(q="메탄", store=_store(),
                        dictionary_lookup=_stub_dict({}))
    # Partial name match via CHEM-06 read.search's ilike behavior on the
    # memory store: "메탄" is contained in "메탄올".
    hits = [i for i in out["items"] if i["chem_id"] == "097377"]
    assert hits


def test_06_whitespace_normalized_korean():
    """A user-typed variant with internal whitespace normalizes to the
    same tokens as the canonical name."""
    # normalize_basic collapses runs of whitespace but does NOT delete
    # them, so " 벤 젠 " → "벤 젠". Kiwi should still emit "벤젠" or a
    # sensible near-substring, but we assert normalization output is
    # deterministic regardless of surrounding whitespace.
    plan_a = A.build_search_plan("벤젠",
                                 dictionary_lookup=_stub_dict({}))
    plan_b = A.build_search_plan("  벤젠  ",
                                 dictionary_lookup=_stub_dict({}))
    plan_c = A.build_search_plan("벤 젠",
                                 dictionary_lookup=_stub_dict({}))
    assert plan_a.normalized_query == plan_b.normalized_query
    assert plan_a.compact_query == plan_c.compact_query  # both = "벤젠"


def test_07_kiwi_morphology_query():
    """Kiwi tokens are present on a natural-language Korean phrase."""
    plan = A.build_search_plan("벤젠 취급",
                               dictionary_lookup=_stub_dict({}))
    # Kiwi is installed in this repo (kiwipiepy 0.23.x). If somehow the
    # fallback fires, safe_help_kiwi still returns tokens for the same
    # input, just via regex — so the assertion holds either way.
    assert plan.tokens  # non-empty
    # And "벤젠" or a compatible surface should appear.
    assert any("벤젠" in t or "취급" in t or t in ("벤젠", "취급") for t in plan.tokens)


def test_08_dictionary_synonym_query():
    """Synthetic dictionary: '메틸알코올' → subject_key '메탄올'.

    The adapter must include '메탄올' in expanded_terms, and the CHEM
    search that follows must hit chemId=097377 via the DICTIONARY_EXPANSION
    match_type.
    """
    lookup = _stub_dict({
        "메틸알코올": [{"subject_key": "메탄올", "matched_term": "메틸알코올",
                        "match_type": "SYNONYM_OF"}],
    })
    out = A.search_by_q(q="메틸알코올", store=_store(), dictionary_lookup=lookup)
    assert "메탄올" in out["match_metadata"]["expanded_terms"]
    hits = [i for i in out["items"] if i["chem_id"] == "097377"]
    assert hits
    assert hits[0]["match_type"] == A.MATCH_DICTIONARY
    assert hits[0]["matched_term"] == "메탄올"


def test_09_abbreviation_if_dictionary_contains_one():
    """Synthetic dictionary: '가성소다' → '수산화나트륨' (SPELLING_VARIANT).

    Once expanded, the CHEM search finds the sodium-hydroxide chemical.
    """
    lookup = _stub_dict({
        "가성소다": [{"subject_key": "수산화나트륨", "matched_term": "가성소다",
                      "match_type": "SPELLING_VARIANT_OF"}],
    })
    out = A.search_by_q(q="가성소다", store=_store(), dictionary_lookup=lookup)
    assert "수산화나트륨" in out["match_metadata"]["expanded_terms"]
    hits = [i for i in out["items"] if i["chem_id"] == "012345"]
    assert hits


def test_10_identifier_is_not_morphologically_tokenized():
    """§8: identifiers bypass Kiwi. CAS/chemId/KE/EN/UN queries yield
    empty `tokens` and empty `expanded_terms` in the plan."""
    for q in ("001008", "71-43-2", "KE-12345", "EN-98765", "UN-1170"):
        plan = A.build_search_plan(q)
        assert plan.identifier_kind is not None, f"expected identifier for {q!r}"
        assert plan.tokens == (), f"Kiwi tokens leaked for identifier {q!r}"
        assert plan.expanded_terms == (), f"dictionary expansion leaked for {q!r}"


def test_11_canonical_identity_unchanged():
    """Adapter must not mutate rows returned by the read service."""
    store = _store()
    original_rows = {
        r["chem_id"]: {k: v for k, v in r.items()}
        for r in store._current  # accessing internal fixture state
    }
    _ = A.search_by_q(q="벤젠", store=store, dictionary_lookup=_stub_dict({}))
    after = {r["chem_id"]: {k: v for k, v in r.items()} for r in store._current}
    assert original_rows == after


def test_12_synonym_expansion_does_not_mutate_db():
    """Even under a dictionary lookup returning synonyms, no store method
    that could write is invoked."""
    store = _store()
    _ = A.search_by_q(
        q="메틸알코올",
        store=store,
        dictionary_lookup=_stub_dict({
            "메틸알코올": [{"subject_key": "메탄올", "matched_term": "메틸알코올"}]
        }),
    )
    # The read store exposes no mutation methods at all (verified in CHEM-06
    # test_15). Reassert the invariant here by checking the class shape.
    forbidden = ("insert", "update", "delete", "upsert", "rpc", "execute_sql")
    for f in forbidden:
        assert f not in {n for n in dir(store) if not n.startswith("_")}


def test_13_no_llm_search_dependency():
    """The adapter and read service must not import an LLM/vector library."""
    forbidden_modules = ("openai", "anthropic", "cohere", "langchain", "llama_index",
                         "sentence_transformers", "chromadb", "pinecone")
    src = Path(A.__file__).read_text(encoding="utf-8")
    for f in forbidden_modules:
        assert f not in src, f"adapter references LLM module {f}"


def test_14_no_new_search_engine_dependency():
    """The adapter must not import Elasticsearch / OpenSearch / Meilisearch / Solr."""
    forbidden = ("elasticsearch", "opensearch", "meilisearch", "typesense", "solr",
                 "algoliasearch")
    src = Path(A.__file__).read_text(encoding="utf-8")
    for f in forbidden:
        assert f not in src, f"adapter references search-engine dep {f}"


def test_15_deterministic_ordering():
    """Same query + same store + same dictionary → same order."""
    d = _stub_dict({"메탄올": []})
    a = A.search_by_q(q="메탄올", store=_store(), dictionary_lookup=d)
    b = A.search_by_q(q="메탄올", store=_store(), dictionary_lookup=d)
    assert [i["chem_id"] for i in a["items"]] == [i["chem_id"] for i in b["items"]]


def test_16_empty_query_handling():
    plan = A.build_search_plan("")
    assert plan.is_empty is True
    assert plan.identifier_kind is None
    assert plan.tokens == ()
    out = A.search_by_q(q="   ", store=_store(),
                        dictionary_lookup=_stub_dict({}))
    # Empty q → list_current envelope with match_metadata attached.
    assert set(out.keys()) == {"items", "total", "limit", "offset", "match_metadata"}
    assert out["match_metadata"]["identifier_kind"] is None


def test_17_no_result_handling():
    out = A.search_by_q(q="존재하지않는화학물질", store=_store(),
                        dictionary_lookup=_stub_dict({}))
    # No chemical row matched → items is empty; envelope shape intact.
    assert out["items"] == []
    assert out["total"] == 0
    # But match_metadata still records what the adapter tried.
    assert "tokens" in out["match_metadata"]


def test_18_router_registered_under_seo_preview_execute_wo():
    """CHEM-09 originally asserted that routers.kosha_public_msds stayed
    out of the registry. WO-CHEM-SEO-PREVIEW-EXECUTE-001 explicitly
    authorized registering it (env default KOSHA_MSDS_PUBLIC_MODE=off
    keeps it 503-dormant until the operational flag flip). This test is
    now the positive complement: the router IS in the public registry."""
    modules = [entry.get("module") for entry in PUBLIC_ROUTERS]
    assert "routers.kosha_public_msds" in modules


# ---------------------------------------------------------------------------
# Extra: router integration + cross-domain isolation
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    # WO-CHEM-SEO-PREVIEW-LIVE-001: router now requires a public mode.
    # These pre-existing tests target FULL semantics.
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "full")
    store = _store()
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(router_mod.router)
    with TestClient(app) as c:
        yield c


def test_19_router_q_param_delegates_to_adapter(client):
    r = client.get("/public/kosha/msds?q=001008")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "001008"
    assert body["items"][0]["match_type"] == A.MATCH_IDENTIFIER_EXACT
    assert "match_metadata" in body


def test_20_router_q_wins_over_structured_filters(client):
    """If both `q` and structured filters are given, `q` wins."""
    r = client.get("/public/kosha/msds?q=001008&chem_id=097377")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["chem_id"] == "001008"


def test_21_router_no_q_preserves_existing_behavior(client):
    """No q, no filter → CHEM-06 list_current envelope. No match_metadata."""
    r = client.get("/public/kosha/msds")
    body = r.json()
    assert "match_metadata" not in body
    assert body["total"] == 3
    assert [i["chem_id"] for i in body["items"]] == ["001008", "012345", "097377"]


def test_22_no_kosha_safety_materials_dependency():
    for module_file in (A.__file__, router_mod.__file__):
        src = Path(module_file).read_text(encoding="utf-8")
        assert "kosha_safety_materials" not in src


def test_23_normalize_reused_not_forked():
    """The adapter must import `tools.search_dict.normalize`, not
    re-implement it."""
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "from tools.search_dict import normalize" in src
    # And must not define its own normalize_basic/compact.
    assert "def normalize_basic" not in src
    assert "def compact(" not in src


def test_24_kiwi_reused_not_forked():
    """The adapter must import `services.safe_help_kiwi`, not re-implement
    the tokenizer or reach for kiwipiepy directly.
    """
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "from services import safe_help_kiwi" in src
    # No direct kiwipiepy import statements. (Docstring mentions are OK.)
    for banned in ("from kiwipiepy", "import kiwipiepy"):
        assert banned not in src, f"adapter must not directly import kiwipiepy ({banned!r})"
    assert "def tokens(" not in src


def test_25_dictionary_lookup_failure_is_silent():
    """If services.search_query_svc.lookup raises, adapter still runs
    with Kiwi tokens only (fail-open)."""
    def raising_lookup(q, limit=5, subject_type=None):
        raise RuntimeError("dictionary unavailable")
    out = A.search_by_q(q="벤젠", store=_store(),
                        dictionary_lookup=raising_lookup)
    assert out["match_metadata"]["expanded_terms"] == []
