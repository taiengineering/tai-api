"""Learning Service — 공통 learning 조회."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.effectiveness_analyzer import analyze_effective_actions, analyze_recurring_patterns
from watch_engine.trans_engine.learning_registry import build_learning_registry
from watch_engine.trans_engine.operational_memory import build_operational_memory

async def get_effective_actions(env: str | None = None) -> list[dict]:
    return await analyze_effective_actions(environment=env)

async def get_recurring_patterns(env: str | None = None) -> list[dict]:
    return await analyze_recurring_patterns(environment=env)

async def get_learning_memory(env: str | None = None) -> list[dict]:
    return await build_learning_registry(environment=env)

async def get_situation_learning(situation_id: str) -> dict[str, Any]:
    return await build_operational_memory(situation_id)
