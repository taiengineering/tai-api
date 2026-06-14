"""
legal_engine_policy — 법령엔진 어댑터의 적용대상 거름망 (테이블 기반 + 코드 폴백).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)

★ 거름망 원칙 (대표 확정):
  1) 한 거름망 = 한 조건. (두 조건 섞으면 느리고 추적 어려움)
  2) 어느 망에서 걸렸는지 추적 가능(trace).
  3) 필요한 망을 먼저 여러 개 짜둔다.
  4) 하나씩 걸러보며 어느 망이 얼마나 거르는지 측정 → 순서가 드러난다.
  5) 부족하면 망을 겹으로 더 쌓는다. 한 망에 조건을 더 넣지 않는다.
  6) ★ 노가다가 효율적인 국면: 망 규칙을 **DB 테이블(legal_sieve_rule)에 한 줄씩** 쌓는다.
     코드 수정 없이 행 추가로 망이 늘어난다. 수백 장이 돼도 코드는 안 비대해진다.

망 규칙 = legal_sieve_rule 행:
  sieve_group / target_field / match_type(exact|regex|contains) / pattern /
  verdict(KEEP|DROP) / class_label / priority(작을수록 먼저) / enabled

처분(최종): priority 순으로 첫 매치의 verdict 채택.
  KEEP       → 추출(사업장 적용대상)
  DROP       → 버림(명백히 사업장 대상 아님)
  미매치(어느 행에도 안 걸림) → KEEP_REVIEW(보류=빠짐없이)

★ "빠짐없이": 명백한 것만 버린다(DROP 행에 걸린 것). 모르면 남긴다(보류).
   Jason Morris: 모르는 값 0/false로 안 깖.

오염 격리: 법령 도메인 지식(수범자 종류)은 여기(어댑터측)·DB에만. 체크엔진 코어엔 안 넣음.
범위: 적용대상 1차(executor, 단위 없는 =/have). 규모 수치(≥,≤)는 별도 sieve_group으로 추가 예정.

규칙 캐시: 테이블을 매 건마다 읽지 않도록 프로세스 캐시. reload_rules()로 갱신.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ── 최종 처분 ──
DECISION_KEEP = "KEEP"               # 추출
DECISION_KEEP_REVIEW = "KEEP_REVIEW" # 보류(빠짐없이)
DECISION_DROP = "DROP"               # 버림

# 분류 라벨(추적·표시)
APPLY_BUSINESS = "BUSINESS"
APPLY_AUTHORITY = "AUTHORITY"
APPLY_FRAGMENT = "FRAGMENT"
APPLY_AMBIGUOUS = "AMBIGUOUS"

_SIEVE_TABLE = "legal_sieve_rule"
_CACHE_TTL_SEC = 300

# 프로세스 캐시: {sieve_group: [(priority, match_type, pattern, compiled, verdict, class_label), ...]}
_rule_cache: Dict[str, List[Tuple[int, str, str, Any, str, str]]] = {}
_cache_at: float = 0.0


def _compile_row(match_type: str, pattern: str):
    if match_type == "regex":
        try:
            return re.compile(pattern)
        except re.error:
            return None
    return None  # exact / contains 는 컴파일 불필요


def load_rules(supabase, sieve_group: str = "applicability", force: bool = False
               ) -> List[Tuple[int, str, str, Any, str, str]]:
    """테이블에서 활성 망 규칙을 priority 순으로 로드(캐시)."""
    global _cache_at
    now = time.time()
    if not force and sieve_group in _rule_cache and (now - _cache_at) < _CACHE_TTL_SEC:
        return _rule_cache[sieve_group]
    rules: List[Tuple[int, str, str, Any, str, str]] = []
    try:
        res = (
            supabase.table(_SIEVE_TABLE)
            .select("priority, match_type, pattern, verdict, class_label")
            .eq("sieve_group", sieve_group)
            .eq("enabled", True)
            .order("priority")
            .execute()
        )
        for r in res.data or []:
            mt = (r.get("match_type") or "regex").strip()
            pat = r.get("pattern") or ""
            rules.append((
                int(r.get("priority") or 100),
                mt, pat, _compile_row(mt, pat),
                (r.get("verdict") or "").strip().upper(),
                (r.get("class_label") or "").strip().upper(),
            ))
    except Exception:
        # 테이블 못 읽으면 코드 폴백 사용
        return _FALLBACK_RULES
    if not rules:
        return _FALLBACK_RULES
    _rule_cache[sieve_group] = rules
    _cache_at = now
    return rules


def reload_rules():
    """캐시 비움 — 테이블에 망 추가 후 호출."""
    global _cache_at
    _rule_cache.clear()
    _cache_at = 0.0


def _match(match_type: str, pattern: str, compiled, ex: str) -> bool:
    if match_type == "exact":
        return ex == pattern
    if match_type == "contains":
        return pattern in ex
    if compiled is not None:
        return compiled.search(ex) is not None
    return False


def classify_with_rules(executor_text: str, rules) -> Tuple[str, str, Optional[int]]:
    """규칙(priority 순)을 한 줄씩 적용. 첫 매치의 verdict 채택.

    반환: (분류 class_label, 처분 DECISION_*, 걸린 priority|None)
    어느 행에도 안 걸리면 (AMBIGUOUS, KEEP_REVIEW, None) — 보류(빠짐없이).
    """
    ex = (executor_text or "").strip()
    if not ex:
        return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW, None
    for priority, mt, pat, compiled, verdict, label in rules:
        if _match(mt, pat, compiled, ex):
            decision = DECISION_KEEP if verdict == "KEEP" else DECISION_DROP
            return (label or APPLY_AMBIGUOUS), decision, priority
    return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW, None


# ════════════════════════════════════════════════════════════════════
# 코드 폴백 (테이블 못 읽을 때만). 테이블이 정상이면 안 쓰임.
# ════════════════════════════════════════════════════════════════════
def _fallback_list() -> List[Tuple[int, str, str, Any, str, str]]:
    frag_noun = ("사항|회의|과태료|사유|내용|경우|기준|방법|절차|사실|결과|효력|범위|"
                 "기간|금액|비용|수수료|벌금|세부사항|미수범|자에게|당사자")
    biz = (r"(사업주|사업자|사용자|관리주체|사업주체|관리자$|소유자|점유자|관계인|발주자|"
           r"도급인|수급인|건설공사도급인|건설공사발주자|제조업자|수입자|판매자|영업자|"
           r"설치자|운영자|소방안전관리자|안전보건관리책임자|대표자|법인|공사시공자|시공자|"
           r"건축주|시행자|사업시행자|신청인|개설자|제작자|수입업자|등록사업자|려는 (자|사람|기업|법인)$)")
    auth = (r"(장관|지사|청장|군수|구청장|시장|위원장|위원회|위원$|공단|허가권자|발주청|"
            r"교육감|이사장|기관의 장|관서의 장|과학원장|처장|본부장|차장|^정부$|^국가$|"
            r"^지방자치단체$|^공무원$|^회의$|행정기관의 장|중앙행정기관|소방본부장|소방서장|"
            r"경찰청장|경찰서장|세무서장|관리청|감독기관|관서장|소방관서장|자원관리관|간사$|^감사$)")
    return [
        (10, "regex", f"^({frag_noun})$", re.compile(f"^({frag_noun})$"), "DROP", APPLY_FRAGMENT),
        (20, "regex", r"^.{1,4}(하|되|함|음|정|것|시|려|어|아)$",
         re.compile(r"^.{1,4}(하|되|함|음|정|것|시|려|어|아)$"), "DROP", APPLY_FRAGMENT),
        (30, "regex", biz, re.compile(biz), "KEEP", APPLY_BUSINESS),
        (40, "regex", auth, re.compile(auth), "DROP", APPLY_AUTHORITY),
    ]

_FALLBACK_RULES = _fallback_list()


# ── 호출부 인터페이스 ──
def classify_applicability(executor_text: str, supabase=None) -> Tuple[str, str]:
    """수범자 → (분류, 처분). supabase 주면 테이블 규칙, 없으면 코드 폴백."""
    rules = load_rules(supabase) if supabase is not None else _FALLBACK_RULES
    cls, decision, _ = classify_with_rules(executor_text, rules)
    return cls, decision


def applicability_trace(executor_text: str, supabase=None) -> Dict[str, object]:
    """디버그/측정용 — 걸린 규칙 priority까지."""
    rules = load_rules(supabase) if supabase is not None else _FALLBACK_RULES
    cls, decision, pri = classify_with_rules(executor_text, rules)
    return {
        "executor": (executor_text or "").strip(),
        "class": cls,
        "decision": decision,
        "matched_priority": pri,
    }
