#!/usr/bin/env python3
"""
네이버 지식iN 검색 결과 모니터링 → Supabase naver_kin_log 적재.

- 자동 게시·자동 답변 등 쓰기/게시 로직은 포함하지 않습니다.
- 네이버 검색 API(지식iN) 조회 및 DB 로깅만 수행합니다.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

NAVER_KIN_API = "https://openapi.naver.com/v1/search/kin.json"


def _strip_tags(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = html.unescape(t)
    return " ".join(t.split())


def _require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def _keywords() -> list[str]:
    raw = os.environ.get("NAVER_KIN_KEYWORDS", "").strip()
    if not raw:
        return ["산업안전", "과태료", "안전관리책임자"]
    parts = [k.strip() for k in raw.split(",")]
    return [k for k in parts if k]


def _display() -> int:
    try:
        n = int(os.environ.get("NAVER_KIN_DISPLAY", "30"))
    except ValueError:
        n = 30
    return max(1, min(100, n))


def _sort() -> str:
    s = os.environ.get("NAVER_KIN_SORT", "date").strip().lower()
    if s not in ("sim", "date", "point"):
        return "date"
    return s


def fetch_kin_items(keyword: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client_id = _require_env("NAVER_CLIENT_ID")
    client_secret = _require_env("NAVER_CLIENT_SECRET")
    params = {
        "query": keyword,
        "display": str(_display()),
        "start": "1",
        "sort": _sort(),
    }
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Accept": "application/json",
    }
    r = requests.get(
        NAVER_KIN_API,
        params=params,
        headers=headers,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    items = data.get("items") or []
    return items, data


def supabase_insert_row(
    base_url: str,
    service_key: str,
    row: dict[str, Any],
) -> tuple[bool, int]:
    """
    Insert one row. Returns (inserted, status_code).
    Duplicate question_link → skip (409).
    """
    url = base_url.rstrip("/") + "/rest/v1/naver_kin_log"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    r = requests.post(url, headers=headers, json=row, timeout=30)
    if r.status_code in (200, 201):
        return True, r.status_code
    if r.status_code == 409:
        return False, r.status_code
    print(f"Supabase insert error {r.status_code}: {r.text[:500]}", file=sys.stderr)
    r.raise_for_status()
    return False, r.status_code


def main() -> None:
    supabase_url = _require_env("SUPABASE_URL")
    supabase_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")

    run_at = datetime.now(timezone.utc).isoformat()
    total_new = 0
    total_dup = 0
    total_api_items = 0

    for kw in _keywords():
        items, envelope = fetch_kin_items(kw)
        total = envelope.get("total")
        for idx, item in enumerate(items):
            total_api_items += 1
            link = (item.get("link") or "").strip()
            if not link:
                continue
            title = _strip_tags(item.get("title") or "")
            desc = _strip_tags(item.get("description") or "")
            row = {
                "question_link": link,
                "question_title": title[:2000] if title else None,
                "question_description": desc[:8000] if desc else None,
                "search_keyword": kw,
                "sort_mode": _sort(),
                "api_total": total,
                "item_index": idx,
                "raw_item": item,
                "run_at": run_at,
            }
            inserted, code = supabase_insert_row(supabase_url, supabase_key, row)
            if inserted:
                total_new += 1
            elif code == 409:
                total_dup += 1

    print(
        json.dumps(
            {
                "ok": True,
                "run_at": run_at,
                "keywords": _keywords(),
                "api_items_seen": total_api_items,
                "inserted": total_new,
                "skipped_duplicate": total_dup,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
