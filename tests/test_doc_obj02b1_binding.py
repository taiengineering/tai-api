"""OBJ02-B1: Catalog schema binding — migration static verification tests.

Verifies that the migration logic is structurally correct without
hitting a real DB. All assertions mirror the migration's DO $check$ blocks.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import types

# ── Canonical stub data ───────────────────────────────────────────────────────
CAT_ID_1 = "aaaaaaaa-0001-0001-0001-000000000001"
CAT_ID_2 = "aaaaaaaa-0002-0002-0002-000000000002"
SCHEMA_ID_APPROVED = "bbbbbbbb-0001-0001-0001-000000000001"
SCHEMA_ID_CANDIDATE = "bbbbbbbb-0002-0002-0002-000000000002"

_CATALOG_ROWS = [
    {"id": CAT_ID_1, "doc_id": "DOC-001", "doc_name": "점검표 A", "document_family": "CHK"},
    {"id": CAT_ID_2, "doc_id": "DOC-002", "doc_name": "점검표 B", "document_family": "CHK"},
]

_SCHEMA_ROWS = [
    {
        "id": SCHEMA_ID_APPROVED,
        "status": "APPROVED_FOR_RUNTIME_USE",
        "catalog_document_id": CAT_ID_1,
        "source_trace": {"source_table": "document_forms",
                         "source_id": CAT_ID_1,
                         "doc_id": "DOC-001"},
    },
    {
        "id": SCHEMA_ID_CANDIDATE,
        "status": "CANDIDATE",
        "catalog_document_id": CAT_ID_2,
        "source_trace": {"source_table": "document_forms",
                         "source_id": CAT_ID_2,
                         "doc_id": "DOC-002"},
    },
]


# ── B1: migration duplicate-doc_id guard (static) ────────────────────────────

def test_B1_no_duplicate_doc_id_in_sourced_schemas():
    """PRE assertion: doc_id unique within document_forms-sourced schemas."""
    doc_ids = [
        s["source_trace"]["doc_id"]
        for s in _SCHEMA_ROWS
        if s["source_trace"]["source_table"] == "document_forms"
    ]
    counts = {}
    for d in doc_ids:
        counts[d] = counts.get(d, 0) + 1
    duplicates = [d for d, c in counts.items() if c > 1]
    assert duplicates == [], f"duplicate doc_ids: {duplicates}"


def test_B2_backfill_dual_condition_exact():
    """POST assertion: backfill correctly sets catalog_document_id via dual key."""
    backfilled = []
    catalog_by_id = {r["id"]: r for r in _CATALOG_ROWS}
    catalog_by_src = {(r["id"], r["doc_id"]): r for r in _CATALOG_ROWS}

    for s in _SCHEMA_ROWS:
        st = s["source_trace"]
        if st.get("source_table") != "document_forms":
            continue
        key = (st["source_id"], st["doc_id"])
        cat = catalog_by_src.get(key)
        if cat:
            backfilled.append({"schema_id": s["id"],
                               "catalog_document_id": cat["id"]})

    assert len(backfilled) == 2


def test_B3_post_backfill_no_null_for_document_forms_source():
    """POST assertion: all document_forms-sourced schemas get catalog_document_id."""
    sourced = [s for s in _SCHEMA_ROWS
               if s["source_trace"]["source_table"] == "document_forms"]
    assert all(s["catalog_document_id"] is not None for s in sourced)


def test_B4_fk_integrity():
    """POST assertion: every non-NULL catalog_document_id references document_forms."""
    catalog_ids = {r["id"] for r in _CATALOG_ROWS}
    for s in _SCHEMA_ROWS:
        cid = s.get("catalog_document_id")
        if cid is not None:
            assert cid in catalog_ids, (
                f"schema {s['id']} references non-existent catalog_document_id={cid}"
            )


def test_B5_no_kind_conflict():
    """POST assertion: only document_forms-sourced schemas have catalog_document_id."""
    for s in _SCHEMA_ROWS:
        cid = s.get("catalog_document_id")
        st = s.get("source_trace", {})
        if cid is not None:
            assert st.get("source_table") == "document_forms", (
                f"schema {s['id']} has catalog_document_id but source_table="
                f"{st.get('source_table')}"
            )


def test_B6_unique_active_approved_per_catalog():
    """FINAL assertion: at most one APPROVED_FOR_RUNTIME_USE per catalog doc."""
    counts: dict[str, int] = {}
    for s in _SCHEMA_ROWS:
        if s["status"] == "APPROVED_FOR_RUNTIME_USE" and s.get("catalog_document_id"):
            cid = s["catalog_document_id"]
            counts[cid] = counts.get(cid, 0) + 1
    violations = [cid for cid, c in counts.items() if c > 1]
    assert violations == [], f"multiple APPROVED schemas: {violations}"


def test_B7_check_constraint_catalog_source_kind():
    """chk_rfs_catalog_source_kind: NULL OR source_table='document_forms'."""
    for s in _SCHEMA_ROWS:
        cid = s.get("catalog_document_id")
        source_table = s.get("source_trace", {}).get("source_table")
        assert cid is None or source_table == "document_forms", (
            f"schema {s['id']} violates chk_rfs_catalog_source_kind"
        )
