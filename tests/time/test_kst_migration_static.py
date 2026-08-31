"""STEP E §23 static oracle — 16 tests over SoT manifests + generated SQL.

Requires materialized:
  docs/time/TAI_TIME_ACTIVE_COLUMN_MANIFEST.json (260 rows)
  docs/time/TAI_TIME_ISOLATED_ASSETS.json (20 cols / 13 tables)
  docs/time/TAI_TIME_VIEW_MANIFEST.json (3 exact viewdefs)
  docs/sql/20260831_tai_time_kst_cutover_{up,down}.sql (generator output)
  docs/time/TAI_TIME_CRON_MANIFEST.json
  docs/sql/20260831_tai_time_cron_kst_cutover.sql
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TIME = ROOT / "docs" / "time"
SQL = ROOT / "docs" / "sql"
sys.path.insert(0, str(ROOT / "scripts"))

VIEW_ORDER = ("v_equipment_unified", "v_payments_list", "v_process_unified")
ACL_ROLES = ("anon", "authenticated", "postgres", "service_role")
CHILD_RE = re.compile(r"work_schedules_p\d{2}")
ALTER_RE = re.compile(
    r"ALTER TABLE public\.([A-Za-z_][A-Za-z0-9_]*) ALTER COLUMN ([A-Za-z_][A-Za-z0-9_]*) TYPE "
)


def _j(name: str):
    return json.loads((TIME / name).read_text(encoding="utf-8"))


def _cols(doc):
    if isinstance(doc, list):
        return doc
    return doc.get("columns") or doc.get("rows") or []


def _active():
    return _cols(_j("TAI_TIME_ACTIVE_COLUMN_MANIFEST.json"))


def _isolated():
    return _cols(_j("TAI_TIME_ISOLATED_ASSETS.json"))


def _views():
    doc = _j("TAI_TIME_VIEW_MANIFEST.json")
    return doc.get("views") or doc


def _up():
    return (SQL / "20260831_tai_time_kst_cutover_up.sql").read_text(encoding="utf-8")


def _down():
    return (SQL / "20260831_tai_time_kst_cutover_down.sql").read_text(encoding="utf-8")


def _cron_sql():
    return (SQL / "20260831_tai_time_cron_kst_cutover.sql").read_text(encoding="utf-8")


def _alters(sql: str):
    return ALTER_RE.findall(sql)


def test_manifest_count():
    assert len(_active()) == 260


def test_manifest_structure_sum():
    rows = _active()
    counts = Counter(r["structure"] for r in rows)
    assert counts["DIRECT_PHYSICAL"] == 236
    assert counts["PARTITION_ROOT"] == 1
    assert counts["PARTITION_CHILD"] == 16
    assert counts["VIEW_DERIVED"] == 7
    assert sum(counts.values()) == 260


def test_isolated_count():
    cols = _isolated()
    tables = {r["object_name"] for r in cols}
    assert len(cols) == 20
    assert len(tables) == 13


def test_no_isolated_alter():
    iso = {(r["object_name"], r["column_name"]) for r in _isolated()}
    for sql in (_up(), _down()):
        for tbl, col in _alters(sql):
            assert (tbl, col) not in iso


def test_up_237():
    assert len(_alters(_up())) == 237
    assert _up().count("TYPE timestamptz USING") == 237
    actions = [r for r in _active() if r["migration_action"] == "ALTER_TYPE_USING_KST"]
    assert len(actions) == 237


def test_down_237():
    assert len(_alters(_down())) == 237
    assert _down().count("TYPE timestamp without time zone USING") == 237


def test_no_child_alter():
    child_names = {f"work_schedules_p{i:02d}" for i in range(16)}
    for sql in (_up(), _down()):
        for tbl, _col in _alters(sql):
            assert not CHILD_RE.fullmatch(tbl)
            assert tbl not in child_names


def test_view_drop_create_3():
    for sql in (_up(), _down()):
        assert "CASCADE" not in sql.split("DROP VIEW")[1].split("\n")[0]
        for name in VIEW_ORDER:
            assert sql.count(f"DROP VIEW public.{name};") == 1
            assert re.search(rf"CREATE VIEW public\.{name}\b", sql) or f"CREATE VIEW public.{name}" in sql


def test_view_exact_definitions():
    views = {v.get("name") or v.get("view_name"): v for v in _views()}
    for name in VIEW_ORDER:
        defn = (views[name].get("definition") or views[name].get("viewdef") or "").strip().rstrip(";")
        assert defn
        for sql in (_up(), _down()):
            assert defn in sql


def test_view_owner():
    views = {v.get("name") or v.get("view_name"): v for v in _views()}
    for name in VIEW_ORDER:
        assert views[name].get("owner") == "postgres"
        for sql in (_up(), _down()):
            assert f"ALTER VIEW public.{name} OWNER TO postgres;" in sql


def test_view_acl():
    views = {v.get("name") or v.get("view_name"): v for v in _views()}
    for name in VIEW_ORDER:
        acl = views[name].get("acl") or {}
        for role in ACL_ROLES:
            val = acl.get(role)
            assert val in ("ALL", "arwdDxtm", "arwdDxtm=ALL") or (isinstance(val, str) and "ALL" in val)
            for sql in (_up(), _down()):
                assert f"GRANT ALL ON TABLE public.{name} TO {role};" in sql


def test_view_comments():
    views = [v for v in _views()]
    comments = [v.get("comment") for v in views]
    korean = [c for c in comments if isinstance(c, str) and c.strip()]
    nulls = [c for c in comments if c is None]
    assert len(korean) == 2
    assert len(nulls) == 1
    for v in views:
        name = v.get("name") or v.get("view_name")
        c = v.get("comment")
        if c is None:
            for sql in (_up(), _down()):
                assert f"COMMENT ON VIEW public.{name}" not in sql
        else:
            escaped = c.replace("'", "''")
            for sql in (_up(), _down()):
                assert f"COMMENT ON VIEW public.{name} IS '{escaped}';" in sql


def test_unique_target_pairs():
    pairs = [
        (r["object_name"], r["column_name"])
        for r in _active()
        if r["migration_action"] == "ALTER_TYPE_USING_KST"
    ]
    assert len(pairs) == 237
    assert len(set(pairs)) == 237
    assert len(set(_alters(_up()))) == 237
    assert len(set(_alters(_down()))) == 237


def test_cron_12_complete():
    jobs = _j("TAI_TIME_CRON_MANIFEST.json")["jobs"]
    ids = [j["job_id"] for j in jobs]
    assert sorted(ids) == list(range(1, 13))
    assert len(ids) == 12
    select_ids = re.findall(r"SELECT cron\.alter_job\(\s*(\d+)", _cron_sql())
    assert sorted(int(x) for x in select_ids) == list(range(1, 13))
    by_id = {j["job_id"]: j for j in jobs}
    for jid in (1, 3, 4):
        assert by_id[jid]["active"] is False


def test_cron_active_state_preserved():
    jobs = _j("TAI_TIME_CRON_MANIFEST.json")["jobs"]
    assert all(j["active_preserved"] is True for j in jobs)
    sql = _cron_sql()
    assert "false);" in sql
    for j in jobs:
        jid = j["job_id"]
        flag = "false" if j["active"] is False else "true"
        assert re.search(rf"cron\.alter_job\(\s*{jid}[\s\S]*?{flag}\s*\)", sql)


def test_retention_localtimestamp_removed():
    sql = _cron_sql()
    assert "now() - interval '30 days'" in sql
    job11 = re.search(r"cron\.alter_job\(\s*11[\s\S]*?\)", sql)
    assert job11, "job 11 alter_job missing"
    body = job11.group(0).lower()
    assert "localtimestamp" not in body
    assert "now() - interval '90 days'" in sql
