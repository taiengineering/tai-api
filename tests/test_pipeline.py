"""Pipeline state machine 단위 테스트 (Phase 2.2-A)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from engine.pipeline import PipelineHaltError, TAIExtractionPipeline, halt_exit
from engine.stages.base import Stage, StageContext, StageOutput
from engine.validator import Validator


class MockPassStage(Stage):
    """sample 정확도 0.95"""

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "mock_pass"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data=input_data, metrics={"sample_accuracy": 0.95, "sample_size": 100})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        return (0.95, 100)


class MockFailStage(Stage):
    """sample 정확도 0.80 (< Stage2 임계 0.90 → FAIL)."""

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "mock_fail"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data=input_data, metrics={})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        return (0.80, 100)


class MockWarnStage(Stage):
    """WARNING 구간 (0.85 ≤ acc < 0.90 for stage 2)."""

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "mock_warn"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data=input_data, metrics={})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        return (0.87, 100)


class MockStage1Pass(Stage):
    @property
    def stage_number(self) -> int:
        return 1

    @property
    def stage_name(self) -> str:
        return "mock_s1"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data={"x": 1}, metrics={})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        return (0.96, 100)


def test_pipeline_pass():
    pipeline = TAIExtractionPipeline(
        stages=[MockPassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    run = pipeline.run({})
    assert run.halted_at is None
    assert len(run.check_results) == 1
    assert run.check_results[0].result_status == "PASS"


def test_pipeline_halt_on_fail():
    pipeline = TAIExtractionPipeline(
        stages=[MockFailStage(), MockPassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    with pytest.raises(PipelineHaltError) as exc_info:
        pipeline.run({})
    assert exc_info.value.stage.stage_name == "mock_fail"
    assert exc_info.value.check.result_status == "FAIL"


def test_pipeline_halt_on_warning_default():
    pipeline = TAIExtractionPipeline(
        stages=[MockWarnStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
        halt_on_warning=True,
    )
    with pytest.raises(PipelineHaltError) as exc_info:
        pipeline.run({})
    assert exc_info.value.check.result_status == "WARNING"


def test_pipeline_warning_allowed_when_disabled():
    pipeline = TAIExtractionPipeline(
        stages=[MockWarnStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
        halt_on_warning=False,
    )
    run = pipeline.run({})
    assert run.halted_at is None
    assert run.check_results[0].result_status == "WARNING"


def test_only_stages_skips_other():
    pipeline = TAIExtractionPipeline(
        stages=[MockStage1Pass(), MockFailStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    run = pipeline.run({}, only_stages=[1])
    assert len(run.stage_outputs) == 1
    assert len(run.check_results) == 1


def test_halt_exit_invokes_sys_exit():
    with patch("engine.pipeline.sys.exit") as m:
        halt_exit(ValueError("x"))
        m.assert_called_once_with(1)


def test_stage1_stage2_chain_smoke():
    """실제 Stage 래퍼 1→2 (DB 없음) — clause id 합성 경로."""
    from engine.stages.stage_1 import Stage1Splitter
    from engine.stages.stage_2 import Stage2Decomposer

    ctx = StageContext(supabase=None)
    s1 = Stage1Splitter()
    out = s1.run({"parts": [{"part_id": "p1", "part_text": "테스트 조문."}]}, ctx)
    s2 = Stage2Decomposer()
    out2 = s2.run(out.data, ctx)
    assert len(out2.data["elements"]) >= 1


def test_pipeline_halt_carries_check_result():
    pipeline = TAIExtractionPipeline(
        stages=[MockFailStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    with pytest.raises(PipelineHaltError) as ei:
        pipeline.run({})
    assert ei.value.check.stage == 2
