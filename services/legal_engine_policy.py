"""
legal_engine_policy — 법령엔진 어댑터의 policyProvider (RASE 적용대상 판정).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)

역할: RASE의 Applicability(적용대상) 판정 = "이 의무의 수범자(executor)가
      '사업장'이 이행할 대상인가"를 분류한다.

분류(닫힌 분류 — 의미해석이 아니라 수범자 종류 가르기):
  AUTHORITY   행정청·기관(장관/지사/청장/위원회/공단...)  → 사업장 의무 아님 → 제외(DROP)
  FRAGMENT    동사조각·비주체명사(해당하/사항/정하/회의...) → 의무 아님 → 제외(DROP)
  BUSINESS    사업장 주체(사업주/사업자/사용자/관리주체...)  → 적용대상 → 추출(KEEP)
  AMBIGUOUS   미분류/애매                                  → 보류(KEEP_REVIEW, "빠짐없이")

★ 목적 "빠짐없이": AUTHORITY/FRAGMENT처럼 **명백히 사업장 대상이 아닌 것만 버린다.**
  애매·미상(AMBIGUOUS)은 버리지 않고 남긴다(추출 후보). 빠뜨리는 것보다 후보로 남겨
  사용자·전문가가 보게 한다.

★ Jason Morris 교훈: 모르는 값을 0/false로 깔지 않는다. 모르면 AMBIGUOUS(보류).

오염 격리: 이 파일은 법령 도메인 지식(수범자 종류)을 담는다. 체크엔진 코어(범용)에는
절대 넣지 않는다. 어댑터 측(여기)에만 둔다. 규칙으로 안 잡히는 잔여 판정에 LLM을 쓸
경우에도 이 단계(어댑터)에서만(코어 오염 금지).

주의: 이것은 사업장 적용대상 1차 판정(=, have / 단위 없음)이다. 규모 요건(수치 ≥,≤)은
2차로 별도(condition 기반). 여기선 적용대상만.
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

# ── 행정청·기관 (사업장 의무 아님). 접미사·고정명 규칙으로 거의 다 잡힘 ──
_AUTHORITY = re.compile(
    r"(장관|지사|청장|군수|구청장|시장|위원장|위원회|위원$|"
    r"공단|허가권자|발주청|교육감|이사장|기관의\s*장|관서의\s*장|"
    r"과학원장|처장|본부장|차장|^정부$|^국가$|^지방자치단체$|^공무원$|"
    r"^회의$|^위원$|행정기관의\s*장|중앙행정기관|소방본부장|소방서장|"
    r"경찰청장|경찰서장|세무서장|관할\s*행정청|관리청|감독기관)"
)

# ── 사업장 주체 (적용대상). 사업장이 이행하는 의무의 수범자 ──
_BUSINESS = re.compile(
    r"(사업주|사업자|사용자|관리주체|사업주체|관리자$|소유자|점유자|"
    r"관계인|발주자|도급인|수급인|건설공사도급인|건설공사발주자|"
    r"제조업자|수입자|판매자|영업자|설치자|운영자|소방안전관리자|"
    r"안전보건관리책임자|대표자|법인|공사시공자|시공자)"
)

# ── 조각·비주체 (의무 아님). 동사어간·추상명사 ──
_FRAGMENT_SUFFIX = re.compile(r"(하|되|함|음|정|것|시|려|어|아)$")
_FRAGMENT_NOUN = frozenset({
    "사항", "회의", "과태료", "사유", "정하", "해당하", "설치하", "사용하",
    "도급하", "판단되", "내용", "경우", "기준", "방법", "절차", "사실",
    "결과", "효력", "범위", "기간", "금액", "비용", "수수료", "벌금",
})


def classify_applicability(executor_text: str) -> Tuple[str, str]:
    """수범자(executor) → (적용대상 분류, 처분).

    반환: (APPLY_*, DECISION_*)
    """
    ex = (executor_text or "").strip()

    # 빈 수범자 → 미상 → 보류(빠짐없이)
    if not ex:
        return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW

    # 1) 명백한 조각·비주체 → 버림
    if ex in _FRAGMENT_NOUN:
        return APPLY_FRAGMENT, DECISION_DROP
    if len(ex) <= 4 and _FRAGMENT_SUFFIX.search(ex) and not _BUSINESS.search(ex):
        # 짧고 동사어간으로 끝나며 사업장주체 단어도 아님 → 조각
        return APPLY_FRAGMENT, DECISION_DROP

    # 2) 사업장 주체 → 추출 (BUSINESS가 AUTHORITY보다 우선:
    #    "건설공사도급인" 등은 사업장이 맞음)
    if _BUSINESS.search(ex):
        return APPLY_BUSINESS, DECISION_KEEP

    # 3) 행정청·기관 → 버림 (사업장 의무 아님)
    if _AUTHORITY.search(ex):
        return APPLY_AUTHORITY, DECISION_DROP

    # 4) 그 외 → 미상 → 보류(빠짐없이: 버리지 않고 남김)
    return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW


def applicability_summary(executor_text: str) -> Dict[str, str]:
    """디버그/표시용 — 분류 결과를 dict로."""
    cls, decision = classify_applicability(executor_text)
    return {
        "executor": (executor_text or "").strip(),
        "applicability_class": cls,
        "decision": decision,
    }
