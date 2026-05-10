"""증거 기반 법령 파싱 엔진 — Evidence Token 추출 v2.

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


# ── 보호 영역 ─────────────────────────────────────────

def _find_protected_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in re.finditer(r"「[^」]+」", text):
        spans.append((m.start(), m.end()))
    return spans


def _is_inside_protected(start: int, end: int, protected: list[tuple[int, int]]) -> bool:
    for ps, pe in protected:
        if start >= ps and end <= pe:
            return True
    return False


# ── 패턴 정의 v2 (대폭 보강) ─────────────────────────

OBLIGATION_PATTERNS = [
    r"하여야\s*한다",
    r"해야\s*한다",
    r"하여야\s*합니다",
    r"의무가\s*있다",
    r"지켜야\s*한다",
    r"이행하여야\s*한다",
    r"준수하여야\s*한다",
    r"따라야\s*한다",
    r"할\s*것",           # 호 단위 의무 항목
]

PROHIBITION_PATTERNS = [
    r"할\s*수\s*없다",
    r"하여서는\s*아니\s*된다",
    r"아니\s*된다",
    r"금지\s*한다",
    r"못한다",
    r"안\s*된다",
]

AUTHORITY_PATTERNS = [
    r"할\s*수\s*있다",
]

DEFINITION_PATTERNS = [
    r"이라\s*한다",
    r"을\s*말한다",
    r"를\s*말한다",
    r"말한다",
]

DELEGATION_PATTERNS = [
    r"대통령령으로\s*정한다",
    r"(?:부|총리)령으로\s*정한다",
    r"고용노동부령으로\s*정한다",
    r"기후에너지환경부령으로\s*정한다",
    r"국토교통부령으로\s*정한다",
    r"으로\s*정한다",
]

CONDITION_PATTERNS = [
    r"경우에는",
    r"경우에",
    r"때에는",
    r"때에",
    r"인\s*경우",
    r"하는\s*경우",
    r"한\s*경우",
]

EXCEPTION_PATTERNS = [
    r"^다만[\s,]",
    r"^단[\s,]",
    r"제외한다",
    r"적용하지\s*아니한다",
    r"그러하지\s*아니하다",
]

FREQUENCY_PATTERNS = [
    r"정기적으로",
    r"매년",
    r"매\s*\d+\s*년",
    r"분기마다",
    r"반기마다",
    r"월\s*\d+\s*회",
    r"\d+년마다",
    r"\d+회\s*이상",
    r"수시로",
]

DEADLINE_PATTERNS = [
    r"\d+일\s*이내",
    r"\d+개월\s*이내",
    r"\d+년\s*이내",
    r"\d+일\s*까지",
    r"\d+개월\s*까지",
    r"\d+년\s*까지",
    r"\d+일\s*전",
    r"지체\s*없이",
    r"즉시",
]

REFERENCE_PATTERNS = [
    r"제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?",
    r"「[^」]+」",
]

ATTACHMENT_PATTERNS = [
    r"별표\s*제?\s*\d+",
    r"별지\s*제?\s*\d+",
    r"별표",
    r"별지",
]

# 행위 키워드 v2 (대폭 보강)
ACTION_KEYWORDS = [
    # 안전 관련
    "점검", "검사", "측정", "평가", "진단", "조사", "확인", "감시", "감독", "모니터링",
    # 보고/신고
    "보고", "신고", "통보", "통지", "알림", "제출", "보고서",
    # 설치/관리
    "설치", "관리", "유지", "보수", "교체", "정비", "보전", "보관", "저장",
    # 교육/훈련
    "교육", "훈련", "지도",
    # 인허가
    "승인", "허가", "등록", "지정", "인가", "인증", "면허",
    # 변경/취소
    "변경", "폐지", "취소", "정지", "철회", "해제",
    # 시정/개선
    "시정", "개선", "방지", "예방", "조치", "대책",
    # 작성/기록
    "작성", "기록", "비치", "보존", "공표", "게시", "공고", "고시",
    # 인사
    "배치", "선임", "해임", "위촉",
    # 제공/공급
    "제공", "공급", "지급", "지원", "배부",
    # 수행
    "실시", "이행", "수행", "시행", "준수", "적용",
    # 처리
    "처리", "수거", "운반", "배출", "처분",
    # 기타
    "명령", "요청", "권고", "협조", "협의",
]

# 주체 패턴 v2 (보강)
ACTOR_PATTERNS = [
    r"사업주(?:는|가|의|에게)?",
    r"근로자(?:는|가|의|에게)?",
    r"관리(?:자|인|책임자)(?:는|가|의|에게)?",
    r"안전관리(?:자|책임자)(?:는|가|의)?",
    r"보건관리(?:자|책임자)(?:는|가|의)?",
    r"안전보건관리(?:자|책임자|담당자)(?:는|가|의)?",
    r"시장[\s·]군수[\s·]구청장(?:은|이|의)?",
    r"(?:시[\s·])?도지사(?:는|가|의)?",
    r"(?:기후에너지)?환경부장관(?:은|이|의)?",
    r"국토교통부장관(?:은|이|의)?",
    r"고용노동부장관(?:은|이|의)?",
    r"소방청장(?:은|이|의)?",
    r"설치자(?:는|가|의)?",
    r"소유자(?:는|가|의)?",
    r"(?:건축|시공|설계|감리)(?:자|사)(?:는|가|의)?",
    r"발주(?:자|처)(?:는|가|의)?",
    r"수급인(?:은|이|의)?",
    r"도급인(?:은|이|의)?",
    r"(?:하|받)는\s*자(?:는|가|에게)?",  # "~하는 자"
    r"관계인(?:은|이|에게)?",
]

# 대상 패턴 (행위의 목적어 후보)
TARGET_PATTERNS = [
    r"안전[\s·]보건\s*관리\s*체제",
    r"안전보건\s*교육",
    r"안전보건\s*관리\s*규정",
    r"유해[\s·]?위험\s*방지\s*계획서",
    r"작업\s*환경\s*측정",
    r"건강\s*진단",
    r"안전\s*검사",
    r"물질\s*안전\s*보건\s*자료",
    r"위험성\s*평가",
    r"산업\s*재해\s*발생\s*기록",
    r"안전[\s·]?보건\s*표지",
    r"보호구",
    r"안전\s*장치",
    r"방호\s*장치",
    r"안전\s*난간",
    r"소화\s*설비",
    r"경보\s*설비",
    r"피난\s*설비",
    r"소방\s*시설",
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


def _dedup_overlapping(tokens: list[EvidenceToken]) -> list[EvidenceToken]:
    """같은 위치에서 짧은 패턴과 긴 패턴이 겹치면 긴 것만 유지."""
    if not tokens:
        return tokens
    sorted_toks = sorted(tokens, key=lambda t: (t.span_start, -(t.span_end - t.span_start)))
    result = []
    for tok in sorted_toks:
        if result and tok.span_start >= result[-1].span_start and tok.span_end <= result[-1].span_end:
            if tok.token_type == result[-1].token_type:
                continue  # 같은 타입이면서 더 짧은 매칭 → 제거
        result.append(tok)
    return result


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

    # 참조/별표는 보호 영역 자체를 추출
    result.tokens.extend(_extract_by_patterns(text, part_id, REFERENCE_PATTERNS, "REFERENCE_TOKEN"))
    result.tokens.extend(_extract_by_patterns(text, part_id, ATTACHMENT_PATTERNS, "ATTACHMENT_TOKEN"))

    # 나머지는 「」 내부 제외
    result.tokens.extend(_extract_by_patterns(text, part_id, OBLIGATION_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, PROHIBITION_PATTERNS, "PROHIBITION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, AUTHORITY_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, DEFINITION_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, DELEGATION_PATTERNS, "OBLIGATION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, CONDITION_PATTERNS, "CONDITION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, EXCEPTION_PATTERNS, "EXCEPTION_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, FREQUENCY_PATTERNS, "FREQUENCY_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, DEADLINE_PATTERNS, "DEADLINE_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, ACTOR_PATTERNS, "ACTOR_TOKEN", protected))
    result.tokens.extend(_extract_by_patterns(text, part_id, TARGET_PATTERNS, "TARGET_TOKEN", protected))
    result.tokens.extend(_extract_action_tokens(text, part_id, protected))

    # 겹치는 토큰 제거 (같은 타입에서 긴 매칭 우선)
    result.tokens = _dedup_overlapping(result.tokens)

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
    result.relations = _build_relations(part_id, result.candidates, result.tokens)

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


def _build_relations(
    part_id: str, candidates: list[EvidenceCandidate], tokens: list[EvidenceToken],
) -> list[EvidenceRelation]:
    """관계 후보 생성. 문장 시작에 가장 가까운 주체를 우선."""
    actors = [c for c in candidates if c.candidate_type == "ACTOR"]
    actions = [c for c in candidates if c.candidate_type == "ACTION"]
    targets = [c for c in candidates if c.candidate_type == "TARGET"]
    conditions = [c for c in candidates if c.candidate_type == "CONDITION"]
    exceptions = [c for c in candidates if c.candidate_type == "EXCEPTION"]

    if not actors and not actions:
        return []

    # 주체: 문장 시작에 가장 가까운 ACTOR_TOKEN
    actor_tokens = sorted(
        [t for t in tokens if t.token_type == "ACTOR_TOKEN"],
        key=lambda t: t.span_start,
    )
    first_actor = actor_tokens[0].value if actor_tokens else None

    return [EvidenceRelation(
        part_id=part_id,
        actor_candidate=first_actor,
        action_candidate=actions[0].candidate_value if actions else None,
        target_candidate=targets[0].candidate_value if targets else None,
        condition_candidate=conditions[0].candidate_value if conditions else None,
        exception_candidate=exceptions[0].candidate_value if exceptions else None,
        status="CANDIDATE" if first_actor and actions else "UNRESOLVED",
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
