"""KOSHA safety-material current snapshot sync.

WO-SAFETY-LIBRARY-001 WP-1C-4A.

Production current = latest COMPLETED snapshot membership.
Catalog write = CURRENT_NEW insert only. No historical mutation, no enrichment.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Tuple

from services.time import now_kst

SOURCE_PROVIDER = "KOSHA"
SOURCE_DATASET = "selectMediaList01"
SOURCE_CALL_API_ID = "1030"
PAGE_SIZE = 100
MAX_PAGES = 500
CATALOG_TABLE = "kosha_safety_materials"
SNAPSHOT_TABLE = "kosha_safety_material_snapshots"
ITEM_TABLE = "kosha_safety_material_snapshot_items"

VALID_MEDSEQ = "VALID_MEDSEQ"
MISSING_MEDSEQ = "MISSING_MEDSEQ"
INVALID_MEDSEQ = "INVALID_MEDSEQ"

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

RESULT_COMPLETED = "COMPLETED"
RESULT_FAILED = "FAILED"
RESULT_NO_CHANGE = "SNAPSHOT_NO_CHANGE"
RESULT_REJECTED = "REJECTED"
RESULT_DRY_RUN = "DRY_RUN"

GUARD_TABLES = (
    CATALOG_TABLE,
    SNAPSHOT_TABLE,
    ITEM_TABLE,
    "kosha_safety_material_details",
    "kosha_safety_material_assets",
    "kosha_safety_material_asset_versions",
)

_MEDSEQ_RE = re.compile(r"(?:^|[?&])medSeq=([^&#]*)", re.I)
_WS_RE = re.compile(r"\s+")

# routers/kosha_collect.py v1.5.0 과 동일. 복제하지 말고 여기만 유지.
_CATEGORY_RULES: list[Tuple[str, str]] = [
    (r"(외국인|다문화|foreign)", "FOREIGN"),
    (r"\((몽골|라오스|미얀마|캄보디아|키르기스|네팔|태국|베트남|중국|우즈베|필리핀|인도네|파키스|방글라|스리랑카|티모르|영어|일본|러시아)", "FOREIGN"),
    (r"(VR|메타버스|HMD용|동영상|숙폼|현장르포|당신의 선택|UCC)", "VIDEO_VR"),
    (r"(SIF 교안|SIF교안|\(교안\)|교재|교육과정|위탁과정|교육프로그램|관리자용|이러닝|e-learning)", "EDUCATION"),
    (r"(OPL|스토리텔링|사고사례|재해사례|재해예방 OPS|\[OPS\])", "CASE_STUDY"),
    (r"(포스터|스티커|픽토그램|안전보건표지|리플릿|리플렛|브로슈어|홍보물|배너|현수막)", "POSTER"),
    (r"(가이드|GUIDE|guide|매뉴얼|manual|안전수칙|작업절차|바로알기|편람)", "GUIDE"),
    (r"(체크리스트|점검표|자율점검)", "CHECKLIST"),
    (r"(연구|보고서|논문|학술|조사|분석|평가|검토|통계|현황|연보|연감|요약집)", "RESEARCH"),
    (r"(건강|보건|검진|직업병|질환|화학물질|유해물질|MSDS|작업환경|소음|분진|석면)", "HEALTH"),
    (r"(법령|규정|고시|시행령|시행규칙)", "REGULATION"),
    (r"(교육|교안|학습)", "EDUCATION"),
    (r"(사고|사례|재해|재해예방)", "CASE_STUDY"),
]

_SECTOR_RULES: list[Tuple[str, str]] = [
    (r"(건설|건설업|건설현장|콘크리트|타워크레인|비계|거푸집|굴착|항타|갱폼|공사)", "CONSTRUCTION"),
    (r"(제조|제조업|프레스|선반|절단기|용접|사출|전단기|절곡기|컨베이어|크레인|지게차|보일러|압력용기)", "MANUFACTURING"),
    (r"(서비스|배달|이륨차|물류|운반|운송|택배|청소|조리)", "SERVICE"),
]

FetchPage = Callable[[int], Awaitable[tuple[list[dict], Optional[int]]]]


def kosha_service_key() -> str:
    """KOSHA/data.go.kr only. BUILDING_API_KEY 는 사용하지 않는다."""
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or ""
    )


def make_id(prefix: str, *parts) -> str:
    raw = "|".join(str(p) for p in parts if p)
    if raw:
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"{prefix}_{now_kst().strftime('%Y%m%d%H%M%S')}"


def classify_material(title: str) -> Tuple[str, str]:
    """제목 기반 카테고리 + 업종. Returns (category, sector_value).

    Live DB column for the sector value is industry_category, not sector.
    """
    t = title or ""
    category = "OTHER"
    sector = "COMMON"
    for pattern, cat in _CATEGORY_RULES:
        if re.search(pattern, t):
            category = cat
            break
    for pattern, sec in _SECTOR_RULES:
        if re.search(pattern, t):
            sector = sec
            break
    return category, sector


def catalog_identity(url: str, title: str, raw: Optional[dict] = None) -> str:
    """기존 _collect_safety_materials ID 규칙과 동일."""
    raw = raw or {}
    rid = raw.get("mediaId") or raw.get("MED_SEQ")
    if rid:
        return str(rid)
    return make_id("mat", url, title)


def extract_medseq(url: str | None) -> tuple[str | None, str]:
    if not url or not str(url).strip():
        return None, MISSING_MEDSEQ
    m = _MEDSEQ_RE.search(str(url))
    if not m:
        return None, MISSING_MEDSEQ
    raw = (m.group(1) or "").strip()
    if not raw:
        return None, INVALID_MEDSEQ
    if raw.isdigit():
        return str(int(raw)), VALID_MEDSEQ
    return raw, INVALID_MEDSEQ


def normalize_title(title: str | None) -> str:
    return _WS_RE.sub(" ", (title or "").strip())


def parse_item_date(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().replace("/", "-")
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    if len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return None


def media_list_params(page_no: int, num_of_rows: int = PAGE_SIZE) -> dict:
    return {"callApiId": SOURCE_CALL_API_ID, "pageNo": page_no, "numOfRows": num_of_rows}


def catalog_row_from_official(raw: dict) -> dict:
    """Live kosha_safety_materials columns. sector 키를 쓰지 않는다."""
    title = raw.get("MED_SJ_NM") or raw.get("title") or raw.get("mediaTitle") or ""
    url = raw.get("MED_URL") or raw.get("url") or raw.get("mediaUrl") or ""
    category, sector = classify_material(title)
    return {
        "id": catalog_identity(url, title, raw),
        "title": title,
        "product_type": raw.get("productType") or raw.get("MED_CL_NM") or "",
        "industry": raw.get("industry") or "",
        "accident_type": raw.get("accidentType") or "",
        "url": url,
        "category": category,
        "industry_category": sector,
        "raw_json": raw,
    }


def snapshot_hash(items: list[dict]) -> str:
    rows = []
    for it in items:
        rows.append({
            "source_med_seq": str(it["source_med_seq"]),
            "MED_URL": it.get("MED_URL") or it.get("url") or "",
            "MED_COMPY_DY": it.get("MED_COMPY_DY") or "",
            "MED_SJ_NM": it.get("MED_SJ_NM") or it.get("title") or "",
        })
    def _sort_key(r: dict) -> tuple:
        seq = r["source_med_seq"]
        if seq.isdigit():
            return (0, int(seq))
        return (1, seq)
    rows.sort(key=_sort_key)
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for r in rows
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class NormalizedOfficial:
    raw: dict
    url: str
    title: str
    medseq: Optional[str]
    medseq_status: str
    date: Optional[str]
    published_raw: str
    catalog_id: str
    category: str
    industry_category: str

    def hash_row(self) -> dict:
        return {
            "source_med_seq": self.medseq or "",
            "MED_URL": self.url,
            "MED_COMPY_DY": self.published_raw,
            "MED_SJ_NM": self.title,
        }


def normalize_official_item(raw: dict) -> NormalizedOfficial:
    title = raw.get("MED_SJ_NM") or raw.get("title") or raw.get("mediaTitle") or ""
    url = raw.get("MED_URL") or raw.get("url") or raw.get("mediaUrl") or ""
    url = str(url).strip() if url is not None else ""
    title = "" if title is None else str(title)
    published_raw = raw.get("MED_COMPY_DY")
    if published_raw is None:
        published_raw = raw.get("date") or ""
    published_raw = "" if published_raw is None else str(published_raw)
    medseq, status = extract_medseq(url)
    category, sector = classify_material(title)
    return NormalizedOfficial(
        raw=raw,
        url=url,
        title=title,
        medseq=medseq,
        medseq_status=status,
        date=parse_item_date(published_raw),
        published_raw=published_raw,
        catalog_id=catalog_identity(url, title, raw),
        category=category,
        industry_category=sector,
    )


def normalize_db_row(row: dict) -> dict:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    url = (row.get("url") or raw.get("MED_URL") or "") or ""
    url = str(url).strip()
    title = row.get("title")
    if title is None:
        title = raw.get("MED_SJ_NM") or ""
    title = str(title)
    date = parse_item_date(raw.get("MED_COMPY_DY"))
    medseq, medseq_status = extract_medseq(url)
    return {
        "id": row.get("id"),
        "url": url,
        "title": title,
        "norm_title": normalize_title(title),
        "date": date,
        "medseq": medseq,
        "medseq_status": medseq_status,
        "category": row.get("category"),
        "industry_category": row.get("industry_category"),
        "collected_at": row.get("collected_at"),
    }


def _unique_by_url(items: list[dict]) -> tuple[list[dict], int]:
    seen: dict[str, dict] = {}
    dup = 0
    order: list[dict] = []
    for it in items:
        url = it.get("url") or ""
        if not url:
            order.append(it)
            continue
        if url in seen:
            dup += 1
            continue
        seen[url] = it
        order.append(it)
    return order, dup


def classify_sets(official_items: list[dict], db_rows: list[dict]) -> dict:
    official_unique, official_dup_urls = _unique_by_url(official_items)
    db_unique, db_dup_urls = _unique_by_url(db_rows)

    db_urls = {r["url"] for r in db_unique if r.get("url")}
    db_medseqs: dict[str, list[dict]] = defaultdict(list)
    for r in db_unique:
        if r.get("medseq_status") == VALID_MEDSEQ and r.get("medseq"):
            db_medseqs[r["medseq"]].append(r)
    db_medseq_set = set(db_medseqs)

    official_urls = {r["url"] for r in official_unique if r.get("url")}
    official_medseqs: dict[str, list[dict]] = defaultdict(list)
    for r in official_unique:
        if r.get("medseq_status") == VALID_MEDSEQ and r.get("medseq"):
            official_medseqs[r["medseq"]].append(r)
    official_medseq_set = set(official_medseqs)

    current_existing: list[dict] = []
    current_new: list[dict] = []
    for it in official_unique:
        by_url = bool(it.get("url") and it["url"] in db_urls)
        by_med = bool(it.get("medseq") and it["medseq"] in db_medseq_set)
        if by_url or by_med:
            current_existing.append(it)
        else:
            current_new.append(it)

    still_current: list[dict] = []
    historical: list[dict] = []
    for r in db_unique:
        by_url = bool(r.get("url") and r["url"] in official_urls)
        by_med = bool(r.get("medseq") and r["medseq"] in official_medseq_set)
        if by_url or by_med:
            still_current.append(r)
        else:
            historical.append(r)

    db_title_date: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in db_unique:
        if r.get("norm_title") and r.get("date"):
            db_title_date[(r["norm_title"], r["date"])].append(r)

    possible: list[dict] = []
    ambiguous_title_date: list[dict] = []
    for it in current_new:
        if not it.get("norm_title") or not it.get("date"):
            continue
        hits = db_title_date.get((it["norm_title"], it["date"])) or []
        if not hits:
            continue
        rec = {"official": it, "db_hits": hits}
        if len(hits) == 1:
            possible.append(rec)
        else:
            ambiguous_title_date.append(rec)

    blocked_urls = set()
    for rec in possible + ambiguous_title_date:
        u = (rec["official"] or {}).get("url")
        if u:
            blocked_urls.add(u)

    current_new_exact = [it for it in current_new if it.get("url") not in blocked_urls]

    return {
        "official_fetched": len(official_items),
        "official_unique": len(official_unique),
        "official_dup_urls": official_dup_urls,
        "current_existing": current_existing,
        "current_new": current_new,
        "current_new_exact": current_new_exact,
        "historical_not_current": historical,
        "still_current_db": still_current,
        "possible_id_or_url_change": possible,
        "ambiguous_title_date": ambiguous_title_date,
        "db_unique_url": len(db_unique),
        "db_dup_urls": db_dup_urls,
        "official_partition": len(current_existing) + len(current_new) == len(official_unique),
        "db_partition": len(still_current) + len(historical) == len(db_unique),
    }


def validate_complete(
    declared_total: Optional[int],
    fetched: list[NormalizedOfficial],
) -> dict:
    fetched_count = len(fetched)
    seqs = [it.medseq for it in fetched if it.medseq_status == VALID_MEDSEQ]
    seq_counts = Counter(seqs)
    unique_count = len(seq_counts)
    duplicate_count = sum(n - 1 for n in seq_counts.values() if n > 1)
    invalid_count = sum(1 for it in fetched if it.medseq_status != VALID_MEDSEQ)
    reasons = []
    if declared_total is None:
        reasons.append("DECLARED_TOTAL_MISSING")
    elif declared_total != fetched_count:
        reasons.append("DECLARED_FETCHED_MISMATCH")
    if fetched_count != unique_count:
        reasons.append("FETCHED_UNIQUE_MISMATCH")
    if duplicate_count != 0:
        reasons.append("DUPLICATE_MEDSEQ")
    if invalid_count != 0:
        reasons.append("INVALID_MEDSEQ")
    return {
        "ok": not reasons,
        "declared_total": declared_total,
        "fetched_count": fetched_count,
        "unique_count": unique_count,
        "duplicate_count": duplicate_count,
        "invalid_count": invalid_count,
        "reasons": reasons,
    }


class MemorySnapshotStore:
    """Unit-test store. No network."""

    def __init__(self, catalog: Optional[list[dict]] = None, extra_counts: Optional[dict] = None):
        self.catalog: dict[str, dict] = {r["id"]: dict(r) for r in (catalog or [])}
        self.snapshots: list[dict] = []
        self.items: list[dict] = []
        self.extra_counts = extra_counts or {
            "kosha_safety_material_details": 20,
            "kosha_safety_material_assets": 73,
            "kosha_safety_material_asset_versions": 2,
        }
        self.mutations = Counter()
        self.catalog_updates = 0
        self.catalog_deletes = 0

    def counts(self) -> dict[str, int]:
        return {
            CATALOG_TABLE: len(self.catalog),
            SNAPSHOT_TABLE: len(self.snapshots),
            ITEM_TABLE: len(self.items),
            "kosha_safety_material_details": int(self.extra_counts.get("kosha_safety_material_details", 0)),
            "kosha_safety_material_assets": int(self.extra_counts.get("kosha_safety_material_assets", 0)),
            "kosha_safety_material_asset_versions": int(self.extra_counts.get("kosha_safety_material_asset_versions", 0)),
        }

    def load_catalog(self) -> list[dict]:
        return [dict(v) for v in self.catalog.values()]

    def latest_completed(self) -> Optional[dict]:
        done = [s for s in self.snapshots if s.get("status") == STATUS_COMPLETED]
        if not done:
            return None
        done.sort(key=lambda s: s.get("completed_at") or "", reverse=True)
        return dict(done[0])

    def insert_snapshot_running(self, row: dict) -> str:
        sid = row.get("id") or str(uuid.uuid4())
        rec = dict(row)
        rec["id"] = sid
        rec["status"] = STATUS_RUNNING
        self.snapshots.append(rec)
        self.mutations["snapshots"] += 1
        return sid

    def update_snapshot(self, snapshot_id: str, fields: dict) -> None:
        for s in self.snapshots:
            if s["id"] == snapshot_id:
                s.update(fields)
                self.mutations["snapshot_updates"] += 1
                return
        raise KeyError(snapshot_id)

    def insert_catalog_rows(self, rows: list[dict]) -> int:
        n = 0
        for row in rows:
            rid = row["id"]
            if rid in self.catalog:
                continue
            self.catalog[rid] = dict(row)
            n += 1
        self.mutations["catalog_inserts"] += n
        return n

    def insert_membership(self, snapshot_id: str, items: list[dict]) -> int:
        n = 0
        for it in items:
            rec = dict(it)
            rec["snapshot_id"] = snapshot_id
            rec["id"] = len(self.items) + 1
            self.items.append(rec)
            n += 1
        self.mutations["membership_inserts"] += n
        return n

    def count_membership(self, snapshot_id: str) -> int:
        return sum(1 for it in self.items if it.get("snapshot_id") == snapshot_id)


class SupabaseSnapshotStore:
    def __init__(self, sb=None):
        if sb is None:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        self.sb = sb
        self.mutations = Counter()
        self.catalog_updates = 0
        self.catalog_deletes = 0

    def counts(self) -> dict[str, int]:
        out = {}
        for name in GUARD_TABLES:
            try:
                r = self.sb.table(name).select("*", count="exact").limit(1).execute()
                out[name] = int(r.count or 0)
            except Exception:
                out[name] = -1
        return out

    def load_catalog(self) -> list[dict]:
        rows: list[dict] = []
        start = 0
        page = 1000
        cols = "id,title,url,raw_json,category,industry_category,collected_at"
        while True:
            r = (
                self.sb.table(CATALOG_TABLE)
                .select(cols)
                .range(start, start + page - 1)
                .execute()
            )
            batch = r.data or []
            rows.extend(batch)
            if len(batch) < page:
                break
            start += page
        return rows

    def latest_completed(self) -> Optional[dict]:
        r = (
            self.sb.table(SNAPSHOT_TABLE)
            .select("id,snapshot_hash,status,unique_count,completed_at")
            .eq("status", STATUS_COMPLETED)
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
        )
        data = r.data or []
        return dict(data[0]) if data else None

    def insert_snapshot_running(self, row: dict) -> str:
        r = self.sb.table(SNAPSHOT_TABLE).insert(row).execute()
        self.mutations["snapshots"] += 1
        return r.data[0]["id"]

    def update_snapshot(self, snapshot_id: str, fields: dict) -> None:
        self.sb.table(SNAPSHOT_TABLE).update(fields).eq("id", snapshot_id).execute()
        self.mutations["snapshot_updates"] += 1

    def insert_catalog_rows(self, rows: list[dict]) -> int:
        n = 0
        for i in range(0, len(rows), 200):
            chunk = rows[i:i + 200]
            self.sb.table(CATALOG_TABLE).insert(chunk).execute()
            n += len(chunk)
        self.mutations["catalog_inserts"] += n
        return n

    def insert_membership(self, snapshot_id: str, items: list[dict]) -> int:
        n = 0
        payload = []
        for it in items:
            rec = dict(it)
            rec["snapshot_id"] = snapshot_id
            payload.append(rec)
        for i in range(0, len(payload), 200):
            chunk = payload[i:i + 200]
            self.sb.table(ITEM_TABLE).insert(chunk).execute()
            n += len(chunk)
        self.mutations["membership_inserts"] += n
        return n

    def count_membership(self, snapshot_id: str) -> int:
        r = (
            self.sb.table(ITEM_TABLE)
            .select("*", count="exact")
            .eq("snapshot_id", snapshot_id)
            .limit(1)
            .execute()
        )
        return int(r.count or 0)


def _official_as_diff_items(items: list[NormalizedOfficial]) -> list[dict]:
    out = []
    for it in items:
        out.append({
            "url": it.url,
            "title": it.title,
            "norm_title": normalize_title(it.title),
            "date": it.date,
            "medseq": it.medseq,
            "medseq_status": it.medseq_status,
            "catalog_id": it.catalog_id,
            "raw": it.raw,
            "published_raw": it.published_raw,
            "category": it.category,
            "industry_category": it.industry_category,
        })
    return out


def _resolve_material_id(official: dict, db_by_url: dict, db_by_medseq: dict) -> Optional[str]:
    url = official.get("url") or ""
    if url and url in db_by_url:
        return db_by_url[url]["id"]
    med = official.get("medseq")
    if med and med in db_by_medseq:
        return db_by_medseq[med]["id"]
    return official.get("catalog_id")


def _diff_summary(diff: dict) -> dict:
    return {
        "current_existing": len(diff["current_existing"]),
        "current_new": len(diff["current_new"]),
        "current_new_exact": len(diff["current_new_exact"]),
        "historical": len(diff["historical_not_current"]),
        "possible": len(diff["possible_id_or_url_change"]),
        "ambiguous": len(diff["ambiguous_title_date"]),
    }


async def fetch_official_full(
    fetch_page: FetchPage,
    *,
    start_page: int = 1,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
) -> dict:
    if start_page != 1:
        return {
            "ok": False,
            "status": RESULT_REJECTED,
            "failure_reason": "SNAPSHOT_REQUIRES_START_PAGE_1",
            "items": [],
            "declared_total": None,
        }
    all_items: list[dict] = []
    declared: Optional[int] = None
    for page in range(1, max_pages + 1):
        items, total = await fetch_page(page)
        if items:
            if declared is None and total is not None:
                declared = int(total)
            elif total is not None and declared is not None and int(total) != declared:
                return {
                    "ok": False,
                    "status": RESULT_FAILED,
                    "failure_reason": "DECLARED_TOTAL_CHANGED_ACROSS_PAGES",
                    "items": [],
                    "declared_total": declared,
                }
        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break
    return {
        "ok": True,
        "items": all_items,
        "declared_total": declared,
        "pages": page,
    }


async def sync_safety_materials(
    *,
    fetch_page: FetchPage,
    store: Any,
    dry_run: bool = True,
    start_page: int = 1,
    max_pages: int = MAX_PAGES,
) -> dict:
    """Fetch-all → validate → set-diff → hash → (optional) CURRENT_NEW + membership.

    COMPLETED is written only after membership arithmetic passes.
    """
    before = store.counts()
    if start_page != 1:
        return {
            "status": RESULT_REJECTED,
            "failure_reason": "SNAPSHOT_REQUIRES_START_PAGE_1",
            "snapshot_status": None,
            "dry_run": dry_run,
            "catalog_dml": 0,
            "membership_dml": 0,
            "snapshot_dml": 0,
            "counts_before": before,
            "counts_after": store.counts(),
        }

    fetched = await fetch_official_full(
        fetch_page, start_page=1, max_pages=max_pages
    )
    if not fetched.get("ok"):
        return {
            "status": fetched.get("status") or RESULT_FAILED,
            "failure_reason": fetched.get("failure_reason"),
            "snapshot_status": None,
            "dry_run": dry_run,
            "catalog_dml": 0,
            "membership_dml": 0,
            "snapshot_dml": 0,
            "counts_before": before,
            "counts_after": store.counts(),
        }

    raw_items = fetched["items"]
    normalized = [normalize_official_item(it) for it in raw_items]
    gate = validate_complete(fetched.get("declared_total"), normalized)
    if not gate["ok"]:
        return {
            "status": RESULT_FAILED,
            "failure_reason": ",".join(gate["reasons"]),
            "snapshot_status": None,
            "dry_run": dry_run,
            "declared": gate["declared_total"],
            "fetched": gate["fetched_count"],
            "unique": gate["unique_count"],
            "duplicate": gate["duplicate_count"],
            "invalid": gate["invalid_count"],
            "catalog_dml": 0,
            "membership_dml": 0,
            "snapshot_dml": 0,
            "counts_before": before,
            "counts_after": store.counts(),
        }

    catalog_rows = store.load_catalog()
    db_norm = [normalize_db_row(r) for r in catalog_rows]
    off_diff_items = _official_as_diff_items(normalized)
    diff = classify_sets(off_diff_items, db_norm)
    hash_items = [it.hash_row() for it in normalized]
    digest = snapshot_hash(hash_items)
    latest = store.latest_completed()
    summary = _diff_summary(diff)

    base = {
        "declared": gate["declared_total"],
        "fetched": gate["fetched_count"],
        "unique": gate["unique_count"],
        "duplicate": gate["duplicate_count"],
        "invalid": gate["invalid_count"],
        "snapshot_hash": digest,
        "dry_run": dry_run,
        **summary,
        "catalog_inserts_planned": len(diff["current_new_exact"]),
        "membership_planned": gate["unique_count"],
        "counts_before": before,
    }

    if latest and latest.get("snapshot_hash") == digest:
        after = store.counts()
        return {
            **base,
            "status": RESULT_NO_CHANGE,
            "snapshot_status": None,
            "snapshot_id": None,
            "catalog_dml": 0,
            "membership_dml": 0,
            "snapshot_dml": 0,
            "counts_after": after,
        }

    if dry_run:
        after = store.counts()
        return {
            **base,
            "status": RESULT_DRY_RUN,
            "snapshot_status": None,
            "catalog_dml": 0,
            "membership_dml": 0,
            "snapshot_dml": 0,
            "counts_after": after,
        }

    started = now_kst().isoformat()
    snapshot_id = None
    inserted = 0
    try:
        snapshot_id = store.insert_snapshot_running({
            "source_provider": SOURCE_PROVIDER,
            "source_dataset": SOURCE_DATASET,
            "source_call_api_id": SOURCE_CALL_API_ID,
            "started_at": started,
            "declared_total": gate["declared_total"],
            "fetched_count": gate["fetched_count"],
            "unique_count": gate["unique_count"],
            "duplicate_count": gate["duplicate_count"],
            "invalid_count": gate["invalid_count"],
            "snapshot_hash": digest,
            "status": STATUS_RUNNING,
        })
        insert_rows = [catalog_row_from_official(it["raw"]) for it in diff["current_new_exact"]]
        inserted = store.insert_catalog_rows(insert_rows) if insert_rows else 0

        catalog_after_insert = store.load_catalog()
        db_after = [normalize_db_row(r) for r in catalog_after_insert]
        known_ids = {r["id"] for r in db_after}
        db_by_url = {r["url"]: r for r in db_after if r.get("url")}
        db_by_medseq = {}
        for r in db_after:
            if r.get("medseq_status") == VALID_MEDSEQ and r.get("medseq") and r["medseq"] not in db_by_medseq:
                db_by_medseq[r["medseq"]] = r

        observed = now_kst().isoformat()
        membership_rows = []
        missing_ids = []
        for it in off_diff_items:
            mid = _resolve_material_id(it, db_by_url, db_by_medseq)
            if not mid or mid not in known_ids:
                missing_ids.append(it.get("medseq") or it.get("url"))
                continue
            membership_rows.append({
                "material_id": mid,
                "source_med_seq": it["medseq"],
                "source_url": it["url"],
                "source_title": it["title"],
                "source_published_date": it["date"],
                "observed_at": observed,
            })

        if missing_ids or len(membership_rows) != gate["unique_count"]:
            store.update_snapshot(snapshot_id, {
                "status": STATUS_FAILED,
                "failure_reason": "MEMBERSHIP_INCOMPLETE",
                "completed_at": now_kst().isoformat(),
            })
            return {
                **base,
                "status": RESULT_FAILED,
                "failure_reason": "MEMBERSHIP_INCOMPLETE",
                "snapshot_id": snapshot_id,
                "snapshot_status": STATUS_FAILED,
                "catalog_inserted": inserted,
                "catalog_dml": inserted,
                "membership_dml": 0,
                "snapshot_dml": 1,
                "repair": "CURRENT_NEW_INSERTED_WITHOUT_COMPLETED_SNAPSHOT" if inserted else None,
                "counts_after": store.counts(),
            }

        mem_n = store.insert_membership(snapshot_id, membership_rows)
        read_back = store.count_membership(snapshot_id)
        if mem_n != gate["unique_count"] or read_back != gate["unique_count"]:
            store.update_snapshot(snapshot_id, {
                "status": STATUS_FAILED,
                "failure_reason": "MEMBERSHIP_COUNT_MISMATCH",
                "completed_at": now_kst().isoformat(),
            })
            return {
                **base,
                "status": RESULT_FAILED,
                "failure_reason": "MEMBERSHIP_COUNT_MISMATCH",
                "snapshot_id": snapshot_id,
                "snapshot_status": STATUS_FAILED,
                "catalog_inserted": inserted,
                "catalog_dml": inserted,
                "membership_dml": mem_n,
                "snapshot_dml": 1,
                "repair": "CURRENT_NEW_INSERTED_WITHOUT_COMPLETED_SNAPSHOT" if inserted else None,
                "counts_after": store.counts(),
            }

        store.update_snapshot(snapshot_id, {
            "status": STATUS_COMPLETED,
            "completed_at": now_kst().isoformat(),
            "failure_reason": None,
        })
        after = store.counts()
        return {
            **base,
            "status": RESULT_COMPLETED,
            "snapshot_id": snapshot_id,
            "snapshot_status": STATUS_COMPLETED,
            "catalog_inserted": inserted,
            "catalog_dml": inserted,
            "membership_dml": mem_n,
            "snapshot_dml": 1,
            "counts_after": after,
        }
    except Exception as e:
        if snapshot_id:
            try:
                store.update_snapshot(snapshot_id, {
                    "status": STATUS_FAILED,
                    "failure_reason": str(e)[:300],
                    "completed_at": now_kst().isoformat(),
                })
            except Exception:
                pass
        return {
            **base,
            "status": RESULT_FAILED,
            "failure_reason": str(e)[:300],
            "snapshot_id": snapshot_id,
            "snapshot_status": STATUS_FAILED if snapshot_id else None,
            "catalog_inserted": inserted,
            "catalog_dml": inserted,
            "membership_dml": 0,
            "snapshot_dml": 1 if snapshot_id else 0,
            "repair": "CURRENT_NEW_INSERTED_WITHOUT_COMPLETED_SNAPSHOT" if inserted else None,
            "counts_after": store.counts(),
        }


def _public_result(result: dict) -> dict:
    keys = (
        "status", "failure_reason", "dry_run", "declared", "fetched", "unique",
        "duplicate", "invalid", "snapshot_hash", "current_existing", "current_new",
        "current_new_exact", "historical", "possible", "ambiguous",
        "catalog_inserts_planned", "membership_planned", "catalog_dml",
        "membership_dml", "snapshot_dml", "catalog_inserted", "snapshot_id",
        "snapshot_status", "repair", "counts_before", "counts_after",
    )
    return {k: result.get(k) for k in keys if k in result}


if __name__ == "__main__":
    import argparse
    import asyncio

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    parser = argparse.ArgumentParser(description="KOSHA safety-material current snapshot sync")
    parser.add_argument("--apply", action="store_true", help="write CURRENT_NEW + snapshot (default dry-run)")
    parser.add_argument("--start-page", type=int, default=1)
    args = parser.parse_args()

    from routers.kosha_collect import _fetch_safety_materials_page

    async def _run():
        store = SupabaseSnapshotStore()
        result = await sync_safety_materials(
            fetch_page=_fetch_safety_materials_page,
            store=store,
            dry_run=not args.apply,
            start_page=args.start_page,
        )
        print(json.dumps(_public_result(result), ensure_ascii=False, indent=2, default=str))

    asyncio.run(_run())

