"""KOSHA GUIDE full-set sync — OBJ-KG atomic current promotion.

Source constants are fixed here. Public callers cannot pass callApiId/path.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from services.kr_public_api import kr_get
from services.time import now_kst, serialize_business_datetime

SOURCE_PATH = "koshaguide/getKoshaGuide"
SOURCE_CALL_API_ID = "1050"
SOURCE_HOST = "https://apis.data.go.kr/B552468"
EXPECTED_FIELDS = ("techGdlnNo", "techGdlnNm", "techGdlnOfancYmd", "fileDownloadUrl")
PAGE_SIZE = 100
MAX_PAGES = 500
METADATA_LICENSE = "CLEAR"
ORIGINAL_RIGHTS_MODE = "LINK_ONLY"
BINARY_STORAGE_ALLOWED = False
MED_FIELDS = ("MED_SJ_NM", "MED_URL", "MED_COMPY_DY")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_URL_RE = re.compile(
    r"^https://portal\.kosha\.or\.kr/openapi/v1/file/down/(FL\d+|CTC\d+)/\d+$"
)
_CODE3_RE = re.compile(r"^([A-Z]+)-\d+-\d{4}$")
_CODE4_RE = re.compile(r"^([A-Z]+)-([A-Z]+)-\d+-\d{4}$")

# Official 1-letter labels (KOSHA Guide 길라잡이). 4-part labels stay NULL.
CATEGORY_NAME_BY_CODE = {
    "A": "시료채취·분석",
    "B": "조선·항만",
    "C": "건설",
    "D": "안전설계",
    "E": "전기·계장",
    "F": "화재보호",
    "G": "안전·보건 일반",
    "H": "건강진단·관리",
    "K": "화학공업",
    "M": "기계일반",
    "O": "점검·정비",
    "P": "공정안전",
    "T": "산업독성",
    "W": "작업환경",
    "X": "리스크관리",
}


class GuideSyncError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class NormalizedGuide:
    source_key: str
    title: str
    published_at: str
    original_url: str
    category_code: str
    category_name: Optional[str]
    raw: dict
    content_hash: str
    hold: bool = False
    hold_reason: Optional[str] = None


@dataclass
class SyncResult:
    status: str
    target: str = "guide"
    dry_run: bool = False
    declared: int = 0
    fetched: int = 0
    unique: int = 0
    duplicates: int = 0
    hold_count: int = 0
    membership: int = 0
    snapshot_hash: Optional[str] = None
    snapshot_id: Optional[str] = None
    catalog_upserted: int = 0
    business_dml: int = 0
    schema: str = "techGdln*"
    source_path: str = SOURCE_PATH
    call_api_id: str = SOURCE_CALL_API_ID
    failure_reason: Optional[str] = None
    extra: dict = field(default_factory=dict)


FetchPage = Callable[[int, int], dict]


def _service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or ""
    )


def official_fetch_page(page_no: int, num_of_rows: int = PAGE_SIZE) -> dict:
    """Live GUIDE fetch. callApiId/path are module constants, not arguments."""
    params = {
        "serviceKey": _service_key(),
        "callApiId": SOURCE_CALL_API_ID,
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
    }
    url = f"{SOURCE_HOST}/{SOURCE_PATH}"
    status, text = kr_get(url, params=params, timeout=30)
    if status >= 400:
        raise GuideSyncError("FETCH_HTTP", f"GUIDE fetch HTTP {status}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GuideSyncError("FETCH_PARSE", f"GUIDE response is not JSON: {e}") from e
    return _unwrap_response(data)


def content_hash(guide_no: str, title: str, published_at: str, url: str) -> str:
    payload = "|".join([guide_no, title, published_at, url])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_hash(guides: list[NormalizedGuide]) -> str:
    parts = [
        f"{g.source_key}:{g.content_hash}"
        for g in sorted(guides, key=lambda x: x.source_key)
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def category_code(guide_no: str) -> str:
    m4 = _CODE4_RE.match(guide_no)
    if m4:
        return f"{m4.group(1)}-{m4.group(2)}"
    m3 = _CODE3_RE.match(guide_no)
    if m3:
        return m3.group(1)
    return guide_no.split("-", 1)[0]


def category_name(code: str) -> Optional[str]:
    if code in CATEGORY_NAME_BY_CODE:
        return CATEGORY_NAME_BY_CODE[code]
    return None


def _items_from_body(body: dict) -> list[dict]:
    items = body.get("items")
    if items is None:
        return []
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    if isinstance(items, dict):
        inner = items.get("item", [])
        if isinstance(inner, dict):
            return [inner]
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _unwrap_response(resp: Any) -> dict:
    if isinstance(resp, dict) and isinstance(resp.get("response"), dict):
        return resp["response"]
    if isinstance(resp, dict):
        return resp
    raise GuideSyncError("BAD_RESPONSE", "response is not an object")


def inspect_page(resp: dict, expected_total: Optional[int] = None) -> tuple[int, list[dict]]:
    resp = _unwrap_response(resp)
    header = resp.get("header") or {}
    if str(header.get("resultCode") or "") != "00":
        raise GuideSyncError(
            "RESULT_CODE",
            f"header.resultCode={header.get('resultCode')!r}",
        )
    body = resp.get("body")
    if not isinstance(body, dict) or not body:
        raise GuideSyncError("MISSING_BODY", "empty or missing body")
    if "totalCount" not in body:
        raise GuideSyncError("MISSING_TOTAL", "body.totalCount missing")
    try:
        total = int(body.get("totalCount"))
    except (TypeError, ValueError) as e:
        raise GuideSyncError("BAD_TOTAL", "totalCount is not an integer") from e
    if total <= 0:
        raise GuideSyncError("TOTAL_ZERO", "totalCount=0")
    if expected_total is not None and total != expected_total:
        raise GuideSyncError(
            "TOTAL_DRIFT",
            f"totalCount changed {expected_total} → {total}",
        )
    raw_items = _items_from_body(body)
    if raw_items and any(any(k in it for k in MED_FIELDS) for it in raw_items):
        raise GuideSyncError("WRONG_SOURCE", "MED_* schema (not GUIDE)")
    return total, raw_items


def normalize_item(raw: dict) -> NormalizedGuide:
    if any(k in raw for k in MED_FIELDS):
        raise GuideSyncError("WRONG_SOURCE", "MED_* item")
    missing = [f for f in EXPECTED_FIELDS if f not in raw]
    if missing:
        raise GuideSyncError("SCHEMA", f"missing fields {missing}")
    extra = {k: raw[k] for k in EXPECTED_FIELDS}
    no = str(extra.get("techGdlnNo") or "").strip()
    title = str(extra.get("techGdlnNm") or "").strip()
    published = str(extra.get("techGdlnOfancYmd") or "").strip()
    url = str(extra.get("fileDownloadUrl") or "").strip()
    if not no:
        raise GuideSyncError("MISSING_KEY", "techGdlnNo empty")
    if not title:
        raise GuideSyncError("MISSING_TITLE", f"{no}: title empty")
    if not published:
        raise GuideSyncError("MISSING_DATE", f"{no}: date empty")
    if not _DATE_RE.match(published):
        raise GuideSyncError("INVALID_DATE", f"{no}: date {published!r}")
    if not url:
        raise GuideSyncError("MISSING_URL", f"{no}: url empty")
    hold = False
    hold_reason = None
    if not _URL_RE.match(url):
        hold = True
        hold_reason = "malformed_official_url"
    code = category_code(no)
    return NormalizedGuide(
        source_key=no,
        title=title,
        published_at=published,
        original_url=url,
        category_code=code,
        category_name=category_name(code),
        raw=extra,
        content_hash=content_hash(no, title, published, url),
        hold=hold,
        hold_reason=hold_reason,
    )


def enumerate_full_set(
    fetch_page: FetchPage,
    page_size: int = PAGE_SIZE,
) -> tuple[int, list[dict]]:
    declared = None
    collected: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp = fetch_page(page, page_size)
        total, items = inspect_page(resp, expected_total=declared)
        if declared is None:
            declared = total
        collected.extend(items)
        if len(items) < page_size:
            break
    if declared is None:
        raise GuideSyncError("MISSING_TOTAL", "no page returned totalCount")
    return declared, collected


def validate_full_set(declared: int, raw_items: list[dict]) -> list[NormalizedGuide]:
    if declared <= 0:
        raise GuideSyncError("TOTAL_ZERO", "totalCount=0")
    if len(raw_items) != declared:
        raise GuideSyncError(
            "COUNT_MISMATCH",
            f"fetched={len(raw_items)} declared={declared}",
        )
    guides = [normalize_item(it) for it in raw_items]
    keys = [g.source_key for g in guides]
    unique = set(keys)
    if len(unique) != declared:
        raise GuideSyncError(
            "DUPLICATE_KEY",
            f"unique={len(unique)} declared={declared}",
        )
    return guides


def _iso(now: datetime) -> str:
    return serialize_business_datetime(now)


class MemoryGuideStore:
    """In-memory store for unit tests. Mirrors production mutation points."""

    def __init__(self):
        self.catalog: dict[str, dict] = {}
        self.snapshots: list[dict] = []
        self.items: list[dict] = []
        self.dml = 0
        self.fail_on_membership = False

    def get_latest_completed(self) -> Optional[dict]:
        done = [s for s in self.snapshots if s["status"] == "COMPLETED"]
        if not done:
            return None
        done.sort(key=lambda s: s.get("completed_at") or "", reverse=True)
        return done[0]

    def current_ids(self) -> list[str]:
        latest = self.get_latest_completed()
        if not latest:
            return []
        return [i["guide_id"] for i in self.items if i["snapshot_id"] == latest["id"]]

    def upsert_catalog(self, rows: list[dict]) -> int:
        self.dml += 1
        for row in rows:
            rid = row["id"]
            prev = self.catalog.get(rid, {})
            if "first_seen_at" in prev and prev["first_seen_at"]:
                row = dict(row)
                row["first_seen_at"] = prev["first_seen_at"]
            self.catalog[rid] = row
        return len(rows)

    def insert_running_snapshot(self, row: dict) -> None:
        self.dml += 1
        self.snapshots.append(dict(row))

    def insert_membership(self, rows: list[dict]) -> None:
        if self.fail_on_membership:
            raise GuideSyncError("MEMBERSHIP_WRITE", "forced membership failure")
        self.dml += 1
        self.items.extend(rows)

    def complete_snapshot(self, snapshot_id: str, completed_at: str) -> None:
        self.dml += 1
        for s in self.snapshots:
            if s["id"] == snapshot_id and s["status"] == "RUNNING":
                s["status"] = "COMPLETED"
                s["completed_at"] = completed_at
                return
        raise GuideSyncError("SNAPSHOT_STATE", "RUNNING snapshot not found")

    def fail_snapshot(self, snapshot_id: str, reason: str, completed_at: str) -> None:
        self.dml += 1
        for s in self.snapshots:
            if s["id"] == snapshot_id:
                s["status"] = "FAILED"
                s["failure_reason"] = reason
                s["completed_at"] = completed_at
                return


class SupabaseGuideStore:
    def __init__(self, sb: Any):
        self.sb = sb

    def get_latest_completed(self) -> Optional[dict]:
        r = (
            self.sb.table("kosha_guide_snapshots")
            .select("*")
            .eq("status", "COMPLETED")
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        data = r.data or []
        return data[0] if data else None

    def upsert_catalog(self, rows: list[dict]) -> int:
        existing = {}
        ids = [r["id"] for r in rows]
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            got = (
                self.sb.table("kosha_guide")
                .select("id,first_seen_at")
                .in_("id", chunk)
                .execute()
            )
            for row in got.data or []:
                existing[row["id"]] = row.get("first_seen_at")
        payload = []
        for row in rows:
            item = dict(row)
            if existing.get(item["id"]):
                item["first_seen_at"] = existing[item["id"]]
            payload.append(item)
        for i in range(0, len(payload), 100):
            self.sb.table("kosha_guide").upsert(
                payload[i : i + 100], on_conflict="id"
            ).execute()
        return len(payload)

    def insert_running_snapshot(self, row: dict) -> None:
        self.sb.table("kosha_guide_snapshots").insert(row).execute()

    def insert_membership(self, rows: list[dict]) -> None:
        for i in range(0, len(rows), 200):
            self.sb.table("kosha_guide_snapshot_items").insert(
                rows[i : i + 200]
            ).execute()

    def complete_snapshot(self, snapshot_id: str, completed_at: str) -> None:
        self.sb.table("kosha_guide_snapshots").update(
            {"status": "COMPLETED", "completed_at": completed_at}
        ).eq("id", snapshot_id).eq("status", "RUNNING").execute()

    def fail_snapshot(self, snapshot_id: str, reason: str, completed_at: str) -> None:
        self.sb.table("kosha_guide_snapshots").update(
            {
                "status": "FAILED",
                "failure_reason": reason[:500],
                "completed_at": completed_at,
            }
        ).eq("id", snapshot_id).execute()


def _catalog_row(g: NormalizedGuide, now_s: str) -> dict:
    return {
        "id": g.source_key,
        "guide_no": g.source_key,
        "guide_title": g.title,
        "guide_url": g.original_url,
        "regist_date": g.published_at,
        "raw_json": g.raw,
        "collected_at": now_s,
        "category_code": g.category_code,
        "category_name": g.category_name,
        "content_hash": g.content_hash,
        "first_seen_at": now_s,
        "last_seen_at": now_s,
        "metadata_license": METADATA_LICENSE,
        "original_rights_mode": ORIGINAL_RIGHTS_MODE,
        "binary_storage_allowed": BINARY_STORAGE_ALLOWED,
    }


def sync_kosha_guides(
    *,
    dry_run: bool = False,
    fetch_page: Optional[FetchPage] = None,
    store: Any = None,
    now: Optional[datetime] = None,
    page_size: int = PAGE_SIZE,
) -> SyncResult:
    """Enumerate the full GUIDE set, then promote current only if complete.

    fetch_page is a test hook. Production uses official_fetch_page (1050 fixed).
    """
    clock = now or now_kst()
    now_s = _iso(clock)
    fetcher = fetch_page or official_fetch_page
    try:
        declared, raw_items = enumerate_full_set(fetcher, page_size=page_size)
        guides = validate_full_set(declared, raw_items)
    except GuideSyncError as e:
        return SyncResult(
            status="REJECT" if e.code in {
                "WRONG_SOURCE", "MISSING_BODY", "TOTAL_ZERO", "SCHEMA",
                "MISSING_KEY", "MISSING_TITLE", "MISSING_DATE", "MISSING_URL",
                "INVALID_DATE", "RESULT_CODE", "FETCH_HTTP", "FETCH_PARSE",
                "BAD_RESPONSE", "MISSING_TOTAL", "BAD_TOTAL",
            } else "FAILED",
            dry_run=dry_run,
            business_dml=0,
            failure_reason=f"{e.code}: {e.message}",
            extra={"error_code": e.code},
        )

    current_guides = [g for g in guides if not g.hold]
    snap_hash = snapshot_hash(current_guides)
    result = SyncResult(
        status="VALIDATED",
        dry_run=dry_run,
        declared=declared,
        fetched=len(guides),
        unique=len(guides),
        duplicates=0,
        hold_count=sum(1 for g in guides if g.hold),
        membership=len(current_guides),
        snapshot_hash=snap_hash,
        business_dml=0,
        extra={"wrong_source_guard": "PASS", "schema": "techGdln*"},
    )
    if dry_run:
        result.status = "DRY_RUN"
        return result

    if store is None:
        from db.supabase_client import get_supabase
        store = SupabaseGuideStore(get_supabase())

    latest = store.get_latest_completed()
    if latest and latest.get("snapshot_hash") == snap_hash:
        result.status = "SNAPSHOT_NO_CHANGE"
        result.snapshot_id = latest.get("id")
        result.business_dml = 0
        return result

    snapshot_id = str(uuid.uuid4())
    running = {
        "id": snapshot_id,
        "status": "RUNNING",
        "source_path": SOURCE_PATH,
        "call_api_id": SOURCE_CALL_API_ID,
        "declared_total": declared,
        "fetched_count": len(guides),
        "unique_count": len(guides),
        "snapshot_hash": snap_hash,
        "started_at": now_s,
        "completed_at": None,
        "failure_reason": None,
    }
    try:
        catalog_n = store.upsert_catalog([_catalog_row(g, now_s) for g in guides])
        store.insert_running_snapshot(running)
        store.insert_membership(
            [
                {
                    "snapshot_id": snapshot_id,
                    "guide_id": g.source_key,
                    "content_hash": g.content_hash,
                }
                for g in current_guides
            ]
        )
        store.complete_snapshot(snapshot_id, now_s)
    except Exception as e:
        try:
            store.fail_snapshot(snapshot_id, str(e), now_s)
        except Exception:
            pass
        result.status = "FAILED"
        result.snapshot_id = snapshot_id
        result.failure_reason = str(e)[:500]
        result.business_dml = getattr(store, "dml", 1)
        result.extra["previous_completed_preserved"] = True
        return result

    result.status = "COMPLETED"
    result.snapshot_id = snapshot_id
    result.catalog_upserted = catalog_n
    result.business_dml = getattr(store, "dml", 1)
    return result
