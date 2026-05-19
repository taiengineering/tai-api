"""Archive Policy — 보존 정쇅 정의."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class RetentionConfig:
    archive_days: int = 30
    summarize_days: int = 90
    delete_days: int = 180

DEFAULT_POLICY = RetentionConfig()
