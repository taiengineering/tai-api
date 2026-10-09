"""Trigger Code Set → semantic_clause 의무후보 생성기 (CURSOR-TASK-001).

Trigger Code Set을 keyword_pattern으로 semantic_clause에서 검색해
의무후보 배치를 반환한다. source_article_id 기준 중복 제거.

핵심 필터:
  content_type IN ('OBLIGATION','PROHIBITION') AND executor_text = '사업주'
  (COALESCE(condition_text,'') || action_text) ~ keyword_pattern
  BUSINESS:REGISTERED → condition_text IS NULL 특수 처리

DB 쓰기 없음. obligation_adapter 무수정.

DEV-IN-004 (production trigger detection 개선):
  (A) [DEV-IN-004V 검증 후 철회] 누락 스펙 6종은 emitter(trigger_generator)에
      해당 has_X/equipment canonical 이 없어 NOT_DECLARED(dead) → 계약 확장 금지 원칙에
      따라 제거함. 필요 시 factories 계약 확장은 별도 승인 작업.
  (B) _match_clause 검색 범위를 구조적 what_text·where_text 로 확장
      (raw 원문/상위문맥은 과탐 위험 → 미포함. 구조적 목적어/장소만).
  매칭 근거(matched_field/matched_pattern/matched_text)를 후보에 기록.
  주의: requirement_atom_v2_dryrun(미커밋 벤치마크) 19건 회복을 주장하지 않음.
        이 수정은 committed production candidate 검출기 개선이며,
        회복률은 tai-api 파이프라인 재실행으로만 확정.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

_PAGE = 1000
_CLAUSE_TABLE = "semantic_clause"
_OBLIGATION_TYPES = ("OBLIGATION", "PROHIBITION")
_DEFAULT_EXECUTOR = "사업주"

_CONF_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_TRIGGER_PRIORITY = {
    "EQUIPMENT_ACT": 50,
    "EQUIPMENT": 40,
    "WORK": 30,
    "THRESHOLD": 20,
    "BUSINESS": 10,
}

# (B) 구조적 주어·문맥 확장에 사용할 clause 필드.
# raw source_text / source_part_text 는 과탐 위험이 커 제외하고,
# 구조적 목적어(what_text)·장소(where_text)만 보조 매칭에 사용.
_PRIMARY_MATCH_FIELDS = ("condition_text", "action_text")
_STRUCTURAL_MATCH_FIELDS = ("what_text", "where_text")
_NO_EVIDENCE: Dict[str, Any] = {"matched_field": None, "matched_pattern": None, "matched_text": None}


class TriggerSpec:
    __slots__ = ("mode", "pattern", "confidence")

    def __init__(
        self,
        *,
        mode: str = "regex",
        pattern: Optional[str] = None,
        confidence: str = "HIGH",
    ):
        self.mode = mode
        self.pattern = pattern
        self.confidence = confidence


# Trigger Code → 검색 규칙 (WO-MAPPING-001 / WO-VALIDATION-001 기준)
# WORK:CONFINED_SPACE는 설계서 키워드로 보정 ("밀폐" 단독 과잉매칭 방지)
TRIGGER_SPECS: Dict[str, TriggerSpec] = {
    "BUSINESS:REGISTERED": TriggerSpec(mode="null_condition", confidence="MEDIUM"),
    "THRESHOLD:EMPLOYEE_50_PLUS": TriggerSpec(
        pattern=r"50인|오십인|50\s*명|오십\s*명",
        confidence="HIGH",
    ),
    "THRESHOLD:EMPLOYEE_100_PLUS": TriggerSpec(
        pattern=r"100인|백인|100\s*명|백\s*명",
        confidence="HIGH",
    ),
    # WORK: 설계서(WO-MAPPING-001) 키워드 패턴 적용
    "WORK:CONFINED_SPACE": TriggerSpec(
        pattern=r"(밀폐공간|산소결핍|황화수소|밀폐된 공간)",
        confidence="HIGH",
    ),
    "WORK:TOWER_CRANE": TriggerSpec(
        pattern=r"타워크레인|tower\s*crane",
        confidence="HIGH",
    ),
    "WORK:ASBESTOS": TriggerSpec(pattern=r"(석면|석면해체|석면분진)", confidence="HIGH"),
    "WORK:BLASTING": TriggerSpec(pattern=r"(발파|화약류|폭발물)", confidence="HIGH"),
    "WORK:DIVING": TriggerSpec(pattern=r"(잠수|잠함|잠수작업자)", confidence="HIGH"),
    "WORK:EXCAVATION": TriggerSpec(pattern=r"(굴착|굴착공사)", confidence="HIGH"),
    "WORK:HIGH_PLACE": TriggerSpec(pattern=r"고소|2\s*미터\s*이상", confidence="HIGH"),
    "WORK:LIFTING": TriggerSpec(pattern=r"양중", confidence="HIGH"),
    "WORK:DEMOLITION": TriggerSpec(pattern=r"(해체|철거)", confidence="HIGH"),
    "WORK:SCAFFOLD": TriggerSpec(pattern=r"비계", confidence="HIGH"),
    "WORK:FORMWORK": TriggerSpec(pattern=r"(거푸집|동바리)", confidence="HIGH"),
    "WORK:WELDING": TriggerSpec(pattern=r"(용접|용단)", confidence="HIGH"),
    "WORK:ELECTRICAL": TriggerSpec(pattern=r"전기공사|전기\s*작업", confidence="HIGH"),
    "WORK:HOT_WORK": TriggerSpec(pattern=r"화기\s*작업|화기작업", confidence="HIGH"),
    "WORK:BOILER": TriggerSpec(pattern=r"보일러", confidence="HIGH"),
    "WORK:HIGH_PRESSURE_GAS": TriggerSpec(pattern=r"(고압작업|고압가스|기압조절실)", confidence="HIGH"),
    "WORK:CHEMICAL_SUBSTANCE": TriggerSpec(pattern=r"(관리대상 유해물질|허가대상 유해물질|금지유해물질|화학물질)", confidence="HIGH"),
    "WORK:SAFETY_MANAGER": TriggerSpec(pattern=r"안전관리자|안전보건관리책임자", confidence="HIGH"),
    "WORK:HAZARDOUS_MATERIAL": TriggerSpec(pattern=r"위험물", confidence="HIGH"),
    # EQUIPMENT
    "EQUIPMENT:CRANE": TriggerSpec(
        pattern=r"(크레인|양중기)",
        confidence="HIGH",
    ),
    "EQUIPMENT_ACT:CRANE_USE": TriggerSpec(
        pattern=r"크레인.{0,10}(사용|작업)|크레인을 사용하여",
        confidence="HIGH",
    ),
    "EQUIPMENT:BOILER": TriggerSpec(pattern=r"보일러", confidence="HIGH"),
    "EQUIPMENT_ACT:BOILER_USE": TriggerSpec(
        pattern=r"보일러.*(사용|운전|조작)",
        confidence="HIGH",
    ),
    "EQUIPMENT:ELEVATOR": TriggerSpec(pattern=r"(승강기|리프트|엘리베이터)", confidence="HIGH"),
    "EQUIPMENT_ACT:ELEVATOR_USE": TriggerSpec(
        pattern=r"승강기.*(사용|운전|조작)",
        confidence="HIGH",
    ),
    "EQUIPMENT:PRESSURE_VESSEL": TriggerSpec(pattern=r"압력용기", confidence="HIGH"),
    "EQUIPMENT_ACT:PRESSURE_VESSEL_USE": TriggerSpec(
        pattern=r"압력용기.*(사용|운전|조작)",
        confidence="HIGH",
    ),
    "EQUIPMENT:HIGH_PRESSURE_GAS": TriggerSpec(pattern=r"(고압작업|고압가스|기압조절실)", confidence="HIGH"),
    "EQUIPMENT_ACT:HIGH_PRESSURE_GAS_USE": TriggerSpec(
        pattern=r"고압가스.*(사용|취급|조작)",
        confidence="HIGH",
    ),
    "EQUIPMENT:WELDER": TriggerSpec(pattern=r"(용접기|용접전원|아크용접)", confidence="HIGH"),
    "EQUIPMENT:CHEMICAL_VESSEL": TriggerSpec(pattern=r"(화학설비|반응기|혼합기)", confidence="HIGH"),
    "EQUIPMENT:LOCAL_EXHAUST": TriggerSpec(pattern=r"(국소배기|집진기|후드)", confidence="HIGH"),
    "EQUIPMENT:EXCAVATOR": TriggerSpec(pattern=r"(굴착기|차량계 건설기계|건설기계)", confidence="HIGH"),
    "EQUIPMENT:CONVEYOR": TriggerSpec(pattern=r"컨베이어", confidence="HIGH"),
    "EQUIPMENT:PRESS": TriggerSpec(pattern=r"프레스", confidence="HIGH"),
    "EQUIPMENT:TOWER_CRANE": TriggerSpec(pattern=r"타워크레인", confidence="HIGH"),
}


def _generic_equipment_specs(trigger_code: str) -> Optional[TriggerSpec]:
    """EQUIPMENT:* / EQUIPMENT_ACT:*_USE 미정의 코드용 폴백."""
    if trigger_code.startswith("EQUIPMENT_ACT:") and trigger_code.endswith("_USE"):
        token = trigger_code[len("EQUIPMENT_ACT:"):-len("_USE")]
        label = token.replace("_", "")
        return TriggerSpec(
            pattern=rf"{label}.*(사용|운전|조작|취급)",
            confidence="MEDIUM",
        )
    if trigger_code.startswith("EQUIPMENT:"):
        token = trigger_code[len("EQUIPMENT:"):]
        label = token.replace("_", "")
        return TriggerSpec(pattern=rf"{label}", confidence="MEDIUM")
    return None


def _get_spec(trigger_code: str) -> Optional[TriggerSpec]:
    spec = TRIGGER_SPECS.get(trigger_code)
    if spec:
        return spec
    return _generic_equipment_specs(trigger_code)


def _trigger_family(trigger_code: str) -> str:
    return trigger_code.split(":", 1)[0]


def _trigger_rank(trigger_code: str) -> int:
    fam = _trigger_family(trigger_code)
    return _TRIGGER_PRIORITY.get(fam, 0)


def _compiled_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _match_clause_ev(clause: Dict[str, Any], spec: TriggerSpec) -> Tuple[bool, Dict[str, Any]]:
    """clause 매칭 + 매칭 근거(matched_field/pattern/text) 반환.

    (A) null_condition 모드는 기존과 동일.
    (B) 검색 순서: ① condition_text+action_text 결합(기존 동작 보존)
                   ② 구조적 what_text → where_text (신규 확장)
        raw source_text / source_part_text 는 과탐 위험으로 사용하지 않는다.
    """
    condition = clause.get("condition_text")
    action = clause.get("action_text") or ""

    if spec.mode == "null_condition":
        ok = condition is None or str(condition).strip() == ""
        if ok:
            return True, {"matched_field": "condition_text", "matched_pattern": None, "matched_text": None}
        return False, dict(_NO_EVIDENCE)

    if not spec.pattern:
        return False, dict(_NO_EVIDENCE)

    pat = _compiled_pattern(spec.pattern)

    # ① 기존 동작 보존: condition_text + action_text 결합 매칭
    hay = f"{condition or ''}{action}"
    m = pat.search(hay)
    if m:
        return True, {"matched_field": "condition_action", "matched_pattern": spec.pattern, "matched_text": m.group(0)}

    # ② (B) 구조적 주어·문맥 확장: what_text, where_text (개별 필드, raw 원문 아님)
    for field in _STRUCTURAL_MATCH_FIELDS:
        val = clause.get(field)
        if not val:
            continue
        m = pat.search(str(val))
        if m:
            return True, {"matched_field": field, "matched_pattern": spec.pattern, "matched_text": m.group(0)}

    return False, dict(_NO_EVIDENCE)


def _match_clause(clause: Dict[str, Any], spec: TriggerSpec) -> bool:
    """하위호환 bool 래퍼."""
    return _match_clause_ev(clause, spec)[0]


def _load_obligation_clauses(
    supabase,
    executor_text: str = _DEFAULT_EXECUTOR,
) -> List[Dict[str, Any]]:
    """semantic_clause에서 사업주 의무절 전체 로드(페이지네이션)."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = (
                supabase.table(_CLAUSE_TABLE)
                .select(
                    "id, source_article_id, source_part_id, executor_text, "
                    "condition_text, action_text, what_text, where_text, "
                    "content_type, sector"
                )
                .in_("content_type", list(_OBLIGATION_TYPES))
                .eq("executor_text", executor_text)
                .range(offset, offset + _PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.error("semantic_clause fetch failed: %s", exc)
            raise
        chunk = res.data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    return rows


def _candidate_from_clause(
    clause: Dict[str, Any],
    trigger_code: str,
    confidence: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ev = evidence or _NO_EVIDENCE
    return {
        "clause_id": str(clause.get("id") or ""),
        "source_article_id": str(clause.get("source_article_id") or ""),
        "source_part_id": str(clause.get("source_part_id") or ""),
        "trigger_code": trigger_code,
        "executor_text": clause.get("executor_text"),
        "condition_text": clause.get("condition_text"),
        "action_text": clause.get("action_text"),
        "content_type": clause.get("content_type"),
        "sector": clause.get("sector"),
        "confidence": confidence,
        # DEV-IN-004: 매칭 근거 (어느 필드/패턴/텍스트로 매칭됐는지)
        "matched_field": ev.get("matched_field"),
        "matched_pattern": ev.get("matched_pattern"),
        "matched_text": ev.get("matched_text"),
    }


def _pick_better(
    current: Dict[str, Any],
    challenger: Dict[str, Any],
) -> Dict[str, Any]:
    """source_article_id 충돌 시 더 구체적인 트리거/높은 confidence 채택."""
    cur_rank = _CONF_RANK.get(current.get("confidence", ""), 0)
    new_rank = _CONF_RANK.get(challenger.get("confidence", ""), 0)
    if new_rank != cur_rank:
        return challenger if new_rank > cur_rank else current
    cur_pri = _trigger_rank(current.get("trigger_code", ""))
    new_pri = _trigger_rank(challenger.get("trigger_code", ""))
    return challenger if new_pri > cur_pri else current


def generate_obligation_candidates(
    trigger_codes: List[str],
    supabase,
    *,
    executor_text: str = _DEFAULT_EXECUTOR,
) -> List[Dict[str, Any]]:
    """Trigger Code Set → 의무후보 배치 (source_article_id 중복 제거)."""
    if not trigger_codes:
        return []

    specs: List[Tuple[str, TriggerSpec]] = []
    for code in trigger_codes:
        spec = _get_spec(code)
        if spec:
            specs.append((code, spec))
        else:
            log.debug("no trigger spec for %s — skipped", code)

    if not specs:
        return []

    clauses = _load_obligation_clauses(supabase, executor_text=executor_text)
    by_article: Dict[str, Dict[str, Any]] = {}

    for clause in clauses:
        for trigger_code, spec in specs:
            ok, evidence = _match_clause_ev(clause, spec)
            if not ok:
                continue
            aid = str(clause.get("source_article_id") or "")
            if not aid:
                continue
            cand = _candidate_from_clause(clause, trigger_code, spec.confidence, evidence)
            prev = by_article.get(aid)
            if prev is None:
                by_article[aid] = cand
            else:
                by_article[aid] = _pick_better(prev, cand)

    return list(by_article.values())


def match_clauses_for_trigger(
    clauses: List[Dict[str, Any]],
    trigger_code: str,
) -> List[Dict[str, Any]]:
    """오프라인/테스트용: clause 리스트에서 단일 트리거 매칭."""
    spec = _get_spec(trigger_code)
    if not spec:
        return []
    return [c for c in clauses if _match_clause(c, spec)]
