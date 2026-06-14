"""
legal_engine_policy — 법령엔진 어댑터의 policyProvider (RASE 적용대상 판정).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)

역할: RASE의 Applicability(적용대상) 판정 = "이 의무의 수범자(executor)가
      '사업장'이 이행할 대상인가"를 분류한다.

분류(닫힌 분류 — 의미해석이 아니라 수범자 종류 가르기):
  AUTHORITY   행정청·기관(장관/지사/청장/위원회/공단...)  → 사업장 의무 아님 → 제외(DROP)
  FRAGMENT    동사조각·비주체명사(해당하/사항/비용/금액...) → 의무 아님 → 제외(DROP)
  BUSINESS    사업장 주체(사업주/사업자/~하려는 자/건축주...) → 적용대상 → 추출(KEEP)
  AMBIGUOUS   미분류/애매(기관인지 사업장인지 등)          → 보류(KEEP_REVIEW, "빠짐없이")

★ 목적 "빠짐없이": AUTHORITY/FRAGMENT처럼 **명백히 사업장 대상이 아닌 것만 버린다.**
  애매·미상(AMBIGUOUS)은 버리지 않고 남긴다(추출 후보).

★ 거름망 원칙(대표): 단계를 겹치되 각 단계 구멍을 비율적으로 줄여야 옆으로 안 샌다.
  AMBIGUOUS(보류)는 구멍이다. 그 안에서 명백한 버릴 것(비주체 명사)과 담을 것(신청·사업
  주체)을 규칙에 추가해 구멍을 좁힌다. 진짜 애매(기관 등)만 보류로 남긴다.
  v2 보강: 비주체 명사(사항/비용/금액 등) → FRAGMENT, "~하려는/받으려는/신청 + 자/사람",
  건축주·시행자·신청인·제작자·수입업자 등 → BUSINESS.

★ Jason Morris 교훈: 모르는 값을 0/false로 깔지 않는다. 모르면 AMBIGUOUS(보류).

오염 격리: 이 파일은 법령 도메인 지식(수범자 종류)을 담는다. 체크엔진 코어(범용)에는
절대 넣지 않는다. 어댑터 측(여기)에만 둔다.

주의: 사업장 적용대상 1차 판정(=, have / 단위 없음). 규모 요건(수치 ≥,≤)은 2차 별도.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

# 판정값
APPLY_BUSINESS = "BUSINESS"      # 사업장 적용대상 → KEEP
APPLY_AUTHORITY = "AUTHORITY"    # 행정청·기관 → DROP
APPLY_FRAGMENT = "FRAGMENT"      # 조각·비주체 → DROP
APPLY_AMBIGUOUS = "AMBIGUOUS"    # 미상·애매 → KEEP(보류, 빠짐없이)

# 처분
DECISION_KEEP = "KEEP"               # 추출(담음)
DECISION_KEEP_REVIEW = "KEEP_REVIEW" # 보류로 담음(빠짐없이)
DECISION_DROP = "DROP"               # 버림(명백히 사업장 대상 아님)

# ── 행정청·기관 (사업장 의무 아님) ──
_AUTHORITY = re.compile(
    r"(장관|지사|청장|군수|구청장|시장|위원장|위원회|위원$|"
    r"공단|허가권자|발주청|교육감|이사장|기관의\s*장|관서의\s*장|"
    r"과학원장|처장|본부장|차장|^정부$|^국가$|^지방자치단체$|^공무원$|"
    r"^회의$|^위원$|행정기관의\s*장|중앙행정기관|소방본부장|소방서장|"
    r"경찰청장|경찰서장|세무서장|관할\s*행정청|관리청|감독기관|관서장|"
    r"소방관서장|자원관리관|간사$|^감사$)"
)

# ── 사업장 주체 (적용대상) ──
# v2: 신청·행위 주체("~하려는/받으려는/지정받으려는/신고하려는 + 자/사람"),
#     건축주·시행자·사업시행자·신청인·개설자·제작자·수입업자 등 추가.
_BUSINESS = re.compile(
    r"(사업주|사업자|사용자|관리주체|사업주체|관리자$|소유자|점유자|"
    r"관계인|발주자|도급인|수급인|건설공사도급인|건설공사발주자|"
    r"제조업자|수입자|판매자|영업자|설치자|운영자|소방안전관리자|"
    r"안전보건관리책임자|대표자|법인|공사시공자|시공자|"
    r"건축주|시행자|사업시행자|신청인|개설자|제작자|수입업자|"
    r"제조ㆍ수입업자|제조·수입업자|등록사업자|사업계획승인권자|"
    r"(하|받으|지정받으|신고하|신청하|등록하|승인받으)려는\s*(자|사람|기업|법인)$|"
    r"려는\s*자$|려는\s*사람$)"
)

# ── 조각·비주체 (의무 아님) ──
# v2: 비주체 명사(사항/비용/금액/내용/세부사항 등) 확대. "미수범" 등 벌칙 잔여 포함.
_FRAGMENT_SUFFIX = re.compile(r"(하|되|함|음|정|것|시|려|어|아)$")
_FRAGMENT_NOUN = frozenset({
    "사항", "회의", "과태료", "사유", "정하", "해당하", "설치하", "사용하",
    "도급하", "판단되", "내용", "경우", "기준", "방법", "절차", "사실",
    "결과", "효력", "범위", "기간", "금액", "비용", "수수료", "벌금",
    "세부사항", "미수범", "자에게", "당사자",
})


def classify_applicability(executor_text: str) -> Tuple[str, str]:
    """수범자(executor) → (적용대상 분류, 처분)."""
    ex = (executor_text or "").strip()

    # 빈 수범자 → 미상 → 보류(빠짐없이)
    if not ex:
        return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW

    # 1) 명백한 조각·비주체 → 버림
    if ex in _FRAGMENT_NOUN:
        return APPLY_FRAGMENT, DECISION_DROP
    if len(ex) <= 4 and _FRAGMENT_SUFFIX.search(ex) and not _BUSINESS.search(ex):
        return APPLY_FRAGMENT, DECISION_DROP

    # 2) 사업장 주체 → 추출 (BUSINESS가 AUTHORITY보다 우선)
    if _BUSINESS.search(ex):
        return APPLY_BUSINESS, DECISION_KEEP

    # 3) 행정청·기관 → 버림
    if _AUTHORITY.search(ex):
        return APPLY_AUTHORITY, DECISION_DROP

    # 4) 그 외 → 미상 → 보류(빠짐없이)
    return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW


def applicability_summary(executor_text: str) -> Dict[str, str]:
    """디버그/표시용."""
    cls, decision = classify_applicability(executor_text)
    return {
        "executor": (executor_text or "").strip(),
        "applicability_class": cls,
        "decision": decision,
    }
