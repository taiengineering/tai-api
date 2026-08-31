#!/usr/bin/env python3
"""Generate TAI TIME KST cutover UP/DOWN SQL from SoT manifests. stdlib only.

Reads:
  docs/time/TAI_TIME_ACTIVE_COLUMN_MANIFEST.json
  docs/time/TAI_TIME_ISOLATED_ASSETS.json
  docs/time/TAI_TIME_VIEW_MANIFEST.json

Writes:
  docs/sql/20260831_tai_time_kst_cutover_{up,down}.sql

Rules:
  ALTER_TYPE_USING_KST → ALTER TYPE (237 = DIRECT 236 + PARTITION_ROOT 1)
  PARENT_DRIVEN / DERIVED_RECREATE → no ALTER TYPE
  isolated (object_name, column_name) in ALTER set → sys.exit HARD FAIL (not skip)
  View census = pg_depend on ALTER source columns (not "view column is naive").
  DROP VIEW explicit 5 names from view manifest, CASCADE forbidden.
  v_demo_buildings is ISOLATED_DEPENDENCY_ONLY: DROP/CREATE only, no ALTER.
  defaults: not re-emitted (ALTER TYPE preserves existing DEFAULT)
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIME = os.path.join(ROOT, "docs", "time")
SQL = os.path.join(ROOT, "docs", "sql")
ACTIVE_PATH = os.path.join(TIME, "TAI_TIME_ACTIVE_COLUMN_MANIFEST.json")
ISOLATED_PATH = os.path.join(TIME, "TAI_TIME_ISOLATED_ASSETS.json")
VIEW_PATH = os.path.join(TIME, "TAI_TIME_VIEW_MANIFEST.json")
UP_PATH = os.path.join(SQL, "20260831_tai_time_kst_cutover_up.sql")
DOWN_PATH = os.path.join(SQL, "20260831_tai_time_kst_cutover_down.sql")

ALTER_ACTION = "ALTER_TYPE_USING_KST"
SKIP_ACTIONS = {"PARENT_DRIVEN", "DERIVED_RECREATE"}
REQUIRED_VIEWS = (
    "v_demo_buildings",
    "v_equipment_unified",
    "v_files_unified",
    "v_payments_list",
    "v_process_unified",
)
ACL_ROLES = ("anon", "authenticated", "postgres", "service_role")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ident(name: str) -> str:
    if not isinstance(name, str) or not IDENT.match(name):
        sys.exit(f"HARD FAIL invalid identifier {name!r}")
    return name


def columns_of(doc) -> list:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        if isinstance(doc.get("columns"), list):
            return doc["columns"]
        if isinstance(doc.get("rows"), list):
            return doc["rows"]
    sys.exit("HARD FAIL active/isolated manifest must be a list or {columns|rows: [...]}")


def pair(row) -> tuple[str, str]:
    try:
        return (row["object_name"], row["column_name"])
    except (KeyError, TypeError):
        sys.exit(f"HARD FAIL row missing object_name/column_name: {row!r}")


def qtable(name: str) -> str:
    return f"public.{ident(name)}"


def qcol(name: str) -> str:
    return ident(name)


def alter_line(tbl: str, col: str, new_type: str) -> str:
    c = qcol(col)
    return (
        f"ALTER TABLE {qtable(tbl)} ALTER COLUMN {c} "
        f"TYPE {new_type} USING {c} AT TIME ZONE 'Asia/Seoul';"
    )


def isolated_pairs(iso_doc) -> set[tuple[str, str]]:
    return {pair(row) for row in columns_of(iso_doc)}


def views_of(doc) -> list:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("views"), list):
        return doc["views"]
    sys.exit("HARD FAIL view manifest must be a list or {views: [...]}")


def view_by_name(views: list) -> dict:
    m = {}
    for v in views:
        name = v.get("name") or v.get("view_name") or v.get("object_name")
        if not name:
            sys.exit("HARD FAIL view row missing name")
        m[name] = v
    return m


def grant_sql(view: str) -> list[str]:
    return [f"GRANT ALL ON TABLE {qtable(view)} TO {role};" for role in ACL_ROLES]


def comment_sql(view: str, comment) -> str | None:
    if comment is None:
        return None
    escaped = str(comment).replace("'", "''")
    return f"COMMENT ON VIEW {qtable(view)} IS '{escaped}';"


def definition_of(v: dict) -> str:
    d = v.get("definition") or v.get("viewdef") or v.get("pg_get_viewdef")
    if not d or not str(d).strip():
        sys.exit(f"HARD FAIL missing viewdef for {v.get('name')}")
    return str(d).rstrip().rstrip(";")


def create_view_sql(name: str, definition: str) -> str:
    body = definition.strip()
    if body.lower().startswith("create"):
        return body if body.endswith(";") else body + ";"
    return f"CREATE VIEW {qtable(name)} AS\n{body};"


def generate(active_doc, iso_doc, view_doc) -> tuple[str, str]:
    rows = columns_of(active_doc)
    isolated = isolated_pairs(iso_doc)
    alter_rows = []
    seen = set()
    for row in rows:
        action = row.get("migration_action")
        p = pair(row)
        if p in isolated:
            sys.exit(f"HARD FAIL isolated target in ALTER set {p[0]}.{p[1]}")
        if action in SKIP_ACTIONS:
            continue
        if action != ALTER_ACTION:
            sys.exit(
                f"HARD FAIL unknown migration_action {action!r} on {p[0]}.{p[1]}"
            )
        if p in seen:
            sys.exit(f"HARD FAIL duplicate ALTER target {p[0]}.{p[1]}")
        seen.add(p)
        alter_rows.append(row)

    views = view_by_name(views_of(view_doc))
    names = [v.get("name") or v.get("view_name") for v in views_of(view_doc)]
    if names != list(REQUIRED_VIEWS):
        sys.exit(f"HARD FAIL view manifest order/set {names!r} != {list(REQUIRED_VIEWS)!r}")
    missing = [n for n in REQUIRED_VIEWS if n not in views]
    if missing:
        sys.exit(f"HARD FAIL view manifest missing {missing}")
    if view_doc.get("required_view_count") != 5:
        sys.exit("HARD FAIL view manifest required_view_count must be 5 (pg_depend)")
    if view_doc.get("downstream_view_count") != 0:
        sys.exit("HARD FAIL downstream views must be 0")
    if view_doc.get("non_view_rule_count") != 0:
        sys.exit("HARD FAIL non-view rewrite rules must be 0")

    drops = [f"DROP VIEW {qtable(n)};" for n in REQUIRED_VIEWS]
    if any("CASCADE" in d.upper() for d in drops):
        sys.exit("HARD FAIL CASCADE on DROP VIEW")

    alters_up = [
        alter_line(r["object_name"], r["column_name"], "timestamptz") for r in alter_rows
    ]
    alters_down = [
        alter_line(r["object_name"], r["column_name"], "timestamp without time zone")
        for r in alter_rows
    ]

    creates = []
    owners = []
    grants = []
    comments = []
    for name in REQUIRED_VIEWS:
        v = views[name]
        creates.append(create_view_sql(name, definition_of(v)))
        owner = v.get("owner") or "postgres"
        owners.append(f"ALTER VIEW {qtable(name)} OWNER TO {ident(owner)};")
        grants.extend(grant_sql(name))
        c = comment_sql(name, v.get("comment"))
        if c:
            comments.append(c)

    header = (
        "-- TAI TIME PHASE 2 KST cutover. EXECUTE = 0.\n"
        "-- Generated by scripts/generate_time_kst_migration.py. Do not hand-edit ALTER list.\n"
        "-- TAI Supabase vwlahtguyggrhvslabax: DO NOT RUN.\n"
    )

    up_parts = [
        header,
        "BEGIN;",
        "-- 5 view DROP (pg_depend on ALTER source columns; explicit; CASCADE 금지)",
        *drops,
        f"-- {len(alters_up)} column ALTER to timestamptz (USING AT TIME ZONE Asia/Seoul)",
        *alters_up,
        "-- 5 view EXACT recreate + OWNER / GRANT ALL / COMMENT (omit COMMENT when null)",
        *creates,
        *owners,
        *grants,
        *comments,
        "COMMIT;",
        "",
    ]
    down_parts = [
        header,
        "BEGIN;",
        "-- 5 view DROP (pg_depend on ALTER source columns; explicit; CASCADE 금지)",
        *drops,
        f"-- {len(alters_down)} column ALTER to timestamp without time zone (USING AT TIME ZONE Asia/Seoul)",
        *alters_down,
        "-- 5 view EXACT recreate + OWNER / GRANT ALL / COMMENT (omit COMMENT when null)",
        *creates,
        *owners,
        *grants,
        *comments,
        "COMMIT;",
        "",
    ]
    return "\n".join(up_parts), "\n".join(down_parts)


def main() -> int:
    active = load(ACTIVE_PATH)
    isolated = load(ISOLATED_PATH)
    views = load(VIEW_PATH)
    rows = columns_of(active)
    if len(rows) == 0:
        sys.exit("HARD FAIL active manifest has 0 rows (SoT json_agg not materialized)")
    up, down = generate(active, isolated, views)
    os.makedirs(SQL, exist_ok=True)
    with open(UP_PATH, "w", encoding="utf-8") as f:
        f.write(up)
    with open(DOWN_PATH, "w", encoding="utf-8") as f:
        f.write(down)
    print(f"wrote {UP_PATH}")
    print(f"wrote {DOWN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
