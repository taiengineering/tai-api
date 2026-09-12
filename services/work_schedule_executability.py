"""STAGE 1 — work_schedules executability hard gate (Definition §6-7-10-O/P).

LIFECYCLE (status_code) ≠ EXECUTABILITY (active_yn).

ACTIVE_EXECUTABLE := active_yn IS TRUE (exact) AND consumer-allowed lifecycle.

This module only applies the active_yn axis at the DB query boundary.
It does not write active_yn=false and does not change status semantics.
"""
from __future__ import annotations

from typing import Any


def require_active_executable(query: Any) -> Any:
    """Fail-close: only rows with active_yn exact TRUE are executable."""
    return query.eq("active_yn", True)
