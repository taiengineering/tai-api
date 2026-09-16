"""WO-RISK-MAP-001 CIC_W source mapping governance — proposal freeze contract tests."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import map001_cicw_governance as gov

GENERATOR = Path("tools/risk_map/map001_cicw_governance.py")
PROPOSAL_TSV = Path("docs/knowledge/risk/RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv")
COVERAGE_TSV = Path("docs/knowledge/risk/RISK_MAP001_CICW_COVERAGE_v1.tsv")
REPORT_MD = Path(
    "docs/knowledge/risk/OBJ_risk-map001-cicw-source-mapping-governance_v1.md"
)


def test_anchor_constants_frozen():
    from tools.risk04.approve001_owner_approval_binding import FROZEN_OWNER_PACKAGE_SHA
    from tools.risk04.materialize001_resume_effective_plan import FROZEN_RECEIPT_SHA

    assert (
        FROZEN_OWNER_PACKAGE_SHA
        == "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
    )
    assert (
        FROZEN_RECEIPT_SHA
        == "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
    )


def test_expected_census_constants():
    assert gov.EXPECTED_APPROVED_CONCEPTS == 1110
    assert gov.EXPECTED_CANONICAL_RECEIPT_ROWS == 1110
    assert gov.EXPECTED_MAPPING_ROWS == 1139
    assert gov.EXPECTED_UNIQUE_SOURCE_KEYS == 1139
    assert gov.EXPECTED_PROMOTED_TARGETS == 1082
    assert gov.EXPECTED_PROMOTED_MAPPING_ROWS == 1082
    assert gov.EXPECTED_MERGED_TARGETS == 28
    assert gov.EXPECTED_MERGED_MAPPING_ROWS == 57
    assert gov.EXPECTED_HOLD_ROWS == 1
    assert gov.EXPECTED_HOLD_SOURCE_KEY == "673"
    assert gov.EXPECTED_EXCLUSIONS == 582
    assert gov.EXPECTED_CIC_W_TOTAL_ACCOUNTING == 1722


def test_generator_closed_surfaces():
    """Confirm the tool doesn't *use* forbidden APIs. String literals — including
    the report template that documents the policy ('fuzzy / embedding used = 0')
    — are excluded so the report text itself isn't misread as usage."""
    src = GENERATOR.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Blank out every string literal in the AST-visible source so only code
    # tokens remain when we scan for forbidden usage.
    literals: list[tuple[int, int, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.end_lineno is not None and node.end_col_offset is not None:
                literals.append(
                    (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
                )

    stripped = _blank_ranges(src, literals).lower()

    for banned in (
        "openai",
        "anthropic",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "sentence_transformers",
        "faiss",
        "psycopg",
        "supabase_client",
        "create_client",
    ):
        assert banned not in stripped, (
            f"forbidden token {banned!r} present in non-string source"
        )


def _blank_ranges(src: str, ranges: list[tuple[int, int, int, int]]) -> str:
    """Replace each (line, col, end_line, end_col) span in `src` with spaces."""
    lines = src.split("\n")
    for lineno, col, end_lineno, end_col in ranges:
        start_idx = lineno - 1
        end_idx = end_lineno - 1
        if start_idx == end_idx:
            row = lines[start_idx]
            lines[start_idx] = row[:col] + " " * (end_col - col) + row[end_col:]
        else:
            first = lines[start_idx]
            lines[start_idx] = first[:col] + " " * (len(first) - col)
            for mid in range(start_idx + 1, end_idx):
                lines[mid] = " " * len(lines[mid])
            last = lines[end_idx]
            lines[end_idx] = " " * end_col + last[end_col:]
    return "\n".join(lines)


def test_no_llm_or_fuzzy_imports():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden_modules = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "psycopg2",
        "psycopg",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden_modules), f"forbidden import: {seen}"


def test_proposal_deterministic_two_run():
    rows_a = gov.build_proposal()
    rows_b = gov.build_proposal()
    assert rows_a == rows_b
    assert gov.proposal_sha(rows_a) == gov.proposal_sha(rows_b)


def test_proposal_row_shape():
    rows = gov.build_proposal()
    assert len(rows) == 1139
    assert list(rows[0].keys()) == list(gov.PROPOSAL_FIELDS)

    source_ids = {r["source_id"] for r in rows}
    assert source_ids == {"CIC_W"}, source_ids

    assert {r["mapping_type"] for r in rows} == {"EXACT_EQUIVALENT"}
    assert {r["mapping_status"] for r in rows} == {"PROPOSED"}
    assert {r["mapping_method"] for r in rows} == {"MANUAL_REVIEW"}
    assert {r["evidence_basis"] for r in rows} == {"OWNER_APPROVED_CONCEPT_MEMBERSHIP"}
    assert {r["owner_approval_id"] for r in rows} == {"RISK-04-APPROVE-001"}

    unique_source_keys = {r["source_key"] for r in rows}
    assert len(unique_source_keys) == 1139
    assert "673" not in unique_source_keys

    canonical_targets = {r["canonical_id"] for r in rows}
    assert len(canonical_targets) == 1110

    origin_counts: dict[str, int] = {}
    for r in rows:
        origin_counts[r["canonical_origin_type"]] = (
            origin_counts.get(r["canonical_origin_type"], 0) + 1
        )
    assert origin_counts == {
        "PROMOTED_FROM_SOURCE": 1082,
        "MERGED_FROM_REVIEWED_SOURCES": 57,
    }
    promoted_targets = {
        r["canonical_id"] for r in rows if r["canonical_origin_type"] == "PROMOTED_FROM_SOURCE"
    }
    merged_targets = {
        r["canonical_id"] for r in rows if r["canonical_origin_type"] == "MERGED_FROM_REVIEWED_SOURCES"
    }
    assert len(promoted_targets) == 1082
    assert len(merged_targets) == 28


def test_no_reject_or_no_match_or_ambiguous():
    rows = gov.build_proposal()
    disallowed = {"NO_MATCH", "POSSIBLE_RELATED", "AMBIGUOUS"}
    assert not (disallowed & {r["mapping_type"] for r in rows})
    assert not ({"APPROVED", "REJECTED", "HOLD"} & {r["mapping_status"] for r in rows})


def test_hold_source_not_in_proposal():
    rows = gov.build_proposal()
    assert all(r["source_key"] != "673" for r in rows)


def test_exclusion_overlap_zero():
    rows = gov.build_proposal()
    mapping_keys = {r["source_key"] for r in rows}
    excl = {r["source_key"] for r in load_tsv(gov.EXCLUSIONS_PATH)}
    assert not (mapping_keys & excl)


def test_no_b_or_c_rows():
    rows = gov.build_proposal()
    assert not any(r["source_id"] in {"KOSHA_CONSTRUCTION_PROCESS", "KALIS_RISK_PROFILE"} for r in rows)


def test_written_proposal_shape_when_present():
    if not PROPOSAL_TSV.exists():
        return
    rows = load_tsv(PROPOSAL_TSV)
    assert len(rows) == 1139
    assert list(rows[0].keys()) == list(gov.PROPOSAL_FIELDS)
    # Anchor exactness in every row
    for r in rows:
        assert (
            r["canonical_receipt_sha"]
            == "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
        )
        assert (
            r["owner_package_sha"]
            == "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
        )
        assert (
            r["source_ingest_receipt_sha"]
            == "9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4"
        )


def test_written_coverage_shape_when_present():
    if not COVERAGE_TSV.exists():
        return
    rows = load_tsv(COVERAGE_TSV)
    by_bucket = {r["bucket"]: r["count"] for r in rows}
    assert by_bucket["MAPPING_PROPOSED"] == "1139"
    assert by_bucket["UNIQUE_SOURCE_KEYS"] == "1139"
    assert by_bucket["CANONICAL_TARGETS_COVERED"] == "1110"
    assert by_bucket["PROMOTED_TARGETS"] == "1082"
    assert by_bucket["MERGED_TARGETS"] == "28"
    assert by_bucket["UNMAPPED_HOLD_LABEL"] == "1"
    assert by_bucket["SEMANTIC_EXCLUSIONS"] == "582"
    assert by_bucket["ACCOUNTING_SUM"] == "1722"
    assert by_bucket["OVERLAP_EXCLUSIONS_VS_MAPPING"] == "0"
    assert by_bucket["KOSHA_MAPPING"] == "0"
    assert by_bucket["KALIS_MAPPING"] == "0"
    assert by_bucket["PRODUCTION_MAPPING_WRITE"] == "0"


def test_written_report_shape_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    assert "CANONICAL RECEIPT SHA" in text
    assert "SOURCE INGEST RECEIPT SHA" in text
    assert "OWNER PACKAGE SHA" in text
    assert "MAPPING_PROPOSAL_FROZEN" in text
    assert "MERGE = NOT AUTHORIZED" in text
    assert "PRODUCTION MAPPING" in text
    # No B/C surface leaks in the report
    assert "KOSHA mapping                = 0" in text
    assert "KALIS mapping                = 0" in text


def test_production_sql_write_surface_zero():
    src = GENERATOR.read_text(encoding="utf-8")
    # No SQL write to risk_source_mappings anywhere
    assert not re.search(r"INSERT\s+INTO\s+public\.risk_source_mappings", src, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+public\.risk_source_mappings", src, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+public\.risk_source_mappings", src, re.IGNORECASE)
    # And no other risk_* production write anywhere in this generator
    assert not re.search(r"INSERT\s+INTO\s+public\.risk_", src, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+public\.risk_", src, re.IGNORECASE)


def test_proposal_sha_stable():
    rows = gov.build_proposal()
    sha = gov.proposal_sha(rows)
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    # Frozen at first successful build; changes only if the proposal composition changes.
    assert sha == "036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026"
