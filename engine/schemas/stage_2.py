"""Stage 2 입출력 schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Stage2Input(BaseModel):
    """Stage 1 출력 = Stage 2 입력."""

    clauses: list[dict[str, Any]] = Field(default_factory=list)


class Stage2Output(BaseModel):
    """Stage 2 출력 — stage_2_elements 형태 dict 리스트."""

    elements: list[dict[str, Any]] = Field(default_factory=list)
