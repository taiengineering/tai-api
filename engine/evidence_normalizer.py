"""증거 기반 법령 파싱 — Stage 2 정규화 (Normalizer).

원문 토큰 → canonical token → family candidate.
정규화는 "의미 확정"이 아니라 "검증 가능한 후보 기호화".

규칙:
1. raw_token은 원문 그대로 보존.
2. canonical_token은 raw_token에서 기계적으로 도출 가능해야 함.
3. family는 registry 기반 후보일 뿐, 확정 아님.
4. 모르면 UNRESOLVED로 남김.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NormalizedToken:
    token_id: str | None
    part_id: str
    raw_token: str
    canonical_token: str
    normalization_type: str  # LEXICAL / IDENTITY / PARTICLE_STRIP
    family: str | None
    family_status: str  # CANDIDATE / UNRESOLVED / FAIL
    span_start: int | None = None
    span_end: int | None = None


# ── 어미 분리 패턴 ────────────────────────────────────

# 의무/금지/권한 어미 (동사에서 분리)
VERB_ENDINGS = [
    (r"^(.+?)(하여야\s*한다)$", "하여야 한다"),
    (r"^(.+?)(해야\s*한다)$", "해야 한다"),
    (r"^(.+?)(하여야\s*합니다)$", "하여야 합니다"),
    (r"^(.+?)(하여야\s*하며)$", "하여야 하며"),
    (r"^(.+?)(지켜야\s*한다)$", "지켜야 한다"),
    (r"^(.+?)(따라야\s*한다)$", "따라야 한다"),
    (r"^(.+?)(할\s*수\s*있다)$", "할 수 있다"),
    (r"^(.+?)(할\s*수\s*없다)$", "할 수 없다"),
    (r"^(.+?)(하여서는\s*아니\s*된다)$", "아니 된다"),
    (r"^(.+?)(아니\s*된다)$", "아니 된다"),
    (r"^(.+?)(금지\s*한다)$", "금지 한다"),
    (r"^(.+?)(할\s*것)$", "할 것"),
    (r"^(.+?)(을\s*말한다)$", "말한다"),
    (r"^(.+?)(를\s*말한다)$", "말한다"),
    (r"^(.+?)(이라\s*한다)$", "이라 한다"),
    (r"^(.+?)(라\s*한다)$", "라 한다"),
]

# 주체 조사 제거
ACTOR_PARTICLES = re.compile(r"(은|는|이|가|의|에게|와|또는|에게서)\s*$")

# 조건 표현에서 핵심 추출
CONDITION_CORE = re.compile(r"^(.+?)((?:하는|한|인)\s*(?:경우에는|경우에|경우|때에는|때에))$")


def _split_verb_ending(raw: str) -> tuple[str, str] | None:
    """동사+어미 표현을 (동사 stem, 어미)로 분리."""
    for pattern, ending_label in VERB_ENDINGS:
        m = re.match(pattern, raw.strip())
        if m and m.group(1).strip():
            return m.group(1).strip(), m.group(2).strip()
    return None


def _strip_actor_particle(raw: str) -> str:
    """주체 표현에서 조사 제거 → canonical."""
    return ACTOR_PARTICLES.sub("", raw.strip()).strip()


def _canonicalize_condition(raw: str) -> str:
    """조건 표현 그대로 유지 (의미 변경 안 함)."""
    return raw.strip()


# ── Registry 로드 ─────────────────────────────────────

def load_registry(conn) -> dict[str, list[dict[str, str]]]:
    """token_family_registry → {canonical_token: [{family, token_type}]}"""
    cur = conn.cursor()
    cur.execute("SELECT token_type, canonical_token, family FROM token_family_registry")
    registry: dict[str, list[dict[str, str]]] = {}
    for token_type, canonical, family in cur.fetchall():
        registry.setdefault(canonical, []).append({"token_type": token_type, "family": family})
    cur.close()
    return registry


def _lookup_family(registry: dict, canonical: str) -> tuple[str | None, str]:
    """registry에서 family 찾기. 없으면 UNRESOLVED."""
    entries = registry.get(canonical)
    if entries:
        return entries[0]["family"], "CANDIDATE"
    return None, "UNRESOLVED"


# ── 메인 정규화 ───────────────────────────────────────

def normalize_tokens(
    conn, part_id: str, tokens: list[dict[str, Any]], registry: dict,
) -> list[NormalizedToken]:
    """evidence_token rows → NormalizedToken 리스트.

    OBLIGATION/PROHIBITION/AUTHORITY 토큰: 동사+어미 분리 → 각각 canonical + family.
    ACTOR 토큰: 조사 제거 → canonical.
    나머지: 그대로 유지 (IDENTITY).
    """
    results: list[NormalizedToken] = []

    for tok in tokens:
        token_id = tok.get("id")
        token_type = tok.get("token_type", "")
        raw = tok.get("value", "")
        span_s = tok.get("span_start")
        span_e = tok.get("span_end")

        if token_type in ("OBLIGATION_TOKEN", "PROHIBITION_TOKEN", "AUTHORITY_TOKEN"):
            # 동사+어미 분리
            split = _split_verb_ending(raw)
            if split:
                verb_stem, ending = split
                # 동사 stem → ACTION family
                family_v, status_v = _lookup_family(registry, verb_stem)
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=verb_stem,
                    normalization_type="LEXICAL",
                    family=family_v, family_status=status_v,
                    span_start=span_s, span_end=span_e,
                ))
                # 어미 → OBLIGATION family
                family_e, status_e = _lookup_family(registry, ending)
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=ending,
                    normalization_type="LEXICAL",
                    family=family_e, family_status=status_e,
                    span_start=span_s, span_end=span_e,
                ))
            else:
                # 분리 불가 → 그대로
                family, status = _lookup_family(registry, raw.strip())
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=raw.strip(),
                    normalization_type="IDENTITY",
                    family=family, family_status=status,
                    span_start=span_s, span_end=span_e,
                ))

        elif token_type == "ACTOR_TOKEN":
            canonical = _strip_actor_particle(raw)
            family, status = _lookup_family(registry, canonical)
            results.append(NormalizedToken(
                token_id=token_id, part_id=part_id,
                raw_token=raw, canonical_token=canonical,
                normalization_type="PARTICLE_STRIP",
                family=family, family_status=status,
                span_start=span_s, span_end=span_e,
            ))

        elif token_type == "DEFINITION_TOKEN":
            split = _split_verb_ending(raw)
            if split:
                noun_part, ending = split
                family_e, status_e = _lookup_family(registry, ending)
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=noun_part,
                    normalization_type="LEXICAL",
                    family=None, family_status="CANDIDATE",
                    span_start=span_s, span_end=span_e,
                ))
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=ending,
                    normalization_type="LEXICAL",
                    family=family_e, family_status=status_e,
                    span_start=span_s, span_end=span_e,
                ))
            else:
                results.append(NormalizedToken(
                    token_id=token_id, part_id=part_id,
                    raw_token=raw, canonical_token=raw.strip(),
                    normalization_type="IDENTITY",
                    family=None, family_status="UNRESOLVED",
                    span_start=span_s, span_end=span_e,
                ))

        else:
            # REFERENCE, ATTACHMENT, CONDITION, EXCEPTION, FREQUENCY, DEADLINE, TARGET, DELEGATION
            # → 그대로 유지, registry 매칭 시도
            canonical = raw.strip()
            family, status = _lookup_family(registry, canonical)
            # DEADLINE/FREQUENCY는 핵심 키워드로 재매칭
            if status == "UNRESOLVED" and token_type in ("DEADLINE_TOKEN", "FREQUENCY_TOKEN"):
                for key in ("이내", "까지", "전", "지체 없이", "즉시", "정기적으로", "매년", "수시로"):
                    if key in canonical:
                        family, status = _lookup_family(registry, key)
                        if family:
                            break
            results.append(NormalizedToken(
                token_id=token_id, part_id=part_id,
                raw_token=raw, canonical_token=canonical,
                normalization_type="IDENTITY",
                family=family, family_status=status,
                span_start=span_s, span_end=span_e,
            ))

    return results


# ── DB 저장 ────────────────────────────────────────────

def save_normalized(conn, results: list[NormalizedToken]) -> int:
    cur = conn.cursor()
    saved = 0
    for n in results:
        try:
            cur.execute("""
                INSERT INTO evidence_normalized
                    (token_id, part_id, raw_token, canonical_token, normalization_type,
                     family, family_status, source_span_start, source_span_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(n.token_id) if n.token_id else None, n.part_id,
                n.raw_token, n.canonical_token, n.normalization_type,
                n.family, n.family_status, n.span_start, n.span_end,
            ))
            saved += 1
        except Exception as e:
            logger.warning("evidence_normalized INSERT: %s", e)
    conn.commit()
    cur.close()
    return saved
