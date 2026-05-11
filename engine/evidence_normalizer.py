"""증거 기반 법령 파싱 — Stage 2 정규화 (Normalizer).

원문 토큰 → canonical token → family candidate.
정규화는 "의미 확정"이 아니라 "검증 가능한 후보 기호화".

규칙:
1. raw_token은 원문 그대로 보존.
2. canonical_token은 raw_token에서 기계적으로 도출 가능해야 함.
3. family는 registry 기반 후보일 뿐, 확정 아님.
4. 모르면 UNRESOLVED로 남김.
5. 판단 개입 최소화. 모든 결과는 후보군.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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
    family_status: str  # CANDIDATE / UNRESOLVED
    span_start: int | None = None
    span_end: int | None = None


# ── 기계적 분리 규칙 ──────────────────────────────────

# 동사+어미 분리 (기계적, stem이 2자 이상일 때만)
VERB_ENDINGS = [
    r"(하여야\s*한다)$",
    r"(해야\s*한다)$",
    r"(하여야\s*합니다)$",
    r"(하여야\s*하며)$",
    r"(지켜야\s*한다)$",
    r"(따라야\s*한다)$",
    r"(할\s*수\s*있다)$",
    r"(할\s*수\s*없다)$",
    r"(하여서는\s*아니\s*된다)$",
    r"(아니\s*된다)$",
    r"(금지\s*한다)$",
    r"(할\s*것)$",
    r"(을\s*말한다)$",
    r"(를\s*말한다)$",
    r"(이라\s*한다)$",
    r"(라\s*한다)$",
]

# 주체 조사 (기계적 제거)
ACTOR_PARTICLES = re.compile(r"(은|는|이|가|의|에게|와|또는|에게서)\s*$")


def _try_split_verb_ending(raw: str) -> tuple[str, str] | None:
    """동사+어미 분리 시도. stem이 2자 미만이면 분리 안 함."""
    text = raw.strip()
    for pattern in VERB_ENDINGS:
        m = re.search(pattern, text)
        if m:
            stem = text[:m.start()].strip()
            ending = m.group(1).strip()
            if len(stem) >= 2:  # stem이 너무 짧으면 분리 부적절
                return stem, ending
    return None


def _strip_particle(raw: str) -> str:
    """조사 제거 (기계적)."""
    return ACTOR_PARTICLES.sub("", raw.strip()).strip()


# ── Registry ──────────────────────────────────────────

def load_registry(conn) -> dict[str, list[dict[str, str]]]:
    cur = conn.cursor()
    cur.execute("SELECT token_type, canonical_token, family FROM token_family_registry")
    registry: dict[str, list[dict[str, str]]] = {}
    for token_type, canonical, family in cur.fetchall():
        registry.setdefault(canonical, []).append({"token_type": token_type, "family": family})
    cur.close()
    return registry


def _lookup(registry: dict, canonical: str) -> tuple[str | None, str]:
    """registry 조회. 있으면 CANDIDATE, 없으면 UNRESOLVED."""
    entries = registry.get(canonical)
    if entries:
        return entries[0]["family"], "CANDIDATE"
    return None, "UNRESOLVED"


def _lookup_partial(registry: dict, text: str, keywords: list[str]) -> tuple[str | None, str]:
    """text 안에 포함된 키워드로 재조회."""
    for kw in keywords:
        if kw in text:
            family, status = _lookup(registry, kw)
            if family:
                return family, status
    return None, "UNRESOLVED"


# ── 메인 정규화 ───────────────────────────────────────

def normalize_tokens(
    conn, part_id: str, tokens: list[dict[str, Any]], registry: dict,
) -> list[NormalizedToken]:
    """모든 토큰에 동일한 처리. 판단 개입 최소화.

    1. 동사+어미 표현 → 기계적 분리 시도 (stem 2자 이상만)
    2. 주체 표현 → 조사 제거 (기계적)
    3. 나머지 → 그대로 유지 (IDENTITY)
    4. registry 조회 → 있으면 CANDIDATE, 없으면 UNRESOLVED
    """
    results: list[NormalizedToken] = []

    for tok in tokens:
        token_id = tok.get("id")
        token_type = tok.get("token_type", "")
        raw = tok.get("value", "")
        span_s = tok.get("span_start")
        span_e = tok.get("span_end")

        # Step 1: 동사+어미 분리 시도 (모든 타입 공통)
        split = _try_split_verb_ending(raw)
        if split:
            stem, ending = split
            # stem → registry 조회
            family_s, status_s = _lookup(registry, stem)
            results.append(NormalizedToken(
                token_id=token_id, part_id=part_id,
                raw_token=raw, canonical_token=stem,
                normalization_type="LEXICAL",
                family=family_s, family_status=status_s,
                span_start=span_s, span_end=span_e,
            ))
            # ending → registry 조회
            family_e, status_e = _lookup(registry, ending)
            results.append(NormalizedToken(
                token_id=token_id, part_id=part_id,
                raw_token=raw, canonical_token=ending,
                normalization_type="LEXICAL",
                family=family_e, family_status=status_e,
                span_start=span_s, span_end=span_e,
            ))
            continue

        # Step 2: 주체 표현 → 조사 제거
        if token_type == "ACTOR_TOKEN":
            canonical = _strip_particle(raw)
            family, status = _lookup(registry, canonical)
            results.append(NormalizedToken(
                token_id=token_id, part_id=part_id,
                raw_token=raw, canonical_token=canonical,
                normalization_type="PARTICLE_STRIP",
                family=family, family_status=status,
                span_start=span_s, span_end=span_e,
            ))
            continue

        # Step 3: 그대로 유지 + registry 조회
        canonical = raw.strip()
        family, status = _lookup(registry, canonical)

        # 기한/주기는 부분 키워드로 재조회 (기계적)
        if status == "UNRESOLVED" and token_type in ("DEADLINE_TOKEN", "FREQUENCY_TOKEN"):
            family, status = _lookup_partial(
                registry, canonical,
                ["이내", "까지", "전", "지체 없이", "즉시", "정기적으로", "매년", "수시로"],
            )

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
