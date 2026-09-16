"""WO-RISK-02-INGEST-001-R1 local executor contract tests. No DB required."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk02 import ingest001_source_core_local_exec as executor
from tools.risk02.ingest001_source_core import (
    memberships_insert_sql,
    nodes_insert_sql,
    records_insert_sql,
)

EXECUTOR = Path("tools/risk02/ingest001_source_core_local_exec.py")


def _source() -> str:
    return EXECUTOR.read_text(encoding="utf-8")


def test_no_destructive_statements():
    src = _source()
    # Only match actual SQL against public schema tables — free-text mentions of
    # "no DELETE / no TRUNCATE" in the module docstring must not trip this guard.
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE(\s+TABLE)?\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDROP\s+(TABLE|VIEW|INDEX)\s+", src, re.IGNORECASE)


def test_no_mapping_or_canonical_writes():
    src = _source()
    assert "INSERT INTO public.risk_source_mappings" not in src
    assert "INSERT INTO public.risk_canonical_nodes" not in src
    assert "INSERT INTO public.risk_canonical_node_sectors" not in src
    assert "UPDATE public.risk_source_mappings" not in src
    assert "UPDATE public.risk_canonical_nodes" not in src
    assert "UPDATE public.risk_canonical_node_sectors" not in src
    # sanity: mapping tables can be *read* for guard checks
    assert "FROM public.risk_source_mappings" in src
    assert "FROM public.risk_canonical_nodes" in src
    assert "FROM public.risk_canonical_node_sectors" in src


def test_updates_are_limited_to_snapshots_and_records():
    src = _source()
    updates = re.findall(r"UPDATE\s+public\.[a-z_]+", src, flags=re.IGNORECASE)
    assert set(updates) <= {
        "UPDATE public.risk_snapshots",
        "UPDATE public.risk_records",
    }
    # risk_records UPDATE must always be inside repair_execute + WHERE-bound by
    # source_id + content_key. That function must bind source_id to SOURCE_KALIS.
    tree = ast.parse(src)
    repair_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "repair_execute":
            repair_fn = node
            break
    assert repair_fn is not None, "repair_execute must exist"
    repair_src = ast.get_source_segment(src, repair_fn) or ""
    assert "UPDATE public.risk_records" in repair_src
    assert "SOURCE_KALIS" in repair_src
    assert 'WHERE source_id = %(source_id)s' in repair_src
    assert "content_key = %(content_key)s" in repair_src
    # And no other function in the module may contain UPDATE public.risk_records.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "repair_execute":
            seg = ast.get_source_segment(src, node) or ""
            assert "UPDATE public.risk_records" not in seg


def test_no_hardcoded_credentials():
    src = _source()
    # No secrets pasted into source; the only accepted path is os.environ.
    assert "postgres://" not in src
    assert "postgresql://" not in src
    assert "eyJ" not in src  # no JWT-shaped tokens
    # Env access must go through DATABASE_URL only.
    tree = ast.parse(src)
    env_gets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_env_get(node.func):
            if node.args and isinstance(node.args[0], ast.Constant):
                env_gets.append(node.args[0].value)
    assert env_gets == ["DATABASE_URL"]


def _is_env_get(func: ast.AST) -> bool:
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    inner = func.value
    if not isinstance(inner, ast.Attribute) or inner.attr != "environ":
        return False
    return isinstance(inner.value, ast.Name) and inner.value.id == "os"


def test_on_conflict_resume_contract():
    nodes_sql = nodes_insert_sql(
        [
            {
                "source_id": "CIC_W",
                "source_key": "01",
                "parent_source_key": None,
                "native_code": "01",
                "node_type": "W_ROOT",
                "depth": 1,
                "name_raw": "x",
                "name_normalized": "x",
                "path_raw": "x",
                "path_normalized": "x",
                "content_hash": "h",
            }
        ]
    )
    rec_sql = records_insert_sql(
        [
            {
                "content_key": "k",
                "task_source_key": "t",
                "raw_payload": {"작업프로세스명": "터파기"},
            }
        ]
    )
    mem_sql = memberships_insert_sql(
        "00000000-0000-0000-0000-000000000001",
        "KALIS_RISK_PROFILE",
        [
            {
                "member_kind": "RECORD",
                "source_id": "KALIS_RISK_PROFILE",
                "member_key": "k",
                "occurrence_count": 1,
            }
        ],
    )
    assert "ON CONFLICT (source_id, source_key) DO NOTHING" in nodes_sql
    assert "ON CONFLICT (source_id, content_key) DO NOTHING" in rec_sql
    assert (
        "ON CONFLICT (snapshot_id, member_kind, source_id, member_key) DO NOTHING"
        in mem_sql
    )


def test_batch_and_expected_constants_frozen():
    assert executor.RECORD_BATCH == 100
    assert executor.MEMBERSHIP_BATCH == 500
    assert executor.EXPECTED_NODES == 3325
    assert executor.EXPECTED_RECORDS == 30696
    assert executor.EXPECTED_MEMBERSHIPS == 34021
    assert executor.KALIS_RECORD_OCCURRENCE_SUM == 47559
    assert executor.KOSHA_LEAF_IDENTITIES == 620
    assert executor.KOSHA_LEAF_OCCURRENCE_SUM == 626
    # 787 KOSHA nodes = 620 leaves + 167 non-leaves. Total occurrence sum
    # across all NODE memberships = leaves(626) + non-leaves(167 × 1) = 793.
    assert executor.KOSHA_NODE_OCCURRENCE_SUM_TOTAL == 793


def test_require_database_url_blocks_when_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        executor._require_database_url()
    except SystemExit as exc:
        assert "DATABASE_URL" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected SystemExit when DATABASE_URL missing")


def test_expected_source_kinds_and_orders():
    src = _source()
    # STAGED→VALIDATED→ACCEPTED must appear in this order in the code.
    idx_staged = src.index("STAGED")
    idx_validated = src.index("VALIDATED")
    idx_accepted = src.index("ACCEPTED")
    assert idx_staged < idx_validated < idx_accepted


def test_no_psycopg_leak_into_generator_module():
    # Guard: the generator module (source_core) must still stay closed to psycopg,
    # per test_risk02_ingest001_source_core.test_generator_closed_surfaces.
    # Executor is separate — that assertion is intentionally not applied here.
    generator = Path("tools/risk02/ingest001_source_core.py").read_text(encoding="utf-8")
    assert "psycopg" not in generator.lower()
