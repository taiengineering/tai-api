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

DISCOVERY-001-R1 corrections (WO-TAI-BIZINFO-SAFETY-DISCOVERY-001):
  - _TECH_ADOPTION extended with 제조AX, 인공지능, SaaS, IoT, 센서,
    영상분석, 안전관제 — previously uncovered digital/AI platform terms.
  - "창업기업" removed from _NON_SAFETY_PURPOSE: 창업기업 여부는 신청
    자격 조건이지 비안전 목적의 근거가 아님. 창업기업 스마트공장 지원은
    안전관리 소프트웨어 도입 가능성 검토 대상 (REVIEW_REQUIRED 유지).

DISCOVERY-002 additions (WO-TAI-BIZINFO-SAFETY-DISCOVERY-002):
  - _STARTUP_ELIGIBILITY_MARKERS: 창업기업·예비창업 등 신청 자격 조건 표현.
    tech_adoption 신호 없이 자격 조건만 존재하는 레코드는 REVIEW_REQUIRED에
    basis "eligibility:xxx"로 기록된다.
    목적: TECH_ADOPTION 90건과 창업기업 자격조건 ~76건을 basis로 분리.

SCOPE_REALIGN-001 (WO-TAI-BIZINFO-SAFETY-SCOPE-REALIGN-001):
  최종 목표 재확정 — 안전·안전관리 관련 모든 분야를 선별 범위로 포함.
  - _DIRECT_SAFETY 확장: 화재예방·유해인자·직업병·안전점검·안전검사·안전사고
    (소방·화재, 산업보건, 시설안전, 점검·검사 의무 분야)
  - _DIRECT_SAFETY_COMPACT Group C: 소방안전시설·작업환경개선
    (소방법·산업안전보건법 직접 의무 지원)
  - _ADJACENT_SIGNAL 확장: 재난안전·시설안전
    (공공·산업 양방향 가능 → REVIEW_REQUIRED; 목적 미확인)
  - 소방·시설안전·공공안전은 산업안전과 다르다는 이유만으로 OUT_OF_SCOPE
    처리하지 않는다. 비안전 목적 마커와 결합 시 purpose_conflict → REVIEW.

SCOPE_REALIGN-001-R1 (WO-TAI-BIZINFO-SAFETY-SCOPE-REALIGN-001-R1):
  제품안전 제외 기준 반영 및 판정 오류 보정.
  - `안전검사`를 _DIRECT_SAFETY에서 제거: 단독으로는 제품안전(생활용품·어린이제품)과
    현장안전(위험기계)을 구별할 수 없음. 위험기계 안전검사는 `위험기계` 키워드로 처리.
  - `안전산업` 추가: 재난안전산업·안전산업 박람회 등 안전산업 직접 지원을 포함.
  - `농어촌민박` _NON_SAFETY_PURPOSE에서 제거: 지원 대상 업종이지 사업 목적이 아님.
    소방안전시설 지원 대상이 농어촌민박이어도 소방안전이 목적이면 IN_SCOPE.
  - 제품안전 마커 추가: 생활용품·어린이제품·kc인증·제품안전은 판매 제품 안전성 검사
    목적임 → _NON_SAFETY_PURPOSE 등재, 직접 안전 신호 없을 때 OUT_OF_SCOPE.

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

# Direct safety-related terms covering all safety domains.
# A hit in both title and summary (purpose verifiable) or two or more hits
# inside the summary alone (strong evidence) qualifies for IN_SCOPE —
# unless a non-safety purpose marker is also present.
#
# SCOPE_REALIGN-001: 안전·안전관리 전체 분야를 포함한다.
# 소방·재해·보건·시설안전은 산업안전과 다르다는 이유만으로 제외하지 않는다.
_DIRECT_SAFETY: frozenset[str] = frozenset({
    # Domain 1 — 산업안전·재해예방
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
    "안전사고",      # 안전사고 예방·대응 (SCOPE_REALIGN-001)
    # Domain 3 — 안전시설·보호구·장비 점검
    "안전점검",      # 시설·장비 안전점검 의무 (SCOPE_REALIGN-001)
    # 주의: "안전검사" 단독은 제품안전(KC인증)과 현장안전(위험기계)을 구별할 수 없어
    # _DIRECT_SAFETY에서 제외. 위험기계 안전검사는 "위험기계" 키워드로 포착.
    # Domain 4 — 소방·화재안전
    "화재예방",      # 화재 예방 (소방법 의무; 산업시설 직접 적용) (SCOPE_REALIGN-001)
    # Domain 5 — 산업보건·유해인자
    "유해인자",      # 유해인자 관리 (산업안전보건법 의무관리 대상) (SCOPE_REALIGN-001)
    "직업병",        # 직업병 예방·관리 (산업보건 법정 의무) (SCOPE_REALIGN-001)
    # Domain 6 — 안전산업 직접 지원 (SCOPE_REALIGN-001-R1)
    "안전산업",      # 안전산업 분야 기업 사업화·박람회 등 직접 지원 (재난안전산업 포함)
})

# Compact-form (whitespace-collapsed) direct safety phrases.
# Three sub-groups:
#   (A) Safety management personnel terms — 법정 의무 인력 선임·고용 지원
#   (B) Safety technology/system terms — 안전관리 소프트웨어·시스템 구축 지원
#       (DISCOVERY-001: 스마트 안전솔루션 등 기술형 안전지원 포함)
#   (C) Fire/facility/occupational safety — 소방·시설·작업환경 직접 의무 지원
#       (SCOPE_REALIGN-001: 소방·시설안전을 직접 안전목적으로 처리)
# All sub-groups follow the same IN_SCOPE evidence paths as _DIRECT_SAFETY.
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
    # (C) Fire / facility / occupational environment (SCOPE_REALIGN-001)
    "소방안전시설",      # "소방안전 시설" 지원 — 직접 소방안전목적 (소방법)
    "작업환경개선",      # "작업환경 개선" — 산업안전보건법 의무 개선 지원
})

# Smart factory / AI / digital transformation terms that MAY enable
# safety management adoption — but do not confirm it without further evidence.
# Records reaching this path receive REVIEW_REQUIRED with basis "tech_adoption:..."
# to distinguish them from generic no_confirming_evidence records.
# Human review should check whether the specific support scope includes
# safety management software/systems.
_TECH_ADOPTION: frozenset[str] = frozenset({
    # DISCOVERY-001 original terms:
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
    # DISCOVERY-001-R1 additions — digital/AI platform terms:
    "제조ax",    # 제조 AX (AI Transformation) (e.g. PBLN_127610)
    "인공지능",  # 인공지능 솔루션 도입·활용 지원
    "saas",      # SaaS 솔루션 구독·도입 지원
    "iot",       # IoT 센서·기기 연결 지원
    "센서",      # 센서 기반 시스템 — 안전 모니터링 연계 가능
    "영상분석",  # 영상 분석 AI — CCTV 위험 감지 연계 가능
    "안전관제",  # 안전 관제 시스템 — 통합 안전 모니터링
})

# Adjacent / review-zone terms.  Presence raises REVIEW_REQUIRED;
# alone they do not confirm safety purpose — human review needed.
# SCOPE_REALIGN-001: 재난안전·시설안전 추가 (공공·산업 양방향 가능).
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
    "재난안전",    # 재난안전 (공공·산업 대상 모두 가능 — 목적 확인 필요) (SCOPE_REALIGN-001)
    "시설안전",    # 시설안전 (건물·공장·공공시설 가능 — 목적 확인 필요) (SCOPE_REALIGN-001)
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
    # "어촌"은 "농어촌" 내 부분 문자열 충돌(소방안전시설+농어촌민박 사례)로 제외.
    # 어촌 단독 사업은 어업인·어업경영체 등 다른 마커로 포착.
    "농업인",
    "농촌",
    "투자유치",
    "특례보증",
    "어업경영체",
    "개인정보",     # 개인정보보호·안전조치 — 데이터 보안, 산업안전 아님
    # 제품안전 목적 마커 (SCOPE_REALIGN-001-R1):
    # 판매·유통 제품의 안전성 검사·인증 지원은 현장·시설 안전관리와 무관.
    "생활용품",     # 생활용품 KC인증·안전검사 — 소비자 제품 안전, 사업장 안전 아님
    "어린이제품",   # 어린이제품 안전검사·인증 — 소비자 제품 안전, 사업장 안전 아님
    "kc인증",       # KC 인증 — 제품 출시용 안전 인증, 현장 설치 지원 아님
    "제품안전",     # 제품 자체의 안전성 검사·인증 — 사업장 안전관리 목적 아님
    # NOTE: "농어촌민박" intentionally excluded — 지원 대상 업종이지 사업 목적이 아님.
    # 소방안전시설 지원이 농어촌민박 대상이어도 소방안전이 목적이면 IN_SCOPE (SCOPE_REALIGN-001-R1).
    # NOTE: "창업기업" intentionally excluded — 창업기업 여부는 신청 자격 조건이며,
    # 비안전 목적의 근거가 아님 (DISCOVERY-001-R1). 창업기업 스마트공장 지원은
    # 안전관리 소프트웨어 도입 가능성이 있으므로 REVIEW_REQUIRED로 처리.
})

# Startup / early-stage company eligibility markers.
# These are APPLICANT ELIGIBILITY criteria, not evidence of non-safety purpose.
# Records with ONLY these markers (no direct safety or tech_adoption signal)
# receive REVIEW_REQUIRED with basis "eligibility:xxx" — distinct from both
# TECH_ADOPTION records and generic "no_confirming_evidence" records.
# Separates ~43 startup-eligibility records from ~90 tech-adoption records.
_STARTUP_ELIGIBILITY_MARKERS: frozenset[str] = frozenset({
    "창업기업",   # 창업기업 대상 사업 — 신청 자격 조건 (DISCOVERY-001-R1)
    "예비창업",   # 예비창업자 프로그램
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
    # DISCOVERY-002: startup / early-stage eligibility markers.
    # Only used to label REVIEW_REQUIRED when no tech or safety signal exists.
    # Separates ~43 창업기업-only records from ~90 tech_adoption records.
    eligibility_hits = [
        kw for kw in _STARTUP_ELIGIBILITY_MARKERS
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
    # ELIGIBILITY_ONLY — startup/early-stage applicant eligibility markers,
    # no tech or safety signal confirmed.
    # Distinguishes 창업기업-only records from generic no_confirming_evidence.
    # basis "eligibility:xxx" separates ~43 창업기업 records from ~90 tech_adoption.
    # ------------------------------------------------------------------

    if eligibility_hits and has_summary:
        return RelevanceDecision(
            verdict="REVIEW_REQUIRED",
            basis=tuple(f"eligibility:{kw}" for kw in eligibility_hits[:2]),
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
