"""Environment Utils — 환경 공통 유틸."""
from __future__ import annotations
from typing import Any

def is_mock_environment(events: list[dict[str, Any]]) -> bool:
    return any(e.get("is_mock") or e.get("source") == "synthetic" for e in events)

def detect_environment(events: list[dict[str, Any]]) -> str:
    return "mock" if is_mock_environment(events) else "production"

def normalize_environment(env: str | None) -> str | None:
    if not env: return None
    env = env.lower().strip()
    if env in ("mock", "synthetic", "syn"): return "mock"
    if env in ("production", "prod"): return "production"
    return env
