"""OBJ-BZI-004/005 — SupabaseBizinfoRepository.

STORAGE_GATE 승인 후 활성화. InMemoryBizinfoRepository를 Supabase 구현으로 교체한다.

활성화 조건:
  1. STORAGE_GATE Owner 승인 완료
  2. sql/20261104_bizinfo_tables.sql Supabase 실행 완료
  3. BIZINFO_STORAGE_ENABLED=1 환경변수 설정

환경변수:
  BIZINFO_STORAGE_ENABLED — 비어있거나 없으면 비활성 (기본 비활성)
  SUPABASE_SERVICE_ROLE_KEY — Supabase 서비스 역할 키 (db/supabase_client.py 경유)

테이블:
  bizinfo_source_records       — 수집·정규화된 원천 공고 스냅샷
  bizinfo_editorial_content    — TAI 해설 + 권리확인 + 공개승인
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from services.bizinfo.approval import (
    ContentApprovalRecord,
    EditorialContent,
    RightsRecord,
)
from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord
from services.bizinfo.repository import BizinfoRepository
from services.bizinfo.status import ChangeRecord

logger = logging.getLogger(__name__)

_SRC  = "bizinfo_source_records"
_EDIT = "bizinfo_editorial_content"


def _parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except (ValueError, TypeError):
        return None


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _to_record(row: dict) -> NormalizedSourceRecord:
    app_start = _parse_date(row.get("application_start"))
    app_end   = _parse_date(row.get("application_end"))
    evt_start = _parse_date(row.get("event_start"))
    evt_end   = _parse_date(row.get("event_end"))
    rcp_start = _parse_date(row.get("reception_start"))
    rcp_end   = _parse_date(row.get("reception_end"))

    return NormalizedSourceRecord(
        source_kind=row["source_kind"],
        source_id="BIZINFO_PROGRAM" if row["source_kind"] == "PROGRAM" else "BIZINFO_EVENT",
        source_key=row["source_key"],
        title=row["title"],
        source_org=row.get("source_org"),
        origin_url=row.get("origin_url"),
        bizinfo_url=row.get("bizinfo_url"),
        retrieved_at=_parse_dt(row["retrieved_at"]) or datetime.now(timezone.utc),
        source_updated_at=_parse_dt(row.get("source_updated_at")),
        summary=row.get("summary"),
        support_target=row.get("support_target"),
        hashtags=row.get("hashtags") or [],
        parse_errors=row.get("parse_errors") or [],
        evidence_pending=row.get("evidence_pending") or [],
        application_period=(
            DateRange(start=app_start, end=app_end)
            if (app_start is not None or app_end is not None)
            else None
        ),
        event_period=(
            DateRange(start=evt_start, end=evt_end)
            if (evt_start is not None or evt_end is not None)
            else None
        ),
        reception_period=(
            DateRange(start=rcp_start, end=rcp_end)
            if (rcp_start is not None or rcp_end is not None)
            else None
        ),
    )


def _record_to_row(record: NormalizedSourceRecord, change: ChangeRecord) -> dict:
    ap = record.application_period
    ep = record.event_period
    rp = record.reception_period
    return {
        "source_kind":        record.source_kind,
        "source_key":         record.source_key,
        "title":              record.title,
        "source_org":         record.source_org,
        "origin_url":         record.origin_url,
        "bizinfo_url":        record.bizinfo_url,
        "retrieved_at":       record.retrieved_at.isoformat(),
        "source_updated_at":  record.source_updated_at.isoformat() if record.source_updated_at else None,
        "summary":            record.summary,
        "support_target":     record.support_target,
        "hashtags":           record.hashtags,
        "parse_errors":       record.parse_errors,
        "evidence_pending":   record.evidence_pending,
        "application_start":  ap.start.isoformat() if ap and ap.start else None,
        "application_end":    ap.end.isoformat()   if ap and ap.end   else None,
        "event_start":        ep.start.isoformat() if ep and ep.start else None,
        "event_end":          ep.end.isoformat()   if ep and ep.end   else None,
        "reception_start":    rp.start.isoformat() if rp and rp.start else None,
        "reception_end":      rp.end.isoformat()   if rp and rp.end   else None,
        "change_verdict":     change.verdict,
        "changed_fields":     list(change.changed_fields),
        "updated_at":         "now()",
    }


class SupabaseBizinfoRepository:
    """Supabase PostgREST 기반 BizinfoRepository 구현체.

    STORAGE_GATE 승인 + DB 테이블 생성 + BIZINFO_STORAGE_ENABLED=1 이후 사용.
    """

    def __init__(self, supabase_client) -> None:
        self._sb = supabase_client

    # -------------------------------------------------------------------------
    # BizinfoRepository Protocol
    # -------------------------------------------------------------------------

    def get_prior_record(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[NormalizedSourceRecord]:
        resp = (
            self._sb.table(_SRC)
            .select("*")
            .eq("source_kind", source_kind)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return _to_record(resp.data[0])

    def save_record(
        self,
        record: NormalizedSourceRecord,
        change: ChangeRecord,
    ) -> None:
        row = _record_to_row(record, change)
        (
            self._sb.table(_SRC)
            .upsert(row, on_conflict="source_kind,source_key")
            .execute()
        )

    def get_editorial(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[EditorialContent]:
        resp = (
            self._sb.table(_EDIT)
            .select("source_kind,source_key,explanation,guidance,authored_at,tai_link")
            .eq("source_kind", source_kind)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        authored_at = _parse_dt(row.get("authored_at"))
        if authored_at is None:
            return None
        return EditorialContent(
            source_key=row["source_key"],
            source_kind=row["source_kind"],
            explanation=row["explanation"],
            guidance=row["guidance"],
            authored_at=authored_at,
            tai_link=row.get("tai_link"),
        )

    def get_rights(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[RightsRecord]:
        resp = (
            self._sb.table(_EDIT)
            .select("source_key,rights_basis,rights_confirmed_at,rights_confirmed_by")
            .eq("source_kind", source_kind)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        if not row.get("rights_basis"):
            return None
        confirmed_at = _parse_dt(row.get("rights_confirmed_at"))
        if confirmed_at is None:
            return None
        return RightsRecord(
            source_key=row["source_key"],
            rights_basis=row["rights_basis"],
            confirmed_at=confirmed_at,
            confirmed_by=row.get("rights_confirmed_by") or "",
        )

    def get_approval(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[ContentApprovalRecord]:
        resp = (
            self._sb.table(_EDIT)
            .select("source_kind,source_key,approved_at,approved_by")
            .eq("source_kind", source_kind)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        if not row.get("approved_at"):
            return None
        approved_at = _parse_dt(row["approved_at"])
        if approved_at is None:
            return None
        return ContentApprovalRecord(
            source_key=row["source_key"],
            source_kind=row["source_kind"],
            approved_at=approved_at,
            approved_by=row.get("approved_by") or "",
        )

    def get_relevance_verdict(
        self,
        source_kind: str,
        source_key: str,
    ) -> Optional[str]:
        resp = (
            self._sb.table(_SRC)
            .select("relevance_verdict")
            .eq("source_kind", source_kind)
            .eq("source_key", source_key)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("relevance_verdict")

    def list_eligible_keys(
        self,
        source_kind: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[str]:
        resp = (
            self._sb.table(_EDIT)
            .select("source_key")
            .eq("source_kind", source_kind)
            .not_.is_("approved_at", "null")
            .order("approved_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [row["source_key"] for row in (resp.data or [])]
