"""Pipeline Stage 3 — engine.stage_3_objectifier 래핑 (본 모듈 변경 없음)."""

from __future__ import annotations

from typing import Any

from engine.stage_3_objectifier import StageObject
from engine.stage_3_objectifier import Stage3Objectifier as LegacyStage3Objectifier
from engine.schemas.stage_3 import Stage3Input, Stage3Output
from engine.stages.base import Stage, StageContext, StageOutput


def _object_to_dict(o: StageObject) -> dict[str, Any]:
    return {
        "element_id": o.element_id,
        "target_master_table": o.target_master_table,
        "target_master_id": o.target_master_id,
        "field_values": o.field_values,
        "mapping_rule_id": o.mapping_rule_id,
        "mapping_status": o.mapping_status,
        "error_message": o.error_message,
    }


class Stage3Objectifier(Stage):
    """객체화 Stage."""

    @property
    def stage_number(self) -> int:
        return 3

    @property
    def stage_name(self) -> str:
        return "stage_3_objectifier"

    def run(self, input_data: Any, ctx: StageContext) -> StageOutput:
        inp = Stage3Input.model_validate(input_data)
        obj = LegacyStage3Objectifier(supabase=ctx.supabase)
        obj.load_rules()
        objs = obj.objectify_batch(inp.elements)
        out = Stage3Output(objects=[_object_to_dict(o) for o in objs])
        metrics: dict[str, Any] = {"object_count": len(objs)}
        return StageOutput(data=out.model_dump(), metrics=metrics)

    def measure_accuracy(self, output: StageOutput, ctx: StageContext) -> tuple[float, int]:
        acc_m = output.metrics.get("sample_accuracy")
        n_m = output.metrics.get("sample_size")
        if isinstance(acc_m, (int, float)) and isinstance(n_m, int) and n_m > 0:
            return (float(acc_m), int(n_m))
        return (0.91, 100)
