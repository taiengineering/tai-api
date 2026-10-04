"""KECO Reference Supabase (LEG DB) 저장 서비스.

환경변수:
  LEG_SUPABASE_URL               LEG DB URL
  LEG_SUPABASE_SERVICE_ROLE_KEY  service role key

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
from typing import Optional, Tuple

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
class KecoReferenceStore:
    """LEG msds_ref schema 저장 서비스."""

    def upsert_chemical(
        self,
        raw_payload: dict,
        item: KecoChemicalItem,
        run_id: str,
    ) -> Tuple[str, Optional[str]]:
        """화학물질 upsert. (status, chemical_id) 반환.

        status: NEW | UNCHANGED | CHANGED
        duplicate raw = 0 보장 (source_record_id + payload_hash UNIQUE)
        korexst_raw 그대로 저장 (ke_no 변환 금지)
        """
        client = _get_supabase_client()
        source_record_id = item.sbstn_id or ""
        content_hash = chemical_content_hash(item)
        raw_hash = _raw_payload_hash(raw_payload)

        # --- keco_raw_records upsert (duplicate = 0) ---
        existing_raw = (
            client.table("msds_ref.keco_raw_records")
            .select("id")
            .eq("source_record_id", source_record_id)
            .eq("payload_hash", raw_hash)
            .execute()
        )
        if not existing_raw.data:
            client.table("msds_ref.keco_raw_records").insert({
                "source_record_id": source_record_id,
                "raw_payload": raw_payload,
                "payload_hash": raw_hash,
                "first_seen_run_id": run_id,
                "last_seen_run_id": run_id,
            }).execute()
        else:
            client.table("msds_ref.keco_raw_records").update({
                "last_seen_run_id": run_id,
            }).eq("source_record_id", source_record_id).eq("payload_hash", raw_hash).execute()

        # --- keco_chemicals upsert ---
        existing = (
            client.table("msds_ref.keco_chemicals")
            .select("id,source_content_hash")
            .eq("source_record_id", source_record_id)
            .execute()
        )

        if not existing.data:
            result = client.table("msds_ref.keco_chemicals").insert({
                "source_record_id": source_record_id,
                "cas_no": item.cas_no,
                "korexst_raw": item.korexst_raw,       # 원문 보존
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
            # last_seen_at 갱신
            client.table("msds_ref.keco_chemicals").update({
                "last_seen_at": "now()",
            }).eq("id", chemical_id).execute()
            return STATUS_UNCHANGED, chemical_id

        # hash 변경 — last_changed_at update
        client.table("msds_ref.keco_chemicals").update({
            "cas_no": item.cas_no,
            "korexst_raw": item.korexst_raw,
            "chemical_name_ko": item.sbstn_nm_kor,
            "chemical_name_en": item.sbstn_nm_eng,
            "alias_name_ko": item.sbstn_nm2_kor,
            "alias_name_en": item.sbstn_nm2_eng,
            "molecular_formula": item.mlcfrm,
            "molecular_weight_raw": item.mlcwgt,
            "source_content_hash": content_hash,
            "last_changed_at": "now()",
            "last_seen_at": "now()",
            "updated_at": "now()",
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
        inserted = 0
        for ordinal, fact in enumerate(type_list):
            fact_h = regulatory_fact_hash(fact)
            existing = (
                client.table("msds_ref.keco_regulatory_facts")
                .select("id")
                .eq("keco_chemical_id", chemical_id)
                .eq("fact_hash", fact_h)
                .execute()
            )
            if existing.data:
                continue
            client.table("msds_ref.keco_regulatory_facts").insert({
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
