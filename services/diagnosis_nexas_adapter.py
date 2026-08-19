"""Nexas free/paid diagnosis — FE form_data ↔ DiagnosisRunBody, 응답 shape 정규화."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from schemas.diagnosis_integrated import DiagnosisRunBody

# form_data 키 → DiagnoseStep1Body 필드
_FORM_ALIASES: Dict[str, str] = {
    "workers": "worker_count",
    "ksic_code": "ksic_major",
    "project_address": "region",
    "address": "region",
    "project_amount": "contract_amount_eok",
}

_NUMERIC_FIELDS = frozenset(
    {
        "floor_area",
        "total_floor_area",
        "contract_amount_eok",
        "worker_count",
        "employee_count",
        "direct_workers",
        "subcon_workers",
        "gas_capacity_kg",
        "gas_capacity_m3",
        "boiler_capacity_kw",
        "annual_energy_toe",
        "electrical_capacity_kw",
        "elevator_count",
        "floor_count",
        "electric_capacity",
    }
)


def _coerce_value(key: str, val: Any) -> Any:
    if val is None or val == "":
        return None
    if key in _NUMERIC_FIELDS:
        try:
            return float(val) if key in ("floor_area", "total_floor_area", "contract_amount_eok") else int(float(val))
        except (TypeError, ValueError):
            return val
    if isinstance(val, bool):
        return val
    if isinstance(val, (list, dict)):
        return val
    return val


def nexas_run_body_from_request(raw: Dict[str, Any]) -> DiagnosisRunBody:
    """Nexas POST /diagnosis/run JSON → DiagnosisRunBody (tier·form_data 병합)."""
    payload = dict(raw)
    form_data = payload.pop("form_data", None) or {}
    tier = (payload.pop("tier", None) or "").strip().upper()
    _industry_tier = {
        "BASIC": "INDUSTRY_V2",
        "STANDARD": "INDUSTRY_STANDARD",
        "PREMIUM": "INDUSTRY_PREMIUM",
        "PAID": None,
    }
    if not payload.get("user_tier") and tier in _industry_tier and _industry_tier[tier]:
        payload["user_tier"] = _industry_tier[tier]

    if tier == "FREE" and not payload.get("payment_ref"):
        payload.setdefault("payment_ref", None)

    if form_data and isinstance(form_data, dict):
        for code, val in form_data.items():
            target = _FORM_ALIASES.get(code, code)
            if target not in DiagnosisRunBody.model_fields:
                continue
            coerced = _coerce_value(target, val)
            if coerced is None:
                continue
            if payload.get(target) is None:
                payload[target] = coerced

    # Phase 1 lossless canonical materialization
    # (WO-GATE8-CANONICAL-LOSSLESS-MATERIALIZATION-IMPLEMENT-01):
    # DiagnosisRunBody 로 선언되지 않은 RTM-vocab applicability(has_confined_space 등)는
    # 위 declared-merge 에서 탈락한다. 이를 body.form_data 에 vocab-allowlist 로 보존해
    # run_diagnosis 가 DiagnoseStep1Body.input 으로 손실 없이 전달하게 한다.
    # alias/derivation/값 생성 없음(정확 이름만).
    from services.canonical.materialization import canonical_applicability

    _preserved = canonical_applicability(form_data)
    if _preserved:
        payload["form_data"] = _preserved

    body = DiagnosisRunBody(**payload)
    return body


def rules_table_to_obligations(full_result: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
    """무료 진단 인라인 UI용 obligations 목록."""
    out: List[Dict[str, Any]] = []
    for r in full_result.get("rules_table") or []:
        if not isinstance(r, dict):
            continue
        law_ref = " ".join(p for p in ((r.get("law_name") or "").strip(), (r.get("law_article") or "").strip()) if p)
        title = (r.get("obligation_summary") or r.get("description") or r.get("what") or "의무사항").strip()
        out.append(
            {
                "title": title,
                "name": title,
                "obligation_name": title,
                "law_reference": law_ref,
                "law": r.get("law_name") or "",
                "category": r.get("category") or r.get("rule_kind_label") or "",
                "who": r.get("who") or "",
                "what": r.get("what") or "",
                "when": r.get("when") or "",
            }
        )
        if len(out) >= limit:
            break
    if not out:
        for ob in full_result.get("key_obligations") or []:
            if isinstance(ob, dict):
                out.append(ob)
            if len(out) >= limit:
                break
    return out


def build_nexas_run_response(svc_result: Dict[str, Any]) -> Dict[str, Any]:
    """diagnosis_integrated_svc 반환 → Nexas FE 기대 { status, data: { obligations, public_token, ... } }."""
    full = svc_result.get("result") or {}
    obligations = rules_table_to_obligations(full)
    preview = obligations[5:] if len(obligations) > 5 else []

    data: Dict[str, Any] = {
        "public_token": svc_result.get("public_token"),
        "diagnosis_id": svc_result.get("diagnosis_id"),
        "tier_code": svc_result.get("tier_code"),
        "is_free": svc_result.get("is_free"),
        "expires_at": svc_result.get("expires_at"),
        "free_remaining_after": svc_result.get("free_remaining_after"),
        "obligations": obligations,
        "results": obligations,
        "items": obligations,
        "unconfirmed": full.get("unconfirmed") or full.get("blind_spots") or [],
        "paid_preview": preview,
        "risk_level": full.get("risk_level"),
        "applicable_count": full.get("applicable_count"),
        "summary": full.get("summary"),
        "engine_version": full.get("engine_version"),
        "rules_table": full.get("rules_table") or [],
        "pdf_url": svc_result.get("pdf_url") or full.get("pdf_url"),
    }
    return {
        "status": svc_result.get("status") or "success",
        "data": data,
        "public_token": svc_result.get("public_token"),
        "diagnosis_id": svc_result.get("diagnosis_id"),
        "tier_code": svc_result.get("tier_code"),
        "is_free": svc_result.get("is_free"),
        "result": full,
    }
