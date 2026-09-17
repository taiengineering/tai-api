"""WO-RISK-KOSHA-B07-EVIDENCE-001 B07 mechanical evidence + full 620 partition.

Also carries the B06 key-terminology regression note: the B06 WO §5-§9
labeled its per-row keys as "source_key" while the values are actually
`review_key` entries in the frozen evidence. The B06 freeze artifact still
preserves the correct source_key per row, so no semantic row is rebound
— but this test module makes that fact machine-checkable.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_semantic_evidence as b01
from tools.risk_map import kosha_b02_semantic_evidence as b02
from tools.risk_map import kosha_b03_semantic_evidence as b03
from tools.risk_map import kosha_b04_semantic_evidence as b04
from tools.risk_map import kosha_b05_semantic_evidence as b05
from tools.risk_map import kosha_b06_semantic_evidence as b06
from tools.risk_map import kosha_b07_semantic_evidence as b07
from tools.risk_map.kosha_map001_review_universe import GPT_REVIEW_PACK_PATH

GENERATOR = Path("tools/risk_map/kosha_b07_semantic_evidence.py")
EVIDENCE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B07_SEMANTIC_EVIDENCE_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b07-semantic-evidence_v1.md")

FROZEN_B07_EVIDENCE_SHA = (
    "b1c9ed4280fc971257561a2696df5748c9411c50a0c9330805375d7114af0060"
)
FROZEN_B06_EVIDENCE_SHA = (
    "b0df9c2e77642184bc98fa67bc94e5073a41913ccc9a867da1ec5bf3bbfc34c2"
)
FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_B01_GPT_REVIEW_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_B02_GPT_REVIEW_SHA = (
    "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787"
)
FROZEN_B03_GPT_REVIEW_SHA = (
    "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885"
)
FROZEN_B04_GPT_REVIEW_SHA = (
    "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b"
)
FROZEN_B05_GPT_REVIEW_SHA = (
    "feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2"
)
FROZEN_B06_GPT_REVIEW_SHA = (
    "2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581"
)

EXPECTED_B07_NAMES = (
    "작업환경 (분진)",
    "작업환경 (조명)",
    "작업환경 (환기)",
    "철근가공 및 운반",
    "철근반입",
    "철근조립",
    "콘크리트 반입",
    "콘크리트타설",
    "터널 발파",
    "터널 버럭처리",
    "터널 장약",
    "터널 천공",
    "터널 방수쉬트설치",
    "터널배수",
    "터널 강지보",
    "터널 락볼트",
    "터널 숏크리트",
    "터널 특수보강",
    "특수터널 (Shield 공법)",
    "특수터널 (TBM공법)",
)


def test_expected_constants():
    assert b07.BATCH_ID == "B07"
    assert b07.EXPECTED_B07_ROWS == 20
    assert b07.EXPECTED_B07_EXACT_NAME == 0
    assert b07.EXPECTED_B07_SEMANTIC_SEARCH == 20
    assert b07.B07_EVIDENCE_FIELDS == b01.B01_EVIDENCE_FIELDS


def test_b07_uses_shared_batch_helper():
    src = GENERATOR.read_text(encoding="utf-8")
    assert "from tools.risk_map.kosha_b01_semantic_evidence import" in src
    assert "build_batch_evidence" in src
    assert "_score_candidate" not in src
    assert "_canonical_index" not in src


def test_b07_deterministic_and_shape():
    rows_a, ref_a = b07.build_b07_evidence()
    rows_b, ref_b = b07.build_b07_evidence()
    assert rows_a == rows_b
    assert ref_a == ref_b
    assert b07.b07_evidence_sha(rows_a) == b07.b07_evidence_sha(rows_b) == FROZEN_B07_EVIDENCE_SHA
    assert len(rows_a) == 20
    assert len({r["review_key"] for r in rows_a}) == 20
    assert len({r["source_key"] for r in rows_a}) == 20
    assert len({(r["review_key"], r["source_key"]) for r in rows_a}) == 20


def test_b07_composition_is_all_semantic_search():
    rows, _ = b07.build_b07_evidence()
    assert all(r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED" for r in rows)
    assert all(r["exact_name_hit_count"] == "0" for r in rows)
    assert all(r["exact_name_canonical_id"] == "" for r in rows)


def test_b07_gpt_decision_fields_blank():
    rows, _ = b07.build_b07_evidence()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_reason"] == ""
        assert r["gpt_confidence_class"] == ""


def test_b07_candidates_are_tasks_capped_and_no_process():
    rows, ref = b07.build_b07_evidence()
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        n = int(r["mechanical_candidate_count"])
        assert 0 <= n <= b07.CANDIDATE_CAP
        prev_score = float("inf")
        for i in range(1, b07.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            score = int(score_s)
            assert score > 0
            assert score <= prev_score
            prev_score = score
            can_id = r.get(f"candidate_{i}_canonical_id", "")
            assert can_id in valid, f"unknown canonical {can_id}"
            origin = r.get(f"candidate_{i}_origin_type", "")
            assert origin != "PROCESS", "PROCESS-typed candidate must not appear"


def test_b07_no_premature_decisions():
    rows, _ = b07.build_b07_evidence()
    forbidden = {"EXACT_EQUIVALENT", "APPROVED", "NO_MATCH", "CANONICAL_GAP", "AMBIGUOUS"}
    for r in rows:
        assert r["gpt_semantic_decision"] not in forbidden
        assert r["gpt_mapping_type"] not in forbidden


def test_b07_expected_source_names():
    """WO §6: exactly the 20 named rows, no additions/omissions."""
    rows, _ = b07.build_b07_evidence()
    names = tuple(sorted(r["source_name"] for r in rows))
    assert names == tuple(sorted(EXPECTED_B07_NAMES))


# ---------------------------------------------------------------------------
# WO §7 Dual-key exact-pair guard
# ---------------------------------------------------------------------------


def test_b07_dual_key_pair_exact_set_equality_with_frozen_pack():
    pack = load_tsv(GPT_REVIEW_PACK_PATH)
    b07_pack = [r for r in pack if r["batch_no"] == "B07"]
    assert len(b07_pack) == 20
    pack_pairs = {(r["review_key"], r["source_key"]) for r in b07_pack}
    assert len(pack_pairs) == 20

    rows, _ = b07.build_b07_evidence()
    ev_pairs = {(r["review_key"], r["source_key"]) for r in rows}
    assert ev_pairs == pack_pairs, (
        f"missing={pack_pairs - ev_pairs} unexpected={ev_pairs - pack_pairs}"
    )


def test_b07_source_side_columns_preserved_from_pack():
    pack = [r for r in load_tsv(GPT_REVIEW_PACK_PATH) if r["batch_no"] == "B07"]
    by_key = {r["review_key"]: r for r in pack}
    assert len(by_key) == 20
    rows, _ = b07.build_b07_evidence()
    preserved = (
        "review_key",
        "source_key",
        "project_kind",
        "work_type",
        "detail_process",
        "source_name",
        "source_name_normalized",
        "source_path",
        "source_path_normalized",
        "source_occurrence_count",
        "duplicate_occurrence_flag",
        "candidate_class",
        "exact_name_hit_count",
        "exact_name_canonical_id",
    )
    for r in rows:
        original = by_key[r["review_key"]]
        for f in preserved:
            assert r[f] == original[f], f


# ---------------------------------------------------------------------------
# WO §8 Full 620 partition guard — B01..B07 must be a perfect partition.
# ---------------------------------------------------------------------------


def _batch_rows(mod, builder):
    rows, _ = builder()
    return rows


def test_full_620_partition_review_source_pair():
    b01_rows, _ = b01.build_b01_evidence()
    b02_rows, _ = b02.build_b02_evidence()
    b03_rows, _ = b03.build_b03_evidence()
    b04_rows, _ = b04.build_b04_evidence()
    b05_rows, _ = b05.build_b05_evidence()
    b06_rows, _ = b06.build_b06_evidence()
    b07_rows, _ = b07.build_b07_evidence()

    all_rows = {
        "B01": b01_rows,
        "B02": b02_rows,
        "B03": b03_rows,
        "B04": b04_rows,
        "B05": b05_rows,
        "B06": b06_rows,
        "B07": b07_rows,
    }
    for tag, rows in all_rows.items():
        expected = 20 if tag == "B07" else 100
        assert len(rows) == expected, tag

    # Cross-batch overlap = 0 on review_key AND source_key AND pair
    batches = list(all_rows)
    for i in range(len(batches)):
        for j in range(i + 1, len(batches)):
            a, b = batches[i], batches[j]
            ar = {r["review_key"] for r in all_rows[a]}
            br = {r["review_key"] for r in all_rows[b]}
            asr = {r["source_key"] for r in all_rows[a]}
            bsr = {r["source_key"] for r in all_rows[b]}
            ap = {(r["review_key"], r["source_key"]) for r in all_rows[a]}
            bp = {(r["review_key"], r["source_key"]) for r in all_rows[b]}
            assert not (ar & br), f"review_key overlap {a}∩{b}"
            assert not (asr & bsr), f"source_key overlap {a}∩{b}"
            assert not (ap & bp), f"pair overlap {a}∩{b}"

    review_union = set().union(*({r["review_key"] for r in v} for v in all_rows.values()))
    source_union = set().union(*({r["source_key"] for r in v} for v in all_rows.values()))
    pair_union = set().union(
        *({(r["review_key"], r["source_key"]) for r in v} for v in all_rows.values())
    )
    assert len(review_union) == 620
    assert len(source_union) == 620
    assert len(pair_union) == 620


# ---------------------------------------------------------------------------
# WO §23 B06 terminology regression guard
# ---------------------------------------------------------------------------


def test_b06_key_terminology_regression_no_source_rebinding():
    """B06 GPT decision manifest is keyed by review_key (not source_key).
    The freeze output must still carry the corresponding source_key per row,
    and both should point at the same B06 evidence row.
    """
    from tools.risk_map import kosha_b06_gpt_review_freeze as b6freeze

    b06_ev = {r["review_key"]: r for r in load_tsv(b06.B06_EVIDENCE_PATH)}
    assert len(b06_ev) == 100

    manifest_keys = set(b6freeze.GPT_DECISIONS)
    assert manifest_keys == set(b06_ev), "manifest keys must exactly match review_key universe"

    decisions_path = Path("docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv")
    if decisions_path.exists():
        for r in load_tsv(decisions_path):
            ev = b06_ev[r["review_key"]]
            assert r["source_key"] == ev["source_key"], r["review_key"]
            assert r["source_name"] == ev["source_name"], r["review_key"]


# ---------------------------------------------------------------------------
# B01-B06 SHA regression — must survive B07 addition unchanged.
# ---------------------------------------------------------------------------


def test_b01_semantic_evidence_sha_regression():
    rows, _ = b01.build_b01_evidence()
    assert b01.b01_evidence_sha(rows) == FROZEN_B01_EVIDENCE_SHA


def test_b02_semantic_evidence_sha_regression():
    rows, _ = b02.build_b02_evidence()
    assert b02.b02_evidence_sha(rows) == FROZEN_B02_EVIDENCE_SHA


def test_b03_semantic_evidence_sha_regression():
    rows, _ = b03.build_b03_evidence()
    assert b03.b03_evidence_sha(rows) == FROZEN_B03_EVIDENCE_SHA


def test_b04_semantic_evidence_sha_regression():
    rows, _ = b04.build_b04_evidence()
    assert b04.b04_evidence_sha(rows) == FROZEN_B04_EVIDENCE_SHA


def test_b05_semantic_evidence_sha_regression():
    rows, _ = b05.build_b05_evidence()
    assert b05.b05_evidence_sha(rows) == FROZEN_B05_EVIDENCE_SHA


def test_b06_semantic_evidence_sha_regression():
    rows, _ = b06.build_b06_evidence()
    assert b06.b06_evidence_sha(rows) == FROZEN_B06_EVIDENCE_SHA


def test_b01_b06_gpt_review_files_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B04_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B05_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B06_GPT_REVIEW_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *DECISION_FIELDS) == sha, path


# ---------------------------------------------------------------------------
# Written artifact assertions
# ---------------------------------------------------------------------------


def test_written_b07_evidence_when_present():
    if not EVIDENCE_TSV.exists():
        return
    rows = load_tsv(EVIDENCE_TSV)
    assert len(rows) == 20
    assert list(rows[0].keys()) == list(b07.B07_EVIDENCE_FIELDS)
    assert b07.b07_evidence_sha(rows) == FROZEN_B07_EVIDENCE_SHA


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS MECHANICAL EVIDENCE ONLY",
        "THIS IS NOT GPT SEMANTIC REVIEW",
        "THIS IS NOT OWNER MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "ZERO MECHANICAL CANDIDATES != NO_MATCH",
    ):
        assert tag in text
    # B06 terminology regression note
    for tag in (
        "review_key = review-row / GPT decision manifest identity",
        "source_key = KOSHA source-node identity",
        "B06 DATA CORRUPTION = NO",
    ):
        assert tag in text
    assert FROZEN_B07_EVIDENCE_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


# ---------------------------------------------------------------------------
# Static-analysis guard
# ---------------------------------------------------------------------------


def test_no_llm_or_fuzzy_or_dbclient_imports():
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


def test_no_semantic_inference_call_sites():
    """Guard: none of the forbidden semantic-inference libraries appear as an
    identifier or attribute in the generator. Docstring mentions of "no
    embedding / no synonym" are intentional prose and are stripped before
    scanning.
    """
    src = GENERATOR.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            # top-level docstrings — clear them so their prose doesn't trigger the guard
            node.value.value = ""
    stripped = ast.unparse(tree).lower()
    for banned in (
        "levenshtein",
        "similarity",
        "embedding",
        "cosine",
        "kiwi",
        "synonym",
        "rapidfuzz",
        "fuzzywuzzy",
    ):
        assert banned not in stripped, f"forbidden token {banned!r} in generator code"
