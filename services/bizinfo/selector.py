"""OBJ-BZI-003 — Bizinfo Safety Relevance Selector.

Pure function — no DB, no network, no storage, no external AI.

Classifies a NormalizedSourceRecord into one of three verdicts:
  IN_SCOPE        — purpose directly relates to industrial safety
  OUT_OF_SCOPE    — content confirms no industrial safety relation
  REVIEW_REQUIRED — ambiguous, keyword-only match, or missing content

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

# Direct industrial-safety terms.  A hit in *both* title and summary, or
# two or more hits inside the summary alone, qualifies for IN_SCOPE.
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
    "고위험산업",
    "산재예방",
    "재해예방",
    "안전진단",
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
    """
    title_lc    = (record.title   or "").lower()
    summary_lc  = (record.summary or "").lower()
    has_summary = bool(record.summary)

    title_direct   = [kw for kw in _DIRECT_SAFETY   if kw in title_lc]
    summary_direct = [kw for kw in _DIRECT_SAFETY   if kw in summary_lc]
    adjacent_hits  = [
        kw for kw in _ADJACENT_SIGNAL
        if kw in title_lc or kw in summary_lc
    ]

    # ------------------------------------------------------------------
    # IN_SCOPE paths — require content-level verification
    # ------------------------------------------------------------------

    # Purpose confirmed in both title and summary
    if title_direct and summary_direct:
        return RelevanceDecision(
            verdict="IN_SCOPE",
            basis=(
                tuple(f"title:{kw}"   for kw in title_direct[:2]) +
                tuple(f"summary:{kw}" for kw in summary_direct[:2])
            ),
        )

    # Strong multi-keyword evidence inside summary alone
    if len(summary_direct) >= 2:
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
    # OUT_OF_SCOPE — content exists and no safety signal found
    # ------------------------------------------------------------------

    if has_summary:
        return RelevanceDecision(
            verdict="OUT_OF_SCOPE",
            basis=("no_safety_signal_in_content",),
        )

    # ------------------------------------------------------------------
    # REVIEW_REQUIRED fallback — no content to verify
    # ------------------------------------------------------------------

    return RelevanceDecision(
        verdict="REVIEW_REQUIRED",
        basis=("no_content_available",),
    )
