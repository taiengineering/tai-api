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
# Legacy [^']* on chemName drops rows whose name contains an apostrophe (2,2'-PCB …).
LEGACY_SELECT_RE = re.compile(r"selectChem\('([^']*)','([^']*)','([^']*)'\)")
SELECT_RE = re.compile(r"selectChem\('([^']*)','([^']*)','(.*?)'\)", re.S)
HREF_SELECT_RE = re.compile(r"javascript:selectChem\(", re.I)
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)


def clean_cell(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).replace("\u000d", " ").replace("_x000D_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


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


@dataclass(frozen=True)
class ListPageStats:
    header_total: int
    page_no: int
    page_count: int
    parsed_selectchem: int
    legacy_selectchem: int
    href_selectchem: int
    data_tr: int
    data_tr_without_selectchem: int

    @property
    def apostrophe_name_recovered(self) -> int:
        return max(0, self.parsed_selectchem - self.legacy_selectchem)

    @property
    def parser_undercount(self) -> int:
        return max(0, self.href_selectchem - self.parsed_selectchem)


def inspect_list_html(html: str) -> ListPageStats:
    header = HEADER_RE.search(html or "")
    if not header:
        raise CurrentIndexError("HEADER_MISSING", "official list header not found")
    total, page_no, page_count = (int(header.group(1)), int(header.group(2)), int(header.group(3)))
    data_tr = 0
    data_tr_without = 0
    for tr in TR_RE.finditer(html or ""):
        inner = tr.group(1)
        if "<th" in inner.lower():
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", inner, re.I | re.S)
        if not tds:
            continue
        data_tr += 1
        if "selectchem(" not in inner.lower():
            data_tr_without += 1
    return ListPageStats(
        header_total=total,
        page_no=page_no,
        page_count=page_count,
        parsed_selectchem=len(SELECT_RE.findall(html or "")),
        legacy_selectchem=len(LEGACY_SELECT_RE.findall(html or "")),
        href_selectchem=len(HREF_SELECT_RE.findall(html or "")),
        data_tr=data_tr,
        data_tr_without_selectchem=data_tr_without,
    )


def parse_list_html(html: str, *, page: int) -> tuple[list[OfficialCurrentRow], int, int, int]:
    header = HEADER_RE.search(html or "")
    if not header:
        raise CurrentIndexError("HEADER_MISSING", "official list header not found")
    total, page_no, page_count = (int(header.group(1)), int(header.group(2)), int(header.group(3)))
    rows: list[OfficialCurrentRow] = []
    for match in SELECT_RE.finditer(html or ""):
        chem_id = normalize_chem_id(match.group(1))
        cas = clean_cell(match.group(2))
        name = clean_cell(match.group(3))
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


OBSERVED_NON_LAST_PAGE_ROWS = 10  # live default row count; not a guessed pageSize query param


def rewrite_current_index(path: Path, rows: list[OfficialCurrentRow]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row.as_row(), ensure_ascii=False) + "\n")
    tmp.replace(path)


def repair_short_pages(
    *,
    dest: Path,
    get_fn: Optional[GetFn] = None,
    delay_s: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    log_progress: bool = False,
) -> dict[str, object]:
    """Refetch pages whose parsed row count is below the observed non-last page size."""
    fetch = get_fn or default_get
    existing = load_current_rows(dest)
    if not existing:
        raise CurrentIndexError("EMPTY_INDEX", f"no rows in {dest}")
    by_page: dict[int, list[OfficialCurrentRow]] = {}
    for row in existing:
        by_page.setdefault(row.official_page, []).append(row)
    last_page = max(by_page)
    url = f"{KOSHA_WEB_HOST}{KOSHA_WEB_LIST_PATH}"
    repaired: list[int] = []
    added = 0
    for page in sorted(by_page):
        if page == last_page:
            continue
        if len(by_page[page]) >= OBSERVED_NON_LAST_PAGE_ROWS:
            continue
        if delay_s:
            sleep_fn(delay_s)
        status, body = fetch(url, {"pageIndex": str(page), "listType": KOSHA_WEB_LIST_TYPE})
        block = detect_access_block(status, body)
        if block:
            raise CurrentIndexError(block, f"STOP at page {page}")
        page_rows, header_total, got_page, page_count = parse_list_html(body, page=page)
        if got_page != page:
            raise CurrentIndexError("PAGE_MISMATCH", f"expected page {page}, got {got_page}")
        stats = inspect_list_html(body)
        if log_progress:
            print(
                f"REPAIR page={page} before={len(by_page[page])} after={len(page_rows)} href={stats.href_selectchem}",
                flush=True,
            )
        added += len(page_rows) - len(by_page[page])
        by_page[page] = page_rows
        repaired.append(page)
    ordered: list[OfficialCurrentRow] = []
    for page in sorted(by_page):
        ordered.extend(by_page[page])
    rewrite_current_index(dest, ordered)
    unique_ids = [r.chem_id for r in ordered if r.chem_id]
    return {
        "pages_repaired": repaired,
        "pages_repaired_n": len(repaired),
        "rows_added": added,
        "row_count": len(ordered),
        "unique_chem_id": len(set(unique_ids)),
        "last_page": last_page,
        "last_page_rows": len(by_page[last_page]),
        "artifact_path": str(dest),
        "written_at": serialize_external_utc(now_kst()),
    }


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
    first_stats = inspect_list_html(first_body)
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
    diag = {
        "href_selectchem": 0,
        "legacy_selectchem": 0,
        "parsed_selectchem": 0,
        "data_tr": 0,
        "data_tr_without_selectchem": 0,
        "apostrophe_name_recovered": 0,
        "pages_inspected": 0,
    }

    def _add_stats(stats: ListPageStats) -> None:
        diag["href_selectchem"] += stats.href_selectchem
        diag["legacy_selectchem"] += stats.legacy_selectchem
        diag["parsed_selectchem"] += stats.parsed_selectchem
        diag["data_tr"] += stats.data_tr
        diag["data_tr_without_selectchem"] += stats.data_tr_without_selectchem
        diag["apostrophe_name_recovered"] += stats.apostrophe_name_recovered
        diag["pages_inspected"] += 1

    if start_page <= 1:
        _add_stats(first_stats)
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
                    _add_stats(inspect_list_html(body))
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
    parsed = len(all_rows)
    header_delta = total - parsed if total else None
    if parsed == total:
        gap_class = "HEADER_MATCH"
    elif diag["data_tr_without_selectchem"] > 0:
        gap_class = "NO_SELECTCHEM_DISPLAY_ROWS"
    elif diag["apostrophe_name_recovered"] > 0 and diag["href_selectchem"] == diag["parsed_selectchem"]:
        gap_class = "PARSER_APOSTROPHE_NAME"
    elif diag["parsed_selectchem"] < diag["href_selectchem"]:
        gap_class = "PARSER_UNDERCOUNT"
    elif diag["href_selectchem"] == diag["parsed_selectchem"] and header_delta:
        gap_class = "HEADER_VS_SELECTCHEM_MISMATCH"
    else:
        gap_class = "UNEXPLAINED"
    return {
        "row_count": parsed,
        "header_total": total,
        "header_delta": header_delta,
        "page_count": last_page,
        "unique_cas": len(set(cas_values)),
        "cas_null": sum(1 for r in all_rows if not r.official_cas),
        "duplicate_cas": len(cas_values) - len(set(cas_values)),
        "direct_official_id": len(unique_ids),
        "unique_chem_id": len(set(unique_ids)),
        "href_selectchem": diag["href_selectchem"],
        "legacy_selectchem": diag["legacy_selectchem"],
        "data_tr": diag["data_tr"],
        "data_tr_without_selectchem": diag["data_tr_without_selectchem"],
        "apostrophe_name_recovered": diag["apostrophe_name_recovered"],
        "pages_inspected": diag["pages_inspected"],
        "gap_classification": gap_class,
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
