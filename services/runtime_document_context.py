"""Runtime document evaluation context — deterministic DB + optional overrides.

facility_id 기준으로 facility_condition·runtime_facility_profile 값을 평탄화하여
conditional_rule 평가에 사용한다. AI 추론 없음.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from db.supabase_client import get_supabase


def build_runtime_context(
    facility_id: Optional[str],
    overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """document-runtime 조건 평가·바인딩에 쓰는 context dict.

    overrides가 있으면 동일 키를 덮어씀(시뮬레이션·QA용).
    """
    ctx: dict[str, Any] = {}
    if overrides:
        for k, v in overrides.items():
            if v is not None and v != "":
                ctx[k] = v
    if not facility_id:
        return ctx

    ctx.setdefault("facility_id", facility_id)

    sb = get_supabase()
    try:
        rows = (
            sb.table("facility_condition")
            .select("condition_field, condition_value")
            .eq("factory_id", facility_id)
            .execute()
        )
        for r in rows.data or []:
            key = r.get("condition_field")
            if key and key not in (overrides or {}):
                ctx[key] = r.get("condition_value")
    except Exception:
        pass

    try:
        prof = (
            sb.table("runtime_facility_profile")
            .select("*")
            .eq("id", facility_id)
            .limit(1)
            .execute()
        )
        if prof.data:
            row = prof.data[0]
            ovr = overrides or {}
            for k, v in row.items():
                if k in ("id",) or k in ovr:
                    continue
                if v is not None:
                    ctx.setdefault(k, v)
    except Exception:
        pass

    return ctx


def parse_context_overrides_json(raw: Optional[str]) -> dict[str, Any]:
    """요청 바디의 JSON 문자열을 dict로. 실패 시 빈 dict."""
    if not raw or not str(raw).strip():
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}
