"""Decision-gate sample/flatten: fixture only, no live API."""
from __future__ import annotations

import json
from pathlib import Path

from services.kosha_msds.bootstrap_decision import (
    classify_pair,
    flatten_msds_xml,
    normalize_compare_text,
    sample_manifest_hash,
    select_sample,
)
from services.kosha_msds.contract import CONTENT_SECONDARY_COMPLETE
from services.kosha_msds.current_index import OfficialCurrentRow
from services.kosha_msds.parse import parse_section_xml

FIXTURES = Path("tests/fixtures/kosha_msds")


def test_flatten_benzene_section01_uses_label_and_skips_empty():
    xml = (FIXTURES / "benzene_detail_01.xml").read_text(encoding="utf-8")
    text = flatten_msds_xml(xml)
    assert "제품명: 벤젠" in text
    assert "제품의 권고 용도: 고분자, 세제, 농약" in text
    parsed = parse_section_xml(xml)
    assert parsed.ok


def test_normalize_and_classify():
    assert normalize_compare_text("a\r\n  b") == "a\nb"
    assert classify_pair("x", "x") == "EXACT"
    assert classify_pair("x  y", "x y") == "NORMALIZED_EQUAL"
    assert classify_pair("a", "b") == "CONTENT_DIFFERENT"
    assert classify_pair(None, "a") == "SECONDARY_MISSING"
    assert classify_pair("", "a") == "SECONDARY_EMPTY"


def test_sample_deterministic_and_exact_chemid():
    official = [
        OfficialCurrentRow("000001", "염산 구아니딘", "50-01-1", "2010-01-01", 1),
        OfficialCurrentRow("001008", "벤젠", "71-43-2", "2026-08-01", 1),
        OfficialCurrentRow("047134", "아닐린 공중합체", None, "2015-01-01", 1),
        OfficialCurrentRow("000010", "2,2'-PCB", "1-1-1", "2026-07-01", 1),
        OfficialCurrentRow("000020", "일반", "2-2-2", "2011-01-01", 1),
        OfficialCurrentRow("000021", "일반2", "3-3-3", "2012-01-01", 1),
        OfficialCurrentRow("000022", "일반3", "4-4-4", "2013-01-01", 1),
        OfficialCurrentRow("000023", "일반4", "5-5-5", "2014-01-01", 1),
        OfficialCurrentRow("000024", "일반5", "6-6-6", "2016-01-01", 1),
        OfficialCurrentRow("000025", "일반6", "7-7-7", "2017-01-01", 1),
        OfficialCurrentRow("000026", "일반7", "8-8-8", "2018-01-01", 1),
        OfficialCurrentRow("999999", "missing", "9-9-9", "2020-01-01", 1),
    ]
    coverage = {
        row.chem_id: {"chemId": row.chem_id, "content_status": CONTENT_SECONDARY_COMPLETE}
        for row in official
        if row.chem_id != "999999"
    }
    coverage["999999"] = {"chemId": "999999", "content_status": "SECONDARY_MISSING"}
    a = select_sample(official, coverage)
    b = select_sample(official, coverage)
    assert a == b
    ids = [row["chemId"] for row in a]
    assert "001008" in ids
    assert "999999" not in ids
    assert sample_manifest_hash(a) == sample_manifest_hash(json.loads(json.dumps(a)))
    assert len(a) <= 20
