"""WO-RISK-KOSHA-GAP-CONSOLIDATE-001 lean gap-consolidation tests.

Lean scope per WO §11: 66 review-pack rows, GPT consolidation fields
blank, project_kind_count in [1..6], P1/P2/P3/P4 sums to 66, prior
aggregate SHA regression, exception resolution row count = 4 with all
VALID_CONTEXT_SPLIT. skip = 0.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_620_aggregate as agg
from tools.risk_map import kosha_gap_consolidate as gc

GENERATOR = Path("tools/risk_map/kosha_gap_consolidate.py")

FROZEN_REVIEW_PACK_SHA = (
    "c4f34cf286e1eab28e5ed6c6daab94be13b2f038f5173fef547cbe945421fad8"
)
FROZEN_FAMILY_CENSUS_SHA = (
    "fb5a4a08c941985883b17041d1948dce92e98a50d3f779519524711a02263a67"
)
FROZEN_EXCEPTION_RESOLUTION_SHA = (
    "d949bb94083eaa1d36074332379065c3bd28b2a45e9b914709220380194d4e60"
)

FROZEN_AGGREGATE_SHA = (
    "7e99b73204876cfef6c85a198430d14adfd8582b17cc2c7162a0729063aea67d"
)


def test_review_pack_shape():
    rows = gc.build_review_pack()
    assert len(rows) == 66
    assert sum(int(r["occurrence_rows"]) for r in rows) == 196
    assert list(rows[0].keys()) == list(gc.REVIEW_PACK_FIELDS)


def test_review_pack_gpt_fields_blank():
    rows = gc.build_review_pack()
    for r in rows:
        assert r["gpt_consolidation_decision"] == "", r["gap_group_id"]
        assert r["gpt_candidate_name"] == "", r["gap_group_id"]
        assert r["gpt_candidate_parent"] == "", r["gap_group_id"]
        assert r["gpt_reason"] == "", r["gap_group_id"]


def test_project_kind_count_range():
    rows = gc.build_review_pack()
    for r in rows:
        pk = int(r["project_kind_count"])
        assert 1 <= pk <= 6, r["gap_group_id"]


def test_priority_accounting():
    rows = gc.build_review_pack()
    priorities = Counter(r["coverage_priority"] for r in rows)
    assert sum(priorities.values()) == 66
    assert set(priorities) <= {"P1", "P2", "P3", "P4"}
    # WO §7 breakdown:
    #   P1 == 6, P2 in 3..5, P3 == 2, P4 == 1  project kinds
    for r in rows:
        pk = int(r["project_kind_count"])
        pri = r["coverage_priority"]
        if pk == 6:
            assert pri == "P1"
        elif 3 <= pk <= 5:
            assert pri == "P2"
        elif pk == 2:
            assert pri == "P3"
        else:
            assert pri == "P4"


def test_review_pack_deterministic_sha():
    a = gc.build_review_pack()
    b = gc.build_review_pack()
    assert a == b
    assert gc.review_pack_sha(a) == gc.review_pack_sha(b) == FROZEN_REVIEW_PACK_SHA


def test_family_census_totals_match():
    pack = gc.build_review_pack()
    census = gc.build_family_census(pack)
    assert sum(int(r["group_count"]) for r in census) == 66
    assert sum(int(r["represented_source_rows"]) for r in census) == 196


def test_family_hint_stable():
    """Family hint is a rule-based classifier — verify a small stable subset
    to guard against silent rule reordering.
    """
    pack = gc.build_review_pack()
    by_id = {r["gap_group_id"]: r for r in pack}
    # P1 anchors — must retain the following families:
    expected = {
        "GAP-0001": "MOBILIZATION_DELIVERY_FAMILY",   # 굴착 장비반입
        "GAP-0005": "MOBILIZATION_DELIVERY_FAMILY",   # 철근반입
        "GAP-0006": "MOBILIZATION_DELIVERY_FAMILY",   # 콘크리트 반입
        "GAP-0002": "REMOVAL_HAULOUT_FAMILY",          # 굴착 토사반출
        "GAP-0004": "UTILITY_PROTECTION_FAMILY",       # 접지
    }
    for gid, fam in expected.items():
        assert by_id[gid]["family_hint"] == fam, gid


def test_exception_resolution_all_valid_context_split():
    rows = gc.build_exception_resolution()
    assert len(rows) == 4
    assert list(rows[0].keys()) == list(gc.EXCEPTION_RESOLUTION_FIELDS)
    assert {r["group_id"] for r in rows} == {"CE-0066", "CE-0067", "CE-0068", "CE-0069"}
    for r in rows:
        assert r["resolution"] == "VALID_CONTEXT_SPLIT"
        assert r["general_context_target_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
        assert r["general_context_target_name"] == "발파"
        assert r["tunnel_context_target_id"] == "473d69ee-4433-487f-bc43-c35c1f2ea28f"
        assert r["tunnel_context_target_name"] == "발파굴착"
    assert gc.exception_resolution_sha(rows) == FROZEN_EXCEPTION_RESOLUTION_SHA


def test_prior_aggregate_sha_regression():
    rows = load_tsv(agg.AGGREGATE_PATH)
    assert agg.aggregate_sha(rows) == FROZEN_AGGREGATE_SHA


def test_written_review_pack_when_present():
    if not gc.REVIEW_PACK_PATH.exists():
        return
    rows = load_tsv(gc.REVIEW_PACK_PATH)
    assert len(rows) == 66
    assert list(rows[0].keys()) == list(gc.REVIEW_PACK_FIELDS)
    assert gc.review_pack_sha(rows) == FROZEN_REVIEW_PACK_SHA


def test_written_family_census_when_present():
    if not gc.FAMILY_CENSUS_PATH.exists():
        return
    rows = load_tsv(gc.FAMILY_CENSUS_PATH)
    assert list(rows[0].keys()) == list(gc.FAMILY_CENSUS_FIELDS)
    assert gc.family_census_sha(rows) == FROZEN_FAMILY_CENSUS_SHA


def test_written_exception_resolution_when_present():
    if not gc.EXCEPTION_RESOLUTION_PATH.exists():
        return
    rows = load_tsv(gc.EXCEPTION_RESOLUTION_PATH)
    assert len(rows) == 4
    assert gc.exception_resolution_sha(rows) == FROZEN_EXCEPTION_RESOLUTION_SHA


def test_report_when_present():
    if not gc.REPORT_PATH.exists():
        return
    text = gc.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "THIS IS NOT CANONICAL CREATION",
        "THIS IS NOT OWNER APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "FAMILY HINTS ARE REVIEW AIDS, NOT CANONICAL NAMES",
        "UNRESOLVED SEMANTIC CONFLICT = 0",
        "CANONICAL CREATE = 0",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text
    assert FROZEN_REVIEW_PACK_SHA in text


def test_no_llm_or_fuzzy_or_dbclient():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "psycopg2",
        "psycopg",
        "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden), f"forbidden import: {seen}"


def test_no_production_sql_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
