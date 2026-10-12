"""EXT-037 화학물질 안전정보 공개 읽기 계층.

TAI DB에서 CAS 번호로 화학물질 안전정보 조회.
Write=0. raw 원본 구조 미변경.
현행(is_current=true) COMPLETED 스냅샷만 사용.

Error contract:
  validate_cas()           → ValueError   (caller converts to 422)
  _get_client() miss       → Ext037Unavailable (env not set)
  any DB query exception   → Ext037Unavailable (runtime DB failure)
"""
from __future__ import annotations

from typing import Any

from services.keco_chemical.read import validate_cas
from services.ext037_chemical_safety.contract import (
    SNAPSHOT_COMPLETED,
    TABLE_ITEMS,
    TABLE_SNAPSHOTS,
)


class Ext037ReadError(Exception):
    pass


class Ext037Unavailable(Ext037ReadError):
    pass


def _get_client():
    import os
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise Ext037Unavailable(
            "EXT037_UNAVAILABLE: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
        )
    from supabase import create_client
    return create_client(url, key)


def _get_current_snapshot_id(client: Any) -> str | None:
    res = (
        client.table(TABLE_SNAPSHOTS)
        .select("id")
        .eq("status", SNAPSHOT_COMPLETED)
        .eq("is_current", True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0]["id"] if rows else None


def get_chemical_safety_by_cas(cas_no: str) -> list[dict[str, Any]]:
    """현행 EXT-037 스냅샷에서 CAS 번호로 화학물질 안전정보 조회.

    Returns list of dicts with public fields only.
    빈 목록은 정상 응답 (CAS가 수집 DB에 없음).

    Raises:
      ValueError         — invalid CAS format (caller → 422)
      Ext037Unavailable  — DB not configured or query failure (caller → 503)
    """
    cas = validate_cas(cas_no)
    try:
        client = _get_client()
        snapshot_id = _get_current_snapshot_id(client)
        if snapshot_id is None:
            return []

        res = (
            client.table(TABLE_ITEMS)
            .select("datano,raw")
            .eq("snapshot_id", snapshot_id)
            .eq("raw->>casNo", cas)
            .execute()
        )
        rows = res.data or []
        return [_extract_public_fields(row) for row in rows]

    except Ext037Unavailable:
        raise
    except Exception as exc:
        raise Ext037Unavailable("EXT037_QUERY_FAILED") from exc


def _extract_public_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw") or {}
    return {
        "datano": row.get("datano") or raw.get("dataNo", ""),
        "chem_ko": raw.get("chemKo", ""),
        "chem_en": raw.get("chemEn", ""),
        "cas_no": raw.get("casNo", ""),
        "oral": raw.get("oral", ""),
        "skin": raw.get("skin", ""),
        "inhale": raw.get("inhale", ""),
        "eyeball": raw.get("eyeball", ""),
        "symptom": raw.get("symptom", ""),
        "etc": raw.get("etc", ""),
    }
