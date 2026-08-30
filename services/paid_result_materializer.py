"""services/paid_result_materializer.py — PAID RESULT MATERIALIZER v1 (STEP3A).

DESIGN BASELINE
    tai-www docs/2026-08-30_PAID_DIAGNOSIS_RESULT_DERIVATION_DESIGN_V1.md
    (PAID-DIAGNOSIS-VALUE-REBUILD-01 / STEP 2-DOC)

WHAT THIS IS
    저장된 진단 결과(RAW)에서 고객가치 재료(Product Material)를 만드는 순수 계층.

        RAW(full_result) -> NORMALIZED -> DERIVED MATERIALS(R01~R16) -> PRODUCT MATERIAL

    Web / PDF / Excel 은 이 산출물(paid_result_materials_v1)을 공통 소비한다.
    각 표면이 법령엔진 결과를 독립적으로 재해석하지 않게 하는 것이 이 모듈의 목적이다.

SOURCE-OF-TRUTH BOUNDARY
    입력은 `public.anonymous_diagnosis_results.row.full_result` 하나다.
    다른 엔진 endpoint / LEG 직접 response / legacy rules_table / sample data /
    historical row shape / 격리·테스트 자산을 읽거나 조합하지 않는다.
    DB 접근은 이 모듈 밖(DB Reader)의 책임이다.

        DB Reader -> full_result -> Materializer

PURITY CONTRACT
    - DB / HTTP / filesystem / datetime.now() / random / env / LLM / external API = 0
    - 입력 mutation = 0 (진입 시 deepcopy 후 읽기만 한다)
    - 같은 입력이면 항상 같은 출력 (모든 정렬은 deterministic)

FORBIDDEN DERIVATION (설계문서 §11)
    위험도 점수 / 법적 위험 % / HIGH·MEDIUM·LOW 임의 생성 / 과태료 합산 /
    예상 최대 과태료 / 근거 없는 우선순위 / 즉시 7일 / 단기 30일 /
    근거 없는 법적 기한 / 없는 자격요건·서식·제출기관·보관기간·처벌 생성 /
    LLM 을 통한 법적 사실 보충 / 의미유사성 기반 의무 병합
    -> 이 모듈에는 위 로직이 존재하지 않는다.

PUBLIC ENTRYPOINT
    build_paid_result_materials_v1(full_result: dict) -> dict
"""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# 버전 상수
# ─────────────────────────────────────────────────────────────────────────────

MATERIAL_VERSION = 1
NORMALIZER_VERSION = 1

DERIVATION_VERSIONS: Dict[str, str] = {
    "R01": "R01_V1", "R02": "R02_V1", "R03": "R03_V1", "R04": "R04_V1",
    "R05": "R05_V1", "R06": "R06_V1", "R07": "R07_V1", "R08": "R08_V1",
    "R09": "R09_V1", "R10": "R10_V1", "R11": "R11_V1", "R12": "R12_V1",
    "R13": "R13_V1", "R14": "R14_V1", "R15": "R15_V1", "R16": "R16_V1",
}

# availability enum (설계문서 §5)
AVAILABLE = "AVAILABLE"
NULL = "NULL"
UNSUPPORTED = "UNSUPPORTED"

# 이번 결과 계약이 제공하지 않는 값. "없음"을 만들어 채우지 않고 UNSUPPORTED 로 표기한다.
# 값을 생성하지 않는다 — 이름과 상태만 선언한다(설계문서 §5).
UNSUPPORTED_FIELDS: Tuple[str, ...] = (
    "qualification",
    "form_name",
    "form_url",
    "report_method_std",
    "online_system",
    "system_url",
    "submit_org",
    "retention_period",
    "penalty",
    "due_days",
    "deadline",
    "risk_level",
)

UNCLASSIFIED = "UNCLASSIFIED"
UNKNOWN = "UNKNOWN"
UNSPECIFIED = "UNSPECIFIED"

BUCKET_OBLIGATION = "OBLIGATION"
BUCKET_PROHIBITION = "PROHIBITION"
BUCKET_UNKNOWN = UNKNOWN

# R11 — deterministic mapping table. 표에 없는 표현은 예외 없이 UNKNOWN.
# substring heuristic(contains "3" / "6" 등) 금지.
TIMING_CHARACTER_MAP: Dict[str, str] = {
    "상시": "CONTINUOUS",
    "매월": "PERIODIC",
    "매년": "PERIODIC",
    "6개월마다": "PERIODIC",
    "작업 전": "BEFORE_EVENT",
    "작업 후": "AFTER_EVENT",
}
TIMING_CHARACTER_UNKNOWN = UNKNOWN

# R12 fingerprint 구성 필드 (설계문서 §R12)
DUPLICATE_FINGERPRINT_FIELDS: Tuple[str, ...] = (
    "law_name",
    "law_article",
    "content_type",
    "obligation_type",
    "what",
    "condition",
    "who",
    "recipient",
    "evidence",
)

_WS_RE = re.compile(r"\s+")


# ─────────────────────────────────────────────────────────────────────────────
# 순수 유틸 — 값을 만들지 않는다. 정리(trim/whitespace)만 한다.
# ─────────────────────────────────────────────────────────────────────────────

def _text(value: Any) -> Any:
    """문자열이면 trim 후 빈 문자열은 None. 문자열이 아니면 원본 보존(값 변환 없음)."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value if value is not None else None


def _listify(value: Any) -> List[Any]:
    """리스트 필드 정규화. 값을 만들지 않는다(없으면 빈 리스트)."""
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None:
        return []
    return [value]


def _bool_or_none(value: Any) -> Optional[bool]:
    """bool 만 bool 로 인정. 그 외는 None(추론하지 않는다)."""
    return value if isinstance(value, bool) else None


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_ws(value: Any) -> Optional[str]:
    """fingerprint / mapping 용 정규화 — Unicode NFKC + trim + 연속 공백 정리."""
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized if normalized else None


def _sort_key(value: Any) -> Tuple[int, str]:
    """None 을 항상 마지막에 두는 deterministic 정렬 키."""
    if value is None:
        return (1, "")
    return (0, value if isinstance(value, str) else repr(value))


def _availability_of(value: Any) -> str:
    if value is None:
        return NULL
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return NULL
    return AVAILABLE


def _counts(values: List[Any], fallback: str) -> Dict[str, int]:
    """exact count. 값이 없으면 fallback 버킷. 합계는 항상 len(values)."""
    out: Dict[str, int] = {}
    for value in values:
        key = value if isinstance(value, str) and value else fallback
        if not isinstance(key, str):
            key = fallback
        out[key] = out.get(key, 0) + 1
    return {k: out[k] for k in sorted(out)}


def _stable_json_key(value: Any) -> str:
    """dict/list 를 exact distinct 하기 위한 deterministic 직렬화 키."""
    if isinstance(value, dict):
        return "{" + ",".join(
            "{}:{}".format(repr(k), _stable_json_key(value[k])) for k in sorted(value, key=repr)
        ) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_json_key(v) for v in value) + "]"
    return repr(value)


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1 — NORMALIZER
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_timing(detail_when: Any, enrichment_cycle: Any) -> Dict[str, Any]:
    """설계문서 §7 — when 과 inspection_cycle 의 관계를 손실 없이 정규화한다.

    A 둘 다 없음        -> raw_cycle=None, conflict=False
    B 한쪽만 있음        -> raw_cycle=그 값,  conflict=False
    C 둘 다 있고 동일     -> raw_cycle=그 값,  conflict=False
    D 둘 다 있고 다름     -> raw_cycle=None,  conflict=True  (원본 두 값 모두 보존)

    조용히 한 값을 선택하지 않는다.
    """
    when = _text(detail_when)
    cycle = _text(enrichment_cycle)

    if when is None and cycle is None:
        raw_cycle, conflict = None, False
    elif when is not None and cycle is None:
        raw_cycle, conflict = when, False
    elif when is None and cycle is not None:
        raw_cycle, conflict = cycle, False
    elif _normalize_ws(when) == _normalize_ws(cycle):
        raw_cycle, conflict = when, False
    else:
        raw_cycle, conflict = None, True

    return {
        "raw_cycle": raw_cycle,
        "when": when,
        "inspection_cycle": cycle,
        "conflict": conflict,
        "timing_character": _timing_character(raw_cycle),
    }


def _timing_character(raw_cycle: Any) -> str:
    """R11 — 명시 표현만 deterministic mapping. 그 외 전부 UNKNOWN."""
    key = _normalize_ws(raw_cycle)
    if key is None:
        return TIMING_CHARACTER_UNKNOWN
    return TIMING_CHARACTER_MAP.get(key, TIMING_CHARACTER_UNKNOWN)


def _normalize_obligation(raw: Dict[str, Any], source_index: int) -> Dict[str, Any]:
    """RAW obligation 1건 -> NormalizedObligation.

    이름과 위치만 정리한다. 값 추론·보충·합성 없음. 없으면 None.
    (설계문서 §4 · WORK ORDER §6 mapping)
    """
    enrichment = _dict_or_empty(raw.get("enrichment"))
    detail = _dict_or_empty(raw.get("obligation_detail"))

    identity = {
        "source_index": source_index,
        "atom_id": _text(raw.get("atom_id")),
        "source_atom_ids": _listify(raw.get("source_atom_ids")),
    }
    legal = {
        "law_name": _text(raw.get("law_name")),
        "law_article": _text(raw.get("law_article")),
        "evidence": _text(raw.get("evidence")),
    }
    classification = {
        "obligation_type": _text(enrichment.get("obligation_type")),
        "content_type": _text(enrichment.get("content_type")),
    }
    duty = {
        "what": _text(detail.get("what")),
        "who": _text(detail.get("who")),
        "when": _text(detail.get("when")),
        "recipient": _text(detail.get("recipient")),
        "where": _text(detail.get("where")),
        "how": _text(detail.get("how")),
    }
    applicability = {
        "condition": _text(detail.get("condition")),
        "triggered_by": _listify(raw.get("triggered_by")),
        "consumer_status": _text(enrichment.get("consumer_status")),
    }
    verification = {
        "check_result": _text(raw.get("check_result")),
        "usable_for_evaluation": _bool_or_none(enrichment.get("usable_for_evaluation")),
        "completeness": _text(enrichment.get("completeness")),
        "missing_fields": _listify(enrichment.get("missing_fields")),
    }
    timing = _normalize_timing(detail.get("when"), enrichment.get("inspection_cycle"))

    normalized = {
        "identity": identity,
        "legal": legal,
        "classification": classification,
        "duty": duty,
        "applicability": applicability,
        "verification": verification,
        "timing": timing,
    }
    normalized["availability"] = _obligation_availability(normalized)
    return normalized


def _obligation_availability(normalized: Dict[str, Any]) -> Dict[str, str]:
    """AVAILABLE / NULL 을 필드 단위로 표기. UNSUPPORTED 는 meta.unsupported_fields 참조.

    NULL(이 의무에 값이 없음)과 UNSUPPORTED(시스템이 제공하지 않음)를 같게 취급하지 않는다.
    """
    out: Dict[str, str] = {}
    for group in ("legal", "classification", "duty", "applicability", "verification"):
        for field, value in normalized[group].items():
            out["{}.{}".format(group, field)] = _availability_of(value)
    out["timing.raw_cycle"] = _availability_of(normalized["timing"]["raw_cycle"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 2 — DERIVED MATERIALS (R01 ~ R16)
# 허용 연산: COUNT / DISTINCT / GROUP BY / SORT / EXACT MATCH /
#            SET UNION / SET DIFFERENCE / FIELD PRESENCE / NULL CHECK /
#            BOOLEAN COMBINATION / DETERMINISTIC LABEL MAPPING
# ─────────────────────────────────────────────────────────────────────────────

def _ref(obligation: Dict[str, Any]) -> int:
    return obligation["identity"]["source_index"]


def _law_key(obligation: Dict[str, Any]) -> str:
    return obligation["legal"]["law_name"] or UNSPECIFIED


def _article_key(obligation: Dict[str, Any]) -> str:
    return obligation["legal"]["law_article"] or UNSPECIFIED


def _r02_law_portfolio(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R02 — 법령별 의무 부담 분포. GROUP KEY = law_name exact."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for ob in obligations:
        groups.setdefault(_law_key(ob), []).append(ob)

    rows: List[Dict[str, Any]] = []
    for law_name, members in groups.items():
        rows.append({
            "law_name": law_name,
            "obligation_count": len(members),
            "article_count": len({_article_key(m) for m in members}),
            "obligation_type_counts": _counts(
                [m["classification"]["obligation_type"] for m in members], UNCLASSIFIED),
            "content_type_counts": _counts(
                [m["classification"]["content_type"] for m in members], UNKNOWN),
            "verification_counts": _counts(
                [m["verification"]["check_result"] for m in members], UNKNOWN),
            "obligation_refs": sorted(_ref(m) for m in members),
        })
    rows.sort(key=lambda r: (-r["obligation_count"], r["law_name"]))
    return rows


def _r01_overview(obligations: List[Dict[str, Any]],
                  law_portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R01 — 전체 의무 구조의 규모와 구성.

    unknown obligation_type -> UNCLASSIFIED (ACTION 등으로 강제 편입하지 않는다)
    unknown content_type    -> UNKNOWN
    unknown verification    -> UNKNOWN
    각 counts 의 합계는 항상 total_obligation_count 와 같다.
    """
    return {
        "total_obligation_count": len(obligations),
        "distinct_law_count": len(law_portfolio),
        "obligation_type_counts": _counts(
            [o["classification"]["obligation_type"] for o in obligations], UNCLASSIFIED),
        "content_type_counts": _counts(
            [o["classification"]["content_type"] for o in obligations], UNKNOWN),
        "verification_counts": _counts(
            [o["verification"]["check_result"] for o in obligations], UNKNOWN),
    }


def _r03_duty_vs_prohibition(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R03 — 해야 할 것 / 하면 안 되는 것. SOURCE = content_type ONLY.

    PROHIBITION -> ACTION 변환 금지. 다른 필드로 추정하지 않는다.
    """
    buckets: Dict[str, List[int]] = {
        BUCKET_OBLIGATION: [], BUCKET_PROHIBITION: [], BUCKET_UNKNOWN: [],
    }
    for ob in obligations:
        content_type = ob["classification"]["content_type"]
        if content_type == BUCKET_OBLIGATION:
            bucket = BUCKET_OBLIGATION
        elif content_type == BUCKET_PROHIBITION:
            bucket = BUCKET_PROHIBITION
        else:
            bucket = BUCKET_UNKNOWN
        buckets[bucket].append(_ref(ob))

    return {
        name: {"count": len(refs), "obligation_refs": sorted(refs)}
        for name, refs in buckets.items()
    }


def _r04_applicability_basis(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R04 — 왜 이 의무가 적용됐는가.

    decision_inputs 는 RAW key 를 그대로 보존한다(코드->한국어 변환은 presentation 단계).
    triggered_by 를 법적 충분조건으로 과장하지 않는다 — 의미는 '판정에 사용된 사업장 정보'.
    """
    rows: List[Dict[str, Any]] = []
    for ob in obligations:
        applicability = ob["applicability"]
        rows.append({
            "obligation_ref": _ref(ob),
            "legal_condition": applicability["condition"],
            "decision_inputs": list(applicability["triggered_by"]),
            "status": applicability["consumer_status"],
            "availability": {
                "legal_condition": _availability_of(applicability["condition"]),
                "decision_inputs": _availability_of(applicability["triggered_by"]),
                "status": _availability_of(applicability["consumer_status"]),
            },
        })
    return rows


def _r05_legal_basis_bundles(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R05 — 조문 단위 법적 근거 묶음. 의무를 합치지 않고 연결만 한다.

    evidence 는 exact distinct. 요약·재작성 금지.
    """
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for ob in obligations:
        groups.setdefault((_law_key(ob), _article_key(ob)), []).append(ob)

    rows: List[Dict[str, Any]] = []
    for (law_name, law_article), members in groups.items():
        seen: List[str] = []
        evidence: List[str] = []
        for member in members:
            value = member["legal"]["evidence"]
            if value is None:
                continue
            key = _stable_json_key(value)
            if key not in seen:
                seen.append(key)
                evidence.append(value)
        rows.append({
            "law_name": law_name,
            "law_article": law_article,
            "evidence": sorted(evidence, key=_sort_key),
            "related_obligation_refs": sorted(_ref(m) for m in members),
        })
    rows.sort(key=lambda r: (r["law_name"], r["law_article"]))
    return rows


def _r06_verification_summary(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R06 — 판정 상태 요약. 원본 상태명 유지.

    신뢰도 % / 정확도 점수 / PASS score 생성 금지.
    """
    return {
        "total": len(obligations),
        "counts": _counts([o["verification"]["check_result"] for o in obligations], UNKNOWN),
    }


def _r07_information_gaps(contract: Dict[str, Any],
                          obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R07 — 추가로 확인해야 할 것.

    A(diagnosis_input_gaps)와 B(obligation_information_gaps)는 의미가 다르므로 절대 합치지 않는다.
    A 는 고객이 채울 수 있고, B 는 고객이 채울 수 없다. 총합 하나를 만들지 않는다.
    """
    has_contract = bool(contract)

    def _distinct(values: List[Any]) -> List[Any]:
        seen: List[str] = []
        out: List[Any] = []
        for value in values:
            key = _stable_json_key(value)
            if key not in seen:
                seen.append(key)
                out.append(value)
        return out

    missing = _distinct(_listify(contract.get("missing_fields")))
    unknown = _distinct(_listify(contract.get("unknown_fields")))
    invalid = _distinct(_listify(contract.get("invalid_fields")))

    diagnosis_input_gaps = {
        "source": "full_result.contract",
        "availability": AVAILABLE if has_contract else NULL,
        "missing_fields": sorted(missing, key=_sort_key) if missing else [],
        "unknown_fields": sorted(unknown, key=_sort_key) if unknown else [],
        "invalid_fields": sorted(invalid, key=_stable_json_key) if invalid else [],
    }

    field_refs: Dict[str, List[int]] = {}
    obligations_with_gaps: List[int] = []
    for ob in obligations:
        fields = ob["verification"]["missing_fields"]
        if not fields:
            continue
        obligations_with_gaps.append(_ref(ob))
        for field in fields:
            key = field if isinstance(field, str) else _stable_json_key(field)
            field_refs.setdefault(key, []).append(_ref(ob))

    obligation_information_gaps = {
        "source": "obligations_raw[].enrichment.missing_fields",
        "availability": AVAILABLE if field_refs else NULL,
        "fields": [
            {"field": field, "count": len(refs), "obligation_refs": sorted(refs)}
            for field, refs in sorted(field_refs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "obligation_count_with_gaps": len(obligations_with_gaps),
        "obligation_refs": sorted(obligations_with_gaps),
    }

    return {
        "diagnosis_input_gaps": diagnosis_input_gaps,
        "obligation_information_gaps": obligation_information_gaps,
    }


def _group_map(obligations: List[Dict[str, Any]], group: str, field: str,
               label: str) -> List[Dict[str, Any]]:
    """R08 / R09 공통 — exact group. 빈 값은 UNKNOWN. 추론하지 않는다."""
    groups: Dict[str, List[int]] = {}
    for ob in obligations:
        key = ob[group][field] or UNKNOWN
        if not isinstance(key, str):
            key = UNKNOWN
        groups.setdefault(key, []).append(_ref(ob))

    rows = [
        {label: key, "count": len(refs), "obligation_refs": sorted(refs)}
        for key, refs in groups.items()
    ]
    rows.sort(key=lambda r: (-r["count"], r[label]))
    return rows


def _r08_legal_actor_map(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R08 — 법령상 수행/책임 주체별 의무. '실제 담당자'가 아니다. 담당자 추론 금지."""
    return _group_map(obligations, "duty", "who", "actor")


def _r09_recipient_map(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R09 — 의무의 대상/상대방별 의무. '제출기관'으로 rename 하지 않는다."""
    return _group_map(obligations, "duty", "recipient", "recipient")


def _r10_legal_timing_profile(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R10 — 법적 시점/주기 원문. RAW value 보존. 실제 날짜 생성 금지."""
    with_timing: List[int] = []
    without_timing: List[int] = []
    conflicts: List[int] = []
    cycle_refs: Dict[str, List[int]] = {}

    for ob in obligations:
        timing = ob["timing"]
        if timing["conflict"]:
            conflicts.append(_ref(ob))
        raw_cycle = timing["raw_cycle"]
        if raw_cycle is None:
            without_timing.append(_ref(ob))
        else:
            with_timing.append(_ref(ob))
            cycle_refs.setdefault(raw_cycle, []).append(_ref(ob))

    return {
        "with_timing_count": len(with_timing),
        "without_timing_count": len(without_timing),
        "conflict_count": len(conflicts),
        "conflict_obligation_refs": sorted(conflicts),
        "distinct_raw_cycles": [
            {"value": value, "count": len(refs), "obligation_refs": sorted(refs)}
            for value, refs in sorted(cycle_refs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
    }


def _r11_timing_character_summary(obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R11 — 시점 성격 분류 요약. 명시 표현만 mapping, 그 외 UNKNOWN."""
    groups: Dict[str, List[int]] = {}
    for ob in obligations:
        groups.setdefault(ob["timing"]["timing_character"], []).append(_ref(ob))
    return {
        "counts": {key: len(groups[key]) for key in sorted(groups)},
        "obligation_refs": {key: sorted(groups[key]) for key in sorted(groups)},
        "mapping_table": dict(sorted(TIMING_CHARACTER_MAP.items())),
    }


def _fingerprint_fields(obligation: Dict[str, Any]) -> Dict[str, Optional[str]]:
    legal = obligation["legal"]
    classification = obligation["classification"]
    duty = obligation["duty"]
    applicability = obligation["applicability"]
    source = {
        "law_name": legal["law_name"],
        "law_article": legal["law_article"],
        "content_type": classification["content_type"],
        "obligation_type": classification["obligation_type"],
        "what": duty["what"],
        "condition": applicability["condition"],
        "who": duty["who"],
        "recipient": duty["recipient"],
        "evidence": legal["evidence"],
    }
    return {field: _normalize_ws(source[field]) for field in DUPLICATE_FINGERPRINT_FIELDS}


def _r12_duplicate_groups(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R12 — 엄격 동일(exact) 의무 그룹.

    normalize 는 Unicode NFKC + trim + 연속 whitespace 정리까지만.
    synonym / embedding / similarity / LLM 사용 금지.
    원본 obligation 을 삭제하지 않는다 — 표현만 group 한다.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for ob in obligations:
        fields = _fingerprint_fields(ob)
        payload = "\x1f".join(
            "" if fields[name] is None else fields[name] for name in DUPLICATE_FINGERPRINT_FIELDS
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        entry = groups.setdefault(digest, {"fields": fields, "refs": []})
        entry["refs"].append(_ref(ob))

    rows = [
        {
            "fingerprint": digest,
            "fingerprint_fields": entry["fields"],
            "count": len(entry["refs"]),
            "obligation_refs": sorted(entry["refs"]),
        }
        for digest, entry in groups.items()
        if len(entry["refs"]) >= 2
    ]
    rows.sort(key=lambda r: (r["obligation_refs"][0], r["fingerprint"]))
    return rows


def _r13_article_bundles(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R13 — 조문 단위 의무 묶음. 의무 합성 금지, 독립성 유지."""
    groups: Dict[Tuple[str, str], List[int]] = {}
    for ob in obligations:
        groups.setdefault((_law_key(ob), _article_key(ob)), []).append(_ref(ob))

    rows = [
        {
            "law_name": law_name,
            "law_article": law_article,
            "count": len(refs),
            "obligation_refs": sorted(refs),
        }
        for (law_name, law_article), refs in groups.items()
    ]
    rows.sort(key=lambda r: (r["law_name"], r["law_article"]))
    return rows


def _r14_compliance_profile(overview: Dict[str, Any],
                            duty_vs_prohibition: Dict[str, Any],
                            timing_character_summary: Dict[str, Any],
                            verification_summary: Dict[str, Any]) -> Dict[str, Any]:
    """R14 — 사업장 법적 의무 구성. 다른 Material 의 숫자 사실만 조합한다.

    평가문·평가 label(위험/높음/심각) 생성 금지. 문장 생성 금지.
    """
    return {
        "total_obligations": overview["total_obligation_count"],
        "distinct_laws": overview["distinct_law_count"],
        "prohibition_count": duty_vs_prohibition[BUCKET_PROHIBITION]["count"],
        "periodic_count": timing_character_summary["counts"].get("PERIODIC", 0),
        "verified_count": verification_summary["counts"].get("VERIFIED", 0),
        "unknown_verification_count": verification_summary["counts"].get(UNKNOWN, 0),
    }


def _r15_coverage_summary(contract: Dict[str, Any],
                          obligations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """R15 — 진단 커버리지와 판정 커버리지. 두 축을 분리한다. 점수/백분율 없음."""
    has_contract = bool(contract)
    diagnosis_coverage = {
        "source": "full_result.contract",
        "availability": AVAILABLE if has_contract else NULL,
        "active_count": len(_listify(contract.get("active_fields"))),
        "missing_count": len(_listify(contract.get("missing_fields"))),
        "unknown_count": len(_listify(contract.get("unknown_fields"))),
        "invalid_count": len(_listify(contract.get("invalid_fields"))),
    }

    evaluable = 0
    not_evaluable = 0
    unknown = 0
    for ob in obligations:
        usable = ob["verification"]["usable_for_evaluation"]
        if usable is True:
            evaluable += 1
        elif usable is False:
            not_evaluable += 1
        else:
            unknown += 1

    obligation_evaluation_coverage = {
        "source": "obligations_raw[].enrichment.usable_for_evaluation",
        "total": len(obligations),
        "evaluable_count": evaluable,
        "not_evaluable_count": not_evaluable,
        "unknown_count": unknown,
    }

    return {
        "diagnosis_coverage": diagnosis_coverage,
        "obligation_evaluation_coverage": obligation_evaluation_coverage,
    }


def _r16_execution_seed(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """R16 — Excel 실행관리의 법적 고정영역 원재료.

    회사별 실제 값(담당자·기준일·예정일·완료여부·완료일·증빙위치·비고)은 포함하지 않는다.
    그 값들은 미래 Excel 의 USER INPUT 영역이다.
    """
    rows: List[Dict[str, Any]] = []
    for ob in obligations:
        rows.append({
            "obligation_ref": _ref(ob),
            "law_name": ob["legal"]["law_name"],
            "law_article": ob["legal"]["law_article"],
            "evidence": ob["legal"]["evidence"],
            "content_type": ob["classification"]["content_type"],
            "obligation_type": ob["classification"]["obligation_type"],
            "what": ob["duty"]["what"],
            "who": ob["duty"]["who"],
            "recipient": ob["duty"]["recipient"],
            "condition": ob["applicability"]["condition"],
            "raw_cycle": ob["timing"]["raw_cycle"],
            "timing_character": ob["timing"]["timing_character"],
            "check_result": ob["verification"]["check_result"],
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# PROVENANCE — 모든 Material 은 출처를 역추적할 수 있어야 한다(설계문서 §13).
# 출력 최상단 shape 를 단순하게 유지하기 위해 meta.materials 레지스트리에 모은다.
# ─────────────────────────────────────────────────────────────────────────────

_MATERIAL_PROVENANCE: Dict[str, Dict[str, Any]] = {
    "normalized_obligations": {
        "material_type": "NORMALIZED_OBLIGATION",
        "derivation_rule": "NORMALIZER",
        "source_fields": [
            "obligations_raw[].atom_id", "obligations_raw[].source_atom_ids",
            "obligations_raw[].law_name", "obligations_raw[].law_article",
            "obligations_raw[].evidence", "obligations_raw[].triggered_by",
            "obligations_raw[].check_result",
            "obligations_raw[].obligation_detail.*", "obligations_raw[].enrichment.*",
        ],
    },
    "overview": {
        "material_type": "OBLIGATION_OVERVIEW", "derivation_rule": "R01",
        "source_fields": ["classification.obligation_type", "classification.content_type",
                          "verification.check_result", "legal.law_name"],
    },
    "law_portfolio": {
        "material_type": "LAW_PORTFOLIO", "derivation_rule": "R02",
        "source_fields": ["legal.law_name", "legal.law_article",
                          "classification.obligation_type", "classification.content_type",
                          "verification.check_result"],
    },
    "duty_vs_prohibition": {
        "material_type": "DUTY_VS_PROHIBITION", "derivation_rule": "R03",
        "source_fields": ["classification.content_type"],
    },
    "applicability_basis": {
        "material_type": "APPLICABILITY_BASIS", "derivation_rule": "R04",
        "source_fields": ["applicability.condition", "applicability.triggered_by",
                          "applicability.consumer_status"],
    },
    "legal_basis_bundles": {
        "material_type": "LEGAL_BASIS_BUNDLE", "derivation_rule": "R05",
        "source_fields": ["legal.law_name", "legal.law_article", "legal.evidence"],
    },
    "verification_summary": {
        "material_type": "VERIFICATION_SUMMARY", "derivation_rule": "R06",
        "source_fields": ["verification.check_result"],
    },
    "information_gaps": {
        "material_type": "INFORMATION_GAPS", "derivation_rule": "R07",
        "source_fields": ["full_result.contract.missing_fields",
                          "full_result.contract.unknown_fields",
                          "full_result.contract.invalid_fields",
                          "verification.missing_fields"],
    },
    "legal_actor_map": {
        "material_type": "LEGAL_ACTOR_MAP", "derivation_rule": "R08",
        "source_fields": ["duty.who"],
    },
    "recipient_map": {
        "material_type": "RECIPIENT_MAP", "derivation_rule": "R09",
        "source_fields": ["duty.recipient"],
    },
    "legal_timing_profile": {
        "material_type": "LEGAL_TIMING_PROFILE", "derivation_rule": "R10",
        "source_fields": ["timing.raw_cycle", "timing.when", "timing.inspection_cycle",
                          "timing.conflict"],
    },
    "timing_character_summary": {
        "material_type": "TIMING_CHARACTER", "derivation_rule": "R11",
        "source_fields": ["timing.raw_cycle"],
    },
    "duplicate_groups": {
        "material_type": "EXACT_DUPLICATE_GROUP", "derivation_rule": "R12",
        "source_fields": list(DUPLICATE_FINGERPRINT_FIELDS),
    },
    "article_bundles": {
        "material_type": "ARTICLE_OBLIGATION_BUNDLE", "derivation_rule": "R13",
        "source_fields": ["legal.law_name", "legal.law_article"],
    },
    "compliance_profile": {
        "material_type": "COMPLIANCE_PROFILE", "derivation_rule": "R14",
        "source_fields": ["overview", "duty_vs_prohibition", "timing_character_summary",
                          "verification_summary"],
    },
    "coverage_summary": {
        "material_type": "RESULT_COVERAGE_SUMMARY", "derivation_rule": "R15",
        "source_fields": ["full_result.contract.active_fields",
                          "full_result.contract.missing_fields",
                          "full_result.contract.unknown_fields",
                          "full_result.contract.invalid_fields",
                          "verification.usable_for_evaluation"],
    },
    "execution_seed": {
        "material_type": "EXECUTION_SEED", "derivation_rule": "R16",
        "source_fields": ["legal.*", "classification.*", "duty.what", "duty.who",
                          "duty.recipient", "applicability.condition", "timing.raw_cycle",
                          "timing.timing_character", "verification.check_result"],
    },
}

# obligation 단위 Material — source_obligation_refs 를 함께 싣는다.
_OBLIGATION_SCOPED = (
    "normalized_obligations", "applicability_basis", "execution_seed",
)


def _build_material_provenance(all_refs: List[int]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key in sorted(_MATERIAL_PROVENANCE):
        spec = _MATERIAL_PROVENANCE[key]
        rule = spec["derivation_rule"]
        entry: Dict[str, Any] = {
            "material_type": spec["material_type"],
            "material_version": MATERIAL_VERSION,
            "derivation_rule": DERIVATION_VERSIONS.get(rule, "NORMALIZER_V{}".format(NORMALIZER_VERSION)),
            "derivation_version": MATERIAL_VERSION,
            "source_fields": list(spec["source_fields"]),
        }
        if key in _OBLIGATION_SCOPED:
            entry["source_obligation_refs"] = list(all_refs)
        out[key] = entry
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

def build_paid_result_materials_v1(full_result: Any) -> Dict[str, Any]:
    """저장된 full_result(RAW) -> paid_result_materials_v1.

    PURE FUNCTION. 입력을 변경하지 않으며, 같은 입력이면 항상 같은 출력을 낸다.
    시간·난수·네트워크·DB·LLM 에 의존하지 않는다.
    """
    # LEVEL 0 — RAW 보존. 입력 mutation 0 을 구조적으로 보장한다.
    raw = copy.deepcopy(full_result) if isinstance(full_result, dict) else {}

    raw_obligations = [o for o in _listify(raw.get("obligations_raw")) if isinstance(o, dict)]
    contract = _dict_or_empty(raw.get("contract"))

    # LEVEL 1 — NORMALIZED
    obligations = [_normalize_obligation(o, i) for i, o in enumerate(raw_obligations)]
    all_refs = [_ref(o) for o in obligations]

    # LEVEL 2 — DERIVED MATERIALS
    law_portfolio = _r02_law_portfolio(obligations)
    overview = _r01_overview(obligations, law_portfolio)
    duty_vs_prohibition = _r03_duty_vs_prohibition(obligations)
    applicability_basis = _r04_applicability_basis(obligations)
    legal_basis_bundles = _r05_legal_basis_bundles(obligations)
    verification_summary = _r06_verification_summary(obligations)
    information_gaps = _r07_information_gaps(contract, obligations)
    legal_actor_map = _r08_legal_actor_map(obligations)
    recipient_map = _r09_recipient_map(obligations)
    legal_timing_profile = _r10_legal_timing_profile(obligations)
    timing_character_summary = _r11_timing_character_summary(obligations)
    duplicate_groups = _r12_duplicate_groups(obligations)
    article_bundles = _r13_article_bundles(obligations)
    compliance_profile = _r14_compliance_profile(
        overview, duty_vs_prohibition, timing_character_summary, verification_summary)
    coverage_summary = _r15_coverage_summary(contract, obligations)
    execution_seed = _r16_execution_seed(obligations)

    # LEVEL 3 — PRODUCT MATERIAL
    meta: Dict[str, Any] = {
        "material_version": MATERIAL_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "obligation_source": "full_result.obligations_raw",
        "unsupported_fields": list(UNSUPPORTED_FIELDS),
        "materials": _build_material_provenance(all_refs),
    }
    source_engine_version = _text(raw.get("engine_version"))
    if source_engine_version is not None:
        meta["source_engine_version"] = source_engine_version

    return {
        "meta": meta,
        "normalized_obligations": obligations,
        "overview": overview,
        "law_portfolio": law_portfolio,
        "duty_vs_prohibition": duty_vs_prohibition,
        "applicability_basis": applicability_basis,
        "legal_basis_bundles": legal_basis_bundles,
        "verification_summary": verification_summary,
        "information_gaps": information_gaps,
        "legal_actor_map": legal_actor_map,
        "recipient_map": recipient_map,
        "legal_timing_profile": legal_timing_profile,
        "timing_character_summary": timing_character_summary,
        "duplicate_groups": duplicate_groups,
        "article_bundles": article_bundles,
        "compliance_profile": compliance_profile,
        "coverage_summary": coverage_summary,
        "execution_seed": execution_seed,
    }


__all__ = ["build_paid_result_materials_v1"]
