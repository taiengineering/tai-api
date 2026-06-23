"""Trigger 6W Service (TASK-005).

semantic_clause action_text + condition_text → extract_six_w() 재사용
→ 6W dict 반환.

수정 금지 함수: extract_six_w()

ISSUE-003: Kiwi 초기화 비용 (Railway 구동 시 서버 시작 + 1~2초).
  연속 호출 시 인스턴스 재사용. get_morpheme_engine() 통해 싱글턴 관리.

ISSUE-004: where_value NULL 대리. condition_text 키워드로
  Trigger Code에서 직접 유추.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from engine.six_w_heuristic import extract_six_w
from engine.morpheme import MorphemeEngine

_ENGINE: Optional[MorphemeEngine] = None


def get_morpheme_engine(supabase=None) -> MorphemeEngine:
    """ISSUE-003: 싱글턴 인스턴스."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = MorphemeEngine(supabase=supabase)
    return _ENGINE


# Trigger Code → where_value 폴백 (ISSUE-004)
_TRIGGER_WHERE_FALLBACK: Dict[str, str] = {
    "WORK:CONFINED_SPACE":    "밀폐공간",
    "WORK:BLASTING":          "발파 작업 장소",
    "WORK:DIVING":            "잠수 작업 장소",
    "WORK:ASBESTOS":          "석면 해체 작업 장소",
    "WORK:HIGH_PRESSURE":     "고압작업 장소",
    "WORK:HIGH_PRESSURE_GAS": "고압가스 취급 장소",
    "WORK:TOWER_CRANE":       "타워크레인 설치 현장",
    "WORK:WELDING":           "용접 작업 장소",
    "WORK:EXCAVATION":        "굴착 작업 장소",
    "WORK:DEMOLITION":        "해체 작업 장소",
    "EQUIPMENT:CRANE":        "크레인 설치 장소",
    "EQUIPMENT:BOILER":       "보일러 스치",
    "EQUIPMENT:ELEVATOR":     "승강기 설치 장소",
    "HAZARD_FACTOR:CHEMICAL": "유해물질 취급 장소",
}


def extract_six_w_for_candidate(
    candidate: Dict[str, Any],
    supabase=None,
) -> Dict[str, Any]:
    """TASK-005: semantic_clause 후보 1건 → 6W dict.

    Args:
      candidate: evaluate_candidate() 결과 + action_text/condition_text 포함
      supabase: Kiwi 사전 로드용 (없으면 폴백 사전만 사용)

    Returns:
      {
        who, when, where, what, how, why,
        condition, completeness(0.0~1.0)
      }
    """
    action_text = candidate.get("action_text") or ""
    condition_text = candidate.get("condition_text") or ""
    trigger_code = candidate.get("trigger_code") or ""

    # Kiwi 토큰화
    try:
        engine = get_morpheme_engine(supabase)
        tokens = engine.tokenize(action_text)
        tok_json = [
            {"form": t.form, "tag": str(t.tag), "start": t.start, "len": t.len}
            for t in tokens
        ]
    except Exception:
        tok_json = []

    raw = extract_six_w(tok_json, action_text)

    # 6W 매핑 (extract_six_w 원본 필드명 → 표준 6W 필드명)
    who = raw.get("executor") or "사업주"  # executor_text 보증
    when = raw.get("when_value")
    where = raw.get("where_value") or _TRIGGER_WHERE_FALLBACK.get(trigger_code)  # ISSUE-004
    what = raw.get("what") or (action_text[:40] if action_text else None)
    how = raw.get("how")
    condition = raw.get("condition") or (condition_text[:80] if condition_text else None)

    # why (법령근거) = source_article_id 기반 연결 예정; 현재는 Trigger Code로 대체
    why = f"Trigger: {trigger_code}" if trigger_code else None

    filled = sum(1 for v in [who, when, where, what, how, condition] if v)
    completeness = round(filled / 6, 2)

    return {
        "who": who,
        "when": when,
        "where": where,
        "what": what,
        "how": how,
        "why": why,
        "condition": condition,
        "completeness": completeness,
    }
