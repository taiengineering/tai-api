"""
Seed document_forms from docs/DOCUMENT_MAP_FULL.csv.

Usage:
  python3 scripts/seed_document_forms_from_csv.py
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from db.supabase_client import get_supabase


CSV_PATH = Path(__file__).resolve().parents[1] / "docs" / "DOCUMENT_MAP_FULL.csv"


def _normalize_grade(v: str) -> str:
    g = (v or "").strip().upper()
    return g if g in {"A", "B", "C", "D", "X"} else "X"


def _ticket_cost_from_grade(grade: str) -> int:
    return {"A": 0, "B": 10, "C": 30, "D": 50, "X": 0}.get(grade, 0)


def _to_int(v: str, default: int = 5) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _build_row(src: Dict[str, str]) -> Dict[str, object]:
    grade = _normalize_grade(src.get("tai_grade", "X"))
    return {
        "doc_id": (src.get("doc_id") or "").strip(),
        "doc_name": (src.get("doc_name") or "").strip(),
        "sector": (src.get("sector") or "공통").strip(),
        "category": (src.get("category") or "일상").strip(),
        "law_ref": (src.get("law_ref") or "").strip() or None,
        "regulation_ref": (src.get("regulation_ref") or "").strip() or None,
        "obligation": (src.get("obligation") or "법정필수").strip(),
        "penalty": (src.get("penalty") or "").strip() or None,
        "submit_to": (src.get("submit_to") or "").strip() or None,
        "submit_timing": (src.get("submit_timing") or "").strip() or None,
        "retention": (src.get("retention") or "").strip() or None,
        "writer": (src.get("writer") or "").strip() or None,
        "frequency": (src.get("frequency") or "").strip() or None,
        "tai_grade": grade,
        "tai_difficulty": (src.get("tai_difficulty") or "X").strip().upper() or "X",
        "ticket_cost": _ticket_cost_from_grade(grade),
        "existing_data": (src.get("existing_data") or "").strip() or None,
        "additional_input": (src.get("additional_input") or "").strip() or None,
        "priority": _to_int(src.get("priority", "5"), default=5),
        "note": (src.get("note") or "").strip() or None,
        "file_url": (src.get("file_url") or "").strip() or None,
        "tab_type": (src.get("tab_type") or "법정서식").strip() or "법정서식",
        "is_active": True,
    }


def _chunks(items: List[Dict[str, object]], size: int = 100):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}. Add DOCUMENT_MAP_FULL.csv first."
        )

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [_build_row(r) for r in reader if (r.get("doc_id") or "").strip()]

    if not rows:
        print("No rows to seed.")
        return

    supabase = get_supabase()
    inserted = 0
    for batch in _chunks(rows, size=100):
        # upsert by doc_id to keep idempotent behavior
        resp = supabase.table("document_forms").upsert(
            batch, on_conflict="doc_id"
        ).execute()
        inserted += len(resp.data or [])

    print(f"seed completed. source_rows={len(rows)} upserted_rows={inserted}")


if __name__ == "__main__":
    main()

