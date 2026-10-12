"""EXT-132 위험물 정보 공개 읽기 계층.

TAI DB에서 CAS 번호로 소방청 위험물 정보 조회.
Write=0. raw 원본 구조 미변경.
현행(is_current=true) COMPLETED 스냅샷만 사용.
동일 CAS에 여러 위험물 레코드 존재 시 모두 반환.

Error contract:
  validate_cas()            → ValueError   (caller converts to 422)
  _get_client() miss        → Ext132Unavailable (env not set)
  any DB query exception    → Ext132Unavailable (runtime DB failure)
"""
from __future__ import annotations

from typing import Any

from services.keco_chemical.read import validate_cas
from services.ext132_hazardous_material.contract import (
    SNAPSHOT_COMPLETED,
    TABLE_ITEMS,
    TABLE_SNAPSHOTS,
)


class Ext132ReadError(Exception):
    pass


class Ext132Unavailable(Ext132ReadError):
    pass


def _get_client():
    import os
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise Ext132Unavailable(
            "EXT132_UNAVAILABLE: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
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


def get_hazardous_material_by_cas(cas_no: str) -> list[dict[str, Any]]:
    """현행 EXT-132 스냅샷에서 CAS 번호로 위험물 정보 조회.

    동일 CAS에 복수 레코드가 존재하면 모두 반환.
    빈 목록은 정상 응답 (CAS가 수집 DB에 없음).

    Raises:
      ValueError          — invalid CAS format (caller → 422)
      Ext132Unavailable   — DB not configured or query failure (caller → 503)
    """
    cas = validate_cas(cas_no)
    try:
        client = _get_client()
        snapshot_id = _get_current_snapshot_id(client)
        if snapshot_id is None:
            return []

        res = (
            client.table(TABLE_ITEMS)
            .select("chemicalno,raw")
            .eq("snapshot_id", snapshot_id)
            .eq("raw->>casno", cas)
            .execute()
        )
        rows = res.data or []
        return [_extract_public_fields(row) for row in rows]

    except Ext132Unavailable:
        raise
    except Exception as exc:
        raise Ext132Unavailable("EXT132_QUERY_FAILED") from exc


def _extract_public_fields(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw") or {}
    return {
        "chemicalno": row.get("chemicalno") or raw.get("chemaicalno", ""),
        "chemical_name": raw.get("chemicalname", ""),
        "cas_no": raw.get("casno", ""),
        "un_no": raw.get("unno", ""),
        "hazard_class": raw.get("hazardmaterialclass", ""),
    }
