"""Human Message — 사람 메시지 표준 구조 (Contract)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HumanMessage:
    """Trans Engine 출력 표준 구조.

    Human Message Contract에 따른 필드:
    - title: 상황 제목 (기술 용어 금지)
    - summary: 1~2문장 운영 설명
    - urgency: 즉시 확인 필요 / 주의 필요 / 참고
    - impact: 영향 범위
    - recommended_checks: 확인 사항 리스트
    - recommended_actions: 권장 조치 리스트
    - confidence: 번역 신뢰도 0.0~1.0
    - technical: developer 전용 기술 상세 (operator에서 생략)
    """

    title: str
    summary: str
    urgency: str
    impact: str
    recommended_checks: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    confidence: float = 0.5
    technical: dict[str, Any] | None = None

    def to_dict(self, include_technical: bool = False) -> dict[str, Any]:
        """dict 변환. include_technical=False면 technical 생략."""
        result: dict[str, Any] = {
            "title": self.title,
            "summary": self.summary,
            "urgency": self.urgency,
            "impact": self.impact,
            "recommended_checks": self.recommended_checks,
            "recommended_actions": self.recommended_actions,
            "confidence": self.confidence,
        }
        if include_technical and self.technical:
            result["technical"] = self.technical
        return result
