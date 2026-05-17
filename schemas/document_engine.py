"""TAI 문서엔진 스키마 v1.0.0"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


# ─── Request ───

class DocumentCreateIn(BaseModel):
    form_schema_id: str
    factory_id: Optional[str] = None
    company_id: Optional[str] = None
    created_by: Optional[str] = None


class DocumentUpdateIn(BaseModel):
    runtime_data_json: Optional[Dict[str, Any]] = None
    evidence_links: Optional[List[dict]] = None
    updated_by: Optional[str] = None


class StatusChangeIn(BaseModel):
    to_status: str
    actor_id: Optional[str] = None
    comment: Optional[str] = None


class EvidenceLinkIn(BaseModel):
    evidence_type: str
    storage_path: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    linked_field_id: Optional[str] = None
    uploaded_by: Optional[str] = None


class GenerateDocumentIn(BaseModel):
    export_type: str = "HTML"
