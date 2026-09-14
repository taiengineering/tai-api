"""KOSHA official current web index collector. workers=1. No pageSize guessing."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.kosha_msds.contract import (
    KOSHA_WEB_HOST,
    KOSHA_WEB_LIST_PATH,
    KOSHA_WEB_LIST_TYPE,
)
from services.kosha_msds.identity import normalize_chem_id
from services.time import now_kst, serialize_external_utc

GetFn = Callable[[str, dict[str, str]], tuple[int, str]]
HEADER_RE = re.compile(
    r"총<span class=\"FontBold01\">(\d+)</span>건 \[(\d+)/(\d+) 페이지\]"
)
SELECT_RE = re.compile(r"selectChem\('([^']*)','([^']*)','([^']*)'\)")
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)


class CurrentIndexError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class OfficialCurrentRow:
    chem_id: Optional[str]
    official_name: Optional[str]
    official_cas: Optional[str]
    official_revision_date: Optional[str]
    official_page: int

    def as_row(self) -> dict[str, object]:
        return {
            "official_name": self.official_name,
            "official_cas": self.official_cas,
            "official_revision_date": self.official_revision_date,
            "official_identifier_if_present": self.chem_id,
            "official_page": self.official_page,
            "chemId": self.chem_id,
        }


def detect_access_block(http_status: int, body: str) -> Optional[str]:
    if http_status == 429:
        return "HTTP_429"
    if http_status == 403:
        return "HTTP_403"
    low = (body or "").lower()
    if "captcha" in low or "recaptcha" in low:
        return "CAPTCHA"
    if "access denied" in low or "access-denied" in low:
        return "ACCESS_DENIED"
    if "anti-bot" in low or "cf-challenge" in low:
        return "ANTI_BOT"
    return None


def parse_list_html(html: str, *, page: int) -> tuple[list[OfficialCurrentRow], int, int, int]:
    header = HEADER_RE.search(html or "")
    if not header:
        raise CurrentIndexError("HEADER_MISSING", "official list header not found")
    total, page_no, page_count = (int(header.group(1)), int(header.group(2)), int(header.group(3)))
    rows: list[OfficialCurrentRow] = []
    for match in SELECT_RE.finditer(html or ""):
        chem_id = normalize_chem_id(match.group(1))
        cas = (match.group(2) or "").strip() or None
        name = (match.group(3) or "").strip() or None
        after = html[match.end() :]
        end = after.lower().find("</tr>")
        chunk = after[:end] if end >= 0 else after[:500]
        tds = re.findall(r"<td[^>]*>(.*?)</td>", chunk, re.I | re.S)
        revision = None
        if tds:
            revision = re.sub(r"<[^>]+>", "", tds[-1]).strip() or None
        rows.append(
            OfficialCurrentRow(
                chem_id=chem_id,
                official_name=name,
                official_cas=cas,
                official_revision_date=revision,
                official_page=page,
            )
        )
    return rows, total, page_no, page_count


def default_get(url: str, params: dict[str, str]) -> tuple[int, str]:
    full = f"{url}?{urlencode(params)}" if params else url
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            req = Request(full, headers={"User-Agent": "TAI-CHEM04-index/1.0"})
            with urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, body
        except (ConnectionResetError, TimeoutError, OSError) as exc:
            last_exc = exc
            time.sleep(2.0 * attempt)
    raise CurrentIndexError("TRANSPORT", f"connection failed: {last_exc}")


def collect_current_index(
    *,
    dest: Path,
    get_fn: GetFn = default_get,
    delay_s: float = 0.5,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_pages: Optional[int] = None,
    log_progress: bool = False,
    resume: bool = False,
) -> dict[str, object]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{KOSHA_WEB_HOST}{KOSHA_WEB_LIST_PATH}"
    first_status, first_body = get_fn(url, {"pageIndex": "1", "listType": KOSHA_WEB_LIST_TYPE})
    block = detect_access_block(first_status, first_body)
    if block:
        raise CurrentIndexError(block, "official current index STOP")
    first_rows, total, page_no, page_count = parse_list_html(first_body, page=1)
    if page_no != 1:
        raise CurrentIndexError("PAGE_MISMATCH", f"expected page 1, got {page_no}")
    last_page = page_count if max_pages is None else min(page_count, max_pages)
    existing: list[OfficialCurrentRow] = []
    start_page = 1
    mode = "w"
    if resume and dest.exists():
        existing = load_current_rows(dest)
        if existing:
            start_page = max(r.official_page for r in existing) + 1
            mode = "a"
    all_rows = list(existing)
    with dest.open(mode, encoding="utf-8") as fh:
        if start_page <= 1:
            for row in first_rows:
                fh.write(json.dumps(row.as_row(), ensure_ascii=False) + "\n")
            all_rows.extend(first_rows)
            start_page = 2
        for page in range(start_page, last_page + 1):
            if delay_s:
                sleep_fn(delay_s)
            page_rows = None
            last_len = 0
            for attempt in range(1, 4):
                status, body = get_fn(url, {"pageIndex": str(page), "listType": KOSHA_WEB_LIST_TYPE})
                block = detect_access_block(status, body)
                if block:
                    raise CurrentIndexError(block, f"STOP at page {page}")
                try:
                    page_rows, _total, got_page, _pages = parse_list_html(body, page=page)
                except CurrentIndexError as exc:
                    if exc.code == "HEADER_MISSING" and attempt < 3:
                        sleep_fn(2.0 * attempt)
                        continue
                    raise
                if got_page != page:
                    raise CurrentIndexError("PAGE_MISMATCH", f"expected page {page}, got {got_page}")
                last_len = len(page_rows)
                if page_rows:
                    break
                sleep_fn(1.0 * attempt)
            if not page_rows:
                raise CurrentIndexError("PAGE_EMPTY", f"no rows at page {page} last_len={last_len}")
            for row in page_rows:
                fh.write(json.dumps(row.as_row(), ensure_ascii=False) + "\n")
            fh.flush()
            all_rows.extend(page_rows)
            if log_progress and page % 50 == 0:
                print(f"INDEX page={page}/{last_page} rows={len(all_rows)}", flush=True)
    cas_values = [r.official_cas for r in all_rows if r.official_cas]
    unique_ids = [r.chem_id for r in all_rows if r.chem_id]
    return {
        "row_count": len(all_rows),
        "header_total": total,
        "page_count": last_page,
        "unique_cas": len(set(cas_values)),
        "cas_null": sum(1 for r in all_rows if not r.official_cas),
        "duplicate_cas": len(cas_values) - len(set(cas_values)),
        "direct_official_id": len(unique_ids),
        "unique_chem_id": len(set(unique_ids)),
        "written_at": serialize_external_utc(now_kst()),
        "artifact_path": str(dest),
    }


def load_current_rows(path: Path) -> list[OfficialCurrentRow]:
    rows: list[OfficialCurrentRow] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            rows.append(
                OfficialCurrentRow(
                    chem_id=rec.get("chemId") or rec.get("official_identifier_if_present"),
                    official_name=rec.get("official_name"),
                    official_cas=rec.get("official_cas"),
                    official_revision_date=rec.get("official_revision_date"),
                    official_page=int(rec.get("official_page") or 0),
                )
            )
    return rows


def diff_current_snapshots(
    previous: list[OfficialCurrentRow],
    current: list[OfficialCurrentRow],
) -> dict[str, tuple[str, ...]]:
    prev_map = {r.chem_id: r.official_revision_date for r in previous if r.chem_id}
    curr_map = {r.chem_id: r.official_revision_date for r in current if r.chem_id}
    new = tuple(sorted(set(curr_map) - set(prev_map)))
    removed = tuple(sorted(set(prev_map) - set(curr_map)))
    changed = tuple(
        sorted(cid for cid in set(prev_map) & set(curr_map) if prev_map[cid] != curr_map[cid])
    )
    unchanged = tuple(
        sorted(cid for cid in set(prev_map) & set(curr_map) if prev_map[cid] == curr_map[cid])
    )
    return {
        "NEW_CURRENT": new,
        "REMOVED_CURRENT": removed,
        "REVISION_CHANGED": changed,
        "UNCHANGED": unchanged,
    }
