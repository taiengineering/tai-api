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
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from services.keco_chemical.contract import SOURCE_CONTRACT_VERSION, SOURCE_ID
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


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            "started_at": _utcnow_iso(),
        }).execute()
        return result.data[0]["id"]

    def complete_run(
        self,
        run_id: str,
        request_count: int,
        record_count: int,
        metrics_json: Optional[dict] = None,
    ) -> None:
        """run을 COMPLETED로 마감."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        db.table("keco_ingestion_runs").update({
            "status": "COMPLETED",
            "completed_at": _utcnow_iso(),
            "request_count": request_count,
            "record_count": record_count,
            "metrics_json": metrics_json,
        }).eq("id", run_id).execute()

    def fail_run(
        self,
        run_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """run을 FAILED로 마감. serviceKey error_message에 포함 금지."""
        client = _get_supabase_client()
        db = client.schema("msds_ref")
        db.table("keco_ingestion_runs").update({
            "status": "FAILED",
            "completed_at": _utcnow_iso(),
            "error_code": error_code,
            "error_message": error_message,
        }).eq("id", run_id).execute()

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
        now = _utcnow_iso()

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
        """단일 항목 저장 orchestration: raw → chemical → facts 순서 보장.

        Returns:
            PersistItemResult(status, chemical_id, inserted_fact_count)
        """
        status, chemical_id = self.upsert_chemical(raw_payload, item, run_id)
        inserted_fact_count = 0
        if chemical_id is not None:
            inserted_fact_count = self.upsert_regulatory_facts(chemical_id, item.type_list)
        return PersistItemResult(
            status=status,
            chemical_id=chemical_id,
            inserted_fact_count=inserted_fact_count,
        )
