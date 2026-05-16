"""Semantic Adapter — Legacy State → Canonical Operational Grammar.

기존 상태값을 운영 의미로 변환.
Watch/Governance/Notification/LLM 계층은 이 Adapter를 통해서만 Canonical Grammar을 소비.
Legacy 상태 직접 참조 금지.
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.semantic_adapter")

# In-memory cache
_mapping_cache: dict = {}


def _load_mappings(sb) -> dict:
    """legacy_state_mapping 로드 (\uce90\uc2dc)."""
    global _mapping_cache
    if _mapping_cache:
        return _mapping_cache
    try:
        resp = sb.table("legacy_state_mapping") \
            .select("source_table,legacy_key,legacy_value,canonical_event,severity,tenant_impact,recoverable,description") \
            .eq("enabled", True).execute()
        for r in (resp.data or []):
            key = f"{r['source_table']}::{r['legacy_key']}::{r['legacy_value']}"
            _mapping_cache[key] = r
    except Exception as e:
        logger.warning("Failed to load legacy mappings: %s", e)
    return _mapping_cache


def translate_state(
    sb,
    source_table: str,
    legacy_key: str,
    legacy_value: str,
) -> dict:
    """Legacy 상태값 → Canonical Operational Event.

    Returns:
        {
            "canonical_event": str,
            "severity": str,
            "tenant_impact": str,
            "recoverable": bool,
            "description": str,
            "mapped": bool  # True if mapping found
        }
    """
    mappings = _load_mappings(sb)
    key = f"{source_table}::{legacy_key}::{legacy_value}"

    if key in mappings:
        m = mappings[key]
        return {
            "canonical_event": m["canonical_event"],
            "severity": m["severity"],
            "tenant_impact": m["tenant_impact"],
            "recoverable": m["recoverable"],
            "description": m["description"],
            "mapped": True,
        }

    # Fallback: unmapped state
    return {
        "canonical_event": f"{source_table}_{legacy_key}_{legacy_value}".lower(),
        "severity": "INFO",
        "tenant_impact": "NONE",
        "recoverable": True,
        "description": f"Unmapped: {source_table}.{legacy_key}={legacy_value}",
        "mapped": False,
    }


def translate_record(
    sb,
    source_table: str,
    record: dict,
    key_fields: list[str] = None,
) -> dict:
    """\ub808\ucf54\ub4dc \uc804\uccb4\ub97c Canonical Context\ub85c \ubcc0\ud658.

    Returns:
        {
            "source_table": str,
            "events": [translated_state, ...],
            "context": {normalized LLM-friendly context},
        }
    """
    if key_fields is None:
        key_fields = _default_key_fields(source_table)

    events = []
    for kf in key_fields:
        val = record.get(kf)
        if val is not None:
            translated = translate_state(sb, source_table, kf, str(val))
            translated["legacy_key"] = kf
            translated["legacy_value"] = str(val)
            events.append(translated)

    # LLM-friendly context
    context = _build_llm_context(source_table, record, events)

    return {
        "source_table": source_table,
        "events": events,
        "context": context,
    }


def _default_key_fields(source_table: str) -> list[str]:
    """\ud14c\uc774\ube14\ubcc4 \uae30\ubcf8 \ub9e4\ud551 \ub300\uc0c1 \ud544\ub4dc."""
    defaults = {
        "payments": ["status_code"],
        "subscriptions": ["status"],
        "factory_process": ["is_active"],
        "generated_document": ["status"],
        "runtime_document_activation": ["status"],
        "diagnosis_session": ["status"],
        "engine_integrity_event": ["severity"],
    }
    return defaults.get(source_table, [])


def _build_llm_context(source_table: str, record: dict, events: list) -> dict:
    """LLM-friendly \uc815\uaddc\ud654 \ucee8\ud14d\uc2a4\ud2b8."""
    ctx = {
        "source": source_table,
        "operational_events": [
            {
                "event": e["canonical_event"],
                "severity": e["severity"],
                "tenant_impact": e["tenant_impact"],
                "recoverable": e["recoverable"],
            }
            for e in events if e.get("mapped")
        ],
    }

    # \ud14c\uc774\ube14\ubcc4 \ucee8\ud14d\uc2a4\ud2b8 \ubcf4\uac15
    if source_table == "payments":
        ctx["payment"] = {
            "status": record.get("status_code"),
            "plan": record.get("plan_code"),
            "amount": str(record.get("total_amount", "")),
            "product_type": record.get("product_type"),
        }
    elif source_table == "subscriptions":
        ctx["subscription"] = {
            "status": record.get("status"),
            "plan": record.get("plan_code"),
            "billing_cycle": record.get("billing_cycle"),
            "has_factory": bool(record.get("factory_id")),
        }
    elif source_table == "engine_integrity_event":
        ctx["incident"] = {
            "flow_key": record.get("flow_key"),
            "event_type": record.get("event_type"),
            "severity": record.get("severity"),
            "resolved": record.get("resolved"),
            "tenant_id": record.get("tenant_id"),
        }
    elif source_table == "generated_document":
        ctx["document"] = {
            "form_code": record.get("form_code"),
            "status": record.get("status"),
            "has_download": bool(record.get("download_url")),
            "flow_key": record.get("flow_key"),
        }

    return ctx


def invalidate_cache():
    """\uce90\uc2dc \ucd08\uae30\ud654 (\ub9e4\ud551 \ubcc0\uacbd \uc2dc)."""
    global _mapping_cache
    _mapping_cache = {}
