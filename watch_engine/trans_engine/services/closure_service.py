"""Closure Service — 공통 closure 조회."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.closure_workflow import (
    get_open_situations, get_followup_situations,
    get_closure_history, get_operator_history,
)
from watch_engine.trans_engine.operational_closure import close_operational_situation

async def resolve_situation(**kwargs) -> dict[str, Any] | None:
    return await close_operational_situation(**kwargs)

async def get_open(env: str | None = None) -> list[dict]:
    return await get_open_situations(environment=env)

async def get_followup(env: str | None = None) -> list[dict]:
    return await get_followup_situations(environment=env)

async def get_history(situation_id: str) -> list[dict]:
    return await get_closure_history(situation_id)

async def get_operator(operator_id: str, limit: int = 30) -> list[dict]:
    return await get_operator_history(operator_id, limit)
