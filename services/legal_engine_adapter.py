"""
legal_engine_adapter — 법령엔진 어댑터 (45cm 생태계 표준 계약 변환).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md
근거: 45cminc/development-governance (evaluation-core 표준 계약 actor/action/scope).

역할 (이것만): 도메인 입력 → 생태계 표준 계약(EvaluationContext)으로 변환.
- 의미절(semantic_clause) 1건 → 표준 계약 1건 (executor→actor, action_text→action,
  condition→scope, content_type→action.type, source_article_id→targets)
- 사용자 입력(섹터/인원/금액 등) → scope / actor.attributes

원칙:
- 엔진 코어는 Domain-agnostic. 이 어댑터가 도메인(법령) 지식을 짊어진다.
- 법령 특화 판정(수범자가 사업주냐 소방업자냐, 조건 충족 여부)은 여기(어댑터)에 격리.
  엔진 코어엔 넣지 않는다. 지식 판정에 LLM이 필요하면 이 어댑터/별도 검증단계에서.
- 변환만 한다. 엔진이 어떻게 평가·정리·출력하는지는 이 파일 밖(표준만 넣으면 엔진이 함).
- 분해기·판정로직(GPT 영역) 무수정. 의미절 데이터 읽기만(수정 X).

표준 계약 형식 (evaluation-core/contracts.ts EvaluationContext):
  actor   : {id, type, identity, roles[], attributes{}}
  action  : {type, operation, targets[{resource, resourceType, namespace}], reason, metadata{}}
  scope   : {namespaces[], resources[], boundaries{maxTargets, crossNamespace}}
  environment : {name, frozen}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ADAPTER_ID = "tai-legal-engine"
ADAPTER_VERSION = "v1"
POLICY_NAMESPACE = "legal"
SUPPORTED_ACTION_TYPES = ("OBLIGATION", "PROHIBITION")

# content_type 중 의무로 다루는 것 (벌칙/정의/위임/효력 제외)
_OBLIGATION_CONTENT_TYPES = frozenset({"OBLIGATION", "PROHIBITION"})


def clause_to_context(
    clause: Dict[str, Any],
    facility_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """의미절 1건 → 표준 EvaluationContext 1건.

    facility_context(사용자 입력 표준화 결과)가 주어지면 scope/actor.attributes에 사업장
    정보를 함께 싣는다(엔진이 의무의 수범자/조건을 사업장과 대조할 수 있도록).

    의무가 아닌 의미절(content_type이 OBLIGATION/PROHIBITION이 아님)은 None 반환(제외).
    """
    content_type = (clause.get("content_type") or "").strip().upper()
    if content_type not in _OBLIGATION_CONTENT_TYPES:
        return None

    executor = (clause.get("executor_text") or "").strip()
    action_text = (clause.get("action_text") or "").strip()
    condition_text = (clause.get("condition_text") or "").strip()
    cycle_text = (clause.get("cycle_text") or "").strip()
    source_text = (clause.get("source_text") or "").strip()
    article_id = str(clause.get("source_article_id") or "").strip()
    part_id = str(clause.get("source_part_id") or "").strip()
    sector = (clause.get("sector") or "").strip().upper()

    fac = facility_context or {}

    # ── ACTOR (누가) : 의무의 수범자 = 보정된 executor_text ──
    actor: Dict[str, Any] = {
        "id": executor or "(미상)",
        "type": "service",          # 법령 의무의 주체는 사람 개인이 아닌 사업장/기관 단위 → service
        "identity": executor,
        "roles": [executor] if executor else [],
        "attributes": {
            # 사업장(사용자 입력) 속성 — 엔진이 "이 사업장이 이 수범자인가" 대조용
            "facility_sector": fac.get("sector") or sector,
            "worker_count": fac.get("worker_count") or fac.get("employee_count"),
            "construction_type": fac.get("construction_type"),
            "ksic_code": fac.get("ksic_code"),
        },
    }

    # ── ACTION (무엇을) : 의무 행위 ──
    action: Dict[str, Any] = {
        "type": content_type,                       # OBLIGATION / PROHIBITION
        "operation": action_text or "(행위 미상)",
        "targets": [
            {
                "resource": article_id,             # 법조문 = 의무의 출처(연결키)
                "resourceType": "law_article",
                "namespace": POLICY_NAMESPACE,
            }
        ],
        "reason": source_text[:300],                # 원문(왜 = 의무 근거)
        "metadata": {
            "clause_id": str(clause.get("id") or ""),
            "part_id": part_id,
            "cycle": cycle_text,
            "clause_sector": sector,
        },
    }

    # ── SCOPE (어디까지) : 적용 조건/범위 ──
    scope: Dict[str, Any] = {
        "namespaces": [POLICY_NAMESPACE],
        "resources": [article_id] if article_id else [],
        "boundaries": {
            "maxTargets": 1,
            "crossNamespace": False,
        },
        # 조건절(문장) — 엔진/정책이 사업장과 대조할 적용 요건
        "condition": condition_text,
    }

    return {
        "actor": actor,
        "action": action,
        "scope": scope,
        "environment": {
            "name": "tai-legal-engine",
            "frozen": False,
        },
    }


def facility_input_to_base(sector_raw: str, facility_context: Dict[str, Any]) -> Dict[str, Any]:
    """사용자 입력(표준화된 facility_context) → 평가 base(사업장 = 평가 주체 측).

    엔진이 의무(clause_to_context로 만든 것)들을 이 사업장 base와 대조한다.
    어댑터는 변환만; 대조 판정은 엔진/정책의 몫.
    """
    fac = facility_context or {}
    return {
        "actor": {
            "id": fac.get("company_id") or "anonymous-facility",
            "type": "service",
            "identity": fac.get("company_name") or "사업장",
            "roles": [],
            "attributes": {
                "sector": sector_raw,
                "worker_count": fac.get("worker_count") or fac.get("employee_count") or 0,
                "building_area": fac.get("building_area") or fac.get("total_floor_area") or 0,
                "construction_type": fac.get("construction_type"),
                "construction_amount": fac.get("construction_amount"),
                "subcontractor_worker_count": fac.get("subcontractor_worker_count"),
                "ksic_code": fac.get("ksic_code"),
            },
        },
        "environment": {"name": "tai-legal-engine", "frozen": False},
    }


def adapter_definition() -> Dict[str, Any]:
    """어댑터 정의 (생태계 AdapterRegistry 등록용 메타). 표준 계약 형식."""
    return {
        "id": ADAPTER_ID,
        "name": "TAI Legal Engine Adapter",
        "version": ADAPTER_VERSION,
        "supportedActionTypes": list(SUPPORTED_ACTION_TYPES),
        "policyNamespace": POLICY_NAMESPACE,
    }
