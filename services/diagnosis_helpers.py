import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

SOURCE_DIAGNOSIS = "DIAGNOSIS"

_KEY_OBLIGATIONS_LIMIT = 6
_LAW_BADGES_LIMIT = 18
_RULES_PREVIEW_LIMIT = 12

_PARTIAL_MESSAGE = (
    "일부 결과만 표시됩니다. 전체 법령·의무 목록은 로그인 후 확인할 수 있습니다."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _auto_tier(
    sector: str,
    floor_area: float = 0.0,
    contract_amount_eok: float = 0.0,
    user_tier: Optional[str] = None,
) -> str:
    if sector == "BUILDING":
        return "BUILDING_LARGE_V2" if (floor_area or 0) >= 5000 else "BUILDING_V2"
    if sector == "CONSTRUCTION":
        return "CONSTRUCTION_PREMIUM" if (contract_amount_eok or 0) >= 50 else "CONSTRUCTION"
    return user_tier or "INDUSTRY_V2"


def _ensure_source_on_rule_row(row: Any) -> dict:
    if not isinstance(row, dict):
        return {"source": SOURCE_DIAGNOSIS}
    out = dict(row)
    out.setdefault("source", SOURCE_DIAGNOSIS)
    return out


def _normalize_key_obligation_item(item: Any) -> dict:
    if isinstance(item, dict):
        out = dict(item)
        out.setdefault("source", SOURCE_DIAGNOSIS)
        if not (out.get("title") or "").strip():
            out["title"] = str(
                out.get("obligation_summary") or out.get("name") or out.get("description") or ""
            ).strip()
        return out
    text = str(item).strip()
    return {"title": text, "source": SOURCE_DIAGNOSIS}


def _source_rule_rows(rows: Any) -> list[dict]:
    if not isinstance(rows, list):
        return []
    return [_ensure_source_on_rule_row(r) for r in rows if isinstance(r, dict)]


def _build_standard_output(full: dict) -> dict:
    """Layer 5→6 표준 partial 출력 (익명/통합 공통)."""
    rules_raw = full.get("rules_table") or full.get("rules") or []
    rules_table = _source_rule_rows(rules_raw)
    rules_preview = rules_table[:_RULES_PREVIEW_LIMIT]
    key_obl = [
        _normalize_key_obligation_item(x) for x in (full.get("key_obligations") or [])
    ][:_KEY_OBLIGATIONS_LIMIT]

    return {
        "risk_level": full.get("risk_level"),
        "summary": full.get("summary"),
        "applicable_count": full.get("applicable_count"),
        "sector": full.get("sector"),
        "evaluated_at": full.get("evaluated_at"),
        "engine_version": full.get("engine_version"),
        "key_obligations": key_obl,
        "rules_table": rules_preview,
        "rules_preview": rules_preview,
        "law_badges": (full.get("law_badges") or [])[:_LAW_BADGES_LIMIT],
        "appointment_required": _source_rule_rows(full.get("appointment_required")),
        "inspection_required": _source_rule_rows(full.get("inspection_required")),
        "action_required": _source_rule_rows(full.get("action_required")),
        "report_required": _source_rule_rows(full.get("report_required")),
        "construction_summary": full.get("construction_summary"),
        "message": _PARTIAL_MESSAGE,
    }


def _build_partial(full: dict) -> dict:
    return _build_standard_output(full)
