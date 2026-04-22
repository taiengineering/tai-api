#!/usr/bin/env python3
"""law.go.kr 에서 건축법·산업안전보건법 본문 XML을 받아 scripts/debug/ 에 저장 (SESSION 1)."""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

BASE = "http://www.law.go.kr/DRF"
OC = os.environ.get("LAW_API_OC", "taieng")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TAI-Session1/1.0)",
    "Accept": "application/xml,text/xml,*/*",
}

TARGETS = [
    ("건축법", "geonchuk_raw.xml"),
    ("산업안전보건법", "sanbohoeon_raw.xml"),
]


def _search(query: str) -> tuple[int, str]:
    r = requests.get(
        f"{BASE}/lawSearch.do",
        params={"OC": OC, "target": "law", "type": "XML", "query": query, "display": 5, "page": 1},
        headers=HEADERS,
        timeout=45,
    )
    r.encoding = "utf-8"
    return r.status_code, r.text


def _extract_mst(xml: str) -> tuple[str | None, str | None]:
    root = ET.fromstring(xml)
    for law in root.findall(".//법령") + root.findall(".//law"):
        mst = (law.findtext("법령일련번호", "") or law.findtext("법령ID", "") or "").strip()
        name = (law.findtext("법령명한글", "") or law.findtext("법령명", "") or "").strip()
        if mst:
            return mst, name
    return None, None


def _fetch_content(mst: str) -> tuple[int, str]:
    r = requests.get(
        f"{BASE}/lawService.do",
        params={"OC": OC, "target": "law", "MST": mst, "type": "XML"},
        headers=HEADERS,
        timeout=120,
    )
    r.encoding = "utf-8"
    return r.status_code, r.text


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    for query, filename in TARGETS:
        st, body = _search(query)
        if st != 200:
            print(f"[ERR] search {query}: HTTP {st}", file=sys.stderr)
            return 1
        mst, name = _extract_mst(body)
        if not mst:
            print(f"[ERR] no MST for {query}", file=sys.stderr)
            return 1
        st2, xml = _fetch_content(mst)
        if st2 != 200:
            print(f"[ERR] content {query} MST={mst}: HTTP {st2}", file=sys.stderr)
            return 1
        path = out_dir / filename
        path.write_text(xml, encoding="utf-8")
        print(f"OK {query} ({name}) MST={mst} -> {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
