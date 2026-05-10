"""TAI 법령엔진 v3.0 — Extraction Pipeline.

단계+단계 흐름 + 검증 hook 내장. 외부 script는 Stage 처리 로직을 중복 제어하지 않음.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from engine.stages.base import Stage, StageContext, StageOutput
from engine.validator import CheckResult, Validator

logger = logging.getLogger(__name__)


class PipelineHaltError(Exception):
    """Stage 검증 미통과 시 raise (마스터 §2.5)."""

    def __init__(self, stage: Stage, check: CheckResult) -> None:
        self.stage = stage
        self.check = check
        super().__init__(
            f"[{stage.stage_name}] 검증 {check.result_status} "
            f"(actual={check.actual_value}, threshold={check.threshold}). "
            f"마스터 §2.5: 데이터셋 점검 + 룰 수정 + 재실행 필요."
        )


@dataclass
class PipelineRun:
    """Pipeline 실행 결과 추적."""

    stage_outputs: list[StageOutput] = field(default_factory=list)
    check_results: list[CheckResult] = field(default_factory=list)
    halted_at: Stage | None = None


class TAIExtractionPipeline:
    """단계+단계 흐름 엔진."""

    def __init__(
        self,
        stages: list[Stage],
        validator: Validator,
        ctx: StageContext,
        *,
        halt_on_warning: bool = True,
    ) -> None:
        self.stages = stages
        self.validator = validator
        self.ctx = ctx
        self.halt_on_warning = halt_on_warning

    def run(self, input_data: Any, *, only_stages: list[int] | None = None) -> PipelineRun:
        """엔진 실행. only_stages로 부분 실행 (예: [2] = Stage 2만)."""
        run = PipelineRun()
        current = input_data

        for stage in self.stages:
            if only_stages is not None and stage.stage_number not in only_stages:
                continue

            logger.info(
                "[Pipeline] Stage %s (%s) 진입",
                stage.stage_number,
                stage.stage_name,
            )

            output = stage.run(current, self.ctx)
            run.stage_outputs.append(output)

            accuracy, sample_size = stage.measure_accuracy(output, self.ctx)
            check = Validator.evaluate_sample_accuracy(
                stage=stage.stage_number,
                accuracy=accuracy,
                sample_size=sample_size,
                check_name=f"{stage.stage_name}_sample_accuracy",
            )
            check.verified_by = f"pipeline_{stage.stage_name}"
            self.validator.log(check)
            run.check_results.append(check)

            halt_statuses: set[str] = {"FAIL"}
            if self.halt_on_warning:
                halt_statuses.add("WARNING")

            if check.result_status in halt_statuses:
                run.halted_at = stage
                raise PipelineHaltError(stage, check)

            current = output.data
            logger.info(
                "[Pipeline] Stage %s PASS (accuracy=%.4f)",
                stage.stage_number,
                accuracy,
            )

        return run


def halt_exit(exc: BaseException, *, code: int = 1) -> None:
    """PipelineHaltError 등 검증 실패 시 프로세스 종료 (스크립트용)."""
    logger.error("%s", exc)
    sys.exit(code)


# 별칭
Pipeline = TAIExtractionPipeline
