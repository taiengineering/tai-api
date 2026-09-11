"""Static contract for kosha_safety_material_storage_holds SQL."""
from __future__ import annotations

import os
import pathlib
import re

HERE = os.path.dirname(__file__)
SQL = os.path.abspath(os.path.join(
    HERE, "..", "docs", "sql", "20260911_kosha_safety_material_storage_holds.sql"
))
MIGRATION = os.path.abspath(os.path.join(
    HERE, "..", "supabase", "migrations", "20260911130000_kosha_safety_material_storage_holds.sql"
))


def _sql(path=SQL) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


OVERSIZE_SQL = os.path.abspath(os.path.join(
    HERE, "..", "docs", "sql", "20260912_kosha_safety_material_storage_holds_oversize.sql"
))
OVERSIZE_MIGRATION = os.path.abspath(os.path.join(
    HERE, "..", "supabase", "migrations",
    "20260912010000_kosha_safety_material_storage_holds_oversize.sql",
))


def test_docs_sql_and_migration_are_identical():
    assert _sql(SQL) == _sql(MIGRATION)


def test_additive_hold_table_only():
    n = _norm(_sql())
    assert "create table if not exists public.kosha_safety_material_storage_holds" in n
    assert "alter table kosha_safety_materials" not in n
    assert "alter table kosha_safety_material_asset_versions" not in n
    assert "drop table" not in n
    assert "unique (snapshot_id, asset_id, reason)" in n
    assert "source_asset_filename_mismatch" in n
    assert "source_asset_zero_match" in n
    assert "source_asset_multi_match" in n
    assert "check (status in ('open', 'resolved'))" in n
    assert "enable row level security" in n
    assert "create policy" not in n
    assert "grant delete" not in n
    assert "to service_role" in n
    down = os.path.join(os.path.dirname(SQL), "20260911_kosha_safety_material_storage_holds_down.sql")
    assert not os.path.exists(down)


def test_oversize_reason_additive_check_only():
    n = _norm(_sql(OVERSIZE_SQL))
    assert _sql(OVERSIZE_SQL) == _sql(OVERSIZE_MIGRATION)
    assert "drop constraint if exists kosha_safety_material_storage_holds_reason_check" in n
    assert "source_asset_oversize_policy" in n
    assert "create table" not in n
    assert "drop table" not in n
    assert "update " not in n
    assert "delete " not in n
    assert "alter table kosha_safety_materials" not in n
