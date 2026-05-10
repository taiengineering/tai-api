"""증거 기반 법령 파싱 엔진 — Evidence Token 추출 v3.

핵심 원칙:
1. 원문 그대로 저장. 한 글자도 변경 금지.
2. 모든 조항은 100% 매핑. 토큰이 없어도 원문 링크 유지.
3. 의미 확정 금지. 토큰은 증거일 뿐.
4. 모든 토큰은 원문 span(start, end) 필수.
5. "관리하여야 한다" 전체를 저장. "관리"로 줄이지 않음.
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
    value: str          # 원문 그대로 (변형 금지)
    span_start: int
    span_end: int
    source_text: str    # text[span_start:span_end] 와 반드시 일치


@dataclass
class EvidenceCandidate:
    part_id: str
    candidate_type: str
    candidate_value: str  # 원문 그대로
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


# ── 보호 영역 ─────────────────────────────────────────

def _find_protected_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"「[^」]+」", text)]


def _is_inside_protected(start: int, end: int, protected: list[tuple[int, int]]) -> bool:
    return any(start >= ps and end <= pe for ps, pe in protected)


# ── 패턴 v3: 전체 표현 보전 ──────────────────────────

# 의무 표현 (동사+어미 전체 보전)
OBLIGATION_FULL = [
    r"[가-힣]{1,30}하여야\s*한다",
    r"[가-힣]{1,30}해야\s*한다",
    r"[가-힣]{1,30}하여야\s*합니다",
    r"[가-힣]{1,30}지켜야\s*한다",
    r"[가-힣]{1,30}따라야\s*한다",
    r"[가-힣]{1,30}하여야\s*하며",
    r"의무가\s*있다",
]

# 금지 표현 (전체 보전)
PROHIBITION_FULL = [
    r"[가-힣]{1,30}할\s*수\s*없다",
    r"[가-힣]{1,30}하여서는\s*아니\s*된다",
    r"[가-힣]{1,30}아니\s*된다",
    r"[가-힣]{1,30}금지\s*한다",
    r"[가-힣]{1,30}못한다",
]

# 권한 표현 (전체 보전)
AUTHORITY_FULL = [
    r"[가-힣]{1,30}할\s*수\s*있다",
]

# 의무 항목 (호 단위)
OBLIGATION_ITEM = [
    r"[가-힣]{1,30}할\s*것",
]

# 정의 표현 (전체 보전)
DEFINITION_FULL = [
    r"[가-힣]{1,30}(?:이라|라)\s*한다",
    r"[가-힣]{1,30}을\s*말한다",
    r"[가-힣]{1,30}를\s*말한다",
]

# 위임 표현 (전체 보전)
DELEGATION_FULL = [
    r"대통령령으로\s*정하는\s*[가-힣]{1,20}",
    r"[가-힣]{1,20}부령으로\s*정하는\s*[가-힣]{1,20}",
    r"[가-힣]{1,30}으로\s*정한다",
]

# 조건 표현 (전체 보전)
CONDITION_FULL = [
    r"[가-힣]{1,30}(?:하는|한|인)\s*경우에는",
    r"[가-힣]{1,30}(?:하는|한|인)\s*경우에",
    r"[가-힣]{1,30}(?:하는|한|인)\s*경우",
    r"[가-힣]{1,30}(?:하는|한|인)\s*때에는",
    r"[가-힣]{1,30}(?:하는|한|인)\s*때에",
]

# 예외 표현
EXCEPTION_FULL = [
    r"^다만[,\s]",
    r"^단[,\s]",
    r"[가-힣]{1,20}제외한다",
    r"적용하지\s*아니한다",
    r"그러하지\s*아니하다",
]

# 주기 표현 (원문 그대로)
FREQUENCY_FULL = [
    r"정기적으로", r"매년", r"매\s*\d+\s*년",
    r"분기마다", r"반기마다", r"월\s*\d+\s*회",
    r"\d+년마다", r"\d+회\s*이상", r"수시로",
]

# 기한 표현 (원문 그대로)
DEADLINE_FULL = [
    r"\d+일\s*이내에?", r"\d+개월\s*이내에?", r"\d+년\s*이내에?",
    r"\d+일\s*까지", r"\d+일\s*전(?:까지)?",
    r"지체\s*없이", r"즉시",
]

# 참조 (법률명 + 조항번호, 원문 그대로)
REFERENCE_FULL = [
    r"「[^」]+」",
    r"제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?",
]

# 별표/별지 (원문 그대로)
ATTACHMENT_FULL = [
    r"별지\s*제?\s*\d+(?:호)?(?:서식)?",
    r"별표\s*제?\s*\d+",
    r"별표", r"별지",
]

# 주체 표현 (조사 포함 원문 그대로)
ACTOR_FULL = [
    r"사업주(?:는|가|의|에게|와|또는)?",
    r"근로자(?:는|가|의|에게)?",
    r"소방(?:본부장|서장|청장)(?:은|이|의|에게|또는|\s*또는)?",
    r"관리(?:자|인|책임자)(?:는|가|의|에게)?",
    r"안전관리(?:자|책임자)(?:는|가|의)?",
    r"보건관리(?:자|책임자)(?:는|가|의)?",
    r"안전보건관리(?:자|책임자|담당자)(?:는|가|의)?",
    r"시장[\s·ㆍ]군수[\s·ㆍ]구청장(?:은|이|의)?",
    r"(?:시[\s·ㆍ])?도지사(?:는|가|의)?",
    r"(?:기후에너지)?환경부장관(?:은|이|의)?",
    r"국토교통부장관(?:은|이|의)?",
    r"고용노동부장관(?:은|이|의)?",
    r"행정안전부장관(?:은|이|의)?",
    r"설치자(?:는|가|의)?",
    r"소유자(?:는|가|의)?",
    r"(?:건축|시공|설계|감리)(?:자|사)(?:는|가|의)?",
    r"발주(?:자|처)(?:는|가|의)?",
    r"수급인(?:은|이|의)?",
    r"도급인(?:은|이|의)?",
    r"관계인(?:은|이|에게)?",
    r"[가-힣]{1,20}(?:하는|한)\s*자(?:는|가|에게)?",
]

# 대상 표현 (원문 그대로)
TARGET_FULL = [
    r"안전[\s·ㆍ]?보건\s*관리\s*체제",
    r"안전보건\s*교육", r"안전보건\s*관리\s*규정",
    r"유해[\s·ㆍ]?위험\s*방지\s*계획서",
    r"작업\s*환경\s*측정", r"건강\s*진단", r"안전\s*검사",
    r"물질\s*안전\s*보건\s*자료", r"위험성\s*평가",
    r"산업\s*재해\s*발생\s*기록", r"안전[\s·ㆍ]?보건\s*표지",
    r"보호구", r"안전\s*장치", r"방호\s*장치",
    r"소방\s*시설", r"소방\s*대상물", r"성능위주설계",
    r"경보\s*설비", r"피난\s*설비", r"소화\s*설비",
]


# ── 추출 함수 ─────────────────────────────────────────

def _extract(
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


def _dedup_overlapping(tokens: list[EvidenceToken]) -> list[EvidenceToken]:
    """겹치는 span → 긴 매칭 우선. 다른 타입이어도 완전 포함이면 긴 것 유지."""
    if not tokens:
        return tokens
    sorted_t = sorted(tokens, key=lambda t: (t.span_start, -(t.span_end - t.span_start)))
    result = []
    for tok in sorted_t:
        # 이전 토큰에 완전히 포함되면 제거
        if result and tok.span_start >= result[-1].span_start and tok.span_end <= result[-1].span_end:
            continue
        result.append(tok)
    return result


# ── 메인 추출 ──────────────────────────────────────────

def extract_evidence(part_id: str, source_text: str) -> PartResult:
    result = PartResult(part_id=part_id, source_text=source_text)

    if not source_text or not source_text.strip():
        # 빈 텍스트도 100% 매핑 유지
        result.validation_status = "PASS"
        result.candidates.append(EvidenceCandidate(
            part_id=part_id, candidate_type="UNKNOWN",
            candidate_value="EMPTY_SOURCE", status="UNRESOLVED",
            reason="source_text 비어있음",
        ))
        return result

    text = source_text.strip()
    protected = _find_protected_spans(text)

    # 참조/별표는 보호 영역 자체를 추출 (protected 적용 안 함)
    result.tokens.extend(_extract(text, part_id, REFERENCE_FULL, "REFERENCE_TOKEN"))
    result.tokens.extend(_extract(text, part_id, ATTACHMENT_FULL, "ATTACHMENT_TOKEN"))

    # 나머지는 「」 내부 제외, 전체 표현 보전
    result.tokens.extend(_extract(text, part_id, OBLIGATION_FULL, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, OBLIGATION_ITEM, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, PROHIBITION_FULL, "PROHIBITION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, AUTHORITY_FULL, "AUTHORITY_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, DEFINITION_FULL, "DEFINITION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, DELEGATION_FULL, "DELEGATION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, CONDITION_FULL, "CONDITION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, EXCEPTION_FULL, "EXCEPTION_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, FREQUENCY_FULL, "FREQUENCY_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, DEADLINE_FULL, "DEADLINE_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, ACTOR_FULL, "ACTOR_TOKEN", protected))
    result.tokens.extend(_extract(text, part_id, TARGET_FULL, "TARGET_TOKEN", protected))

    # 겹치는 토큰 제거 (긴 매칭 우선, 타입 무관)
    result.tokens = _dedup_overlapping(result.tokens)

    # span 검증: 원문 일치 이중 확인
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

    # 후보 생성 (원문 그대로, 확정 아님)
    result.candidates = _build_candidates(part_id, result.tokens)

    # 관계 후보
    result.relations = _build_relations(part_id, result.candidates, result.tokens)

    # 100% 매핑: 토큰 없어도 원문 링크 유지
    if not result.tokens and not result.issues:
        result.candidates.append(EvidenceCandidate(
            part_id=part_id, candidate_type="UNKNOWN",
            candidate_value="NO_TOKEN_FOUND", status="UNRESOLVED",
            reason="패턴 매칭 토큰 없음, 원문 보전",
        ))

    # 검증 상태
    if result.issues:
        result.validation_status = "FAIL"
    else:
        result.validation_status = "PASS"

    return result


def _build_candidates(part_id: str, tokens: list[EvidenceToken]) -> list[EvidenceCandidate]:
    candidates = []
    seen = set()
    TYPE_MAP = {
        "ACTOR_TOKEN": "ACTOR", "OBLIGATION_TOKEN": "OBLIGATION_TYPE",
        "PROHIBITION_TOKEN": "PROHIBITION_TYPE", "AUTHORITY_TOKEN": "AUTHORITY_TYPE",
        "DEFINITION_TOKEN": "DEFINITION_TYPE", "DELEGATION_TOKEN": "DELEGATION_TYPE",
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
            candidate_value=tok.value,  # 원문 그대로
            status="CANDIDATE",
        ))
    return candidates


def _build_relations(
    part_id: str, candidates: list[EvidenceCandidate], tokens: list[EvidenceToken],
) -> list[EvidenceRelation]:
    actors = [c for c in candidates if c.candidate_type == "ACTOR"]
    obligations = [c for c in candidates if c.candidate_type in ("OBLIGATION_TYPE", "PROHIBITION_TYPE", "AUTHORITY_TYPE")]
    conditions = [c for c in candidates if c.candidate_type == "CONDITION"]
    exceptions = [c for c in candidates if c.candidate_type == "EXCEPTION"]
    targets = [c for c in candidates if c.candidate_type == "TARGET"]

    if not actors and not obligations:
        return []

    # 주체: 문장 시작 가장 가까운 것
    actor_tokens = sorted(
        [t for t in tokens if t.token_type == "ACTOR_TOKEN"],
        key=lambda t: t.span_start,
    )
    first_actor = actor_tokens[0].value if actor_tokens else None

    return [EvidenceRelation(
        part_id=part_id,
        actor_candidate=first_actor,
        action_candidate=obligations[0].candidate_value if obligations else None,
        target_candidate=targets[0].candidate_value if targets else None,
        condition_candidate=conditions[0].candidate_value if conditions else None,
        exception_candidate=exceptions[0].candidate_value if exceptions else None,
        status="CANDIDATE" if first_actor and obligations else "UNRESOLVED",
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
            logger.warning("evidence_token INSERT: %s", e)

    for cand in result.candidates:
        try:
            cur.execute("""
                INSERT INTO evidence_candidate (part_id, candidate_type, candidate_value, status, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (cand.part_id, cand.candidate_type, cand.candidate_value, cand.status, cand.reason))
            saved["candidates"] += 1
        except Exception as e:
            logger.warning("evidence_candidate INSERT: %s", e)

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
            logger.warning("evidence_relation INSERT: %s", e)

    try:
        cur.execute("""
            INSERT INTO evidence_validation (part_id, validation_status, total_tokens, valid_tokens, issues)
            VALUES (%s, %s, %s, %s, %s)
        """, (result.part_id, result.validation_status,
              len(result.tokens) + len(result.issues), len(result.tokens),
              json.dumps([{"type": i.issue_type, "detail": i.detail} for i in result.issues], ensure_ascii=False)))
        saved["validations"] += 1
    except Exception as e:
        logger.warning("evidence_validation INSERT: %s", e)

    for iss in result.issues:
        try:
            cur.execute("""
                INSERT INTO evidence_issue (part_id, issue_type, detail, source_text)
                VALUES (%s, %s, %s, %s)
            """, (iss.part_id, iss.issue_type,
                  json.dumps(iss.detail, ensure_ascii=False), iss.source_text))
            saved["issues"] += 1
        except Exception as e:
            logger.warning("evidence_issue INSERT: %s", e)

    conn.commit()
    cur.close()
    return saved
