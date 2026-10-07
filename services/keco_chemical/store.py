"""KECO Reference Supabase (LEG DB) 저장 서비스.

환경변수:
  LEG_SUPABASE_URL               LEG DB URL
  LEG_SUPABASE_SERVICE_ROLE_KEY  service role key

Custom schema access:
  supabase_client.schema("msds_ref").table("keco_*") — qualified table name 문자열 금지.

Change detection:
  NEW       — source_record_id 없음
  UNCHANGED — source_content_hash 동일
  CHANGED   — source_content_hash 다름 → last_changed_at update

Collection target state machine (KECO-003):
  bootstrap_targets   — identity_projection CAS → keco_collection_targets PENDING
  claim_targets       — PENDING/RETRY/stale-RUNNING → RUNNING (claim)
  mark_target_*       — RUNNING → DONE / EMPTY / RETRY / FAILED / CONFLICT
  get_status_summary  — 현재 상태 집계
  get_due_targets     — next_refresh_at <= now 대상
  has_active_run      — lock check (중복 실행 방지)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Tuple

from services.time import now_kst, serialize_business_datetime
from services.keco_chemical.contract import (
    SOURCE_CONTRACT_VERSION,
    SOURCE_ID,
    TARGET_TYPE_CAS,
    TARGET_STATUS_PENDING,
    TARGET_STATUS_RUNNING,
    TARGET_STATUS_DONE,
    TARGET_STATUS_EMPTY,
    TARGET_STATUS_RETRY,
    TARGET_STATUS_FAILED,
    TARGET_STATUS_CONFLICT,
    DEFAULT_STALE_RUNNING_MINUTES,
    DEFAULT_REFRESH_INTERVAL_DAYS,
    LOCK_RUNTIME_RUN_TYPES,
)
from services.keco_chemical.hash import chemical_content_hash, regulatory_fact_hash
from services.keco_chemical.parse import KecoChemicalItem, KecoRegulatoryFact

logger = logging.getLogger(__name__)

STATUS_NEW = "NEW"
STATUS_UNCHANGED = "UNCHANGED"
STATUS_CHANGED = "CHANGED"


class KecoStoreError(Exception):
    pass


class KecoStoreMissingConfigError(KecoStoreError):
    def __init__(self, missing: str):
        super().__init__(f"LEG Supabase config missing: {missing}")


class KecoStoreSourceRecordIdError(KecoStoreError):
    def __init__(self):
        super().__init__("SOURCE_RECORD_ID_REQUIRED: sbstnId is blank or missing — identity contamination prevented")


def _now_iso() -> str:
    """TAI Time Contract 승인 ISO 시리얼: KST +09:00."""
    return serialize_business_datetime(now_kst())


def _get_supabase_client():
    """LEG DB Supabase 클라이언트 생성."""
    url = os.getenv("LEG_SUPABASE_URL", "").strip()
    key = os.getenv("LEG_SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url:
        raise KecoStoreMissingConfigError("LEG_SUPABASE_URL")
    if not key:
        raise KecoStoreMissingConfigError("LEG_SUPABASE_SERVICE_ROLE_KEY")
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError as exc:
        raise KecoStoreError("supabase package not installed") from exc


def _raw_payload_hash(raw_payload: dict) -> str:
    """raw payload dict의 SHA-256 hash."""
    text = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PersistItemResult:
    status: str          # NEW | UNCHANGED | CHANGED
    chemical_id: Optional[str]
    inserted_fact_count: int


@dataclass
class KecoReferenceStore:
    """LEG msds_ref schema 저장 서비스."""

    # ──────────────────────────────────────────
    # Ingestion Run Lifecycle
    # ──────────────────────────────────────────

    def start_run(
        self,
        run_type: str,
        search_gubun: Optional[str] = None,
        search_nm: Optional[str] = None,
    ) -> str:
        """RUNNING 상태 ingestion run 생성. run_id(uuid) 반환. serviceKey 저장 금지."""
        now = _now_iso()
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        result = db.table("keco_ingestion_runs").insert({
            "source_id": SOURCE_ID,
            "source_contract_version": SOURCE_CONTRACT_VERSION,
            "run_type": run_type,
            "status": "RUNNING",
            "search_gubun": search_gubun,
            "search_nm": search_nm,
            "request_count": 0,
            "record_count": 0,
            "started_at": now,
            "heartbeat_at": now,
        }).execute()
        return result.data[0]["id"]

    def start_exclusive_run(
        self,
        run_type: str,
        search_gubun: Optional[str] = None,
        search_nm: Optional[str] = None,
        stale_minutes: int = DEFAULT_STALE_RUNNING_MINUTES,
    ) -> tuple:
        """Recover stale runs → atomic INSERT → returns (run_id, locked).

        locked=False: insert succeeded, run_id is valid.
        locked=True:  DB unique violation — another runtime run is RUNNING.
        Callers must check locked before proceeding.
        """
        self.recover_stale_runs(stale_minutes)
        try:
            run_id = self.start_run(run_type, search_gubun=search_gubun, search_nm=search_nm)
            return run_id, False
        except Exception as exc:
            msg = str(exc)
            if "23505" in msg or "unique" in msg.lower() or "duplicate" in msg.lower():
                logger.info(
                    "[KECO-STORE] start_exclusive_run(%s): locked — another runtime run is RUNNING",
                    run_type,
                )
                return None, True
            raise

    def finish_run(
        self,
        run_id: str,
        status: str,
        request_count: int,
        record_count: int,
        metrics_json: Optional[dict] = None,
    ) -> None:
        """run을 status("COMPLETED" 또는 "PARTIAL")로 마감."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        db.table("keco_ingestion_runs").update({
            "status": status,
            "completed_at": _now_iso(),
            "request_count": request_count,
            "record_count": record_count,
            "metrics_json": metrics_json,
        }).eq("id", run_id).execute()

    def complete_run(
        self,
        run_id: str,
        request_count: int,
        record_count: int,
        metrics_json: Optional[dict] = None,
    ) -> None:
        """run을 COMPLETED로 마감. finish_run("COMPLETED", ...) wrapper."""
        self.finish_run(run_id, "COMPLETED", request_count, record_count, metrics_json)

    def fail_run(
        self,
        run_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """run을 FAILED로 마감. serviceKey가 error_message에 코드되면 실제로 제거한 후 저장.
        해당 run에 남은 RUNNING targets도 RETRY로 해제해 orphan 방지."""
        from services.keco_chemical.client import redact_key
        api_key = (os.getenv("KECO_API_SERVICE_KEY") or "").strip()
        safe_msg = redact_key(error_message or "", api_key)
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        db.table("keco_ingestion_runs").update({
            "status": "FAILED",
            "completed_at": _now_iso(),
            "error_code": error_code,
            "error_message": safe_msg,
        }).eq("id", run_id).execute()
        self.release_running_targets(run_id)

    # ──────────────────────────────────────────
    # Item Persistence
    # ──────────────────────────────────────────

    def upsert_chemical(
        self,
        raw_payload: dict,
        item: KecoChemicalItem,
        run_id: str,
    ) -> Tuple[str, Optional[str]]:
        """화학물질 upsert. (status, chemical_id) 반환.

        status: NEW | UNCHANGED | CHANGED
        source_record_id blank → KecoStoreSourceRecordIdError (identity contamination 방지)
        korexst_raw 그대로 저장 (ke_no 변환 금지)
        """
        source_record_id = (item.sbstn_id or "").strip()
        if not source_record_id:
            raise KecoStoreSourceRecordIdError()

        client = _get_supabase_client()
        db = client.schema("msds_ref")
        content_hash = chemical_content_hash(item)
        raw_hash = _raw_payload_hash(raw_payload)
        now = _now_iso()

        # --- keco_raw_records upsert ---
        existing_raw = (
            db.table("keco_raw_records")
            .select("id")
            .eq("source_record_id", source_record_id)
            .eq("payload_hash", raw_hash)
            .execute()
        )
        if not existing_raw.data:
            db.table("keco_raw_records").insert({
                "source_record_id": source_record_id,
                "raw_payload": raw_payload,
                "payload_hash": raw_hash,
                "first_seen_run_id": run_id,
                "last_seen_run_id": run_id,
                "last_seen_at": now,
            }).execute()
        else:
            db.table("keco_raw_records").update({
                "last_seen_run_id": run_id,
                "last_seen_at": now,
            }).eq("source_record_id", source_record_id).eq("payload_hash", raw_hash).execute()

        # --- keco_chemicals upsert ---
        existing = (
            db.table("keco_chemicals")
            .select("id,source_content_hash")
            .eq("source_record_id", source_record_id)
            .execute()
        )

        if not existing.data:
            result = db.table("keco_chemicals").insert({
                "source_record_id": source_record_id,
                "cas_no": item.cas_no,
                "korexst_raw": item.korexst_raw,
                "chemical_name_ko": item.sbstn_nm_kor,
                "chemical_name_en": item.sbstn_nm_eng,
                "alias_name_ko": item.sbstn_nm2_kor,
                "alias_name_en": item.sbstn_nm2_eng,
                "molecular_formula": item.mlcfrm,
                "molecular_weight_raw": item.mlcwgt,
                "source_content_hash": content_hash,
            }).execute()
            chemical_id = result.data[0]["id"] if result.data else None
            return STATUS_NEW, chemical_id

        row = existing.data[0]
        chemical_id = row["id"]

        if row["source_content_hash"] == content_hash:
            db.table("keco_chemicals").update({
                "last_seen_at": now,
            }).eq("id", chemical_id).execute()
            return STATUS_UNCHANGED, chemical_id

        db.table("keco_chemicals").update({
            "cas_no": item.cas_no,
            "korexst_raw": item.korexst_raw,
            "chemical_name_ko": item.sbstn_nm_kor,
            "chemical_name_en": item.sbstn_nm_eng,
            "alias_name_ko": item.sbstn_nm2_kor,
            "alias_name_en": item.sbstn_nm2_eng,
            "molecular_formula": item.mlcfrm,
            "molecular_weight_raw": item.mlcwgt,
            "source_content_hash": content_hash,
            "last_changed_at": now,
            "last_seen_at": now,
            "updated_at": now,
        }).eq("id", chemical_id).execute()
        return STATUS_CHANGED, chemical_id

    def upsert_regulatory_facts(
        self,
        chemical_id: str,
        type_list: list[KecoRegulatoryFact],
    ) -> int:
        """규제 사실 upsert. inserted count 반환. duplicate = 0 보장."""
        if not type_list:
            return 0
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        inserted = 0
        for ordinal, fact in enumerate(type_list):
            fact_h = regulatory_fact_hash(fact)
            existing = (
                db.table("keco_regulatory_facts")
                .select("id")
                .eq("keco_chemical_id", chemical_id)
                .eq("fact_hash", fact_h)
                .execute()
            )
            if existing.data:
                continue
            db.table("keco_regulatory_facts").insert({
                "keco_chemical_id": chemical_id,
                "classification_type": fact.sbstn_clsf_type_nm,
                "unique_no": fact.unq_no,
                "content_info": fact.cont_info,
                "exception_info": fact.excp_info,
                "notice_date_raw": fact.ancmnt_ymd,
                "notice_info": fact.ancmnt_info,
                "fact_hash": fact_h,
                "source_ordinal": ordinal,
            }).execute()
            inserted += 1
        return inserted

    def persist_item(
        self,
        raw_payload: dict,
        item: KecoChemicalItem,
        run_id: str,
    ) -> PersistItemResult:
        """단일 항목 저장 orchestration: raw → chemical → facts 순서 보장."""
        status, chemical_id = self.upsert_chemical(raw_payload, item, run_id)
        inserted_fact_count = 0
        if chemical_id is not None:
            inserted_fact_count = self.upsert_regulatory_facts(chemical_id, item.type_list)
        return PersistItemResult(
            status=status,
            chemical_id=chemical_id,
            inserted_fact_count=inserted_fact_count,
        )

    # ──────────────────────────────────────────
    # Collection Target Table (KECO-003)
    # ──────────────────────────────────────────

    def bootstrap_targets(self, dry_run: bool = False) -> int:
        """identity_projection CAS → keco_collection_targets PENDING 생성.

        이미 target이 있으면 skip (idempotent).
        dry_run=True: DB write 없이 대상 수만 반환.
        반환: 새로 생성된(될) target 수.
        """
        client = _get_supabase_client()
        db = client.schema("msds_ref")

        # Read all CAS from identity_projection (paginated)
        all_cas: set = set()
        page_size = 1000
        offset = 0
        while True:
            rows = (
                db.table("identity_projection")
                .select("cas_no")
                .not_.is_("cas_no", "null")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            if not rows.data:
                break
            for row in rows.data:
                cas = (row.get("cas_no") or "").strip()
                if cas:
                    all_cas.add(cas)
            if len(rows.data) < page_size:
                break
            offset += page_size

        distinct_cas = sorted(all_cas)
        if dry_run:
            return len(distinct_cas)

        # Find already-existing targets
        existing: set = set()
        page_size_ex = 1000
        ex_offset = 0
        while True:
            ex_rows = (
                db.table("keco_collection_targets")
                .select("target_value")
                .eq("target_type", TARGET_TYPE_CAS)
                .range(ex_offset, ex_offset + page_size_ex - 1)
                .execute()
            )
            if not ex_rows.data:
                break
            for row in ex_rows.data:
                existing.add(row["target_value"])
            if len(ex_rows.data) < page_size_ex:
                break
            ex_offset += page_size_ex

        new_cas = [c for c in distinct_cas if c not in existing]
        now = _now_iso()
        batch_size = 500
        for i in range(0, len(new_cas), batch_size):
            batch = new_cas[i : i + batch_size]
            rows_to_insert = [
                {
                    "target_type": TARGET_TYPE_CAS,
                    "target_value": cas,
                    "status": TARGET_STATUS_PENDING,
                    "created_at": now,
                    "updated_at": now,
                }
                for cas in batch
            ]
            db.table("keco_collection_targets").insert(rows_to_insert).execute()

        return len(new_cas)

    def claim_targets(
        self,
        run_id: str,
        limit: int,
        stale_minutes: int = DEFAULT_STALE_RUNNING_MINUTES,
        mode: str = "bulk",
    ) -> List[dict]:
        """target을 RUNNING으로 claim해서 반환. last_run_id = run_id로 기록.

        mode="bulk"  → PENDING + RETRY (초기 전수수집 / batch)
        mode="retry" → RETRY + FAILED only (재처리 전용 — PENDING 포함 안함)

        stale RUNNING recovery는 recover_stale_runs()로 분리. claim_targets에서는 처리 안함.
        """
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()

        if mode == "retry":
            candidate_statuses = (TARGET_STATUS_RETRY, TARGET_STATUS_FAILED)
        else:
            candidate_statuses = (TARGET_STATUS_PENDING, TARGET_STATUS_RETRY)

        claimed = []
        for status in candidate_statuses:
            if len(claimed) >= limit:
                break
            need = limit - len(claimed)
            rows = (
                db.table("keco_collection_targets")
                .select("id,target_type,target_value,attempt_count")
                .eq("status", status)
                .order("created_at")
                .limit(need)
                .execute()
            )
            claimed.extend(rows.data or [])

        if not claimed:
            return []

        ids = [r["id"] for r in claimed]
        db.table("keco_collection_targets").update({
            "status": TARGET_STATUS_RUNNING,
            "last_run_id": run_id,
            "last_attempted_at": now,
            "updated_at": now,
        }).in_("id", ids).execute()

        return claimed

    def claim_due_targets(
        self,
        run_id: str,
        limit: int,
    ) -> List[dict]:
        """next_refresh_at <= now の DONE/EMPTY/RETRY targets を RUNNING に claim して返す."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        rows = (
            db.table("keco_collection_targets")
            .select("id,target_type,target_value,attempt_count")
            .in_("status", [TARGET_STATUS_DONE, TARGET_STATUS_EMPTY, TARGET_STATUS_RETRY])
            .lte("next_refresh_at", now)
            .order("next_refresh_at")
            .limit(limit)
            .execute()
        )
        due = rows.data or []
        if not due:
            return []
        ids = [r["id"] for r in due]
        db.table("keco_collection_targets").update({
            "status": TARGET_STATUS_RUNNING,
            "last_run_id": run_id,
            "last_attempted_at": now,
            "updated_at": now,
        }).in_("id", ids).execute()
        return due

    def recover_stale_runs(
        self,
        stale_minutes: int = DEFAULT_STALE_RUNNING_MINUTES,
    ) -> int:
        """COALESCE(heartbeat_at, started_at) 기준으로 stale RUNNING run → PARTIAL 처리.

        Stale run에 last_run_id로 연결된 RUNNING target도 RETRY로 복구.
        반환: 처리된 run 수.
        """
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        threshold = serialize_business_datetime(
            now_kst() - timedelta(minutes=stale_minutes)
        )
        error_msg = f"Run RUNNING for >{stale_minutes}m without heartbeat — auto-recovered"

        # heartbeat_at이 있으면 heartbeat_at 기준, 없으면 started_at 기준
        q1 = (
            db.table("keco_ingestion_runs")
            .select("id")
            .eq("status", "RUNNING")
            .not_.is_("heartbeat_at", "null")
            .lt("heartbeat_at", threshold)
            .execute()
        )
        q2 = (
            db.table("keco_ingestion_runs")
            .select("id")
            .eq("status", "RUNNING")
            .is_("heartbeat_at", "null")
            .lt("started_at", threshold)
            .execute()
        )

        stale_ids = [r["id"] for r in (q1.data or [])] + [r["id"] for r in (q2.data or [])]
        if not stale_ids:
            return 0

        db.table("keco_ingestion_runs").update({
            "status": "PARTIAL",
            "completed_at": now,
            "error_code": "STALE_RUN_RECOVERED",
            "error_message": error_msg,
        }).in_("id", stale_ids).execute()

        # stale run에 속했던 RUNNING targets → RETRY
        db.table("keco_collection_targets").update({
            "status": TARGET_STATUS_RETRY,
            "updated_at": now,
        }).eq("status", TARGET_STATUS_RUNNING).in_("last_run_id", stale_ids).execute()

        count = len(stale_ids)
        logger.info(
            "[KECO-STORE] recover_stale_runs: recovered %d stale run(s) → PARTIAL, RUNNING targets → RETRY",
            count,
        )
        return count

    def heartbeat_run(self, run_id: str) -> None:
        """진행 중 run의 heartbeat_at 갱신. stale recovery에서 최근 활성 증명용."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        db.table("keco_ingestion_runs").update({
            "heartbeat_at": _now_iso(),
        }).eq("id", run_id).execute()

    def release_running_targets(self, run_id: str) -> int:
        """run_id에 속한 미처리 RUNNING targets → RETRY 해제. 다음 실행에서 즉시 재처리 가능."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        result = (
            db.table("keco_collection_targets")
            .update({
                "status": TARGET_STATUS_RETRY,
                "updated_at": now,
            })
            .eq("status", TARGET_STATUS_RUNNING)
            .eq("last_run_id", run_id)
            .execute()
        )
        count = len(result.data or [])
        if count:
            logger.info(
                "[KECO-STORE] release_running_targets(run_id=%s): released %d targets → RETRY",
                run_id, count,
            )
        return count

    def mark_target_running(self, target_id: str, run_id: str) -> None:
        """target을 RUNNING으로 마크 (claim_targets 이후 per-target 확정용)."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        db.table("keco_collection_targets").update({
            "status": TARGET_STATUS_RUNNING,
            "last_run_id": run_id,
            "last_attempted_at": now,
            "updated_at": now,
        }).eq("id", target_id).execute()

    def _mark_target(
        self,
        target_id: str,
        run_id: str,
        status: str,
        api_requests: int = 0,
        source_items: int = 0,
        error_code: Optional[str] = None,
        error_msg: Optional[str] = None,
        set_success: bool = False,
        set_refresh: bool = False,
        refresh_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
        clear_errors: bool = False,
    ) -> None:
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        updates: dict = {
            "status": status,
            "last_run_id": run_id,
            "last_attempted_at": now,
            "updated_at": now,
            "api_request_count": api_requests,
            "source_item_count": source_items,
        }
        if clear_errors:
            updates["last_error_code"] = None
            updates["last_error_message"] = None
        else:
            if error_code is not None:
                updates["last_error_code"] = error_code
            if error_msg is not None:
                updates["last_error_message"] = error_msg[:500] if error_msg else None
        if set_success:
            updates["last_success_at"] = now
        if set_refresh:
            refresh_at = serialize_business_datetime(
                now_kst() + timedelta(days=refresh_days)
            )
            updates["next_refresh_at"] = refresh_at

        # Increment attempt_count
        existing = (
            db.table("keco_collection_targets")
            .select("attempt_count,first_attempted_at")
            .eq("id", target_id)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            updates["attempt_count"] = (row.get("attempt_count") or 0) + 1
            if not row.get("first_attempted_at"):
                updates["first_attempted_at"] = now

        db.table("keco_collection_targets").update(updates).eq("id", target_id).execute()

    def mark_target_done(
        self,
        target_id: str,
        run_id: str,
        api_requests: int,
        source_items: int,
        refresh_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
    ) -> None:
        self._mark_target(
            target_id, run_id, TARGET_STATUS_DONE,
            api_requests=api_requests, source_items=source_items,
            set_success=True, set_refresh=True, refresh_days=refresh_days,
            clear_errors=True,
        )

    def mark_target_empty(
        self,
        target_id: str,
        run_id: str,
        api_requests: int,
        refresh_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
    ) -> None:
        self._mark_target(
            target_id, run_id, TARGET_STATUS_EMPTY,
            api_requests=api_requests, source_items=0,
            set_success=True, set_refresh=True, refresh_days=refresh_days,
            clear_errors=True,
        )

    def mark_target_conflict(
        self,
        target_id: str,
        run_id: str,
        api_requests: int,
        source_items: int,
        msg: str,
    ) -> None:
        self._mark_target(
            target_id, run_id, TARGET_STATUS_CONFLICT,
            api_requests=api_requests, source_items=source_items,
            error_code="CAS_MISMATCH", error_msg=msg,
        )

    def mark_target_retry(
        self,
        target_id: str,
        run_id: str,
        error_code: str,
        error_msg: str,
    ) -> None:
        self._mark_target(
            target_id, run_id, TARGET_STATUS_RETRY,
            error_code=error_code, error_msg=error_msg,
        )

    def mark_target_failed(
        self,
        target_id: str,
        run_id: str,
        error_code: str,
        error_msg: str,
    ) -> None:
        self._mark_target(
            target_id, run_id, TARGET_STATUS_FAILED,
            error_code=error_code, error_msg=error_msg,
        )

    def get_status_summary(self) -> dict:
        """target status 별 카운트 집계 (exact count 쿼리 사용)."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        statuses = [
            TARGET_STATUS_PENDING, TARGET_STATUS_RUNNING, TARGET_STATUS_DONE,
            TARGET_STATUS_EMPTY, TARGET_STATUS_RETRY, TARGET_STATUS_FAILED,
            TARGET_STATUS_CONFLICT,
        ]
        counts: dict = {}
        for status in statuses:
            result = (
                db.table("keco_collection_targets")
                .select("id", count="exact")
                .eq("status", status)
                .execute()
            )
            counts[status] = result.count or 0
        counts["total"] = sum(counts[s] for s in statuses)
        return counts

    def get_due_targets(self, max_targets: int) -> List[dict]:
        """next_refresh_at <= now のtarget を返す (DONE/EMPTY のみ)."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        now = _now_iso()
        rows = (
            db.table("keco_collection_targets")
            .select("id,target_type,target_value,attempt_count")
            .in_("status", [TARGET_STATUS_DONE, TARGET_STATUS_EMPTY])
            .lte("next_refresh_at", now)
            .order("next_refresh_at")
            .limit(max_targets)
            .execute()
        )
        return rows.data or []

    def has_active_run(self, run_type: Optional[str] = None) -> bool:
        """RUNNING run이 존재하면 True (lock check용).

        run_type 지정 시 해당 type만 확인. None이면 모든 RUNNING run.
        """
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        q = (
            db.table("keco_ingestion_runs")
            .select("id")
            .eq("status", "RUNNING")
        )
        if run_type:
            q = q.eq("run_type", run_type)
        rows = q.limit(1).execute()
        return bool(rows.data)

    def get_run(self, run_id: str) -> Optional[dict]:
        """run_id로 단일 run row 반환. 없으면 None."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        rows = (
            db.table("keco_ingestion_runs")
            .select("*")
            .eq("id", run_id)
            .limit(1)
            .execute()
        )
        return rows.data[0] if rows.data else None
