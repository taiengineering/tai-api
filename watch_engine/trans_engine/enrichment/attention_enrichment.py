"""Attention Enrichment."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.attention_engine import enrich_snapshot_attention

def apply_attention_enrichment(snapshot: dict[str, Any]) -> dict[str, Any]:
    return enrich_snapshot_attention(snapshot)
