"""Regression: normalization + term_id determinism (WO §23/§26)."""
from tools.search_dict import normalize as N


def test_normalize_basic_collapses_ws():
    assert N.normalize_basic("  국소  배기 장치 ") == "국소 배기 장치"


def test_compact_strips_all_ws():
    assert N.compact("국소 배기 장치") == "국소배기장치"


def test_latin_lower_casefolds():
    assert N.latin_lower("MSDS") == "msds"


def test_term_id_is_sha256_and_stable():
    a = N.term_id("SRC-LEG-ALIAS", "산안법", "ABBREVIATION", "산안법")
    b = N.term_id("SRC-LEG-ALIAS", "산안법", "ABBREVIATION", "산안법")
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_term_id_differs_on_any_field():
    base = N.term_id("SRC-A", "k", "ABBREVIATION", "t")
    assert base != N.term_id("SRC-B", "k", "ABBREVIATION", "t")
    assert base != N.term_id("SRC-A", "k2", "ABBREVIATION", "t")
    assert base != N.term_id("SRC-A", "k", "SYNONYM", "t")
    assert base != N.term_id("SRC-A", "k", "ABBREVIATION", "t2")
