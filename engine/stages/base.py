"""TAI 법령엔진 v3.0 — Stage 추상 base 클래스.

엔진의 단계+단계 흐름의 본질을 정의. 각 Stage는 입력 → 처리 → 출력 + 검증 메트릭.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageContext:
    """Stage 실행 시 공유 컨텍스트 (Pipeline 주입)."""

    supabase: Any | None = None
    config: dict[str, Any] | None = None


@dataclass
class StageOutput:
    """Stage 실행 결과. Pipeline이 다음 Stage 입력으로 전달."""

    data: Any
    metrics: dict[str, Any] = field(default_factory=dict)
    sample_size: int = 0
    notes: str | None = None


class Stage(ABC):
    """엔진의 단계 추상 클래스."""

    @property
    @abstractmethod
    def stage_number(self) -> int:
        """1 / 2 / 3 (validator.py SAMPLE_ACCURACY_THRESHOLDS key)."""

    @property
    @abstractmethod
    def stage_name(self) -> str:
        """모듈 식별자 (검증 로그용)."""

    @property
    def validation_thresholds(self) -> dict[str, float]:
        """Stage별 검증 임계 (validator.py 정합)."""
        from engine.validator import SAMPLE_ACCURACY_THRESHOLDS

        return {"sample_accuracy": SAMPLE_ACCURACY_THRESHOLDS[self.stage_number]}

    @abstractmethod
    def run(self, input_data: Any, ctx: StageContext) -> StageOutput:
        """단계 실행. 반환: StageOutput (data + metrics)."""

    @abstractmethod
    def measure_accuracy(self, output: StageOutput, ctx: StageContext) -> tuple[float, int]:
        """sample 정확도 측정. 반환: (accuracy, sample_size)."""
