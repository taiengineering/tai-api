"""WO-RISK-MAP-MATERIALIZE-001 static + evidence contract tests."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import map001_cicw_governance as gov
from tools.risk_map import map_approve001_owner_binding as approve
from tools.risk_map import map_materialize001 as mat

GENERATOR = Path("tools/risk_map/map_materialize001.py")
RECEIPT_TSV = Path("docs/knowledge/risk/RISK_MAP001_MATERIALIZATION_RECEIPT_v1.tsv")
REPORT_MD = Path(
    "docs/knowledge/risk/OBJ_risk-map-materialize001-production-mapping_v1.md"
)


def test_anchor_constants_agree():
    assert (
        mat.FROZEN_PROPOSAL_SHA
        == "036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026"
    )
    assert (
        mat.FROZEN_APPROVAL_BINDING_SHA
        == "402b4004b987169e1cc5b9b0356061794218ef45ee473839b80b72a91cf1f9ed"
    )
    assert (
        mat.FROZEN_CANONICAL_RECEIPT_SHA
        == "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
    )
    assert (
        mat.FROZEN_SOURCE_INGEST_RECEIPT_SHA
        == "9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4"
    )
    assert (
        mat.FROZEN_OWNER_PACKAGE_SHA
        == "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
    )
    assert mat.MATERIALIZATION_ID == "RISK-MAP-MATERIALIZE-001"


def test_repository_anchor_verification_passes():
    """_verify_repository_anchors succeeds against the current repo without DB."""
    anchors = mat._verify_repository_anchors()
    assert len(anchors["proposal_rows"]) == 1139
    assert anchors["proposal_sha"] == mat.FROZEN_PROPOSAL_SHA
    assert anchors["approval_binding_sha"] == mat.FROZEN_APPROVAL_BINDING_SHA
    assert anchors["binding_row"]["scope_source_id"] == "CIC_W"


def test_target_row_status_is_only_approved_in_generator():
    src = GENERATOR.read_text(encoding="utf-8")
    # The tool must set mapping_status to APPROVED (target row), no other status.
    assert 'cp["mapping_status_target"] = "APPROVED"' in src
    # No PROPOSED / HOLD / REJECTED writes anywhere in the generator (as SQL/status).
    assert '"mapping_status", "PROPOSED"' not in src
    assert '"mapping_status", "HOLD"' not in src
    assert '"mapping_status", "REJECTED"' not in src


def test_no_delete_or_truncate_or_upsert_hide():
    src = GENERATOR.read_text(encoding="utf-8")
    # No DELETE / TRUNCATE / DROP anywhere in the SQL surface.
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
    assert not re.search(r"\bDROP\s+(TABLE|VIEW|INDEX)\b", src, re.IGNORECASE)
    # No ON CONFLICT ... DO NOTHING / DO UPDATE hiding the initial write's errors.
    assert "ON CONFLICT" not in src


def test_writes_are_restricted_to_risk_source_mappings():
    src = GENERATOR.read_text(encoding="utf-8")
    inserts = re.findall(r"INSERT\s+INTO\s+public\.[a-z_]+", src, re.IGNORECASE)
    assert set(inserts) == {"INSERT INTO public.risk_source_mappings"}
    updates = re.findall(r"UPDATE\s+public\.[a-z_]+", src, re.IGNORECASE)
    assert updates == []


def test_no_canonical_or_sector_or_source_core_mutation():
    src = GENERATOR.read_text(encoding="utf-8")
    for target in (
        "public.risk_canonical_nodes",
        "public.risk_canonical_node_sectors",
        "public.risk_source_nodes",
        "public.risk_records",
        "public.risk_snapshot_memberships",
        "public.risk_snapshots",
    ):
        assert not re.search(
            rf"INSERT\s+INTO\s+{re.escape(target)}", src, re.IGNORECASE
        )
        assert not re.search(
            rf"UPDATE\s+{re.escape(target)}", src, re.IGNORECASE
        )
        assert not re.search(
            rf"DELETE\s+FROM\s+{re.escape(target)}", src, re.IGNORECASE
        )


def test_parameterized_insert_only():
    """execute_values with a %s-parameter template — no manual value interpolation."""
    src = GENERATOR.read_text(encoding="utf-8")
    assert "execute_values" in src
    assert "%s::uuid" in src
    assert "%s::jsonb" in src
    # No f-string SQL that would interpolate row values into the INSERT statement.
    assert not re.search(r"INSERT\s+INTO\s+public\.risk_source_mappings.*\{", src, re.IGNORECASE)


def test_single_transaction_intent():
    """The executor uses _connect_txn (not autocommit) for the execute path,
    and only calls conn.commit() once at the end."""
    src = GENERATOR.read_text(encoding="utf-8")
    tree = ast.parse(src)
    exec_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute_materialization":
            exec_fn = node
    assert exec_fn is not None
    body = ast.get_source_segment(src, exec_fn) or ""
    assert "_connect_txn()" in body
    assert body.count("conn.commit()") == 1
    assert "conn.rollback()" in body
    assert "LOCK TABLE public.risk_source_mappings" in body


def test_no_llm_or_supabase_client():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
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


def test_target_status_type_method_frozen():
    src = GENERATOR.read_text(encoding="utf-8")
    # Target enum values appear exactly and no other values are written.
    assert 'mapping_type": "EXACT_EQUIVALENT"' in src or '"EXACT_EQUIVALENT"' in src
    assert '"APPROVED"' in src
    assert '"MANUAL_REVIEW"' in src


def test_planned_rows_and_scope():
    anchors = mat._verify_repository_anchors()
    proposal_rows = anchors["proposal_rows"]
    assert len(proposal_rows) == 1139
    assert {r["source_id"] for r in proposal_rows} == {"CIC_W"}
    assert not any(r["source_key"] == "673" for r in proposal_rows)
    assert not any(
        r["source_id"] in {"KOSHA_CONSTRUCTION_PROCESS", "KALIS_RISK_PROFILE"}
        for r in proposal_rows
    )


def test_receipt_when_present():
    if not RECEIPT_TSV.exists():
        return
    rows = load_tsv(RECEIPT_TSV)
    assert len(rows) == 1139
    assert list(rows[0].keys()) == list(mat.RECEIPT_FIELDS)
    assert {r["mapping_status"] for r in rows} == {"APPROVED"}
    assert {r["mapping_type"] for r in rows} == {"EXACT_EQUIVALENT"}
    assert {r["mapping_method"] for r in rows} == {"MANUAL_REVIEW"}
    assert {r["source_id"] for r in rows} == {"CIC_W"}
    assert {r["proposal_sha"] for r in rows} == {mat.FROZEN_PROPOSAL_SHA}
    assert {r["approval_binding_sha"] for r in rows} == {mat.FROZEN_APPROVAL_BINDING_SHA}
    assert {r["production_verified"] for r in rows} == {"YES"}
    assert not any(r["source_key"] == "673" for r in rows)


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    assert mat.FROZEN_PROPOSAL_SHA in text
    assert mat.FROZEN_APPROVAL_BINDING_SHA in text
    assert "PRODUCTION_MATERIALIZED" in text
    assert "MERGE = NOT AUTHORIZED" in text
    assert "1110 DRAFT" in text
    assert "ACTIVE                        = 0" in text
