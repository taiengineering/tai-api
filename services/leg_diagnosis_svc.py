"""services/leg_diagnosis_svc.py — WO-PIPE-004: LEG 전용 소비자 진단 (글루).

UI step1_body -> LEG Input Contract facility -> POST /rtm/evaluate -> full_result(LEG).
TAI Compiler Core 미경유. 실패 시 예외를 올린다(TAI fallback 금지).
rtm obligations(law_name/law_article/evidence/triggered_by)는 얇으므로,
headline/roi/risk_summary 등 TAI-rich 필드는 생성하지 않는다(임의값 금지). 후속 enrichment WO에서 보강.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from clients import leg_runtime_client as leg_client

# WO-CHECK-015: Production Result Builder Collector wiring (add-only, fail-safe import).
try:
    from services import collector_activation as _collector_activation
except Exception:
    _collector_activation = None

log = logging.getLogger("services.leg_diagnosis")

LEG_ENGINE_VERSION = "leg-runtime-v3"
LEG_RULE_SOURCE = "leg-prod"

# rtm 시스템 오류 — 소비자 결과로 위장하지 않고 예외로 올린다.
_SYSTEM_ERROR_STATUS = {"REPO_QUERY_ERROR", "INTERNAL_ERROR", "INPUT_REJECTED"}
_SYSTEM_ERROR_CODE = {"REPO_UNAVAILABLE", "INTERNAL", "INPUT_REJECTED"}


class LegDiagnosisError(RuntimeError):
    pass


def _obligation_to_key_item(o: Dict[str, Any]) -> Dict[str, Any]:
    """rtm obligation view -> key_obligations item. 값 생성 없음(law_name/article로 title만 구성)."""
    law = (o.get("law_name") or "").strip()
    art = (o.get("law_article") or "").strip()
    if law and art:
        title = "{} {}".format(law, art)
    elif law:
        title = law
    else:
        title = "관련 법령 의무"
    return {
        "title": title,
        "obligation_summary": title,
        "law_name": law,
        "law_article": art,
        "evidence": o.get("evidence"),
        "triggered_by": o.get("triggered_by"),
        "atom_id": o.get("atom_id"),
        "source_atom_ids": o.get("source_atom_ids"),
        "applicability": o.get("applicability") or "APPLICABLE",
        "source": "LEG",
    }


def run_leg_diagnosis(step1_body: Any) -> Dict[str, Any]:
    """LEG 전용 진단. 반환 = full_result(LEG). 실패 시 LegDiagnosisError/LegRuntimeError 전파."""
    facility = leg_client.build_facility(step1_body)
    data = leg_client.evaluate_rtm(facility)  # net/parse 실패시 LegRuntimeError

    status = data.get("status")
    error_code = data.get("error_code")
    if status in _SYSTEM_ERROR_STATUS or error_code in _SYSTEM_ERROR_CODE:
        raise LegDiagnosisError(
            "LEG runtime status={} code={} detail={}".format(status, error_code, data.get("error"))
        )

    obligations = data.get("obligations") or []
    key_obl = [_obligation_to_key_item(o) for o in obligations]

    law_names: List[str] = []
    for o in obligations:
        ln = (o.get("law_name") or "").strip()
        if ln and ln not in law_names:
            law_names.append(ln)

    full_result: Dict[str, Any] = {
        # ── LEG 식보 메타 ──
        "engine_family": "LEG",
        "engine_version": LEG_ENGINE_VERSION,
        "rule_source": LEG_RULE_SOURCE,
        "fallback_used": False,
        "leg_status": status,
        "leg_trace_id": data.get("trace_id"),
        # ── 소비자 계약(_build_standard_output 호환) ──
        "sector": getattr(step1_body, "sector", None),
        "applicable_count": data.get("obligation_count", len(obligations)),
        "key_obligations": key_obl,
        "applicable_laws": law_names,
        "law_badges": law_names,
        "rules": [],          # rtm낔 rule-table 미제공 → 빈 값(임의 생성 금지)
        "risk_level": None,   # LEG rtm 미산출 → None(위장 금지)
        "summary": None,
        # ── 원본 보존(추적성) ──
        "provenance": data.get("provenance"),
        "contract": data.get("contract"),
        "obligations_raw": obligations,
        "facility_used": facility,
    }
    log.info(
        "leg_diagnosis status=%s obligations=%d laws=%d",
        status, len(obligations), len(law_names),
    )
    # WO-CHECK-015: last enrichment stage — add ONLY check.collectors.{penalty,agency}.
    # add-only, fail-closed; never alters existing fields or breaks the runtime result.
    if _collector_activation is not None:
        try:
            full_result = _collector_activation.activate(full_result)
        except Exception:
            pass
    return full_result
