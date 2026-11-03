"""OBJ-BZI-003 — Bizinfo Safety Relevance Selector.

Pure function — no DB, no network, no storage, no external AI.

Classifies a NormalizedSourceRecord into one of three verdicts:
  IN_SCOPE        — purpose directly relates to industrial safety
  OUT_OF_SCOPE    — content confirms non-safety purpose (not keyword absence)
  REVIEW_REQUIRED — ambiguous, unverifiable, missing content, purpose conflict

R1 corrections (WO-TAI-BIZINFO-OBJ-003-SOURCE-IV-R1):
  - IN_SCOPE requires confirmed safety PURPOSE; keyword co-occurrence alone
    is insufficient when non-safety purpose markers are also present.
  - OUT_OF_SCOPE requires positive evidence of non-safety purpose;
    keyword absence alone does not confirm out-of-scope.

IN_SCOPE is a candidate signal, not a content-publication approval.
OBJ-BZI-005 human editorial gate is required before public display.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from services.bizinfo.normalizer import NormalizedSourceRecord

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

# Direct industrial-safety terms.  A hit in both title and summary (purpose
# verifiable) or two or more hits inside the summary alone (strong evidence)
# qualifies for IN_SCOPE — unless a non-safety purpose marker is also present.
_DIRECT_SAFETY: frozenset[str] = frozenset({
    "산업안전",
    "산업재해",
    "중대재해",
    "작업안전",
    "안전보호구",
    "안전설비",
    "안전보건",
    "안전일터",
    "안전동행",
    "안전관리자",
    "위험성평가",
    "방호장치",
    "방호",          # 방호덮개, 방호망 등 — 위험기계 보호 장치
    "끼임",          # 끼임사고 예방
    "추락",          # 추락사고 예방
    "감전",          # 감전사고 예방
    "고위험산업",
    "산재예방",
    "재해예방",
    "안전진단",
    "유해위험",      # 유해위험요인 개선
    "위험기계",      # 위험기계 방호
})

# Adjacent / review-zone terms.  Presence raises REVIEW_REQUIRED;
# alone they do not confirm industrial-safety purpose.
_ADJACENT_SIGNAL: frozenset[str] = frozenset({
    "소방",
    "화학물질",
    "환경안전",
    "노동보건",
    "보건관리",
    "작업환경",
    "안전교육",
    "iso45001",
    "법정의무교육",
})

# Compact-form markers (no spaces) indicating a NON-industrial-safety purpose.
# Matched against whitespace-collapsed text to handle spacing variants
# e.g. "판로 개척" → compact "판로개척".
# Used for:
#   - R1-01: downgrade IN_SCOPE candidate to REVIEW_REQUIRED when safety keywords
#            appear alongside marketing/export purpose
#   - R1-02: confirm OUT_OF_SCOPE only when these appear without any safety signal
_NON_SAFETY_PURPOSE: frozenset[str] = frozenset({
    "판로개척",
    "수출마케팅",
    "해외판로",
    "해외진출",
    "운전자금",
    "이차보전",
    "어업인",
    "어촌",
    "농업인",
    "농촌",
    "창업기업",
    "투자유치",
    "특례보증",
    "어업경영체",
})


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelevanceDecision:
    """Result of review_relevance().

    verdict:  Classification outcome.
    basis:    Tuple of short evidence codes.  Never contains raw HTML,
              personal data, API keys, or full text from the record.
    """
    verdict: Literal["IN_SCOPE", "OUT_OF_SCOPE", "REVIEW_REQUIRED"]
    basis:   tuple[str, ...]


def review_relevance(record: NormalizedSourceRecord) -> RelevanceDecision:
    """Classify one NormalizedSourceRecord for industrial-safety relevance.

    Uses title and summary text only.  Hashtags and category codes are
    upstream fetch signals (OBJ-BZI-001) and do not determine the verdict.
    The original record is never modified.

    OUT_OF_SCOPE requires positive evidence of a non-safety purpose —
    absence of safety keywords is not sufficient.
    """
    title_lc    = (record.title   or "").lower()
    summary_lc  = (record.summary or "").lower()
    has_summary = bool(record.summary)

    # Whitespace-collapsed forms for non-safety purpose detection,
    # so "판로 개척" matches compact keyword "판로개척".
    _title_compact   = title_lc.replace(" ", "")
    _summary_compact = summary_lc.replace(" ", "")

    title_direct   = [kw for kw in _DIRECT_SAFETY   if kw in title_lc]
    summary_direct = [kw for kw in _DIRECT_SAFETY   if kw in summary_lc]
    adjacent_hits  = [
        kw for kw in _ADJACENT_SIGNAL
        if kw in title_lc or kw in summary_lc
    ]
    # R1: non-safety PURPOSE markers (marketing, export, unrelated sectors)
    non_safety_hits = [
        kw for kw in _NON_SAFETY_PURPOSE
        if kw in _summary_compact or kw in _title_compact
    ]

    # ------------------------------------------------------------------
    # IN_SCOPE paths — require confirmed safety PURPOSE
    # R1-01: if non-safety purpose markers co-exist, downgrade to REVIEW
    # ------------------------------------------------------------------

    # Purpose verified in both title and summary
    if title_direct and summary_direct:
        if non_safety_hits:
            # Safety keywords present but purpose appears to be marketing/export
            return RelevanceDecision(
                verdict="REVIEW_REQUIRED",
                basis=(
                    tuple(f"purpose_conflict:{kw}" for kw in non_safety_hits[:2]) +
                    tuple(f"safety_signal:{kw}"    for kw in (title_direct + summary_direct)[:2])
                ),
            )
        return RelevanceDecision(
            verdict="IN_SCOPE",
            basis=(
                tuple(f"title:{kw}"   for kw in title_direct[:2]) +
                tuple(f"summary:{kw}" for kw in summary_direct[:2])
            ),
        )

    # Strong multi-keyword evidence inside summary alone
    if len(summary_direct) >= 2:
        if non_safety_hits:
            return RelevanceDecision(
                verdict="REVIEW_REQUIRED",
                basis=(
                    tuple(f"purpose_conflict:{kw}" for kw in non_safety_hits[:2]) +
                    tuple(f"summary:{kw}"          for kw in summary_direct[:2])
                ),
            )
        return RelevanceDecision(
            verdict="IN_SCOPE",
            basis=tuple(f"summary:{kw}" for kw in summary_direct[:3]),
        )

    # ------------------------------------------------------------------
    # REVIEW_REQUIRED paths
    # ------------------------------------------------------------------

    # Direct keyword present but purpose not fully verifiable
    if title_direct or summary_direct:
        hits = title_direct + summary_direct
        basis: list[str] = [f"signal:{kw}" for kw in hits[:3]]
        if title_direct and not has_summary:
            basis.append("summary_missing")
        return RelevanceDecision(verdict="REVIEW_REQUIRED", basis=tuple(basis))

    # Adjacent / review-zone keyword found
    if adjacent_hits:
        return RelevanceDecision(
            verdict="REVIEW_REQUIRED",
            basis=tuple(f"adjacent:{kw}" for kw in adjacent_hits[:3]),
        )

    # ------------------------------------------------------------------
    # OUT_OF_SCOPE — only when non-safety purpose is explicitly confirmed.
    # R1-02: keyword absence alone does not confirm out-of-scope.
    # ------------------------------------------------------------------

    if has_summary and non_safety_hits:
        return RelevanceDecision(
            verdict="OUT_OF_SCOPE",
            basis=tuple(f"non_safety:{kw}" for kw in non_safety_hits[:3]),
        )

    # ------------------------------------------------------------------
    # REVIEW_REQUIRED fallback — cannot confirm safety or non-safety purpose
    # ------------------------------------------------------------------

    if has_summary:
        return RelevanceDecision(
            verdict="REVIEW_REQUIRED",
            basis=("no_confirming_evidence",),
        )
    return RelevanceDecision(
        verdict="REVIEW_REQUIRED",
        basis=("no_content_available",),
    )
