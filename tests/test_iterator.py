"""PipelineIterator 단위 테스트 (Track A P3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from engine.iterator import (
    Phase22V3Iterator,
    PipelineIterator,
    isolation_reason_for_fp_subtype,
)
from engine.pipeline import PipelineHaltError, TAIExtractionPipeline
from engine.stages.base import Stage, StageContext, StageOutput
from engine.validator import CheckResult, Validator


class MockLawAwarePassStage(Stage):
    """law별로 PASS — 정확도 0.95."""

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "mock_law_pass"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data=input_data or {}, metrics={})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        return (0.95, 100)


class MockLawAwareFailAtStage(Stage):
    """지정 law_id에서만 FAIL."""

    def __init__(self, fail_at: int | str) -> None:
        self.fail_at = fail_at

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "mock_law_fail_at"

    def run(self, input_data, ctx):  # noqa: ANN001
        return StageOutput(data=input_data or {}, metrics={})

    def measure_accuracy(self, output, ctx):  # noqa: ANN001
        if ctx.law_id == self.fail_at:
            return (0.80, 100)
        return (0.95, 100)


def test_iterator_all_pass(monkeypatch):
    ids = list(range(10))

    def fake_order(self):  # noqa: ANN001
        return ids

    monkeypatch.setattr(PipelineIterator, "_fetch_law_order", fake_order)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, regression_window=0, halt_on_first_fail=True)
    run = it.iterate(only_stages=[2])

    assert run.total_laws == 10
    assert len(run.laws_processed) == 10
    assert len(run.laws_failed) == 0
    assert run.halted is False


def test_iterator_halt_on_first_fail(monkeypatch):
    ids = [1, 2, 3, 4, 5, 6]

    def fake_order(self):  # noqa: ANN001
        return ids

    monkeypatch.setattr(PipelineIterator, "_fetch_law_order", fake_order)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwareFailAtStage(fail_at=5)],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, halt_on_first_fail=True)
    run = it.iterate(only_stages=[2])

    assert run.halted is True
    assert len(run.laws_processed) == 4
    assert len(run.laws_failed) == 1
    assert run.laws_failed[0][0] == 5


def test_iterator_continue_after_fail(monkeypatch):
    ids = [1, 2, 3, 5]

    def fake_order(self):  # noqa: ANN001
        return ids

    monkeypatch.setattr(PipelineIterator, "_fetch_law_order", fake_order)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwareFailAtStage(fail_at=2)],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, halt_on_first_fail=False)
    run = it.iterate(only_stages=[2])

    assert run.halted is False
    assert len(run.laws_failed) == 1
    assert len(run.laws_processed) == 3


def test_iterator_regression_window_calls(monkeypatch):
    ids = list(range(15))

    def fake_order(self):  # noqa: ANN001
        return ids

    monkeypatch.setattr(PipelineIterator, "_fetch_law_order", fake_order)

    calls: list[list] = []

    def spy_regression(self, recent, *, only_stages=None):  # noqa: ANN001
        calls.append(list(recent))

    monkeypatch.setattr(PipelineIterator, "_regression_check", spy_regression)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(
        pipeline,
        None,
        regression_window=10,
        halt_on_first_fail=True,
    )
    it.iterate(only_stages=[2])

    assert len(calls) >= 1
    assert len(calls[0]) <= 10


def test_iterator_regression_failure_halts(monkeypatch):
    ids = list(range(15))

    def fake_order(self):  # noqa: ANN001
        return ids

    monkeypatch.setattr(PipelineIterator, "_fetch_law_order", fake_order)

    def boom(self, recent, *, only_stages=None):  # noqa: ANN001
        chk = CheckResult(
            stage=2,
            check_name="regression",
            check_type="AUTO_HOOK",
            result_status="FAIL",
            actual_value="0.0",
            threshold="0.9",
        )
        raise PipelineHaltError(MockLawAwarePassStage(), chk)

    monkeypatch.setattr(PipelineIterator, "_regression_check", boom)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(
        pipeline,
        None,
        regression_window=10,
        halt_on_first_fail=True,
    )
    run = it.iterate(only_stages=[2])

    assert run.halted is True
    assert len(run.laws_failed) == 1
    assert run.laws_failed[0][0] == 10


def test_pipeline_law_id_restored_after_run():
    ctx = StageContext()
    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=ctx,
    )
    pipeline.run(
        {},
        only_stages=[2],
        law_id=999,
        isolation_mode=True,
        exclude_isolated=True,
    )
    assert ctx.law_id is None
    assert ctx.law_batch is None
    assert ctx.isolation_mode is False
    assert ctx.exclude_isolated is False


def test_regression_check_invokes_pipeline_per_law():
    calls: list = []

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    orig = pipeline.run

    def wrapped(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(kwargs.get("law_id"))
        return orig(*args, **kwargs)

    pipeline.run = wrapped  # type: ignore[method-assign]

    it = PipelineIterator(pipeline, None)
    it._regression_check([101, 102], only_stages=[2])
    assert calls == [101, 102]


def test_fetch_law_order_ascending_size(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(30, 100), (10, 5), (20, 50)]
    mock_conn.cursor.return_value = mock_cur
    monkeypatch.setattr(psycopg2, "connect", lambda _url: mock_conn)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, order="ascending_size")
    assert it._fetch_law_order() == [10, 20, 30]


def test_fetch_law_order_descending_size(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(1, 10), (2, 90), (3, 30)]
    mock_conn.cursor.return_value = mock_cur
    monkeypatch.setattr(psycopg2, "connect", lambda _url: mock_conn)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, order="descending_size")
    assert it._fetch_law_order() == [2, 3, 1]


def test_fetch_law_order_sequential(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [(20, 1), (3, 1), (100, 1)]
    mock_conn.cursor.return_value = mock_cur
    monkeypatch.setattr(psycopg2, "connect", lambda _url: mock_conn)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None, order="sequential")
    assert it._fetch_law_order() == [100, 20, 3]


def test_fetch_law_order_sql_error_returns_empty(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

    def boom(_url):  # noqa: ANN001
        raise RuntimeError("db down")

    monkeypatch.setattr(psycopg2, "connect", boom)
    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = PipelineIterator(pipeline, None)
    assert it._fetch_law_order() == []


def test_pipeline_law_id_visible_in_stage(monkeypatch):
    seen: list = []

    class CaptureStage(Stage):
        @property
        def stage_number(self) -> int:
            return 2

        @property
        def stage_name(self) -> str:
            return "capture"

        def run(self, input_data, ctx):  # noqa: ANN001
            seen.append(ctx.law_id)
            return StageOutput(data={}, metrics={})

        def measure_accuracy(self, output, ctx):  # noqa: ANN001
            return (0.95, 100)

    pipeline = TAIExtractionPipeline(
        stages=[CaptureStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    pipeline.run({}, only_stages=[2], law_id=12345)
    assert seen == [12345]


def test_isolation_reason_fp_as_bonda():
    assert isolation_reason_for_fp_subtype("AS_본다") == "FP_AS_본다_보조_룰"


def test_phase22_v3_pass_first_iteration(monkeypatch):
    monkeypatch.setattr(
        "engine.iterator.fetch_law_ids_ordered",
        lambda _order: [100],
    )
    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = Phase22V3Iterator(
        pipeline,
        None,
        regression_window=0,
        max_iterations_per_law=3,
    )
    run = it.iterate(only_stages=[2])
    assert not run.halted
    assert len(run.law_results) == 1
    assert run.law_results[0].final_status == "PASS"
    assert run.law_results[0].iterations_used == 1


def test_phase22_v3_fail_halt_after_max_iter(monkeypatch):
    monkeypatch.setattr(
        "engine.iterator.fetch_law_ids_ordered",
        lambda _order: [7],
    )
    monkeypatch.setattr(Phase22V3Iterator, "_isolate_fp_rows", lambda self, lid, c: 0)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwareFailAtStage(fail_at=7)],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = Phase22V3Iterator(
        pipeline,
        None,
        regression_window=0,
        max_iterations_per_law=2,
        halt_on_first_fail=True,
    )
    run = it.iterate(only_stages=[2])
    assert run.halted
    assert run.laws_halted[0][1].final_status == "FAIL_HALT"


def test_phase22_v3_regression_checkpoint(monkeypatch):
    monkeypatch.setattr(
        "engine.iterator.fetch_law_ids_ordered",
        lambda _order: list(range(11)),
    )
    calls: list[list] = []

    def spy(self, recent, *, only_stages=None):  # noqa: ANN001
        calls.append(list(recent))

    monkeypatch.setattr(Phase22V3Iterator, "_regression_check", spy)

    pipeline = TAIExtractionPipeline(
        stages=[MockLawAwarePassStage()],
        validator=Validator(supabase=None),
        ctx=StageContext(),
    )
    it = Phase22V3Iterator(
        pipeline,
        None,
        regression_window=10,
        max_iterations_per_law=1,
    )
    it.iterate(only_stages=[2])
    assert len(calls) >= 1


def test_stage2_initialization_once():
    """동일 Stage2Decomposer 인스턴스 — Kiwi/분해기/룰 로드 1회만."""
    from engine.stages.stage_2 import Stage2Decomposer

    dec_mock = MagicMock()
    dec_mock.decompose_batch.return_value = []

    with patch("engine.stages.stage_2.MorphemeEngine") as ME:
        with patch(
            "engine.stages.stage_2.LegacyStage2Decomposer",
            return_value=dec_mock,
        ) as LD:
            s2 = Stage2Decomposer()
            ctx = StageContext(supabase=None)
            for _ in range(5):
                s2.run(None, ctx)

            ME.assert_called_once()
            LD.assert_called_once()
            dec_mock.load_rules.assert_called_once()
            assert dec_mock.decompose_batch.call_count == 5
