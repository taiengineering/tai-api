"""
legal_engine_policy — 법령엔진 어댑터의 적용대상 거름망 (망 분리 구조).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)

★ 거름망 원칙 (대표 확정):
  1) 한 거름망 = 한 조건. (두 조건 섞으면 느리고 추적 어려움)
  2) 한 조건이라 빨리 통과하고, 어느 망에서 걸렸는지 추적 가능(trace).
  3) 필요하다고 생각되는 망을 먼저 여러 개 짜둔다.
  4) 하나씩 걸러보며 어느 망이 얼마나 거르는지 측정 → 먼저/나중 순서가 드러난다.
     (순서를 미리 추측하지 않는다. 걸러보고 발견한다.)
  5) 부족하면 망을 겹으로 더 쌓는다. 한 망에 조건을 더 넣지 않는다.

각 망(Sieve)은 executor 1건을 받아 판정 하나를 반환:
  PASS   이 망의 조건에 안 걸림 → 다음 망으로
  DROP   이 망이 "버린다"고 판정 (명백히 사업장 대상 아님)
  KEEP   이 망이 "담는다"고 판정 (사업장 적용대상)
각 망은 자기 이름과 판정·이유를 trace에 남긴다.

처분(최종): KEEP / KEEP_REVIEW(보류=빠짐없이) / DROP.

★ "빠짐없이": 어느 KEEP망에도 안 담기고 어느 DROP망에도 안 걸린 것 = 보류(KEEP_REVIEW).
   명백한 것만 버린다. 모르면 남긴다(Jason Morris: 모르는 값 0/false로 안 깖).

오염 격리: 법령 도메인 지식(수범자 종류)은 여기(어댑터측)에만. 체크엔진 코어엔 안 넣음.
범위: 적용대상 1차 판정(=, have / 단위 없음). 규모 수치(≥,≤)는 별도 망(2차)으로 추가 예정.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Tuple

# ── 망 판정값 ──
PASS = "PASS"      # 이 망 통과 (다음 망으로)
DROP = "DROP"      # 이 망이 버림
KEEP = "KEEP"      # 이 망이 담음

# ── 최종 처분 ──
DECISION_KEEP = "KEEP"               # 추출
DECISION_KEEP_REVIEW = "KEEP_REVIEW" # 보류(빠짐없이)
DECISION_DROP = "DROP"               # 버림

# ════════════════════════════════════════════════════════════════════
# 망 정의 — 각 망은 한 조건만. (executor) → (판정 PASS/DROP/KEEP)
# 순서는 SIEVE_ORDER에서 정한다. 지금은 한 줄로 켜고 끄며 측정 가능.
# ════════════════════════════════════════════════════════════════════

# 망1 조건: 비어있는 수범자
def sieve_empty(ex: str) -> str:
    return DROP if not ex else PASS  # 빈 건 의무 아님으로 취급(단, 처분은 호출부서 REVIEW로 완화 가능)

# 망2 조건: 비주체 명사 (사항/비용/금액 등 — 의무의 주체가 아님)
_FRAGMENT_NOUN = frozenset({
    "사항", "회의", "과태료", "사유", "내용", "경우", "기준", "방법", "절차",
    "사실", "결과", "효력", "범위", "기간", "금액", "비용", "수수료", "벌금",
    "세부사항", "미수범", "자에게", "당사자", "사항등", "기타",
})
def sieve_fragment_noun(ex: str) -> str:
    return DROP if ex in _FRAGMENT_NOUN else PASS

# 망3 조건: 동사조각 (짧고 동사어간으로 끝남 — 분해 잔여)
_FRAGMENT_SUFFIX = re.compile(r"(하|되|함|음|정|것|시|려|어|아)$")
def sieve_fragment_verb(ex: str) -> str:
    if len(ex) <= 4 and _FRAGMENT_SUFFIX.search(ex):
        return DROP
    return PASS

# 망4 조건: 행정청·기관 (장관/지사/청장/위원회 — 사업장 의무 아님)
_AUTHORITY = re.compile(
    r"(장관|지사|청장|군수|구청장|시장|위원장|위원회|위원$|"
    r"공단|허가권자|발주청|교육감|이사장|기관의\s*장|관서의\s*장|"
    r"과학원장|처장|본부장|차장|^정부$|^국가$|^지방자치단체$|^공무원$|"
    r"^회의$|^위원$|행정기관의\s*장|중앙행정기관|소방본부장|소방서장|"
    r"경찰청장|경찰서장|세무서장|관할\s*행정청|관리청|감독기관|관서장|"
    r"소방관서장|자원관리관|간사$|^감사$)"
)
def sieve_authority(ex: str) -> str:
    return DROP if _AUTHORITY.search(ex) else PASS

# 망5 조건: 사업장 주체 (사업주/사업자/~하려는 자/건축주 — 적용대상)
_BUSINESS = re.compile(
    r"(사업주|사업자|사용자|관리주체|사업주체|관리자$|소유자|점유자|"
    r"관계인|발주자|도급인|수급인|건설공사도급인|건설공사발주자|"
    r"제조업자|수입자|판매자|영업자|설치자|운영자|소방안전관리자|"
    r"안전보건관리책임자|대표자|법인|공사시공자|시공자|"
    r"건축주|시행자|사업시행자|신청인|개설자|제작자|수입업자|"
    r"제조ㆍ수입업자|제조·수입업자|등록사업자|사업계획승인권자|"
    r"려는\s*(자|사람|기업|법인)$)"
)
def sieve_business(ex: str) -> str:
    return KEEP if _BUSINESS.search(ex) else PASS


# 망 레지스트리: (이름, 함수). 순서는 SIEVE_ORDER가 정함.
SIEVES: Dict[str, Callable[[str], str]] = {
    "empty": sieve_empty,
    "fragment_noun": sieve_fragment_noun,
    "fragment_verb": sieve_fragment_verb,
    "authority": sieve_authority,
    "business": sieve_business,
}

# 적용 순서 (지금은 이 순서로 켜본다. 측정 결과로 바꾼다 — 미리 확정 아님).
# 먼저/나중은 "하나씩 걸러보며" 데이터로 정한다.
SIEVE_ORDER: List[str] = [
    "empty",
    "fragment_noun",
    "fragment_verb",
    "business",      # 담기를 버리기보다 먼저: "건설공사도급인"이 authority보다 우선
    "authority",
]


def run_sieves(
    executor_text: str,
    order: List[str] = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """망을 순서대로 한 개씩 통과시킨다. 첫 DROP/KEEP에서 멈춤.

    반환: (최종 처분 DECISION_*, trace[{sieve, verdict}])
    - 어떤 망이 KEEP → DECISION_KEEP
    - 어떤 망이 DROP → DECISION_DROP
    - 모든 망 PASS → DECISION_KEEP_REVIEW (보류, 빠짐없이)
    각 망 통과 여부가 trace에 남아 추적 가능.
    """
    ex = (executor_text or "").strip()
    use = order or SIEVE_ORDER
    trace: List[Dict[str, str]] = []
    for name in use:
        fn = SIEVES.get(name)
        if fn is None:
            continue
        verdict = fn(ex)
        trace.append({"sieve": name, "verdict": verdict})
        if verdict == DROP:
            return DECISION_DROP, trace
        if verdict == KEEP:
            return DECISION_KEEP, trace
    # 모든 망 통과 = 어디에도 안 걸림 → 보류(빠짐없이)
    return DECISION_KEEP_REVIEW, trace


# ── 하위호환: 기존 호출부(adapter_run)가 쓰는 인터페이스 유지 ──
APPLY_BUSINESS = "BUSINESS"
APPLY_AUTHORITY = "AUTHORITY"
APPLY_FRAGMENT = "FRAGMENT"
APPLY_AMBIGUOUS = "AMBIGUOUS"


def classify_applicability(executor_text: str) -> Tuple[str, str]:
    """기존 인터페이스 — (분류, 처분). 내부는 망 구조로 위임.

    분류는 trace의 마지막 망 이름에서 유도(추적성 유지).
    """
    decision, trace = run_sieves(executor_text)
    last = trace[-1]["sieve"] if trace else ""
    if decision == DECISION_KEEP:
        cls = APPLY_BUSINESS
    elif decision == DECISION_DROP:
        cls = APPLY_AUTHORITY if last == "authority" else APPLY_FRAGMENT
    else:
        cls = APPLY_AMBIGUOUS
    return cls, decision


def applicability_trace(executor_text: str) -> Dict[str, object]:
    """디버그/측정용 — 망별 통과 기록까지 반환(어느 망에서 걸렸나)."""
    decision, trace = run_sieves(executor_text)
    return {
        "executor": (executor_text or "").strip(),
        "decision": decision,
        "trace": trace,
        "stopped_at": trace[-1]["sieve"] if trace else None,
    }
