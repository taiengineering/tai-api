from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ParseArticleRequest(BaseModel):
    law_name: str = ""
    law_article: str = ""
    article_text: str = ""
    article_id: Optional[str] = None


class ParseBatchRequest(BaseModel):
    law_id: str
    skip_existing: bool = True
    max_articles: int = Field(50, ge=1, le=1000)


class AutoParseAndApproveRequest(BaseModel):
    secret: str
    law_id: str
    max_articles: int = Field(30, ge=1, le=500)
    auto_approve_threshold: int = Field(80, ge=0, le=100)


class ValidateMasterRequest(BaseModel):
    sector: str = "ALL"


class ReparseMasterRequest(BaseModel):
    secret: str
    sector: str = ""
    limit: int = Field(50, ge=1, le=500)
    fill_empty_only: bool = True
    rule_ids: List[str] = Field(default_factory=list)


class UpdateDraftRequest(BaseModel):
    draft_rule_id: Optional[str] = None
    obligation_type: Optional[str] = None
    sector: Optional[str] = None
    condition_code: Optional[str] = None
    condition_operator: Optional[str] = None
    condition_value: Optional[str] = None
    obligation_summary: Optional[str] = None
    penalty_summary: Optional[str] = None
    appointment_target: Optional[str] = None
    diagnosis_stage: Optional[int] = None
    reviewer_note: Optional[str] = None


class ReviewDraftRequest(BaseModel):
    rule_id: Optional[str] = None
    reviewer_note: Optional[str] = None
