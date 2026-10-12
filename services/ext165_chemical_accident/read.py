"""EXT-165 화학사고 공개 읽기 계층.

TAI DB에서 EXT-165 화학사고 정보 공개 조회.
Write=0. raw 원본 구조 미변경.
현행(is_current=true, collect_scope IS NULL) COMPLETED 스냅샷만 사용.

Error contract:
  validate_datano()               → ChemicalAccidentQueryError("DATANO_INVALID")
  sanitize_q() bad format         → ChemicalAccidentQueryError("Q_INVALID")
  sanitize_q() too long           → ChemicalAccidentQueryError("Q_TOO_LONG")
  _get_snapshot_id() miss         → ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT")
  get_ready() miss                → ChemicalAccidentQueryError("NOT_FOUND")
  any DB query exception          → ChemicalAccidentQueryError("UNAVAILABLE")
"""
from __future__ import annotations

import re
from typing import Any

from services.ext165_chemical_accident.contract import (
    SNAPSHOT_COMPLETED,
    TABLE_ITEMS,
    TABLE_SNAPSHOTS,
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_Q_LEN = 80

# 허용 검색어: 한글·영숫자 시작, 이후 한글·영숫자·공백·하이픈 조합
_Q_OK = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s\-]*$")

# 검색 대상 JSONB 필드 (raw->>field 형태로 사용)
_SEARCH_FIELDS = ("summary", "chem", "area", "cscTy", "cause", "place")


class ChemicalAccidentQueryError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(code)


def sanitize_q(raw: str | None) -> str | None:
    """검색어 정제. None 또는 빈 문자열이면 None 반환.

    Raises:
      ChemicalAccidentQueryError("Q_TOO_LONG")  — 80자 초과
      ChemicalAccidentQueryError("Q_INVALID")   — 허용되지 않는 문자 포함
    """
    if raw is None:
        return None
    q = str(raw).strip()
    if not q:
        return None
    if len(q) > MAX_Q_LEN:
        raise ChemicalAccidentQueryError("Q_TOO_LONG")
    if not _Q_OK.fullmatch(q):
        raise ChemicalAccidentQueryError("Q_INVALID")
    return q


def escape_ilike(q: str) -> str:
    """PostgREST ilike 필터 특수문자 이스케이프.

    역슬래시→이중역슬래시, %→\\%, _→\\_, ,→공백 (or_() 절 주입 방지).
    """
    return (
        q.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
        .replace(",", " ")
    )


def validate_datano(datano: str) -> str:
    v = str(datano or "").strip()
    if not v:
        raise ChemicalAccidentQueryError("DATANO_INVALID")
    return v


def _extract_public_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw") or {}
    return {
        "datano": row.get("datano") or raw.get("dataNo") or raw.get("datano", ""),
        "accident_date": raw.get("cscDe") or "",
        "accident_type": raw.get("cscTy") or "",
        "area": raw.get("area") or "",
        "place": raw.get("place") or "",
        "chemical": raw.get("chem") or "",
        "cause": raw.get("cause") or "",
        "summary": raw.get("summary") or "",
    }


# ── In-memory store (tests) ──────────────────────────────────────────────────

class MemoryChemicalAccidentStore:
    """Tests용 인메모리 스토어.

    items=None  → NO_CURRENT_SNAPSHOT (스냅샷 없음, 503)
    items=[]    → 스냅샷 있음, 검색 결과 0건 (200 빈 목록)
    items=[...] → 스냅샷 있음, 데이터 존재
    """

    def __init__(self, items: list[dict[str, Any]] | None = None):
        self._has_snapshot = items is not None
        self._items: list[dict[str, Any]] = list(items or [])

    def _match(self, item: dict[str, Any], term: str) -> bool:
        t = term.lower()
        for f in ("summary", "chemical", "area", "accident_type", "cause", "place"):
            if t in str(item.get(f) or "").lower():
                return True
        return False

    def list_ready(
        self, q: str | None, page: int, page_size: int
    ) -> dict[str, Any]:
        if not self._has_snapshot:
            raise ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT")
        items = self._items if q is None else [i for i in self._items if self._match(i, q)]
        total = len(items)
        offset = (page - 1) * page_size
        return {
            "items": items[offset: offset + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_ready(self, datano: str) -> dict[str, Any] | None:
        if not self._has_snapshot:
            raise ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT")
        for item in self._items:
            if item.get("datano") == datano:
                return item
        return None


# ── Supabase store (production) ──────────────────────────────────────────────

class SupabaseChemicalAccidentStore:
    """생산 환경 Supabase 스토어.

    현행(is_current=true, collect_scope IS NULL) COMPLETED 스냅샷만 조회.
    """

    def __init__(self, client: Any):
        self._client = client

    def _get_snapshot_id(self) -> str:
        """현행 전체수집 스냅샷 ID 반환.

        Raises ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT") if none found.
        """
        res = (
            self._client.table(TABLE_SNAPSHOTS)
            .select("id")
            .eq("status", SNAPSHOT_COMPLETED)
            .eq("is_current", True)
            .is_("collect_scope", "null")
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            raise ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT")
        return rows[0]["id"]

    def list_ready(
        self, q: str | None, page: int, page_size: int
    ) -> dict[str, Any]:
        snapshot_id = self._get_snapshot_id()
        offset = (page - 1) * page_size
        base = (
            self._client.table(TABLE_ITEMS)
            .select("datano,raw", count="exact")
            .eq("snapshot_id", snapshot_id)
        )
        if q:
            safe = escape_ilike(q)
            clause = ",".join(f"raw->>{f}.ilike.%{safe}%" for f in _SEARCH_FIELDS)
            base = base.or_(clause)
        res = (
            base
            .order("datano", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = res.data or []
        total = res.count if res.count is not None else len(rows)
        return {
            "items": [_extract_public_fields(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_ready(self, datano: str) -> dict[str, Any] | None:
        snapshot_id = self._get_snapshot_id()
        res = (
            self._client.table(TABLE_ITEMS)
            .select("datano,raw")
            .eq("snapshot_id", snapshot_id)
            .eq("datano", datano)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        return _extract_public_fields(rows[0])


# ── Public façade ────────────────────────────────────────────────────────────

def list_chemical_accidents(
    store: MemoryChemicalAccidentStore | SupabaseChemicalAccidentStore,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    page = max(1, int(page))
    page_size = max(1, min(MAX_PAGE_SIZE, int(page_size)))
    try:
        return store.list_ready(q, page, page_size)
    except ChemicalAccidentQueryError:
        raise
    except Exception as exc:
        raise ChemicalAccidentQueryError("UNAVAILABLE") from exc


def get_chemical_accident_by_datano(
    store: MemoryChemicalAccidentStore | SupabaseChemicalAccidentStore,
    datano: str,
) -> dict[str, Any]:
    """단건 조회.

    Raises ChemicalAccidentQueryError("DATANO_INVALID") for empty datano.
    Raises ChemicalAccidentQueryError("NO_CURRENT_SNAPSHOT") if no current snapshot.
    Raises ChemicalAccidentQueryError("NOT_FOUND") if absent in current snapshot.
    Raises ChemicalAccidentQueryError("UNAVAILABLE") on DB failure.
    """
    clean = validate_datano(datano)
    try:
        item = store.get_ready(clean)
    except ChemicalAccidentQueryError:
        raise
    except Exception as exc:
        raise ChemicalAccidentQueryError("UNAVAILABLE") from exc
    if item is None:
        raise ChemicalAccidentQueryError("NOT_FOUND")
    return item
