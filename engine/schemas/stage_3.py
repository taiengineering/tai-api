"""Stage 3 입출력 schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Stage3Input(BaseModel):
    """Stage 2 출력 = Stage 3 입력."""

    elements: list[dict[str, Any]] = Field(default_factory=list)


class Stage3Output(BaseModel):
    """Stage 3 출력 — stage_3_objects 형태 dict 리스트."""

    objects: list[dict[str, Any]] = Field(default_factory=list)
