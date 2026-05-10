"""증거 기반 법령 파싱 엔진 — Evidence Token 추출.

원칙: 의미 해석 금지. 원문에서 span 기반 토큰만 기계 추출.
모든 추출값은 source_text 내 span(start, end)을 가져야 한다.
span이 없으면 폐기.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvidenceToken:
    part_id: str
    token_type: str
    value: str
    span_start: int
    span_end: int
    source_text: str


@dataclass
class EvidenceCandidate:
    part_id: str
    candidate_type: str
    candidate_value: str
    status: str = "CANDIDATE"
    evidence_token_ids: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass
class EvidenceRelation:
    part_id: str
    actor_candidate: str | None = None
    action_candidate: str | None = None
    target_candidate: str | None = None
    condition_candidate: str | None = None
    exception_candidate: str | None = None
    evidence_token_ids: list[str] = field(default_factory=list)
    status: str = "CANDIDATE"


@dataclass
class EvidenceIssue:
    part_id: str
    issue_type: str
    detail: dict[str, Any] = field(default_factory=dict)
    source_text: str | None = None


@dataclass
class PartResult:
    part_id: str
    source_text: str
    tokens: list[EvidenceToken] = field(default_factory=list)
    candidates: list[EvidenceCandidate] = field(default_factory=list)
    relations: list[EvidenceRelation] = field(default_factory=list)
    issues: list[EvidenceIssue] = field(default_factory=list)
    validation_status: str = "UNRESOLVED"


# ── 보호 영역 (추출 제외) ─────────────────────────────

def _find_protected_spans(text: str) -> list[tuple[int, int]]:
    """「법률명」 등 참조 내부는 토큰 추출에서 제외."""
    spans = []
    for m in re.finditer(r"「[^」]+」", text):
        spans.append((m.start(), m.end()))
    return spans


def _is_inside_protected(start: int, end: int, protected: list[tuple[int, int]]) -> bool:
    for ps, pe in protected:
        if start >= ps and end <= pe:
            return True
    return False


# ── 패턴 정의 ─────────────────────────────────────────

OBLIGATION_PATTERNS = [
    r"하여야\s*한다",
    r"해야\s*한다",
    r"하여야\s*합니다",
    r"의무가\s*있다",
    r"지켜야\s*한다",
    r"이행하여야\s*한다",
]

PROHIBITION_PATTERNS = [
    r"할\s*수\s*없다",
    r"하여서는\s*아니\s*된다",
    r"아니\s*된다",
    r"금지\s*한다",
    r"못한다",
]

AUTHORITY_PATTERNS = [
    r"할\s*수\s*있다",
]

CONDITION_PATTERNS = [
    r"경우에는",
    r"경우에",
    r"때에는",
    r"때에",
]

EXCEPTION_PATTERNS = [
    r"^다만[\s,]",
    r"^단[\s,]",
]

FREQUENCY_PATTERNS = [
    r"정기적으로",
    r"매년",
    r"매\s*\d+\s*년",
    r"분기마다",
    r"반기마다",
    r"월\s*\d+\s*회",
    r"\d+\s*년마다",
]

# 기한: 반드시 숫자+단위+까지/이내 형태만
DEADLINE_PATTERNS = [
    r"\d+일\s*이내",
    r"\d+개월\s*이내",
    r"\d+년\s*이내",
    r"\d+일\s*까지",
    r"\d+개월\s*까지",
    r"\d+년\s*까지",
    r"이전에",
]

REFERENCE_PATTERNS = [
    r"제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?",
    r"「[^」]+」",
]

ATTACHMENT_PATTERNS = [
    r"별표\s*제?\s*\d+",
    r"별지\s*제?\s*\d+",
]

ACTION_KEYWORDS = [
    "점검", "검사", "보고", "신고", "설치", "관리", "측정", "기록",
    "교육", "훈련", "평가", "조사", "승인", "허가", "등록", "지정",
    "변경", "폐지", "취소", "정지", "시정", "개선", "보수", "교체",
    "제출", "통보", "공표", "고시", "공고", "게시", "비치", "보존",
    "작성", "확인", "배치", "선임", "해임", "감독", "감시",
]

ACTOR_PATTERNS = [
    r"사업주(?:는|가|의|에게)?",
    r"관리(?:자|인|책임자)(?:는|가|의|에게)?",
    r"안전관리(?:자|책임자)(?:는|가|의)?",
    r"시장[\s·]군수[\s·]구청장(?:은|이|의)?",
    r"(?:시[\s·])?도지사(?:는|가|의)?",
    r"(?:기후에너지)?환경부장관(?:은|이|의)?",
    r"국토교통부장관(?:은|이|의)?",
    r"고용노동부장관(?:은|이|의)?",
    r"소방청장(?:은|이|의)?",
    r"설치자(?:는|가|의)?",
    r"소유자(?:는|가|의)?",
    r"(?:건축|시공|설계|감리)(?:자|사)(?:는|가|의)?",
]


# ── 추출 함수 ─────────────────────────────────────────

def _extract_by_patterns(
    text: str, part_id: str, patterns: list[str], token_type: str,
    protected: list[tuple[int, int]] | None = None,
) -> list[EvidenceToken]:
    tokens = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            if protected and _is_inside_protected(m.start(), m.end(), protected):
                continue
            tokens.append(EvidenceToken(
                part_id=part_id, token_type=token_type,
                value=m.group(), span_start=m.start(), span_end=m.end(),
                source_text=text[m.start():m.end()],
            ))
    return tokens


def _extract_action_tokens(
    text: str, part_id: str, protected: list[tuple[int, int]],
) -> list[EvidenceToken]:
    tokens = []
    for kw in ACTION_KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            if _is_inside_protected(m.start(), m.end(), protected):
                continue
            tokens.append(EvidenceToken(
                part_id=part_id, token_type="ACTION_TOKEN",
                value=m.group(), span_start=m.start(), span_end=m.end(),
                source_text=text[m.start():m.end()],
            ))
    return tokens


# ── 메인 추출 ──────────────────────────────────────────

def extract_evidence(part_id: str, source_text: str) -> PartResult:
    result = PartResult(part_id=part_id, source_text=source_text)

    if not source_text or not source_text.strip():
        result.validation_status = "FAIL"
        result.issues.append(EvidenceIssue(
            part_id=part_id, issue_type="ISSUE_NO_SPAN",
            detail={"reason": "source_text 비어있음"},
        ))
        return result

    text = source_text.strip()
    protected = _find_protected_spans(text)

    # 참조(REFERENCE)는 보호 영역 자체를 추출하므로 protected 적용 안 함
    result.tokens.extend(_extract_by_patterns(text, part_id, REFERENCE_PATTERNS, "REFERENCE_TOKEN"))
    result.tokens.extend(_extract_by_patterns(text, part_id, ATTACHMENT_PATTERNS, "ATTACHMENT_TOKEN"))

    # 나머지는 「」 내부 제외
    result.tokens.extend(_extract_by_patterns(text, part_id, OBLIGATION_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, PROHIBITION_PATTERNS, "PROHIBITION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, AUTHORITY_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, CONDITION_PATTERNS, "CONDITION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, EXCEPTION_PATTERNS, "EXCEPTION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, FREQUENCY_PATTERNS, "FREQUENCY_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, DEADLINE_PATTERNS, "DEADLINE_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, ACTOR_PATTERNS, "ACTOR_TOKEN", protected))
    result.tokens.extend(_extract_action_tokens(text, part_id, protected))

    # span 검증
    valid_tokens = []
    for tok in result.tokens:
        if 0 <= tok.span_start < tok.span_end <= len(text):
            if text[tok.span_start:tok.span_end] == tok.source_text:
                valid_tokens.append(tok)
            else:
                result.issues.append(EvidenceIssue(
                    part_id=part_id,
                    issue_type="ISSUE_GENERATED_VALUE_NOT_IN_SOURCE",
                    detail={"value": tok.value, "span": [tok.span_start, tok.span_end]},
                    source_text=tok.source_text,
                ))
        else:
            result.issues.append(EvidenceIssue(
                part_id=part_id, issue_type="ISSUE_NO_SPAN",
                detail={"value": tok.value, "span": [tok.span_start, tok.span_end]},
            ))

    result.tokens = valid_tokens
    result.candidates = _build_candidates(part_id, result.tokens)
    result.relations = _build_relations(part_id, result.candidates)

    if result.issues:
        result.validation_status = "FAIL"
    elif not result.tokens:
        result.validation_status = "UNRESOLVED"
    else:
        result.validation_status = "PASS"

    return result


def _build_candidates(part_id: str, tokens: list[EvidenceToken]) -> list[EvidenceCandidate]:
    candidates = []
    seen = set()
    TYPE_MAP = {
        "ACTOR_TOKEN": "ACTOR", "ACTION_TOKEN": "ACTION",
        "OBLIGATION_TOKEN": "OBLIGATION_TYPE", "PROHIBITION_TOKEN": "OBLIGATION_TYPE",
        "CONDITION_TOKEN": "CONDITION", "EXCEPTION_TOKEN": "EXCEPTION",
        "FREQUENCY_TOKEN": "FREQUENCY", "DEADLINE_TOKEN": "DEADLINE",
        "TARGET_TOKEN": "TARGET", "REFERENCE_TOKEN": "REFERENCE",
        "ATTACHMENT_TOKEN": "ATTACHMENT",
    }
    for tok in tokens:
        key = (tok.token_type, tok.value)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(EvidenceCandidate(
            part_id=part_id,
            candidate_type=TYPE_MAP.get(tok.token_type, "UNKNOWN"),
            candidate_value=tok.value, status="CANDIDATE",
        ))
    return candidates


def _build_relations(part_id: str, candidates: list[EvidenceCandidate]) -> list[EvidenceRelation]:
    actors = [c for c in candidates if c.candidate_type == "ACTOR"]
    actions = [c for c in candidates if c.candidate_type == "ACTION"]
    conditions = [c for c in candidates if c.candidate_type == "CONDITION"]
    exceptions = [c for c in candidates if c.candidate_type == "EXCEPTION"]
    if not actors and not actions:
        return []
    return [EvidenceRelation(
        part_id=part_id,
        actor_candidate=actors[0].candidate_value if actors else None,
        action_candidate=actions[0].candidate_value if actions else None,
        condition_candidate=conditions[0].candidate_value if conditions else None,
        exception_candidate=exceptions[0].candidate_value if exceptions else None,
        status="CANDIDATE" if actors and actions else "UNRESOLVED",
    )]


# ── DB 저장 ────────────────────────────────────────────

def save_result(conn, result: PartResult) -> dict[str, int]:
    import json
    cur = conn.cursor()
    saved = {"tokens": 0, "candidates": 0, "relations": 0, "validations": 0, "issues": 0}

    for tok in result.tokens:
        try:
            cur.execute("""
                INSERT INTO evidence_token (part_id, token_type, value, span_start, span_end, source_text)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (tok.part_id, tok.token_type, tok.value, tok.span_start, tok.span_end, tok.source_text))
            saved["tokens"] += 1
        except Exception as e:
            logger.warning("evidence_token INSERT 실패: %s", e)

    for cand in result.candidates:
        try:
            cur.execute("""
                INSERT INTO evidence_candidate (part_id, candidate_type, candidate_value, status, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (cand.part_id, cand.candidate_type, cand.candidate_value, cand.status, cand.reason))
            saved["candidates"] += 1
        except Exception as e:
            logger.warning("evidence_candidate INSERT 실패: %s", e)

    for rel in result.relations:
        try:
            cur.execute("""
                INSERT INTO evidence_relation
                    (part_id, actor_candidate, action_candidate, target_candidate,
                     condition_candidate, exception_candidate, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (rel.part_id, rel.actor_candidate, rel.action_candidate,
                  rel.target_candidate, rel.condition_candidate,
                  rel.exception_candidate, rel.status))
            saved["relations"] += 1
        except Exception as e:
            logger.warning("evidence_relation INSERT 실패: %s", e)

    try:
        cur.execute("""
            INSERT INTO evidence_validation (part_id, validation_status, total_tokens, valid_tokens, issues)
            VALUES (%s, %s, %s, %s, %s)
        """, (result.part_id, result.validation_status,
              len(result.tokens) + len(result.issues), len(result.tokens),
              json.dumps([{"type": i.issue_type, "detail": i.detail} for i in result.issues], ensure_ascii=False)))
        saved["validations"] += 1
    except Exception as e:
        logger.warning("evidence_validation INSERT 실패: %s", e)

    for iss in result.issues:
        try:
            cur.execute("""
                INSERT INTO evidence_issue (part_id, issue_type, detail, source_text)
                VALUES (%s, %s, %s, %s)
            """, (iss.part_id, iss.issue_type,
                  json.dumps(iss.detail, ensure_ascii=False), iss.source_text))
            saved["issues"] += 1
        except Exception as e:
            logger.warning("evidence_issue INSERT 실패: %s", e)

    conn.commit()
    cur.close()
    return saved
