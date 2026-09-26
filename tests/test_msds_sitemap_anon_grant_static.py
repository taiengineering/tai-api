"""WO-MSDS-SITEMAP-ANON-GRANT-20260926-001 — migration static contract test.

Static text validation only — no DB connection.

Cases:
  G1  GRANT target is exactly public.kosha_msds_seo_preview_current
  G2  Grantee is exactly anon
  G3  Privilege is SELECT only (not ALL, not INSERT/UPDATE/DELETE/TRUNCATE)
  G4  GRANT ALL absent
  G5  DML grants absent (INSERT, UPDATE, DELETE, TRUNCATE)
  G6  No structural mutations (ALTER TABLE, ALTER VIEW, CREATE/DROP VIEW,
      CREATE/ALTER POLICY, ENABLE/DISABLE ROW LEVEL SECURITY)
  G7  Rollback command present in comments (REVOKE SELECT ... FROM anon)
  G8  Transaction wrapped in BEGIN/COMMIT
"""
from __future__ import annotations

import os
import pathlib
import re

MIGRATION = pathlib.Path(__file__).parent.parent / (
    "supabase/migrations/"
    "20260926_kosha_msds_seo_preview_current_anon_select.sql"
)


def _sql() -> str:
    with open(MIGRATION, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


# ═══════════════════════════════════════════════════════════════════════
# G1 — GRANT target is public.kosha_msds_seo_preview_current
# ═══════════════════════════════════════════════════════════════════════
def test_G1_grant_target_is_current_view():
    n = _norm(_sql())
    assert "grant select" in n and "kosha_msds_seo_preview_current" in n, (
        "GRANT SELECT on kosha_msds_seo_preview_current not found"
    )


# ═══════════════════════════════════════════════════════════════════════
# G2 — Grantee is anon
# ═══════════════════════════════════════════════════════════════════════
def test_G2_grantee_is_anon():
    n = _norm(_sql())
    m = re.search(
        r"grant\s+select\s+on\s+\S*kosha_msds_seo_preview_current\S*\s+to\s+(\w+)",
        n,
    )
    assert m, "GRANT SELECT ... TO <grantee> pattern not found"
    assert m.group(1).rstrip(";") == "anon", (
        f"Expected grantee 'anon', got '{m.group(1)}'"
    )


# ═══════════════════════════════════════════════════════════════════════
# G3 — Privilege is SELECT, not a wildcard or combination
# ═══════════════════════════════════════════════════════════════════════
def test_G3_privilege_is_select_only():
    n = _norm(_sql())
    grants = re.findall(r"grant\s+([\w,\s]+?)\s+on\s+", n)
    for g in grants:
        privs = [p.strip() for p in g.split(",")]
        for p in privs:
            assert p == "select", (
                f"Non-SELECT privilege found in GRANT: '{p}'"
            )


# ═══════════════════════════════════════════════════════════════════════
# G4 — GRANT ALL absent
# ═══════════════════════════════════════════════════════════════════════
def test_G4_no_grant_all():
    n = _norm(_sql())
    assert not re.search(r"grant\s+all", n), "GRANT ALL found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# G5 — DML grants absent
# ═══════════════════════════════════════════════════════════════════════
def test_G5_no_dml_grants():
    n = _norm(_sql())
    for dml in ("insert", "update", "delete", "truncate"):
        assert not re.search(rf"grant\s+{dml}", n), (
            f"GRANT {dml.upper()} found — prohibited"
        )


# ═══════════════════════════════════════════════════════════════════════
# G6 — No structural mutations
# ═══════════════════════════════════════════════════════════════════════
def test_G6_no_structural_mutations():
    n = _norm(_sql())
    prohibited = [
        (r"alter\s+table",              "ALTER TABLE"),
        (r"alter\s+view",               "ALTER VIEW"),
        (r"create\s+view",              "CREATE VIEW"),
        (r"drop\s+view",                "DROP VIEW"),
        (r"drop\s+table",               "DROP TABLE"),
        (r"create\s+policy",            "CREATE POLICY"),
        (r"alter\s+policy",             "ALTER POLICY"),
        (r"enable\s+row\s+level",       "ENABLE ROW LEVEL SECURITY"),
        (r"disable\s+row\s+level",      "DISABLE ROW LEVEL SECURITY"),
    ]
    for pattern, label in prohibited:
        assert not re.search(pattern, n), f"{label} found — prohibited"


# ═══════════════════════════════════════════════════════════════════════
# G7 — Rollback comment present
# ═══════════════════════════════════════════════════════════════════════
def test_G7_rollback_comment_present():
    raw = _sql().lower()
    assert "revoke select" in raw and "anon" in raw, (
        "Rollback REVOKE SELECT ... FROM anon not found in comments"
    )


# ═══════════════════════════════════════════════════════════════════════
# G8 — Wrapped in BEGIN/COMMIT
# ═══════════════════════════════════════════════════════════════════════
def test_G8_transaction_wrapped():
    n = _norm(_sql())
    assert re.search(r"\bbegin\b", n), "BEGIN not found"
    assert re.search(r"\bcommit\b", n), "COMMIT not found"
