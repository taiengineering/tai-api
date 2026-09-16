"""WO-RISK-MAP-APPROVE-001 Owner mapping approval binding — evidence tests."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import map001_cicw_governance as gov
from tools.risk_map import map_approve001_owner_binding as approve

GENERATOR = Path("tools/risk_map/map_approve001_owner_binding.py")
BINDING_TSV = Path("docs/knowledge/risk/RISK_MAP001_OWNER_APPROVAL_BINDING_v1.tsv")
RECEIPT_MD = Path(
    "docs/knowledge/risk/OBJ_risk-map-approve001-owner-approval-execution-receipt_v1.md"
)

FROZEN_PROPOSAL_SHA = (
    "036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026"
)
FROZEN_CANONICAL_RECEIPT_SHA = (
    "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
)
FROZEN_SOURCE_INGEST_RECEIPT_SHA = (
    "9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4"
)
FROZEN_CANONICAL_OWNER_PACKAGE_SHA = (
    "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
)
FROZEN_BINDING_IDENTITY_SHA = (
    "402b4004b987169e1cc5b9b0356061794218ef45ee473839b80b72a91cf1f9ed"
)


def test_anchor_constants_agree_with_governance_tool():
    assert approve.FROZEN_PROPOSAL_SHA == FROZEN_PROPOSAL_SHA
    assert approve.FROZEN_SOURCE_INGEST_RECEIPT_SHA == FROZEN_SOURCE_INGEST_RECEIPT_SHA
    assert approve.APPROVAL_ID == "RISK-MAP-APPROVE-001"


def test_proposal_sha_matches_disk():
    rows_on_disk = load_tsv(gov.PROPOSAL_PATH)
    assert len(rows_on_disk) == 1139
    assert gov.proposal_sha(rows_on_disk) == FROZEN_PROPOSAL_SHA

    rebuilt = gov.build_proposal()
    assert rebuilt == rows_on_disk, "disk proposal must equal rebuilt proposal exactly"
    assert gov.proposal_sha(rebuilt) == FROZEN_PROPOSAL_SHA


def test_binding_row_shape():
    rows = approve.build_binding()
    assert len(rows) == 1
    row = rows[0]
    assert list(row.keys()) == list(approve.BINDING_FIELDS)
    assert row["approval_id"] == "RISK-MAP-APPROVE-001"
    assert row["approval_state"] == "OWNER_APPROVED"
    assert row["approval_target"] == "CIC_W_SOURCE_TO_CANONICAL_MAPPING_PACKAGE"
    assert row["scope_source_id"] == "CIC_W"
    assert row["mapping_type"] == "EXACT_EQUIVALENT"
    assert row["mapping_method"] == "MANUAL_REVIEW"
    assert row["proposal_rows"] == "1139"
    assert row["proposal_sha256"] == FROZEN_PROPOSAL_SHA
    assert row["canonical_receipt_sha"] == FROZEN_CANONICAL_RECEIPT_SHA
    assert row["source_ingest_receipt_sha"] == FROZEN_SOURCE_INGEST_RECEIPT_SHA
    assert row["canonical_owner_package_sha"] == FROZEN_CANONICAL_OWNER_PACKAGE_SHA
    assert row["binding_target"] == "PACKAGE_SHA_NOT_HEAD"
    assert row["production_write_authorized"] == "NO"
    assert row["materialization_authorized"] == "NO"
    assert row["merge_authorized"] == "NO"


def test_binding_identity_sha_frozen():
    rows = approve.build_binding()
    sha = approve.binding_identity_sha(rows)
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    assert sha == FROZEN_BINDING_IDENTITY_SHA


def test_binding_identity_excludes_timestamp_and_head():
    """WO §18: rerunning against the same package with a different timestamp
    and HEAD must yield the same binding identity SHA."""
    base = approve.build_binding()
    mutated = [dict(base[0])]
    mutated[0]["owner_approval_event_utc"] = "2099-01-01T00:00:00Z"
    mutated[0]["repository_head_at_execution"] = "deadbeef" * 5
    assert approve.binding_identity_sha(mutated) == approve.binding_identity_sha(base)


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
        "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden_modules), f"forbidden import: {seen}"


def test_no_production_sql_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"INSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"UPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"TRUNCATE\s+", src, re.IGNORECASE)
    assert "psycopg" not in src.lower()
    assert "supabase_client" not in src.lower()
    assert "create_client" not in src.lower()


def test_written_binding_shape_when_present():
    if not BINDING_TSV.exists():
        return
    rows = load_tsv(BINDING_TSV)
    assert len(rows) == 1
    row = rows[0]
    assert row["approval_id"] == "RISK-MAP-APPROVE-001"
    assert row["approval_state"] == "OWNER_APPROVED"
    assert row["proposal_sha256"] == FROZEN_PROPOSAL_SHA
    assert row["canonical_receipt_sha"] == FROZEN_CANONICAL_RECEIPT_SHA
    assert row["source_ingest_receipt_sha"] == FROZEN_SOURCE_INGEST_RECEIPT_SHA
    assert row["canonical_owner_package_sha"] == FROZEN_CANONICAL_OWNER_PACKAGE_SHA
    assert row["scope_source_id"] == "CIC_W"
    assert row["mapping_type"] == "EXACT_EQUIVALENT"
    assert row["mapping_method"] == "MANUAL_REVIEW"
    assert row["production_write_authorized"] == "NO"
    assert row["materialization_authorized"] == "NO"
    assert row["merge_authorized"] == "NO"


def test_receipt_shape_when_present():
    if not RECEIPT_MD.exists():
        return
    text = RECEIPT_MD.read_text(encoding="utf-8")
    assert "OWNER MAPPING APPROVAL != PRODUCTION MAPPING MATERIALIZATION" in text
    assert "OWNER MAPPING APPROVAL != CANONICAL ACTIVE TRANSITION" in text
    assert FROZEN_PROPOSAL_SHA in text
    assert FROZEN_BINDING_IDENTITY_SHA in text
    assert "MATERIALIZATION              = NOT OPENED" in text
    assert "MERGE                        = NOT AUTHORIZED" in text


def test_proposal_and_coverage_immutability():
    """WO §23/§24: proposal + coverage TSV must not be mutated by this WO."""
    proposal_rows = load_tsv(gov.PROPOSAL_PATH)
    assert len(proposal_rows) == 1139
    assert gov.proposal_sha(proposal_rows) == FROZEN_PROPOSAL_SHA
    coverage = load_tsv(gov.COVERAGE_PATH)
    by_bucket = {r["bucket"]: r["count"] for r in coverage}
    assert by_bucket["MAPPING_PROPOSED"] == "1139"
    assert by_bucket["ACCOUNTING_SUM"] == "1722"
    assert by_bucket["PRODUCTION_MAPPING_WRITE"] == "0"


def test_scope_hard_guard():
    rows = approve.build_binding()
    assert rows[0]["scope_source_id"] == "CIC_W"
    # binding row must NOT authorize KOSHA / KALIS / mass writes:
    assert rows[0]["production_write_authorized"] == "NO"
    assert rows[0]["materialization_authorized"] == "NO"
    # And in the proposal itself no B/C leakage:
    proposal_rows = load_tsv(gov.PROPOSAL_PATH)
    assert not any(
        r["source_id"] in {"KOSHA_CONSTRUCTION_PROCESS", "KALIS_RISK_PROFILE"}
        for r in proposal_rows
    )


def test_hold_source_still_unmapped():
    proposal_rows = load_tsv(gov.PROPOSAL_PATH)
    assert all(r["source_key"] != "673" for r in proposal_rows)
