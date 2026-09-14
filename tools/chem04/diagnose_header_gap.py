"""Classify header_total vs parsed selectChem rows. Probe or local full.

Cursor: --pages 1,4,102,1493,2057
Local full: --full
"""
from __future__ import annotations

import argparse
import json

from services.kosha_msds.contract import KOSHA_WEB_HOST, KOSHA_WEB_LIST_PATH, KOSHA_WEB_LIST_TYPE
from services.kosha_msds.current_index import CurrentIndexError, default_get, inspect_list_html, parse_list_html
from tools.chem04.paths import MANIFESTS, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 classify header vs selectChem gap")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pages", help="comma-separated page indexes (Cursor probe)")
    mode.add_argument("--full", action="store_true", help="LOCAL: inspect every header page")
    parser.add_argument("--delay", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    url = f"{KOSHA_WEB_HOST}{KOSHA_WEB_LIST_PATH}"
    status, first = default_get(url, {"pageIndex": "1", "listType": KOSHA_WEB_LIST_TYPE})
    if status != 200:
        raise SystemExit(f"HTTP {status}")
    first_stats = inspect_list_html(first)
    if args.full:
        pages = list(range(1, first_stats.page_count + 1))
        executor = "LOCAL"
    else:
        pages = [int(p.strip()) for p in args.pages.split(",") if p.strip()]
        executor = "CURSOR_PROBE"
    page_reports = []
    totals = {
        "href_selectchem": 0,
        "legacy_selectchem": 0,
        "parsed_selectchem": 0,
        "data_tr": 0,
        "data_tr_without_selectchem": 0,
        "apostrophe_name_recovered": 0,
    }
    for i, page in enumerate(pages):
        if i == 0 and page == 1:
            body = first
        else:
            if args.delay and i:
                import time

                time.sleep(args.delay)
            status, body = default_get(url, {"pageIndex": str(page), "listType": KOSHA_WEB_LIST_TYPE})
            if status != 200:
                raise CurrentIndexError("HTTP", f"page {page} HTTP {status}")
        stats = inspect_list_html(body)
        rows, *_ = parse_list_html(body, page=page)
        rec = {
            "page": page,
            "header_total": stats.header_total,
            "page_no": stats.page_no,
            "href_selectchem": stats.href_selectchem,
            "legacy_selectchem": stats.legacy_selectchem,
            "parsed_selectchem": stats.parsed_selectchem,
            "parsed_rows": len(rows),
            "data_tr": stats.data_tr,
            "data_tr_without_selectchem": stats.data_tr_without_selectchem,
            "apostrophe_name_recovered": stats.apostrophe_name_recovered,
        }
        page_reports.append(rec)
        for key in totals:
            totals[key] += rec[key] if key != "apostrophe_name_recovered" else stats.apostrophe_name_recovered
        print(
            f"DIAG page={page} href={stats.href_selectchem} legacy={stats.legacy_selectchem} "
            f"parsed={stats.parsed_selectchem} data_tr={stats.data_tr} no_select={stats.data_tr_without_selectchem}",
            flush=True,
        )
    classification = "PARSER_APOSTROPHE_NAME"
    if totals["data_tr_without_selectchem"]:
        classification = "NO_SELECTCHEM_DISPLAY_ROWS"
    elif totals["href_selectchem"] != totals["parsed_selectchem"]:
        classification = "PARSER_UNDERCOUNT"
    elif totals["apostrophe_name_recovered"] == 0 and totals["href_selectchem"] == totals["parsed_selectchem"]:
        classification = "HREF_EQUALS_PARSED"
    payload = {
        "executor": executor,
        "header_total": first_stats.header_total,
        "page_count": first_stats.page_count,
        "pages_inspected": len(pages),
        "totals": totals,
        "gap_classification": classification,
        "note": (
            "698-row gap vs 19870 was legacy [^']* chemName parse. "
            "Live probe: data_tr without selectChem = 0; apostrophe names were dropped."
        ),
        "pages": page_reports if not args.full else None,
    }
    dest = MANIFESTS / "header_gap_diagnosis.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "pages"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
