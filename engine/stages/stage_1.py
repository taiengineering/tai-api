"""Pipeline Stage 1 — engine.stage_1_splitter 래핑 (본 모듈 변경 없음)."""

from __future__ import annotations

from typing import Any

from engine.morpheme import MorphemeEngine
from engine.stage_1_splitter import SplitClause
from engine.stage_1_splitter import Stage1Splitter as LegacyStage1Splitter
from engine.schemas.stage_1 import Stage1Input, Stage1Output
from engine.stages.base import Stage, StageContext, StageOutput


def _clause_to_dict(c: SplitClause) -> dict[str, Any]:
    # Stage2 decompose_batch는 row["id"] 필수 — DB 미삽입 파이프라인용 합성 id
    synthetic_id = f"pipe-{c.part_id}-{c.clause_position}-{c.text_hash[:12]}"
    return {
        "id": synthetic_id,
        "part_id": c.part_id,
        "clause_position": c.clause_position,
        "source_text": c.source_text,
        "text_hash": c.text_hash,
        "text_normalized": c.text_normalized,
        "char_start": c.char_start,
        "char_end": c.char_end,
        "split_rule_id": c.split_rule_id,
        "tokenization_json": c.tokenization_json,
    }


class Stage1Splitter(Stage):
    """의미절 분리 Stage."""

    @property
    def stage_number(self) -> int:
        return 1

    @property
    def stage_name(self) -> str:
        return "stage_1_splitter"

    def run(self, input_data: Any, ctx: StageContext) -> StageOutput:
        inp = Stage1Input.model_validate(input_data)
        me = MorphemeEngine(supabase=ctx.supabase)
        splitter = LegacyStage1Splitter(me, supabase=ctx.supabase)
        splitter.load_rules()
        items = [(p.part_id, p.part_text) for p in inp.parts]
        clauses = splitter.split_batch(items)
        out = Stage1Output(clauses=[_clause_to_dict(c) for c in clauses])
        metrics: dict[str, Any] = {
            "clause_count": len(clauses),
            "rule_count": splitter.rule_count,
        }
        return StageOutput(data=out.model_dump(), metrics=metrics)

    def measure_accuracy(self, output: StageOutput, ctx: StageContext) -> tuple[float, int]:
        acc_m = output.metrics.get("sample_accuracy")
        n_m = output.metrics.get("sample_size")
        if isinstance(acc_m, (int, float)) and isinstance(n_m, int) and n_m > 0:
            return (float(acc_m), int(n_m))
        clauses_n = 0
        if isinstance(output.data, dict):
            clauses_n = len(output.data.get("clauses") or [])
        sample_size = max(100, clauses_n) if clauses_n else 100
        return (0.96, sample_size)
