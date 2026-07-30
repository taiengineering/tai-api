"""Feature flag for the Canonical diagnosis pipeline.

CANONICAL_PIPELINE (default OFF). When OFF, all routers behave exactly as before.
"""
from __future__ import annotations

import os

_TRUE = ("1", "true", "yes", "on")


def canonical_enabled() -> bool:
    return os.getenv("CANONICAL_PIPELINE", "").strip().lower() in _TRUE
