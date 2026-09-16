"""WO-RISK-KOSHA-MAP-001A KOSHA review universe contract tests. No DB required."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_map001_review_universe as ku

GENERATOR = Path("tools/risk_map/kosha_map001_review_universe.py")
UNIVERSE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_MAP001_REVIEW_UNIVERSE_v1.tsv")
PACK_TSV = Path("docs/knowledge/risk/RISK_KOSHA_MAP001_GPT_REVIEW_PACK_v1.tsv")
COVERAGE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_MAP001_COVERAGE_v1.tsv")
REPORT_MD = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-map001-review-universe_v1.md"
)

FROZEN_UNIVERSE_SHA = (
    "30a2762eec244518fd73eb53fb0c3e53f56e6a41669569d94ee570175cd0e04a"
)
FROZEN_PACK_SHA = (
    "20bcdf3a7827a2446dae933a1d055463176478cccf86f7ad8c607c23fe29f9b5"
)
FROZEN_CANONICAL_RECEIPT_SHA = (
    "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
)


def test_expected_census_constants():
    assert ku.EXPECTED_KOSHA_TOTAL == 787
    assert ku.EXPECTED_PROJECT_KIND == 6
    assert ku.EXPECTED_WORK_TYPE == 161
    assert ku.EXPECTED_DETAIL_PROCESS == 620
    assert ku.EXPECTED_RAW_LEAF_OCCURRENCE_SUM == 626
    assert ku.EXPECTED_PATH_IDENTITIES == 620
    assert ku.EXPECTED_DUPLICATE_GROUPS == 3
    assert ku.EXPECTED_DUPLICATE_EXTRAS == 6
    assert ku.EXPECTED_EXACT_NAME_HITS == 12
    assert ku.EXPECTED_NO_EXACT_NAME == 608
    assert ku.EXPECTED_MULTI_TARGET_AMBIGUITY == 0
    assert ku.BATCH_SIZE == 100


def test_review_universe_shape_deterministic():
    rows_a, _ = ku.build_review_universe()
    rows_b, _ = ku.build_review_universe()
    assert rows_a == rows_b
    assert ku.universe_sha_for_rows(rows_a) == ku.universe_sha_for_rows(rows_b)


def test_review_universe_census_and_scope():
    rows, _ = ku.build_review_universe()
    assert len(rows) == 620
    assert {r["source_id"] for r in rows} == {"KOSHA_CONSTRUCTION_PROCESS"}
    assert {r["source_identity_status"] for r in rows} == {"HOLD"}
    assert {r["canonical_kind_required"] for r in rows} == {"TASK"}
    assert {r["review_status"] for r in rows} == {"REVIEW_REQUIRED"}

    # 620 unique source keys.
    source_keys = [r["source_key"] for r in rows]
    assert len(set(source_keys)) == 620

    # Occurrence-sum must reproduce raw leaf occurrence (626).
    occ_sum = sum(int(r["source_occurrence_count"]) for r in rows)
    assert occ_sum == 626

    # 3 duplicate-occurrence groups, 6 duplicate raw extras.
    dup_rows = [r for r in rows if r["duplicate_occurrence_flag"] == "YES"]
    assert len(dup_rows) == 3
    assert sum(int(r["source_occurrence_count"]) - 1 for r in dup_rows) == 6

    # No B/C leakage.
    assert not any(r["source_id"] == "CIC_W" for r in rows)
    assert not any(r["source_id"] == "KALIS_RISK_PROFILE" for r in rows)


def test_exact_name_inventory():
    rows, _ = ku.build_review_universe()
    exact_rows = [r for r in rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE"]
    semantic_rows = [r for r in rows if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"]

    assert len(exact_rows) == 12
    assert len(semantic_rows) == 608
    assert len(exact_rows) + len(semantic_rows) == 620

    # Exact-name candidates come first in sort order.
    for r in rows[:12]:
        assert r["candidate_class"] == "EXACT_NAME_CANDIDATE"
    for r in rows[12:]:
        assert r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"

    # 발파 (6) + 콘크리트양생 (6) = 12.
    fam = Counter(r["exact_name_canonical_name"] for r in exact_rows)
    assert fam.get("발파") == 6
    assert fam.get("콘크리트양생") == 6

    # No exact-name candidate carries EXACT_EQUIVALENT / APPROVED — just POSSIBLE_RELATED.
    for r in exact_rows:
        assert r["exact_name_hit_count"] == "1"
        assert r["recommended_mapping_type"] == "POSSIBLE_RELATED"
        assert r["mapping_method_hint"] == "EXACT_NAME"
        assert r["exact_name_canonical_id"]
        assert r["exact_name_canonical_name"]

    for r in semantic_rows:
        assert r["exact_name_hit_count"] == "0"
        assert r["exact_name_canonical_id"] == ""
        assert r["recommended_mapping_type"] == ""
        assert r["mapping_method_hint"] == ""


def test_no_multi_target_ambiguity():
    rows, _ = ku.build_review_universe()
    hits = Counter(
        int(r["exact_name_hit_count"]) for r in rows
    )
    # Only 0 or 1 hits — never >=2 (no ambiguity today).
    assert set(hits) <= {0, 1}


def test_no_premature_decisions():
    rows, _ = ku.build_review_universe()
    # Semantic decision fields must all be blank in this WO.
    for r in rows:
        assert r["semantic_decision"] == ""
        assert r["semantic_target_canonical_id"] == ""
        assert r["semantic_mapping_type"] == ""
        assert r["semantic_reason"] == ""
        assert r["recommended_mapping_type"] != "EXACT_EQUIVALENT"
        assert r["recommended_mapping_type"] != "APPROVED"


def test_no_premature_no_match():
    rows, _ = ku.build_review_universe()
    # Missing exact-name must NOT be recorded as NO_MATCH here.
    for r in rows:
        assert r["semantic_mapping_type"] != "NO_MATCH"
        assert r["recommended_mapping_type"] != "NO_MATCH"


def test_frozen_shas_stable():
    rows, _ = ku.build_review_universe()
    assert ku.universe_sha_for_rows(rows) == FROZEN_UNIVERSE_SHA
    packed = ku._batchify(rows)
    assert ku.pack_sha_for_rows(packed) == FROZEN_PACK_SHA


def test_written_review_universe_when_present():
    if not UNIVERSE_TSV.exists():
        return
    rows = load_tsv(UNIVERSE_TSV)
    assert len(rows) == 620
    assert list(rows[0].keys()) == list(ku.REVIEW_UNIVERSE_FIELDS)
    assert {r["source_id"] for r in rows} == {"KOSHA_CONSTRUCTION_PROCESS"}
    exact_rows = [r for r in rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE"]
    semantic_rows = [r for r in rows if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"]
    assert len(exact_rows) == 12
    assert len(semantic_rows) == 608


def test_written_gpt_pack_when_present():
    if not PACK_TSV.exists():
        return
    rows = load_tsv(PACK_TSV)
    assert len(rows) == 620
    assert list(rows[0].keys()) == list(ku.GPT_REVIEW_PACK_FIELDS)
    # 7 batches: 6 × 100 + 1 × 20 (last batch 20).
    from collections import Counter as C
    counts = C(r["batch_no"] for r in rows)
    assert counts["B01"] == 100
    assert counts["B02"] == 100
    assert counts["B03"] == 100
    assert counts["B04"] == 100
    assert counts["B05"] == 100
    assert counts["B06"] == 100
    assert counts["B07"] == 20
    assert set(counts) == {"B01", "B02", "B03", "B04", "B05", "B06", "B07"}


def test_written_coverage_when_present():
    if not COVERAGE_TSV.exists():
        return
    rows = load_tsv(COVERAGE_TSV)
    by_bucket = {r["bucket"]: r["count"] for r in rows}
    assert by_bucket["KOSHA_TOTAL_NODES"] == "787"
    assert by_bucket["PROJECT_KIND_CONTEXT_ONLY"] == "6"
    assert by_bucket["WORK_TYPE_CONTEXT_ONLY"] == "161"
    assert by_bucket["DETAIL_PROCESS_REVIEW_UNIVERSE"] == "620"
    assert by_bucket["RAW_LEAF_OCCURRENCES"] == "626"
    assert by_bucket["PATH_IDENTITIES"] == "620"
    assert by_bucket["IDENTITY_STATUS"] == "HOLD"
    assert by_bucket["EXACT_NAME_SOURCE_HITS"] == "12"
    assert by_bucket["NO_EXACT_NAME_ROWS"] == "608"
    assert by_bucket["MULTI_TARGET_EXACT_NAME_AMBIGUITY"] == "0"
    assert by_bucket["SEMANTIC_DECISIONS"] == "0"
    assert by_bucket["APPROVED_DECISIONS"] == "0"
    assert by_bucket["NO_MATCH_DECISIONS"] == "0"
    assert by_bucket["PRODUCTION_KOSHA_MAPPINGS"] == "0"


def test_written_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    assert "THIS IS NOT MAPPING APPROVAL" in text
    assert "THIS IS NOT PRODUCTION MATERIALIZATION" in text
    assert "THIS DOES NOT LIFT KOSHA IDENTITY HOLD" in text
    assert "THIS DOES NOT CREATE CANONICAL NODES" in text
    assert "THIS DOES NOT DECIDE NO_MATCH FOR ANY ROW" in text
    assert FROZEN_CANONICAL_RECEIPT_SHA in text
    assert FROZEN_UNIVERSE_SHA in text
    assert FROZEN_PACK_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


def test_no_llm_fuzzy_embedding_imports():
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
        "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden_modules), f"forbidden import: {seen}"


def test_no_production_sql_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"INSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"TRUNCATE", src, re.IGNORECASE)
    assert "psycopg" not in src.lower()
    assert "supabase_client" not in src.lower()
    assert "create_client" not in src.lower()


def test_generator_uses_frozen_canonical_receipt_only():
    """Anchor must be repository evidence, not a live DB query."""
    src = GENERATOR.read_text(encoding="utf-8")
    assert "RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv" in src or "CANONICAL_RECEIPT_PATH" in src
    assert "FROZEN_CANONICAL_RECEIPT_SHA" in src


def test_generator_never_writes_no_match():
    src = GENERATOR.read_text(encoding="utf-8")
    # 'NO_MATCH' must not appear as an assigned value in the generator source.
    # (It is fine for docstring / comment mentions, but not as a decision.)
    assert '"NO_MATCH"' not in src
    assert "'NO_MATCH'" not in src


def test_generator_never_writes_exact_equivalent_or_approved():
    src = GENERATOR.read_text(encoding="utf-8")
    assert '"EXACT_EQUIVALENT"' not in src
    assert "'EXACT_EQUIVALENT'" not in src
    assert '"APPROVED"' not in src
    assert "'APPROVED'" not in src
