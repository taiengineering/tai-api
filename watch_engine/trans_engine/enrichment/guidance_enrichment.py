"""Guidance Enrichment."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.response_guidance import enrich_snapshot_guidance

def apply_guidance_enrichment(snapshot: dict[str, Any]) -> dict[str, Any]:
    return enrich_snapshot_guidance(snapshot)
