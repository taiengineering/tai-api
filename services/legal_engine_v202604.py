"""
services/legal_engine_v202604.py — v1.0.0

BE-06-final: legal_engine.py INSERT 경로 v2026.04 래퍼

주요 함수:
  wrap_result_to_v202604(sector, stage, input_data, legacy_result, rule_count)
  → v2026.04 표준 result_data dict 반환

안전장치:
  - Pydantic 검증 실패 시 500 오류 + 로깅 (조용한 fallback 금지)
  - evidence[] 결정론적: 알파벳 오름차순, source·factory_id 제외, 상위 5개
  - severity: risk_summary 기반 → rule_count 추정 (100≥=HIGH, 50≥=MEDIUM, else LOW)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ── tier 정규화 맵 ───────────────────────────────────────────────────────────
TIER_NORMALIZE = {
    'PAID_FULL':         'PAID',
    'PAID1_FACILITY':    'PAID1',
    'PAID2_PROCESS':     'PAID2',
    'PAID3_EQUIPMENT':   'PAID3',
}
VALID_TIERS    = frozenset({'FREE', 'PAID', 'PAID1', 'PAID2', 'PAID3'})
VALID_SECTORS  = frozenset({'BUILDING', 'INDUSTRY', 'CONSTRUCTION'})
VALID_SEVERITY = frozenset({'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'})

# ── evidence[] 선택 기준 (BE-06 기획창 승인): 알파벳 오름차순, 제외 키 제외, 상위 5개
EVIDENCE_EXCLUDE_KEYS = frozenset({'source', 'factory_id'})
EVIDENCE_MAX = 5


def _normalize_tier(raw_tier: str | None, stage: int) -> str:
    t = (raw_tier or '').strip().upper()
    t = TIER_NORMALIZE.get(t, t)
    if t in VALID_TIERS:
        return t
    return 'PAID' if stage >= 2 else 'FREE'


def _normalize_sector(raw_sector: str | None, column_sector: str) -> str:
    s = (raw_sector or column_sector or '').strip().upper()
    if s == 'MANUFACTURING':
        return 'INDUSTRY'
    return s if s in VALID_SECTORS else column_sector.strip().upper()


def _build_evidence(input_data: dict | None) -> list:
    """
    결정론적 evidence[] 생성.
    알파벳 오름차순으로 source·factory_id 제외 후 상위 5개를
    "input.{key}={value}" 형식으로 이문화.
    재실행 시 동일한 결과가 카라포됨 (stable sort).
    """
    if not input_data or not isinstance(input_data, dict):
        return []
    keys = sorted(k for k in input_data.keys() if k not in EVIDENCE_EXCLUDE_KEYS)
    return [
        f'input.{k}={input_data[k]}'
        for k in keys[:EVIDENCE_MAX]
    ]


def _build_severity(risk_summary: dict | None, rule_count: int) -> str:
    """
    Q3 확정 로직:
      risk_summary.critical > 0 → CRITICAL
      risk_summary.high     > 0 → HIGH
      risk_summary.medium   > 0 → MEDIUM
      risk_summary.low      > 0 → LOW
      없으면 rule_count 기반 추정: >=100=HIGH, >=50=MEDIUM, else LOW
    """
    if isinstance(risk_summary, dict):
        if int(risk_summary.get('critical', 0) or 0) > 0: return 'CRITICAL'
        if int(risk_summary.get('high',     0) or 0) > 0: return 'HIGH'
        if int(risk_summary.get('medium',   0) or 0) > 0: return 'MEDIUM'
        if int(risk_summary.get('low',      0) or 0) > 0: return 'LOW'
    rc = rule_count or 0
    if rc >= 100: return 'HIGH'
    if rc >= 50:  return 'MEDIUM'
    return 'LOW'


def _safe_array(val: Any) -> list:
    if isinstance(val, list): return val
    return []


def _merge_warnings(legacy: dict) -> list:
    """warnings/urgent_action_items/construction_specific_tips/age_warnings 통합"""
    result = list(_safe_array(legacy.get('warnings')))
    for item in _safe_array(legacy.get('urgent_action_items')):
        result.append({'code': 'URGENT', 'message': str(item) if not isinstance(item, dict) else item.get('message', str(item)), 'level': 'HIGH'})
    for item in _safe_array(legacy.get('construction_specific_tips')):
        result.append({'code': 'CONSTRUCTION_TIP', 'message': str(item), 'level': 'INFO'})
    age = legacy.get('age_warnings')
    if isinstance(age, list):
        for item in age:
            result.append({'code': 'AGE_WARNING', 'message': str(item), 'level': 'HIGH'})
    elif isinstance(age, dict):
        for k, v in age.items():
            if k != 'age_years' and v is not None:
                result.append({'code': 'AGE_WARNING', 'message': f'{k}: {v}', 'level': 'HIGH'})
    return result


def _merge_obligations(legacy: dict) -> list:
    """obligations > key_obligations > mandatory_obligations > critical_obligations 우선순위"""
    for key in ('obligations', 'key_obligations', 'mandatory_obligations', 'critical_obligations'):
        val = legacy.get(key)
        if isinstance(val, list) and val:
            return val
    return []


def wrap_result_to_v202604(
    sector: str,
    stage: int,
    input_data: dict | None,
    legacy_result: dict,
    rule_count: int,
) -> dict:
    """
    legacy result_data를 v2026.04 표준 형식으로 전환.

    연동 지점:
      - legal_engine.py diagnose_step1 INSERT 직전
      - legal_engine.py _save_diagnosis_result INSERT 직전

    안전장치:
      - 변환 실패 시 HTTPException(500) raise — silently fallback 금지
      - Pydantic 검증은 코드 모델로 수행 (올라첨 jsonschema 의존성 제거)
    """
    from fastapi import HTTPException

    if not isinstance(legacy_result, dict):
        log.error('[v202604] legacy_result가 dict가 아님: %s', type(legacy_result))
        raise HTTPException(status_code=500, detail='[BE-06] result_data 형식 오류: dict여야 함')

    try:
        # --- Rule 1: tier 정규화 ---
        tier = _normalize_tier(legacy_result.get('tier'), stage)

        # --- Rule 2: sector 교정 (MANUFACTURING → INDUSTRY) ---
        norm_sector = _normalize_sector(legacy_result.get('sector'), sector)

        # --- generated_at ---
        generated_at = (
            legacy_result.get('evaluated_at')
            or datetime.now(timezone.utc).isoformat()
        )

        # --- Rule 6: risk_summary 표준화 ---
        raw_rs = legacy_result.get('risk_summary')
        risk_summary: dict = (
            raw_rs if isinstance(raw_rs, dict)
            else {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        )

        # --- Q3: severity 판정 ---
        severity = _build_severity(risk_summary, rule_count)

        # --- headline ---
        headline_msg = (
            legacy_result.get('headline_message')
            or (legacy_result.get('summary', {}) or {}).get('headline')
            or f'적용된 의무 {rule_count}건 발걸'
        )

        # --- Rule 4: obligations 통합 ---
        obligations = _merge_obligations(legacy_result)

        # --- Rule 5: rule_count 분리 ---
        rule_count_total = int(
            legacy_result.get('total_rules_checked')
            or legacy_result.get('applicable_count')
            or rule_count
            or 0
        )
        rule_count_shown = len(obligations)

        # --- Rule 3: warnings 통합 ---
        warnings = _merge_warnings(legacy_result)

        # --- Rule 11: evidence[] 결정론적 생성 ---
        evidence = _build_evidence(input_data)

        # --- applicable_laws ---
        applicable_laws = _safe_array(legacy_result.get('applicable_laws'))

        # --- v2026.04 표준 dict 구성 (기존 키 전체 보존 + 신규 키 오버라이드) ---
        v2 = dict(legacy_result)  # 기존 키 전체 보존 (additionalProperties)
        v2.update({
            'schema_version':  '2026.04',
            'tier':            tier,
            'sector':          norm_sector,
            'generated_at':    generated_at,
            'valid_until':     None,
            'headline':        {'summary': str(headline_msg), 'severity': severity},
            'applicable_laws': applicable_laws,
            'obligations':     obligations,
            'risk_summary':    risk_summary,
            'warnings':        warnings,
            'rule_count_total': rule_count_total,
            'rule_count_shown': rule_count_shown,
            'evidence':        evidence,
            'next_actions':    _safe_array(legacy_result.get('next_actions')),
            # Rule 8: _legacy_process_hazards 보존
            '_legacy_process_hazards': legacy_result.get('process_hazards'),
        })

        # --- Pydantic 검증 ---
        try:
            from app.models.diagnosis_result import DiagnosisResultV202604
            DiagnosisResultV202604.model_validate(v2)
            log.info('[v202604] Pydantic 검증 통과 (sector=%s, stage=%d, obligations=%d건)',
                     norm_sector, stage, len(obligations))
        except Exception as pydantic_err:
            log.error('[v202604] Pydantic 검증 실패: %s', pydantic_err)
            raise HTTPException(
                status_code=500,
                detail=f'[BE-06] v2026.04 스키마 검증 실패: {pydantic_err}'
            )

        return v2

    except HTTPException:
        raise
    except Exception as e:
        log.error('[v202604] 예상치 못한 오류: %s', e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f'[BE-06] result_data v2026.04 변환 실패: {e}'
        )
