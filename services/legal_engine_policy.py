"""
legal_engine_policy — 법령엔진 어댑터의 거름망 (테이블 기반, 다중 sieve_group).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)

★ 거름망 원칙 (대표 확정):
  1) 한 거름망 = 한 조건. (두 조건 섞으면 느리고 추적 어려움)
  2) 어느 망에서 걸렸는지 추적 가능(trace).
  3) 필요한 망을 먼저 여러 개 짜둔다.
  4) 하나씩 걸러보며 어느 망이 얼마나 거르는지 측정 → 순서가 드러난다.
  5) 부족하면 망을 겹으로 더 쌓는다.
  6) 노가다가 효율적: 망 규칙을 DB 테이블(legal_sieve_rule)에 한 줄씩. 코드수정 없이 행 추가.
  7) ★ 섹터 거름은 앞단 매칭표(law_sector_mapping)가 아니라 여기(거름망)서 한다.
     이유(대표 판단): 법 단위 매칭표는 거칠다(산안법이 건설에도 적용→제조업 작업장의무까지
     딸려옴). 의미절 단위(clause_sector)로 거름망에서 걸러야 결과가 좋아진다. 거름이 옳다.

망 그룹(sieve_group):
  'sector'        — clause_sector(의미절 sector)가 사업장 섹터에 안 맞으면 DROP. priority 5(먼저).
                    applies_facility_sector = 이 망이 적용될 사업장 섹터(CONSTRUCTION/BUILDING/INDUSTRIAL).
  'applicability' — executor(수범자)가 사업장 적용대상인가. priority 10~40.

처분: priority 순 첫 매치의 verdict 채택. 미매치=KEEP_REVIEW(보류=빠짐없이).
  COMMON·미정 clause_sector는 sector망에 행이 없어 통과(빠짐없이).

오염 격리: 도메인 지식은 여기·DB에만. 체크엔진 코어엔 안 넣음.
캐시: reload_rules()로 갱신.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

# ── 최종 처분 ──
DECISION_KEEP = "KEEP"
DECISION_KEEP_REVIEW = "KEEP_REVIEW"
DECISION_DROP = "DROP"

# 분류 라벨
APPLY_BUSINESS = "BUSINESS"
APPLY_AUTHORITY = "AUTHORITY"
APPLY_FRAGMENT = "FRAGMENT"
APPLY_AMBIGUOUS = "AMBIGUOUS"
SECTOR_MISMATCH = "SECTOR_MISMATCH"

_SIEVE_TABLE = "legal_sieve_rule"
_CACHE_TTL_SEC = 300

# 캐시: {sieve_group: [rule, ...]}; rule = dict(priority, match_type, pattern, compiled,
#                                               verdict, class_label, target_field, applies_sector)
_rule_cache: Dict[str, List[Dict[str, Any]]] = {}
_cache_at: float = 0.0


def _compile_row(match_type: str, pattern: str):
    if match_type == "regex":
        try:
            return re.compile(pattern)
        except re.error:
            return None
    return None


def load_rules(supabase, sieve_group: str, force: bool = False) -> List[Dict[str, Any]]:
    """테이블에서 활성 망 규칙을 priority 순으로 로드(캐시)."""
    global _cache_at
    now = time.time()
    if not force and sieve_group in _rule_cache and (now - _cache_at) < _CACHE_TTL_SEC:
        return _rule_cache[sieve_group]
    rules: List[Dict[str, Any]] = []
    try:
        res = (
            supabase.table(_SIEVE_TABLE)
            .select("priority, match_type, pattern, verdict, class_label, target_field, applies_facility_sector")
            .eq("sieve_group", sieve_group)
            .eq("enabled", True)
            .order("priority")
            .execute()
        )
        for r in res.data or []:
            mt = (r.get("match_type") or "regex").strip()
            pat = r.get("pattern") or ""
            rules.append({
                "priority": int(r.get("priority") or 100),
                "match_type": mt,
                "pattern": pat,
                "compiled": _compile_row(mt, pat),
                "verdict": (r.get("verdict") or "").strip().upper(),
                "class_label": (r.get("class_label") or "").strip().upper(),
                "target_field": (r.get("target_field") or "executor_text").strip(),
                "applies_sector": (r.get("applies_facility_sector") or "").strip().upper() or None,
            })
    except Exception:
        return _FALLBACK_APPLICABILITY if sieve_group == "applicability" else []
    if not rules and sieve_group == "applicability":
        return _FALLBACK_APPLICABILITY
    _rule_cache[sieve_group] = rules
    _cache_at = now
    return rules


def reload_rules():
    global _cache_at
    _rule_cache.clear()
    _cache_at = 0.0


def _match(rule: Dict[str, Any], value: str) -> bool:
    mt = rule["match_type"]
    if mt == "exact":
        return value == rule["pattern"]
    if mt == "contains":
        return rule["pattern"] in value
    c = rule["compiled"]
    return c is not None and c.search(value) is not None


def sieve_clause(
    clause: Dict[str, Any],
    facility_sector: str,
    supabase,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """의미절 1건을 거름망에 통과시킨다. (sector망 → applicability망 순)

    반환: (분류 class_label, 처분 DECISION_*, trace[{group, field, value, verdict, priority}])
    - 어떤 망이 DROP → 즉시 DROP
    - applicability망이 KEEP → KEEP
    - 모든 망 미매치 → KEEP_REVIEW (보류=빠짐없이)
    """
    fac = (facility_sector or "").strip().upper()
    trace: List[Dict[str, Any]] = []

    # ── 망 그룹 1: sector (clause_sector가 사업장 섹터에 안 맞으면 DROP) ──
    clause_sector = (clause.get("sector") or "").strip().upper()
    if clause_sector:  # 미정(빈값)은 거르지 않음(빠짐없이)
        for r in load_rules(supabase, "sector"):
            # 이 망이 현재 사업장 섹터에 적용되는 것만
            if r["applies_sector"] and r["applies_sector"] != fac:
                continue
            if _match(r, clause_sector):
                trace.append({"group": "sector", "field": "clause_sector",
                              "value": clause_sector, "verdict": r["verdict"],
                              "priority": r["priority"], "label": r["class_label"]})
                if r["verdict"] == "DROP":
                    return SECTOR_MISMATCH, DECISION_DROP, trace
                if r["verdict"] == "KEEP":
                    return r["class_label"] or APPLY_BUSINESS, DECISION_KEEP, trace

    # ── 망 그룹 2: applicability (executor 수범자) ──
    executor = (clause.get("executor_text") or "").strip()
    if not executor:
        return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW, trace
    for r in load_rules(supabase, "applicability"):
        if r["applies_sector"] and r["applies_sector"] != fac:
            continue
        if _match(r, executor):
            decision = DECISION_KEEP if r["verdict"] == "KEEP" else DECISION_DROP
            trace.append({"group": "applicability", "field": "executor_text",
                          "value": executor, "verdict": r["verdict"],
                          "priority": r["priority"], "label": r["class_label"]})
            return (r["class_label"] or APPLY_AMBIGUOUS), decision, trace

    # 모든 망 미매치 → 보류(빠짐없이)
    return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW, trace


# ════════════════════════════════════════════════════════════════════
# 코드 폴백 (applicability 테이블 못 읽을 때만)
# ════════════════════════════════════════════════════════════════════
def _fallback_applicability() -> List[Dict[str, Any]]:
    frag = ("사항|회의|과태료|사유|내용|경우|기준|방법|절차|사실|결과|효력|범위|"
            "기간|금액|비용|수수료|벌금|세부사항|미수범|자에게|당사자")
    biz = (r"(사업주|사업자|사용자|관리주체|사업주체|관리자$|소유자|점유자|관계인|발주자|"
           r"도급인|수급인|건설공사도급인|건설공사발주자|제조업자|수입자|판매자|영업자|"
           r"설치자|운영자|소방안전관리자|안전보건관리책임자|대표자|법인|공사시공자|시공자|"
           r"건축주|시행자|사업시행자|신청인|개설자|제작자|수입업자|등록사업자|려는 (자|사람|기업|법인)$)")
    auth = (r"(장관|지사|청장|군수|구청장|시장|위원장|위원회|위원$|공단|허가권자|발주청|"
            r"교육감|이사장|기관의 장|관서의 장|과학원장|처장|본부장|차장|^정부$|^국가$|"
            r"^지방자치단체$|^공무원$|^회의$|행정기관의 장|중앙행정기관|소방본부장|소방서장|"
            r"경찰청장|경찰서장|세무서장|관리청|감독기관|관서장|소방관서장|자원관리관|간사$|^감사$)")
    def mk(pri, pat, verdict, label):
        return {"priority": pri, "match_type": "regex", "pattern": pat,
                "compiled": re.compile(pat), "verdict": verdict, "class_label": label,
                "target_field": "executor_text", "applies_sector": None}
    return [
        mk(10, f"^({frag})$", "DROP", APPLY_FRAGMENT),
        mk(20, r"^.{1,4}(하|되|함|음|정|것|시|려|어|아)$", "DROP", APPLY_FRAGMENT),
        mk(30, biz, "KEEP", APPLY_BUSINESS),
        mk(40, auth, "DROP", APPLY_AUTHORITY),
    ]

_FALLBACK_APPLICABILITY = _fallback_applicability()


# ── 하위호환: executor만 보는 기존 인터페이스 ──
def classify_applicability(executor_text: str, supabase=None) -> Tuple[str, str]:
    """executor만 판정(섹터망 제외). 하위호환용."""
    rules = load_rules(supabase, "applicability") if supabase is not None else _FALLBACK_APPLICABILITY
    ex = (executor_text or "").strip()
    if not ex:
        return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW
    for r in rules:
        if _match(r, ex):
            return (r["class_label"] or APPLY_AMBIGUOUS), (DECISION_KEEP if r["verdict"] == "KEEP" else DECISION_DROP)
    return APPLY_AMBIGUOUS, DECISION_KEEP_REVIEW
