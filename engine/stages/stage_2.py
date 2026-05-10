"""Pipeline Stage 2 — engine.stage_2_decomposer 래핑 (본 모듈 변경 없음)."""

from __future__ import annotations

from typing import Any

from engine.clause_fetch import (
    fetch_clauses_by_law_batch,
    fetch_clauses_by_law_id,
    fetch_isolated_clauses_by_law_id,
)
from engine.morpheme import MorphemeEngine
from engine.sample_accuracy import compute_stage2_sample_accuracy
from engine.stage_2_decomposer import StageElement
from engine.stage_2_decomposer import Stage2Decomposer as LegacyStage2Decomposer
from engine.schemas.stage_2 import Stage2Input, Stage2Output
from engine.stages.base import Stage, StageContext, StageOutput


def _element_to_dict(e: StageElement) -> dict[str, Any]:
    return {
        "clause_id": e.clause_id,
        "sub_type": e.sub_type,
        "if_pattern": e.if_pattern,
        "executor": e.executor,
        "recipient": e.recipient,
        "what": e.what,
        "when_value": e.when_value,
        "where_value": e.where_value,
        "how": e.how,
        "condition": e.condition,
        "exception": e.exception,
        "applied_rules": e.applied_rules,
        "confidence_score": e.confidence_score,
    }


class Stage2Decomposer(Stage):
    """역할 분해 + sub_type 분류 Stage."""

    def __init__(self) -> None:
        self._me: MorphemeEngine | None = None
        self._dec: LegacyStage2Decomposer | None = None

    @property
    def stage_number(self) -> int:
        return 2

    @property
    def stage_name(self) -> str:
        return "stage_2_decomposer"

    def _ensure_initialized(self, supabase: Any) -> None:
        """Kiwi·사전·룰 — Pipeline 동일 Stage 인스턴스에서 1회만 로드."""
        if self._me is None:
            self._me = MorphemeEngine(supabase=supabase)
        if self._dec is None:
            self._dec = LegacyStage2Decomposer(self._me, supabase=supabase)
            self._dec.load_rules()

    def run(self, input_data: Any, ctx: StageContext) -> StageOutput:
        if ctx.law_id is not None and ctx.isolation_mode:
            clauses = fetch_isolated_clauses_by_law_id(ctx.supabase, ctx.law_id)
        elif ctx.law_id is not None:
            clauses = fetch_clauses_by_law_id(ctx.supabase, ctx.law_id)
        elif ctx.law_batch:
            clauses = fetch_clauses_by_law_batch(ctx.supabase, ctx.law_batch)
        else:
            inp = Stage2Input.model_validate(
                input_data if input_data is not None else {"clauses": []}
            )
            clauses = inp.clauses

        self._ensure_initialized(ctx.supabase)
        assert self._dec is not None
        elements = self._dec.decompose_batch(clauses)
        classified = sum(1 for e in elements if e.sub_type != "UNCLASSIFIED")
        out = Stage2Output(elements=[_element_to_dict(e) for e in elements])
        metrics: dict[str, Any] = {
            "total_elements": len(elements),
            "classified_count": classified,
            "classified_pct": (classified / len(elements)) if elements else 0.0,
        }
        return StageOutput(data=out.model_dump(), metrics=metrics)

    def measure_accuracy(self, output: StageOutput, ctx: StageContext) -> tuple[float, int]:
        acc_m = output.metrics.get("sample_accuracy")
        n_m = output.metrics.get("sample_size")
        if isinstance(acc_m, (int, float)) and isinstance(n_m, int) and n_m > 0:
            return (float(acc_m), int(n_m))
        return compute_stage2_sample_accuracy(
            ctx.supabase,
            law_id=ctx.law_id,
            law_batch=ctx.law_batch,
            exclude_isolated=ctx.exclude_isolated,
        )
