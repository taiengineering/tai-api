"""WO-RISK-01 deterministic taxonomy helpers. Fixture only."""
from pathlib import Path

from tools.risk01.analyze_3way import coverage, norm_name, parse_a_works


def test_norm_name_trim_and_separators():
    assert norm_name("  토공사\r\n") == "토공사"
    assert norm_name("기초파일  작업") == "기초파일 작업"
    assert norm_name("미장·견출") == "미장 견출"


def test_parse_a_works_hierarchy():
    text = "라. 공종분류(W) 01.토공사 011.굴착 0111.터파기 마. 자원분류"
    nodes = parse_a_works(text)
    assert [n["code"] for n in nodes] == ["01", "011", "0111"]
    assert nodes[2]["parent"] == "011"
    assert nodes[2]["path"] == "토공사 > 굴착 > 터파기"


def test_coverage_exact_and_ambiguous():
    tgt = {"토공사": ["a1"]}
    stats = coverage(["토공사", "없는공종"], tgt)
    assert stats["exact_matched"] == 1
    assert stats["unmatched"] == 1
    amb = coverage(["방수"], {"방수": ["b1", "b2"]})
    assert amb["ambiguous"] == 1
    assert amb["one_to_n"] == 1


def test_no_llm_fuzzy_in_analyzer():
    src = Path("tools/risk01/analyze_3way.py").read_text(encoding="utf-8").lower()
    for token in ("openai", "embedding"):
        assert token not in src
    assert "fuzzymatch" not in src
    assert "rapidfuzz" not in src


def test_letter_bucket_native_hm_values():
    from collections import Counter

    from tools.risk01.analyze_3way import letter_bucket

    buckets = letter_bucket(Counter({"H(4)": 2, "M(3)": 1, "": 1, "X": 1}))
    assert buckets["H"] == 2
    assert buckets["M"] == 1
    assert buckets["NULL"] == 1
    assert buckets["OTHER"] == 1
