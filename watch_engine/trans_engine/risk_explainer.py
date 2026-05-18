"""Risk Explainer — 내부 severity/risk → 운영 위험 언어 변환."""

from __future__ import annotations

# Severity → 운영 언어
_SEVERITY_RISK: dict[str, dict[str, str]] = {
    "INFO":     {"label": "정상 흐름",            "description": "특이사항 없습니다."},
    "WARNING":  {"label": "주의 필요",            "description": "상황을 지켜볼 필요가 있습니다."},
    "CRITICAL": {"label": "즉시 확인 필요",        "description": "지금 바로 확인해야 합니다."},
    "FATAL":    {"label": "운영 중단 가능성",    "description": "서비스 중단 위험이 있습니다."},
}

# Risk Level → 운영 언어
_RISK_LEVEL: dict[str, dict[str, str]] = {
    "HEALTHY":  {"label": "정상 운영 중",       "description": "서비스가 정상적으로 운영되고 있습니다."},
    "RISK":     {"label": "위험 요소 감지",       "description": "위험 요소가 감지되었습니다."},
    "DEGRADED": {"label": "안정성 저하 중",       "description": "서비스 안정성이 낮아지고 있습니다."},
    "CRITICAL": {"label": "심각한 위험 상태",    "description": "심각한 운영 위험 상태입니다."},
}


def explain_severity(severity: str) -> dict[str, str]:
    """Severity 코드 → 운영 언어."""
    return _SEVERITY_RISK.get(
        severity.upper(),
        {"label": "확인 필요", "description": "상태를 확인해 주세요."},
    )


def explain_risk_level(level: str) -> dict[str, str]:
    """Risk level 코드 → 운영 언어."""
    return _RISK_LEVEL.get(
        level.upper(),
        {"label": "확인 필요", "description": "상태를 확인해 주세요."},
    )
