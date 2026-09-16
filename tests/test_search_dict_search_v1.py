"""Regression: search tiers T1-T3 + APPROVED-only production gate (WO §52)."""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SD = os.path.join(ROOT, "tools", "search_dict")
sys.path.insert(0, SD)


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    import search_core
    out = tmp_path_factory.mktemp("proj")
    subprocess.run([sys.executable, os.path.join(SD, "build_dictionary.py"),
                    "build", str(out)], check=True, cwd=ROOT, capture_output=True)
    proj = os.path.join(str(out), "TAI_SEARCH_RUNTIME_PROJECTION_v1.json")
    with open(proj, encoding="utf-8") as f:
        return search_core.SearchEngine(json.load(f))


def _top(engine, q):
    items = engine.search(q)["items"]
    return items[0] if items else None


def test_exact_abbreviation_resolves(engine):
    top = _top(engine, "산안법")
    assert top is not None
    assert "산업안전보건법" in top["subject_key"]


def test_spacing_insensitive(engine):
    top = _top(engine, "고압가스안전관리법")
    assert top is not None


def test_reviewed_term_excluded_from_production(engine):
    # LEV is REVIEWED (not APPROVED) -> must NOT surface (APPROVED-only gate)
    assert _top(engine, "LEV") is None


def test_junk_returns_no_match(engine):
    assert _top(engine, "zzznotaterm") is None


def test_every_result_is_explainable(engine):
    for it in engine.search("MSDS")["items"]:
        assert it["match_type"]
        assert it["matched_term"]


@pytest.mark.skipif(
    os.environ.get("SEARCH_DICT_SEED") != "seed_v2",
    reason="PUNCTUATION-variant law names (ㆍ) only in leg-prod seed_v2 corpus",
)
def test_punctuation_insensitive_law_name(engine):
    # '소음ㆍ진동관리법' is APPROVED in seed_v2; query without ㆍ must resolve
    # via the PUNCTUATION tier (match_type=PUNCTUATION).
    top = _top(engine, "소음진동관리법")
    assert top is not None
    assert top["subject_key"] == "소음ㆍ진동관리법"
    assert top["match_type"] == "PUNCTUATION"
