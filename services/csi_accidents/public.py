"""CSI public read model. READY current rows only. No anon table access."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from services.csi_accidents.contract import DATASET_URL
from services.knowledge_graph_svc import TAI_ORIGIN

SOURCE_NAME = "국토안전관리원(CSI)"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_Q_LEN = 80
SEARCH_FIELDS = (
    "title",
    "summary",
    "construction_type",
    "process_major",
    "process_minor",
    "work_process",
    "object_major",
    "object_minor",
    "accident_type_major",
    "accident_type",
    "cause_major",
    "cause_mid",
    "cause_minor",
    "cause_detail",
)
FORBIDDEN_PUBLIC_FIELDS = frozenset(
    {
        "raw_json",
        "identity_fingerprint",
        "identity_reason",
        "source_content_hash",
        "snapshot_id",
        "row_number",
        "user_id",
        "company_id",
        "factory_id",
        "diagnosis_id",
        "file_sha256",
    }
)
PUBLIC_COLUMNS = (
    "content_id,title,summary,occurred_at,construction_type,process_major,"
    "process_minor,object_major,object_minor,work_process,accident_type_major,"
    "accident_type,cause_major,cause_mid,cause_minor,cause_detail,death_count,"
    "injury_count,source_dataset_url,source_item_url,identity_status"
)
_Q_OK = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s\-]*$")


class PublicCsiQueryError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sanitize_q(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    q = raw.strip()
    if q == "":
        return None
    if len(q) > MAX_Q_LEN:
        raise PublicCsiQueryError("Q_TOO_LONG")
    if not _Q_OK.fullmatch(q):
        raise PublicCsiQueryError("Q_INVALID")
    return q


def content_id_from_uuid(case_uuid: str) -> str:
    try:
        parsed = uuid.UUID(str(case_uuid).strip())
    except (ValueError, AttributeError, TypeError) as e:
        raise PublicCsiQueryError("UUID_INVALID") from e
    return f"CSI:{parsed}"


def csi_tai_url(content_id: str) -> str:
    uuid_part = content_id.split("CSI:", 1)[-1]
    return f"{TAI_ORIGIN}/accident/csi/{uuid_part}"


def public_item(row: dict[str, Any]) -> dict[str, Any]:
    cid = str(row.get("content_id") or "")
    item = {
        "content_type": "ACCIDENT",
        "content_id": cid,
        "source_id": "CSI",
        "source_name": SOURCE_NAME,
        "title": row.get("title"),
        "summary": row.get("summary"),
        "occurred_at": row.get("occurred_at"),
        "construction_type": row.get("construction_type"),
        "process_major": row.get("process_major"),
        "process_minor": row.get("process_minor"),
        "object_major": row.get("object_major"),
        "object_minor": row.get("object_minor"),
        "work_process": row.get("work_process"),
        "accident_type_major": row.get("accident_type_major"),
        "accident_type": row.get("accident_type"),
        "cause_major": row.get("cause_major"),
        "cause_mid": row.get("cause_mid"),
        "cause_minor": row.get("cause_minor"),
        "cause_detail": row.get("cause_detail"),
        "death_count": row.get("death_count"),
        "injury_count": row.get("injury_count"),
        "source_dataset_url": row.get("source_dataset_url") or DATASET_URL,
        "source_item_url": None,
        "tai_url": csi_tai_url(cid),
    }
    for banned in FORBIDDEN_PUBLIC_FIELDS:
        item.pop(banned, None)
    return item


def _ready(row: dict) -> bool:
    return str(row.get("identity_status") or "") == "READY"


def _matches_q(row: dict, q: str) -> bool:
    needle = q.casefold()
    for field in SEARCH_FIELDS:
        val = row.get(field)
        if val is not None and needle in str(val).casefold():
            return True
    return False


def escape_ilike(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace(",", " ")


@dataclass
class ListResult:
    items: list[dict]
    page: int
    page_size: int
    total: int


class MemoryCsiPublicStore:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = list(rows or [])
        self.fetched_unbounded = False
        self.writes = 0

    def list_ready(self, *, q: Optional[str], page: int, page_size: int) -> ListResult:
        ready = [r for r in self.rows if _ready(r)]
        if q:
            ready = [r for r in ready if _matches_q(r, q)]
        ready.sort(key=lambda r: str(r.get("content_id") or ""))
        ready.sort(key=lambda r: r.get("occurred_at") or "", reverse=True)
        total = len(ready)
        start = (page - 1) * page_size
        end = start + page_size
        sliced = ready[start:end]
        return ListResult(items=[public_item(r) for r in sliced], page=page, page_size=page_size, total=total)

    def get_ready(self, content_id: str) -> Optional[dict]:
        for row in self.rows:
            if row.get("content_id") == content_id and _ready(row):
                return public_item(row)
        return None


class SupabaseCsiPublicStore:
    def __init__(self, sb: Any):
        self.sb = sb

    def list_ready(self, *, q: Optional[str], page: int, page_size: int) -> ListResult:
        start = (page - 1) * page_size
        end = start + page_size - 1
        query = (
            self.sb.table("csi_accident_current")
            .select(PUBLIC_COLUMNS, count="exact")
            .eq("identity_status", "READY")
            .order("occurred_at", desc=True)
            .order("content_id")
        )
        if q:
            safe = escape_ilike(sanitize_q(q) or "")
            clause = ",".join(f"{field}.ilike.%{safe}%" for field in SEARCH_FIELDS)
            query = query.or_(clause)
        resp = query.range(start, end).execute()
        rows = list(resp.data or [])
        total = int(getattr(resp, "count", None) or len(rows))
        return ListResult(
            items=[public_item(r) for r in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_ready(self, content_id: str) -> Optional[dict]:
        resp = (
            self.sb.table("csi_accident_current")
            .select(PUBLIC_COLUMNS)
            .eq("content_id", content_id)
            .eq("identity_status", "READY")
            .limit(1)
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            return None
        return public_item(rows[0])


def list_public_accidents(store, *, q: Optional[str] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    if page < 1:
        raise PublicCsiQueryError("PAGE_INVALID")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise PublicCsiQueryError("PAGE_SIZE_INVALID")
    term = sanitize_q(q)
    result = store.list_ready(q=term, page=page, page_size=page_size)
    return {
        "items": result.items,
        "page": result.page,
        "page_size": result.page_size,
        "total": result.total,
        "content_type": "ACCIDENT",
        "source_id": "CSI",
    }


def get_public_accident(store, case_uuid: str) -> dict:
    content_id = content_id_from_uuid(case_uuid)
    item = store.get_ready(content_id)
    if item is None:
        raise PublicCsiQueryError("NOT_FOUND")
    return item
