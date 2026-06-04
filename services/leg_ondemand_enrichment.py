"""
services/leg_ondemand_enrichment.py — ON_DEMAND Enrichment Post-Processor v1

역할:
- ON_DEMAND 후보만 대상으로 비어 있는 who/when/form_name/submit_org/submit_method 보강
- PERIODIC 후보는 절대 변경하지 않음
- 외부기관(소방청장/공단/정부/수탁기관/평가기관/실시기관/행정기관/지자체/장관) 의무는 skip
- 기존 candidate 필드만 채움 (신규 필드 생성 없음)
- 정규식/문자열 매칭만 사용 (LLM/AI 호출 없음)

원칙:
- 엔진/legal_format/정제/Check 무수정
- 빈 필드만 채움 (기존 값 덮어쓰기 금지)
- 9개 패턴: 신청·신고·제출(통보)·보고·기록·등록·확인·선임/해임
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

ONDEMAND = "ON_DEMAND"

# 외부기관 의무 → 사업장 의무로 보강하지 않고 skip
EXTERNAL_KEYWORDS = (
    "소방청장", "공단", "정부", "수탁기관", "평가기관",
    "실시기관", "행정기관", "지자체", "장관",
)

# 문장 내 행위주체 후보 (우선순위 순)
ACTORS = (
    "소방안전관리보조자", "소방안전관리자", "전기안전관리자", "기계설비유지관리자",
    "안전보건관리책임자", "관리감독자", "안전관리자", "보건관리자",
    "관리주체", "관계인", "경영책임자", "사업주",
)

# 패턴별 WHEN 트리거 (ON_DEMAND 전용 표현)
WHEN_BY_PATTERN = {
    "선임해임": "선임·해임 후 법정기한 내",
    "신청": "사유 발생 시",
    "신고": "사유 발생 후 법정기한 내",
    "제출통보": "법정 제출시기",
    "보고": "법정 보고시기",
    "기록": "작성 후 법정 보존기간",
    "등록": "사유 발생 시",
    "확인": "요구 시",
}

# 패턴별 METHOD
METHOD_BY_PATTERN = {
    "선임해임": "관할기관 제출", "신청": "관할기관 제출", "신고": "관할기관 제출",
    "제출통보": "관할기관 제출", "보고": "관할기관 제출", "등록": "관할기관 제출",
    "확인": "확인서 발급", "기록": "자체 보관",
}

# 패턴별 ORG (기록은 자체보관이라 미부여)
ORG_BY_PATTERN = {
    "선임해임": "관할 행정기관", "신청": "관할 행정기관", "신고": "관할 행정기관",
    "제출통보": "관할 행정기관", "보고": "관할 행정기관", "등록": "관할 행정기관",
    "확인": "관할 행정기관",
}

# 패턴별 FORM 접미 (문장에서 서류명 추출 실패 시 사용)
FORM_SUFFIX = {
    "선임해임": "신고서", "신청": "신청서", "신고": "신고서", "제출통보": "제출서류",
    "보고": "보고서", "기록": "기록부", "등록": "등록신청서", "확인": "확인서",
}

_DOC_RE = re.compile(
    r"[가-힣A-Za-z0-9·]+(?:신고증명서|신고서|신청서|보고서|확인서|증명서|"
    r"성적서|계획서|명세서|대장|기록부|신고증)"
)


def _is_external(what: str) -> bool:
    return any(k in what for k in EXTERNAL_KEYWORDS)


def _detect_pattern(what: str) -> str:
    """9개 패턴 분류 (우선순위 순). 해당 없으면 빈 문자열."""
    if re.search(r"선임|해임", what):
        return "선임해임"
    if "신청" in what:
        return "신청"
    if "신고" in what:
        return "신고"
    if re.search(r"제출|통보|송부|통지", what):
        return "제출통보"
    if "보고" in what:
        return "보고"
    if re.search(r"기록|보관|대장|보존", what):
        return "기록"
    if "등록" in what:
        return "등록"
    if re.search(r"확인", what):
        return "확인"
    return ""


def _extract_actor(what: str) -> str:
    for a in ACTORS:
        if a in what:
            return a
    return ""


def _extract_form(what: str, pattern: str) -> str:
    m = _DOC_RE.search(what)
    if m:
        return m.group(0)
    return FORM_SUFFIX.get(pattern, "")


def _blank(v: Any) -> bool:
    return not (v or "").strip()


def enrich_ondemand(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ON_DEMAND 후보의 빈 who/when/form_name/submit_org/submit_method 보강.

    - PERIODIC 후보는 변경하지 않음
    - 외부기관 의무는 skip
    - 빈 필드만 채움 (기존 값 보존)
    - 후보 개수 불변
    """
    for c in (candidates or []):
        if (c.get("schedule_type") or "").strip() != ONDEMAND:
            continue
        what = c.get("what") or ""
        if _is_external(what):
            continue
        pattern = _detect_pattern(what)
        if not pattern:
            continue

        if _blank(c.get("who")):
            actor = _extract_actor(what)
            if actor:
                c["who"] = actor

        if _blank(c.get("form_name")):
            form = _extract_form(what, pattern)
            if form:
                c["form_name"] = form

        if _blank(c.get("submit_org")):
            org = ORG_BY_PATTERN.get(pattern)
            if org:
                c["submit_org"] = org

        if _blank(c.get("when")):
            when = WHEN_BY_PATTERN.get(pattern)
            if when:
                c["when"] = when

        if _blank(c.get("submit_method")):
            method = METHOD_BY_PATTERN.get(pattern)
            if method:
                c["submit_method"] = method

    return candidates
