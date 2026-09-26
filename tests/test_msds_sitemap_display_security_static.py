"""WO-MSDS-SITEMAP-DISPLAY-SECURITY-20260926-001 — migration static contract test.

Static text validation only — no DB connection.

Cases:
  S1  Target is exact: public.kosha_msds_seo_preview_display
  S2  Changes security_invoker option (SET false or RESET)
  S3  No CREATE OR REPLACE VIEW (view body not redefined)
  S4  No base-table GRANTs (chemicals / sections / snapshot_items / snapshots)
  S5  No GRANT ALL
  S6  No DML (INSERT / UPDATE / DELETE / TRUNCATE)
  S7  No RLS/policy changes
  S8  Rollback command present in comments
  S9  Transaction wrapped in BEGIN/COMMIT
"""
from __future__ import annotations

import pathlib
import re

MIGRATION = pathlib.Path(__file__).parent.parent / (
    "supabase/migrations/"
    "20260926_kosha_msds_seo_preview_display_security.sql"
)

BASE_TABLES = (
    "kosha_msds_chemicals",
    "kosha_msds_sections",
    "kosha_msds_snapshot_items",
    "kosha_msds_snapshots",
)


def _sql() -> str:
    with open(MIGRATION, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


# ═══════════════════════════════════════════════════════════════════════
# S1 — Target is kosha_msds_seo_preview_display
# ═══════════════════════════════════════════════════════════════════════
def test_S1_target_is_display_view():
    n = _norm(_sql())
    assert "alter view" in n and "kosha_msds_seo_preview_display" in n, (
        "ALTER VIEW kosha_msds_seo_preview_display not found"
    )


# ═══════════════════════════════════════════════════════════════════════
# S2 — security_invoker option is being changed
# ═══════════════════════════════════════════════════════════════════════
def test_S2_security_invoker_changed():
    n = _norm(_sql())
    assert "security_invoker" in n, "security_invoker not mentioned in migration"
    # Either RESET or SET (security_invoker = false/off)
    has_reset = bool(re.search(r"reset\s*\(\s*security_invoker\s*\)", n))
    has_set_false = bool(re.search(r"set\s*\(\s*security_invoker\s*=\s*(false|off)\s*\)", n))
    assert has_reset or has_set_false, (
        "Expected RESET (security_invoker) or SET (security_invoker = false)"
    )


# ═══════════════════════════════════════════════════════════════════════
# S3 — No CREATE OR REPLACE VIEW (view body not redefined)
# ═══════════════════════════════════════════════════════════════════════
def test_S3_no_create_or_replace_view():
    n = _norm(_sql())
    assert not re.search(r"create\s+(or\s+replace\s+)?view", n), (
        "CREATE [OR REPLACE] VIEW found — view body must not be changed"
    )


# ═══════════════════════════════════════════════════════════════════════
# S4 — No base-table GRANTs
# ═══════════════════════════════════════════════════════════════════════
def test_S4_no_base_table_grants():
    n = _norm(_sql())
    for table in BASE_TABLES:
        assert f"grant" not in n or table not in n or not re.search(
            rf"grant\b.*\b{re.escape(table)}\b", n
        ), f"GRANT on base table {table} found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# S5 — No GRANT ALL
# ═══════════════════════════════════════════════════════════════════════
def test_S5_no_grant_all():
    n = _norm(_sql())
    assert not re.search(r"grant\s+all", n), "GRANT ALL found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# S6 — No DML
# ═══════════════════════════════════════════════════════════════════════
def test_S6_no_dml():
    # Strip comments before checking for DML keywords
    sql_no_comments = re.sub(r"--[^\n]*", "", _sql())
    n = _norm(sql_no_comments)
    for dml in ("insert ", "update ", "delete ", "truncate "):
        assert dml not in n, f"DML keyword '{dml.strip()}' found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# S7 — No RLS/policy changes
# ═══════════════════════════════════════════════════════════════════════
def test_S7_no_rls_policy_changes():
    n = _norm(_sql())
    prohibited = [
        (r"create\s+policy",            "CREATE POLICY"),
        (r"alter\s+policy",             "ALTER POLICY"),
        (r"drop\s+policy",              "DROP POLICY"),
        (r"enable\s+row\s+level",       "ENABLE ROW LEVEL SECURITY"),
        (r"disable\s+row\s+level",      "DISABLE ROW LEVEL SECURITY"),
    ]
    for pattern, label in prohibited:
        assert not re.search(pattern, n), f"{label} found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# S8 — Rollback present in comments
# ═══════════════════════════════════════════════════════════════════════
def test_S8_rollback_comment_present():
    raw = _sql().lower()
    assert "rollback" in raw or (
        "set (security_invoker = true)" in raw or "set (security_invoker=true)" in raw
    ), "Rollback SET (security_invoker = true) not found in comments"


# ═══════════════════════════════════════════════════════════════════════
# S9 — Wrapped in BEGIN/COMMIT
# ═══════════════════════════════════════════════════════════════════════
def test_S9_transaction_wrapped():
    n = _norm(_sql())
    assert re.search(r"\bbegin\b", n), "BEGIN not found"
    assert re.search(r"\bcommit\b", n), "COMMIT not found"
