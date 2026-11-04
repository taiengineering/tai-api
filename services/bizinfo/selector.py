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

FINAL-FIX corrections (WO-TAI-BIZINFO-OBJ-003-IV-FINAL-FIX):
  - IN_SCOPE is blocked when safety keywords appear in a negating context
    (e.g. "안전설비 지원 제외", "산업안전과 무관"); detected via
    _SAFETY_EXCLUSION_COMPACT compact-form markers in the summary.

DISCOVERY-001 additions (WO-TAI-BIZINFO-SAFETY-DISCOVERY-001):
  - _DIRECT_SAFETY_COMPACT extended with safety technology/system terms
    (e.g. "스마트 안전솔루션", "안전관리 시스템") → same IN_SCOPE paths
    as personnel compact terms.
  - _TECH_ADOPTION: smart factory / AI / DX terms that have potential for
    safety management adoption. When present without any direct safety signal,
    these produce REVIEW_REQUIRED with basis "tech_adoption:..." to distinguish
    tech-potential records from generic no_confirming_evidence records.

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
    "보건관리자",    # 안전관리자와 동급 법정 의무 인력 (산업안전보건법)
    "안전관리담당자",  # 소규모사업장 법정 의무
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

# Compact-form (whitespace-collapsed) direct safety phrases.
# Two sub-groups:
#   (A) Safety management personnel terms — 법정 의무 인력 선임·고용 지원
#   (B) Safety technology/system terms — 안전관리 소프트웨어·시스템 구축 지원
#       (DISCOVERY-001: 스마트 안전솔루션 등 기술형 안전지원 포함)
# Both sub-groups follow the same IN_SCOPE evidence paths as _DIRECT_SAFETY.
_DIRECT_SAFETY_COMPACT: frozenset[str] = frozenset({
    # (A) Personnel
    "안전관리인력",       # "안전관리 인력" 고용·선임 지원
    "안전보건관리담당자",  # "안전보건관리 담당자" 선임 지원 (소규모사업장)
    "안전보건담당자",     # "안전보건 담당자" 선임·지원
    "안전관리인원",       # "안전관리 인원" 채용 지원
    # (B) Safety technology/systems
    "스마트안전솔루션",   # "스마트 안전솔루션" 구축·도입 지원 (e.g. PBLN_127340)
    "스마트안전",        # "스마트 안전" 솔루션·관리 등
    "안전솔루션",        # "안전 솔루션" 도입 지원
    "안전관리시스템",    # "안전관리 시스템" 구축 지원
    "안전모니터링",      # "안전 모니터링" 시스템 지원
    "재해예방시스템",    # "재해예방 시스템" 구축
    "안전관리소프트웨어", # "안전관리 소프트웨어" 도입
    "산업안전솔루션",    # "산업안전 솔루션" 구축
})

# Smart factory / AI / digital transformation terms that MAY enable
# safety management adoption — but do not confirm it without further evidence.
# Records reaching this path receive REVIEW_REQUIRED with basis "tech_adoption:..."
# to distinguish them from generic no_confirming_evidence records.
# Human review should check whether the specific support scope includes
# safety management software/systems.
_TECH_ADOPTION: frozenset[str] = frozenset({
    "스마트공장",   # 스마트공장 구축·고도화 지원사업
    "스마트팩토리", # smart factory (English transliteration)
    "ai팩토리",    # AI 팩토리 프로그램
    "스마트제조",   # 스마트 제조혁신
    "제조혁신",    # 제조혁신 바우처 (e.g. PBLN_127589)
    "예지보전",    # 예지보전 — 설비 고장 예측, 안전 연계 가능
    "디지털트윈",  # 디지털 트윈 — 현장 시뮬레이션 안전 연계 가능
    "공정자동화",  # 공정 자동화 — 위험작업 자동화
    "스마트설비",  # 스마트 설비 도입
    "디지털전환",  # 디지털 전환 (DX) (e.g. PBLN_127587, PBLN_124841)
    "스마트공정",  # 스마트 공정 최적화
    "제조ai",     # 제조 AI 도입
    "ai전환",     # AI 전환 (AX)
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
#   - R2: when only adjacent (not direct) safety signal exists alongside a confirmed
#         non-safety purpose → OUT_OF_SCOPE (e.g. 농어촌민박 소방시설)
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
    "농어촌민박",   # 농촌 숙박시설 — 산업현장 아님 (R2: adjacent+non_safety → OUT)
    "개인정보",     # 개인정보보호·안전조치 — 데이터 보안, 산업안전 아님
})

# Compact-form markers indicating the safety aspect is explicitly negated or
# excluded in the summary (e.g. "안전 설비 지원 제외", "산업안전과 무관").
# Matched against whitespace-collapsed summary text only.
# When present alongside safety keywords, IN_SCOPE cannot be confirmed.
_SAFETY_EXCLUSION_COMPACT: frozenset[str] = frozenset({
    "산업안전과무관",      # 산업안전과 무관한 ~
    "안전과무관",          # 안전과 무관한 ~
    "지원대상아님",        # 지원 대상 아님
    "안전설비지원제외",    # 안전 설비 지원 제외
    "안전지원제외",        # 안전 지원 제외
    "산업안전제외",        # 산업안전 제외
})

# Non-safety markers that only block IN_SCOPE when they appear in the TITLE.
# When found only in the summary, they are treated as incidental (e.g. a
# boilerplate privacy notice at the bottom of an industrial-safety grant
# announcement) and do NOT downgrade a confirmed title+summary safety signal.
# These markers still count toward OUT_OF_SCOPE when they are the main purpose
# (the OUT_OF_SCOPE path uses full non_safety_hits, not conflict_hits).
_INCIDENTAL_SAFE_MARKERS: frozenset[str] = frozenset({
    "개인정보",   # 개인정보 처리방침 안내 등 보조문구에 등장하는 경우 무시
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

    # R2: compact-form multi-word direct safety phrases (e.g. "안전관리 인력")
    title_direct   = title_direct   + [kw for kw in _DIRECT_SAFETY_COMPACT if kw in _title_compact]
    summary_direct = summary_direct + [kw for kw in _DIRECT_SAFETY_COMPACT if kw in _summary_compact]

    adjacent_hits  = [
        kw for kw in _ADJACENT_SIGNAL
        if kw in title_lc or kw in summary_lc
    ]
    # R1: non-safety PURPOSE markers (marketing, export, unrelated sectors)
    non_safety_hits = [
        kw for kw in _NON_SAFETY_PURPOSE
        if kw in _summary_compact or kw in _title_compact
    ]
    # FINAL-FIX: explicit negation of safety relevance within the summary
    exclusion_hits = [
        kw for kw in _SAFETY_EXCLUSION_COMPACT
        if kw in _summary_compact
    ]
    # R1-03: incidental-safe markers (e.g. 개인정보) only block IN_SCOPE
    # when in the title; summary-only appearance is treated as boilerplate.
    non_safety_conflict_hits = [
        kw for kw in non_safety_hits
        if kw not in _INCIDENTAL_SAFE_MARKERS or kw in _title_compact
    ]
    # DISCOVERY-001: smart factory / AI / DX adoption potential signals.
    # Computed unconditionally; only used in the TECH_ADOPTION path at the
    # bottom of the function when no direct or tech-safety signal was found.
    tech_adoption_hits = [
        kw for kw in _TECH_ADOPTION
        if kw in _title_compact or kw in _summary_compact
    ]

    # ------------------------------------------------------------------
    # IN_SCOPE paths — require confirmed safety PURPOSE
    # R1-01: if non-safety purpose markers co-exist, downgrade to REVIEW
    # ------------------------------------------------------------------

    # Purpose verified in both title and summary
    if title_direct and summary_direct:
        if non_safety_conflict_hits or exclusion_hits:
            # Safety keywords present but purpose is marketing/export OR
            # safety relevance is explicitly negated in summary
            return RelevanceDecision(
                verdict="REVIEW_REQUIRED",
                basis=(
                    tuple(f"purpose_conflict:{kw}" for kw in non_safety_conflict_hits[:2]) +
                    tuple(f"safety_negated:{kw}"   for kw in exclusion_hits[:2]) +
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
        if non_safety_conflict_hits or exclusion_hits:
            return RelevanceDecision(
                verdict="REVIEW_REQUIRED",
                basis=(
                    tuple(f"purpose_conflict:{kw}" for kw in non_safety_conflict_hits[:2]) +
                    tuple(f"safety_negated:{kw}"   for kw in exclusion_hits[:2]) +
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

    # R2: adjacent safety signal overridden by confirmed non-safety purpose.
    # When only adjacent (not direct) safety keywords appear alongside an
    # explicit non-safety purpose marker, the purpose evidence wins.
    # e.g. 농어촌민박 소방안전시설: 소방=adjacent, 농어촌민박=non_safety → OUT_OF_SCOPE.
    if adjacent_hits and non_safety_hits and has_summary:
        return RelevanceDecision(
            verdict="OUT_OF_SCOPE",
            basis=(
                tuple(f"non_safety:{kw}"        for kw in non_safety_hits[:2]) +
                tuple(f"adjacent_overridden:{kw}" for kw in adjacent_hits[:1])
            ),
        )

    # Adjacent / review-zone keyword found (no non-safety purpose confirmed)
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
    # TECH_ADOPTION_POTENTIAL — no direct/tech safety signal confirmed,
    # but smart factory / AI / DX terms present.  Richer basis than
    # no_confirming_evidence; human review should verify support scope.
    # Non-safety purpose records are already handled above (OUT_OF_SCOPE).
    # ------------------------------------------------------------------

    if tech_adoption_hits and has_summary:
        return RelevanceDecision(
            verdict="REVIEW_REQUIRED",
            basis=tuple(f"tech_adoption:{kw}" for kw in tech_adoption_hits[:3]),
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
