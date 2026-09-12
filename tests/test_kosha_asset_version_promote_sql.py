"""Static contract for 20260911_kosha_asset_version_promote.sql."""
from __future__ import annotations

import os
import pathlib
import re

HERE = os.path.dirname(__file__)
SQL = os.path.abspath(os.path.join(HERE, "..", "docs", "sql", "20260911_kosha_asset_version_promote.sql"))


def _sql() -> str:
    with open(SQL, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def test_additive_function_only():
    n = _norm(_sql())
    assert "create or replace function public.promote_kosha_safety_material_asset_version" in n
    assert "drop table" not in n
    assert "create table" not in n
    assert "alter table kosha_safety_material_asset_versions" not in n
    assert "pg_advisory_xact_lock" in n
    assert "security definer" in n
    assert "set search_path = public" in n
    assert "revoke all on function" in n
    assert "from public" in n
    assert "from anon" in n
    assert "from authenticated" in n
    assert "to postgres, service_role" in n
    assert "execute" in n
    assert "is_current_version = false" in n
    assert "'no_change'" in n
    assert "'new_version'" in n
    assert "'promoted_existing_version'" in n
    assert "format(" not in n  # no dynamic SQL


def test_single_sql_file_location():
    root = pathlib.Path(HERE).resolve().parent
    matches = [p for p in root.rglob("20260911_kosha_asset_version_promote.sql") if "node_modules" not in str(p)]
    rels = [str(p.relative_to(root)) for p in matches]
    assert rels == ["docs/sql/20260911_kosha_asset_version_promote.sql"]
