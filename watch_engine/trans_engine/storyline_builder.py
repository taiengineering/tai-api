"""Storyline Builder — 이벤트 흐름을 원인→악화→영향→확인사항 순서로 서술.

Storyline 구조:
  1. 원인 단계 — 무엇이 시작되었는가 (degradation, timeout)
  2. 악화 단계 — 어떻게 진행되었는가 (repeated_failure, escalation)
  3. 현재 영향 — 지금 어떤 상태인가 (workflow.failed, step.failed)
  4. 권장 확인 — 무엇을 먼저 확인해야 하는가 (자동 생성)
"""

from __future__ import annotations

from typing import Any

from .event_translator import translate_event

# 이벤트 유형 → Storyline 단계
_STAGE_MAP: dict[str, int] = {
    # 1: 원인
    "degradation": 1,
    "runtime.degraded": 1,
    "health.warning": 1,
    # 2: 악화
    "repeated_failure": 2,
    "escalation": 2,
    # 3: 현재 영향
    "workflow.failed": 3,
    "step.failed": 3,
}

_STAGE_TEMPLATES: dict[int, str] = {
    1: "최근 {domain_hint}에서 성능 저하가 감지되었습니다.",
    2: "이후 실패 흐름이 반복 발생하기 시작했습니다.",
    3: "현재 일부 사용자가 작업을 완료하지 못하고 있습니다.",
}


def build_storyline(
    events: list[dict[str, Any]],
    audience: str = "operator",
) -> list[str]:
    """이벤트 집합 → Storyline 리스트.

    Returns:
        ["원인 문장", "악화 문장", "영향 문장", "권장 확인 문장"]
    """
    if not events:
        return ["현재 특이사항이 없습니다."]

    # 단계별 이벤트 수집
    stages_present: set[int] = set()
    domain_hints: list[str] = []

    for e in events:
        et = e.get("event_type", "")
        stage = _STAGE_MAP.get(et)
        if stage:
            stages_present.add(stage)

        # domain hint 수집
        fk = e.get("flow_key", "")
        if fk:
            label = fk.replace("_", " ")
            if label not in domain_hints:
                domain_hints.append(label)

    domain_hint = domain_hints[0] if domain_hints else "시스템"

    # Storyline 조립
    storyline: list[str] = []

    if 1 in stages_present:
        storyline.append(
            _STAGE_TEMPLATES[1].format(domain_hint=domain_hint)
        )
    if 2 in stages_present:
        storyline.append(_STAGE_TEMPLATES[2])
    if 3 in stages_present:
        storyline.append(_STAGE_TEMPLATES[3])

    # 단계가 없으면 개별 번역 사용
    if not storyline:
        for e in events[:3]:
            msg = translate_event(e, audience)
            storyline.append(msg.get("summary", ""))

    # 4단계: 권장 확인사항 (항상 추가)
    check = _generate_recommended_check(events, domain_hint)
    storyline.append(check)

    return storyline


def _generate_recommended_check(
    events: list[dict[str, Any]],
    domain_hint: str,
) -> str:
    """이벤트에서 권장 확인사항 생성."""
    types = {e.get("event_type", "") for e in events}
    flow_keys = {e.get("flow_key", "") for e in events}

    # 결제 관련
    if any("payment" in fk for fk in flow_keys if fk):
        return "결제 API 상태와 PG사 응답을 우선 확인하세요."
    # 문서 관련
    if any("document" in fk for fk in flow_keys if fk):
        return "Gotenberg 서비스 상태를 확인하세요."
    # degradation
    if "degradation" in types or "runtime.degraded" in types:
        return "서버 리소스와 외부 API 응답 시간을 확인하세요."
    # 반복 실패
    if "repeated_failure" in types:
        return "반복 실패의 근본 원인을 파악하세요."
    # 기본
    return f"{domain_hint} 관련 서비스 상태를 확인하세요."
