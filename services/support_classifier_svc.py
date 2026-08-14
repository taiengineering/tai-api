# -*- coding: utf-8 -*-
"""TAI 고객응대 — 질문 분류기(트랙 B 최소 구현).

책임(단일): question + 최소 safe context → type_code / subtype_code 분류.
이 파일은 '분류'만 한다. routing/answer/권한/DB/ACTION 은 하지 않는다.

호출 시점(고정): 최종 HANDOFF 가 확정된 뒤, inquiry 저장 직전에만.
  ANSWER/ASK 에서는 호출되지 않는다(호출측 member_support 가 보장).

경계(엄수):
  - READ scope = 0. DB/로그/권한/진단payload 를 조회하지 않는다.
  - resolution_axis 를 만들지 않는다(서버가 HANDOFF 로 확정).
  - 설명/추론/CoT/ACTION 추천/READ 요청/customer data 를 출력하지 않는다.
  - LLM 출력은 절대 그대로 저장하지 않는다 — 서버가 support_taxonomy 로 검증 후에만.

SoT 재사용: 가능한 code/label/parent_type 는 services.support_taxonomy 에서만 가져온다
  (36개 code 목록/label 복붙 금지).

LLM 재사용: 기존 support_answer_svc 와 동일 계열(OpenAI SDK, env OPENAI_API_KEY, chat.completions JSON).
  신규 provider/abstraction 없음. 호출은 주입 가능(llm_call), 미주입 시 기본 구현 지연 import.

실패 정책(best-effort): timeout/exception/invalid JSON/unknown code/mismatch/empty →
  classify() 는 None 을 반환한다(예외를 밖으로 던지지 않는다). 호출측은 None 이면 taxonomy 를
  NULL 로 두고 HANDOFF 저장을 계속한다. ERROR 승격/저장 취소/재시도 요구 금지.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from services import support_taxonomy

logger = logging.getLogger("support_classifier")

# 분류기 출력 계약(고정): type_code + subtype_code 만. 설명/축/추론 금지.
_LLM_SYSTEM = (
    "You classify a Korean TAI Safe support question into exactly one taxonomy type and subtype.\n"
    "You are given the allowed taxonomy (code, label, parent_type). Choose codes from it only.\n"
    "STRICT RULES:\n"
    "- Classify the QUESTION'S NATURE only. Do not answer, act, or make legal judgments.\n"
    "- Pick exactly one type_code and one subtype_code.\n"
    "- subtype_code MUST be a child of the chosen type_code (parent_type == type_code).\n"
    "- Do not output resolution_axis, explanation, reasoning, chain-of-thought, or any customer data.\n"
    "- Do not request to read anything.\n"
    "Boundary hints:\n"
    "- Plain status check -> T3; delay/stuck/abnormality claim -> T4 (T3_PROGRESS vs T4_PROCESSING).\n"
    "- Why something is blocked -> T5; request to enable/grant -> T7 (T5_ACTION_DISABLED vs T7_PERMISSION_ACCOUNT).\n"
    "- Why an existing result came out -> T2; what happens if changed -> T6.\n"
    "- How-to/next-step guidance -> T1_NEXT_STEP; my remaining tasks -> T3_TODO.\n"
    "- General result reason -> T2_RESULT_REASON; specific law application -> T2_LEGAL_REASON.\n"
    "- Future 'if I change input' impact -> T6_DIAGNOSIS_INPUT_CHANGE; past 'why different from before' -> T2_RESULT_DIFF.\n"
    'Return JSON only: {"type_code": "<Tx>", "subtype_code": "<Tx_...>"}'
)


def _build_taxonomy_brief() -> str:
    """support_taxonomy SoT 에서 code/label/parent_type 를 구조화 문자열로(복붙 아님, 파생)."""
    lines: List[str] = ["types:"]
    for t in support_taxonomy.TYPES:
        lines.append(f"  {t['code']} = {t['label']}")
    lines.append("subtypes (code | parent_type | label):")
    for s in support_taxonomy.SUBTYPES:
        lines.append(f"  {s['code']} | {s['parent_type']} | {s['label']}")
    return "\n".join(lines)


def _default_llm_call(system_msg: str, user_msg: str) -> str:
    """기존 support_answer_svc 와 동일 provider·설정 재사용(OpenAI gpt-4o, JSON). raw 문자열 반환."""
    import os
    from openai import OpenAI  # 지연 import
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _safe_context_line(safe_context: Optional[Dict[str, Any]]) -> str:
    """분류에 필요한 최소 context 만 문자열로. 원문 id/payload 는 넣지 않는다.

    허용: page_url, object_type, has_factory(bool). 그 외는 무시한다(전달 금지 항목 차단).
    """
    if not isinstance(safe_context, dict):
        return ""
    bits: List[str] = []
    page_url = safe_context.get("page_url")
    if isinstance(page_url, str) and page_url.strip():
        bits.append(f"page_url={page_url.strip()[:200]}")
    object_type = safe_context.get("object_type")
    if isinstance(object_type, str) and object_type.strip():
        bits.append(f"object_type={object_type.strip()[:40]}")
    has_factory = safe_context.get("has_factory")
    if isinstance(has_factory, bool):
        bits.append(f"has_factory={str(has_factory).lower()}")
    return ("\n[context] " + ", ".join(bits)) if bits else ""


def _validate_pair(type_code: Any, subtype_code: Any) -> Optional[Dict[str, str]]:
    """(type, subtype) pair integrity 검증. 통과 시 dict, 실패 시 None.

    - is_valid_type / is_valid_subtype / subtype_matches_type 모두 통과해야 한다.
    - 하나라도 실패하면 None(호출측이 taxonomy 를 NULL 로 둔다 — pair 전체 폐기).
    """
    if not support_taxonomy.is_valid_type(type_code):
        return None
    if not support_taxonomy.is_valid_subtype(subtype_code):
        return None
    if not support_taxonomy.subtype_matches_type(subtype_code, type_code):
        return None
    return {"type_code": type_code, "subtype_code": subtype_code}


def classify(
    question: str,
    safe_context: Optional[Dict[str, Any]] = None,
    *,
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> Optional[Dict[str, str]]:
    """question → {type_code, subtype_code} 또는 None(실패/무효).

    best-effort: 어떤 실패든 예외를 밖으로 던지지 않고 None 을 반환한다.
    resolution_axis 는 여기서 만들지 않는다(서버가 HANDOFF 로 확정).
    """
    q = (question or "").strip()
    if not q:
        return None
    llm_call = llm_call or _default_llm_call

    taxonomy_brief = _build_taxonomy_brief()
    user_msg = (
        f"[allowed taxonomy]\n{taxonomy_brief}\n\n"
        f"[question]\n{q[:2000]}"
        f"{_safe_context_line(safe_context)}\n\n"
        "Return only {\"type_code\": ..., \"subtype_code\": ...} using codes from the taxonomy above."
    )

    try:
        raw = llm_call(_LLM_SYSTEM, user_msg)
    except Exception:  # noqa: BLE001
        logger.warning("classifier_failed: llm_call raised")
        return None

    try:
        parsed = json.loads(raw)
    except Exception:  # noqa: BLE001
        logger.warning("invalid_taxonomy: llm output not json")
        return None
    if not isinstance(parsed, dict):
        logger.warning("invalid_taxonomy: llm output not an object")
        return None

    result = _validate_pair(parsed.get("type_code"), parsed.get("subtype_code"))
    if result is None:
        logger.warning("invalid_taxonomy: type/subtype validation failed")
        return None
    return result
