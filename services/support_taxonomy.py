# -*- coding: utf-8 -*-
"""TAI 고객응대 taxonomy — 유일 SoT (트랙 A).

설계: 고객응대 AI 1:1 문의 유형 체계.
  - 상위유형 T1~T7 (사용자에게 노출하지 않음. LLM 이 뒷단에서 분류 — 트랙 B).
  - 세부유형 37종 (stable code + 한국어 label + parent_type).
  - 처리축 3종 (KNOWLEDGE / INVESTIGATION / HANDOFF). AI ACTION 은 없다(capability=0).

이 모듈은 '값의 정의(SoT)'만 제공한다. 분류(어느 문의가 어느 type 인지)는 하지 않는다(그건 트랙 B).
저장은 inquiries.type_code / subtype_code / resolution_axis (nullable). 트랙 B 분류기 전까지 NULL.

주의(기존 축과 혼동 금지):
  - inquiry_type (INQUIRY/FEEDBACK) = '문의인가 피드백인가' — 다른 축. 재활용하지 않는다.
  - category (safety/electric/... ) = '무엇에 관한 문의인가' — 다른 축. 삭제/변환하지 않는다.
  - type_code (T1~T7) = '어떤 성격의 질문인가' — 이 모듈이 정의하는 새 축.

라벨은 운영자 표시용. 사용자에게는 내부 code(T2, T2_LEGAL_REASON, HANDOFF 등)를 노출하지 않는다.

기획 GAP(이번에 재설계하지 않음, 기록만):
  - T3 '진행상태'(T3_PROGRESS) 와 T4 '처리·대기'(T4_PROCESSING) 는 의미가 겹칠 수 있다.
  - 과거 T5 '권한부여 요청' 은 본질적으로 처리요청이므로 T7_PERMISSION_ACCOUNT 로 통합했다(별도 subtype 두지 않음).
  이 GAP 들은 트랙 B(분류기) 착수 시 재검토한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ── 처리축 (내부 분석용). ACTION 없음. ──
RESOLUTION_AXES: List[Dict[str, str]] = [
    {"code": "KNOWLEDGE", "label": "지식 답변"},
    {"code": "INVESTIGATION", "label": "조회 확인"},
    {"code": "HANDOFF", "label": "담당자 이관"},
]
RESOLUTION_AXIS_CODES = frozenset(a["code"] for a in RESOLUTION_AXES)

# ── 상위유형 T1~T7 ──
TYPES: List[Dict[str, str]] = [
    {"code": "T1", "label": "사용법·안내"},
    {"code": "T2", "label": "결과·근거 설명"},
    {"code": "T3", "label": "업무현황·상태 조회"},
    {"code": "T4", "label": "오류·장애·처리지연"},
    {"code": "T5", "label": "권한·가시성"},
    {"code": "T6", "label": "변경·영향"},
    {"code": "T7", "label": "처리요청"},
]
TYPE_CODES = frozenset(t["code"] for t in TYPES)

# ── 세부유형 37종 (code · label · parent_type) ──
# T5-5 '권한부여 요청' 은 T7_PERMISSION_ACCOUNT 로 통합(여기 T5 에는 두지 않음).
SUBTYPES: List[Dict[str, str]] = [
    # T1 사용법·안내 (5)
    {"code": "T1_HOW_TO", "label": "기능 사용법", "parent_type": "T1"},
    {"code": "T1_INPUT_FORMAT", "label": "입력 형식", "parent_type": "T1"},
    {"code": "T1_SCREEN_LOCATION", "label": "화면 위치", "parent_type": "T1"},
    {"code": "T1_NEXT_STEP", "label": "다음 단계", "parent_type": "T1"},
    {"code": "T1_SELECTION_GUIDE", "label": "일반 선택 기준", "parent_type": "T1"},
    # T2 결과·근거 설명 (5)
    {"code": "T2_RESULT_REASON", "label": "결과 이유", "parent_type": "T2"},
    {"code": "T2_LEGAL_REASON", "label": "법 적용 이유", "parent_type": "T2"},
    {"code": "T2_RESULT_MEANING", "label": "결과항목 의미", "parent_type": "T2"},
    {"code": "T2_RESULT_DIFF", "label": "이전 결과 차이", "parent_type": "T2"},
    {"code": "T2_EVIDENCE_SOURCE", "label": "근거·출처", "parent_type": "T2"},
    # T3 업무현황·상태 조회 (5)
    {"code": "T3_TODO", "label": "해야 할 업무", "parent_type": "T3"},
    {"code": "T3_INCOMPLETE", "label": "미완료", "parent_type": "T3"},
    {"code": "T3_DEADLINE", "label": "기한·임박", "parent_type": "T3"},
    {"code": "T3_PROGRESS", "label": "진행상태", "parent_type": "T3"},
    {"code": "T3_CONTRACT_STATUS", "label": "계약·이용상태", "parent_type": "T3"},
    # T4 오류·장애·처리지연 (6)
    {"code": "T4_MISSING_INPUT", "label": "필수값 누락", "parent_type": "T4"},
    {"code": "T4_TRANSITION_BLOCKED", "label": "전이조건 미충족", "parent_type": "T4"},
    {"code": "T4_PROCESSING", "label": "처리·대기", "parent_type": "T4"},
    {"code": "T4_EXEC_FAILED", "label": "실행실패", "parent_type": "T4"},
    {"code": "T4_DATA_MISMATCH", "label": "데이터 불일치", "parent_type": "T4"},
    {"code": "T4_UNKNOWN_CAUSE", "label": "원인불명", "parent_type": "T4"},
    # T5 권한·가시성 (4) — 과거 '권한부여 요청' 은 T7 로 통합
    {"code": "T5_MENU_HIDDEN", "label": "메뉴 미노출", "parent_type": "T5"},
    {"code": "T5_OBJECT_HIDDEN", "label": "객체 미노출", "parent_type": "T5"},
    {"code": "T5_ACTION_DISABLED", "label": "수정·버튼 비활성", "parent_type": "T5"},
    {"code": "T5_USER_DIFF", "label": "사용자 간 차이", "parent_type": "T5"},
    # T6 변경·영향 (5)
    {"code": "T6_SITE_PROCESS_IMPACT", "label": "사업장·공정 변경 영향", "parent_type": "T6"},
    {"code": "T6_DIAGNOSIS_INPUT_CHANGE", "label": "진단입력 변경", "parent_type": "T6"},
    {"code": "T6_POST_COMPLETION_EDIT", "label": "완료후 수정 영향", "parent_type": "T6"},
    {"code": "T6_DELETE_HISTORY_IMPACT", "label": "삭제·이력 영향", "parent_type": "T6"},
    {"code": "T6_RELATION_CHANGE_IMPACT", "label": "관계변경 영향", "parent_type": "T6"},
    # T7 처리요청 (6) — AI ACTION 아님. 읽어서 정리 후 HANDOFF.
    {"code": "T7_SELF_SERVICEABLE", "label": "사용자 직접 처리 가능", "parent_type": "T7"},
    {"code": "T7_OPERATOR_ONLY", "label": "운영자 전용 처리", "parent_type": "T7"},
    {"code": "T7_PERMISSION_ACCOUNT", "label": "권한·계정 변경", "parent_type": "T7"},
    {"code": "T7_PAYMENT_REFUND", "label": "결제·환불", "parent_type": "T7"},
    {"code": "T7_DATA_CHANGE", "label": "데이터 변경", "parent_type": "T7"},
    {"code": "T7_ERROR_RECOVERY", "label": "오류복구·재처리", "parent_type": "T7"},
]
SUBTYPE_CODES = frozenset(s["code"] for s in SUBTYPES)

# ── 빠른 조회용 label map (중복 정의 금지 — 위 리스트에서 파생) ──
TYPE_LABELS: Dict[str, str] = {t["code"]: t["label"] for t in TYPES}
SUBTYPE_LABELS: Dict[str, str] = {s["code"]: s["label"] for s in SUBTYPES}
RESOLUTION_AXIS_LABELS: Dict[str, str] = {a["code"]: a["label"] for a in RESOLUTION_AXES}


def type_label(code: Optional[str]) -> Optional[str]:
    """T1~T7 code → 한국어 label. 미지정/미매핑 → None(운영자 UI 에서 '미분류' 처리)."""
    if not isinstance(code, str):
        return None
    return TYPE_LABELS.get(code)


def subtype_label(code: Optional[str]) -> Optional[str]:
    """세부유형 code → 한국어 label. 미지정/미매핑 → None."""
    if not isinstance(code, str):
        return None
    return SUBTYPE_LABELS.get(code)


def resolution_axis_label(code: Optional[str]) -> Optional[str]:
    """처리축 code → 한국어 label. 미지정/미매핑 → None."""
    if not isinstance(code, str):
        return None
    return RESOLUTION_AXIS_LABELS.get(code)


def is_valid_type(code: Optional[str]) -> bool:
    return isinstance(code, str) and code in TYPE_CODES


def is_valid_subtype(code: Optional[str]) -> bool:
    return isinstance(code, str) and code in SUBTYPE_CODES


def is_valid_axis(code: Optional[str]) -> bool:
    return isinstance(code, str) and code in RESOLUTION_AXIS_CODES


def subtype_matches_type(subtype_code: Optional[str], type_code: Optional[str]) -> bool:
    """세부유형이 상위유형에 속하는지(정합성). 둘 중 하나라도 미지정이면 False.

    트랙 B 분류기가 저장 전에 정합성을 스스로 확인할 때 재사용할 수 있는 순수 함수.
    DB constraint 로 강제하지 않는다(app-level SoT + nullable 우선 — 첫 버전 단순화).
    """
    if not is_valid_subtype(subtype_code) or not is_valid_type(type_code):
        return False
    for s in SUBTYPES:
        if s["code"] == subtype_code:
            return s["parent_type"] == type_code
    return False


def taxonomy_snapshot() -> Dict[str, Any]:
    """운영자/분석 도구가 참조할 전체 taxonomy 구조(읽기 전용).

    SaaS 사용자에게는 제공하지 않는다(사용자는 taxonomy 를 읽지 않는다).
    현재 공개 endpoint 는 만들지 않는다 — 소비처가 생기면 그때 이 함수를 재사용한다.
    """
    return {
        "types": TYPES,
        "subtypes": SUBTYPES,
        "resolution_axes": RESOLUTION_AXES,
    }
