"""OBJ-BZI-003 — Bizinfo LLM Semantic Analyzer.

WO-TAI-BIZINFO-OBJ-003-LLM-ANALYZER-001.
No DB, no routing, no scheduler. Pure-function analysis layer.

LLM call is injected via `llm_call_fn` for testability.
Tests must supply a mock. Production must supply _default_openai_call or
equivalent. Real API calls are subject to a separate execution-approval Gate.

Verdict contract:
  INCLUDE — industrial-safety support purpose confirmed in original text.
  EXCLUDE — non-safety purpose confirmed in original text.
  HOLD    — insufficient evidence, contradiction, AI error, or any
            verification failure. Not a human review queue.

Verification is code-level (independent of LLM self-report):
  1. cited_evidence exists verbatim in the original text (compact match).
  2. cited_evidence is not surrounded by negation/exclusion context.
  3. confidence == "high" for INCLUDE or EXCLUDE.
  Any failure → HOLD.

Layer 1 (selector.py) verdicts do NOT auto-confirm here.
  skip_layer1_exclude=False by default; enable only after quality evaluation
  confirms acceptable miss-rate on real sample data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from services.bizinfo.normalizer import NormalizedSourceRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPENAI_MODEL           = "gpt-4o-mini"
_MAX_TOKENS             = 400
_MAX_TITLE_LEN          = 200
_MAX_SUMMARY_LEN        = 1_000
_MAX_SUPPORT_TARGET_LEN = 300
_NEGATION_WINDOW        = 50  # compact chars before/after citation to inspect

# Compact-form particles indicating negation or exclusion in the vicinity of
# a cited evidence phrase.  Applied to INCLUDE verdicts only: for EXCLUDE,
# negation near the citation is expected and correct.
_NEGATION_VICINITY: frozenset[str] = frozenset({
    "제외",         # 제외되며, 제외됩니다, 제외입니다
    "무관",         # 무관한, 무관합니다
    "지원하지않",   # 지원하지 않습니다
    "대상아님",     # 지원 대상 아님
    "해당없음",     # 해당 없음
})

_SYSTEM_PROMPT = (
    "너는 한국 정부 지원사업·행사 공고의 실제 사업 목적을 분석하는 도구다.\n"
    "다음 규칙을 엄격히 지켜라.\n"
    "1) 판정 기준: 이 공고의 핵심 지원 목적이 산업 현장의 안전·재해예방·위험감소 활동과\n"
    "   직접 관련된가? 마케팅·수출·금융·농업·어업 등은 산업안전 지원이 아니다.\n"
    "2) cited_evidence는 원문에 있는 표현만 그대로 발췤한다. 없는 말을 만들지 않는다.\n"
    "3) 판정:\n"
    "   INCLUDE: 산업안전 직접 지원 목적이 원문에서 확인됨.\n"
    "   EXCLUDE: 비안전 목적이 원문에서 확인되고 안전 지원과 무관함이 명확함.\n"
    "   HOLD: 정보 부족, 목적 불명확, 확신 불가.\n"
    "4) cited_evidence는 판정 이유를 직접 뒷받침하는 원문 구절이어야 한다.\n"
    "   지원에서 제외된다는 표현은 INCLUDE의 근거가 될 수 없다.\n"
    "5) confidence: 판정이 확실하면 'high', 불확실하면 'low'.\n"
    "출력은 JSON만. 형식:\n"
    '{"verdict":"INCLUDE|EXCLUDE|HOLD",'
    '"purpose_summary":"<실제 사업 목적 한 문장>",'
    '"cited_evidence":"<원문 구절 그대로>",'
    '"confidence":"high|low"}'
)

# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisResult:
    """Result of analyze_relevance().

    verdict: INCLUDE / EXCLUDE / HOLD
    basis:   Short evidence codes.  Never contains raw HTML, PII, API keys,
             or full text from the record.
    """
    verdict: Literal["INCLUDE", "EXCLUDE", "HOLD"]
    basis:   tuple[str, ...]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(title: str, summary: str, support_target: str) -> tuple[str, str]:
    t  = title[:_MAX_TITLE_LEN]
    s  = summary[:_MAX_SUMMARY_LEN]
    st = support_target[:_MAX_SUPPORT_TARGET_LEN]
    parts = [f"[제목] {t}"]
    if s:
        parts.append(f"[요약] {s}")
    if st:
        parts.append(f"[지원대상] {st}")
    return _SYSTEM_PROMPT, "\n".join(parts)


# ---------------------------------------------------------------------------
# Code-level verification (independent of LLM self-report)
# ---------------------------------------------------------------------------


def _cited_in_negation_context(
    compact_cited: str, compact_original: str
) -> bool:
    """Return True if the cited evidence appears inside a negation window."""
    pos = compact_original.find(compact_cited)
    if pos < 0:
        return False
    window = compact_original[
        max(0, pos - _NEGATION_WINDOW): pos + len(compact_cited) + _NEGATION_WINDOW
    ]
    return any(marker in window for marker in _NEGATION_VICINITY)


def _verify(
    raw: dict,
    original_title: str,
    original_summary: str,
    original_support_target: str,
) -> AnalysisResult:
    """Verify LLM response with code-level checks.  Returns HOLD on any failure."""
    verdict = (raw.get("verdict") or "").strip().upper()
    if verdict not in {"INCLUDE", "EXCLUDE", "HOLD"}:
        return AnalysisResult(verdict="HOLD", basis=("invalid_verdict",))

    if verdict == "HOLD":
        return AnalysisResult(verdict="HOLD", basis=("llm_hold",))

    # INCLUDE / EXCLUDE require high confidence and verifiable evidence
    confidence = (raw.get("confidence") or "").strip().lower()
    if confidence != "high":
        return AnalysisResult(verdict="HOLD", basis=("low_confidence",))

    cited = (raw.get("cited_evidence") or "").strip()
    if not cited:
        return AnalysisResult(verdict="HOLD", basis=("missing_cited_evidence",))

    combined_lc = (
        (original_title or "")          + " " +
        (original_summary or "")        + " " +
        (original_support_target or "")
    ).lower()
    compact_combined = combined_lc.replace(" ", "")
    compact_cited    = cited.lower().replace(" ", "")

    if not compact_cited:
        return AnalysisResult(verdict="HOLD", basis=("empty_cited_evidence",))

    if compact_cited not in compact_combined:
        return AnalysisResult(verdict="HOLD", basis=("cited_not_in_source",))

    # Negation context check: only for INCLUDE.
    # For EXCLUDE, negation near cited evidence is expected and meaningful.
    if verdict == "INCLUDE" and _cited_in_negation_context(compact_cited, compact_combined):
        return AnalysisResult(verdict="HOLD", basis=("negation_context",))

    return AnalysisResult(
        verdict=verdict,
        basis=("cited_verified", f"layer2_{verdict.lower()}"),
    )


# ---------------------------------------------------------------------------
# Default OpenAI call  (production only — guarded against test/CI use)
# ---------------------------------------------------------------------------


def _default_openai_call(system_msg: str, user_msg: str) -> dict:
    """Call OpenAI API.  Requires OPENAI_API_KEY environment variable.

    Real API calls and associated costs require a separate execution-approval
    Gate per WO-TAI-BIZINFO-OBJ-003-LLM-ANALYZER-001.
    Do NOT call this function in tests or CI.
    """
    import os
    if os.environ.get("APP_ENV") in ("test", "ci"):
        raise RuntimeError(
            "_default_openai_call must not be used in test/CI environments. "
            "Inject a mock llm_call_fn instead."
        )
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=_MAX_TOKENS,
    )
    return json.loads(resp.choices[0].message.content)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_relevance(
    record: NormalizedSourceRecord,
    *,
    llm_call_fn: Callable[[str, str], dict],
    skip_layer1_exclude: bool = False,
    layer1_verdict: Optional[str] = None,
) -> AnalysisResult:
    """Classify one NormalizedSourceRecord using LLM semantic analysis.

    llm_call_fn:          callable(system_msg, user_msg) -> dict.
                          Must be injected; never use a default that calls a
                          real API without explicit approval.
    skip_layer1_exclude:  When True and layer1_verdict == "OUT_OF_SCOPE",
                          returns EXCLUDE immediately without an LLM call.
                          DISABLED by default — enable only after quality
                          evaluation confirms acceptable miss-rate.
    layer1_verdict:       Optional Layer 1 (selector.py) verdict string.

    The original record is never modified.
    """
    if skip_layer1_exclude and layer1_verdict == "OUT_OF_SCOPE":
        return AnalysisResult(
            verdict="EXCLUDE",
            basis=("layer1_out_of_scope_skip",),
        )

    title          = record.title          or ""
    summary        = record.summary        or ""
    support_target = record.support_target or ""

    system_msg, user_msg = _build_prompt(title, summary, support_target)

    try:
        raw = llm_call_fn(system_msg, user_msg)
    except Exception:
        return AnalysisResult(verdict="HOLD", basis=("llm_call_error",))

    if not isinstance(raw, dict):
        return AnalysisResult(verdict="HOLD", basis=("invalid_response_type",))

    return _verify(raw, title, summary, support_target)
