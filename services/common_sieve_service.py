"""D-002: Common Sieve Engine 서비스

legal_sieve_rule (2,219개)을 SemanticClause.executor_text에 적용해
CandidateClause (KEEP/DROP/PENDING)를 생성.

핵심 원칙:
  DROP = 확실한 경우만 (exact 패턴 매칭)
  애매하면 PENDING (보류, 소멸 금지)
  법 해석 기반 DROP 금지 (산안법이면 DROP 같은 규칙 절대 금지)
  AUTHORITY/BUSINESS/FRAGMENT/DELEGATED_ORG/SPECIAL_FACILITY 수준만 허용

금지:
  admin_executor_llm_fix.py 수정
  legal_sieve_rule 테이블 수정
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from schemas.candidate_clause_schema import CandidateClause, SieveResult, SieveSummary
from schemas.semantic_clause_schema import SemanticClause

log = logging.getLogger(__name__)


def _load_sieve_rules(supabase) -> List[dict]:
    """legal_sieve_rule 전체 로드 (enabled=true만).

    PostgREST 1000행 제한 → range 페이지네이션.
    """
    all_rules: List[dict] = []
    offset = 0
    page = 1000
    while True:
        res = (
            supabase.table("legal_sieve_rule")
            .select("id, pattern, verdict, class_label, match_type, priority")
            .eq("enabled", True)
            .order("priority")
            .range(offset, offset + page - 1)
            .execute()
        )
        batch = res.data or []
        all_rules.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return all_rules


def _apply_rule(executor_text: str, rule: dict) -> bool:
    """단일 룰이 executor_text에 매칭되는지 확인.

    현재 match_type:
      exact — executor_text == pattern (완전 일치)
      contains — pattern이 executor_text에 포함 (추후 확장)
    """
    match_type = rule.get("match_type", "exact")
    pattern = rule.get("pattern", "")
    if not pattern:
        return False
    if match_type == "exact":
        return executor_text == pattern
    if match_type == "contains":
        return pattern in executor_text
    return False


def apply_common_sieve(
    clause: SemanticClause,
    sieve_rules: List[dict],
) -> CandidateClause:
    """단일 SemanticClause에 거름망 적용.

    우선순위(priority) 순으로 순회, 첫 매칭 룰 기준 판정.
    매칭 없으면 PENDING (소멸 금지).
    """
    for rule in sieve_rules:  # 이미 priority 정렬됨
        if _apply_rule(clause.executor_text, rule):
            verdict = rule.get("verdict", "DROP")
            sieve_result = SieveResult.KEEP if verdict == "KEEP" else SieveResult.DROP
            return CandidateClause.from_semantic(
                clause,
                result=sieve_result,
                rule_id=str(rule["id"]),
                class_label=rule.get("class_label"),
            )
    # 미매칭 → PENDING
    return CandidateClause.from_semantic(clause, result=SieveResult.PENDING)


def run_common_sieve_batch(
    supabase,
    clauses: List[SemanticClause],
) -> Tuple[List[CandidateClause], SieveSummary]:
    """SemanticClause 목록에 거름망 일괄 적용.

    Returns:
        (CandidateClause 목록, 요약 통계)
    """
    sieve_rules = _load_sieve_rules(supabase)
    log.info("거름망 룰 %d개 로드", len(sieve_rules))

    results: List[CandidateClause] = []
    keep = drop = pending = 0

    for clause in clauses:
        candidate = apply_common_sieve(clause, sieve_rules)
        results.append(candidate)
        if candidate.sieve_result == SieveResult.KEEP:
            keep += 1
        elif candidate.sieve_result == SieveResult.DROP:
            drop += 1
        else:
            pending += 1

    summary = SieveSummary(
        total=len(results),
        keep=keep,
        drop=drop,
        pending=pending,
    )
    return results, summary
