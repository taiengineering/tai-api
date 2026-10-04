"""KECO Reference DB row 모델 (LEG msds_ref schema)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class KecoIngestionRunRow:
    id: str
    source_id: str
    run_type: str
    status: str
    search_gubun: str
    search_nm: str
    request_count: int
    record_count: int
    started_at: str
    completed_at: Optional[str]
    source_contract_version: str
    error_code: Optional[str]
    error_message: Optional[str]
    metrics_json: Optional[dict]


@dataclass
class KecoRawRecordRow:
    id: str
    source_record_id: str
    raw_payload: dict
    payload_hash: str
    first_seen_at: str
    last_seen_at: str
    last_changed_at: str
    first_seen_run_id: str
    last_seen_run_id: str


@dataclass
class KecoChemicalRow:
    id: str
    source_record_id: str          # = sbstnId
    cas_no: Optional[str]
    korexst_raw: Optional[str]     # 기존화학물질번호 원문 — KE번호 변환 금지
    chemical_name_ko: Optional[str]
    chemical_name_en: Optional[str]
    alias_name_ko: Optional[str]
    alias_name_en: Optional[str]
    molecular_formula: Optional[str]
    molecular_weight_raw: Optional[str]
    source_content_hash: str
    first_seen_at: str
    last_seen_at: str
    last_changed_at: str
    created_at: str
    updated_at: str


@dataclass
class KecoRegulatoryFactRow:
    id: str
    keco_chemical_id: str          # FK → keco_chemicals.id
    classification_type: Optional[str]
    unique_no: Optional[str]
    content_info: Optional[str]
    exception_info: Optional[str]
    notice_date_raw: Optional[str]
    notice_info: Optional[str]
    fact_hash: str
    source_ordinal: int
    created_at: str
    updated_at: str
