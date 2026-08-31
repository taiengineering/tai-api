"""Explicit enable gate. Default OFF so cutover enable is a deliberate env change."""
from __future__ import annotations

import os

_TRUE = frozenset({"1", "true", "yes", "on"})


def scheduler_enabled() -> bool:
    raw = (os.environ.get("TAI_SCHEDULER_ENABLED") or "").strip().lower()
    return raw in _TRUE
