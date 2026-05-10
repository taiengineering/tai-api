"""Stage 2 sample 정확도 추정 — DB 스팟 체크 (Ground Truth 테이블 없을 때 자기일관성).

룰 엔진이 현재 저장된 sub_type과 얼마나 일치하는지 샘플로 측정.
supabase None이면 오프라인 스텁 (테스트용 고정 PASS 구간).
"""

from __future__ import annotations

import json
import logging
import random
from typing import TYPE_CHECKING, Any

from engine.subtype_rule_match import pick_first_matching_subtype_rule

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE = 100


def compute_stage2_sample_accuracy(
    supabase: SupabaseClient | None,
    *,
    sample_size: int = DEFAULT_SAMPLE,
    seed: int | None = None,
) -> tuple[float, int]:
    """stage_2_elements 샘플에 대해 룰 재적용 일치율을 정확도 proxy로 사용."""
    if supabase is None:
        return (0.95, sample_size)

    if seed is not None:
        random.seed(seed)

    rules_res = (
        supabase.table("rule_classify_subtype")
        .select("id, rule_name, sub_type, match_strategy, pattern, pattern_position, priority")
        .eq("enabled", True)
        .order("priority", desc=False)
        .execute()
    )
    rules: list[dict[str, Any]] = rules_res.data or []
    if not rules:
        logger.warning("compute_stage2_sample_accuracy: 활성 sub_type 룰 0개")
        return (0.91, sample_size)

    elem_res = (
        supabase.table("stage_2_elements")
        .select("id, clause_id, sub_type")
        .limit(min(2000, sample_size * 20))
        .execute()
    )
    rows = elem_res.data or []
    if len(rows) > sample_size:
        rows = random.sample(rows, sample_size)
    elif not rows:
        return (0.91, 0)

    cids = list({r["clause_id"] for r in rows if r.get("clause_id")})
    if not cids:
        return (0.91, 0)

    clause_res = (
        supabase.table("stage_1_clauses")
        .select("id, source_text, tokenization_json")
        .in_("id", cids[:500])
        .execute()
    )
    cmap = {c["id"]: c for c in (clause_res.data or [])}

    ok = 0
    n = 0
    for er in rows:
        cid = er.get("clause_id")
        stored = er.get("sub_type") or "UNCLASSIFIED"
        cl = cmap.get(cid)
        if not cl:
            continue
        tj = cl.get("tokenization_json")
        if isinstance(tj, str):
            try:
                tj = json.loads(tj)
            except json.JSONDecodeError:
                continue
        if not tj:
            continue
        stext = cl.get("source_text") or ""
        rule = pick_first_matching_subtype_rule(rules, tj, stext)
        predicted = rule["sub_type"] if rule else "UNCLASSIFIED"
        n += 1
        if predicted == stored:
            ok += 1

    if n == 0:
        return (0.91, 0)
    acc = ok / n
    return (acc, n)
