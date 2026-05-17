"""Intelligence Result \ud45c\uc900."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntelligenceResult:
    intelligence_type: str
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    risk_score: int = 0     # 0~100
    confidence: float = 0.0  # 0.0~1.0
    summary: str = ""
    recommendations: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intelligence_type": self.intelligence_type,
            "severity": self.severity,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
            "details": self.details,
        }
