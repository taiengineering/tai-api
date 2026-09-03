"""services/paid_result_public_projection_svc.py — public-safe premium_result_v1

WO-PAID-DIAGNOSIS-STEP8A-BACKEND-PROJECTION-001

WHAT THIS IS
    이미 조립된 내부 Product(_paid_product) 를 HTTP 에 실을 public-safe
    projection 으로 옮기는 순수 계층. 입력은 assembler 1회 결과 재사용.

        build_paid_result_product_v1(row)  --(이미 1회)--
                    |
                    v
        build_public_premium_result_v1(product)  -> data.premium_result_v1

    DB read 0 · LEG call 0 · assembler 재호출 0.
    값 합성 / 재판정 / 재집계 / 매칭 / 정렬변경 / dedupe = 0.
    허용 연산 = allowlist pick · 키 rename · COUNT(이미 만든 배열의 len) ·
                F13 trigger 화이트리스트 필터.

PUBLIC SHAPE
    version / contract_version / diagnosis / profile / materials /
    evidence.articles / canonical_sources
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECTION_VERSION = 1

PROFILE_PUBLIC_FIELDS: Tuple[str, ...] = (
    "profile_version",
    "company_name",
    "sector",
    "workers",
    "floor_area",
    "contract_amount_eok",
    "construction_type",
    "building_use_type",
    "address",
    "has_excavation",
    "has_hazardous_material",
)

OVERVIEW_PUBLIC_FIELDS: Tuple[str, ...] = (
    "total_obligation_count",
    "distinct_law_count",
    "unspecified_law_obligation_count",
    "obligation_type_counts",
    "content_type_counts",
)

LAW_PORTFOLIO_FIELDS: Tuple[str, ...] = (
    "law_name",
    "obligation_count",
    "article_count",
    "unspecified_article_obligation_count",
)

ACTOR_FIELDS: Tuple[str, ...] = ("actor", "count")
ARTICLE_BUNDLE_FIELDS: Tuple[str, ...] = ("law_name", "law_article", "count")
TIMING_PUBLIC_KEYS: Tuple[str, ...] = (
    "CONTINUOUS", "PERIODIC", "BEFORE_EVENT", "AFTER_EVENT",
)
DUTY_VS_BUCKETS: Tuple[str, ...] = ("OBLIGATION", "PROHIBITION", "UNKNOWN")

OBLIGATION_LEGAL_FIELDS: Tuple[str, ...] = ("law_name", "law_article", "evidence")
OBLIGATION_CLASS_FIELDS: Tuple[str, ...] = ("content_type", "obligation_type")
OBLIGATION_DUTY_FIELDS: Tuple[str, ...] = ("who", "recipient", "where", "how")
OBLIGATION_TIMING_FIELDS: Tuple[str, ...] = (
    "when", "inspection_cycle", "raw_cycle", "conflict",
)
EVIDENCE_ARTICLE_FIELDS: Tuple[str, ...] = (
    "article_no", "article_sub_no", "article_title", "article_text", "law_name",
)

#: D01 finding_id -> public facts allowlist (STEP8A REV-1 presentation 계약).
#: F03/F08/F09 중첩 배열은 FINDING_NESTED_ALLOWLIST 로 재투영한다 (raw pass-through 금지).
FINDING_FACTS_ALLOWLIST: Dict[str, Tuple[str, ...]] = {
    "F01": ("obligation_count", "law_count"),
    "F02": ("law_count", "article_count"),
    "F03": ("max_obligation_count", "actors"),
    "F04": ("actor_count",),
    "F05": ("prohibition_count",),
    "F06": ("inspection_count",),
    "F07": ("notification_count",),
    "F08": ("obligation_count", "laws"),
    "F09": ("obligation_count", "articles"),
    "F10": ("timing_obligation_count",),
    "F11": ("condition_obligation_count",),
    "F12": ("recipient_obligation_count",),
    "F13": ("triggers",),
    "F14": ("obligation_gap_count",),
}

#: F03/F08/F09 nested 배열 → 새 dict 재투영. 미지정 키(count 등) drop.
FINDING_NESTED_ALLOWLIST: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "F03": {"actors": ("actor",)},
    "F08": {"laws": ("law_name",)},
    "F09": {"articles": ("law_name", "law_article")},
}

#: F13 public triggers. presentation frozen 8키 EXACT. 새 trigger 어휘 생성 0.
F13_TRIGGER_WHITELIST: Tuple[str, ...] = (
    "worker_count",
    "total_floor_area",
    "contract_amount_eok",
    "sector",
    "construction_type",
    "building_use_type",
    "has_excavation",
    "has_hazardous_material",
)
_F13_TRIGGER_SET = frozenset(F13_TRIGGER_WHITELIST)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _only(src: Any, fields: Sequence[str]) -> Dict[str, Any]:
    row = _as_dict(src)
    return {key: row.get(key) for key in fields}


def _map_only(rows: Any, fields: Sequence[str]) -> List[Dict[str, Any]]:
    return [_only(row, fields) for row in _as_list(rows) if isinstance(row, dict)]


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _project_profile(product: Dict[str, Any]) -> Dict[str, Any]:
    return _only(product.get("diagnosis_profile"), PROFILE_PUBLIC_FIELDS)


def _project_diagnosis(product: Dict[str, Any]) -> Dict[str, Any]:
    return {"diagnosed_at": _as_dict(product.get("diagnosis")).get("diagnosed_at")}


def _project_duty_vs_prohibition(src: Any) -> Dict[str, Any]:
    buckets = _as_dict(src)
    return {
        name: {"count": _as_dict(buckets.get(name)).get("count")}
        for name in DUTY_VS_BUCKETS
    }


def _project_information_gaps(src: Any) -> Dict[str, Any]:
    gaps = _as_dict(src)
    input_gaps = _as_dict(gaps.get("diagnosis_input_gaps"))
    obl_gaps = _as_dict(gaps.get("obligation_information_gaps"))
    return {
        "diagnosis_input_gaps": {
            "missing_count": _count_list(input_gaps.get("missing_fields")),
            "unknown_count": _count_list(input_gaps.get("unknown_fields")),
            "invalid_count": _count_list(input_gaps.get("invalid_fields")),
        },
        "obligation_information_gaps": {
            "field_count": _count_list(obl_gaps.get("fields")),
            "obligation_count_with_gaps": obl_gaps.get("obligation_count_with_gaps"),
        },
    }


def _project_coverage(src: Any) -> Dict[str, Any]:
    eval_cov = _as_dict(_as_dict(src).get("obligation_evaluation_coverage"))
    return {
        "obligation_evaluation_coverage": {
            "total": eval_cov.get("total"),
            "evaluable_count": eval_cov.get("evaluable_count"),
            "not_evaluable_count": eval_cov.get("not_evaluable_count"),
            "unknown_count": eval_cov.get("unknown_count"),
        }
    }


def _project_timing_counts(src: Any) -> Dict[str, Any]:
    counts = _as_dict(_as_dict(src).get("counts"))
    return {"counts": {key: counts.get(key) for key in TIMING_PUBLIC_KEYS}}


def _project_f13_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    raw = facts.get("triggers")
    triggers = [
        item for item in _as_list(raw)
        if isinstance(item, str) and item in _F13_TRIGGER_SET
    ]
    return {"triggers": triggers}


def _project_finding_facts(finding_id: Any, raw_facts: Dict[str, Any]) -> Dict[str, Any]:
    allow = FINDING_FACTS_ALLOWLIST.get(finding_id)
    if allow is None:
        return {}
    if finding_id == "F13":
        return _project_f13_facts(raw_facts)
    nested = FINDING_NESTED_ALLOWLIST.get(finding_id) or {}
    facts: Dict[str, Any] = {}
    for key in allow:
        if key in nested:
            facts[key] = _map_only(raw_facts.get(key), nested[key])
        else:
            facts[key] = raw_facts.get(key)
    return facts


def _project_findings(src: Any) -> Dict[str, Any]:
    findings_out: List[Dict[str, Any]] = []
    for finding in _as_list(_as_dict(src).get("findings")):
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("finding_id")
        findings_out.append({
            "id": finding_id,
            "type": finding.get("finding_type"),
            "eligible": finding.get("eligible"),
            "facts": _project_finding_facts(finding_id, _as_dict(finding.get("facts"))),
        })
    return {"findings": findings_out}


def _project_obligation(ob: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(ob, dict):
        return None
    identity = _as_dict(ob.get("identity"))
    applicability = _as_dict(ob.get("applicability"))
    verification = _as_dict(ob.get("verification"))
    triggered = applicability.get("triggered_by")
    return {
        "ref": identity.get("source_index"),
        "legal": _only(ob.get("legal"), OBLIGATION_LEGAL_FIELDS),
        "classification": _only(ob.get("classification"), OBLIGATION_CLASS_FIELDS),
        "duty": _only(ob.get("duty"), OBLIGATION_DUTY_FIELDS),
        "applicability": {"condition": applicability.get("condition")},
        "verification": {"check_result": verification.get("check_result")},
        "timing": _only(ob.get("timing"), OBLIGATION_TIMING_FIELDS),
        "decision_input_count": _count_list(triggered),
    }


def _project_materials(product: Dict[str, Any]) -> Dict[str, Any]:
    materials = _as_dict(product.get("paid_result_materials_v1"))
    meta = _as_dict(materials.get("meta"))
    return {
        "meta": {"material_version": meta.get("material_version")},
        "overview": _only(materials.get("overview"), OVERVIEW_PUBLIC_FIELDS),
        "duty_vs_prohibition": _project_duty_vs_prohibition(
            materials.get("duty_vs_prohibition")
        ),
        "compliance_profile": {
            "periodic_count": _as_dict(materials.get("compliance_profile")).get(
                "periodic_count"
            ),
        },
        "law_portfolio": _map_only(materials.get("law_portfolio"), LAW_PORTFOLIO_FIELDS),
        "legal_actor_map": _map_only(materials.get("legal_actor_map"), ACTOR_FIELDS),
        "article_bundles": _map_only(
            materials.get("article_bundles"), ARTICLE_BUNDLE_FIELDS
        ),
        "timing_character_summary": _project_timing_counts(
            materials.get("timing_character_summary")
        ),
        "information_gaps": _project_information_gaps(materials.get("information_gaps")),
        "coverage_summary": _project_coverage(materials.get("coverage_summary")),
        "diagnosis_findings": _project_findings(materials.get("diagnosis_findings")),
        "obligations": [
            projected
            for projected in (
                _project_obligation(ob)
                for ob in _as_list(materials.get("normalized_obligations"))
            )
            if projected is not None
        ],
    }


def _project_evidence(product: Dict[str, Any]) -> Dict[str, Any]:
    articles_out: List[Dict[str, Any]] = []
    for row in _as_list(_as_dict(product.get("paid_result_evidence_v1")).get("articles")):
        if not isinstance(row, dict):
            continue
        item = _only(row, EVIDENCE_ARTICLE_FIELDS)
        item["related_refs"] = list(row.get("related_obligation_refs") or [])
        articles_out.append(item)
    return {"articles": articles_out}


def _project_canonical_sources(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    """§9 EXACT + non-empty text 만. 동일 ref 2건이면 둘 다(backend dedupe 0)."""
    sidecar = _as_dict(product.get("paid_result_source_text_v1"))
    out: List[Dict[str, Any]] = []
    for item in _as_list(sidecar.get("items")):
        if not isinstance(item, dict):
            continue
        if item.get("resolution_status") != "EXACT":
            continue
        text = item.get("text")
        if not (isinstance(text, str) and text):
            continue
        out.append({"ref": item.get("obligation_ref"), "text": text})
    return out


def build_public_premium_result_v1(product: Any) -> Dict[str, Any]:
    """내부 Product -> public-safe premium_result_v1. 입력 mutation 0."""
    src = _as_dict(product)
    return {
        "version": PROJECTION_VERSION,
        "contract_version": src.get("contract_version"),
        "diagnosis": _project_diagnosis(src),
        "profile": _project_profile(src),
        "materials": _project_materials(src),
        "evidence": _project_evidence(src),
        "canonical_sources": _project_canonical_sources(src),
    }


__all__ = [
    "PROJECTION_VERSION",
    "PROFILE_PUBLIC_FIELDS",
    "FINDING_FACTS_ALLOWLIST",
    "FINDING_NESTED_ALLOWLIST",
    "F13_TRIGGER_WHITELIST",
    "build_public_premium_result_v1",
]
