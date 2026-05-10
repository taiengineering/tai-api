"""Stage 1 입출력 schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Stage1Part(BaseModel):
    """단일 law_article_part 단위 입력."""

    part_id: str
    part_text: str


class Stage1Input(BaseModel):
    """Stage 1 입력 — part 목록."""

    parts: list[Stage1Part] = Field(default_factory=list)


class Stage1Output(BaseModel):
    """Stage 1 출력 — stage_1_clauses 형태 dict 리스트."""

    clauses: list[dict[str, Any]] = Field(default_factory=list)
