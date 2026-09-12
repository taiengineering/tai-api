"""Static checks for 20260911_kosha_safety_material_snapshots.sql."""
from __future__ import annotations

import os
import pathlib
import re

HERE = os.path.dirname(__file__)
SQL = os.path.abspath(os.path.join(
    HERE, "..", "docs", "sql", "20260911_kosha_safety_material_snapshots.sql"
))


def _sql() -> str:
    with open(SQL, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def test_migration_lives_only_in_docs_sql():
    root = pathlib.Path(HERE).resolve().parent
    matches = list(root.rglob("20260911_kosha_safety_material_snapshots.sql"))
    rels = [str(p.relative_to(root)) for p in matches if "node_modules" not in str(p)]
    assert rels == ["docs/sql/20260911_kosha_safety_material_snapshots.sql"]


def test_additive_if_not_exists_and_no_down_pair():
    n = _norm(_sql())
    assert "create table if not exists kosha_safety_material_snapshots" in n
    assert "create table if not exists kosha_safety_material_snapshot_items" in n
    assert "create index if not exists" in n
    down = os.path.join(os.path.dirname(SQL), "20260911_kosha_safety_material_snapshots_down.sql")
    assert not os.path.exists(down)


def test_no_catalog_alter():
    n = _norm(_sql())
    assert "alter table kosha_safety_materials" not in n
    assert "kosha_safety_materials.source" not in n


def test_rls_enabled_without_public_policies():
    n = _norm(_sql())
    assert "alter table kosha_safety_material_snapshots enable row level security" in n
    assert "alter table kosha_safety_material_snapshot_items enable row level security" in n
    assert "create policy" not in n
    assert "grant insert" not in n
    assert "grant update" not in n
    assert "grant delete" not in n


def test_snapshot_item_uniques_and_fks():
    n = _norm(_sql())
    assert "unique (snapshot_id, material_id)" in n
    assert "unique (snapshot_id, source_med_seq)" in n
    assert "references kosha_safety_material_snapshots(id)" in n
    assert "references kosha_safety_materials(id)" in n
    assert "check (status in ('running', 'completed', 'failed'))" in n
