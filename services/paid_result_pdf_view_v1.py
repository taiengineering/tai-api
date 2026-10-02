"""
services/paid_result_pdf_view_v1.py
WO-WP04-PDF-PREMIUM-CONTRACT-REPOINT-001

public premium_result_v1 → PDF Presentation ViewModel.

허용: field rename, section ordering, 값 존재 확인, display-only projection.
금지: COUNT/GROUP/DISTINCT 재계산, 법령 재판정, penalty/risk/deadline 생성,
      DB/network 접근, LLM, legal SoT 조회, full_result 접근.

PURE FUNCTION — 같은 입력 → 같은 출력. 현재시각 생성 0.

Legal Time — WP-03 EXACT 계약:
  legal_time_normalized.timing/cycle.source_text 우선.
  trim은 empty check에만 사용 — 반환값은 원본 string EXACT.
  presentation fallback 유지.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PDF_VIEW_VERSION = 1

_SECTOR_LABELS: Dict[str, str] = {
    "BUILDING":         "건물",
    "INDUSTRY":         "산업",
    "INDUSTRIAL":       "산업",
    "MANUFACTURING":    "산업(제조)",
    "CONSTRUCTION":     "건설",
    "SPECIAL_FACILITY": "특정시설",
}


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _text(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s if s else None


def _ltn_source_text(ltn: Any, key: str) -> Optional[str]:
    """legal_time_normalized.{key}.source_text — EXACT original (trim only for empty check)."""
    if not isinstance(ltn, dict):
        return None
    node = ltn.get(key)
    if not isinstance(node, dict):
        return None
    value = node.get("source_text")
    if not isinstance(value, str):
        return None
    if value.strip() == "":
        return None
    return value  # EXACT — do not strip


def _presentation_text(p: Any, field: str) -> Optional[str]:
    return _text(_as_dict(p).get(field))


def _ob_timing(ob: dict) -> Optional[str]:
    """WP-03: legal_time_normalized.timing.source_text 우선, presentation.timing fallback."""
    ltn = ob.get("legal_time_normalized")
    src = _ltn_source_text(ltn, "timing")
    return src if src is not None else _presentation_text(ob.get("presentation"), "timing")


def _ob_cycle(ob: dict) -> Optional[str]:
    """WP-03: legal_time_normalized.cycle.source_text 우선, presentation.cycle fallback."""
    ltn = ob.get("legal_time_normalized")
    src = _ltn_source_text(ltn, "cycle")
    return src if src is not None else _presentation_text(ob.get("presentation"), "cycle")


def _build_source_text_index(canonical_sources: List[Any]) -> Dict[Any, str]:
    """ref → EXACT canonical source text. 2건 이상이면 absent (fail-closed)."""
    by_ref: Dict[Any, str] = {}
    hits: Dict[Any, int] = {}
    for item in _as_list(canonical_sources):
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        t = item.get("text")
        if not (isinstance(t, str) and t):
            continue
        hits[ref] = hits.get(ref, 0) + 1
        by_ref[ref] = t
    for ref, n in hits.items():
        if n > 1:
            by_ref.pop(ref, None)
    return by_ref


def _build_obligation_rows(
    obligations: List[Any],
    source_index: Dict[Any, str],
) -> List[Dict[str, Any]]:
    rows = []
    for ob in _as_list(obligations):
        if not isinstance(ob, dict):
            continue
        ref = ob.get("ref")
        legal = _as_dict(ob.get("legal"))
        cls = _as_dict(ob.get("classification"))
        p = _as_dict(ob.get("presentation"))

        rows.append({
            "ref": ref,
            "law_name": _text(legal.get("law_name")),
            "law_article": _text(legal.get("law_article")),
            "obligation_type": _text(cls.get("obligation_type")),
            "title": _presentation_text(p, "action"),
            "actor": _presentation_text(p, "actor"),
            "timing": _ob_timing(ob),
            "cycle": _ob_cycle(ob),
            "condition": _presentation_text(p, "condition"),
            "how": _presentation_text(p, "how"),
            "where": _presentation_text(p, "where"),
            "source_text": source_index.get(ref),
        })
    return rows


def _bool_or_none(v: Any) -> Optional[bool]:
    """True→True, False→False, None/other→None. unknown ≠ false."""
    return v if isinstance(v, bool) else None


def _build_profile_view(profile: dict) -> Dict[str, Any]:
    sector_raw = (profile.get("sector") or "").strip().upper()
    sector_label = _SECTOR_LABELS.get(sector_raw) or _text(profile.get("sector"))
    return {
        "company_name": _text(profile.get("company_name")),
        "sector": sector_label,
        "workers": profile.get("workers"),
        "floor_area": profile.get("floor_area"),
        "contract_amount_eok": profile.get("contract_amount_eok"),
        "construction_type": _text(profile.get("construction_type")),
        "building_use_type": _text(profile.get("building_use_type")),
        "address": _text(profile.get("address")),
        "has_excavation": _bool_or_none(profile.get("has_excavation")),
        "has_hazardous_material": _bool_or_none(profile.get("has_hazardous_material")),
    }


def _build_evidence_rows(evidence: Any) -> List[Dict[str, Any]]:
    rows = []
    for article in _as_list(_as_dict(evidence).get("articles")):
        if not isinstance(article, dict):
            continue
        law_name = _text(article.get("law_name"))
        article_text = _text(article.get("article_text"))
        if law_name is None or article_text is None:
            continue
        rows.append({
            "law_name": law_name,
            "article_no": article.get("article_no"),
            "article_sub_no": article.get("article_sub_no"),
            "article_title": _text(article.get("article_title")),
            "article_text": article_text,
            "related_refs": _as_list(
                article.get("related_obligation_refs") or article.get("related_refs")
            ),
        })
    return rows


# ── 공개 진입점 ──────────────────────────────────────────────────────────────

def build_paid_result_pdf_view_v1(premium: Any) -> Dict[str, Any]:
    """public premium_result_v1 → PDF ViewModel.

    Pure function: DB/network 없음, 현재시각 없음, 법적 재판정 없음.
    숫자는 materials.overview 값 그대로 — 재계산 0.
    Legal Time: WP-03 EXACT source_text contract 준수.
    """
    src = _as_dict(premium)
    materials = _as_dict(src.get("materials"))
    overview = _as_dict(materials.get("overview"))
    profile = _as_dict(src.get("profile"))
    diagnosis = _as_dict(src.get("diagnosis"))
    canonical_sources = _as_list(src.get("canonical_sources"))

    source_index = _build_source_text_index(canonical_sources)
    obligation_rows = _build_obligation_rows(
        _as_list(materials.get("obligations")), source_index
    )
    evidence_rows = _build_evidence_rows(src.get("evidence"))

    return {
        "pdf_view_version": PDF_VIEW_VERSION,
        # 진단 메타
        "diagnosed_at": diagnosis.get("diagnosed_at"),
        # 사업장
        "profile": _build_profile_view(profile),
        # 결과 요약 — overview 값 그대로
        "total_obligation_count": overview.get("total_obligation_count", 0),
        "distinct_law_count": overview.get("distinct_law_count", 0),
        "obligation_type_counts": _as_dict(overview.get("obligation_type_counts")),
        # 의무 목록
        "obligations": obligation_rows,
        # 법령 구성 — materials 값 그대로
        "law_portfolio": [
            lp for lp in _as_list(materials.get("law_portfolio")) if isinstance(lp, dict)
        ],
        "article_bundles": [
            ab for ab in _as_list(materials.get("article_bundles")) if isinstance(ab, dict)
        ],
        "legal_actor_map": [
            a for a in _as_list(materials.get("legal_actor_map")) if isinstance(a, dict)
        ],
        # 법적 근거 원문
        "evidence": evidence_rows,
    }


__all__ = ["PDF_VIEW_VERSION", "build_paid_result_pdf_view_v1"]
